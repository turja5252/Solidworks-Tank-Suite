"""Spiral stair on the tank: shell, two climbing stringers, pan treads, bolts.

The stringers are rolled 3/8 in sheet-metal plates cut to the lisp burn
outline, so each one flattens to that outline. Each tread is a five-face
pan (top and four walls, no bottom) centered between the stringers with 1/16 in
clear each side. The two 7/16 in bolts per side are located from the tread's
front face in the side profile and cut separately through the inner stringer
and the outer stringer into that tread's end wall.

Geometry: Y up, tank axis at X = Z = 0. The helix starts at +Z and turns
toward -X. Position at angle a is (-R sin a, y, R cos a).
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import BuildStopped, SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rename_feature
from swauto.parts import extrude_blind, new_part
from swauto.stair.development import (
    END_HOLE_RADIUS_IN,
    SLOT_LENGTH_IN,
    DevelopedStringer,
    develop_both,
    flight_step,
    flight_treads,
)
from swauto.stair.stringer import (
    BOLT_DIA_IN,
    BOLT_FROM_FRONT_IN,
    BOLT_SPACE_IN,
    BOLT_UP_IN,
    CLEAR_IN,
    THICKNESS_IN,
    TREAD_DEPTH_IN,
    TREAD_MARK_IN,
    TREAD_PLATE_IN,
    StringerMock,
    layout_stringer,
)
from swauto.stair.stringer_sw import (
    _create_circle,
    _delete_named,
    _keep_bent_view,
    _names,
    _rename_new,
    _select_feature,
)
from swauto.tank.profile import course_radii_m
from swauto.tank.shell import (
    _clear_selection,
    _close_sketch,
    _delete_feature,
    _feature_name,
    _open_sketch,
    create_tank_shell,
)
from swauto.tank.spec import WALL_OD, TankSpec

if TYPE_CHECKING:
    from swauto.stair.grab_sw import GrabRail

_INCH = 0.0254
TREAD_CLEAR_IN = (CLEAR_IN - TREAD_PLATE_IN) / 2.0
# swUserPreferenceToggle_e.swUserEnableFreezeBar, swMoveFreezeBarTo_e.swMoveFreezeBarToAfterFeature
_SW_ENABLE_FREEZE_BAR = 461
_SW_FREEZE_AFTER_FEATURE = 3


class StairResult:
    def __init__(self, title: str, model, note: str) -> None:
        self.title = title
        self.model = model
        self.note = note


@dataclass(frozen=True)
class TreadPlace:
    index: int
    phi: float
    y0: float
    y1: float
    center: tuple[float, float, float]


def create_stair(
    app, stair: StringerMock, wall_in: float, progress=None, *, shell: bool = True, platforms: int = 0,
    top_platform: bool = False, posts: tuple[int, ...] = (), platform_post_in: float | None = None,
    top_rail: bool = False, mid_rail: bool = False, platform_mid_top: float | None = None,
    grab: GrabRail | None = None,
) -> StairResult:
    """New part, then the stair. ``shell`` adds the tank; the stringers do not change.

    ``platforms`` mid platforms split the stair into equal flights, and
    ``top_platform`` puts the same platform past the top tread. ``posts`` are
    the treads in each flight that get a handrail post on the outer stringer;
    ``platform_post_in`` sets the platform posts in from the platform ends, and
    ``top_rail`` and ``mid_rail`` run the outer top rail and midrail along the posts,
    the midrail ``platform_mid_top`` over each platform's grating. ``grab`` runs the
    outer grab rail on the flight posts.
    """
    flight_treads(stair.treads, platforms)
    profiles = _platform_profiles(app) if platforms or top_platform else None
    post_file = _post_profile(app) if posts else None
    if shell:
        return create_stair_on_tank(
            app, stair, wall_in, progress=progress, platforms=platforms, top_platform=top_platform, profiles=profiles,
            posts=posts, post_profile=post_file, platform_post_in=platform_post_in, top_rail=top_rail,
            mid_rail=mid_rail, platform_mid_top=platform_mid_top, grab=grab,
        )
    stair.validate()
    if wall_in <= 0 or wall_in >= TREAD_MARK_IN or wall_in * 2 >= TREAD_DEPTH_IN:
        raise ValueError("Pan wall must be greater than zero and thinner than the tread.")
    model = new_part(app)
    return build_stair_on_model(
        model, stair.shell_od_in, stair, wall_in, progress=progress, platforms=platforms,
        top_platform=top_platform, profiles=profiles, posts=posts, post_profile=post_file,
        platform_post_in=platform_post_in, top_rail=top_rail, mid_rail=mid_rail, platform_mid_top=platform_mid_top,
        grab=grab,
    )


def create_stair_on_tank(
    app, stair: StringerMock, wall_in: float, progress=None, *, platforms: int = 0, top_platform: bool = False,
    profiles: tuple[str, str, str] | None = None, posts: tuple[int, ...] = (), post_profile: str | None = None,
    platform_post_in: float | None = None, top_rail: bool = False, mid_rail: bool = False,
    platform_mid_top: float | None = None, grab: GrabRail | None = None,
) -> StairResult:
    """New part with the shell at the Stringer tab's OD radius, then the stair."""
    stair.validate()
    if wall_in <= 0 or wall_in >= TREAD_MARK_IN or wall_in * 2 >= TREAD_DEPTH_IN:
        raise ValueError("Pan wall must be greater than zero and thinner than the tread.")
    if profiles is None and (platforms or top_platform):
        profiles = _platform_profiles(app)
    if post_profile is None and posts:
        post_profile = _post_profile(app)
    tank = TankSpec(diameter_in=2.0 * stair.shell_od_in, diameter_basis=WALL_OD)
    shell = create_tank_shell(app, tank)
    model = shell.live.model
    outer_m, _inner_m = course_radii_m(tank, tank.active_courses()[0])
    shell_od = outer_m / _INCH
    _progress(progress, "shell built")
    return build_stair_on_model(
        model, shell_od, stair, wall_in, progress=progress, platforms=platforms, top_platform=top_platform,
        profiles=profiles, posts=posts, post_profile=post_profile, platform_post_in=platform_post_in,
        top_rail=top_rail, mid_rail=mid_rail, platform_mid_top=platform_mid_top, grab=grab,
    )


def _platform_profiles(app) -> tuple[str, str, str]:
    """C4x5.4 for the platform frames, L6x6x3/8 for the stringer clips, L3x3x3/8 for the knee braces."""
    from swauto.stair.brace_sw import angle_profile
    from swauto.stair.platform_sw import clip_profile, platform_profile

    return platform_profile(app), clip_profile(app), angle_profile(app)


def _post_profile(app) -> str:
    """L2x2x1/4 for the handrail posts."""
    from swauto.stair.post_sw import post_profile

    return post_profile(app)


def _progress(callback, text: str) -> None:
    if callback is None:
        return
    try:
        callback(text)
    except BuildStopped:
        raise
    except Exception:  # noqa: BLE001
        pass


