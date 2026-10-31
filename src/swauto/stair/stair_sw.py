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
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import BuildStopped, SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rename_feature
from swauto.parts import extrude_blind, new_part, quiet
from swauto.stair.development import (
    END_HOLE_RADIUS_IN,
    SLOT_LENGTH_IN,
    DevelopedStringer,
    develop_both,
    flight_step,
    flight_treads,
    flight_turns,
)
from swauto.stair.splitter import (
    GAP_IN,
    RELIEF_IN,
    Joint,
    Relief,
    SplitSettings,
    clashes,
    cut_span,
    joints,
    relief_cutter,
    reliefs,
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
    _select_data,
    create_tank_shell,
)
from swauto.tank.spec import WALL_OD, Course, TankSpec, default_stagger_for_course

if TYPE_CHECKING:
    from swauto.stair.grab_sw import GrabRail

_INCH = 0.0254
_DELETE_ABSORBED = 1  # swDeleteSelectionOptions_e
_DELETE_CHILDREN = 2
TREAD_CLEAR_IN = (CLEAR_IN - TREAD_PLATE_IN) / 2.0
# swUserPreferenceToggle_e.swUserEnableFreezeBar, swMoveFreezeBarTo_e.swMoveFreezeBarToAfterFeature
_SW_ENABLE_FREEZE_BAR = 461
_SW_FREEZE_AFTER_FEATURE = 3


class StairResult:
    """``shell_bodies`` names the bodies that were in the part before the stair: the shell's plates."""

    def __init__(self, title: str, model, note: str, shell_bodies: frozenset[str] = frozenset()) -> None:
        self.title = title
        self.model = model
        self.note = note
        self.shell_bodies = shell_bodies


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
    grab: GrabRail | None = None, ground_in: float = 0.0, shell_height_in: float | None = None,
    splits: SplitSettings | None = None, inner_rail: InnerRail | None = None, rail_splits: tuple = (),
) -> StairResult:
    """New part, then the stair. ``shell`` adds the tank; the stringers do not change.

    ``platforms`` mid platforms split the stair into equal flights, and
    ``top_platform`` puts the same platform past the top tread. ``posts`` are
    the treads in each flight that get a handrail post on the outer stringer;
    ``platform_post_in`` sets the platform posts in from the platform ends, and
    ``top_rail`` and ``mid_rail`` run the outer top rail and midrail along the posts,
    the midrail ``platform_mid_top`` over each platform's grating. ``grab`` runs the
    outer grab rail on the flight posts. ``ground_in`` is the stair's ground on Y,
    the floor being 0; the shell is ``shell_height_in`` tall when given. ``inner_rail`` adds the inside
    handrail, and ``rail_splits`` ((side, pan of the post below the bay), ...) split the rails into pieces.
    """
    flight_treads(stair.treads, platforms)
    profiles = _platform_profiles(app) if platforms or top_platform else None
    post_file = _post_profile(app) if posts or inner_rail is not None else None
    if shell:
        return create_stair_on_tank(
            app, stair, wall_in, progress=progress, platforms=platforms, top_platform=top_platform, profiles=profiles,
            posts=posts, post_profile=post_file, platform_post_in=platform_post_in, top_rail=top_rail,
            mid_rail=mid_rail, platform_mid_top=platform_mid_top, grab=grab, ground_in=ground_in,
            shell_height_in=shell_height_in, splits=splits, inner_rail=inner_rail, rail_splits=rail_splits,
        )
    stair.validate()
    if wall_in <= 0 or wall_in >= TREAD_MARK_IN or wall_in * 2 >= TREAD_DEPTH_IN:
        raise ValueError("Pan wall must be greater than zero and thinner than the tread.")
    model = new_part(app)
    with quiet(app, model):
        return build_stair_on_model(
            model, stair.shell_od_in, stair, wall_in, progress=progress, platforms=platforms,
            top_platform=top_platform, profiles=profiles, posts=posts, post_profile=post_file,
            platform_post_in=platform_post_in, top_rail=top_rail, mid_rail=mid_rail,
            platform_mid_top=platform_mid_top, grab=grab, ground_in=ground_in, splits=splits, inner_rail=inner_rail,
            rail_splits=rail_splits,
        )


def create_stair_on_tank(
    app, stair: StringerMock, wall_in: float, progress=None, *, platforms: int = 0, top_platform: bool = False,
    profiles: tuple[str, str, str] | None = None, posts: tuple[int, ...] = (), post_profile: str | None = None,
    platform_post_in: float | None = None, top_rail: bool = False, mid_rail: bool = False,
    platform_mid_top: float | None = None, grab: GrabRail | None = None, ground_in: float = 0.0,
    shell_height_in: float | None = None, splits: SplitSettings | None = None, inner_rail: InnerRail | None = None,
    rail_splits: tuple = (),
) -> StairResult:
    """New part with the shell at the Stringer tab's OD radius, then the stair. The shell is one course of
    ``shell_height_in`` when given, so the stair can be checked against its top."""
    stair.validate()
    if wall_in <= 0 or wall_in >= TREAD_MARK_IN or wall_in * 2 >= TREAD_DEPTH_IN:
        raise ValueError("Pan wall must be greater than zero and thinner than the tread.")
    if profiles is None and (platforms or top_platform):
        profiles = _platform_profiles(app)
    if post_profile is None and (posts or inner_rail is not None):
        post_profile = _post_profile(app)
    tank = TankSpec(diameter_in=2.0 * stair.shell_od_in, diameter_basis=WALL_OD)
    if shell_height_in:
        tank = TankSpec(
            diameter_in=2.0 * stair.shell_od_in, diameter_basis=WALL_OD,
            courses=[Course(shell_height_in, 1.0, stagger=default_stagger_for_course(1))],
        )
    shell = create_tank_shell(app, tank)
    model = shell.live.model
    outer_m, _inner_m = course_radii_m(tank, tank.active_courses()[0])
    shell_od = outer_m / _INCH
    _progress(progress, "shell built")
    with quiet(app, model):
        return build_stair_on_model(
            model, shell_od, stair, wall_in, progress=progress, platforms=platforms, top_platform=top_platform,
            profiles=profiles, posts=posts, post_profile=post_profile, platform_post_in=platform_post_in,
            top_rail=top_rail, mid_rail=mid_rail, platform_mid_top=platform_mid_top, grab=grab,
            ground_in=ground_in, splits=splits, inner_rail=inner_rail, rail_splits=rail_splits,
        )


