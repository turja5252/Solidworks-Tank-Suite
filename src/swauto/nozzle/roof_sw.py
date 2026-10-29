"""Put roof nozzles on the cone roof the Roof tab built.

Everything is built where it goes. The roof is opened for the pipe first, and every cut is scoped to the
one body it is for (the roof, the pad, a flange), so nothing over or under it is touched. A repad is a band
of the cone's outside, revolved round the tank axis and trimmed to the pad's plan outline. The neck is
turned about its own plumb axis, and the bolt holes straddle the radial line through it.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.nozzle.nozzle_sw import (
    _SWBODYINTERSECT,
    _body_with_feature,
    _centerline,
    _close_sketch,
    _delete_feature,
    _drew,
    _extrude_both,
    _extrude_cut_both,
    _hide_sketch,
    _latest,
    _offset_selected,
    _open_on,
    _revolve,
    _safe,
    _swallow,
    _to_sketch,
)
from swauto.nozzle.roof_place import (
    RoofPlacement,
    outside_y,
    pad_reach,
    pad_thickness_vertical,
    place_on_roof,
    slope,
    tombstone_corners,
)
from swauto.nozzle.roof_spec import RoofNozzle
from swauto.nozzle.shape import (
    blind_loop,
    blind_seat_z,
    bolt_centers,
    gasket_loop,
    inside_flange_loop,
    inside_stations,
    outer_end_z,
    slip_on_loops,
    stations,
    weld_neck_loop,
)
from swauto.params import rebuild, rename_feature
from swauto.parts import select_plane
from swauto.tank.roof import RoofSpec, cone_profile_in
from swauto.tank.roof_sw import ROOF_NAME, _revolve_profile

PREFIX = "EliteRoofNozzle"  # starts like the roof's own features, so rebuilding the roof takes these with it
ROOF_BODY = "Roof"
_INCH = 0.0254


def add_roof_nozzles(model, roof: RoofSpec, nozzles: list[RoofNozzle], progress=None) -> str:
    """Rebuild every roof nozzle on ``model``, the part with the Roof tab's cone. Earlier ones go first."""
    if model is None:
        raise SolidWorksError("Build the roof on the Roof tab first.")
    if not nozzles:
        raise SolidWorksError("Add a roof nozzle to the list first.")
    if find_feature(model, ROOF_NAME) is None:
        raise SolidWorksError(
            "This part has no roof. Build it on the Roof tab first, into the tank shell part."
        )
    placed = [place_on_roof(nozzle, roof) for nozzle in nozzles]  # every row checked before anything is built
    _delete_prefixed(model)
    rebuild(model)
    _check_roof(model, roof)
    for spot in placed:
        _say(progress, f"Roof nozzle {spot.nozzle.mark}...")
        _build_one(model, spot)
    rebuild(model)
    # A cut names the body it cuts after itself. Name the roof again; SolidWorks will not give a body the
    # name of a feature (it keeps the cut's name when told "EliteRoof"), so it is "Roof".
    roof_body = _body_with_feature(model, ROOF_NAME)
    if roof_body is not None:
        with _swallow():
            roof_body.Name = ROOF_BODY
    return "On the roof: " + ", ".join(spot.nozzle.mark for spot in placed) + "."


def _build_one(model, placed: RoofPlacement) -> None:
    base = f"{PREFIX}{_safe(placed.nozzle.mark)}"
    try:
        level = _level_plane(model, placed.surface_in, f"{base}Level")
        _roof_hole(model, placed, level, base)
        if placed.repad is not None:
            _repad(model, placed, level, base)
        _turned(model, placed, base)
        _bolt_holes(model, placed, base)
        _hide_plane(model, level)
        rebuild(model)
        _name_bodies(model, placed, base)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"{placed.nozzle.mark} failed: {format_com_error(exc)}") from exc


# ---------------------------------------------------------------- the roof and the pad