def build_stair_on_model(
    model,
    shell_od: float,
    stair: StringerMock,
    wall_in: float,
    *,
    stringers: bool = True,
    do_treads: bool = True,
    progress=None,
    platforms: int = 0,
    top_platform: bool = False,
    profiles: tuple[str, str, str] | None = None,
    posts: tuple[int, ...] = (),
    post_profile: str | None = None,
    platform_post_in: float | None = None,
    top_rail: bool = False,
    mid_rail: bool = False,
    platform_mid_top: float | None = None,
    grab: GrabRail | None = None,
) -> StairResult:
    """Stringers (unless already there), then tread by tread: pan, inner bolts, outer bolts.

    With ``platforms`` the stair is that many plus one equal flights, each the
    one below turned and raised past a 36 in mid platform. Platform frames and
    their stringer clips go in last: a higher flight's stringer cuts start
    inside the platform below it. ``profiles`` is (C4 frame, 6x6 clip, 3x3 knee).
    Handrail posts at the ``posts`` treads of every flight follow, on ``post_profile``,
    and with ``top_rail`` and ``mid_rail`` the outer top rail and midrail along them,
    and with ``grab`` the grab rail on the flight posts.
    """
    per_flight = flight_treads(stair.treads, platforms)
    flight = StringerMock(
        shell_od_in=shell_od,
        gap_in=stair.gap_in,
        treads=per_flight,
        rise_in=stair.rise_in,
        run_in=stair.run_in,
        plate_width_in=stair.plate_width_in,
    )
    layout = layout_stringer(
        StringerMock(
            shell_od_in=shell_od,
            gap_in=stair.gap_in,
            treads=per_flight,
            rise_in=stair.rise_in,
            run_in=stair.run_in,
            plate_width_in=stair.plate_width_in,
            outside_face=True,
        )
    )
    turn, lift = flight_step(flight)
    offsets = [(k * turn, k * lift) for k in range(platforms + 1)]
    places = [
        _moved_place(place, k * per_flight + place.index, *offsets[k])
        for k in range(platforms + 1)
        for place in _tread_places(layout)
    ]
    platform_note = ""
    post_note = ""
    try:
        if stringers:
            for k, at in enumerate(offsets):
                build_flight_stringers(model, flight, shell_od, at=at, suffix=flight_suffix(k), progress=progress)
            freeze_note = _freeze_stringers(model)
        else:
            freeze_note = ""
        done = 0
        total = 0
        # One tread at a time: the pan, then its inner bolts, then its outer bolts.
        # One rebuild per tread, before the bolts, so a cut is not lost. Not again after each bolt.
        for place in (places if do_treads else []):
            _tread(model, layout, place, wall_in)
            _progress(progress, f"tread {place.index} placed")
            _rebuild(model)
            for side in ("In", "Out"):
                total += 1
                before_bolts = _names(model)
                try:
                    hit = _bolts(model, layout, place, side, wall_in)
                except Exception:
                    # A missed tread bolt must not skip the rest of the pans.
                    _discard_since(model, before_bolts)
                    hit = False
                done += int(hit)
                _progress(progress, f"tread {place.index} {side.lower()} bolts {'through' if hit else 'missed'}")
        if platforms or top_platform:
            if profiles is None:
                raise SolidWorksError("Platforms need the C4, 6x6 angle and 3x3 angle weldment profiles.")
            platform_note = _platforms(
                model, layout, places, per_flight, platforms, top_platform, profiles, shell_od, progress
            )
        if posts:
            if post_profile is None:
                raise SolidWorksError("Handrail posts need the L2x2 angle weldment profile.")
            post_note = _handrail_posts(
                model, layout, places, per_flight, posts, post_profile, platforms, top_platform,
                platform_post_in, top_rail, mid_rail, platform_mid_top, grab, progress,
            )
    except (BuildStopped, SolidWorksError):
        with contextlib.suppress(Exception):
            _hide_construction(model)
        raise
    except Exception as exc:
        with contextlib.suppress(Exception):
            _hide_construction(model)
        raise SolidWorksError(f"Stair failed: {format_com_error(exc)}") from exc
    with contextlib.suppress(Exception):
        _hide_construction(model)
    with contextlib.suppress(Exception):
        model.ShowNamedView2("*Isometric", 7)
        model.ViewZoomtofit2()
        model.ViewDisplayShaded()
        model.GraphicsRedraw2()
    flights = (
        f" in {platforms + 1} flights of {per_flight} around {platforms} mid platform{'s' if platforms > 1 else ''}"
        if platforms else ""
    )
    note = (
        f"Shell OD radius {shell_od:.2f} in, {len(places)} pan treads{flights} with {wall_in:g} in walls, "
        f"top tread at {math.degrees(places[-1].phi):.2f}°, rise {stair.treads * stair.rise_in:.1f} in. "
        f"Bolt pairs through {done} of {total} stringer-to-tread joints."
    )
    if platform_note:
        note = f"{note} {platform_note}"
    if post_note:
        note = f"{note} {post_note}"
    if freeze_note:
        note = f"{note} {freeze_note}"
    return StairResult(title=str(com_value(model.GetTitle) or "Part"), model=model, note=note)


def flight_suffix(flight: int) -> str:
    """Name ending for a flight's stringers: none for the first, F2, F3... above it."""
    return "" if flight == 0 else f"F{flight + 1}"


def _moved_place(place: TreadPlace, index: int, turn: float, lift: float) -> TreadPlace:
    c, sn = math.cos(turn), math.sin(turn)
    x, y, z = place.center
    return TreadPlace(
        index=index, phi=place.phi + turn, y0=place.y0 + lift, y1=place.y1 + lift,
        center=(x * c - z * sn, y + lift, x * sn + z * c),
    )


def _platforms(
    model, layout, places, per_flight: int, platforms: int, top_platform: bool, profiles, shell_od: float, progress
) -> str:
    """C4 frame past the top tread of each flight below a mid platform (and past the
    last one for a top platform), the 6x6 clips where the stringers meet it, the
    shell clips at both ends of its inner channel, and the knee braces under both
    ends of its outer channel."""
    from swauto.stair.platform_sw import (
        add_platform_knee_braces,
        add_platform_shell_clips,
        add_stringer_clips,
        place_mid_platform,
    )

    frame_profile, clip_profile, knee_profile = profiles
    r_a = layout.inner_face_in
    r_b = r_a + CLEAR_IN
    after = []
    missed = []
    for k in range(1, platforms + 1 + (1 if top_platform else 0)):
        last = places[k * per_flight - 1]
        place_mid_platform(
            model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, profile=frame_profile,
            progress=progress,
        )
        clips = add_stringer_clips(
            model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, profile=clip_profile,
            sides=("A", "B") if k <= platforms else ("A",), progress=progress,
        )
        try:
            shell = add_platform_shell_clips(
                model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, shell_r=shell_od,
                progress=progress,
            )
            if "missed" in shell.note:
                missed.append(f"shell clip holes after tread {last.index}")
        except SolidWorksError as exc:
            # The stair is whole without them; say why in the note.
            missed.append(str(exc))
        try:
            knees = add_platform_knee_braces(
                model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, shell_r=shell_od,
                profile=knee_profile, progress=progress,
            )
            if "missed" in knees.note:
                missed.append(f"knee brace holes after tread {last.index}")
        except SolidWorksError as exc:
            missed.append(str(exc))
        after.append(str(last.index))
        if "Missed" in clips.note:
            missed.append(clips.note.split("Missed: ", 1)[1].rstrip("."))
    note = (
        f"C4x5.4 platform frames after tread{'s' if len(after) > 1 else ''} {', '.join(after)}, "
        "with L6x6x3/8 clips at every stringer end that meets them, shell clips at both ends "
        "of each inner channel, and L3x3x3/8 knee braces to the shell under both ends of each outer channel."
    )
    return note + (f" Missed: {'; '.join(missed)}." if missed else "")


def _handrail_posts(
    model, layout, places, per_flight: int, posts: tuple[int, ...], profile: str, platforms: int,
    top_platform: bool, post_in: float | None, top_rail: bool, mid_rail: bool, mid_top: float | None,
    grab: GrabRail | None, progress,
) -> str:
    """Handrail posts at the same treads of every flight on the outer stringer, and near
    both ends of each platform's outer channel, ``post_in`` in from the ends. With
    ``top_rail`` and ``mid_rail``, the outer top rail and midrail along them, the
    midrail ``mid_top`` over a platform's grating; with ``grab``, the grab rail on the flight posts."""
    from swauto.stair.grab_sw import add_grab_rails
    from swauto.stair.post_sw import PLATFORM_POST_IN, add_handrail_posts, add_platform_posts, post_layout
    from swauto.stair.rail_sw import PLATFORM_MID_TOP_IN, add_bottom_end, add_mid_rails, add_top_rails

    if post_in is None:
        post_in = PLATFORM_POST_IN
    if mid_top is None:
        mid_top = PLATFORM_MID_TOP_IN
    r_a = layout.inner_face_in
    r_b = r_a + CLEAR_IN
    flight_posts = post_layout(places, per_flight, posts, r_b)
    note = add_handrail_posts(model, flight_posts, r_b=r_b, profile=profile, progress=progress).note
    after = []
    missed = []
    for k in range(1, platforms + 1 + (1 if top_platform else 0)):
        last = places[k * per_flight - 1]
        try:
            placed = add_platform_posts(
                model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, profile=profile,
                post_in=post_in, progress=progress,
            )
            after.append(str(last.index))
            if "missed" in placed.note:
                missed.append(f"post holes at the platform after tread {last.index}")
        except SolidWorksError as exc:
            missed.append(str(exc))
    if after:
        note += (
            f" Posts bolted {post_in:g} in in from both ends of the outer channel of the "
            f"platform{'s' if len(after) > 1 else ''} after tread{'s' if len(after) > 1 else ''} {', '.join(after)}."
        )
    if missed:
        note += f" Platform posts missed: {'; '.join(missed)}."
    if top_rail:
        try:
            note += " " + add_top_rails(
                model, places, per_flight, r_a=r_a, r_b=r_b, platforms=platforms, top_platform=top_platform,
                profile=profile, post_in=post_in, mid_top=mid_top, progress=progress,
            ).note
        except SolidWorksError as exc:
            note += f" Top rail stopped: {exc}"
    if mid_rail:
        try:
            note += " " + add_mid_rails(
                model, places, per_flight, r_a=r_a, r_b=r_b, platforms=platforms, top_platform=top_platform,
                post_in=post_in, mid_top=mid_top, progress=progress,
            ).note
        except SolidWorksError as exc:
            note += f" Midrail stopped: {exc}"
        else:
            if top_rail:
                try:
                    note += " " + add_bottom_end(
                        model, places, per_flight, r_b=r_b, profile=profile, progress=progress
                    ).note
                except SolidWorksError as exc:
                    note += f" Rail end at the foot stopped: {exc}"
    if grab is not None:
        try:
            note += " " + add_grab_rails(
                model, places, per_flight, flight_posts, r_a=r_a, r_b=r_b, platforms=platforms,
                top_platform=top_platform, post_in=post_in, mid_top=mid_top, grab=grab, progress=progress,
            ).note
        except SolidWorksError as exc:
            note += f" Grab rail stopped: {exc}"
    return note