def _platform_profiles(app) -> tuple[str, str, str]:
    """C4x5.4 for the platform frames (a C6 platform's file is beside it), L6x6x3/8 for the stringer clips,
    L3x3x3/8 for the knee braces."""
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
    ground_in: float = 0.0,
    splits: SplitSettings | None = None,
    inner_rail: InnerRail | None = None,
    rail_splits: tuple = (),
) -> StairResult:
    """Stringers (unless already there), then tread by tread: pan, inner bolts, outer bolts.

    With ``platforms`` the stair is that many plus one equal flights, each the
    one below turned and raised past its mid platform (``stair.platform_specs``
    their shapes, 36 in straight by default). Platform frames and
    their stringer clips go in last: a higher flight's stringer cuts start
    inside the platform below it. ``profiles`` is (C4 frame, 6x6 clip, 3x3 knee).
    Handrail posts at the ``posts`` treads of every flight follow, on ``post_profile``,
    and with ``top_rail`` and ``mid_rail`` the outer top rail and midrail along them,
    and with ``grab`` the grab rail on the flight posts. ``ground_in`` is where the stair's ground is on Y.
    With ``splits`` the stringers are cut into the splitter's pieces after the treads are bolted on.
    """
    where = stair_places(stair, shell_od, platforms, ground_in)
    per_flight, flight, layout, offsets, places = (
        where.per_flight, where.flight, where.layout, where.offsets, where.places
    )
    shell_bodies = frozenset(_body_names(model))
    platform_note = ""
    post_note = ""
    try:
        if stringers:
            for k, at in enumerate(offsets):
                build_flight_stringers(model, flight, shell_od, at=at, suffix=flight_suffix(k), progress=progress,
                                       foot_holes=k > 0)
            freeze_note = _freeze_stringers(model)
        else:
            freeze_note = ""
        done = 0
        total = 0
        # The pans are the same shape. Model the first, then copy it turned about the tank
        # axis and raised for every later tread. The bolt holes come after every pan is in
        # place: each hole also goes through the stringer, so a copy must not carry them.
        # One rebuild per tread, before its bolts, so a cut is not lost.
        if do_treads and places:
            _tread(model, layout, places[0], wall_in)
            _progress(progress, f"tread {places[0].index} placed")
            master = _tread_body(model, places[0])
            for place in places[1:]:
                copied = master is not None and _copy_tread(model, master, places[0], place)
                if not copied:
                    _tread(model, layout, place, wall_in)
                _progress(progress, f"tread {place.index} {'copied' if copied else 'placed'}")
        for place in (places if do_treads else []):
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
        split_note = ""
        if splits is not None and stringers:
            split_note = split_stringers(model, layout, flight, offsets, splits, progress)
        if platforms or top_platform:
            if profiles is None:
                raise SolidWorksError("Platforms need the C4, 6x6 angle and 3x3 angle weldment profiles.")
            platform_note = _platforms(
                model, layout, places, per_flight, platforms, top_platform, profiles, shell_od, progress,
                stair.platform_specs,
            )
        if posts:
            if post_profile is None:
                raise SolidWorksError("Handrail posts need the L2x2 angle weldment profile.")
            post_note = _handrail_posts(
                model, layout, places, per_flight, posts, post_profile, platforms, top_platform,
                platform_post_in, top_rail, mid_rail, platform_mid_top, grab, progress, stair.platform_specs,
            )
        if inner_rail is not None and any(inner_rail.posts):
            if post_profile is None:
                raise SolidWorksError("Handrail posts need the L2x2 angle weldment profile.")
            post_note = (post_note + " " + _inner_handrail(
                model, layout, places, per_flight, inner_rail, post_profile, platforms, top_platform, progress,
                stair.platform_specs,
            )).strip()
        if rail_splits and post_profile is not None:
            post_note = (post_note + " " + _rail_splits(
                model, layout, places, per_flight, rail_splits, posts, inner_rail, post_profile,
                top_rail or mid_rail, grab, progress,
            )).strip()
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
        f"the top tread's surface {places[-1].y1 - ground_in:.2f} in above the ground "
        f"({stair.treads} rises of {stair.rise_in:.4g} in). "
        f"Bolt pairs through {done} of {total} stringer-to-tread joints."
    )
    if platform_note:
        note = f"{note} {platform_note}"
    if post_note:
        note = f"{note} {post_note}"
    if split_note:
        note = f"{note} {split_note}"
    if freeze_note:
        note = f"{note} {freeze_note}"
    return StairResult(
        title=str(com_value(model.GetTitle) or "Part"), model=model, note=note, shell_bodies=shell_bodies
    )


@dataclass(frozen=True)
class StairPlaces:
    """Where the clockwise build puts every flight and pan, before any mirror or turn. ``offsets`` are
    each flight's (turn, lift); ``places`` every pan, lowest first, numbered the way braces count them."""

    per_flight: int
    flight: StringerMock
    layout: object  # StringerLayout of one flight
    offsets: tuple[tuple[float, float], ...]
    places: tuple[TreadPlace, ...]


def stair_places(stair: StringerMock, shell_od: float, platforms: int = 0, ground_in: float = 0.0) -> StairPlaces:
    """The flights and pans of a stair on a shell of OD radius ``shell_od``, its ground at ``ground_in`` on Y.

    No SolidWorks: the build and the stretchout preview both place the stair from this.
    """
    per_flight = flight_treads(stair.treads, platforms)
    flight = replace(stair, shell_od_in=shell_od, treads=per_flight, outside_face=True)
    layout = layout_stringer(flight)
    _turn, lift = flight_step(flight)
    turns = flight_turns(flight, platforms)
    # The ground is tread zero's walking surface (the lisp's Height/Angle pick), so tread i stands
    # i rises up and the top tread's surface is at the stair's height. The layout centres each
    # 2-1/2 in tread on its rise; every flight comes down half a tread to put the surfaces there.
    ground = ground_in - TREAD_MARK_IN / 2.0
    offsets = tuple((turns[k], ground + k * lift) for k in range(platforms + 1))
    places = tuple(
        _moved_place(place, k * per_flight + place.index, *offsets[k])
        for k in range(platforms + 1)
        for place in _tread_places(layout)
    )
    return StairPlaces(per_flight, flight, layout, offsets, places)


def flight_suffix(flight: int) -> str:
    """Name ending for a flight's stringers: none for the first, F2, F3... above it."""
    return "" if flight == 0 else f"F{flight + 1}"


SPLICE_THK_IN = 0.375  # not in the lisp: the stringer's own 3/8, on its back face (the treads are on the walk face)
_SPLIT_MARGIN_IN = 1.0


def split_joints(flight: StringerMock, splits: SplitSettings) -> dict[str, list[Joint]]:
    """Each stringer's joints in one flight, by side ("In", "Out"). The same treads on both."""
    inner, outer = develop_both(flight)
    return {
        "In": joints(inner, flight.rise_in, flight.treads, splits),
        "Out": joints(outer, flight.rise_in, flight.treads, splits),
    }