def _check_roof(model, roof: RoofSpec) -> None:
    """The cone in the part is the one on the Roof tab: its top and its eave are where the tab puts them."""
    body = _body_with_feature(model, ROOF_NAME)
    if body is None:
        raise SolidWorksError("Could not find the roof's body in this part.")
    try:
        box = [float(v) / _INCH for v in body.GetBodyBox()]
    except Exception as exc:
        raise SolidWorksError(f"Could not read the roof's size ({format_com_error(exc)}).") from exc
    profile = cone_profile_in(roof)
    top = max(y for _r, y in profile)
    eave = max(r for r, _y in profile)
    if abs(box[4] - top) > 0.05 or abs(max(abs(box[0]), abs(box[3])) - eave) > 0.05:
        raise SolidWorksError(
            "The roof in SolidWorks is not the one on the Roof tab (its top or its eave is elsewhere). "
            "Build the roof again on the Roof tab, then build the roof nozzles."
        )


def _roof_hole(model, placed: RoofPlacement, level, base: str) -> None:
    """The pipe's hole through the roof plate, and nothing else."""
    name = f"{base}Hole"
    roof = _body_with_feature(model, ROOF_NAME)
    before = _volume(roof)
    sketch = _circle_sketch(model, level, placed, placed.pipe.outside_diameter_in / 2.0, name)
    reach = placed.roof.thickness_in * 2.0 + slope(placed.roof) * placed.pipe.outside_diameter_in + 1.0
    _extrude_cut_both(model, sketch, reach * _INCH, reach * _INCH, name, ROOF_NAME)
    _hide_sketch(model, f"{name}Sk")
    rebuild(model)
    after = _volume(_body_with_feature(model, ROOF_NAME))
    if before > 0.0 and after > before - 1e-9:
        raise SolidWorksError(f"{placed.nozzle.mark}: the hole missed the roof plate.")


def _repad(model, placed: RoofPlacement, level, base: str) -> None:
    """A band of the cone's outside the pad's thickness, square to the roof, all the way round, trimmed to
    the pad's plan outline, then opened for the pipe."""
    roof = placed.roof
    pad = placed.repad
    inner, outer = pad_reach(placed)
    inner, outer = max(0.0, inner - 0.5), outer + 0.5
    m = slope(roof)
    k = math.hypot(1.0, m)
    thick = pad.thickness_in
    low_in, low_out = outside_y(roof, inner), outside_y(roof, outer)
    top_out = (outer + thick * m / k, low_out + thick / k)
    if inner <= 1e-9:
        # Across the apex the band closes on the axis: its top meets the axis a pad's height over the roof.
        profile = ((0.0, low_in), (outer, low_out), top_out, (0.0, low_in + thick * k))
    else:
        profile = ((inner, low_in), (outer, low_out), top_out, (inner + thick * m / k, low_in + thick / k))
    _revolve_profile(model, profile, f"{base}BandSk", f"{base}Band")
    keep = f"{base}Keep"
    sketch = _outline_sketch(model, level, placed, keep)
    reach = max(low_in + thick * k - placed.surface_in, placed.surface_in - low_out) + 1.0
    _extrude_both(model, sketch, reach * _INCH, reach * _INCH, keep)
    _hide_sketch(model, f"{keep}Sk")
    _intersect(model, f"{base}Band", keep, f"{base}Repad", placed.nozzle.mark)
    hole = f"{base}PadHole"
    radius = max(pad.inner_diameter_in, placed.pipe.outside_diameter_in) / 2.0
    sketch = _circle_sketch(model, level, placed, radius, hole)
    reach = pad_thickness_vertical(placed) + m * 2.0 * radius + 1.0
    _extrude_cut_both(model, sketch, reach * _INCH, reach * _INCH, hole, f"{base}Repad")
    _hide_sketch(model, f"{hole}Sk")


