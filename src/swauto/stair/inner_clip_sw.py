"""Inner clip at one tread: the inner stringer tied back to a landing clip on the shell.

From InnerClip.lsp (INNERCLIP), the stair section in Tread Sideview.lsp, and
SpiralTreadInnerClip.lsp. An L4x3x3/8 from the SolidWorks library, 6 in long,
stands on the tank side of the inner stringer with its bottom level with the
tread top. The 3 in leg is bolted flat to the stringer through two 13/16 holes
3 in apart, 1-11/16 in from the heel, the lower one 1-1/2 in above the tread
top. Along the stringer the top hole sits 1-1/4 in square to the stringer's top
edge in the inner stringer's development, with the heel on the uphill side.
The 4 in leg points at the tank and is bolted through two more 13/16 holes,
2-5/8 in out from the heel, to a 3/8 landing clip as tall as the angle on the
leg's uphill face. The landing clip runs from a 1/4 shell pad (4 in wide,
8 in tall, 2 in radius ends) to 1/2 in short of the stringer: 7-1/4 in long at
an 8 in gap.

The angle is flat and the stringer is curved, so the angle is set in by the
sag over its leg: it touches the stringer at the heel and clears it elsewhere.
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
    PAD_WIDE_IN,
    BraceResult,
    _body_points,
    _draw_pad,
    _extrude_to,
    _Frame,
    _new_body,
    _progress,
    _set_turn,
    _shell,
    _sketch_at,
    _stair_parts,
    flight_tops,
)
from swauto.stair.stringer import THICKNESS_IN, TREAD_DEPTH_IN, TREAD_MARK_IN
from swauto.stair.stringer_sw import _create_circle, _names, _rename_new
from swauto.tank.shell import _clear_selection

_INCH = 0.0254
PROFILE = ("ansi inch", "L Angle", "L4x3x0.375.SLDLFP")
LONG_LEG_IN = 4.0  # toward the tank
SHORT_LEG_IN = 3.0  # flat on the stringer
LEG_THK_IN = 0.375
TALL_IN = 6.0
HOLE_DIA_IN = 0.8125  # 13/16
HOLE_LOW_IN = 1.5  # lower hole above the tread top
HOLE_SPACE_IN = 3.0
HEEL_FROM_HOLE_IN = 1.6875  # stringer holes to the heel
LANDING_HOLE_IN = 2.625  # landing holes out from the heel
EDGE_CLEAR_IN = 1.25  # top hole to the stringer's top edge, square to it
LANDING_THK_IN = 0.375
LANDING_SHORT_IN = 0.5  # landing clip end to the stringer
PAD_THK_IN = 0.25
PAD_TALL_IN = 8.0
MIN_GAP_IN = 4.5  # the 4 in leg has to clear the pad


@dataclass(frozen=True)
class _Clip:
    phi: float  # angle of the stringer holes
    heel_r: float  # back of the flat leg
    tank_face: float  # tank side of the inner stringer
    shell_r: float  # shell OD
    y0: float  # tread top, the bottom of the clip

    @property
    def radial(self) -> tuple[float, float, float]:
        return (-math.sin(self.phi), 0.0, math.cos(self.phi))

    @property
    def travel(self) -> tuple[float, float, float]:
        """Toward the upper treads."""
        return (-math.cos(self.phi), 0.0, -math.sin(self.phi))

    def world(self, r: float, t: float, y: float) -> tuple[float, float, float]:
        """Inches: r out along the hole line, t toward the upper treads, y up."""
        c, sn = math.cos(self.phi), math.sin(self.phi)
        return (-r * sn - t * c, y, r * c - t * sn)

    def local(self, point) -> tuple[float, float]:
        """(r, t) of a model point in inches."""
        c, sn = math.cos(self.phi), math.sin(self.phi)
        return (-point[0] * sn + point[2] * c, -point[0] * c - point[2] * sn)

    @property
    def hole_ys(self) -> tuple[float, float]:
        return (self.y0 + HOLE_LOW_IN, self.y0 + HOLE_LOW_IN + HOLE_SPACE_IN)

    @property
    def y_mid(self) -> float:
        return self.y0 + TALL_IN / 2.0

    @property
    def landing_t(self) -> float:
        """Mid-plane of the landing clip."""
        return HEEL_FROM_HOLE_IN + LANDING_THK_IN / 2.0


def clip_angle_profile(app) -> str:
    """The L4x3x0.375 file in this SolidWorks' weldment library."""
    root = str(com_value(app.GetExecutablePath))
    path = os.path.join(root, "lang", "english", "weldment profiles", *PROFILE)
    if not os.path.isfile(path):
        raise SolidWorksError(f"The L4x3x0.375 weldment profile is not at {path}.")
    return path