def split_stringers(model, layout, flight: StringerMock, offsets, splits: SplitSettings, progress=None) -> str:
    """Cut every flight's stringers into the splitter's pieces, each joint spliced by a plate on the stringer's
    back face, with the four 13/16 holes through plate and stringer, and the inner stringer's 1 in rounds. The
    plates' holes go in before their trims and round, the order in which they still flatten.

    The cut is a level 1/4 in slab through the stringer's own band at the joint, as wide as the stringer is
    there; the plate starts as a rolled sheet-metal blank over its extent, like the stringer's, so it flattens,
    and is trimmed to the stringer's top and bottom edges by the same helical cuts that shape the stringer,
    swept through the plate's band. Each round is cut from the one piece or plate it belongs to. Run it before
    platforms, posts and clips: those cuts take whatever is in the band.
    """
    inner_dev, outer_dev = develop_both(flight)
    tank_face = flight.shell_od_in + flight.gap_in
    sides = (
        (inner_dev, tank_face, tank_face + THICKNESS_IN, "In", (tank_face - SPLICE_THK_IN, tank_face)),
        (outer_dev, layout.outside_radius_in - THICKNESS_IN, layout.outside_radius_in, "Out",
         (layout.outside_radius_in, layout.outside_radius_in + SPLICE_THK_IN)),
    )
    made = 0
    missed = []
    round_count = [0, 0]  # cut, wanted; not "rounds": the holes below use that name
    for k, at in enumerate(offsets):
        turn, lift = at
        for dev, r_in, r_out, side, plate_band in sides:
            cuts = joints(dev, flight.rise_in, flight.treads, splits)
            if not cuts:
                continue
            name = f"EliteSplit{side}{flight_suffix(k)}"
            radius = dev.radius_in
            for joint in cuts:
                tag = f"{name}T{joint.tread:02d}"
                x0, x1 = cut_span(dev, joint)
                _sector_cut(model, (r_in - 0.03, r_out + 0.03), turn + (x0 - _SPLIT_MARGIN_IN) / radius,
                            turn + (x1 + _SPLIT_MARGIN_IN) / radius, lift + joint.y_cut - GAP_IN / 2.0,
                            lift + joint.y_cut + GAP_IN / 2.0, f"{tag}Cut")
                count = len(_stringer_pieces(model, f"{tag}Cut", (r_in, r_out)))
                if count != 2:
                    missed.append(f"{tag} (the cut left {count} stringer piece{'s' if count != 1 else ''}, not 2)")
                _progress(progress, f"{tag} cut")
                # The stringer's rounds go in before the plate, so nothing else is behind them yet.
                for index, relief in enumerate((r for r in reliefs(dev, joint) if r.piece != "plate"), start=1):
                    round_count[1] += 1

                    def half(cut=f"{tag}Cut", band=(r_in, r_out), which=relief.piece):
                        found = _stringer_pieces(model, cut, band)
                        return (found[0] if which == "lower" else found[1]) if len(found) == 2 else None

                    round_count[0] += int(_relief_cut(model, dev, relief, at, dev.radius_in, True, half,
                                                      f"{tag}Round{index}"))
                    _progress(progress, f"{tag} round {index}")
                xs = [x for x, _y in joint.plate]
                ys = [y for _x, y in joint.plate]
                # Rolled the way the stringer blank is, so the plate is sheet metal and flattens for burning.
                _rolled_blank(model, plate_band[0], plate_band[1], turn + (min(xs) - _SPLIT_MARGIN_IN) / radius,
                              turn + (max(xs) + _SPLIT_MARGIN_IN) / radius, lift + min(ys), lift + max(ys),
                              f"{tag}Plate")
                _progress(progress, f"{tag} splice placed")
            # One small jig a hole: the holes in a row are too far apart for one flat jig on a curved face. The
            # holes go in before the plates are trimmed and rounded: in the other order SolidWorks 2013 would
            # not flatten the plates.
            rounds = replace(dev, slotted=False)
            outward = abs(dev.radius_in - r_out) <= abs(dev.radius_in - r_in)
            for joint in cuts:
                tag = f"{name}T{joint.tread:02d}"
                hit = 0
                for index, hole in enumerate(joint.holes, start=1):
                    before = _names(model)
                    try:
                        hit += int(_end_hole_pair(model, rounds, dev.radius_in, outward, [hole], f"{tag}H{index}", at))
                    except Exception:
                        _discard_since(model, before)
                made += 1
                if hit < len(joint.holes):
                    missed.append(f"{tag} ({len(joint.holes) - hit} of {len(joint.holes)} holes)")
                _progress(progress, f"{tag} holes {'cut' if hit == len(joint.holes) else 'missed'}")
            # Trim this side's plates in the flight to the stringer's edges: only plates are in their band yet.
            g = _stringer_geometry(layout, dev, r_in, r_out)
            far = g["phi_end"]
            helix = ((plate_band[0] + plate_band[1]) / 2.0, g["rise_per_rad"] * far, far / (2.0 * math.pi))
            span = 30.0

            def plates(names=tuple(f"{name}T{joint.tread:02d}Plate" for joint in cuts)):
                return [body for feature in names for body in _bodies_made_by(model, feature)]

            for label, y0, y1 in (("Top", lift + g["top_at_zero"], lift + g["top_at_zero"] + span),
                                  ("Bottom", lift + g["bottom_at_zero"] - span, lift + g["bottom_at_zero"])):
                # Scoped to the plates, past both their faces: a trim that ran into the stringer shaved it, and one
                # that stopped on the face they share left the plates unflattenable (SolidWorks 2013).
                before = _names(model)
                try:
                    _cut_sweep(model, helix, (plate_band[0] - 0.03, plate_band[1] + 0.03), y0, y1,
                               f"{name}Plate{label}", turn, scope=plates)
                except SolidWorksError:
                    _discard_since(model, before)
                    _cut_sweep(model, helix, _plate_trim_band(plate_band, (r_in, r_out)), y0, y1,
                               f"{name}Plate{label}", turn)
            _rebuild(model)
            _keep_bent_view(model)  # the plates show bent, like the stringers, until Flatten is clicked
            _progress(progress, f"{name} splices trimmed")
            for joint in cuts:
                tag = f"{name}T{joint.tread:02d}"
                for relief in (r for r in reliefs(dev, joint) if r.piece == "plate"):
                    round_count[1] += 1

                    def plate(feature=f"{tag}Plate"):
                        found = _bodies_made_by(model, feature)
                        return found[0] if len(found) == 1 else None

                    # The jig goes on the plate's far side; the stringer is on its near side.
                    round_count[0] += int(_relief_cut(model, dev, relief, at, plate_band[0], False, plate,
                                                      f"{tag}PlateRound"))
                    _progress(progress, f"{tag} plate round")
    note = (
        f"Stringers split at {made} joint{'s' if made != 1 else ''}: a 1/4 in level cut, a {SPLICE_THK_IN:g} in "
        "splice plate on the stringer's back face, and four 13/16 holes through both"
        + (f"; {round_count[0]} of {round_count[1]} inner stringer 1 in rounds cut" if round_count[1] else "") + "."
    )
    checks = [text for dev in (inner_dev, outer_dev)
              for text in clashes(dev, joints(dev, flight.rise_in, flight.treads, splits), splits.avoid)]
    if not made:
        return ""
    return (note + (f" Missed: {'; '.join(missed)}." if missed else "")
            + (f" Check: {' '.join(checks)}" if checks else ""))


def _plate_trim_band(plate_band: tuple[float, float], stringer: tuple[float, float]) -> tuple[float, float]:
    """The radii the plates' trims cut through: past the plate's free face, but stopping at the face it shares with
    the stringer. Run into the stringer, the trim shaved it along its top and bottom edges, and the shaved piece and
    plate no longer flattened (SolidWorks 2013)."""
    if plate_band[1] <= stringer[0] + 1e-6:  # the plate is inside the stringer, toward the tank
        return plate_band[0] - 0.03, plate_band[1]
    return plate_band[0], plate_band[1] + 0.03


def _stringer_pieces(model, cut: str, band: tuple[float, float]) -> list:
    """The stringer bodies the cut feature ``cut`` left, lowest first: two when it split the stringer."""
    found = []
    for body in _bodies_made_by(model, cut):
        with contextlib.suppress(Exception):
            box = _box_in(body)
            radii = [math.hypot(x, z) for x in (box[0], box[3]) for z in (box[2], box[5])]
            if min(radii) - 1.0 <= band[1] and max(radii) + 1.0 >= band[0]:
                found.append((box[1], body))
    return [body for _y, body in sorted(found, key=lambda item: item[0])]


def _bodies_made_by(model, feature_name: str) -> list:
    """Bodies with ``feature_name`` in their history. A body a cut splits off lists only that cut."""
    found = []
    for body in _bodies(model):
        with contextlib.suppress(Exception):
            features = com_value(body.GetFeatures)
            if any(str(com_value(f.Name) or "") == feature_name for f in features or ()):
                found.append(body)
    return found