def _intersect(model, band_name: str, keep_name: str, result: str, mark: str) -> None:
    """Common of the band and the outline (InsertCombineFeature, intersect). SW 2013 takes the two bodies
    selected with mark 2 and no main body, as for the shell's pads."""
    rebuild(model)
    band = _body_with_feature(model, band_name)
    keep = _body_with_feature(model, keep_name)
    if band is None or keep is None:
        raise SolidWorksError(f"{mark}: the repad pieces were not made.")
    model.ClearSelection2(True)
    data = model.SelectionManager.CreateSelectData
    data.Mark = 2
    if not (band.Select2(False, data) and keep.Select2(True, data)):
        raise SolidWorksError(f"{mark}: could not select the repad pieces.")
    try:
        import pythoncom
        from win32com.client import VARIANT

        no_tools = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [])
        combined = model.FeatureManager.InsertCombineFeature(_SWBODYINTERSECT, com_nothing(), no_tools)
    except Exception as exc:
        raise SolidWorksError(f"{mark}: could not trim the repad to the roof ({format_com_error(exc)}).") from exc
    if combined is None:
        raise SolidWorksError(f"{mark}: could not trim the repad to the roof.")
    rename_feature(combined, result)


# ---------------------------------------------------------------- the turned pieces and the bolts


def _turned(model, placed: RoofPlacement, base: str) -> None:
    """Neck and flange (or pipe and slip-on), gasket, blind and inside flange, each turned in place."""
    section = _section_plane(model, placed.plan_in[1], f"{base}Section")
    loops = []
    if placed.nozzle.kind == "so":
        pipe_loop, flange_loop = slip_on_loops(placed)
        loops += [(pipe_loop, "Pipe"), (flange_loop, "Flange")]
    else:
        loops.append((weld_neck_loop(placed), "Neck"))
    for loop, piece in ((gasket_loop(placed), "Gasket"), (blind_loop(placed), "Blind"),
                        (inside_flange_loop(placed), "InsideFlange")):
        if loop is not None:
            loops.append((loop, piece))
    for loop, piece in loops:
        _turn(model, placed, section, loop, f"{base}{piece}")
    if section is not None:
        _hide_plane(model, section)


def _turn(model, placed: RoofPlacement, plane, loop, name: str) -> None:
    """Revolve a closed (z, radius) loop about the nozzle's plumb axis, sketched on a plane through it."""
    px, pz = placed.plan_in
    lift = placed.surface_in
    _open_sketch_on(model, plane)
    to_sketch = _sketch_mapper(model, name)
    sketch = model.SketchManager
    z0 = min(z for z, _r in loop) - 1.0
    z1 = max(z for z, _r in loop) + 1.0
    a = to_sketch((px, lift + z0, pz))
    b = to_sketch((px, lift + z1, pz))
    if not _drew(model, lambda: _centerline(sketch, a[0], a[1], b[0], b[1])):
        _close_sketch(model)
        raise SolidWorksError(f"{name}: could not draw the nozzle axis.")
    for index, (z, radius) in enumerate(loop):
        nz, nr = loop[(index + 1) % len(loop)]
        s = to_sketch((px + radius, lift + z, pz))
        e = to_sketch((px + nr, lift + nz, pz))
        if math.hypot(e[0] - s[0], e[1] - s[1]) < 1e-9:
            continue

        def side(s=s, e=e):
            return sketch.CreateLine(s[0], s[1], 0.0, e[0], e[1], 0.0)

        if not _drew(model, side):
            _close_sketch(model)
            raise SolidWorksError(f"{name}: the turned profile did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    if not feature.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the profile.")
    try:
        revolved = _revolve(model, 2.0 * math.pi)
    except SolidWorksError:
        # SW 2013 now and then turns down a good profile; a rebuild and a second try takes it.
        rebuild(model)
        model.ClearSelection2(True)
        if not feature.Select2(False, 0):
            raise SolidWorksError(f"{name}: could not select the profile.") from None
        revolved = _revolve(model, 2.0 * math.pi)
    rename_feature(revolved, name)
    _hide_sketch(model, f"{name}Sk")