def add_inner_clip(model, tread_index: int, profile: str, shell_radius_in: float | None = None, progress=None) -> BraceResult:
    """Inner clip above tread ``tread_index``. ``profile`` is from ``clip_angle_profile``.

    The shell OD radius is read from the shell plates in the part; ``shell_radius_in``
    is used when the part has no shell.
    """
    clip = _layout(model, tread_index, shell_radius_in)
    name = f"EliteBrace{tread_index:02d}Inner"
    _clip_angle(model, clip, profile, name)
    _progress(progress, f"{name} angle placed")
    _landing_and_pad(model, clip, name)
    _progress(progress, f"{name} landing clip placed")
    stringer_ok = _stringer_holes(model, clip, name)
    landing_ok = _landing_holes(model, clip, name)
    _progress(progress, f"{name} holes {'cut' if stringer_ok and landing_ok else 'missed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()
    landing = clip.tank_face - LANDING_SHORT_IN - clip.shell_r - PAD_THK_IN
    note = (
        f"Inner clip above tread {tread_index}: L4x3x3/8 x {TALL_IN:g} in on the inner stringer, "
        f"bolted to a {LANDING_THK_IN:g} x {landing:.3f} x {TALL_IN:g} landing clip on a "
        f"{PAD_WIDE_IN:g} x {PAD_TALL_IN:g} shell pad. Stringer holes {'cut' if stringer_ok else 'missed'}, "
        f"landing clip holes {'cut' if landing_ok else 'missed'}."
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _layout(model, tread_index: int, shell_radius_in: float | None) -> _Clip:
    r_a, r_b, treads = _stair_parts(model)
    count = len(treads)
    if not 1 <= tread_index <= count:
        raise SolidWorksError(f"This stair has {count} treads; there is no tread {tread_index}.")
    if tread_index in flight_tops([y for y, _phi, _r in treads]):
        raise SolidWorksError(
            f"Tread {tread_index} is the top of its flight. The inner stringer stops at its top, "
            "so there is no plate above it for the inner clip."
        )
    y_bottom, phi, _r = treads[tread_index - 1]
    # One step up the same flight: a mid platform turns the stair without rising.
    (y_low, phi_low, _r1), (y_high, phi_high, _r2) = next(
        (a, b) for a, b in zip(treads, treads[1:]) if b[0] - a[0] > 0.01
    )
    tan_p = (y_high - y_low) / (phi_high - phi_low) / r_a
    pitch = math.atan(tan_p)
    # Inner stringer development at its walk face: the top edge runs through the
    # tread's trailing top corner, and the top hole is EDGE_CLEAR_IN square below it.
    along = -TREAD_DEPTH_IN / 2.0 + (HOLE_LOW_IN + HOLE_SPACE_IN) / tan_p + EDGE_CLEAR_IN / math.sin(pitch)
    tank_face = r_a - THICKNESS_IN
    reach = max(HEEL_FROM_HOLE_IN, SHORT_LEG_IN - HEEL_FROM_HOLE_IN)
    sag = reach * reach / (2.0 * tank_face) + 0.001
    shell_r, _bottom = _shell(model, _Frame(phi=phi, y_top=0.0, r_a=r_a, r_b=r_b))
    if shell_r is None:
        if shell_radius_in is None:
            raise SolidWorksError("This part has no tank shell; the inner clip needs the shell radius.")
        shell_r = shell_radius_in
    if tank_face - shell_r < MIN_GAP_IN:
        raise SolidWorksError(
            f"The gap is {tank_face - shell_r:.2f} in; the inner clip's 4 in leg needs at least {MIN_GAP_IN:g} in."
        )
    return _Clip(
        phi=phi + along / r_a,
        heel_r=tank_face - sag,
        tank_face=tank_face,
        shell_r=shell_r,
        y0=y_bottom + TREAD_MARK_IN,
    )


def _clip_angle(model, clip: _Clip, profile: str, name: str) -> None:
    """Library L4x3 on a vertical line at the heel.

    SolidWorks sets the L's turn on a vertical line itself, so the turn is read
    off the member and corrected: 4 in leg in toward the tank, 3 in leg flat on
    the stringer running down the stair from the heel. If the L comes in
    mirrored, the line is drawn the other way.
    """
    heel = clip.world(clip.heel_r, HEEL_FROM_HOLE_IN, clip.y0)
    want_long = (math.sin(clip.phi), -math.cos(clip.phi))  # plan x, z
    want_short = (math.cos(clip.phi), math.sin(clip.phi))
    ends = [clip.world(clip.heel_r, HEEL_FROM_HOLE_IN, y) for y in (clip.y0, clip.y0 + TALL_IN)]
    for flip in (False, True):
        a, b = (ends[1], ends[0]) if flip else (ends[0], ends[1])
        feature, path_sketch, bodies_before = _member(model, profile, a, b, name)
        body = _new_body(model, bodies_before)
        if body is None:
            s._rebuild(model)
            body = _new_body(model, bodies_before)
        placed = _clip_fits(body, clip)
        axes = None if body is None or placed else _leg_axes(body, heel)
        if axes is not None and _hand(*axes) * _hand(want_long, want_short) > 0:
            turn = _angle_between(axes[0], want_long)
            for rotation in (turn, -turn):
                if _set_turn(model, feature, rotation) and _clip_fits(_new_body(model, bodies_before), clip):
                    placed = True
                    break
        if placed:
            with contextlib.suppress(Exception):
                rename_feature(feature, name)
            _clear_selection(model)
            with contextlib.suppress(Exception):
                if path_sketch.Select2(False, 0):
                    model.BlankSketch()
            _clear_selection(model)
            return
        with contextlib.suppress(Exception):
            s._delete_named(model, (s._feature_name(feature), s._feature_name(path_sketch)))
        s._rebuild(model)
    raise SolidWorksError(f"{name}: could not turn the clip angle with its 4 in leg toward the tank.")


def _member(model, profile: str, a, b, name: str):
    """3D line from ``a`` to ``b`` (inches) and the structural member on it."""
    a_m = [v * _INCH for v in a]
    b_m = [v * _INCH for v in b]
    sketch = model.SketchManager
    before = _names(model)
    with contextlib.suppress(Exception):
        sketch.AddToDB = True
    sketch.Insert3DSketch(True)
    line = sketch.CreateLine(a_m[0], a_m[1], a_m[2], b_m[0], b_m[1], b_m[2])
    sketch.Insert3DSketch(True)
    if line is None:
        raise SolidWorksError(f"{name}: clip angle line was not drawn.")
    path_sketch = _rename_new(model, before, f"{name}Path", "clip angle path")
    s._select_segments(model, path_sketch, name, 1)
    bodies_before = s._body_names(model)
    try:
        feature = model.FeatureManager.InsertStructuralWeldment2(profile, 1, False, 0.0)
    except Exception as exc:
        raise SolidWorksError(f"{name}: structural member failed ({format_com_error(exc)}).") from exc
    if feature is None:
        raise SolidWorksError(f"{name}: structural member was not made.")
    return feature, path_sketch, bodies_before


def _faces(body) -> list:
    raw = body.GetFaces()
    return list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])


