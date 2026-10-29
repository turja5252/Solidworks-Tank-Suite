"""Cross brace under one tread, added to an open stair part.

An L3x3x3/8 weldment member from the SolidWorks library runs between the two
stringer walk faces under the tread: flat leg on top, 1/2 in below the tread
bottom, the other leg hanging down on the side toward the upper treads. A
2-5/8 x 2-5/8 x 3/8 cap sits inside the L at each end, flush with the angle
end, its inner corner clipped clear of the angle's root fillet. A 13/16 hole
on the tread centerline goes through each cap and its stringer, cut both ways
like the tread bolts. The down leg has a 13/16 hole 3 in in from the outer
end, 1-11/16 below the top (level with the cap holes).

The knee brace is the same angle, bolted through that leg hole and running
down at 45 deg toward the tank, in the plane just outside the down leg, with
its other leg along the top edge. Its ends are cut square 1-1/2 in past each
bolt. It lands on a 1/4 x 7 x 4 clip in line with the down leg, the clip on a
1/4 shell pad 6 in tall x 4 in wide with 2 in radius ends. The clip bolt is
5.766 in out from the shell OD (Tread Sideview.lsp). When the stair is low the
landing is below the shell; the shell is taken to run straight down at its
radius, and a construction line shows that extension.

Geometry is read from the part (stringer radii, tread positions), so the
brace can go on any stair the app built. Y up, tank axis at X = Z = 0, a
point at angle a is (-R sin a, y, R cos a).
"""

from __future__ import annotations

import contextlib
import math
import os
from dataclasses import dataclass

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.parts import extrude_blind
from swauto.stair import stair_sw as s
from swauto.stair.stringer import THICKNESS_IN, TREAD_MARK_IN
from swauto.stair.stringer_sw import _create_circle, _names, _rename_new
from swauto.tank.shell import _clear_selection, _close_sketch

_INCH = 0.0254
PROFILE = ("ansi inch", "L Angle", "L3x3x0.375.SLDLFP")
LEG_IN = 3.0
LEG_THK_IN = 0.375
DROP_IN = 0.5  # tread bottom to the top of the angle
CAP_IN = LEG_IN - LEG_THK_IN  # fills the inside of the L
CAP_THK_IN = 0.375
CAP_CLIP_IN = 0.375  # clears the angle's root fillet
HOLE_DIA_IN = 0.8125  # 13/16
LEG_SIDE = 1.0  # down leg toward the upper treads (+1) or the lower treads (-1)
LEG_HOLE_FROM_END_IN = 3.0  # from the end at the outer stringer
LEG_HOLE_DOWN_IN = LEG_THK_IN + CAP_IN / 2.0  # below the top of the angle
LEG_HOLE_DIA_IN = 0.8125
JIG_THK_IN = 0.5
JIG_HALF_IN = 1.0
JIG_HEIGHT_IN = 1.8
KNEE_END_IN = 1.5  # square cut past each knee bolt
KNEE_HOLE_DIA_IN = 0.8125
CLIP_THK_IN = 0.25
CLIP_OUT_IN = 7.0  # from the pad face
CLIP_HEIGHT_IN = 4.0
CLIP_BOLT_OUT_IN = 5.7657  # clip bolt from the shell OD
PAD_THK_IN = 0.25
PAD_TALL_IN = 6.0
PAD_WIDE_IN = 4.0  # ends are full 2 in radii


@dataclass(frozen=True)
class BraceResult:
    title: str
    note: str


@dataclass(frozen=True)
class _Frame:
    phi: float
    y_top: float
    r_a: float  # walk face of the inner stringer
    r_b: float  # walk face of the outer stringer

    @property
    def radial(self) -> tuple[float, float, float]:
        return (-math.sin(self.phi), 0.0, math.cos(self.phi))

    @property
    def travel(self) -> tuple[float, float, float]:
        """Toward the upper treads."""
        return (-math.cos(self.phi), 0.0, -math.sin(self.phi))

    def world(self, r: float, t: float, y: float) -> tuple[float, float, float]:
        """Inches: r along the tread centerline, t toward the upper treads, y up."""
        u, v = self.radial, self.travel
        return (r * u[0] + t * v[0], y, r * u[2] + t * v[2])