def _bolt_holes(model, placed: RoofPlacement, base: str) -> None:
    """Each flange's holes, cut through that flange only, from a level plane half way through it."""
    spot = stations(placed)
    main = f"{base}{'Flange' if placed.nozzle.kind == 'so' else 'Neck'}"
    cuts = [(spot.back_z, spot.face_z, main, f"{base}Bolts")]
    if placed.nozzle.blind:
        cuts.append((blind_seat_z(placed), outer_end_z(placed), f"{base}Blind", f"{base}BlindBolts"))
    inside = inside_stations(placed)
    if inside is not None:
        cuts.append((inside.face_z, inside.back_z, f"{base}InsideFlange", f"{base}InsideBolts"))
    fitting = placed.flange
    radius = fitting.bolt_hole_diameter_in / 2.0
    px, pz = placed.plan_in
    ux, uz = placed.outward
    nx, nz = -uz, ux
    for low, high, scope, name in cuts:
        middle = placed.surface_in + (low + high) / 2.0
        plane = _level_plane(model, middle, f"{name}Plane")
        _open_sketch_on(model, plane)
        to_sketch = _sketch_mapper(model, name)
        sketch = model.SketchManager
        for x, y in bolt_centers(fitting.bolt_circle_in, fitting.bolt_count):
            c = to_sketch((px + y * ux + x * nx, middle, pz + y * uz + x * nz))
            if not _drew(model, lambda c=c: sketch.CreateCircleByRadius(c[0], c[1], 0.0, radius * _INCH)):
                _close_sketch(model)
                raise SolidWorksError(f"{name}: a bolt hole did not draw.")
        _close_sketch(model)
        feature = _latest(model)
        rename_feature(feature, f"{name}Sk")
        target = _body_with_feature(model, scope)
        before = _volume(target)
        reach = (high - low) / 2.0 + 0.1
        _extrude_cut_both(model, feature, reach * _INCH, reach * _INCH, name, scope)
        _hide_sketch(model, f"{name}Sk")
        _hide_plane(model, plane)
        rebuild(model)
        if before > 0.0 and _volume(_body_with_feature(model, scope)) > before - 1e-9:
            raise SolidWorksError(f"{placed.nozzle.mark}: the bolt holes missed the {scope[len(base):].lower()}.")


def _name_bodies(model, placed: RoofPlacement, base: str) -> None:
    """Readable body names in the Solid Bodies folder, found by the feature that made each one."""
    nozzle = placed.nozzle
    parts = [("Neck", "Neck"), ("Pipe", "Pipe"), ("Flange", "Flange"), ("Repad", "Repad"),
             ("InsideFlange", "Inside flange"), ("Blind", "Blind")]
    if placed.gasket is not None:
        parts.append(("Gasket", f"Gasket - {placed.gasket.material}"))
    for feature, label in parts:
        body = _body_with_feature(model, f"{base}{feature}")
        if body is not None:
            with _swallow():
                body.Name = f"{nozzle.mark} {label}"


# ---------------------------------------------------------------- sketches and planes


