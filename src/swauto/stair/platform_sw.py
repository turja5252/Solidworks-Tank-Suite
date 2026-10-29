"""Mid platform frame: C4x5.4 channels mitered at all four corners, on an open stair part.

From Stair Platform Top View.lsp (RADIALPLATFORM, Mid, straight connectors),
SpiralShellPlatform.lsp, and Platform_Sideview.lsp. In plan the outside of the
frame runs on four lines. A and B are radial: A where the stringers stop past
the tread the platform follows, B 36 in further on along the walk centerline.
C and D are straight between them, on the tank face of the inner stringer and
the outside face of the outer stringer, so the frame is as wide as the stair
over its stringers. The channels come from the SolidWorks weldment library,
web on that outline and flanges in. The 1-1/4 in grating that goes on top is
flush with the tread top, so the channels' top is 1-1/4 in below it and their
bottom is level with the bottom of the stringer's end drop.

Each stringer end at a platform is tied to the radial channel by an L6x6x3/8
clip 2-1/2 in tall on the walk side of the stringer: one leg flat on the
stringer, the other flat on the channel web, heel in the corner. Both legs have
two 13/16 holes 2-3/16 and 4-11/16 in from the heel, on the stringer end hole
line 2-3/4 in below the channel top, so the clip is flush with the channel
bottom. The web has 13/16 rounds at the inner stringer and 1-5/8 slots along
the channel at the outer stringer; the clips have rounds only.

Two knee braces carry the outer channel, one at each end of the platform
(Stair Platform Streatchout.lsp, Platform_Sideview.lsp): a 3/8 plate 4 in wide
and 5 in tall hangs under the outer channel 1/4 in in from the platform end,
from 1/4 in to 4-1/4 in in from the outside. The stair's L3x3x3/8 knee brace
bolts to it at its middle, 3-1/2 in below the channel, and runs down at 45 deg
on the platform side of the plate to the same 1/4 x 7 x 4 clip and 6 x 4 pad
on the shell, its bolt 5.766 in out from the shell. Each knee is radial.

The inner channel is tied to the shell at both ends (Stair Platform Top
View.lsp, Platform_Sideview.lsp): a 3/8 x 4 in tab welded square to the web
1/4 in in from the channel end, 3-1/2 in out toward the shell, bolted to a 3/8
shell clip as tall as the channel on the tab's face toward the platform middle.
The shell clip runs from a 1/4 pad on the shell (4 in wide, 6 in tall, 2 in
radius ends) to 3/4 in short of the channel. Two 13/16 holes 2 in apart, one
above the other about the channel's mid-height, 2-1/8 in out from the web.
"""

from __future__ import annotations

import contextlib
import math
import os
from dataclasses import dataclass

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import (
    CLIP_BOLT_OUT_IN,
    BraceResult,
    _body_points,
    _draw_pad,
    _extrude_to,
    _face_at,
    _Frame,
    _Knee,
    _knee_angle,
    _knee_clip_and_pad,
    _knee_holes,
    _progress,
    _set_turn,
    _stair_parts,
)
from swauto.stair.development import END_EXT_IN, PLATFORM_CLEAR_IN
from swauto.stair.inner_clip_sw import _angle_between, _hand, _leg_axes, _member
from swauto.stair.stringer import CLEAR_IN, THICKNESS_IN, TREAD_DEPTH_IN, TREAD_MARK_IN
from swauto.stair.stringer_sw import _create_circle, _names, _rename_new
from swauto.tank.shell import _clear_selection, _close_sketch

_INCH = 0.0254
PROFILE = ("ansi inch", "C Channel", "C4x5.4.SLDLFP")
CLIP_PROFILE = ("ansi inch", "L Angle", "L6x6x0.375.SLDLFP")
CHANNEL_IN = 4.0
WEB_IN = 0.184  # C4x5.4 web
GRATING_IN = 1.25
CLIP_LEG_IN = 6.0
CLIP_THK_IN = 0.375
CLIP_TALL_IN = 2.5
CLIP_GAUGES_IN = (2.1875, 4.6875)  # from the heel on both legs: the stringer end holes' set-back
HOLE_DOWN_IN = 2.75  # below the channel top: the stringer end hole line
HOLE_DIA_IN = 0.8125
SLOT_IN = 1.625
TAB_THK_IN = 0.375
TAB_OUT_IN = 3.5  # from the channel web toward the shell
TAB_FROM_END_IN = 0.25
SHELL_CLIP_THK_IN = 0.375
SHELL_CLIP_SHORT_IN = 0.75  # its end short of the channel web
SHELL_PAD_THK_IN = 0.25
SHELL_PAD_TALL_IN = 6.0
SHELL_BOLT_OUT_IN = 2.125  # from the channel web
SHELL_BOLT_SPACE_IN = 2.0
HANGER_THK_IN = 0.375
HANGER_WIDE_IN = 4.0
HANGER_TALL_IN = 5.0
HANGER_FROM_END_IN = 0.25
HANGER_IN_FROM_OUTSIDE_IN = 0.25
HANGER_BOLT_DOWN_IN = 3.5  # below the channel bottom


