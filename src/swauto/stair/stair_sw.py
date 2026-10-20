"""Spiral stair on the tank: shell, two climbing stringers, pan treads, bolts.

The stringers are the formed 3/8 x 9 in plates swept on a helix at each
radius, the same solids as the earlier visual model. Each tread is a five-face
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

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature
from swauto.params import rename_feature
from swauto.parts import extrude_blind
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
    _names,
    _rename_new,
    _select_feature,
)
from swauto.tank.profile import course_radii_m
from swauto.tank.shell import (
    _clear_selection,
    _close_sketch,
    _feature_name,
    _open_sketch,
    create_tank_shell,
)
from swauto.tank.spec import WALL_OD, TankSpec

_INCH = 0.0254
TREAD_CLEAR_IN = (CLEAR_IN - TREAD_PLATE_IN) / 2.0


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


def create_stair_on_tank(app, stair: StringerMock, wall_in: float, progress=None) -> StairResult:
    """New part with the shell at the Stringer tab's OD radius, then the stair."""
    stair.validate()
    if wall_in <= 0 or wall_in >= TREAD_MARK_IN or wall_in * 2 >= TREAD_DEPTH_IN:
        raise ValueError("Pan wall must be greater than zero and thinner than the tread.")
    tank = TankSpec(diameter_in=2.0 * stair.shell_od_in, diameter_basis=WALL_OD)
    shell = create_tank_shell(app, tank)
    model = shell.live.model
    outer_m, _inner_m = course_radii_m(tank, tank.active_courses()[0])
    shell_od = outer_m / _INCH
    _progress(progress, "shell built")
    return build_stair_on_model(model, shell_od, stair, wall_in, progress=progress)


def _progress(callback, text: str) -> None:
    if callback is not None:
        with contextlib.suppress(Exception):
            callback(text)


def build_stair_on_model(
    model,
    shell_od: float,
    stair: StringerMock,
    wall_in: float,
    *,
    stringers: bool = True,
    progress=None,
) -> StairResult:
    """Stringers (unless already there), then tread by tread: pan, inner bolts, outer bolts."""
    layout = layout_stringer(
        StringerMock(
            shell_od_in=shell_od,
            gap_in=stair.gap_in,
            treads=stair.treads,
            rise_in=stair.rise_in,
            run_in=stair.run_in,
            plate_width_in=stair.plate_width_in,
            outside_face=True,
        )
    )
    try:
        if stringers:
            inner_mid = shell_od + stair.gap_in + THICKNESS_IN / 2.0
            _stringer(model, layout, inner_mid, "EliteStringerIn")
            _progress(progress, "inner stringer swept")
            _stringer(model, layout, layout.mid_radius_in, "EliteStringerOut")
            _progress(progress, "outer stringer swept")
            with contextlib.suppress(Exception):
                model.EditRebuild3()
        done = 0
        total = 0
        # One tread at a time: the pan, then its inner bolts, then its outer bolts.
        for place in _tread_places(layout):
            _tread(model, layout, place, wall_in)
            _progress(progress, f"tread {place.index} placed")
            for side in ("In", "Out"):
                total += 1
                try:
                    hit = _bolts(model, layout, place, side, wall_in)
                except SolidWorksError:
                    raise
                except Exception:
                    _recover(model)
                    hit = False
                done += int(hit)
                _progress(progress, f"tread {place.index} {side.lower()} bolts {'through' if hit else 'missed'}")
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Stair failed: {format_com_error(exc)}") from exc
    with contextlib.suppress(Exception):
        model.ShowNamedView2("*Isometric", 7)
        model.ViewZoomtofit2()
        model.ViewDisplayShaded()
        model.GraphicsRedraw2()
    note = (
        f"Shell OD radius {shell_od:.2f} in, {stair.treads} pan treads with {wall_in:g} in walls, "
        f"sweep {layout.sweep_deg:.2f}°, rise {layout.total_rise_in:.1f} in. "
        f"Bolt pairs through {done} of {total} stringer-to-tread joints."
    )
    return StairResult(title=str(com_value(model.GetTitle) or "Part"), model=model, note=note)


# ---------------------------------------------------------------- stringers


def _stringer(model, layout, mid_in: float, name: str) -> None:
    revolutions = layout.sweep_rad / (2.0 * math.pi)
    helix = _helix(model, mid_in, layout.total_rise_in, revolutions, layout.plate_width_in / 2.0, name)
    before_bodies = _body_names(model)
    _sweep(model, helix, mid_in, layout.plate_width_in, name)
    _name_new_body(model, before_bodies, name)