def _relief_cut(model, dev: DevelopedStringer, relief: Relief, at: tuple[float, float], face_r: float,
                outward: bool, find, name: str) -> bool:
    """Cut one 1 in round from the body ``find()`` gives, alone: a jig against its face at ``face_r`` (on the
    outward side or the inward one), the round's sliver sketched on the jig, cut one way scoped to the body, the
    jig deleted. The body is looked up just before the cut, as rebuilds can leave an older handle stale. True
    once the body has the round's 1 in face. A miss does not raise."""
    radius = dev.radius_in
    turn, lift = at
    points = [(x + turn * radius, y + lift) for x, y in (*relief_cutter(relief), relief.middle)]
    phis = [x / radius for x, _y in points]
    phi = (min(phis) + max(phis)) / 2.0
    half_along = (max(phis) - min(phis)) / 2.0 * radius + 0.6
    ys = [y for _x, y in points]
    y_mid, half_y = (min(ys) + max(ys)) / 2.0, (max(ys) - min(ys)) / 2.0 + 0.6
    jig_thick = 0.5
    r0, r1 = (face_r, face_r + jig_thick) if outward else (face_r - jig_thick, face_r)
    center = (-((r0 + r1) / 2.0) * math.sin(phi), y_mid, ((r0 + r1) / 2.0) * math.cos(phi))

    def on_face(x: float, y: float) -> tuple[float, float, float]:
        return (-face_r * math.sin(x / radius) * _INCH, y * _INCH, face_r * math.cos(x / radius) * _INCH)

    before_all = _names(model)
    try:
        base = _offset_from(model, _plane(model, "Top"), y_mid - half_y, f"{name}JigPln")
        sketch = _sketch_on(model, base, f"{name}JigSk", lambda: _plan_rect(model, phi, r0, r1, half_along))
        _extrude(model, sketch, half_y * 2.0, f"{name}Jig", merge=False)
        _rebuild(model)
        jig = _body_near(model, center, max_height=half_y * 2.0 + 0.4, max_dist=1.5)
        face = _face_at_radius(jig, face_r) if jig is not None else None
        if face is None or not _select_face(model, face):
            raise SolidWorksError(f"{name}: no jig face to sketch the round on.")
        before = _names(model)
        manager = model.SketchManager
        with contextlib.suppress(Exception):
            manager.AddToDB = True
        with contextlib.suppress(Exception):
            manager.DisplayWhenAdded = False
        manager.InsertSketch(True)
        try:
            data = [float(v) for v in com_value(com_value(com_value(model.GetActiveSketch2).ModelToSketchTransform)
                                                          .ArrayData)]
            *path, m = (_to_sketch(data, on_face(x, y)) for x, y in points)
            # Out past the edges and round the corner, then the arc from the end back to the start.
            drawn = (all(manager.CreateLine(a[0], a[1], 0.0, b[0], b[1], 0.0) is not None
                         for a, b in zip(path, path[1:], strict=False))
                     and manager.Create3PointArc(path[-1][0], path[-1][1], 0.0, path[0][0], path[0][1], 0.0,
                                                 m[0], m[1], 0.0) is not None)
            if not drawn:
                raise SolidWorksError(f"{name}: the round's sketch did not draw.")
        except Exception:
            _recover(model)
            raise
        _close_sketch(model)
        round_sketch = _rename_new(model, before, f"{name}Sk", "round sketch")
        body = find()
        if body is None:
            raise SolidWorksError(f"{name}: no body to round.")
        feature = _cut_one_way_in(model, round_sketch, jig_thick + THICKNESS_IN + 0.35, body)
        if feature is None:
            raise SolidWorksError(f"{name}: the round was not cut.")
        with contextlib.suppress(Exception):
            rename_feature(feature, name)
        _rebuild(model)
        jig = _body_near(model, center, max_height=half_y * 2.0 + 0.4, max_dist=1.5)
        if jig is not None:
            _delete_body(model, jig)
        _rebuild(model)
    except Exception:
        _discard_since(model, before_all)
        return False
    probe = on_face(relief.center[0] + turn * radius, relief.center[1] + lift)
    return any(_has_hole_axis(piece, probe, RELIEF_IN * _INCH, 0.1 * _INCH) is True
               for piece in _bodies_made_by(model, name))


CCW_MIRROR = "EliteStairCCW"
_MIRROR_PLANE_MARK = 2
_MIRROR_BODY_MARK = 256


def is_counterclockwise(model) -> bool:
    """The stair in this part was mirrored to climb counterclockwise."""
    return find_feature(model, CCW_MIRROR) is not None


def mirror_stair(model, keep: frozenset[str] = frozenset(), progress=None) -> str:
    """Turn a finished stair counterclockwise: mirror every stair body through the Right plane, then delete the
    clockwise ones. ``keep`` names the bodies that were in the part before the stair (the shell's plates).

    The stair is built climbing clockwise seen from above, and the lisp draws a counterclockwise one the same
    way, as the mirror of its clockwise one. The Right plane holds the tank axis and the stair's foot at +Z, so
    the foot stays put and the stair climbs toward +X instead of -X. Braces and clips go in before this: they
    find the treads by their clockwise angles.
    """
    stair = [body for body in _bodies(model) if _body_name(body) not in keep]
    if not stair:
        raise SolidWorksError("There is no stair in this part to mirror.")
    names = {_body_name(body) for body in stair}
    before = _names(model)
    before_bodies = _body_names(model)
    _clear_selection(model)
    nothing = com_nothing()
    right = _feature_name(_plane(model, "Right"))
    if not model.Extension.SelectByID2(right, "PLANE", 0.0, 0.0, 0.0, False, _MIRROR_PLANE_MARK, nothing, 0):
        raise SolidWorksError("Could not select the Right plane to mirror the stair.")
    picked = _select_bodies(model, stair, _MIRROR_BODY_MARK)
    if picked != len(stair):
        _clear_selection(model)
        raise SolidWorksError(f"Could select only {picked} of the stair's {len(stair)} bodies to mirror.")
    feature = _insert_body_mirror(model)
    _clear_selection(model)
    if feature is None:
        _discard_since(model, before)
        raise SolidWorksError("SolidWorks did not mirror the stair.")
    with contextlib.suppress(Exception):
        rename_feature(feature, CCW_MIRROR)
    _rebuild(model)
    mirrored = [body for body in _bodies(model) if _body_name(body) not in before_bodies]
    if len(mirrored) != len(stair):
        _discard_since(model, before)
        raise SolidWorksError(f"The mirror made {len(mirrored)} bodies for the stair's {len(stair)}.")
    _progress(progress, "stair mirrored")
    clockwise = [body for body in _bodies(model) if _body_name(body) in names]
    _clear_selection(model)
    if len(clockwise) != len(stair) or _select_bodies(model, clockwise, 0) != len(stair):
        _clear_selection(model)
        _discard_since(model, before)
        raise SolidWorksError("Could not select the clockwise stair to delete it after the mirror.")
    if not _insert_delete_bodies(model):
        _clear_selection(model)
        _discard_since(model, before)
        raise SolidWorksError("SolidWorks did not delete the clockwise stair after the mirror.")
    _rebuild(model)
    left = [body for body in _bodies(model) if _body_name(body) in names]
    if left:
        _discard_since(model, before)
        raise SolidWorksError(f"{len(left)} clockwise stair bodies were left after the mirror.")
    _keep_bent_view(model)
    lines = _redraw_shell_lines(model, lambda p: (-p[0], p[1], p[2]), "CCW")
    _progress(progress, "clockwise stair deleted")
    with contextlib.suppress(Exception):
        model.ViewZoomtofit2()
        model.GraphicsRedraw2()
    return (
        f"Mirrored through the Right plane, so the stair climbs counterclockwise seen from above "
        f"({_count(len(stair), 'body', 'bodies')}); the clockwise ones it was built from are deleted."
        f"{_lines_note(lines)}"
    )


TURN_FEATURE = "EliteStairTurn"


def turn_stair(model, angle: float, keep: frozenset[str] = frozenset(), progress=None) -> str:
    """Turn every stair body about the tank axis by ``angle`` (radians the stair's way: from +Z toward -X,
    clockwise seen from above), to put the stair at its orientation. ``keep`` names the shell's bodies.

    The stair is built, braced and mirrored at its own angles, then one Move/Copy Body turns the finished
    bodies, the way the treads are copied, so none of that is built anywhere new.
    """
    stair = [body for body in _bodies(model) if _body_name(body) not in keep]
    if not stair:
        raise SolidWorksError("There is no stair in this part to turn.")
    try:
        x, y, z = _mass_point(stair[0])
    except Exception as exc:
        raise SolidWorksError("Could not read where the stair is before turning it.") from exc
    c, sn = math.cos(angle), math.sin(angle)

    def turned(point):
        return (point[0] * c - point[2] * sn, point[1], point[2] * c + point[0] * sn)

    before = _names(model)
    _clear_selection(model)
    picked = _select_bodies(model, stair, 1)
    if picked != len(stair):
        _clear_selection(model)
        raise SolidWorksError(f"Could select only {picked} of the stair's {len(stair)} bodies to turn.")
    feature = None
    try:
        # A right-hand turn about +Y is the opposite of the stair's angle (see _copy_turned).
        feature = model.FeatureManager.InsertMoveCopyBody2(
            0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            0.0, -float(angle), 0.0,
            False, 1,
        )
    except Exception:
        _recover(model)
    _clear_selection(model)
    if feature is not None:
        # Before the rebuild: the feature handle goes stale after it.
        with contextlib.suppress(Exception):
            rename_feature(feature, TURN_FEATURE)
    fresh = [item for item in iter_features(model) if _feature_name(item) not in before]
    _rebuild(model)
    if not fresh or _body_at(model, turned((x, y, z))) is None:
        _discard_since(model, before)
        raise SolidWorksError("SolidWorks did not turn the stair to its orientation.")
    _keep_bent_view(model)
    lines = _redraw_shell_lines(model, turned, "Turn")
    _progress(progress, "stair turned")
    with contextlib.suppress(Exception):
        model.ViewZoomtofit2()
        model.GraphicsRedraw2()
    return (
        f"Turned {math.degrees(angle):.2f}° about the tank axis to its orientation "
        f"({_count(len(stair), 'body', 'bodies')}).{_lines_note(lines)}"
    )