@dataclass(frozen=True)
class _Lines:
    """Plan lines of one platform: radial sides A and B, the walk faces of a full-width stair's
    stringers (the frame's inside), the channel top, and the outer stringer's walk face, which is
    further in when the treads are narrower than the platform."""

    phi_a: float
    phi_b: float
    r_a: float
    r_b: float
    top: float
    stringer_b: float

    @property
    def r_in(self) -> float:
        return self.r_a - THICKNESS_IN

    @property
    def r_out(self) -> float:
        return self.r_b + THICKNESS_IN


def platform_lines(*, phi: float, tread_top: float, r_a: float, r_b: float, stringer_b: float | None = None) -> _Lines:
    """A sits on the inner stringer's end, half a tread plus 1/8 in past the tread centerline at ``phi``.

    ``r_b`` is the platform's outer walk face; ``stringer_b`` the outer stringer's, if not the same."""
    phi_a = phi + (TREAD_DEPTH_IN / 2.0 + END_EXT_IN) / r_a
    return _Lines(
        phi_a, phi_a + PLATFORM_CLEAR_IN / ((r_a + r_b) / 2.0), r_a, r_b, tread_top - GRATING_IN,
        r_b if stringer_b is None else stringer_b,
    )


def _library(app, parts) -> str:
    root = str(com_value(app.GetExecutablePath))
    path = os.path.join(root, "lang", "english", "weldment profiles", *parts)
    if not os.path.isfile(path):
        raise SolidWorksError(f"The {parts[-1][:-7]} weldment profile is not at {path}.")
    return path


def platform_profile(app) -> str:
    """The C4x5.4 file in this SolidWorks' weldment library."""
    return _library(app, PROFILE)


def clip_profile(app) -> str:
    """The L6x6x0.375 file in this SolidWorks' weldment library."""
    return _library(app, CLIP_PROFILE)


def _world(phi: float, r: float, t: float, y: float) -> tuple[float, float, float]:
    """Inches: r out along the radial line at ``phi``, t toward the upper treads, y up."""
    c, sn = math.cos(phi), math.sin(phi)
    return (-r * sn - t * c, y, r * c - t * sn)


def add_mid_platform(model, tread_index: int, profile: str, progress=None) -> BraceResult:
    """Platform frame starting where the stringers stop past tread ``tread_index``, read from the part.

    ``profile`` is from ``platform_profile``. The grating top is flush with that tread's top.
    """
    r_a, _r_b, treads = _stair_parts(model)
    if not 1 <= tread_index <= len(treads):
        raise SolidWorksError(f"This stair has {len(treads)} treads; there is no tread {tread_index}.")
    y_bottom, phi, _r = treads[tread_index - 1]
    return place_mid_platform(
        model, tread_index, phi=phi, tread_top=y_bottom + TREAD_MARK_IN, r_a=r_a, r_b=r_a + CLEAR_IN,
        profile=profile, progress=progress,
    )