def add_cross_brace(model, tread_index: int, profile: str, progress=None) -> BraceResult:
    """Brace under tread ``tread_index`` (1 is the lowest). ``profile`` is from ``angle_profile``."""
    frame = _frame(model, tread_index)
    name = f"EliteBrace{tread_index:02d}"
    _angle(model, frame, profile, name)
    _progress(progress, f"{name} angle placed")
    holes = 0
    for side, face_r, inward in (("In", frame.r_a, 1.0), ("Out", frame.r_b, -1.0)):
        if _cap_with_hole(model, frame, face_r, inward, f"{name}Cap{side}"):
            holes += 1
        _progress(progress, f"{name} {side.lower()} cap placed")
    leg_ok = _leg_hole(model, frame, f"{name}LegHole")
    _progress(progress, f"{name} leg hole {'cut' if leg_ok else 'missed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()
    note = (
        f"L3x3x3/8 brace under tread {tread_index}, {frame.r_b - frame.r_a:.3f} in long, "
        f"top {DROP_IN:g} in below the tread. Caps {CAP_IN:g} x {CAP_IN:g} x {CAP_THK_IN:g} in. "
        f"13/16 holes through cap and stringer at {holes} of 2 ends. "
        f"Leg hole {'cut' if leg_ok else 'missed'}."
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def remove_cross_brace(model, tread_index: int) -> int:
    """Delete the brace under this tread and everything it added. Returns the count."""
    prefix = f"EliteBrace{tread_index:02d}"
    doomed = []
    inside = False
    for feature in s.iter_features(model):
        name = s._feature_name(feature)
        if name.startswith(prefix):
            inside = True
            doomed.append(name)
        elif name.startswith("EliteBrace"):
            inside = False  # another tread's brace
        elif inside and name.startswith("Body-Delete"):
            doomed.append(name)
    for name in reversed(doomed):
        with contextlib.suppress(Exception):
            s._delete_named(model, (name,))
    s._rebuild(model)
    return len(doomed)


def _progress(callback, text: str) -> None:
    if callback is not None:
        callback(text)


def angle_profile(app) -> str:
    """The L3x3x0.375 file in this SolidWorks' weldment library."""
    root = str(com_value(app.GetExecutablePath))
    path = os.path.join(root, "lang", "english", "weldment profiles", *PROFILE)
    if not os.path.isfile(path):
        raise SolidWorksError(f"The L3x3x0.375 weldment profile is not at {path}.")
    return path


def stair_tread_count(model) -> int:
    """How many treads the stair in this part has."""
    return len(_stair_parts(model)[2])


def stair_flight_tops(model) -> tuple[int, set[int]]:
    """Tread count, and the treads that end a flight: the top one, and each one
    level with the next (the tread on the far side of a mid platform)."""
    treads = _stair_parts(model)[2]
    return len(treads), flight_tops([y for y, _phi, _r in treads])


def flight_tops(bottoms: list[float]) -> set[int]:
    """1-based treads, lowest first by bottom height, with no stringer above them."""
    count = len(bottoms)
    return {i for i in range(1, count + 1) if i == count or abs(bottoms[i] - bottoms[i - 1]) < 0.01}


def _frame(model, tread_index: int) -> _Frame:
    """Tread centerline angle and bottom, and the two stringer walk faces, read from the part."""
    r_a, r_b, treads = _stair_parts(model)
    if not 1 <= tread_index <= len(treads):
        raise SolidWorksError(f"This stair has {len(treads)} treads; there is no tread {tread_index}.")
    y_bottom, phi, _r = treads[tread_index - 1]
    return _Frame(phi=phi, y_top=y_bottom - DROP_IN, r_a=r_a, r_b=r_b)


def _stair_parts(model) -> tuple[float, float, list[tuple[float, float, float]]]:
    """Walk faces of the two stringers and the treads (bottom, angle, radius), lowest first."""
    plates: list[tuple[float, float]] = []
    treads: list[tuple[float, float, float]] = []
    for body in s._bodies(model):
        try:
            box = s._box_in(body)
        except Exception:
            continue
        height = box[4] - box[1]
        # Treads are exactly the tread height; an angle (3 in) or a cap (2-5/8) is not.
        if abs(height - TREAD_MARK_IN) < 0.06:
            cx, cz = (box[0] + box[3]) / 2.0, (box[2] + box[5]) / 2.0
            treads.append((box[1], math.atan2(-cx, cz), math.hypot(cx, cz)))
            continue
        if height < 12.0:
            continue
        radii = sorted(_cylinder_radii(body))
        if len(radii) == 2 and abs(radii[1] - radii[0] - THICKNESS_IN) < 0.01:
            plates.append((radii[0], radii[1]))
    if len(plates) < 2:
        raise SolidWorksError("Could not find both stringers in this part.")
    plates.sort()
    r_a = plates[0][1]
    r_b = plates[-1][0]
    middle = (r_a + r_b) / 2.0
    return r_a, r_b, sorted(t for t in treads if abs(t[2] - middle) < 3.0)


def _cylinder_radii(body) -> set[float]:
    radii: set[float] = set()
    raw = body.GetFaces()
    faces = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    for face in faces:
        try:
            surface = com_value(face.GetSurface)
            is_cyl = surface.IsCylinder
            if not (is_cyl() if callable(is_cyl) else is_cyl):
                continue
            values = [float(v) for v in com_value(surface.CylinderParams)]
        except Exception:
            continue
        if values[6] / _INCH > 50.0:
            radii.add(round(values[6] / _INCH, 4))
    return radii


def _angle(model, frame: _Frame, profile: str, name: str) -> None:
    """The member's line runs along the heel, on the down-leg side of the tread
    centerline. The library L comes in upright; it is turned until the flat leg
    is on top and the down leg hangs at the heel, checked against the model."""
    t_heel = LEG_SIDE * (LEG_THK_IN + CAP_IN / 2.0)
    a = [v * _INCH for v in frame.world(frame.r_a, t_heel, frame.y_top)]
    b = [v * _INCH for v in frame.world(frame.r_b, t_heel, frame.y_top)]
    sketch = model.SketchManager
    before = _names(model)
    with contextlib.suppress(Exception):
        sketch.AddToDB = True
    sketch.Insert3DSketch(True)
    line = sketch.CreateLine(a[0], a[1], a[2], b[0], b[1], b[2])
    sketch.Insert3DSketch(True)
    if line is None:
        raise SolidWorksError(f"{name}: brace line was not drawn.")
    path_sketch = _rename_new(model, before, f"{name}Path", "brace path")
    s._select_segments(model, path_sketch, name, 1)
    try:
        feature = model.FeatureManager.InsertStructuralWeldment2(profile, 1, False, 0.0)
    except Exception as exc:
        raise SolidWorksError(f"{name}: structural member failed ({format_com_error(exc)}).") from exc
    if feature is None:
        raise SolidWorksError(f"{name}: structural member was not made.")
    # Box center of the finished L: halfway down, 3/16 in off the centerline toward the heel.
    want = frame.world((frame.r_a + frame.r_b) / 2.0, LEG_SIDE * 0.1875, frame.y_top - LEG_IN / 2.0)
    turns = (math.pi,) if LEG_SIDE < 0 else (math.pi / 2.0, 3.0 * math.pi / 2.0)
    placed = False
    for turn in turns:
        data = com_value(feature.GetDefinition)
        data.AccessSelections(model, com_nothing())
        data.RotationAngle = turn
        if not feature.ModifyDefinition(data, model, com_nothing()):
            continue
        s._rebuild(model)
        if s._body_near(model, want, max_height=LEG_IN + 0.2, max_dist=0.3) is not None:
            placed = True
            break
    if not placed:
        raise SolidWorksError(f"{name}: could not turn the angle flat leg up.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if path_sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)


def _cap_with_hole(model, frame: _Frame, face_r: float, inward: float, name: str) -> bool:
    """Cap nested in the L at one end, then the 13/16 hole through cap and stringer.

    ``inward`` is +1 at the inner stringer and -1 at the outer one: the direction
    from the stringer face into the angle. A temporary block inside the L gives a
    flat face square to the brace to sketch on; it is deleted at the end.
    """
    cap_back = face_r + inward * CAP_THK_IN
    jig_far = cap_back + inward * JIG_THK_IN
    r0, r1 = sorted((cap_back, jig_far))
    y_center = frame.y_top - LEG_THK_IN - CAP_IN / 2.0
    jig_center = frame.world((r0 + r1) / 2.0, 0.0, y_center)
    top = s._plane(model, "Top")
    base = s._offset_from(model, top, y_center - JIG_HEIGHT_IN / 2.0, f"{name}JigPln")
    jig_sketch = s._sketch_on(
        model, base, f"{name}JigSk",
        lambda: s._plan_rect(model, frame.phi, r0, r1, JIG_HALF_IN),
    )
    s._extrude(model, jig_sketch, JIG_HEIGHT_IN, f"{name}Jig", merge=False)
    s._rebuild(model)
    try:
        _cap(model, frame, face_r, cap_back, jig_center, name)
        return _hole(model, frame, face_r, cap_back, jig_center, y_center, name)
    finally:
        before = _names(model)
        s._delete_bodies_near(model, jig_center, max_height=JIG_HEIGHT_IN + 0.1, max_dist=0.6)
        s._rebuild(model)
        for index, gone in enumerate(sorted(_names(model) - before)):
            with contextlib.suppress(Exception):
                rename_feature(s.find_feature(model, gone), f"{name}JigGone{index or ''}")


def _sketch_on_jig(model, jig_center, cap_back: float, name: str, draw) -> object:
    jig = s._body_near(model, jig_center, max_height=JIG_HEIGHT_IN + 0.1, max_dist=0.6)
    if jig is None:
        raise SolidWorksError(f"{name}: temporary block not found.")
    face = s._face_at_radius(jig, cap_back)
    _clear_selection(model)
    if face is None or not s._select_face(model, face):
        raise SolidWorksError(f"{name}: could not select the temporary block face.")
    before = _names(model)
    manager = model.SketchManager
    with contextlib.suppress(Exception):
        manager.AddToDB = True
    with contextlib.suppress(Exception):
        manager.DisplayWhenAdded = False
    manager.InsertSketch(True)
    try:
        sketch_obj = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch_obj.ModelToSketchTransform).ArrayData)]
        draw(manager, data)
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    return _rename_new(model, before, f"{name}Sk", "cap sketch")


