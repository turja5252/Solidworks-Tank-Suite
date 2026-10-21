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
from swauto.features import find_feature, iter_features
from swauto.params import rename_feature
from swauto.parts import extrude_blind
from swauto.stair.development import END_HOLE_RADIUS_IN, SLOT_LENGTH_IN, DevelopedStringer, develop_both
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
    _ensure_tank_axis,
    _feature_name,
    _open_sketch,
    create_tank_shell,
)
from swauto.tank.spec import WALL_OD, TankSpec

_INCH = 0.0254
TREAD_CLEAR_IN = (CLEAR_IN - TREAD_PLATE_IN) / 2.0
WIDE_EXTRA_IN = 3.0  # extra plate below the 9 in line, trimmed back after the sweep


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
    do_treads: bool = True,
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
            inner_dev, outer_dev = develop_both(
                StringerMock(
                    shell_od_in=shell_od,
                    gap_in=stair.gap_in,
                    treads=stair.treads,
                    rise_in=stair.rise_in,
                    run_in=stair.run_in,
                    plate_width_in=stair.plate_width_in,
                )
            )
            axis = _ensure_tank_axis(model)
            if axis is None:
                raise SolidWorksError("Could not create the tank axis for the stringer end holes.")
            tank_face = shell_od + stair.gap_in
            jobs = (
                (inner_dev, tank_face, tank_face + THICKNESS_IN, "EliteStringerIn"),
                (outer_dev, layout.outside_radius_in - THICKNESS_IN, layout.outside_radius_in, "EliteStringerOut"),
            )
            # Sweep both wide plates first. A swept cut right after its own
            # protrusion returns nothing, but cuts cleanly once the plates have
            # settled through the second sweep and a rebuild.
            for dev, r_in, r_out, nm in jobs:
                _stringer_sweep(model, layout, dev, r_in, r_out, nm)
                _progress(progress, f"{nm} swept")
            _rebuild(model)
            for dev, r_in, r_out, nm in jobs:
                _stringer_form(model, layout, dev, r_in, r_out, nm, axis, progress)
            _rebuild(model)
        done = 0
        total = 0
        # One tread at a time: the pan, then its inner bolts, then its outer bolts.
        for place in (_tread_places(layout) if do_treads else []):
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


def _stringer_sweep(model, layout, dev: DevelopedStringer, r_in: float, r_out: float, name: str) -> None:
    """Sweep the wide plate. The finished width is cut back later (deductive)."""
    g = _stringer_geometry(layout, dev, r_in, r_out)
    helix = _helix(model, g["r_mid"], g["rise_per_rad"] * g["phi_end"], g["phi_end"] / (2.0 * math.pi), name)
    before_bodies = _body_names(model)
    _sweep(model, helix, r_in, r_out, g["bottom_at_zero"] - WIDE_EXTRA_IN, g["top_at_zero"], name)
    _name_new_body(model, before_bodies, name)


def _stringer_form(model, layout, dev: DevelopedStringer, r_in: float, r_out: float, name: str, axis, progress=None) -> None:
    """Trim the swept plate to the lisp burn outline and cut the end holes.

    The plate is one piece. The 9 in edge is one helix from the lower cutback
    to the upper cutback. Each horizontal end cut stops on that helix, which
    is the lisp outline: top flat, vertical, return; bottom vertical, then
    the foot. All deductive, no merge.
    """
    g = _stringer_geometry(layout, dev, r_in, r_out)
    radius, band = g["radius"], g["band"]
    p4, p_start, p_end, p2, p3, l2_end, l3_end, p5 = g["outline"]

    # l2 is where the 9 in line meets the top cutback. The trim runs to there
    # and no further, so the boot below that line stays for the return cut.
    trim_phi = l2_end[0] / radius
    foot_phi = l3_end[0] / radius
    trim_spec = (g["r_mid"], g["rise_per_rad"] * trim_phi, trim_phi / (2.0 * math.pi))
    _cut_sweep(model, trim_spec, band, g["bottom_at_zero"] - WIDE_EXTRA_IN - 1.0, g["bottom_at_zero"], f"{name}Trim")
    _progress(progress, f"{name} bottom edge trimmed")

    # Top end: horizontal at the top tread's top, vertical cut, horizontal return.
    _sector_cut(model, band, p_end[0] / radius, g["phi_end"] + 0.02, p_end[1], p_end[1] + 20.0, f"{name}TopFlat")
    _sector_cut(model, band, p2[0] / radius, g["phi_end"] + 0.02, -200.0, 200.0, f"{name}TopCut")
    _sector_cut(model, band, trim_phi, g["phi_end"] + 0.02, p3[1] - 20.0, p3[1], f"{name}TopReturn")
    # Bottom end: vertical cut, then the foot, stopping where it meets the 9 in line.
    _sector_cut(model, band, -0.03, p4[0] / radius, -200.0, 200.0, f"{name}BotCut")
    _sector_cut(model, band, -0.03, foot_phi, -200.0, l3_end[1], f"{name}BotFlat")
    _progress(progress, f"{name} ends formed")
    _rebuild(model)
    hole_ok = _end_holes(model, axis, dev, g["r_mid"], name)
    _progress(progress, f"{name} end holes {'cut' if hole_ok else 'missed'}")