# ---------------------------------------------------------------- stringers


def build_flight_stringers(
    model, stair: StringerMock, shell_od: float, *, at: tuple[float, float] = (0.0, 0.0), suffix: str = "",
    progress=None,
) -> None:
    """Both stringers of one flight of ``stair.treads`` treads, turned and raised by ``at``.

    Rolls both blanks, rebuilds, then cuts both to the lisp outline before
    any holes: a missed connecting hole must not skip the other stringer or
    the treads. Flat patterns stay suppressed so the stringers show bent
    until Flatten is clicked. Names end in ``suffix`` for flights above the first.
    """
    flight = StringerMock(
        shell_od_in=shell_od,
        gap_in=stair.gap_in,
        treads=stair.treads,
        rise_in=stair.rise_in,
        run_in=stair.run_in,
        plate_width_in=stair.plate_width_in,
    )
    layout = layout_stringer(
        StringerMock(
            shell_od_in=shell_od, gap_in=stair.gap_in, treads=stair.treads, rise_in=stair.rise_in,
            run_in=stair.run_in, plate_width_in=stair.plate_width_in, outside_face=True,
        )
    )
    inner_dev, outer_dev = develop_both(flight)
    tank_face = shell_od + stair.gap_in
    jobs = (
        (inner_dev, tank_face, tank_face + THICKNESS_IN, f"EliteStringerIn{suffix}"),
        (outer_dev, layout.outside_radius_in - THICKNESS_IN, layout.outside_radius_in, f"EliteStringerOut{suffix}"),
    )
    for dev, r_in, r_out, nm in jobs:
        _stringer_blank(model, dev, r_in, r_out, nm, at)
        _progress(progress, f"{nm} rolled")
    _rebuild(model)
    for dev, r_in, r_out, nm in jobs:
        _stringer_form(model, layout, dev, r_in, r_out, nm, progress, at)
    _keep_bent_view(model)
    for dev, r_in, r_out, nm in jobs:
        _stringer_holes(model, dev, r_in, r_out, nm, progress, at)


def _stringer_geometry(layout, dev: DevelopedStringer, r_in: float, r_out: float):
    """Shared angle/height values for one stringer's sweep and forming."""
    radius = dev.radius_in
    rise_per_rad = layout.total_rise_in / layout.sweep_rad
    tan = math.tan(dev.pitch_rad)
    p4, p_start, p_end, p2, p3, l2_end, l3_end, p5 = dev.outline
    top_at_zero = p_start[1] - p_start[0] * tan
    height = dev.plate_width_in / math.cos(dev.pitch_rad)
    return {
        "radius": radius,
        "rise_per_rad": rise_per_rad,
        "top_at_zero": top_at_zero,
        "bottom_at_zero": top_at_zero - height,
        "phi_end": p2[0] / radius + 0.03,
        "r_mid": (r_in + r_out) / 2.0,
        "band": (r_in - 0.03, r_out + 0.03),
        "outline": (p4, p_start, p_end, p2, p3, l2_end, l3_end, p5),
    }