_SHOWN = 2  # swVisibilityState_e; a hidden sketch reads 1


def _redraw_shell_lines(model, move, suffix: str) -> int:
    """Knee braces draw a 3D line down the shell where a pad sits below it. Mirroring or turning the bodies
    leaves sketches where they are, so draw each line still showing again through ``move`` (a point, in
    meters) and hide the old one. Returns how many."""
    count = 0
    for feature in list(iter_features(model)):
        name = _feature_name(feature)
        if "ShellLine" not in name:
            continue
        try:
            if com_value(feature.Visible) != _SHOWN:
                continue
            sketch = com_value(feature.GetSpecificFeature2)
            ends = []
            for segment in com_value(sketch.GetSketchSegments) or ():
                a, b = com_value(segment.GetStartPoint2), com_value(segment.GetEndPoint2)
                ends.append(
                    (move((float(a.X), float(a.Y), float(a.Z))), move((float(b.X), float(b.Y), float(b.Z))))
                )
        except Exception:
            continue
        if not ends:
            continue
        before = _names(model)
        # With a 3D sketch still selected, Insert3DSketch opens that one instead of a new one.
        _clear_selection(model)
        manager = model.SketchManager
        manager.Insert3DSketch(True)
        for (x0, y0, z0), (x1, y1, z1) in ends:
            manager.CreateLine(x0, y0, z0, x1, y1, z1)
        manager.Insert3DSketch(True)
        with contextlib.suppress(SolidWorksError):
            _rename_new(model, before, f"{name}{suffix}", "shell line")
        _blank_construction(model, feature, name, "SKETCH")
        count += 1
    return count


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _lines_note(lines: int) -> str:
    return f" Redrew {_count(lines, 'shell line', 'shell lines')} under knee brace pads with it." if lines else ""


def _body_name(body) -> str:
    try:
        return str(body.Name)
    except Exception:
        return ""


def _select_bodies(model, bodies, mark: int) -> int:
    """Add each body to the selection with ``mark``. How many took."""
    data = _select_data(model, mark)
    nothing = com_nothing()
    count = 0
    for body in bodies:
        ok = False
        if data is not None:
            with contextlib.suppress(Exception):
                ok = bool(body.Select2(True, data))
        if not ok:
            with contextlib.suppress(Exception):
                ok = bool(
                    model.Extension.SelectByID2(_body_name(body), "SOLIDBODY", 0.0, 0.0, 0.0, True, mark, nothing, 0)
                )
        count += int(ok)
    return count


def _insert_body_mirror(model):
    """Mirror the selected bodies about the selected plane, unmerged, as their own bodies."""
    manager = model.FeatureManager
    for method_name, args in (
        ("InsertMirrorFeature2", (True, False, False, False, 0)),
        ("InsertMirrorFeature", (True, False, False, False)),
    ):
        try:
            feature = getattr(manager, method_name)(*args)
        except Exception:
            continue
        if feature is not None:
            return feature
    return None


def _insert_delete_bodies(model) -> bool:
    """Delete Body on the selected bodies. SolidWorks 2013 has only InsertDeleteBody, a no-argument call
    that late binding makes a property: reading it is what deletes, so it is read once, through com_value."""
    try:
        result = com_value(model.FeatureManager.InsertDeleteBody)
    except Exception:
        return False
    if result in (None, False):
        return False
    with contextlib.suppress(Exception):
        rename_feature(result, f"{CCW_MIRROR}Drop")
    return True


def _moved_place(place: TreadPlace, index: int, turn: float, lift: float) -> TreadPlace:
    c, sn = math.cos(turn), math.sin(turn)
    x, y, z = place.center
    return TreadPlace(
        index=index, phi=place.phi + turn, y0=place.y0 + lift, y1=place.y1 + lift,
        center=(x * c - z * sn, y + lift, x * sn + z * c),
    )


def _platforms(
    model, layout, places, per_flight: int, platforms: int, top_platform: bool, profiles, shell_od: float, progress,
    shapes: tuple = (),
) -> str:
    """C4 (or C6) frame past the top tread of each flight below a mid platform (and past the
    last one for a top platform), of its shape in ``shapes``, the 6x6 clips where the
    stringers meet it, the shell clips by both ends of its inner channel and every
    radial between, and the knee braces under the outer channel at the same."""
    from swauto.stair.platform_sw import (
        add_platform_knee_braces,
        add_platform_shell_clips,
        add_stringer_clips,
        place_mid_platform,
    )

    frame_profile, clip_profile, knee_profile = profiles
    r_a = layout.inner_face_in
    r_b = r_a + CLEAR_IN  # a platform is always full width, lined up on the inner stringer
    after = []
    missed = []
    frames = []
    for k in range(1, platforms + 1 + (1 if top_platform else 0)):
        last = places[k * per_flight - 1]
        spec = shapes[k - 1] if k - 1 < len(shapes) else None
        frames.append(place_mid_platform(
            model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, profile=frame_profile,
            progress=progress, spec=spec,
        ).note)
        clips = add_stringer_clips(
            model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, profile=clip_profile,
            sides=("A", "B") if k <= platforms else ("A",), stringer_b=r_a + layout.clear_in, progress=progress,
            spec=spec,
        )
        try:
            shell = add_platform_shell_clips(
                model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, shell_r=shell_od,
                progress=progress, spec=spec,
            )
            if "missed" in shell.note:
                missed.append(f"shell clip holes after tread {last.index}")
        except SolidWorksError as exc:
            # The stair is whole without them; say why in the note.
            missed.append(str(exc))
        try:
            knees = add_platform_knee_braces(
                model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_b, shell_r=shell_od,
                profile=knee_profile, progress=progress, spec=spec,
            )
            if "missed" in knees.note:
                missed.append(f"knee brace holes after tread {last.index}")
        except SolidWorksError as exc:
            missed.append(str(exc))
        after.append(str(last.index))
        if "Missed" in clips.note:
            missed.append(clips.note.split("Missed: ", 1)[1].rstrip("."))
    if any(spec.is_rolled or spec.radial_positions() or spec.extra_in or spec.channel != "C4" for spec in shapes):
        note = " ".join(frames) + (
            " L6x6x3/8 clips at every stringer end that meets them, shell clips by both ends of each inner channel "
            "and every held radial, and L3x3x3/8 knee braces to the shell under the outer channel at the same."
        )
    else:
        note = (
            f"C4x5.4 platform frames after tread{'s' if len(after) > 1 else ''} {', '.join(after)}, "
            "with L6x6x3/8 clips at every stringer end that meets them, shell clips at both ends "
            "of each inner channel, and L3x3x3/8 knee braces to the shell under both ends of each outer channel."
        )
    return note + (f" Missed: {'; '.join(missed)}." if missed else "")


@dataclass(frozen=True)
class InnerRail:
    """The inside handrail, Elite STWE: L2x2 posts on the inner stringer's tank face at these treads of each
    flight (``post_sw.flight_picks``), carrying a 1-1/2 in pipe on PC #34s ``top`` over the stringer's top edge,
    the posts' tops cut ``post_sw.TOP_GAP_IN`` under the rail line ``post_top`` over it."""

    posts: tuple = ()
    top: float = 34.0
    post_top: float = 31.6875  # STWE: 3'-2 3/4" posts at Elite's 8-1/2 in rise


