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
from swauto.stair.brace_sw import BraceResult, _body_points, _progress, _set_turn, _stair_parts
from swauto.stair.development import END_EXT_IN, PLATFORM_CLEAR_IN
from swauto.stair.inner_clip_sw import _angle_between, _hand, _leg_axes, _member
from swauto.stair.stringer import THICKNESS_IN, TREAD_DEPTH_IN, TREAD_MARK_IN
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


@dataclass(frozen=True)
class _Lines:
    """Plan lines of one platform: radial sides A and B, the stringer walk faces, the channel top."""

    phi_a: float
    phi_b: float
    r_a: float
    r_b: float
    top: float

    @property
    def r_in(self) -> float:
        return self.r_a - THICKNESS_IN

    @property
    def r_out(self) -> float:
        return self.r_b + THICKNESS_IN


def platform_lines(*, phi: float, tread_top: float, r_a: float, r_b: float) -> _Lines:
    """A sits on the inner stringer's end, half a tread plus 1/8 in past the tread centerline at ``phi``."""
    phi_a = phi + (TREAD_DEPTH_IN / 2.0 + END_EXT_IN) / r_a
    return _Lines(phi_a, phi_a + PLATFORM_CLEAR_IN / ((r_a + r_b) / 2.0), r_a, r_b, tread_top - GRATING_IN)


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
    r_a, r_b, treads = _stair_parts(model)
    if not 1 <= tread_index <= len(treads):
        raise SolidWorksError(f"This stair has {len(treads)} treads; there is no tread {tread_index}.")
    y_bottom, phi, _r = treads[tread_index - 1]
    return place_mid_platform(
        model, tread_index, phi=phi, tread_top=y_bottom + TREAD_MARK_IN, r_a=r_a, r_b=r_b,
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
    sides: tuple[str, ...] = ("A", "B"), progress=None,
) -> BraceResult:
    """Clips tying the stringer ends to the platform after tread ``tread_index``.

    Side A is the radial channel where the flight below stops, side B the one
    where the flight above starts. ``profile`` is from ``clip_profile``.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b)
    name = f"ElitePlatform{tread_index:02d}"
    hole_y = lines.top - HOLE_DOWN_IN
    sag = CLIP_LEG_IN * CLIP_LEG_IN / (2.0 * r_b) + 0.001
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
        for label, heel_r, inward in (("In", r_a, 1.0), ("Out", r_b - sag, -1.0)):
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


def _faces(body) -> list:
    raw = body.GetFaces()
    return list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])


def _face_at(bodies, point_in, normal):
    """Planar face whose plane goes through ``point_in`` square to ``normal`` and whose box holds the point."""
    point = [v * _INCH for v in point_in]
    tol = 0.01 * _INCH
    for body in bodies:
        for face in _faces(body):
            try:
                surface = com_value(face.GetSurface)
                flag = surface.IsPlane
                if not (flag() if callable(flag) else flag):
                    continue
                params = [float(v) for v in com_value(surface.PlaneParams)]
                box = [float(v) for v in com_value(face.GetBox)]
            except Exception:
                continue
            n, root = params[0:3], params[3:6]
            if abs(sum(n[i] * normal[i] for i in range(3))) < 0.9999:
                continue
            if abs(sum((point[i] - root[i]) * n[i] for i in range(3))) > tol:
                continue
            if all(box[i] - tol <= point[i] <= box[i + 3] + tol for i in range(3)):
                return face
    return None


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
    slots = [_world(line_phi, lines.r_b - g, 0.0, hole_y) for g in CLIP_GAUGES_IN]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in rounds:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")
        for point in slots:
            sx, sy = to_sketch(point)
            ax, ay = to_sketch(_world(line_phi, lines.r_b - 1.0, 0.0, hole_y))
            bx, by = to_sketch(_world(line_phi, lines.r_b, 0.0, hole_y))
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
    ends = [_world(line_phi, heel_r, 0.0, y) for y in (top - CHANNEL_IN, top - CHANNEL_IN + CLIP_TALL_IN)]
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
    placed = _clip_fits(body, line_phi, heel_r, inward, away)
    axes = None if body is None or placed else _leg_axes(body, heel)
    if axes is not None:
        first, second = axes
        target = along if _hand(first, second) * _hand(along, across) > 0 else across
        turn = _angle_between(first, target)
        for rotation in (turn, -turn):
            if _set_turn(model, feature, rotation) and _clip_fits(body_now(), line_phi, heel_r, inward, away):
                placed = True
                break
    if not placed:
        raise SolidWorksError(f"{name}: could not turn the 6x6 clip into the stringer corner.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if path_sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)
    return body_now()


def _clip_fits(body, line_phi: float, heel_r: float, inward: float, away: float, tol: float = 0.03) -> bool:
    if body is None:
        return False
    points = _body_points(body)
    if not points:
        return False
    rs = [inward * (p[0] * _radial(line_phi)[0] + p[2] * _radial(line_phi)[2] - heel_r) for p in points]
    ts = [away * (p[0] * _travel(line_phi)[0] + p[2] * _travel(line_phi)[2]) for p in points]
    return (
        min(rs) > -tol and max(rs) < CLIP_LEG_IN + tol and max(rs) - min(rs) > CLIP_LEG_IN - tol - 0.01
        and min(ts) > -tol and max(ts) < CLIP_LEG_IN + tol and max(ts) - min(ts) > CLIP_LEG_IN - tol - 0.01
    )


def _clip_web_leg_holes(model, lines: _Lines, line_phi: float, hole_y: float, name: str) -> bool:
    """Rounds through both clips' web legs, from the web's back face; they land in the web's holes and slots."""
    points = [_world(line_phi, r, 0.0, hole_y) for g in CLIP_GAUGES_IN for r in (lines.r_a + g, lines.r_b - g)]
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