def _cap(model, frame: _Frame, face_r: float, cap_back: float, jig_center, name: str) -> None:
    half = CAP_IN / 2.0
    top = frame.y_top - LEG_THK_IN
    bottom = top - CAP_IN
    # The clipped corner is the one tucked into the L, next to the down leg.
    k = LEG_SIDE
    corners = (
        (-k * half, top),
        (k * (half - CAP_CLIP_IN), top),
        (k * half, top - CAP_CLIP_IN),
        (k * half, bottom),
        (-k * half, bottom),
    )

    def draw(manager, data):
        points = []
        for t, y in corners:
            sx, sy, sz = s._to_sketch(data, [v * _INCH for v in frame.world(cap_back, t, y)])
            if abs(sz) > 0.01 * _INCH:
                raise SolidWorksError(f"{name}: cap corner is {sz / _INCH:.3f} in off the sketch face.")
            points.append((sx, sy))
        for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: cap edge failed.")

    sketch = _sketch_on_jig(model, jig_center, cap_back, name, draw)
    cap_center = frame.world((face_r + cap_back) / 2.0, 0.0, (top + bottom) / 2.0)
    for reverse in (False, True):
        _clear_selection(model)
        if not s._select_feature(model, sketch, "SKETCH", mark=0, append=False):
            raise SolidWorksError(f"{name}: could not select the cap sketch.")
        feature = extrude_blind(model.FeatureManager, CAP_THK_IN * _INCH, merge=False, reverse=reverse)
        s._rebuild(model)
        body = s._body_near(model, cap_center, max_height=CAP_IN + 0.1, max_dist=0.1)
        if body is not None:
            with contextlib.suppress(Exception):
                rename_feature(feature, name)
            return
        with contextlib.suppress(Exception):
            s._delete_named(model, (s._feature_name(feature),))
    raise SolidWorksError(f"{name}: the cap did not land inside the angle.")