def _inner_handrail(
    model, layout, places, per_flight: int, rail: InnerRail, profile: str, platforms: int, top_platform: bool,
    progress, shapes: tuple = (),
) -> str:
    """The inside handrail's posts and pipe; a pipe that will not go is noted, the posts stay."""
    from swauto.stair.grab_sw import GrabRail, add_grab_rails
    from swauto.stair.post_sw import add_handrail_posts, post_layout

    r_a = layout.inner_face_in
    posts = post_layout(places, per_flight, rail.posts, r_a, rail_top=rail.post_top)
    note = add_handrail_posts(model, posts, r_b=r_a, profile=profile, progress=progress, inner=True).note
    try:
        note += " " + add_grab_rails(
            model, places, per_flight, posts, r_a=r_a, r_b=r_a + layout.clear_in, platforms=platforms,
            top_platform=top_platform, grab=GrabRail(top=rail.top), progress=progress, inner=True, shapes=shapes,
        ).note
    except SolidWorksError as exc:
        note += f" Inside handrail pipe stopped: {exc}"
    return note


def _rail_splits(
    model, layout, places, per_flight: int, wanted, posts, inner_rail: InnerRail | None, profile: str, rails: bool,
    grab: GrabRail | None, progress,
) -> str:
    """Each wanted split, (side, pan of the post below its bay), between that post and the next one up its flight.
    One whose posts are not there is noted."""
    from swauto.stair.post_sw import post_layout
    from swauto.stair.rail_split_sw import add_rail_splits

    r_a = layout.inner_face_in
    r_b = r_a + layout.clear_in
    laid = {"outer": post_layout(places, per_flight, posts, r_b) if posts else []}
    if inner_rail is not None:
        laid["inner"] = post_layout(places, per_flight, inner_rail.posts, r_a, rail_top=inner_rail.post_top)
    pairs, lost = [], []
    for side, pan in wanted:
        mine = sorted(laid.get(side, []), key=lambda p: p.index)
        low = next((p for p in mine if p.index == pan), None)
        high = next((p for p in mine if p.index > pan and (p.index - 1) // per_flight == (pan - 1) // per_flight),
                    None)
        if low is None or high is None:
            lost.append(f"{side} at tread {pan}")
            continue
        pairs.append((side, low, high))
    note = add_rail_splits(
        model, places, per_flight, pairs, r_a=r_a, r_b=r_b, profile=profile, rails=rails,
        outer_pipe_top=grab.top if grab is not None else None,
        inner_pipe_top=inner_rail.top if inner_rail is not None else None, progress=progress,
    ).note if pairs else ""
    if lost:
        note += f" No posts either side for the handrail split(s) {', '.join(lost)}."
    return note.strip()


def _handrail_posts(
    model, layout, places, per_flight: int, posts: tuple[int, ...], profile: str, platforms: int,
    top_platform: bool, post_in: float | None, top_rail: bool, mid_rail: bool, mid_top: float | None,
    grab: GrabRail | None, progress, shapes: tuple = (),
) -> str:
    """Handrail posts at the same treads of every flight on the outer stringer, and near
    both ends of each platform's outer channel, ``post_in`` in from the ends. With
    ``top_rail`` and ``mid_rail``, the outer top rail and midrail along them, the
    midrail ``mid_top`` over a platform's grating; with ``grab``, the grab rail on the flight posts."""
    from swauto.stair.grab_sw import add_grab_rails
    from swauto.stair.post_sw import PLATFORM_POST_IN, add_handrail_posts, add_platform_posts, post_layout
    from swauto.stair.rail_sw import PLATFORM_MID_TOP_IN, add_bottom_end, add_mid_rails, add_toe_plates, add_top_rails

    if post_in is None:
        post_in = PLATFORM_POST_IN
    if mid_top is None:
        mid_top = PLATFORM_MID_TOP_IN
    r_a = layout.inner_face_in
    r_b = r_a + layout.clear_in  # the outer stringer
    platform_b = r_a + CLEAR_IN  # a platform is always full width, lined up on the inner stringer
    flight_posts = post_layout(places, per_flight, posts, r_b)
    note = add_handrail_posts(model, flight_posts, r_b=r_b, profile=profile, progress=progress).note
    after = []
    missed = []
    for k in range(1, platforms + 1 + (1 if top_platform else 0)):
        last = places[k * per_flight - 1]
        try:
            placed = add_platform_posts(
                model, last.index, phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=platform_b, profile=profile,
                post_in=post_in, stringer_b=r_b, progress=progress, spec=shapes[k - 1] if k - 1 < len(shapes) else None,
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
    if platforms or top_platform:
        try:
            note += " " + add_toe_plates(
                model, places, per_flight, r_a=r_a, r_b=r_b, platforms=platforms, top_platform=top_platform,
                platform_b=platform_b, progress=progress, shapes=shapes,
            ).note
        except SolidWorksError as exc:
            note += f" Toe plates stopped: {exc}"
    if top_rail:
        try:
            note += " " + add_top_rails(
                model, places, per_flight, r_a=r_a, r_b=r_b, platforms=platforms, top_platform=top_platform,
                profile=profile, post_in=post_in, mid_top=mid_top, platform_b=platform_b, progress=progress,
                shapes=shapes,
            ).note
        except SolidWorksError as exc:
            note += f" Top rail stopped: {exc}"
    if mid_rail:
        try:
            note += " " + add_mid_rails(
                model, places, per_flight, r_a=r_a, r_b=r_b, platforms=platforms, top_platform=top_platform,
                post_in=post_in, mid_top=mid_top, platform_b=platform_b, progress=progress, shapes=shapes,
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
                top_platform=top_platform, post_in=post_in, mid_top=mid_top, grab=grab, platform_b=platform_b,
                progress=progress, shapes=shapes,
            ).note
        except SolidWorksError as exc:
            note += f" Grab rail stopped: {exc}"
    return note


# ---------------------------------------------------------------- stringers


def build_flight_stringers(
    model, stair: StringerMock, shell_od: float, *, at: tuple[float, float] = (0.0, 0.0), suffix: str = "",
    progress=None, foot_holes: bool = True, sides: tuple[str, ...] = ("In", "Out"),
) -> None:
    """Both stringers of one flight of ``stair.treads`` treads (or only the ``sides`` named, "In" and "Out"),
    turned and raised by ``at``.

    Rolls both blanks, rebuilds, then cuts both to the lisp outline before
    any holes: a missed connecting hole must not skip the other stringer or
    the treads. Flat patterns stay suppressed so the stringers show bent
    until Flatten is clicked. Names end in ``suffix`` for flights above the first. Without ``foot_holes`` the
    stringers' feet get no connecting holes: the first flight stands on the ground.
    """
    flight = replace(stair, shell_od_in=shell_od, outside_face=True)
    layout = layout_stringer(flight)
    inner_dev, outer_dev = develop_both(flight)
    tank_face = shell_od + stair.gap_in
    jobs = tuple(job for side, job in (
        ("In", (inner_dev, tank_face, tank_face + THICKNESS_IN, f"EliteStringerIn{suffix}")),
        ("Out", (outer_dev, layout.outside_radius_in - THICKNESS_IN, layout.outside_radius_in,
                 f"EliteStringerOut{suffix}")),
    ) if side in sides)
    for dev, r_in, r_out, nm in jobs:
        _stringer_blank(model, dev, r_in, r_out, nm, at)
        _progress(progress, f"{nm} rolled")
    _rebuild(model)
    for dev, r_in, r_out, nm in jobs:
        _stringer_form(model, layout, dev, r_in, r_out, nm, progress, at)
    _keep_bent_view(model)
    for dev, r_in, r_out, nm in jobs:
        _stringer_holes(model, dev, r_in, r_out, nm, progress, at, foot=foot_holes)


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
    to cap). The thickness goes in from the arcs, so the plate is r_in to r_out
    and its mid-wall is on the trim helices. It is sheet metal from the first
    feature, so the stringer flattens. ``at`` turns and raises a higher flight:
    (angle, inches).

    InsertSheetMetalLoftedBend takes a side flag, then the thickness. Flag 1
    rolls the wall to the other side from flag 0, but which side flag 0 picks
    depends on what is already in the part: in a full build it rolled an upper
    flight's inner blank outside its arcs, where on its own it rolls inside. So
    each roll is read back, and a wall outside its arcs is deleted and rolled
    again with the flags in turn. The blank is found by where it sits: the
    rebuild after it can give other bodies new names.
    """
    radius = dev.radius_in
    p4, _p_start, _p_end, p2, _p3, _l2, _l3, p5 = dev.outline
    _rolled_blank(model, r_in, r_out, at[0] + p4[0] / radius, at[0] + p2[0] / radius, at[1] + p5[1], at[1] + p2[1],
                  name)


def _rolled_blank(
    model, r_in: float, r_out: float, phi_a: float, phi_b: float, y_low: float, y_high: float, name: str
) -> None:
    """A 3/8 in sheet-metal wall rolled between arcs at ``r_out`` from ``phi_a`` to ``phi_b``, ``y_low`` to
    ``y_high``, its thickness in from the arcs to ``r_in``: ``_stringer_blank``'s roll, which the splice plates
    share so they flatten too. The feature and its body are named ``name``."""
    tried = []
    for side in (0, 1, 0, 1):
        before = _names(model)
        before_bodies = _body_names(model)
        low = _arc_sketch(model, y_low, r_out, phi_a, phi_b, f"{name}LowArc")
        high = _arc_sketch(model, y_high, r_out, phi_a, phi_b, f"{name}HighArc")
        _clear_selection(model)
        if not (
            _select_feature(model, low, "SKETCH", mark=1, append=False)
            and _select_feature(model, high, "SKETCH", mark=1, append=True)
        ):
            raise SolidWorksError(f"{name}: could not select the blank arcs.")
        feature = model.FeatureManager.InsertSheetMetalLoftedBend(side, THICKNESS_IN * _INCH)
        outcome = "not made"
        if feature is not None:
            _rebuild(model)
            body = _new_blank(model, before_bodies, phi_a, phi_b, r_out)
            if body is not None and _wall_inside(body, r_out):
                with contextlib.suppress(Exception):
                    rename_feature(feature, name)
                with contextlib.suppress(Exception):
                    body.Name = name
                return
            outcome = "not found" if body is None else "outside"
            _discard_blank(model, feature)
        tried.append(f"flag {side} {outcome}")
        _discard_since(model, before)
        _rebuild(model)
    raise SolidWorksError(
        f"{name}: the rolled blank would not land inside its arcs, {r_in:.3f} to {r_out:.3f} in ({', '.join(tried)})."
    )


def _new_blank(model, before: set[str], phi_a: float, phi_b: float, r_out: float):
    """The one new body centered on the blank's arcs.

    A curved wall's mass center sits in from its radius by sin(a/2) / (a/2) of the arc it spans: half an inch
    on a short flight, inches on a long one. So it is looked for there, on the arcs' bisector.
    """
    mid = (phi_a + phi_b) / 2.0
    half = abs(phi_b - phi_a) / 2.0
    expected = r_out * (math.sin(half) / half if half > 1e-9 else 1.0)
    found = []
    for body in _bodies(model):
        if str(body.Name) in before:
            continue
        try:
            x, _y, z = _mass_point(body)
        except Exception:
            continue
        on_bisector = abs(math.remainder(math.atan2(-x, z) - mid, 2.0 * math.pi)) < 0.02
        if abs(math.hypot(x, z) / _INCH - expected) < 1.0 and on_bisector:
            found.append(body)
    return found[0] if len(found) == 1 else None


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


def _discard_blank(model, feature) -> None:
    """Delete a rejected blank in one go, with its arcs and its own sheet-metal and flat-pattern features.
    One at a time, newest first, SolidWorks would ask about the children."""
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if feature.Select2(False, 0):
            model.Extension.DeleteSelection2(_DELETE_ABSORBED | _DELETE_CHILDREN)
    _clear_selection(model)


def _wall_inside(body, r_out: float) -> bool:
    """No point of the blank stands out past its arcs' radius. Facets only cut inside a curved face, so a wall
    rolled inward peaks exactly on the arcs, and one rolled outward 3/8 in past them."""
    far = None
    raw = body.GetFaces()
    faces = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    for face in faces:
        try:
            tris = list(face.GetTessTriangles(True) or [])
        except Exception:
            continue
        for i in range(0, len(tris) - 2, 3):
            r = math.hypot(tris[i], tris[i + 2]) / _INCH
            far = r if far is None else max(far, r)
    return far is not None and abs(far - r_out) < 0.05


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
            if abs(math.remainder(math.atan2(-cx, cz) - near_phi, 2.0 * math.pi)) > 0.02:  # atan2 wraps at 180°
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
    at: tuple[float, float] = (0.0, 0.0), foot: bool = True,
) -> None:
    """Connecting holes after both stringers are formed, at the foot too with ``foot``. A miss does not abort."""
    before = _names(model)
    try:
        hole_ok = _end_holes(model, dev, r_in, r_out, name, at, foot=foot)
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
    # SolidWorks may take the angle either way round, and an angle past a half turn as its turn the other way.
    turn = math.remainder(phi, 2.0 * math.pi)
    tries: list[float] = []
    for base in (phi, turn, turn + 2.0 * math.pi, turn - 2.0 * math.pi):
        for value in (base, -base):
            if all(abs(value - seen) > 1e-9 for seen in tries):
                tries.append(value)
    for angle in tries:
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
    model, helix_spec, band: tuple[float, float], y_bottom: float, y_top: float, name: str, start_phi: float = 0.0,
    scope=None,
) -> None:
    """Helical cut: a rectangle swept along a trim helix through the plate band.

    The rectangle is on the Right plane for the first flight, or on a radial
    plane at ``start_phi`` where the helix of a higher flight starts. A helix
    sweep is a screw about the tank axis, so a rectangle drawn at a higher
    flight's height is cut at that height all the way along. ``scope()``, when
    given, finds the only bodies to cut (selected with mark 8, auto-select off).
    One rebuild-and-retry only if the cut feature comes back empty.
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
        for method_name, args in (_scoped(methods) if scope is not None else methods):
            method = getattr(model.FeatureManager, method_name, None)
            if method is None:
                continue
            _clear_selection(model)
            if not _select_feature(model, profile, "SKETCH", mark=1, append=False):
                continue
            if not _select_feature(model, helix, "REFERENCECURVES", mark=4, append=True):
                continue
            if scope is not None and not _select_scope(model, scope()):
                errors.append(f"{method_name} attempt={attempt}: no bodies to scope to")
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


def _scoped(methods):
    """The sweep-cut calls with auto-select off, so the cut takes only the bodies selected with mark 8: in both
    InsertCutSwept4 and InsertCutSwept3 the feature scope and auto-select flags come at index 12 and 13."""
    return tuple((name, args[:12] + (True, False) + args[14:]) for name, args in methods)


def _select_scope(model, bodies) -> bool:
    if not bodies:
        return False
    data = model.SelectionManager.CreateSelectData
    data.Mark = 8  # feature scope bodies go in with mark 8
    return all(body.Select2(True, data) for body in bodies)


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
    """Rectangle on the open sketch, in inches, from four lines.

    CreateCornerRectangle snaps a side onto the sketch origin while the view is
    still zoomed out to the whole tank: the inner stringer's top cut, 5 in up,
    was only a few pixels from that axis and landed on it, so the plate came out
    short and the tread bolts passed over it. Lines written straight into the
    sketch are not snapped. The corners are read back, and a snapped rectangle
    is refused.
    """
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = True
    with contextlib.suppress(Exception):
        sketch.DisplayWhenAdded = False
    xm0, ym0, xm1, ym1 = x0 * _INCH, y0 * _INCH, x1 * _INCH, y1 * _INCH
    corners = ((xm0, ym0), (xm1, ym0), (xm1, ym1), (xm0, ym1))
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1], strict=False):
        with contextlib.suppress(Exception):
            sketch.CreateLine(ax, ay, 0.0, bx, by, 0.0)
    if _sketch_segment_count(model) < 4:
        return False
    ys = _open_sketch_ys(model)
    lo, hi = (y0, y1) if y0 <= y1 else (y1, y0)
    return ys is not None and abs(ys[0] - lo) < 0.02 and abs(ys[1] - hi) < 0.02