def _stringer_blank(
    model, dev: DevelopedStringer, r_in: float, r_out: float, name: str, at: tuple[float, float] = (0.0, 0.0)
) -> None:
    """Rolled 3/8 in sheet-metal blank: a lofted bend between two arcs on the
    outside face, filling the lisp outline's box (bottom end to top end, foot
    to cap). The thickness goes in from the arcs, so the plate is r_in to r_out.
    It is sheet metal from the first feature, so the stringer flattens.
    ``at`` turns and raises a higher flight: (angle, inches)."""
    radius = dev.radius_in
    p4, _p_start, _p_end, p2, _p3, _l2, _l3, p5 = dev.outline
    phi_a, phi_b = at[0] + p4[0] / radius, at[0] + p2[0] / radius
    low = _arc_sketch(model, at[1] + p5[1], r_out, phi_a, phi_b, f"{name}LowArc")
    high = _arc_sketch(model, at[1] + p2[1], r_out, phi_a, phi_b, f"{name}HighArc")
    _clear_selection(model)
    if not (
        _select_feature(model, low, "SKETCH", mark=1, append=False)
        and _select_feature(model, high, "SKETCH", mark=1, append=True)
    ):
        raise SolidWorksError(f"{name}: could not select the blank arcs.")
    before_bodies = _body_names(model)
    feature = model.FeatureManager.InsertSheetMetalLoftedBend(THICKNESS_IN * _INCH, THICKNESS_IN * _INCH)
    if feature is None:
        raise SolidWorksError(f"{name}: the rolled blank (lofted bend) was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _name_new_body(model, before_bodies, name)


def _arc_sketch(model, y_in: float, radius: float, phi_a: float, phi_b: float, name: str):
    plane = _offset_from(model, _plane(model, "Top"), y_in, f"{name}Pln")
    before = _names(model)
    _open_sketch(model, plane)
    a, b = _plan_xy(radius, phi_a), _plan_xy(radius, phi_b)
    if model.SketchManager.CreateArc(0.0, 0.0, 0.0, a[0], a[1], 0.0, b[0], b[1], 0.0, -1) is None:
        _recover(model)
        raise SolidWorksError(f"{name}: arc failed.")
    _close_sketch(model)
    return _rename_new(model, before, name, "blank arc")


def _stringer_form(
    model, layout, dev: DevelopedStringer, r_in: float, r_out: float, name: str, progress=None,
    at: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Cut the lisp outline into the rolled blank. Every cut is square to the plate.

    The blank already has the foot, the cap and both vertical ends. Three cuts
    finish it: above the top slope, below the 9 in slope up to the corner under
    the cap, and the return. The return starts on the end face the 9 in cut
    left, read from the model, so the two cuts meet with no hair strip between.
    ``at`` turns and raises a higher flight; its helices start at that angle.
    Platforms go in after every flight is cut: a higher flight's helices start
    inside the platform before it.
    """
    g = _stringer_geometry(layout, dev, r_in, r_out)
    radius, band, rise_per_rad = g["radius"], g["band"], g["rise_per_rad"]
    _p4, _p_start, _p_end, p2, p3, l2_end, _l3, p5 = g["outline"]
    turn, lift = at
    far = p2[0] / radius + 0.03
    corner = l2_end[0] / radius
    span = p2[1] - p5[1] + 10.0
    _cut_sweep(
        model, (g["r_mid"], rise_per_rad * far, far / (2.0 * math.pi)), band,
        lift + g["top_at_zero"], lift + g["top_at_zero"] + span, f"{name}TopEdge", turn,
    )
    _progress(progress, f"{name} top edge cut")
    _cut_sweep(
        model, (g["r_mid"], rise_per_rad * corner, corner / (2.0 * math.pi)), band,
        lift + g["bottom_at_zero"] - span, lift + g["bottom_at_zero"], f"{name}Trim", turn,
    )
    _progress(progress, f"{name} 9 in edge cut")
    start = _cut_end_angle(model, r_in, r_out, turn + corner)
    _sector_cut(
        model, band, turn + corner if start is None else start, turn + far, lift - 200.0, lift + p3[1],
        f"{name}TopReturn",
    )
    _progress(progress, f"{name} ends formed")
    _rebuild(model)


def _cut_end_angle(model, r_in: float, r_out: float, near_phi: float):
    """Angle of the vertical end face a helical cut left near ``near_phi``.

    The helix ends about 1e-5 in short of the nominal angle. Starting the
    return on the nominal angle leaves that strip as a loose body.
    """
    best = None
    for body in _bodies(model):
        raw = body.GetFaces()
        faces = list(raw) if isinstance(raw, (list, tuple)) else [raw]
        for face in faces:
            try:
                surface = com_value(face.GetSurface)
                is_plane = surface.IsPlane
                if not (is_plane() if callable(is_plane) else is_plane):
                    continue
                params = [float(v) for v in com_value(surface.PlaneParams)]
                box = [float(v) / _INCH for v in com_value(face.GetBox)]
            except Exception:
                continue
            if abs(params[1]) > 1e-6:
                continue
            cx, cz = (box[0] + box[3]) / 2.0, (box[2] + box[5]) / 2.0
            if not r_in - 0.5 <= math.hypot(cx, cz) <= r_out + 0.5:
                continue
            if abs(math.atan2(-cx, cz) - near_phi) > 0.02:
                continue
            phi = math.atan2(params[2], params[0])
            while phi - near_phi > math.pi / 2.0:
                phi -= math.pi
            while phi - near_phi < -math.pi / 2.0:
                phi += math.pi
            if best is None or abs(phi - near_phi) < best[0]:
                best = (abs(phi - near_phi), phi)
    return None if best is None else best[1]


def _stringer_holes(
    model, dev: DevelopedStringer, r_in: float, r_out: float, name: str, progress=None,
    at: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Connecting holes after both stringers are formed. A miss does not abort."""
    before = _names(model)
    try:
        hole_ok = _end_holes(model, dev, r_in, r_out, name, at)
    except Exception:
        _discard_since(model, before)
        hole_ok = False
    _progress(progress, f"{name} end holes {'cut' if hole_ok else 'missed'}")


def _helix(model, radius_in: float, height_in: float, revolutions: float, name: str, start_phi: float = 0.0):
    """Helix on the Top plane, starting at angle ``start_phi`` from +Z and climbing toward -X.

    InsertHelix turns its start angle the other way from the stair, so it gets -start_phi.
    """
    top = _plane(model, "Top")
    before = _names(model)
    _open_sketch(model, top)
    circle = model.SketchManager.CreateCircleByRadius(0.0, 0.0, 0.0, radius_in * _INCH)
    if circle is None:
        circle = model.SketchManager.CreateCircle(0.0, 0.0, 0.0, radius_in * _INCH, 0.0, 0.0)
    if circle is None:
        _recover(model)
        raise SolidWorksError(f"{name}: helix circle failed.")
    _close_sketch(model)
    sketch = _rename_new(model, before, f"{name}Sk", "helix sketch")
    _clear_selection(model)
    if not sketch.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the helix circle.")
    before = _names(model)
    model.InsertHelix(False, True, False, False, 1, height_in * _INCH, 0.0, float(revolutions), 0.0, -float(start_phi))
    return _rename_new(model, before, f"{name}Helix", "helix")


def _axis_y(model):
    """Reference axis on the tank axis, from the Front and Right planes. Made once per part."""
    axis = find_feature(model, "EliteAxisY")
    if axis is not None:
        return axis
    _clear_selection(model)
    nothing = com_nothing()
    extension = model.Extension
    if not (
        _plane(model, "Front").Select2(False, 0)
        and extension.SelectByID2(_feature_name(_plane(model, "Right")), "PLANE", 0, 0, 0, True, 0, nothing, 0)
    ):
        raise SolidWorksError("Could not select the Front and Right planes for the tank axis.")
    before = _names(model)
    model.InsertAxis2(True)
    axis = _rename_new(model, before, "EliteAxisY", "tank axis")
    _blank_construction(model, axis, "EliteAxisY", "AXIS")
    return axis


def _radial_plane(model, phi: float, name: str):
    """Plane through the tank axis at angle ``phi``: the Right plane turned about the axis.

    Its sketch x runs inward along the radius and y is up, as on the Right plane.
    """
    axis = _axis_y(model)
    nothing = com_nothing()
    for angle in (phi, -phi):
        _clear_selection(model)
        extension = model.Extension
        if not (
            extension.SelectByID2(_feature_name(_plane(model, "Right")), "PLANE", 0, 0, 0, False, 0, nothing, 0)
            and extension.SelectByID2(_feature_name(axis), "AXIS", 0, 0, 0, True, 1, nothing, 0)
        ):
            raise SolidWorksError(f"{name}: could not select the Right plane and the tank axis.")
        before = _names(model)
        plane = model.FeatureManager.InsertRefPlane(16, float(angle), 4, 0.0, 0, 0.0)
        _clear_selection(model)
        if plane is None:
            continue
        rows = [float(v) for v in com_value(com_value(com_value(plane.GetSpecificFeature2).Transform).ArrayData)]
        if abs(rows[6] - math.cos(phi)) < 1e-6 and abs(rows[8] - math.sin(phi)) < 1e-6:
            return _rename_new(model, before, name, "radial plane")
        _delete_feature(model, plane)
    raise SolidWorksError(f"{name}: the radial plane did not land at {phi:.5f} rad.")


# ------------------------------------------------------------ end formation


def _plan_xy(radius: float, phi: float) -> tuple[float, float]:
    """World plan point at (radius, phi) in Top-plane sketch coordinates (x, -z)."""
    return (-radius * math.sin(phi) * _INCH, -radius * math.cos(phi) * _INCH)


def _sector_sketch(model, plane, band: tuple[float, float], phi0: float, phi1: float, name: str):
    """Closed ring sector between two radii and two angles: radial lines plus true arcs."""
    r0, r1 = band
    mid = (phi0 + phi1) / 2.0
    before = _names(model)
    _open_sketch(model, plane)
    try:
        sketch = model.SketchManager
        a0, a1 = _plan_xy(r0, phi0), _plan_xy(r1, phi0)
        b0, b1 = _plan_xy(r0, phi1), _plan_xy(r1, phi1)
        m0, m1 = _plan_xy(r0, mid), _plan_xy(r1, mid)
        if sketch.CreateLine(a0[0], a0[1], 0.0, a1[0], a1[1], 0.0) is None:
            raise SolidWorksError(f"{name}: sector line failed.")
        if sketch.Create3PointArc(a1[0], a1[1], 0.0, b1[0], b1[1], 0.0, m1[0], m1[1], 0.0) is None:
            raise SolidWorksError(f"{name}: sector arc failed.")
        if sketch.CreateLine(b1[0], b1[1], 0.0, b0[0], b0[1], 0.0) is None:
            raise SolidWorksError(f"{name}: sector line failed.")
        if sketch.Create3PointArc(b0[0], b0[1], 0.0, a0[0], a0[1], 0.0, m0[0], m0[1], 0.0) is None:
            raise SolidWorksError(f"{name}: sector arc failed.")
    except Exception:
        _recover(model)
        raise
    _close_sketch(model)
    return _rename_new(model, before, f"{name}Sk", "sector sketch")


def _sector_cut(model, band, phi0: float, phi1: float, y0: float, y1: float, name: str) -> None:
    """Remove the stringer material inside the plan sector between heights y0 and y1."""
    top = _plane(model, "Top")
    plane = _offset_from(model, top, (y0 + y1) / 2.0, f"{name}Pln")
    sketch = _sector_sketch(model, plane, band, phi0, phi1, name)
    feature = _cut_both_ways(model, sketch, (y1 - y0) / 2.0)
    if feature is None:
        raise SolidWorksError(f"{name}: end cut was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)


def _discard_since(model, before: set[str]) -> None:
    """Delete top-level features created after ``before``. Newest first.

    Closes an open sketch first. Used when a trim attempt or an end-hole
    attempt fails, so the bad helix, plane, and sketch do not stay behind
    and the next attempt is not pointed at the stale one.
    """
    _recover(model)
    fresh = []
    for feature in iter_features(model):
        current = _feature_name(feature)
        if current and current not in before:
            fresh.append(feature)
    for feature in reversed(fresh):
        _delete_feature(model, feature)


def _cut_sweep(
    model, helix_spec, band: tuple[float, float], y_bottom: float, y_top: float, name: str, start_phi: float = 0.0
) -> None:
    """Helical cut: a rectangle swept along a trim helix through the plate band.

    The rectangle is on the Right plane for the first flight, or on a radial
    plane at ``start_phi`` where the helix of a higher flight starts.
    CreateCornerRectangle often returns nothing even though the four lines are
    in the sketch. ``_corner_rect`` trusts those lines, so the cut is made on
    the first attempt. One rebuild-and-retry only if that cut feature comes
    back empty — not six full rebuilds.
    """
    r_mid, height_in, revolutions = helix_spec
    # 19-arg InsertCutSwept4 (feature-scope booleans at the tail) removes the
    # strip along the helix on this SolidWorks. Alignment on the first call is
    # the one that has been cutting; the others are the fallback.
    methods = (
        ("InsertCutSwept4", (False, True, 0, False, False, 0, 0, False, 0, 0, 0, 0, True, True, 0, True, True, True, False)),
        ("InsertCutSwept4", (False, False, 0, False, False, 0, 0, False, 0, 0, 0, 0, True, True, 0, True, True, True, False)),
        ("InsertCutSwept3", (False, False, 0, False, False, 0, 0, False, 0.0, 0.0, 0, True, True, True, 0.0, True)),
    )
    errors: list[str] = []
    baseline = _names(model)
    for attempt in range(2):
        if attempt:
            _discard_since(model, baseline)
            _rebuild(model)
        try:
            helix = _helix(model, r_mid, height_in, revolutions, name, start_phi)
        except Exception as exc:
            errors.append(f"attempt {attempt}: helix {format_com_error(exc)}")
            _recover(model)
            continue
        try:
            if start_phi:
                plane = _radial_plane(model, start_phi, f"{name}ProfPln")
            else:
                plane = _plane(model, "Right")
            before = _names(model)
            _open_sketch(model, plane)
            if start_phi:
                _check_radial_sketch(model, start_phi, name)
            if not _corner_rect(model, -band[1], y_bottom, -band[0], y_top):
                _recover(model)
                errors.append(f"attempt {attempt}: profile failed")
                continue
            _close_sketch(model)
            profile = _rename_new(model, before, f"{name}Prof", "trim profile")
        except Exception as exc:
            _recover(model)
            errors.append(f"attempt {attempt}: profile {format_com_error(exc)}")
            continue
        stuck = False
        for method_name, args in methods:
            method = getattr(model.FeatureManager, method_name, None)
            if method is None:
                continue
            _clear_selection(model)
            if not _select_feature(model, profile, "SKETCH", mark=1, append=False):
                continue
            if not _select_feature(model, helix, "REFERENCECURVES", mark=4, append=True):
                continue
            try:
                feature = method(*args)
            except Exception as exc:
                errors.append(f"{method_name}/{len(args)} attempt={attempt}: {format_com_error(exc)}")
                continue
            if feature in (None, False):
                errors.append(f"{method_name}/{len(args)} attempt={attempt}: returned nothing")
                continue
            with contextlib.suppress(Exception):
                rename_feature(feature, name)
            stuck = True
            break
        if stuck:
            return
    _discard_since(model, baseline)
    raise SolidWorksError(f"{name}: edge trim failed ({'; '.join(errors[-4:]) or 'no sweep-cut method'}).")


def _check_radial_sketch(model, phi: float, name: str) -> None:
    """The open sketch on a radial plane must map (radius, height) to (-radius, height) like the Right plane."""
    sketch = com_value(model.GetActiveSketch2)
    data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]
    point = (-100.0 * math.sin(phi) * _INCH, 7.0 * _INCH, 100.0 * math.cos(phi) * _INCH)
    sx, sy, sz = _to_sketch(data, point)
    if abs(sx + 100.0 * _INCH) > 1e-6 or abs(sy - 7.0 * _INCH) > 1e-6 or abs(sz) > 1e-6:
        raise SolidWorksError(f"{name}: the radial plane sketch is not set like the Right plane.")


def _rebuild(model) -> None:
    """Rebuild the model. EditRebuild3 is a no-argument property on this
    SolidWorks late-binding wrapper: reading it rebuilds. ForceRebuild3 takes a
    flag and is a real method, used as a fallback."""
    try:
        com_value(model.EditRebuild3)
        return
    except Exception:
        pass
    with contextlib.suppress(Exception):
        model.ForceRebuild3(False)


def _freeze_stringers(model) -> str:
    """Put the freeze bar just after the stringer features.

    Later treads then do not recompute the sweeps. SolidWorks 2013 has the
    freeze bar when the license and the system option allow it. Turning the
    option on and moving the bar in the same call often does not stick, so
    the move is tried twice. If the license has no freeze bar, say so and
    keep building. Graphics stay on either way.
    """
    last = ""
    for feature in iter_features(model):
        name = _feature_name(feature)
        if name:
            last = name
    if not last:
        return "Freeze bar skipped (no features to freeze)."
    try:
        import win32com.client

        app = win32com.client.GetActiveObject("SldWorks.Application")
    except Exception:
        app = None
    if app is not None:
        try:
            app.SetUserPreferenceToggle(_SW_ENABLE_FREEZE_BAR, True)
        except Exception:
            return "Freeze bar skipped (this SolidWorks has no freeze bar)."
    method = getattr(model.FeatureManager, "EditFreeze", None)
    if not callable(method):
        return "Freeze bar skipped (this SolidWorks has no freeze bar)."

    def location() -> str:
        try:
            place = com_value(model.FeatureManager.GetFreezeLocation)
        except Exception:
            return ""
        if place is None:
            return ""
        try:
            return str(com_value(place.Name) or "")
        except Exception:
            return ""

    for _ in range(2):
        try:
            method(_SW_FREEZE_AFTER_FEATURE, last, True)
        except Exception:
            return "Freeze bar skipped (the freeze bar could not be moved)."
        if location() == last:
            return f"Freeze bar is after {last}."
    return "Freeze bar skipped (this license did not move the freeze bar)."


def _sketch_segment_count(model) -> int:
    """How many segments are in the open sketch. AddToDB can add them and still return nothing."""
    sketch = com_value(model.GetActiveSketch2)
    if sketch is None:
        return 0
    try:
        raw = com_value(sketch.GetSketchSegments)
    except Exception:
        return 0
    if raw is None:
        return 0
    if isinstance(raw, (list, tuple)):
        return len(raw)
    return 1


def _corner_rect(model, x0: float, y0: float, x1: float, y1: float) -> bool:
    """Right-plane corner rectangle in inches.

    With AddToDB on, CreateCornerRectangle often returns nothing even though the
    four lines are in the sketch. A trim attempt was aborting on that and never
    calling the cut. Trust the sketch contents, and fall back to four lines.
    """
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = True
    xm0, ym0, xm1, ym1 = x0 * _INCH, y0 * _INCH, x1 * _INCH, y1 * _INCH
    for _ in range(3):
        with contextlib.suppress(Exception):
            sketch.CreateCornerRectangle(xm0, ym0, 0.0, xm1, ym1, 0.0)
        if _sketch_segment_count(model) >= 4:
            return True
    corners = ((xm0, ym0), (xm1, ym0), (xm1, ym1), (xm0, ym1))
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1], strict=False):
        with contextlib.suppress(Exception):
            sketch.CreateLine(ax, ay, 0.0, bx, by, 0.0)
    return _sketch_segment_count(model) >= 4