def _helix(model, radius_in: float, height_in: float, revolutions: float, name: str):
    """Helix on the Top plane, starting at +Z and climbing toward -X."""
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
    model.InsertHelix(False, True, False, False, 1, height_in * _INCH, 0.0, float(revolutions), 0.0, 0.0)
    return _rename_new(model, before, f"{name}Helix", "helix")


def _sweep(model, helix, r_in: float, r_out: float, y_bottom: float, y_top: float, name: str) -> None:
    right = _plane(model, "Right")
    before = _names(model)
    _open_sketch(model, right)
    # Right-plane sketch: +X is world -Z, +Y is world +Y.
    if not _corner_rect(model, -r_out, y_bottom, -r_in, y_top):
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


def _cut_sweep(model, helix_spec, band: tuple[float, float], y_bottom: float, y_top: float, name: str) -> None:
    """Helical cut: a Right-plane rectangle swept along a trim helix through the
    plate band. The swept cut on this SolidWorks is intermittent, so each attempt
    rebuilds and rebuilds the helix and profile fresh before trying the call.
    """
    r_mid, height_in, revolutions = helix_spec
    # 19-arg InsertCutSwept4 (feature-scope booleans at the tail) removes the
    # bottom strip along the helix on this SolidWorks.
    methods = (
        ("InsertCutSwept4", (False, True, 0, False, False, 0, 0, False, 0, 0, 0, 0, True, True, 0, True, True, True, False)),
        ("InsertCutSwept4", (False, False, 0, False, False, 0, 0, False, 0, 0, 0, 0, True, True, 0, True, True, True, False)),
        ("InsertCutSwept3", (False, False, 0, False, False, 0, 0, False, 0.0, 0.0, 0, True, True, True, 0.0, True)),
    )
    errors: list[str] = []
    for attempt in range(6):
        _delete_named(model, (f"{name}Prof", f"{name}Helix", f"{name}HelixSk"))
        _rebuild(model)
        helix = _helix(model, r_mid, height_in, revolutions, f"{name}Helix")
        right = _plane(model, "Right")
        before = _names(model)
        _open_sketch(model, right)
        if not _corner_rect(model, -band[1], y_bottom, -band[0], y_top):
            _recover(model)
            errors.append(f"attempt {attempt}: profile failed")
            continue
        _close_sketch(model)
        profile = _rename_new(model, before, f"{name}Prof", "trim profile")
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
            return
    raise SolidWorksError(f"{name}: bottom edge trim failed ({'; '.join(errors[-4:]) or 'no sweep-cut method'}).")


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


def _corner_rect(model, x0: float, y0: float, x1: float, y1: float) -> bool:
    """Right-plane corner rectangle in inches. Retry through AddToDB when the
    first call returns nothing (flaky right after a helix)."""
    sketch = model.SketchManager
    for _ in range(3):
        result = None
        with contextlib.suppress(Exception):
            result = sketch.CreateCornerRectangle(x0 * _INCH, y0 * _INCH, 0.0, x1 * _INCH, y1 * _INCH, 0.0)
        if result is not None:
            return True
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
    return False


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


def _end_holes(model, axis, dev: DevelopedStringer, r_mid: float, name: str) -> bool:
    """Two holes at each end, on a plane tangent to the plate at that end.

    Inner stringer: 13/16 round. Outer stringer: 1-5/8 horizontal slots.
    """
    radius = dev.radius_in
    ok = True
    for label, pair in (("Top", dev.end_holes[:2]), ("Bot", dev.end_holes[2:])):
        psi = sum(x for x, _y in pair) / len(pair) / radius
        plane = _tangent_plane(model, axis, psi, r_mid, f"{name}{label}Holes")
        before = _names(model)
        _open_sketch(model, plane)
        try:
            sketch_obj = com_value(model.GetActiveSketch2)
            data = [float(v) for v in com_value(com_value(sketch_obj.ModelToSketchTransform).ArrayData)]
            for x_in, y_in in pair:
                phi = x_in / radius
                point = (-r_mid * math.sin(phi) * _INCH, y_in * _INCH, r_mid * math.cos(phi) * _INCH)
                sx, sy, _sz = _to_sketch(data, point)
                if dev.slotted:
                    _slot(model, sx, sy, SLOT_LENGTH_IN * _INCH, END_HOLE_RADIUS_IN * _INCH)
                elif _create_circle(model.SketchManager, sx, sy, END_HOLE_RADIUS_IN * _INCH) is None:
                    raise SolidWorksError(f"{name}: end hole circle failed.")
        except Exception:
            _recover(model)
            raise
        _close_sketch(model)
        sketch = _rename_new(model, before, f"{name}{label}HolesSk", "end holes sketch")
        feature = _cut_both_ways(model, sketch, THICKNESS_IN + 0.5)
        if feature is None:
            ok = False
            _delete_named(model, (f"{name}{label}HolesSk", f"{name}{label}HolesPln", f"{name}{label}HolesAng"))
            continue
        with contextlib.suppress(Exception):
            rename_feature(feature, f"{name}{label}Holes")
    return ok