def _hole(model, frame: _Frame, face_r: float, cap_back: float, jig_center, y_center: float, name: str) -> bool:
    point = frame.world(cap_back, 0.0, y_center)

    def draw(manager, data):
        sx, sy, _sz = s._to_sketch(data, [v * _INCH for v in point])
        if _create_circle(manager, sx, sy, HOLE_DIA_IN / 2.0 * _INCH) is None:
            raise SolidWorksError(f"{name}: hole circle failed.")

    sketch = _sketch_on_jig(model, jig_center, cap_back, f"{name}Hole", draw)
    reach = CAP_THK_IN + THICKNESS_IN + JIG_THK_IN + 0.35
    feature = s._cut_both_ways(model, sketch, reach)
    if feature is None:
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Hole")
    s._rebuild(model)
    on_face = frame.world(face_r, 0.0, y_center)
    hit = s._stringer_has_hole(model, face_r, on_face, HOLE_DIA_IN / 2.0, 0.12 * _INCH)
    return hit is not False


def _leg_hole(model, frame: _Frame, name: str) -> bool:
    """13/16 hole through the down leg: 3 in in from the outer end, 1-11/16 below the top.

    This is the knee brace's top bolt. Sketched on the leg's outside face and
    cut both ways through the 3/8 leg only.
    """
    point = frame.world(
        frame.r_b - LEG_HOLE_FROM_END_IN,
        LEG_SIDE * (LEG_THK_IN + CAP_IN / 2.0),
        frame.y_top - LEG_HOLE_DOWN_IN,
    )
    point_m = [v * _INCH for v in point]
    _clear_selection(model)
    if not model.Extension.SelectByID2("", "FACE", point_m[0], point_m[1], point_m[2], False, 0, com_nothing(), 0):
        return False
    before = _names(model)
    manager = model.SketchManager
    with contextlib.suppress(Exception):
        manager.AddToDB = True
    with contextlib.suppress(Exception):
        manager.DisplayWhenAdded = False
    manager.InsertSketch(True)
    try:
        sketch_obj = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch_obj.ModelToSketchTransform).ArrayData)]
        sx, sy, sz = s._to_sketch(data, point_m)
        if abs(sz) > 0.01 * _INCH:
            raise SolidWorksError(f"{name}: leg hole is {sz / _INCH:.3f} in off the leg face.")
        if _create_circle(manager, sx, sy, LEG_HOLE_DIA_IN / 2.0 * _INCH) is None:
            raise SolidWorksError(f"{name}: leg hole circle failed.")
    except Exception:
        s._recover(model)
        s._discard_since(model, before)
        return False
    _close_sketch(model)
    sketch = _rename_new(model, before, f"{name}Sk", "leg hole sketch")
    feature = s._cut_both_ways(model, sketch, LEG_THK_IN + 0.25)
    if feature is None:
        s._delete_named(model, (f"{name}Sk",))
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
    for body in s._bodies(model):
        if s._has_hole_axis(body, point_m, LEG_HOLE_DIA_IN / 2.0 * _INCH, 0.1 * _INCH) is True:
            return True
    return False