def _band_faces(model, band: tuple[float, float]) -> int:
    """Total face count of the tall bodies whose plan reach sits in the radial band."""
    total = 0
    for body in _bodies(model):
        box = _box_in(body)
        if box[4] - box[1] < TREAD_MARK_IN + 1.0:
            continue
        reach = max(math.hypot(box[0], box[2]), math.hypot(box[3], box[5]), math.hypot(box[0], box[5]), math.hypot(box[3], box[2]))
        if band[0] - 1.0 <= reach <= band[1] + 1.0:
            with contextlib.suppress(Exception):
                total += int(body.GetFaceCount())
    return total


def _end_holes(
    model, dev: DevelopedStringer, r_in: float, r_out: float, name: str, at: tuple[float, float] = (0.0, 0.0)
) -> bool:
    """Connecting holes sketched the way tread bolts are, then the jig is deleted.

    A tangent plane landed on the tank axis and never cut the plate. Instead,
    a temporary plate sits against the walk-side face. The holes are sketched
    on that face and cut both ways through the plate and the stringer. Only
    the temporary body is deleted; the cut feature stays in the stringer.
    Inner ends are two 13/16 rounds. Outer ends are two 1-5/8 horizontal slots.
    A miss does not raise.
    """
    # Walk-side face is the development radius: outer face of the inner
    # stringer, inner face of the outer stringer. The jig sits on the tread side.
    face_r = dev.radius_in
    outward = abs(face_r - r_out) <= abs(face_r - r_in)
    ok = True
    for label, pair in (("Top", dev.end_holes[:2]), ("Bot", dev.end_holes[2:])):
        before = _names(model)
        try:
            if not _end_hole_pair(model, dev, face_r, outward, pair, f"{name}{label}Holes", at):
                ok = False
        except Exception:
            _discard_since(model, before)
            ok = False
    return ok