def _open_sketch_ys(model):
    """The lowest and highest sketch Y of the open sketch, in inches."""
    sketch = com_value(model.GetActiveSketch2)
    if sketch is None:
        return None
    try:
        raw = com_value(sketch.GetSketchSegments)
    except Exception:
        return None
    segments = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    ys = []
    for segment in segments:
        for getter in (segment.GetStartPoint2, segment.GetEndPoint2):
            with contextlib.suppress(Exception):
                ys.append(float(com_value(getter).Y) / _INCH)
    return None if not ys else (min(ys), max(ys))


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
    model, dev: DevelopedStringer, r_in: float, r_out: float, name: str, at: tuple[float, float] = (0.0, 0.0),
    foot: bool = True,
) -> bool:
    """Connecting holes sketched the way tread bolts are, then the jig is deleted.

    A tangent plane landed on the tank axis and never cut the plate. Instead,
    a temporary plate sits against the walk-side face. The holes are sketched
    on that face and cut both ways through the plate and the stringer. Only
    the temporary body is deleted; the cut feature stays in the stringer.
    Inner ends are two 13/16 rounds. Outer ends are two 1-5/8 horizontal slots. Without ``foot``, the top end
    only. A miss does not raise.
    """
    # Walk-side face is the development radius: outer face of the inner
    # stringer, inner face of the outer stringer. The jig sits on the tread side.
    face_r = dev.radius_in
    outward = abs(face_r - r_out) <= abs(face_r - r_in)
    ok = True
    for label, pair in (("Top", dev.end_holes[:2]), ("Bot", dev.end_holes[2:]) if foot else ("Bot", ())):
        if not pair:
            continue
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
    center_r = inner_edge + layout.tread_in / 2.0
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
    outer_edge = inner_edge + layout.tread_in
    half = TREAD_DEPTH_IN / 2.0
    top = _plane(model, "Top")
    base = _offset_from(model, top, place.y0, f"{name}Pln")
    # One unmerged block, hollowed from below: on a small tank the pan's straight outer edge reaches
    # the curved outer stringer at its corners, and a merged lid would fuse the two.
    block_sk = _sketch_on(model, base, f"{name}Sk", lambda: _plan_rect(model, place.phi, inner_edge, outer_edge, half))
    _extrude(model, block_sk, TREAD_MARK_IN, name, merge=False)
    pocket_sk = _sketch_on(
        model,
        base,
        f"{name}PocketSk",
        lambda: _plan_rect(model, place.phi, inner_edge + wall_in, outer_edge - wall_in, half - wall_in),
    )
    # Up to the lid's underside, and as far down into the empty space under the pan.
    pocket = _cut_both_ways(model, pocket_sk, TREAD_MARK_IN - wall_in)
    if pocket is None:
        raise SolidWorksError(f"{name}: the pan was not hollowed.")
    with contextlib.suppress(Exception):
        rename_feature(pocket, f"{name}Pocket")
    body = _tread_body(model, place)
    if body is not None:
        with contextlib.suppress(Exception):
            body.Name = name