# ------------------------------------------------------------------ knee brace

_ROOT2 = math.sqrt(2.0)


@dataclass(frozen=True)
class _Knee:
    t_face: float  # contact plane: outside face of the cross brace down leg
    top: tuple[float, float]  # (r, y) of the top bolt, the cross brace leg hole
    bottom: tuple[float, float]  # (r, y) of the clip bolt
    shell_r: float  # shell OD radius
    side: float = LEG_SIDE  # +1: the knee sits on the +t side of the contact plane, -1: the -t side


def add_knee_brace(model, tread_index: int, profile: str, shell_radius_in: float | None = None, progress=None) -> BraceResult:
    """45 deg knee brace from this tread's cross brace leg hole down to a clip on the shell.

    The shell OD radius is read from the shell plates in the part; ``shell_radius_in``
    is used when the part has no shell.
    """
    frame = _frame(model, tread_index)
    shell_r, shell_bottom = _shell(model, frame)
    if shell_r is None:
        if shell_radius_in is None:
            raise SolidWorksError("This part has no tank shell; the knee brace needs the shell radius.")
        shell_r = shell_radius_in
    knee = _knee_layout(frame, shell_r)
    name = f"EliteBrace{tread_index:02d}Knee"
    _knee_angle(model, frame, knee, profile, name)
    _progress(progress, f"{name} angle placed")
    _knee_clip_and_pad(model, frame, knee, name)
    _progress(progress, f"{name} clip placed")
    holes_ok = _knee_holes(model, frame, knee, name)
    _progress(progress, f"{name} holes {'cut' if holes_ok else 'missed'}")
    pad_top = knee.bottom[1] + PAD_TALL_IN / 2.0
    below = ""
    if shell_bottom is not None and pad_top < shell_bottom:
        _shell_line(model, frame, knee, pad_top, shell_bottom, f"{name}ShellLine")
        below = (
            f" The clip lands {shell_bottom - pad_top:.1f} in below the shell; "
            "a construction line shows the shell carried down to it."
        )
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    span = (knee.top[0] - knee.bottom[0]) * _ROOT2 + 2.0 * KNEE_END_IN
    note = (
        f"Knee brace under tread {tread_index}: L3x3x3/8 at 45 deg, {span:.3f} in long, on a "
        f"{CLIP_THK_IN:g} x {CLIP_OUT_IN:g} x {CLIP_HEIGHT_IN:g} clip and a {PAD_TALL_IN:g} x "
        f"{PAD_WIDE_IN:g} shell pad, clip bolt {CLIP_BOLT_OUT_IN:g} in out from the shell. "
        f"Holes {'cut' if holes_ok else 'missed'}.{below}"
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _shell(model, frame: _Frame) -> tuple[float | None, float | None]:
    """Shell OD radius and the bottom of the shell, from the shell plates in the part."""
    radius = None
    bottom = None
    for body in s._bodies(model):
        try:
            box = s._box_in(body)
        except Exception:
            continue
        if box[4] - box[1] < 12.0:
            continue
        inside = [r for r in _cylinder_radii(body) if r < frame.r_a - 1.0]
        if not inside:
            continue
        radius = max(inside) if radius is None else max(radius, max(inside))
        bottom = box[1] if bottom is None else min(bottom, box[1])
    return radius, bottom


def _knee_layout(frame: _Frame, shell_r: float) -> _Knee:
    t_face = LEG_SIDE * (LEG_THK_IN + CAP_IN / 2.0)
    r1 = frame.r_b - LEG_HOLE_FROM_END_IN
    y1 = frame.y_top - LEG_HOLE_DOWN_IN
    r2 = shell_r + CLIP_BOLT_OUT_IN
    if r2 >= r1 - 1.0:
        raise SolidWorksError("The knee brace has no room between the stair and the shell.")
    return _Knee(t_face=t_face, top=(r1, y1), bottom=(r2, y1 - (r1 - r2)), shell_r=shell_r)


def _knee_axes(frame: _Frame, sign: float = LEG_SIDE):
    """Down the brace toward the shell, square to it upward, and away from the contact plane."""
    u, v = frame.radial, frame.travel
    down = (-u[0] / _ROOT2, -1.0 / _ROOT2, -u[2] / _ROOT2)
    up = (-u[0] / _ROOT2, 1.0 / _ROOT2, -u[2] / _ROOT2)
    side = (sign * v[0], 0.0, sign * v[2])
    return down, up, side


def _knee_angle(model, frame: _Frame, knee: _Knee, profile: str, name: str) -> None:
    """Member on the heel line: the top edge of the brace, on the contact plane.

    The flat leg lies on the cross brace's down leg and the clip; the other leg
    runs along the top edge, away from the cross brace. The library L is turned
    until that is what the model shows.
    """
    e = KNEE_END_IN / _ROOT2
    w = (LEG_IN / 2.0) / _ROOT2
    (r1, y1), (r2, y2) = knee.top, knee.bottom
    h1 = (r1 + e - w, y1 + e + w)
    h2 = (r2 - e - w, y2 - e + w)
    heel = frame.world(h1[0], knee.t_face, h1[1])
    a = [v * _INCH for v in heel]
    b = [v * _INCH for v in frame.world(h2[0], knee.t_face, h2[1])]
    sketch = model.SketchManager
    before = _names(model)
    with contextlib.suppress(Exception):
        sketch.AddToDB = True
    sketch.Insert3DSketch(True)
    line = sketch.CreateLine(a[0], a[1], a[2], b[0], b[1], b[2])
    sketch.Insert3DSketch(True)
    if line is None:
        raise SolidWorksError(f"{name}: knee brace line was not drawn.")
    path_sketch = _rename_new(model, before, f"{name}Path", "knee path")
    s._select_segments(model, path_sketch, name, 1)
    bodies_before = s._body_names(model)
    try:
        feature = model.FeatureManager.InsertStructuralWeldment2(profile, 1, False, 0.0)
    except Exception as exc:
        raise SolidWorksError(f"{name}: structural member failed ({format_com_error(exc)}).") from exc
    if feature is None:
        raise SolidWorksError(f"{name}: structural member was not made.")
    down, up, side = _knee_axes(frame, knee.side)

    def end_after(turn):
        if not _set_turn(model, feature, turn):
            return []
        body = _new_body(model, bodies_before)
        return [] if body is None else _end_face(body, heel, down, up, side)

    # On a sloped line SolidWorks sets the L twisted about its own axis, and the twist
    # grows the further round the tank the line is (9 deg at 12 deg round). Read how
    # it sits and turn it by exactly that.
    body = _new_body(model, bodies_before)
    end = [] if body is None else _end_face(body, heel, down, up, side)
    if not end:
        end = end_after(0.0)
    off = _turn_off(end)
    if off is None:
        raise SolidWorksError(f"{name}: could not read how the knee brace is turned.")
    # SolidWorks' rotation angle may run either way in this frame, so try both.
    if not _knee_fits(end, 0.01) and not any(_knee_fits(end_after(turn), 0.01) for turn in (off, -off)):
        raise SolidWorksError(f"{name}: could not turn the knee brace with its flat leg on the clip.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if path_sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)


def _new_body(model, before: set[str]):
    for body in s._bodies(model):
        with contextlib.suppress(Exception):
            if str(body.Name) not in before:
                return body
    return None


def _set_turn(model, feature, turn: float) -> bool:
    data = com_value(feature.GetDefinition)
    data.AccessSelections(model, com_nothing())
    # SolidWorks keeps 0 for a negative rotation, so pass the same turn in [0, 2 pi).
    data.RotationAngle = turn % (2.0 * math.pi)
    if not feature.ModifyDefinition(data, model, com_nothing()):
        return False
    s._rebuild(model)
    return True


def _end_face(body, heel, down, up, side) -> list[tuple[float, float]]:
    """Top end face of the knee, as (across, out) from the heel: across is square to
    the brace upward, out is away from the cross brace."""
    points = _body_points(body)
    if not points:
        return []

    def dot(p, axis):
        return sum((p[i] - heel[i]) * axis[i] for i in range(3))

    along = [dot(p, down) for p in points]
    first = min(along)
    return [(dot(p, up), dot(p, side)) for p, a in zip(points, along) if a - first < 0.02]


def _knee_fits(end, tol: float, leg: float = LEG_IN) -> bool:
    """Flat leg ``leg`` in down the face from the heel, other leg ``leg`` in out away from the cross brace."""
    if not end:
        return False
    across = [a for a, _o in end]
    out = [o for _a, o in end]
    return (
        min(across) > -leg - tol and max(across) < tol
        and min(out) > -tol and max(out) < leg + tol
        and max(across) - min(across) > leg - tol - 0.01
        and max(out) - min(out) > leg - tol - 0.01
    )


def _turn_off(end) -> float | None:
    """Turn, counterclockwise in (across, out), that lays the legs along -across and +out.

    The outside faces of the legs bound the end face in a 90 deg wedge from the heel.
    """
    far = [(a, o) for a, o in end if math.hypot(a, o) > 1.0]
    if not far:
        return None
    mean = math.atan2(sum(o for _a, o in far), sum(a for a, _o in far))
    rel = [math.remainder(math.atan2(o, a) - mean, 2.0 * math.pi) for a, o in far]
    bisector = mean + (min(rel) + max(rel)) / 2.0
    return math.remainder(0.75 * math.pi - bisector, 2.0 * math.pi)


def _body_points(body) -> list[tuple[float, float, float]]:
    points = []
    for face in _faces(body):
        try:
            tris = list(face.GetTessTriangles(True) or [])
        except Exception:
            continue
        for i in range(0, len(tris) - 2, 3):
            points.append((tris[i] / _INCH, tris[i + 1] / _INCH, tris[i + 2] / _INCH))
    return points


def _faces(body) -> list:
    raw = body.GetFaces()
    return list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])