def _circle_sketch(model, plane, placed: RoofPlacement, radius_in: float, name: str):
    px, pz = placed.plan_in
    _open_sketch_on(model, plane)
    to_sketch = _sketch_mapper(model, name)
    c = to_sketch((px, placed.surface_in, pz))
    if not _drew(model, lambda: model.SketchManager.CreateCircleByRadius(c[0], c[1], 0.0, radius_in * _INCH)):
        _close_sketch(model)
        raise SolidWorksError(f"{name}: the circle did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    return feature


def _outline_sketch(model, plane, placed: RoofPlacement, name: str):
    """The pad in plan: a circle, or the roof tombstone (half circle toward the center, sides out to the
    landing circle, closed along it)."""
    pad = placed.repad
    if pad.style != "tombstone":
        return _circle_sketch(model, plane, placed, pad.outer_diameter_in / 2.0, name)
    px, pz = placed.plan_in
    y = placed.surface_in
    half = pad.outer_diameter_in / 2.0
    ux, uz = placed.outward
    (foot_a, foot_b), (tan_a, tan_b) = tombstone_corners(placed)
    landing = placed.roof.landing_radius_in()
    angle = math.atan2(pz, px) if placed.radius_in > 1e-6 else math.atan2(uz, ux)
    rim_mid = (landing * math.cos(angle), landing * math.sin(angle))
    round_end = (px - half * ux, pz - half * uz)
    _open_sketch_on(model, plane)
    to_sketch = _sketch_mapper(model, name)
    manager = model.SketchManager
    pts = {key: to_sketch((p[0], y, p[1])) for key, p in
           (("ta", tan_a), ("tb", tan_b), ("fa", foot_a), ("fb", foot_b), ("rim", rim_mid), ("end", round_end))}

    def arc(a, b, mid):
        return manager.Create3PointArc(pts[a][0], pts[a][1], 0.0, pts[b][0], pts[b][1], 0.0,
                                       pts[mid][0], pts[mid][1], 0.0)

    def line(a, b):
        return manager.CreateLine(pts[a][0], pts[a][1], 0.0, pts[b][0], pts[b][1], 0.0)

    for draw in (lambda: arc("ta", "tb", "end"), lambda: line("tb", "fb"), lambda: arc("fb", "fa", "rim"),
                 lambda: line("fa", "ta")):
        if not _drew(model, draw):
            _close_sketch(model)
            raise SolidWorksError(f"{name}: the tombstone outline did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    return feature


def _sketch_mapper(model, name: str):
    """World inches to the open sketch's meters, from its ModelToSketchTransform."""
    try:
        transform = com_value(com_value(model.GetActiveSketch2).ModelToSketchTransform)
        data = [float(v) for v in com_value(transform.ArrayData)]
    except Exception as exc:
        _close_sketch(model)
        raise SolidWorksError(f"{name}: could not read the sketch plane ({format_com_error(exc)}).") from exc

    def to_sketch(point_in):
        x, y, _z = _to_sketch(data, tuple(v * _INCH for v in point_in))
        return (x, y)

    return to_sketch


def _open_sketch_on(model, plane) -> None:
    if plane is None:
        model.ClearSelection2(True)
        if not select_plane(model, "Front Plane"):
            raise SolidWorksError("Could not select the Front Plane.")
        sketch = model.SketchManager
        with _swallow():
            sketch.AddToDB = True
        with _swallow():
            sketch.DisplayWhenAdded = False
        sketch.InsertSketch(True)
        return
    _open_on(model, plane)


def _level_plane(model, y_in: float, name: str):
    """A plane level with the Top Plane, ``y_in`` up."""
    model.ClearSelection2(True)
    if not select_plane(model, "Top Plane"):
        raise SolidWorksError("Could not select the Top Plane.")
    return _offset_selected(model, y_in * _INCH, y_in < 0.0, name)


def _section_plane(model, z_in: float, name: str):
    """A plane square to Z through the nozzle axis: the Front Plane moved to its Z, or None for the Front
    Plane itself."""
    if abs(z_in) < 1e-6:
        return None
    model.ClearSelection2(True)
    if not select_plane(model, "Front Plane"):
        raise SolidWorksError("Could not select the Front Plane.")
    return _offset_selected(model, z_in * _INCH, z_in < 0.0, name)


def _hide_plane(model, plane) -> None:
    if plane is None:
        return
    model.ClearSelection2(True)
    with _swallow():
        if plane.Select2(False, 0):
            blank = model.BlankRefGeom
            blank() if callable(blank) else com_value(blank)
    model.ClearSelection2(True)


# ---------------------------------------------------------------- bookkeeping


def _volume(body) -> float:
    if body is None:
        return 0.0
    try:
        props = tuple(body.GetMassProperties(0))
    except Exception:
        return 0.0
    return float(props[3]) if len(props) > 3 else 0.0


def _delete_prefixed(model) -> None:
    named = [feature for feature in iter_features(model) if str(com_value(feature.Name) or "").startswith(PREFIX)]
    for feature in reversed(named):
        _delete_feature(model, feature)


def _say(progress, text: str) -> None:
    if progress is not None:
        with contextlib.suppress(Exception):
            progress(text)