def _end_hole_pair(
    model, dev: DevelopedStringer, face_r: float, outward: bool, pair, name: str, at: tuple[float, float] = (0.0, 0.0)
) -> bool:
    """One end: jig plate, sketch on its stringer face, cut, delete the jig body."""
    radius = dev.radius_in
    turn, lift = at
    pair = [(x + turn * radius, y + lift) for x, y in pair]
    phis = [x / radius for x, _y in pair]
    phi = sum(phis) / len(phis)
    span = max(abs(p - phi) * radius for p in phis)
    extra = (SLOT_LENGTH_IN / 2.0 if dev.slotted else END_HOLE_RADIUS_IN) + 0.6
    half_along = span + extra
    y_mid = sum(y for _x, y in pair) / len(pair)
    half_y = 0.9
    jig_thick = 0.5
    if outward:
        r0, r1 = face_r, face_r + jig_thick
    else:
        r0, r1 = face_r - jig_thick, face_r
    top = _plane(model, "Top")
    base = _offset_from(model, top, y_mid - half_y, f"{name}JigPln")
    sketch = _sketch_on(
        model, base, f"{name}JigSk",
        lambda: _plan_rect(model, phi, r0, r1, half_along),
    )
    _extrude(model, sketch, half_y * 2.0, f"{name}Jig", merge=False)
    _rebuild(model)
    center = (
        -((r0 + r1) / 2.0) * math.sin(phi),
        y_mid,
        ((r0 + r1) / 2.0) * math.cos(phi),
    )
    jig = _body_near(model, center, max_height=half_y * 2.0 + 0.4, max_dist=1.5)
    if jig is None:
        return False
    face = _face_at_radius(jig, face_r)
    if face is None or not _select_face(model, face):
        _delete_bodies_near(model, center, max_height=half_y * 2.0 + 0.4, max_dist=1.5)
        return False
    before = _names(model)
    sketch_manager = model.SketchManager
    with contextlib.suppress(Exception):
        sketch_manager.AddToDB = True
    with contextlib.suppress(Exception):
        sketch_manager.DisplayWhenAdded = False
    sketch_manager.InsertSketch(True)
    points: list[tuple[float, float, float]] = []
    try:
        sketch_obj = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch_obj.ModelToSketchTransform).ArrayData)]
        for x_in, y_in in pair:
            hole_phi = x_in / radius
            point = (
                -face_r * math.sin(hole_phi) * _INCH,
                y_in * _INCH,
                face_r * math.cos(hole_phi) * _INCH,
            )
            points.append((point[0] / _INCH, point[1] / _INCH, point[2] / _INCH))
            sx, sy, sz = _to_sketch(data, point)
            if abs(sz) > 0.05 * _INCH:
                raise SolidWorksError(f"{name}: hole is {sz / _INCH:.3f} in off the jig face.")
            if dev.slotted:
                tangent = (-math.cos(hole_phi), 0.0, -math.sin(hole_phi))
                ahead = (
                    point[0] + tangent[0] * _INCH,
                    point[1],
                    point[2] + tangent[2] * _INCH,
                )
                ax, ay, _az = _to_sketch(data, ahead)
                _slot_along(
                    model, sx, sy, ax - sx, ay - sy,
                    SLOT_LENGTH_IN * _INCH, END_HOLE_RADIUS_IN * _INCH,
                )
            elif _create_circle(sketch_manager, sx, sy, END_HOLE_RADIUS_IN * _INCH) is None:
                raise SolidWorksError(f"{name}: end hole circle failed.")
    except Exception:
        _recover(model)
        _discard_since(model, before)
        _delete_bodies_near(model, center, max_height=half_y * 2.0 + 0.4, max_dist=1.5)
        return False
    _close_sketch(model)
    hole_sketch = _rename_new(model, before, f"{name}Sk", "end holes sketch")
    # Through the 1/2 in jig and the 3/8 in stringer, both directions.
    feature = _cut_both_ways(model, hole_sketch, jig_thick + THICKNESS_IN + 0.35)
    if feature is None:
        _discard_since(model, before)
        _delete_bodies_near(model, center, max_height=half_y * 2.0 + 0.4, max_dist=1.5)
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _rebuild(model)
    _delete_bodies_near(model, center, max_height=half_y * 2.0 + 0.4, max_dist=1.5)
    _rebuild(model)
    near = (SLOT_LENGTH_IN / 2.0 + 0.15) * _INCH if dev.slotted else 0.12 * _INCH
    for point in points:
        if _stringer_has_hole(model, face_r, point, END_HOLE_RADIUS_IN, near) is not True:
            return False
    return True


def _slot(model, cx: float, cy: float, length: float, radius: float) -> None:
    """Horizontal stadium in sketch meters: two lines and two three-point end arcs."""
    _slot_along(model, cx, cy, 1.0, 0.0, length, radius)


def _slot_along(model, cx: float, cy: float, ux: float, uy: float, length: float, radius: float) -> None:
    """Stadium in sketch meters along sketch direction (ux, uy). World-horizontal when that direction is."""
    norm = math.hypot(ux, uy)
    if norm < 1e-9:
        raise SolidWorksError("Slot direction is not on the sketch face.")
    ux, uy = ux / norm, uy / norm
    px, py = -uy, ux
    half = max(length / 2.0 - radius, 0.0)
    sketch = model.SketchManager

    def at(along: float, side: float) -> tuple[float, float]:
        return cx + ux * along + px * side, cy + uy * along + py * side

    a, b = at(-half, radius), at(half, radius)
    c, d = at(half, -radius), at(-half, -radius)
    for start, end in ((a, b), (c, d)):
        if sketch.CreateLine(start[0], start[1], 0.0, end[0], end[1], 0.0) is None:
            raise SolidWorksError("Could not draw a slot line.")
    right, left = at(half + radius, 0.0), at(-(half + radius), 0.0)
    if sketch.Create3PointArc(b[0], b[1], 0.0, c[0], c[1], 0.0, right[0], right[1], 0.0) is None:
        raise SolidWorksError("Could not draw a slot arc.")
    if sketch.Create3PointArc(d[0], d[1], 0.0, a[0], a[1], 0.0, left[0], left[1], 0.0) is None:
        raise SolidWorksError("Could not draw a slot arc.")


# ------------------------------------------------------------------- treads


def _tread_places(layout) -> list[TreadPlace]:
    inner_edge = layout.inner_face_in + TREAD_CLEAR_IN
    center_r = inner_edge + TREAD_PLATE_IN / 2.0
    places: list[TreadPlace] = []
    count = len(layout.treads)
    for index in range(1, count + 1):
        phi = index / count * layout.sweep_rad
        # Lisp Height/Angle placement: ground is tread zero, centres at i/N of the rise.
        y_center = (index / count) * layout.total_rise_in
        places.append(
            TreadPlace(
                index=index,
                phi=phi,
                y0=y_center - TREAD_MARK_IN / 2.0,
                y1=y_center + TREAD_MARK_IN / 2.0,
                center=(-center_r * math.sin(phi), y_center, center_r * math.cos(phi)),
            )
        )
    return places


def _tread(model, layout, place: TreadPlace, wall_in: float) -> None:
    name = f"EliteTread{place.index:02d}"
    inner_edge = layout.inner_face_in + TREAD_CLEAR_IN
    outer_edge = inner_edge + TREAD_PLATE_IN
    half = TREAD_DEPTH_IN / 2.0
    top = _plane(model, "Top")
    base = _offset_from(model, top, place.y0, f"{name}Pln")
    walls_sk = _sketch_on(
        model,
        base,
        f"{name}WallsSk",
        lambda: (
            _plan_rect(model, place.phi, inner_edge, outer_edge, half),
            _plan_rect(model, place.phi, inner_edge + wall_in, outer_edge - wall_in, half - wall_in),
        ),
    )
    _extrude(model, walls_sk, TREAD_MARK_IN - wall_in, f"{name}Walls", merge=False)
    lid = _offset_from(model, top, place.y1 - wall_in, f"{name}TopPln")
    top_sk = _sketch_on(
        model,
        lid,
        f"{name}TopSk",
        lambda: _plan_rect(model, place.phi, inner_edge, outer_edge, half),
    )
    _extrude(model, top_sk, wall_in, name, merge=True)
    body = _tread_body(model, place)
    if body is not None:
        with contextlib.suppress(Exception):
            body.Name = name


def _sketch_on(model, plane, name: str, draw):
    """Open a sketch on ``plane``, draw, close, rename. One retry after a rebuild.

    Right after a sweep SolidWorks can refuse the first sketch line; a rebuild
    clears that.
    """
    last_error: Exception | None = None
    for attempt in range(2):
        before = _names(model)
        _open_sketch(model, plane)
        try:
            draw()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            _recover(model)
            _delete_named(model, tuple(n for n in _names(model) if n not in before))
            if attempt == 0:
                _rebuild(model)
            continue
        _close_sketch(model)
        return _rename_new(model, before, name, "tread sketch")
    raise SolidWorksError(f"{name}: {last_error}")


def _plan_rect(model, phi: float, r0: float, r1: float, half_along: float) -> None:
    """Rectangle on a Top-plane sketch: radial from r0 to r1, +/- half_along on the travel line."""
    radial = (-math.sin(phi), math.cos(phi))
    travel = (-math.cos(phi), -math.sin(phi))
    corners = []
    for radius, sign in ((r0, 1.0), (r1, 1.0), (r1, -1.0), (r0, -1.0)):
        x = radial[0] * radius + travel[0] * half_along * sign
        z = radial[1] * radius + travel[1] * half_along * sign
        corners.append((x, -z))  # Top-plane sketch: sketch y is world -z
    sketch = model.SketchManager
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1], strict=False):
        segment = sketch.CreateLine(ax * _INCH, ay * _INCH, 0.0, bx * _INCH, by * _INCH, 0.0)
        if segment is None:
            with contextlib.suppress(Exception):
                sketch.AddToDB = True
            segment = sketch.CreateLine(ax * _INCH, ay * _INCH, 0.0, bx * _INCH, by * _INCH, 0.0)
        if segment is None:
            raise SolidWorksError("Could not draw a tread edge.")