def _leg_axes(body, heel) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Plan directions (x, z) of the 4 in leg and the 3 in leg, out from the heel."""
    best = None
    for face in _faces(body):
        try:
            surface = com_value(face.GetSurface)
            flag = surface.IsPlane
            if not (flag() if callable(flag) else flag):
                continue
            normal = [float(v) for v in com_value(surface.PlaneParams)][:3]
            area = float(com_value(face.GetArea))
        except Exception:
            continue
        if abs(normal[1]) > 0.1:
            continue
        if best is None or area > best[0]:
            best = (area, normal)
    if best is None:
        return None
    size = math.hypot(best[1][0], best[1][2])
    # The broadest side is the back of the 4 in leg; the 3 in leg runs square to it.
    short = (best[1][0] / size, best[1][2] / size)
    long = (-short[1], short[0])
    plan = [(p[0] - heel[0], p[2] - heel[2]) for p in _body_points(body)]
    if not plan:
        return None
    if sum(x * long[0] + z * long[1] for x, z in plan) < 0:
        long = (-long[0], -long[1])
    if sum(x * short[0] + z * short[1] for x, z in plan) < 0:
        short = (-short[0], -short[1])
    return long, short


def _hand(a, b) -> float:
    """Up component of a x b for plan vectors (x, z)."""
    return a[1] * b[0] - a[0] * b[1]


def _angle_between(a, b) -> float:
    """Turn about +Y that takes plan vector ``a`` to ``b``."""
    return math.atan2(_hand(a, b), a[0] * b[0] + a[1] * b[1])


def _clip_fits(body, clip: _Clip, tol: float = 0.03) -> bool:
    """4 in leg from the heel in toward the tank, 3 in leg from the heel down the stair."""
    if body is None:
        return False
    points = _body_points(body)
    if not points:
        return False
    rs, ts = zip(*(clip.local(p) for p in points))
    heel_t = HEEL_FROM_HOLE_IN
    return (
        min(rs) > clip.heel_r - LONG_LEG_IN - tol and max(rs) < clip.heel_r + tol
        and min(ts) > heel_t - SHORT_LEG_IN - tol and max(ts) < heel_t + tol
        and max(rs) - min(rs) > LONG_LEG_IN - tol - 0.01
        and max(ts) - min(ts) > SHORT_LEG_IN - tol - 0.01
    )


def _landing_and_pad(model, clip: _Clip, name: str) -> None:
    """Landing clip on the uphill face of the 4 in leg, then the shell pad behind it."""
    heel_t = HEEL_FROM_HOLE_IN
    root = clip.shell_r + PAD_THK_IN
    tip = clip.tank_face - LANDING_SHORT_IN
    y0, y1 = clip.y0, clip.y0 + TALL_IN
    corners = ((root, y0), (tip, y0), (tip, y1), (root, y1))

    def draw_landing(manager, to_sketch):
        pts = [to_sketch(clip.world(r, heel_t, y)) for r, y in corners]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: landing clip edge failed.")

    leg_face = clip.world(clip.heel_r - LONG_LEG_IN / 2.0, heel_t, clip.y_mid)
    # Faces are found from the bodies: a pick through the view can take the face in front.
    landing_sketch = _sketch_at(model, leg_face, f"{name}LandingSk", draw_landing, clip.travel)
    _extrude_to(
        model, landing_sketch, LANDING_THK_IN, clip.world((root + tip) / 2.0, clip.landing_t, clip.y_mid),
        TALL_IN + 0.1, f"{name}Landing",
    )

    def draw_pad(manager, to_sketch):
        _draw_pad(manager, lambda t, y: to_sketch(clip.world(root, t, y)), clip.landing_t, clip.y_mid, PAD_TALL_IN, name)

    # The landing clip's end at the shell is the pad's outside face.
    pad_sketch = _sketch_at(model, clip.world(root, clip.landing_t, clip.y_mid), f"{name}PadSk", draw_pad, clip.radial)
    _extrude_to(
        model, pad_sketch, PAD_THK_IN, clip.world(clip.shell_r + PAD_THK_IN / 2.0, clip.landing_t, clip.y_mid),
        PAD_TALL_IN + 0.1, f"{name}Pad",
    )


def _stringer_holes(model, clip: _Clip, name: str) -> bool:
    """Two 13/16 holes through the 3 in leg and the stringer, square to the stringer."""
    back = clip.heel_r - LEG_THK_IN
    centers = [clip.world(back, 0.0, y) for y in clip.hole_ys]
    reach = LEG_THK_IN + THICKNESS_IN + (clip.tank_face - clip.heel_r) + 0.06
    if not _cut_holes(model, clip.world(back, 0.0, clip.y_mid), clip.radial, centers, reach, f"{name}Holes"):
        return False
    return all(
        s._stringer_has_hole(model, clip.tank_face, clip.world(clip.tank_face, 0.0, y), HOLE_DIA_IN / 2.0, 0.12 * _INCH)
        is True
        for y in clip.hole_ys
    )


def _landing_holes(model, clip: _Clip, name: str) -> bool:
    """Two 13/16 holes through the landing clip and the 4 in leg."""
    face_t = HEEL_FROM_HOLE_IN + LANDING_THK_IN
    r = clip.heel_r - LANDING_HOLE_IN
    centers = [clip.world(r, face_t, y) for y in clip.hole_ys]
    pick = clip.world(r + 1.0, face_t, clip.y_mid)
    return _cut_holes(model, pick, clip.travel, centers, LANDING_THK_IN + LEG_THK_IN + 0.06, f"{name}LandingHoles")


def _cut_holes(model, pick, normal, centers, reach: float, name: str) -> bool:
    """Circles at ``centers`` on the face at ``pick``, square to ``normal``, cut both ways. True when all are in."""

    def draw(manager, to_sketch):
        for point in centers:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, HOLE_DIA_IN / 2.0 * _INCH) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    try:
        sketch = _sketch_at(model, pick, f"{name}Sk", draw, normal)
    except SolidWorksError:
        return False
    feature = s._cut_both_ways(model, sketch, reach)
    if feature is None:
        s._delete_named(model, (f"{name}Sk",))
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
    radius_m = HOLE_DIA_IN / 2.0 * _INCH
    for point in centers:
        point_m = [v * _INCH for v in point]
        if not any(s._has_hole_axis(body, point_m, radius_m, 0.1 * _INCH) is True for body in s._bodies(model)):
            return False
    return True