def _copy_tread(model, master, source: TreadPlace, place: TreadPlace) -> bool:
    """Copy ``master`` onto ``place``: turned about the tank axis and raised."""
    return _copy_turned(
        model, master, place.phi - source.phi, place.center[1] - source.center[1], f"EliteTread{place.index:02d}",
    )


def _copy_turned(model, master, dphi: float, dy_in: float, name: str) -> bool:
    """Copy ``master``, turned ``dphi`` about the tank axis and raised ``dy_in``.

    A right-hand turn about +Y is the opposite of the stair's angle, as for the shell
    courses. One Move/Copy Body either turns or moves: given both, it turns and drops
    the lift, so the copy is turned, then raised. The copy is found by where its mass
    center lands, since other bodies can take new names on a rebuild, and the original
    has to stay put. Returns False, with nothing left behind, otherwise.
    """
    if abs(dphi) < 1e-9 and abs(dy_in) < 1e-6:
        return False
    try:
        x, y, z = _mass_point(master)
        kept = _box_in(master)
    except Exception:
        return False
    master_name = str(master.Name)
    if not master_name:
        return False
    c, sn = math.cos(dphi), math.sin(dphi)
    turned = (x * c - z * sn, y, z * c + x * sn)
    raised = (turned[0], y + dy_in * _INCH, turned[2])
    nothing = com_nothing()
    _clear_selection(model)
    if not model.Extension.SelectByID2(master_name, "SOLIDBODY", 0.0, 0.0, 0.0, False, 1, nothing, 0):
        return False
    before = _names(model)
    try:
        model.FeatureManager.InsertMoveCopyBody2(
            0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            0.0, -float(dphi), 0.0,
            True, 1,
        )
    except Exception:
        _recover(model)
    _clear_selection(model)
    body = _body_at(model, turned)
    if body is not None and abs(dy_in) > 1e-6:
        if model.Extension.SelectByID2(str(body.Name), "SOLIDBODY", 0.0, 0.0, 0.0, False, 1, nothing, 0):
            try:
                model.FeatureManager.InsertMoveCopyBody2(
                    0.0, dy_in * _INCH, 0.0, 0.0,
                    0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0,
                    False, 1,
                )
            except Exception:
                _recover(model)
        _clear_selection(model)
        body = _body_at(model, raised)
    fresh = [n for n in _names(model) if n not in before]
    if body is None or not _same_box(master, kept):
        if fresh:
            _delete_named(model, tuple(fresh))
            _rebuild(model)
        return False
    labels = iter((f"{name}Copy", f"{name}Lift"))
    for candidate in iter_features(model):
        if _feature_name(candidate) in fresh:
            label = next(labels, None)
            if label is None:
                break
            with contextlib.suppress(Exception):
                rename_feature(candidate, label)
    with contextlib.suppress(Exception):
        body.Name = name
    return True


def _mass_point(body) -> tuple[float, float, float]:
    """Center of mass, meters."""
    props = [float(v) for v in com_value(body.GetMassProperties(1.0))]
    return props[0], props[1], props[2]


def _body_at(model, point_m, tol_in: float = 0.1):
    """The one body whose mass center is at ``point_m`` (meters)."""
    found = []
    point_in = [v / _INCH for v in point_m]
    for body in _bodies(model):
        try:
            box = _box_in(body)
            if not all(box[i] - 1.0 <= point_in[i] <= box[i + 3] + 1.0 for i in range(3)):
                continue
            if math.dist(_mass_point(body), point_m) < tol_in * _INCH:
                found.append(body)
        except Exception:
            continue
    return found[0] if len(found) == 1 else None


def _same_box(body, box) -> bool:
    """The master was copied, not moved."""
    try:
        now = _box_in(body)
    except Exception:
        return False
    return all(abs(now[i] - box[i]) < 0.02 for i in range(6))


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
    edge_r = inner_edge if side == "In" else inner_edge + layout.tread_in
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


def _cut_one_way_in(model, sketch, depth_in: float, body):
    """A blind cut of ``depth_in`` scoped to ``body`` alone, one way from the sketch: away from it first, then the
    other way if that misses. Not both ways at once: on a rolled sheet-metal body a cut both ways leaves faces
    that stop it flattening (SolidWorks 2013), and a normal cut is refused on the jig's face."""
    for flip in (False, True):
        # Argument 2 would cut away everything outside the profile; argument 3 is the direction (nozzle_sw._cut).
        args = (
            True, False, flip, 0, 0, depth_in * _INCH, 0.0,
            False, False, False, False, 0.0, 0.0, False, False, False, False,
            False, True, False, True,
            True, False, 0, 0.0, False,
        )
        _clear_selection(model)
        if not _select_feature(model, sketch, "SKETCH", mark=0, append=False):
            raise SolidWorksError("Could not select the round's sketch.")
        data = model.SelectionManager.CreateSelectData
        data.Mark = 8  # feature scope bodies go in with mark 8
        if not body.Select2(True, data):
            raise SolidWorksError("Could not select the body to cut.")
        try:
            feature = model.FeatureManager.FeatureCut3(*args)
        except Exception:
            feature = None
        if feature not in (None, False):
            return feature
    return None


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