def _slot(model, cx: float, cy: float, length: float, radius: float) -> None:
    """Horizontal stadium in sketch meters: two lines and two three-point end arcs."""
    sketch = model.SketchManager
    half = max(length / 2.0 - radius, 0.0)
    left, right = cx - half, cx + half
    top, bottom = cy + radius, cy - radius
    for (ax, ay), (bx, by) in (((left, top), (right, top)), ((right, bottom), (left, bottom))):
        if sketch.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
            raise SolidWorksError("Could not draw a slot line.")
    for (sx, sy), (ex, ey), (mx, my) in (
        ((right, top), (right, bottom), (right + radius, cy)),
        ((left, bottom), (left, top), (left - radius, cy)),
    ):
        if sketch.Create3PointArc(sx, sy, 0.0, ex, ey, 0.0, mx, my, 0.0) is None:
            raise SolidWorksError("Could not draw a slot arc.")


def _tangent_plane(model, axis, psi: float, distance_in: float, name: str):
    """Vertical plane tangent to the cylinder of ``distance_in`` at angle ``psi``.

    Fold the Front plane about the tank axis by ``psi`` (radians), then offset
    it; of the two offsets keep the one on the stringer's side of the tank.
    """
    front = _plane(model, "Front")
    before = _names(model)
    _clear_selection(model)
    if not front.Select2(False, 0):
        raise SolidWorksError("Could not select the Front Plane.")
    if not _select_feature(model, axis, "AXIS", mark=1, append=True):
        raise SolidWorksError("Could not select the tank axis.")
    model.CreatePlaneAtAngle(float(psi), False)
    _clear_selection(model)
    base = _rename_new(model, before, f"{name}Ang", "angle plane")
    # The tangent point on the stringer's side of the tank. The near offset
    # passes through it; the far offset sits about 2R away. Pick by distance,
    # not by the reported origin sign (which can be the far side).
    target = (-distance_in * math.sin(psi) * _INCH, 0.0, distance_in * math.cos(psi) * _INCH)
    best = None
    best_gap = None
    for flip in (False, True):
        before_off = _names(model)
        _clear_selection(model)
        base.Select2(False, 0)
        try:
            model.CreatePlaneAtOffset(distance_in * _INCH, flip)
        except Exception:
            continue
        _clear_selection(model)
        plane = None
        for feature in iter_features(model):
            current = _feature_name(feature)
            if current and current not in before_off:
                plane = feature
                break
        if plane is None:
            continue
        values = [float(v) for v in com_value(com_value(plane.GetSpecificFeature2).GetRefPlaneParams)]
        origin, normal = values[0:3], _unit(values[6:9])
        gap = abs(sum(normal[i] * (target[i] - origin[i]) for i in range(3))) / _INCH
        if best is None or gap < best_gap:
            if best is not None:
                _delete_named(model, (_feature_name(best),))
            best, best_gap = plane, gap
        else:
            _delete_named(model, (_feature_name(plane),))
    if best is None:
        raise SolidWorksError(f"{name}: tangent plane was not created.")
    rename_feature(best, f"{name}Pln")
    return find_feature(model, f"{name}Pln") or best


def _unit(vec):
    length = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / length for v in vec]


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


def _bolts(model, layout, place: TreadPlace, side: str, wall_in: float) -> bool:
    """Two bolts on this tread's side wall, cut perpendicular to that wall.

    The sketch sits on the outside face of the tread end wall (the wall that
    faces the stringer). The holes are located from the tread front face in the
    side profile. One cut runs both ways: through the 1/2 in wall into the pan,
    and across the 1/16 in gap through the 3/8 in stringer.
    """
    name = f"EliteBolt{place.index:02d}{side}"
    # Settle the model first: a cut right after the previous feature can
    # silently remove nothing until the model is rebuilt.
    _rebuild(model)
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