# -------------------------------------------------------------------- bolts


def _end_wall_face(model, place: TreadPlace, edge_r: float):
    """The tread end face that faces the stringer, found on the body itself.

    A coordinate pick misses once the stringers fill the view. The face is the
    planar wall whose center sits on ``edge_r``.
    """
    body = _tread_body(model, place)
    if body is None:
        return None
    best = None
    best_gap = None
    raw = body.GetFaces()
    faces = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    for face in faces:
        try:
            box = [float(v) / _INCH for v in com_value(face.GetBox)]
        except Exception:
            continue
        cx = (box[0] + box[3]) / 2.0
        cz = (box[2] + box[5]) / 2.0
        gap = abs(math.hypot(cx, cz) - edge_r)
        if gap > 0.2 or box[4] - box[1] < TREAD_MARK_IN * 0.4:
            continue
        if best is None or gap < best_gap:
            best, best_gap = face, gap
    return best


def _select_segments(model, sketch, name: str, count: int | None = None) -> None:
    """Select the lines of ``sketch`` from the sketch itself.

    A pick by model coordinates depends on the view and misses when the line
    is off screen or behind other bodies.
    """
    _clear_selection(model)
    raw = com_value(com_value(sketch.GetSpecificFeature2).GetSketchSegments)
    segments = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    if not segments or (count is not None and len(segments) != count):
        raise SolidWorksError(f"{name}: the sketch has {len(segments)} lines, not {count}.")
    nothing = com_nothing()
    for index, segment in enumerate(segments):
        picked = False
        with contextlib.suppress(Exception):
            picked = bool(segment.Select4(index > 0, nothing))
        if not picked:
            with contextlib.suppress(Exception):
                picked = bool(segment.Select2(index > 0, 0))
        if not picked:
            raise SolidWorksError(f"{name}: could not select sketch line {index + 1}.")


def _select_face(model, face) -> bool:
    with contextlib.suppress(Exception):
        if face.Select2(False, 0):
            return True
    try:
        box = [float(v) for v in com_value(face.GetBox)]
    except Exception:
        return False
    nothing = com_nothing()
    try:
        return bool(
            model.Extension.SelectByID2(
                "", "FACE",
                (box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0, (box[2] + box[5]) / 2.0,
                False, 0, nothing, 0,
            )
        )
    except Exception:
        return False


def _bolts(model, layout, place: TreadPlace, side: str, wall_in: float) -> bool:
    """Two bolts on this tread's side wall, cut perpendicular to that wall.

    The sketch sits on the outside face of the tread end wall (the wall that
    faces the stringer). The holes are located from the tread front face in the
    side profile. One cut runs both ways: through the 1/2 in wall into the pan,
    and across the 1/16 in gap through the 3/8 in stringer.
    """
    name = f"EliteBolt{place.index:02d}{side}"
    inner_edge = layout.inner_face_in + TREAD_CLEAR_IN
    edge_r = inner_edge if side == "In" else inner_edge + TREAD_PLATE_IN
    half = TREAD_DEPTH_IN / 2.0
    alongs = (half - BOLT_FROM_FRONT_IN, half - BOLT_FROM_FRONT_IN - BOLT_SPACE_IN)
    y_bolt = place.y0 + BOLT_UP_IN
    radial = (-math.sin(place.phi), math.cos(place.phi))
    travel = (-math.cos(place.phi), -math.sin(place.phi))

    def world(along: float, y_in: float) -> tuple[float, float, float]:
        return (
            (edge_r * radial[0] + along * travel[0]) * _INCH,
            y_in * _INCH,
            (edge_r * radial[1] + along * travel[1]) * _INCH,
        )

    face = _end_wall_face(model, place, edge_r)
    before = _names(model)
    _clear_selection(model)
    if face is None or not _select_face(model, face):
        raise SolidWorksError(f"{name}: could not select the tread side wall.")
    sketch_manager = model.SketchManager
    with contextlib.suppress(Exception):
        sketch_manager.AddToDB = True
    with contextlib.suppress(Exception):
        sketch_manager.DisplayWhenAdded = False
    sketch_manager.InsertSketch(True)
    try:
        sketch_obj = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch_obj.ModelToSketchTransform).ArrayData)]
        for along in alongs:
            sx, sy, sz = _to_sketch(data, world(along, y_bolt))
            if abs(sz) > 0.01 * _INCH:
                raise SolidWorksError(f"{name}: bolt point is {sz / _INCH:.3f} in off the wall face.")
            if _create_circle(sketch_manager, sx, sy, BOLT_DIA_IN / 2.0 * _INCH) is None:
                raise SolidWorksError(f"{name}: bolt circle failed.")
    except Exception:
        _recover(model)
        raise
    _close_sketch(model)
    sketch = _rename_new(model, before, f"{name}Sk", "bolt sketch")
    # From this face: one way through the pan wall, the other across the 1/16 in
    # gap and through the 3/8 in stringer. Same depth both ways so either face
    # of the wall still breaks out.
    reach_in = wall_in + TREAD_CLEAR_IN + THICKNESS_IN + 0.35
    points = [world(along, y_bolt) for along in alongs]
    feature = _cut_both_ways(model, sketch, reach_in)
    if feature is None:
        _rebuild(model)
        feature = _cut_both_ways(model, sketch, reach_in)
    if feature is None:
        _delete_named(model, (f"{name}Sk",))
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    stringer_r = layout.inner_face_in if side == "In" else layout.outside_radius_in - THICKNESS_IN
    tread = _tread_body(model, place)
    pierced = True
    radius_m = BOLT_DIA_IN / 2.0 * _INCH
    near_m = 0.1 * _INCH
    for point in points:
        tread_hit = _has_hole_axis(tread, point, radius_m, near_m) if tread is not None else False
        stringer_hit = _stringer_has_hole(model, stringer_r, _inches(point), BOLT_DIA_IN / 2.0, near_m)
        if tread_hit is True and stringer_hit is True:
            continue
        if tread_hit is False or stringer_hit is False:
            pierced = False
            break
        # Could not read surfaces: keep the cut. A face-count miss used to delete real holes.
    if pierced:
        return True
    _delete_named(model, (name, f"{name}Sk"))
    return False


def _inches(point_m: tuple[float, float, float]) -> tuple[float, float, float]:
    return (point_m[0] / _INCH, point_m[1] / _INCH, point_m[2] / _INCH)


def _cut_both_ways(model, sketch, depth_in: float):
    """Double-ended blind cut of the selected sketch, ``depth_in`` each way."""
    method = getattr(model.FeatureManager, "FeatureCut3", None)
    if not callable(method):
        raise SolidWorksError("FeatureCut3 is not on this SolidWorks interface.")
    depth = depth_in * _INCH
    args = (
        False, False, False, 0, 0, depth, depth,
        False, False, False, False, 0.0, 0.0, False, False, False, False,
        False, True, True, True,
        True, False, 0, 0.0, False,
    )
    _clear_selection(model)
    if not _select_feature(model, sketch, "SKETCH", mark=0, append=False):
        raise SolidWorksError("Could not select the bolt sketch.")
    try:
        feature = method(*args)
    except Exception:
        return None
    return feature if feature not in (None, False) else None


def _to_sketch(data, point):
    """ModelToSketchTransform.ArrayData: 3x3 (used by columns) then a translation.

    sketch = M · model + t. The translation is added after the rotation; verified
    against a pin extruded from the sketch on SolidWorks 2013.
    """
    x = data[0] * point[0] + data[3] * point[1] + data[6] * point[2] + data[9]
    y = data[1] * point[0] + data[4] * point[1] + data[7] * point[2] + data[10]
    z = data[2] * point[0] + data[5] * point[1] + data[8] * point[2] + data[11]
    return x, y, z


# ------------------------------------------------------------------- bodies


def _bodies(model):
    raw = model.GetBodies2(0, False)
    if raw is None:
        return []
    return list(raw) if isinstance(raw, (list, tuple)) else [raw]


def _body_names(model) -> set[str]:
    names = set()
    for body in _bodies(model):
        with contextlib.suppress(Exception):
            names.add(str(body.Name))
    return names


def _name_new_body(model, before: set[str], name: str) -> None:
    for body in _bodies(model):
        try:
            current = str(body.Name)
        except Exception:
            continue
        if current not in before:
            with contextlib.suppress(Exception):
                body.Name = name
            return


def _box_in(body) -> list[float]:
    return [float(v) / _INCH for v in com_value(body.GetBodyBox)]