def _face_at(bodies, point_in, normal):
    """Planar face whose plane goes through ``point_in`` square to ``normal`` and whose box holds the point."""
    point = [v * _INCH for v in point_in]
    tol = 0.01 * _INCH

    def holds(box):
        return all(box[i] - tol <= point[i] <= box[i + 3] + tol for i in range(3))

    for body in bodies:
        with contextlib.suppress(Exception):
            if not holds([float(v) for v in com_value(body.GetBodyBox)]):
                continue
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
            if holds(box):
                return face
    return None


def _sketch_at(model, point_in, name: str, draw, normal=None):
    """Sketch on the face at a model point (inches); ``draw(manager, to_sketch)``.

    With ``normal`` the face is found from the bodies; without it, it is picked through the view.
    """
    point_m = [v * _INCH for v in point_in]
    _clear_selection(model)
    if normal is not None:
        face = _face_at(s._bodies(model), point_in, normal)
        if face is None or not s._select_face(model, face):
            raise SolidWorksError(f"{name}: could not find the face to sketch on.")
    elif not model.Extension.SelectByID2("", "FACE", point_m[0], point_m[1], point_m[2], False, 0, com_nothing(), 0):
        raise SolidWorksError(f"{name}: could not pick the face to sketch on.")
    before = _names(model)
    manager = model.SketchManager
    with contextlib.suppress(Exception):
        manager.AddToDB = True
    with contextlib.suppress(Exception):
        manager.DisplayWhenAdded = False
    manager.InsertSketch(True)
    try:
        sketch_obj = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch_obj.ModelToSketchTransform).ArrayData)]

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
    return _rename_new(model, before, name, "sketch")