def place_mid_platform(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, profile: str, progress=None
) -> BraceResult:
    """Platform frame after the tread centered at angle ``phi`` with its top at ``tread_top``.

    ``r_a`` and ``r_b`` are the walk faces of the inner and outer stringers. No
    tread has to be in the part, so a stringers-only stair works.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b)
    r_in, r_out, phi_a, phi_b = lines.r_in, lines.r_out, lines.phi_a, lines.phi_b
    base = lines.top - CHANNEL_IN
    name = f"ElitePlatform{tread_index:02d}"
    outline = [s._plan_xy(r, a) for r, a in ((r_in, phi_a), (r_out, phi_a), (r_out, phi_b), (r_in, phi_b))]
    if _signed_area(outline) < 0:
        outline.reverse()  # counterclockwise in the sketch puts the flanges inside
    _frame(model, outline, base, profile, name)
    _progress(progress, f"{name} frame placed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()
    radial = r_out - r_in
    inner = 2.0 * r_in * math.sin((phi_b - phi_a) / 2.0)
    outer = 2.0 * r_out * math.sin((phi_b - phi_a) / 2.0)
    note = (
        f"Mid platform after tread {tread_index}: C4x5.4 frame mitered at all four corners, "
        f"{PLATFORM_CLEAR_IN:g} in clear along the walk centerline. Outside lengths: two radial sides "
        f"{radial:.3f} in, inner side {inner:.3f} in, outer side {outer:.3f} in. "
        f"Channel tops {GRATING_IN:g} in below the top of tread {tread_index} for the grating."
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _signed_area(points) -> float:
    return 0.5 * sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]))


def _frame(model, outline, base: float, profile: str, name: str) -> None:
    """Closed loop on a level plane at the channels' bottom, then one structural member on all four lines.

    SolidWorks miters the corners of a closed loop and sets each channel with
    its web back on the line, its flanges toward the inside, standing up from
    the sketch plane.
    """
    plane = s._offset_from(model, s._plane(model, "Top"), base, f"{name}Pln")

    def draw():
        manager = model.SketchManager
        with contextlib.suppress(Exception):
            manager.AddToDB = True
        for (ax, ay), (bx, by) in zip(outline, outline[1:] + outline[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: frame line failed.")

    sketch = s._sketch_on(model, plane, f"{name}Sk", draw)
    bodies_before = s._body_names(model)
    s._select_segments(model, sketch, name, 4)
    try:
        feature = model.FeatureManager.InsertStructuralWeldment2(profile, 1, False, 0.0)
    except Exception as exc:
        raise SolidWorksError(f"{name}: structural member failed ({format_com_error(exc)}).") from exc
    if feature is None:
        raise SolidWorksError(f"{name}: structural member was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Frame")
    s._rebuild(model)
    channels = []
    for body in s._bodies(model):
        with contextlib.suppress(Exception):
            if str(body.Name) not in bodies_before:
                channels.append(s._box_in(body))
    if len(channels) != 4 or any(abs(box[4] - box[1] - CHANNEL_IN) > 0.01 for box in channels):
        raise SolidWorksError(f"{name}: expected four 4 in channels, got {len(channels)} bodies.")
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)


# ------------------------------------------------------------- stringer clips


def add_stringer_clips(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, profile: str,
    sides: tuple[str, ...] = ("A", "B"), stringer_b: float | None = None, progress=None,
) -> BraceResult:
    """Clips tying the stringer ends to the platform after tread ``tread_index``.

    Side A is the radial channel where the flight below stops, side B the one
    where the flight above starts. ``profile`` is from ``clip_profile``. The outer
    clip is on the outer stringer, at ``stringer_b`` when the treads are narrower
    than the platform.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b, stringer_b=stringer_b)
    name = f"ElitePlatform{tread_index:02d}"
    hole_y = lines.top - HOLE_DOWN_IN
    sag = CLIP_LEG_IN * CLIP_LEG_IN / (2.0 * lines.stringer_b) + 0.001
    missed = []
    for side in sides:
        line_phi = lines.phi_a if side == "A" else lines.phi_b
        away = -1.0 if side == "A" else 1.0  # along the travel, from the channel to that flight
        tag = f"{name}Clip{side}"
        if not _web_holes(model, lines, line_phi, hole_y, f"{name}Web{side}"):
            missed.append(f"web holes {side}")
        clips = []
        # Inner stringer: walk face convex toward the clip, so the flat leg sits on it at the heel.
        # Outer stringer: walk face concave toward the clip, so the leg is eased in by the sag.
        for label, heel_r, inward in (("In", r_a, 1.0), ("Out", lines.stringer_b - sag, -1.0)):
            body = _clip(model, line_phi, heel_r, inward, away, lines.top, profile, f"{tag}{label}")
            clips.append((body, heel_r, inward))
        _progress(progress, f"{tag} angles placed")
        if not _clip_web_leg_holes(model, lines, line_phi, hole_y, f"{tag}WebLegHoles"):
            missed.append(f"clip web legs {side}")
        for (_body, heel_r, inward), label in zip(clips, ("In", "Out")):
            if not _clip_stringer_leg_holes(model, line_phi, heel_r, inward, away, hole_y, f"{tag}{label}LegHoles"):
                missed.append(f"clip {side} {label.lower()} stringer leg")
        _progress(progress, f"{tag} holes {'missed' if missed else 'cut'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: L6x6x3/8 x {CLIP_TALL_IN:g} in clips on side(s) "
        f"{', '.join(sides)}, two 13/16 holes in each leg at 2-3/16 and 4-11/16 in from the heel. "
        "Channel web: rounds at the inner stringer, 1-5/8 slots at the outer."
        + (f" Missed: {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _sketch_on_face(model, face, name: str, draw):
    """Sketch on ``face``; ``draw(manager, to_sketch)`` with model points in inches."""
    _clear_selection(model)
    if face is None or not s._select_face(model, face):
        raise SolidWorksError(f"{name}: could not select the face to sketch on.")
    before = _names(model)
    manager = model.SketchManager
    with contextlib.suppress(Exception):
        manager.AddToDB = True
    manager.InsertSketch(True)
    try:
        sketch = com_value(model.GetActiveSketch2)
        if sketch is None:
            raise SolidWorksError(f"{name}: no sketch opened on the face.")
        data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]

        def to_sketch(p_in):
            sx, sy, sz = s._to_sketch(data, [v * _INCH for v in p_in])
            if abs(sz) > 0.01 * _INCH:
                raise SolidWorksError(f"{name}: a point is {sz / _INCH:.3f} in off the sketch face.")
            return sx, sy

        draw(manager, to_sketch)
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    return _rename_new(model, before, f"{name}Sk", "hole sketch")


def _cut(model, face, name: str, draw, depth_in: float) -> bool:
    try:
        sketch = _sketch_on_face(model, face, name, draw)
    except SolidWorksError:
        return False
    feature = s._cut_both_ways(model, sketch, depth_in)
    if feature is None:
        s._delete_named(model, (f"{name}Sk",))
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
    return True


def _radial(phi: float) -> tuple[float, float, float]:
    return (-math.sin(phi), 0.0, math.cos(phi))


def _travel(phi: float) -> tuple[float, float, float]:
    return (-math.cos(phi), 0.0, -math.sin(phi))


def _channel_face(model, lines: _Lines, line_phi: float):
    """Back of the radial channel web on this side: the platform outline's radial plane."""
    mid = (lines.r_a + lines.r_b) / 2.0
    frame = [b for b in s._bodies(model) if str(b.Name).startswith("ElitePlatform")]
    return _face_at(frame, _world(line_phi, mid, 0.0, lines.top - CHANNEL_IN / 2.0), _travel(line_phi))


def _web_holes(model, lines: _Lines, line_phi: float, hole_y: float, name: str) -> bool:
    """13/16 rounds at the inner stringer and 1-5/8 slots along the channel at the outer, through the web."""
    rounds = [_world(line_phi, lines.r_a + g, 0.0, hole_y) for g in CLIP_GAUGES_IN]
    slots = [_world(line_phi, lines.stringer_b - g, 0.0, hole_y) for g in CLIP_GAUGES_IN]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in rounds:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")
        for point in slots:
            sx, sy = to_sketch(point)
            ax, ay = to_sketch(_world(line_phi, lines.stringer_b - 1.0, 0.0, hole_y))
            bx, by = to_sketch(_world(line_phi, lines.stringer_b, 0.0, hole_y))
            s._slot_along(model, sx, sy, ax - bx, ay - by, SLOT_IN * _INCH, radius)

    if not _cut(model, _channel_face(model, lines, line_phi), name, draw, WEB_IN + 0.06):
        return False
    return all(_hole_in(model, p) for p in rounds)


def _hole_in(model, point_in) -> bool:
    point = [v * _INCH for v in point_in]
    radius = HOLE_DIA_IN / 2.0 * _INCH
    return any(s._has_hole_axis(body, point, radius, 0.1 * _INCH) is True for body in s._bodies(model))


def _clip(model, line_phi: float, heel_r: float, inward: float, away: float, top: float, profile: str, name: str):
    """L6x6 on a vertical line at the heel, turned until one leg runs along the stringer
    away from the channel and the other along the web toward the walk centerline."""
    ys = (top - CHANNEL_IN, top - CHANNEL_IN + CLIP_TALL_IN)
    return _upright_angle(model, line_phi, heel_r, inward, away, ys, CLIP_LEG_IN, profile, name)


def _upright_angle(
    model, line_phi: float, heel_r: float, inward: float, away: float, ys: tuple[float, float], leg_in: float,
    profile: str, name: str, heel_t: float = 0.0,
):
    """Equal-leg angle on a vertical line at the heel from ``ys[0]`` up to ``ys[1]``, turned
    until one leg runs ``away`` along the travel and the other ``inward`` along the radial.
    The heel is ``heel_t`` along the travel from the radial line at ``line_phi``."""
    ends = [_world(line_phi, heel_r, heel_t, y) for y in ys]
    heel = ends[0]
    along = (away * _travel(line_phi)[0], away * _travel(line_phi)[2])
    across = (inward * _radial(line_phi)[0], inward * _radial(line_phi)[2])
    feature, path_sketch, bodies_before = _member(model, profile, ends[0], ends[1], name)

    def body_now():
        for body in s._bodies(model):
            with contextlib.suppress(Exception):
                if str(body.Name) not in bodies_before:
                    return body
        return None

    body = body_now()
    if body is None:
        s._rebuild(model)
        body = body_now()
    placed = _upright_fits(body, line_phi, heel_r, inward, away, leg_in, heel_t)
    axes = None if body is None or placed else _leg_axes(body, heel)
    if axes is not None:
        first, second = axes
        target = along if _hand(first, second) * _hand(along, across) > 0 else across
        turn = _angle_between(first, target)
        for rotation in (turn, -turn):
            if _set_turn(model, feature, rotation) and _upright_fits(
                body_now(), line_phi, heel_r, inward, away, leg_in, heel_t
            ):
                placed = True
                break
    if not placed:
        raise SolidWorksError(f"{name}: could not turn the angle into place.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if path_sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)
    return body_now()


def _upright_fits(
    body, line_phi: float, heel_r: float, inward: float, away: float, leg_in: float, heel_t: float = 0.0,
    tol: float = 0.03,
) -> bool:
    if body is None:
        return False
    points = _body_points(body)
    if not points:
        return False
    rs = [inward * (p[0] * _radial(line_phi)[0] + p[2] * _radial(line_phi)[2] - heel_r) for p in points]
    ts = [away * (p[0] * _travel(line_phi)[0] + p[2] * _travel(line_phi)[2] - heel_t) for p in points]
    return (
        min(rs) > -tol and max(rs) < leg_in + tol and max(rs) - min(rs) > leg_in - tol - 0.01
        and min(ts) > -tol and max(ts) < leg_in + tol and max(ts) - min(ts) > leg_in - tol - 0.01
    )


def _clip_web_leg_holes(model, lines: _Lines, line_phi: float, hole_y: float, name: str) -> bool:
    """Rounds through both clips' web legs, from the web's back face; they land in the web's holes and slots."""
    points = [_world(line_phi, r, 0.0, hole_y) for g in CLIP_GAUGES_IN for r in (lines.r_a + g, lines.stringer_b - g)]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    if not _cut(model, _channel_face(model, lines, line_phi), name, draw, CLIP_THK_IN + 0.05):
        return False
    return all(_hole_in(model, p) for p in points)


def _clip_stringer_leg_holes(
    model, line_phi: float, heel_r: float, inward: float, away: float, hole_y: float, name: str
) -> bool:
    """Rounds through the clip's stringer leg only, on the stringer's end holes.

    The cut stops in the gap between the flat leg and the curved stringer, so
    the stringer's own holes and slots are left as they are.
    """
    face_r = heel_r + inward * CLIP_THK_IN
    points = [_world(line_phi, face_r, away * g, hole_y) for g in CLIP_GAUGES_IN]
    clips = [b for b in s._bodies(model) if str(b.Name).startswith(name[: name.index("Clip") + 4])]
    face = _face_at(clips, _world(line_phi, face_r, away * 3.0, hole_y), _radial(line_phi))
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    if not _cut(model, face, name, draw, CLIP_THK_IN + 0.001):
        return False
    return all(_hole_in(model, p) for p in points)


# --------------------------------------------------------------- knee braces


def add_platform_knee_braces(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, shell_r: float,
    profile: str, progress=None,
) -> BraceResult:
    """Hanger plate under the outer channel and a 45 deg knee brace to the shell, at both platform ends.

    ``profile`` is the L3x3x0.375 file (``brace_sw.angle_profile``). The part does not need a shell.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b)
    name = f"ElitePlatform{tread_index:02d}Knee"
    missed = []
    for label, frame, knee, back in platform_knees(lines, shell_r):
        tag = f"{name}{label}"
        _hanger(model, frame, back, lines.top, knee.side, f"{tag}Hanger")
        _knee_angle(model, frame, knee, profile, tag)
        _knee_clip_and_pad(model, frame, knee, tag)
        if not _knee_holes(model, frame, knee, tag):
            missed.append(label)
        _progress(progress, f"{tag} placed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: a 3/8 x {HANGER_WIDE_IN:g} x {HANGER_TALL_IN:g} hanger under the "
        "outer channel at each end with an L3x3x3/8 knee brace at 45 deg down to a clip and pad on the shell."
        + (f" Holes missed at end(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def platform_knees(lines: _Lines, shell_r: float) -> list[tuple[str, _Frame, _Knee, float]]:
    """The knee brace at each end of a platform's outer channel: end label, radial frame, knee, and the outer
    channel back's radius on that line. Raises when the shell leaves no room."""
    half = (lines.phi_b - lines.phi_a) / 2.0
    mid = lines.phi_a + half
    outer_chord = lines.r_out * math.cos(half)  # the outer channel's back, from the axis along the bisector
    r_mid_plate = lines.r_out - HANGER_IN_FROM_OUTSIDE_IN - HANGER_WIDE_IN / 2.0
    set_in = HANGER_FROM_END_IN + HANGER_THK_IN
    knees = []
    for label, knee_phi, side in (
        ("A", lines.phi_a + set_in / r_mid_plate, 1.0),
        ("B", lines.phi_b - set_in / r_mid_plate, -1.0),
    ):
        frame = _Frame(phi=knee_phi, y_top=lines.top, r_a=lines.r_a, r_b=lines.r_b)
        back = outer_chord / math.cos(knee_phi - mid)  # outer channel back on this radial line
        r1 = back - HANGER_IN_FROM_OUTSIDE_IN - HANGER_WIDE_IN / 2.0
        y1 = lines.top - CHANNEL_IN - HANGER_BOLT_DOWN_IN
        r2 = shell_r + CLIP_BOLT_OUT_IN
        if r2 >= r1 - 1.0:
            raise SolidWorksError("The platform knee brace has no room between the platform and the shell.")
        knee = _Knee(t_face=0.0, top=(r1, y1), bottom=(r2, y1 - (r1 - r2)), shell_r=shell_r, side=side)
        knees.append((label, frame, knee, back))
    return knees


def shell_pads(lines: _Lines, shell_r: float) -> list[tuple[str, float, float]]:
    """The shell pad at each end of a platform's inner channel: end label, plan angle (taken near the
    platform's own angles) and middle height. Each pad is 4 in wide by SHELL_PAD_TALL_IN, full-radius ends."""
    pads = []
    for end, label in zip(_channel_ends(lines), ("A", "B"), strict=True):
        qx, qz = _pad_point(end, shell_r)
        phi_q = lines.phi_a + math.remainder(math.atan2(-qx, qz) - lines.phi_a, 2.0 * math.pi)
        pads.append((label, phi_q, end.top - CHANNEL_IN / 2.0))
    return pads


def _hanger(model, frame: _Frame, back: float, top: float, side: float, name: str) -> None:
    """3/8 plate under the outer channel, on the platform-end side of the knee's contact plane."""
    r0 = back - HANGER_IN_FROM_OUTSIDE_IN - HANGER_WIDE_IN
    r1 = back - HANGER_IN_FROM_OUTSIDE_IN
    y1 = top - CHANNEL_IN
    y0 = y1 - HANGER_TALL_IN
    plane = s._radial_plane(model, frame.phi, f"{name}Pln")

    def draw(manager, to_sketch):
        pts = [to_sketch(frame.world(r, 0.0, y)) for r, y in ((r0, y0), (r1, y0), (r1, y1), (r0, y1))]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: hanger edge failed.")

    sketch = _sketch_on_face(model, plane, name, draw)
    _extrude_to(
        model, sketch, HANGER_THK_IN, frame.world((r0 + r1) / 2.0, -side * HANGER_THK_IN / 2.0, (y0 + y1) / 2.0),
        HANGER_TALL_IN + 0.1, name,
    )


# --------------------------------------------------------------- shell clips


@dataclass(frozen=True)
class _ChannelEnd:
    """One end of the inner channel's back line C, in plan inches."""

    origin: tuple[float, float]  # the corner, (x, z)
    along: tuple[float, float]  # along C toward the other end
    inward: tuple[float, float]  # square to C, toward the tank axis
    top: float

    def world(self, c: float, h: float, y: float) -> tuple[float, float, float]:
        """c along the channel from this end, h out from the web toward the shell."""
        return (
            self.origin[0] + c * self.along[0] + h * self.inward[0],
            y,
            self.origin[1] + c * self.along[1] + h * self.inward[1],
        )


def _channel_ends(lines: _Lines) -> list[_ChannelEnd]:
    a = (-lines.r_in * math.sin(lines.phi_a), lines.r_in * math.cos(lines.phi_a))
    b = (-lines.r_in * math.sin(lines.phi_b), lines.r_in * math.cos(lines.phi_b))
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    along = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    inward = (-along[1], along[0])
    if inward[0] * -a[0] + inward[1] * -a[1] < 0:
        inward = (-inward[0], -inward[1])
    return [
        _ChannelEnd(a, along, inward, lines.top),
        _ChannelEnd(b, (-along[0], -along[1]), inward, lines.top),
    ]


def add_platform_shell_clips(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, shell_r: float, progress=None,
) -> BraceResult:
    """Tab, shell clip, and pad at both ends of the inner channel of the platform after tread ``tread_index``.

    ``shell_r`` is the shell OD radius; the part does not need a shell.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b)
    if lines.r_in - shell_r < TAB_OUT_IN + SHELL_PAD_THK_IN + 0.5:
        raise SolidWorksError(f"The {lines.r_in - shell_r:.2f} in gap leaves no room for the platform's shell clips.")
    name = f"ElitePlatform{tread_index:02d}Shell"
    missed = []
    for end, label in zip(_channel_ends(lines), ("A", "B")):
        tag = f"{name}{label}"
        _shell_tab(model, end, f"{tag}Tab")
        _shell_clip_and_pad(model, end, shell_r, tag)
        if not _shell_holes(model, end, f"{tag}Holes"):
            missed.append(label)
        _progress(progress, f"{tag} clip placed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: 3/8 x 4 in tabs welded to the inner channel at both ends, "
        f"bolted to 3/8 shell clips on 1/4 x 4 x 6 pads, two 13/16 holes 2 in apart."
        + (f" Holes missed at end(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _shell_tab(model, end: _ChannelEnd, name: str) -> None:
    """3/8 tab welded square to the web back, 1/4 in in from the channel end, out toward the shell."""
    c0, c1 = TAB_FROM_END_IN, TAB_FROM_END_IN + TAB_THK_IN
    y0, y1 = end.top - CHANNEL_IN, end.top
    frame = [b for b in s._bodies(model) if str(b.Name).startswith("ElitePlatform")]
    web = _face_at(frame, end.world((c0 + c1) / 2.0, 0.0, end.top - CHANNEL_IN / 2.0), (end.inward[0], 0.0, end.inward[1]))

    def draw(manager, to_sketch):
        pts = [to_sketch(end.world(c, 0.0, y)) for c, y in ((c0, y0), (c1, y0), (c1, y1), (c0, y1))]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: tab edge failed.")

    sketch = _sketch_on_face(model, web, name, draw)
    _extrude_to(
        model, sketch, TAB_OUT_IN, end.world((c0 + c1) / 2.0, TAB_OUT_IN / 2.0, end.top - CHANNEL_IN / 2.0),
        CHANNEL_IN + 0.1, name,
    )


def _pad_point(end: _ChannelEnd, shell_r: float) -> tuple[float, float]:
    """Where the tab's face toward the platform middle, carried out to the shell, meets the shell OD."""
    c = TAB_FROM_END_IN + TAB_THK_IN
    px, pz = end.world(c, 0.0, 0.0)[0], end.world(c, 0.0, 0.0)[2]
    b = px * end.inward[0] + pz * end.inward[1]
    k = px * px + pz * pz - shell_r * shell_r
    s_near = -b - math.sqrt(b * b - k)
    return px + s_near * end.inward[0], pz + s_near * end.inward[1]


def _shell_clip_and_pad(model, end: _ChannelEnd, shell_r: float, tag: str) -> None:
    """Shell clip on the tab's face toward the platform middle, then the pad flat on the shell behind it."""
    c_face = TAB_FROM_END_IN + TAB_THK_IN
    qx, qz = _pad_point(end, shell_r)
    phi_q = math.atan2(-qx, qz)
    normal = (-math.sin(phi_q), math.cos(phi_q))
    # Out along the tab's line from the web to the pad's outside face.
    px, pz = end.world(c_face, 0.0, 0.0)[0], end.world(c_face, 0.0, 0.0)[2]
    face_x, face_z = qx + SHELL_PAD_THK_IN * normal[0], qz + SHELL_PAD_THK_IN * normal[1]
    reach = ((face_x - px) * normal[0] + (face_z - pz) * normal[1]) / (end.inward[0] * normal[0] + end.inward[1] * normal[1])
    h0, h1 = SHELL_CLIP_SHORT_IN, reach
    y0, y1 = end.top - CHANNEL_IN, end.top
    tabs = [b for b in s._bodies(model) if str(b.Name).startswith(f"{tag}Tab")]
    tab_face = _face_at(tabs, end.world(c_face, TAB_OUT_IN / 2.0, end.top - CHANNEL_IN / 2.0), (end.along[0], 0.0, end.along[1]))

    def draw_clip(manager, to_sketch):
        pts = [to_sketch(end.world(c_face, h, y)) for h, y in ((h0, y0), (h1, y0), (h1, y1), (h0, y1))]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{tag}: shell clip edge failed.")

    clip_sketch = _sketch_on_face(model, tab_face, f"{tag}ShellClip", draw_clip)
    _extrude_to(
        model, clip_sketch, SHELL_CLIP_THK_IN,
        end.world(c_face + SHELL_CLIP_THK_IN / 2.0, (h0 + h1) / 2.0, end.top - CHANNEL_IN / 2.0),
        CHANNEL_IN + 0.1, f"{tag}ShellClip",
    )

    # The pad sits flat on the shell where the tab's line meets it, centered on that line.
    plane = _tangent_plane(model, phi_q, shell_r, f"{tag}Pad")
    y_mid = end.top - CHANNEL_IN / 2.0

    def draw_pad(manager, to_sketch):
        _draw_pad(manager, lambda t, y: to_sketch(_world(phi_q, shell_r, t, y)), 0.0, y_mid, SHELL_PAD_TALL_IN, tag)

    pad_sketch = _sketch_on_face(model, plane, f"{tag}Pad", draw_pad)
    _extrude_to(
        model, pad_sketch, SHELL_PAD_THK_IN, _world(phi_q, shell_r + SHELL_PAD_THK_IN / 2.0, 0.0, y_mid),
        SHELL_PAD_TALL_IN + 0.1, f"{tag}Pad",
    )


def _tangent_plane(model, phi: float, radius: float, name: str):
    """Plane touching the cylinder of ``radius`` at angle ``phi``: the radial plane a quarter turn on,
    moved out ``radius``. The offset side is read back and flipped if SolidWorks went the other way."""
    axis_plane = s._radial_plane(model, phi + math.pi / 2.0, f"{name}AxisPln")
    out = (-math.sin(phi), math.cos(phi))
    for distance in (radius, -radius):
        plane = s._offset_from(model, axis_plane, distance, f"{name}Pln")
        rows = [float(v) for v in com_value(com_value(com_value(plane.GetSpecificFeature2).Transform).ArrayData)]
        if abs((rows[9] * out[0] + rows[11] * out[1]) / _INCH - radius) < 0.01:
            return plane
        s._delete_named(model, (s._feature_name(plane),))
    raise SolidWorksError(f"{name}: the pad plane did not land on the shell.")


def _shell_holes(model, end: _ChannelEnd, name: str) -> bool:
    """Two 13/16 rounds through the tab and the shell clip, from the face they share."""
    c_face = TAB_FROM_END_IN + TAB_THK_IN
    y_mid = end.top - CHANNEL_IN / 2.0
    points = [end.world(c_face, SHELL_BOLT_OUT_IN, y_mid + dy) for dy in (SHELL_BOLT_SPACE_IN / 2.0, -SHELL_BOLT_SPACE_IN / 2.0)]
    tabs = [b for b in s._bodies(model) if str(b.Name).startswith(name.replace("Holes", "Tab"))]
    face = _face_at(tabs, end.world(c_face, TAB_OUT_IN - 0.25, y_mid), (end.along[0], 0.0, end.along[1]))
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    if not _cut(model, face, name, draw, TAB_THK_IN + SHELL_CLIP_THK_IN + 0.05):
        return False
    return all(_hole_in(model, p) for p in points)