def _tread_body(model, place: TreadPlace):
    best = None
    best_dist = None
    for body in _bodies(model):
        box = _box_in(body)
        if box[4] - box[1] > TREAD_MARK_IN + 0.5:
            continue
        center = ((box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0, (box[2] + box[5]) / 2.0)
        dist = math.dist(center, place.center)
        if best is None or dist < best_dist:
            best, best_dist = body, dist
    return best if best is not None and best_dist < 3.0 else None


def _classify(model, layout, place: TreadPlace) -> dict[str, object]:
    """The two stringers and this tread, by where they sit. Cuts rename bodies."""
    found: dict[str, object] = {}
    for body in _bodies(model):
        box = _box_in(body)
        height = box[4] - box[1]
        reach = max(math.hypot(box[0], box[2]), math.hypot(box[3], box[5]), math.hypot(box[0], box[5]), math.hypot(box[3], box[2]))
        if reach <= layout.shell_od_in + 0.5:
            continue  # shell plate
        if height > TREAD_MARK_IN + 1.0:
            key = "EliteStringerOut" if reach > layout.mid_radius_in - 5.0 else "EliteStringerIn"
            if key not in found:
                found[key] = body
            continue
        if height <= TREAD_MARK_IN + 0.5:
            center = ((box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0, (box[2] + box[5]) / 2.0)
            if math.dist(center, place.center) < 3.0:
                found[f"EliteTread{place.index:02d}"] = body
    return found


def _counts(bodies: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, body in bodies.items():
        with contextlib.suppress(Exception):
            counts[key] = int(body.GetFaceCount())
    return counts


def _body_near(model, center: tuple[float, float, float], max_height: float, max_dist: float):
    """Short body whose box center is near ``center`` (inches). Skips the stringers."""
    best = None
    best_dist = None
    for body in _bodies(model):
        try:
            box = _box_in(body)
        except Exception:
            continue
        if box[4] - box[1] > max_height:
            continue
        midpoint = ((box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0, (box[2] + box[5]) / 2.0)
        dist = math.dist(midpoint, center)
        if dist <= max_dist and (best is None or dist < best_dist):
            best, best_dist = body, dist
    return best


def _delete_bodies_near(model, center, max_height: float, max_dist: float) -> None:
    """Delete temporary jig bodies. Leaves the hole cut that pierced the stringer."""
    for _ in range(4):
        body = _body_near(model, center, max_height, max_dist)
        if body is None or not _delete_body(model, body):
            return
        _rebuild(model)


def _delete_body(model, body) -> bool:
    """Insert a Delete Body feature. The history, including hole cuts, stays."""
    _clear_selection(model)
    selected = False
    with contextlib.suppress(Exception):
        selected = bool(body.Select2(False, 0))
    if not selected:
        name = ""
        with contextlib.suppress(Exception):
            name = str(body.Name or "")
        nothing = com_nothing()
        if name:
            with contextlib.suppress(Exception):
                selected = bool(model.Extension.SelectByID2(name, "SOLIDBODY", 0.0, 0.0, 0.0, False, 0, nothing, 0))
    if not selected:
        return False
    manager = model.FeatureManager
    for method_name, args in (("InsertDeleteBody", ()), ("InsertDeleteBody2", (False,))):
        method = getattr(manager, method_name, None)
        if not callable(method):
            continue
        try:
            result = method(*args)
        except Exception:
            continue
        if result not in (None, False):
            return True
    return False


def _face_at_radius(body, face_r: float):
    """Planar face of a jig whose center sits on the stringer face radius."""
    best = None
    best_gap = None
    try:
        raw = body.GetFaces()
    except Exception:
        return None
    faces = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    for face in faces:
        try:
            box = [float(v) / _INCH for v in com_value(face.GetBox)]
        except Exception:
            continue
        gap = abs(math.hypot((box[0] + box[3]) / 2.0, (box[2] + box[5]) / 2.0) - face_r)
        if gap > 0.25 or box[4] - box[1] < 0.4:
            continue
        if best is None or gap < best_gap:
            best, best_gap = face, gap
    return best


def _stringer_has_hole(model, face_r: float, point_in, radius_in: float, near_m: float):
    """True/False if a tall plate at ``face_r`` has this hole, or None if surfaces could not be read."""
    point_m = (point_in[0] * _INCH, point_in[1] * _INCH, point_in[2] * _INCH)
    radius_m = radius_in * _INCH
    saw_no = False
    saw_body = False
    for body in _bodies(model):
        try:
            box = _box_in(body)
        except Exception:
            continue
        if box[4] - box[1] < 12.0:
            continue
        radii = [math.hypot(x, z) for x in (box[0], box[3]) for z in (box[2], box[5])]
        if not radii or min(radii) - 1.0 > face_r or max(radii) + 1.0 < face_r:
            continue
        saw_body = True
        hit = _has_hole_axis(body, point_m, radius_m, near_m)
        if hit is True:
            return True
        if hit is False:
            saw_no = True
    if not saw_body:
        return None
    return False if saw_no else None


def _has_hole_axis(body, point_m, radius_m: float, near_m: float):
    """True when a cylindrical face of this radius has its axis at the hole point."""
    if body is None:
        return False
    try:
        raw = body.GetFaces()
    except Exception:
        return None
    faces = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    if not faces:
        return None
    readable = 0
    for face in faces:
        try:
            surface = com_value(face.GetSurface)
            flag = surface.IsCylinder
            flag = bool(flag() if callable(flag) else flag)
            readable += 1
        except Exception:
            continue
        if not flag:
            continue
        try:
            values = [float(v) for v in com_value(surface.CylinderParams)]
        except Exception:
            continue
        if len(values) < 7 or abs(values[6] - radius_m) > 0.03 * _INCH:
            continue
        if _axis_distance(values[0:3], values[3:6], point_m) <= near_m:
            return True
    return False if readable else None


def _axis_distance(origin, direction, point) -> float:
    axis = (direction[0], direction[1], direction[2])
    length = math.sqrt(sum(v * v for v in axis)) or 1.0
    rel = (point[0] - origin[0], point[1] - origin[1], point[2] - origin[2])
    cross = (
        rel[1] * axis[2] - rel[2] * axis[1],
        rel[2] * axis[0] - rel[0] * axis[2],
        rel[0] * axis[1] - rel[1] * axis[0],
    )
    return math.sqrt(sum(v * v for v in cross)) / length


def _hide_construction(model) -> None:
    """Hide helices, sketches, and planes added for the stair. Leave Front, Top, and Right."""
    keep = {"Front Plane", "Top Plane", "Right Plane", "Front", "Top", "Right"}
    items = []
    for feature in iter_features(model):
        name = _feature_name(feature)
        if not name or name in keep:
            continue
        if name.endswith("Pln") or name.startswith("Plane"):
            items.append((feature, name, "PLANE"))
        elif name.endswith("Sk") or name.startswith("Sketch"):
            items.append((feature, name, "SKETCH"))
        elif "Helix" in name or name.startswith("Helix"):
            items.append((feature, name, "REFERENCECURVES"))
    for feature, name, kind in items:
        _blank_construction(model, feature, name, kind)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()


def _blank_construction(model, feature, name: str, kind: str) -> None:
    _clear_selection(model)
    nothing = com_nothing()
    selected = False
    with contextlib.suppress(Exception):
        selected = bool(model.Extension.SelectByID2(name, kind, 0.0, 0.0, 0.0, False, 0, nothing, 0))
    if not selected and kind == "REFERENCECURVES":
        with contextlib.suppress(Exception):
            selected = bool(model.Extension.SelectByID2(name, "REFCURVE", 0.0, 0.0, 0.0, False, 0, nothing, 0))
    if not selected:
        with contextlib.suppress(Exception):
            selected = bool(feature.Select2(False, 0))
    if not selected:
        return
    if kind == "SKETCH":
        with contextlib.suppress(Exception):
            model.BlankSketch()
    else:
        with contextlib.suppress(Exception):
            blank = model.BlankRefGeom
            blank() if callable(blank) else com_value(blank)
    _clear_selection(model)


# ------------------------------------------------------------------ helpers


def _plane(model, short: str):
    plane = find_feature(model, f"{short} Plane") or find_feature(model, short)
    if plane is None:
        raise SolidWorksError(f"Could not find the {short} Plane.")
    return plane


def _offset_from(model, base, distance_in: float, name: str):
    before = _names(model)
    _clear_selection(model)
    if not base.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the base plane.")
    model.CreatePlaneAtOffset(abs(distance_in) * _INCH, distance_in < 0)
    _clear_selection(model)
    return _rename_new(model, before, name, "offset plane")


def _extrude(model, sketch, depth_in: float, name: str, *, merge: bool):
    _clear_selection(model)
    if not _select_feature(model, sketch, "SKETCH", mark=0, append=False):
        raise SolidWorksError(f"{name}: could not select the sketch.")
    feature = extrude_blind(model.FeatureManager, depth_in * _INCH, merge=merge)
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    return feature


def _recover(model) -> None:
    with contextlib.suppress(Exception):
        if com_value(model.GetActiveSketch2) is not None:
            _close_sketch(model)
    _clear_selection(model)