def _extrude_to(model, sketch, depth_in: float, center_in, max_height: float, name: str) -> None:
    """Separate-body extrude; flipped if the first try does not land on ``center_in``."""
    for reverse in (False, True):
        _clear_selection(model)
        if not s._select_feature(model, sketch, "SKETCH", mark=0, append=False):
            raise SolidWorksError(f"{name}: could not select its sketch.")
        feature = extrude_blind(model.FeatureManager, depth_in * _INCH, merge=False, reverse=reverse)
        s._rebuild(model)
        if s._body_near(model, center_in, max_height=max_height, max_dist=0.1) is not None:
            with contextlib.suppress(Exception):
                rename_feature(feature, name)
            return
        with contextlib.suppress(Exception):
            s._delete_named(model, (s._feature_name(feature),))
    raise SolidWorksError(f"{name}: did not land where it should.")


def knee_pad(knee: _Knee) -> tuple[float, float]:
    """Middle of a knee's shell pad: t along its frame's travel, and y. The pad is PAD_WIDE_IN by PAD_TALL_IN
    with full-radius ends, on the shell OD, centered on the clip."""
    return knee.t_face - knee.side * CLIP_THK_IN / 2.0, knee.bottom[1]


def _knee_clip_and_pad(model, frame: _Frame, knee: _Knee, name: str) -> None:
    """Clip in line with the cross brace down leg, then the shell pad behind it."""
    r2, y2 = knee.bottom
    t_mid, _y = knee_pad(knee)
    root = knee.shell_r + PAD_THK_IN
    half = CLIP_HEIGHT_IN / 2.0
    clip = ((root, y2 - half), (root + CLIP_OUT_IN, y2 - half), (root + CLIP_OUT_IN, y2 + half), (root, y2 + half))

    def draw_clip(manager, to_sketch):
        pts = [to_sketch(frame.world(r, knee.t_face, y)) for r, y in clip]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: clip edge failed.")

    # The knee's flat leg at the clip bolt is the clip's outside face.
    clip_sketch = _sketch_at(model, frame.world(r2, knee.t_face, y2), f"{name}ClipSk", draw_clip, frame.travel)
    _extrude_to(
        model, clip_sketch, CLIP_THK_IN, frame.world(root + CLIP_OUT_IN / 2.0, t_mid, y2),
        CLIP_HEIGHT_IN + 0.1, f"{name}Clip",
    )

    def draw_pad(manager, to_sketch):
        _draw_pad(manager, lambda t, y: to_sketch(frame.world(root, t, y)), t_mid, y2, PAD_TALL_IN, name)

    # The clip's end at the shell is the pad's outside face.
    pad_sketch = _sketch_at(model, frame.world(root, t_mid, y2), f"{name}PadSk", draw_pad, frame.radial)
    _extrude_to(
        model, pad_sketch, PAD_THK_IN, frame.world(knee.shell_r + PAD_THK_IN / 2.0, t_mid, y2),
        PAD_TALL_IN + 0.1, f"{name}Pad",
    )