def _helix(model, radius_in: float, height_in: float, revolutions: float, y_in: float, name: str):
    top = _plane(model, "Top")
    before = _names(model)
    _clear_selection(model)
    if not top.Select2(False, 0):
        raise SolidWorksError("Could not select the Top Plane.")
    model.CreatePlaneAtOffset(y_in * _INCH, False)
    plane = _rename_new(model, before, f"{name}Pln", "helix plane")
    before = _names(model)
    _open_sketch(model, plane)
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
    model.InsertHelix(False, True, False, False, 1, height_in * _INCH, 0.0, float(revolutions), 0.0, 0.0)
    return _rename_new(model, before, f"{name}Helix", "helix")


def _sweep(model, helix, mid_in: float, width_in: float, name: str) -> None:
    right = _plane(model, "Right")
    before = _names(model)
    _open_sketch(model, right)
    # Right-plane sketch: +X is world -Z, +Y is world +Y.
    x_mid = -mid_in * _INCH
    half_t = (THICKNESS_IN / 2.0) * _INCH
    half_w = (width_in / 2.0) * _INCH
    rect = model.SketchManager.CreateCornerRectangle(x_mid - half_t, 0.0, 0.0, x_mid + half_t, 2.0 * half_w, 0.0)
    if rect is None:
        _recover(model)
        raise SolidWorksError(f"{name}: profile rectangle failed.")
    _close_sketch(model)
    profile = _rename_new(model, before, f"{name}Prof", "sweep profile")
    method = model.FeatureManager.InsertProtrusionSwept3
    attempts = (
        (False, False, 0, False, False, 0, 0, False, 0.0, 0.0, 0, False, False, True, 0.0, True),
        (False, False, 0, False, False, 0, 0, False, 0.0, 0.0, 0, False, False, True, 0.0, True, False),
    )
    errors: list[str] = []
    for args in attempts:
        _clear_selection(model)
        if not profile.Select2(False, 1):
            raise SolidWorksError(f"{name}: could not select the profile.")
        if not _select_feature(model, helix, "REFERENCECURVES", mark=4, append=True):
            raise SolidWorksError(f"{name}: could not select the helix.")
        try:
            feature = method(*args)
        except Exception as exc:
            errors.append(format_com_error(exc))
            continue
        if feature not in (None, False):
            with contextlib.suppress(Exception):
                rename_feature(feature, name)
            return
    raise SolidWorksError(f"{name}: sweep failed ({'; '.join(errors) or 'returned nothing'}).")


# ------------------------------------------------------------------- treads


def _tread_places(layout) -> list[TreadPlace]:
    inner_edge = layout.inner_face_in + TREAD_CLEAR_IN
    center_r = inner_edge + TREAD_PLATE_IN / 2.0
    places: list[TreadPlace] = []
    count = len(layout.treads)
    for index in range(1, count + 1):
        phi = index / count * layout.sweep_rad
        y_center = layout.plate_width_in / 2.0 + (index / count) * layout.total_rise_in
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
                with contextlib.suppress(Exception):
                    model.EditRebuild3()
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

    face_point = world(0.0, (place.y0 + place.y1) / 2.0)
    before = _names(model)
    _clear_selection(model)
    nothing = com_nothing()
    if not model.Extension.SelectByID2("", "FACE", face_point[0], face_point[1], face_point[2], False, 0, nothing, 0):
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
    reach_in = max(wall_in, TREAD_CLEAR_IN + THICKNESS_IN) + 0.25
    stringer_name = f"EliteStringer{side}"
    tread_name = f"EliteTread{place.index:02d}"
    bodies_before = _classify(model, layout, place)
    counts_before = _counts(bodies_before)
    feature = _cut_both_ways(model, sketch, reach_in)
    if feature is not None:
        with contextlib.suppress(Exception):
            rename_feature(feature, name)
        bodies_after = _classify(model, layout, place)
        counts_after = _counts(bodies_after)
        if (
            counts_after.get(stringer_name, 0) > counts_before.get(stringer_name, 0)
            and counts_after.get(tread_name, 0) > counts_before.get(tread_name, 0)
        ):
            for key, body in bodies_after.items():
                with contextlib.suppress(Exception):
                    body.Name = key
            return True
        _delete_named(model, (name,))
    _delete_named(model, (f"{name}Sk",))
    return False


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
        if height >= layout.total_rise_in - 1.0 and height <= layout.total_rise_in + layout.plate_width_in + 1.0:
            reach = max(math.hypot(box[0], box[2]), math.hypot(box[3], box[5]), math.hypot(box[0], box[5]), math.hypot(box[3], box[2]))
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