def _draw_pad(manager, at, t_mid: float, y_mid: float, tall: float, name: str) -> None:
    """Shell pad outline, PAD_WIDE_IN wide with full-radius ends. ``at(t, y)`` gives sketch x, y."""
    radius = PAD_WIDE_IN / 2.0
    straight = tall / 2.0 - radius
    lo_l, hi_l = at(t_mid - radius, y_mid - straight), at(t_mid - radius, y_mid + straight)
    lo_r, hi_r = at(t_mid + radius, y_mid - straight), at(t_mid + radius, y_mid + straight)
    top, bottom = at(t_mid, y_mid + straight + radius), at(t_mid, y_mid - straight - radius)
    if manager.CreateLine(lo_l[0], lo_l[1], 0.0, hi_l[0], hi_l[1], 0.0) is None:
        raise SolidWorksError(f"{name}: pad edge failed.")
    if manager.Create3PointArc(hi_l[0], hi_l[1], 0.0, hi_r[0], hi_r[1], 0.0, top[0], top[1], 0.0) is None:
        raise SolidWorksError(f"{name}: pad end failed.")
    if manager.CreateLine(hi_r[0], hi_r[1], 0.0, lo_r[0], lo_r[1], 0.0) is None:
        raise SolidWorksError(f"{name}: pad edge failed.")
    if manager.Create3PointArc(lo_r[0], lo_r[1], 0.0, lo_l[0], lo_l[1], 0.0, bottom[0], bottom[1], 0.0) is None:
        raise SolidWorksError(f"{name}: pad end failed.")


def _knee_holes(model, frame: _Frame, knee: _Knee, name: str) -> bool:
    """13/16 at both knee bolts: through the knee, the cross brace leg, and the clip."""
    t_in = knee.t_face + knee.side * LEG_THK_IN
    centers = [frame.world(r, t_in, y) for r, y in (knee.top, knee.bottom)]

    def draw(manager, to_sketch):
        for point in centers:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, KNEE_HOLE_DIA_IN / 2.0 * _INCH) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    try:
        sketch = _sketch_at(model, centers[0], f"{name}HolesSk", draw, frame.travel)
    except SolidWorksError:
        return False
    feature = s._cut_both_ways(model, sketch, 2.0 * LEG_THK_IN + CLIP_THK_IN + 0.25)
    if feature is None:
        s._delete_named(model, (f"{name}HolesSk",))
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Holes")
    s._rebuild(model)
    radius_m = KNEE_HOLE_DIA_IN / 2.0 * _INCH
    for point in centers:
        point_m = [v * _INCH for v in point]
        if not any(s._has_hole_axis(body, point_m, radius_m, 0.1 * _INCH) is True for body in s._bodies(model)):
            return False
    return True


def _shell_line(model, frame: _Frame, knee: _Knee, y_from: float, y_to: float, name: str) -> None:
    """Construction line on the shell OD, from the pad up to the shell bottom."""
    t_mid = knee.t_face - knee.side * CLIP_THK_IN / 2.0
    a = [v * _INCH for v in frame.world(knee.shell_r, t_mid, y_from)]
    b = [v * _INCH for v in frame.world(knee.shell_r, t_mid, y_to)]
    sketch = model.SketchManager
    before = _names(model)
    sketch.Insert3DSketch(True)
    line = sketch.CreateLine(a[0], a[1], a[2], b[0], b[1], b[2])
    sketch.Insert3DSketch(True)
    if line is not None:
        with contextlib.suppress(SolidWorksError):
            _rename_new(model, before, name, "shell extension line")
