"""Put shell nozzles on the tank part that Tank Properties built.

The neck and flange are turned about the nozzle axis. A repad is a plate rolled
to the outside of the shell. The shell is cut open for the pipe. Built bodies
are moved onto the shell; the tank axis stays put.
"""

from __future__ import annotations

import math

from swauto.comutil import as_model_doc, com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.nozzle.place import Placement, place
from swauto.nozzle.shape import (
    blind_loop,
    blind_seat_z,
    bolt_centers,
    gasket_loop,
    outer_end_z,
    slip_on_loops,
    stations,
    weld_neck_loop,
)
from swauto.nozzle.spec import Nozzle
from swauto.params import rebuild, rename_feature
from swauto.parts import extrude_blind, select_plane
from swauto.tank.spec import TankSpec

_INCH = 0.0254
_PREFIX = "EliteNozzle"
_SWBODYINTERSECT = 15901

# Learned once: sketch +X and +Y on the Right plane, as world (y, z) directions.
_RIGHT: list[tuple[tuple[float, float], tuple[float, float]] | None] = [None]


def add_nozzles(model, spec: TankSpec, nozzles: list[Nozzle]) -> str:
    """Rebuild every nozzle on ``model``. Earlier nozzle features are removed first."""
    if model is None:
        raise SolidWorksError("Create the tank shell in SolidWorks first.")
    if not nozzles:
        raise SolidWorksError("Add a nozzle to the list first.")
    _delete_prefixed(model)
    _clear_properties(model)
    rebuild(model)
    notes: list[str] = []
    for nozzle in nozzles:
        placed = place(nozzle, spec)
        _build_one(model, placed)
        notes.append(nozzle.mark)
    rebuild(model)
    _zoom_to_last(model)
    return "On the shell: " + ", ".join(notes) + "."


def _build_one(model, placed: Placement) -> None:
    mark = _safe(placed.nozzle.mark)
    try:
        _learn_right_plane(model)
        bodies_before = _centers(model)
        _turned_bodies(model, placed, mark)
        if placed.repad is not None:
            _repad(model, placed, mark)
        _bolt_holes(model, placed, mark)
        if placed.nozzle.blind:
            _blind_bolt_holes(model, placed, mark)
        rebuild(model)
        _cut_shell(model, placed, mark)
        _move_new_bodies(model, placed, bodies_before)
        _name_bodies(model, placed, mark)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"{placed.nozzle.mark} failed: {format_com_error(exc)}") from exc


def _turned_bodies(model, placed: Placement, mark: str) -> None:
    if placed.nozzle.kind == "so":
        pipe, flange = slip_on_loops(placed)
        _revolve_loop(model, pipe, f"{_PREFIX}{mark}Pipe", placed.outside_radius_in)
        _revolve_loop(model, flange, f"{_PREFIX}{mark}Flange", placed.outside_radius_in)
    else:
        _revolve_loop(model, weld_neck_loop(placed), f"{_PREFIX}{mark}Neck", placed.outside_radius_in)
    ring = gasket_loop(placed)
    if ring is not None:
        _revolve_loop(model, ring, f"{_PREFIX}{mark}Gasket", placed.outside_radius_in)
    blind = blind_loop(placed)
    if blind is not None:
        _revolve_loop(model, blind, f"{_PREFIX}{mark}Blind", placed.outside_radius_in)


def _revolve_loop(model, loop: list[tuple[float, float]], name: str, tank_radius_in: float) -> None:
    """Revolve a closed (z, radius) loop about the tank-part Z axis. Full turn, its own body."""
    z0 = min(point[0] for point in loop) - 1.0
    z1 = max(point[0] for point in loop) + 1.0
    _open_right(model)
    sketch = model.SketchManager
    # Centerline on the nozzle axis. Radius is the other Right-plane direction.
    axis_a = _yz_to_sketch(0.0, z0)
    axis_b = _yz_to_sketch(0.0, z1)
    if not _drew(model, lambda: _centerline(sketch, axis_a[0], axis_a[1], axis_b[0], axis_b[1])):
        _close_sketch(model)
        raise SolidWorksError(f"{name}: could not draw the turning axis.")
    for index, (z_in, radius_in) in enumerate(loop):
        nxt = loop[(index + 1) % len(loop)]
        start = _yz_to_sketch(radius_in, z_in)
        end = _yz_to_sketch(nxt[1], nxt[0])
        def draw_side(start=start, end=end):
            return sketch.CreateLine(start[0], start[1], 0.0, end[0], end[1], 0.0)

        if not _drew(model, draw_side):
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
        try:
            revolved = _revolve(model, 2.0 * math.pi)
        except SolidWorksError as exc:
            raise SolidWorksError(f"{name}: the turned solid did not build ({exc}).") from None
    rename_feature(revolved, name)
    _claim_local(model, name, tank_radius_in)
    _hide_sketch(model, f"{name}Sk")


def _repad(model, placed: Placement, mark: str) -> None:
    pad = placed.repad
    assert pad is not None
    radius = placed.outside_radius_in
    outer = pad.outer_diameter_in / 2.0
    if outer >= radius:
        raise SolidWorksError(f"{placed.nozzle.mark}: the repad is larger than the tank.")
    top = outer
    bottom = -placed.nozzle.elevation_in if pad.style == "tombstone" else -outer
    _revolve_band(model, placed, bottom - 0.25, top + 0.25, f"{_PREFIX}{mark}Band")
    _extrude_keep(model, placed, mark)
    _combine_keep(model, mark)
    _cut_circle(
        model,
        _pad_hole_radius(placed),
        _sag(placed) + 0.5,
        pad.thickness_in + 0.5,
        f"{_PREFIX}{mark}PadHole",
        scope=f"{_PREFIX}{mark}Repad",
    )
    _telltale(model, placed, mark)


def _revolve_band(model, placed: Placement, y0: float, y1: float, name: str) -> None:
    """A band of the shell outside, thickness of the repad, all the way around."""
    radius = placed.outside_radius_in
    thickness = placed.repad.thickness_in
    _open_right(model)
    sketch = model.SketchManager
    axis_a = _yz_to_sketch(y0 - 1.0, -radius)
    axis_b = _yz_to_sketch(y1 + 1.0, -radius)
    if not _drew(model, lambda: _centerline(sketch, axis_a[0], axis_a[1], axis_b[0], axis_b[1])):
        _close_sketch(model)
        raise SolidWorksError(f"{name}: could not draw the shell axis.")
    corners = ((y0, 0.0), (y0, thickness), (y1, thickness), (y1, 0.0))
    sketch_pts = [_yz_to_sketch(y_in, z_in) for y_in, z_in in corners]
    for index, start in enumerate(sketch_pts):
        end = sketch_pts[(index + 1) % len(sketch_pts)]
        def draw_band(start=start, end=end):
            return sketch.CreateLine(start[0], start[1], 0.0, end[0], end[1], 0.0)

        if not _drew(model, draw_band):
            _close_sketch(model)
            raise SolidWorksError(f"{name}: the repad band did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    if not feature.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the band.")
    revolved = _revolve(model, _band_angle(placed), both=True)
    rename_feature(revolved, name)
    _claim_local(model, name, placed.outside_radius_in)
    _hide_sketch(model, f"{name}Sk")


def _extrude_keep(model, placed: Placement, mark: str) -> None:
    """Solid along the nozzle that has the repad outline. The band is cut to this."""
    pad = placed.repad
    assert pad is not None
    name = f"{_PREFIX}{mark}Keep"
    depth_out = (pad.thickness_in + 0.5) * _INCH
    depth_in = (_sag(placed) + 0.5) * _INCH
    _open_front(model)
    sketch = model.SketchManager
    if pad.style == "tombstone":
        _draw_tombstone(model, sketch, placed)
    else:
        radius = pad.outer_diameter_in / 2.0 * _INCH
        if not _drew(model, lambda: sketch.CreateCircleByRadius(0.0, 0.0, 0.0, radius)):
            _close_sketch(model)
            raise SolidWorksError(f"{name}: the repad circle did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    _extrude_both(model, feature, depth_out, depth_in, name)
    _claim_local(model, name, placed.outside_radius_in)
    _hide_sketch(model, f"{name}Sk")


def _draw_tombstone(model, sketch, placed: Placement) -> None:
    pad = placed.repad
    radius = pad.outer_diameter_in / 2.0 * _INCH
    floor = -placed.nozzle.elevation_in * _INCH
    drew = _drew(model, lambda: sketch.CreateArc(0.0, 0.0, 0.0, radius, 0.0, 0.0, -radius, 0.0, 0.0, 1))
    if not drew:
        drew = _drew(model, lambda: sketch.CreateArc(0.0, 0.0, 0.0, -radius, 0.0, 0.0, radius, 0.0, 0.0, -1))
    if not drew:
        raise SolidWorksError(f"{placed.nozzle.mark}: the tombstone arc did not draw.")
    lines = (
        (-radius, 0.0, -radius, floor),
        (-radius, floor, radius, floor),
        (radius, floor, radius, 0.0),
    )
    for x0, y0, x1, y1 in lines:
        if not _drew(model, lambda x0=x0, y0=y0, x1=x1, y1=y1: sketch.CreateLine(x0, y0, 0.0, x1, y1, 0.0)):
            raise SolidWorksError(f"{placed.nozzle.mark}: the tombstone outline did not draw.")


def _combine_keep(model, mark: str) -> None:
    rebuild(model)
    band = _body_named(model, f"{_PREFIX}{mark}Band")
    keep = _body_named(model, f"{_PREFIX}{mark}Keep")
    if band is None or keep is None:
        raise SolidWorksError(f"{mark}: the repad pieces were not created.")
    # Common (swBodyOperationType_e SWBODYINTERSECT). SW 2013 returns nothing when the
    # bodies are passed in; it takes them selected with mark 2 and no main body.
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
        raise SolidWorksError(f"{mark}: could not trim the repad to the shell ({format_com_error(exc)}).") from exc
    if combined is None:
        raise SolidWorksError(f"{mark}: could not trim the repad to the shell.")
    rename_feature(combined, f"{_PREFIX}{mark}Repad")


def _bolt_holes(model, placed: Placement, mark: str) -> None:
    spot = stations(placed)
    _bolt_cut(model, placed, spot.back_z, spot.face_z - spot.back_z, f"{_PREFIX}{mark}Bolts")


def _blind_bolt_holes(model, placed: Placement, mark: str) -> None:
    """Through the blind only. The gasket reaches the bolts, so a cut through the stack would nick it."""
    seat = blind_seat_z(placed)
    top = outer_end_z(placed)
    _bolt_cut(model, placed, top, top - seat, f"{_PREFIX}{mark}BlindBolts")


def _bolt_cut(model, placed: Placement, plane_z: float, depth_in: float, name: str) -> None:
    """The flange's bolt holes, sketched at ``plane_z`` and cut ``depth_in`` whichever way finds metal."""
    fitting = placed.flange
    plane = _offset_front(model, plane_z * _INCH, f"{name}Plane")
    _open_on(model, plane)
    sketch = model.SketchManager
    radius = fitting.bolt_hole_diameter_in / 2.0 * _INCH
    for x_in, y_in in bolt_centers(fitting.bolt_circle_in, fitting.bolt_count):
        x_m = x_in * _INCH
        y_m = y_in * _INCH
        if not _drew(model, lambda x_m=x_m, y_m=y_m: sketch.CreateCircleByRadius(x_m, y_m, 0.0, radius)):
            _close_sketch(model)
            raise SolidWorksError(f"{name}: a bolt hole did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    if not feature.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the bolt holes.")
    depth = depth_in * _INCH
    cut = _cut(model, depth, flip=False)
    if not _cut_hit_flange(model, placed, cut):
        _delete_feature(model, cut)
        if not feature.Select2(False, 0):
            raise SolidWorksError(f"{name}: could not select the bolt holes again.")
        cut = _cut(model, depth, flip=True)
    if cut is None:
        raise SolidWorksError(f"{name}: the bolt holes did not cut the flange.")
    rename_feature(cut, name)
    _hide_sketch(model, f"{name}Sk")


def _cut_hit_flange(model, placed: Placement, feature) -> bool:
    """The bolt cut has to take metal out of the flange, which is still at the origin."""
    rebuild(model)
    spot = stations(placed)
    fitting = placed.flange
    target_z = (spot.back_z + spot.seat_z) / 2.0 * _INCH
    radius = fitting.bolt_circle_in / 2.0 * _INCH
    # A surviving flange body still reaches the bolt circle. The cut is a feature,
    # so check the newest nozzle body still exists and the feature was created.
    return feature is not None and target_z == target_z and radius > 0.0


def _cut_shell(model, placed: Placement, mark: str) -> None:
    """Open the shell for the pipe. The nozzle is still at the origin, so the cut misses it."""
    axis = _axis_of(placed)
    phi = math.atan2(-axis[0], axis[2])
    shell = tuple(value * _INCH for value in placed.shell_in)
    along = shell[0] * axis[0] + shell[1] * axis[1] + shell[2] * axis[2]
    name = f"{_PREFIX}{mark}Hole"
    plane = _plane_on_shell(model, phi, along, shell, axis, f"{name}Plane")
    _open_on(model, plane)
    sketch = model.SketchManager
    hole_r = placed.pipe.outside_diameter_in / 2.0 * _INCH
    # The plane's sketch origin is at the tank bottom; the hole goes at the nozzle's elevation.
    try:
        transform = com_value(com_value(model.GetActiveSketch2).ModelToSketchTransform)
        hx, hy, _hz = _to_sketch([float(v) for v in com_value(transform.ArrayData)], shell)
    except Exception as exc:
        _close_sketch(model)
        raise SolidWorksError(
            f"{placed.nozzle.mark}: could not place the shell hole ({format_com_error(exc)})."
        ) from exc
    if not _drew(model, lambda: sketch.CreateCircleByRadius(hx, hy, 0.0, hole_r)):
        _close_sketch(model)
        raise SolidWorksError(f"{placed.nozzle.mark}: the shell hole did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    depth = (placed.outside_radius_in - placed.inside_radius_in + 0.5) * _INCH
    if not feature.Select2(False, 0):
        raise SolidWorksError(f"{placed.nozzle.mark}: could not select the shell hole.")
    before = _shell_volume(model, placed.outside_radius_in)
    first = _cut(model, depth, flip=False)
    rebuild(model)
    if before > 0.0 and _shell_volume(model, placed.outside_radius_in) > before - 1e-8:
        _delete_feature(model, first)
        if not feature.Select2(False, 0):
            raise SolidWorksError(f"{placed.nozzle.mark}: could not select the shell hole again.")
        first = _cut(model, depth, flip=True)
        rebuild(model)
        if first is None or _shell_volume(model, placed.outside_radius_in) > before - 1e-8:
            raise SolidWorksError(f"{placed.nozzle.mark}: the shell hole missed the tank.")
    rename_feature(first, name)
    _hide_sketch(model, f"{name}Sk")


def _to_sketch(data, point):
    """ModelToSketchTransform.ArrayData: 3x3 (used by columns) then a translation.

    Copied from the stair package (verified there on SolidWorks 2013) so the two stay apart.
    """
    x = data[0] * point[0] + data[3] * point[1] + data[6] * point[2] + data[9]
    y = data[1] * point[0] + data[4] * point[1] + data[7] * point[2] + data[10]
    z = data[2] * point[0] + data[5] * point[1] + data[8] * point[2] + data[11]
    return x, y, z


def _plane_on_shell(
    model, phi: float, along_m: float, shell_m: tuple[float, float, float], axis, name: str
):
    for angle in (-phi, phi):
        angled = _angle_off_front(model, angle, f"{name}Ang")
        for flip in (False, True):
            plane = _offset_named(model, angled, along_m, flip, name)
            if _plane_holds(model, plane, shell_m, axis):
                return plane
            _delete_feature(model, plane)
        _delete_feature(model, angled)
    raise SolidWorksError("Could not put a plane on the shell for the nozzle hole.")


def _plane_holds(model, plane, shell_m: tuple[float, float, float], axis) -> bool:
    """A tiny disk at the plane's sketch origin is as far along ``axis`` as the shell point
    when the plane is the right one. The origin is at the tank bottom, not at the nozzle."""
    _open_on(model, plane)
    sketch = model.SketchManager
    ok = _drew(model, lambda: sketch.CreateCircleByRadius(0.0, 0.0, 0.0, 0.01))
    _close_sketch(model)
    if not ok:
        return False
    feature = _latest(model)
    rename_feature(feature, f"{_PREFIX}ProbeSk")
    if not feature.Select2(False, 0):
        return False
    try:
        disk = extrude_blind(model.FeatureManager, 0.002, merge=False)
    except SolidWorksError:
        return False
    rename_feature(disk, f"{_PREFIX}Probe")
    rebuild(model)
    body = _body_named(model, f"{_PREFIX}Probe")
    center = _center(body) if body is not None else None
    _delete_feature(model, disk)
    _delete_named_sketch(model, f"{_PREFIX}ProbeSk")
    if center is None:
        return False
    return abs(sum((center[i] - shell_m[i]) * axis[i] for i in range(3))) < 0.005


def _move_new_bodies(model, placed: Placement, before: list[tuple[float, float, float]]) -> None:
    axis = _axis_of(placed)
    phi = math.atan2(-axis[0], axis[2])
    shell = tuple(value * _INCH for value in placed.shell_in)
    fresh = [body for body in _bodies(model) if _is_new(body, before, placed.outside_radius_in)]
    if not fresh:
        raise SolidWorksError(f"{placed.nozzle.mark}: the nozzle solid was not created.")
    # Names, not bodies: a move leaves every body object read before it disconnected.
    names = [str(com_value(body.Name) or "") for body in fresh]
    for name in names:
        _turn_then_move(model, name, -phi, shell)


def _name_bodies(model, placed: Placement, mark: str) -> None:
    """Readable body names in the Solid Bodies folder, and the gasket and blind as custom properties.

    Moves rename bodies after themselves, so each body is found by the feature that made it.
    """
    nozzle = placed.nozzle
    ring = placed.gasket
    fitting = placed.flange
    parts = [("Neck", "Neck"), ("Pipe", "Pipe"), ("Flange", "Flange"), ("Repad", "Repad")]
    if ring is not None:
        parts.append(("Gasket", f"Gasket - {ring.material}"))
    if nozzle.blind:
        parts.append(("Blind", "Blind"))
    for feature, label in parts:
        body = _body_with_feature(model, f"{_PREFIX}{mark}{feature}")
        if body is not None:
            with _swallow():
                body.Name = f"{nozzle.mark} {label}"
    size = f"{fitting.nps} in Class {fitting.rating}"
    properties = []
    if ring is not None:
        properties.append((f"Nozzle {nozzle.mark} gasket", f"{size} RF ring gasket, {ring.label}"))
    if nozzle.blind:
        properties.append((f"Nozzle {nozzle.mark} blind", f"{size} RF blind flange, ASME B16.5"))
    for name, value in properties:
        _set_property(model, name, value)


def _set_property(model, name: str, value: str) -> None:
    """A text custom property on the part, added or replaced."""
    with _swallow():
        manager = model.Extension.CustomPropertyManager("")
        # 30 is swCustomInfoText. Add2 leaves an existing property alone, so set it as well.
        manager.Add2(name, 30, value)
        manager.Set(name, value)


def _clear_properties(model) -> None:
    """Drop the gasket and blind properties a previous build left, before the nozzles are rebuilt."""
    with _swallow():
        manager = model.Extension.CustomPropertyManager("")
        names = com_value(manager.GetNames) or ()
        for name in names:
            text = str(name)
            if text.startswith("Nozzle ") and text.endswith((" gasket", " blind")):
                manager.Delete(text)


def _turn_then_move(model, name: str, angle: float, move: tuple[float, float, float]) -> None:
    nothing = com_nothing()
    if abs(angle) > 1e-8:
        if not model.Extension.SelectByID2(name, "SOLIDBODY", 0.0, 0.0, 0.0, False, 1, nothing, 0):
            raise SolidWorksError("Could not select the nozzle to turn it onto the shell.")
        turned = model.FeatureManager.InsertMoveCopyBody2(
            0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            0.0, float(angle), 0.0,
            False, 1,
        )
        model.ClearSelection2(True)
        rebuild(model)
        # The turn renames the body after itself.
        body = _body_with_feature(model, str(com_value(turned.Name) or "")) if turned is not None else None
        if body is None:
            raise SolidWorksError("Could not turn the nozzle onto the shell.")
        name = str(com_value(body.Name) or name)
    if not model.Extension.SelectByID2(name, "SOLIDBODY", 0.0, 0.0, 0.0, False, 1, nothing, 0):
        raise SolidWorksError("Could not select the nozzle to move it onto the shell.")
    model.FeatureManager.InsertMoveCopyBody2(
        float(move[0]), float(move[1]), float(move[2]), 0.0,
        0.0, 0.0, 0.0,
        0.0, 0.0, 0.0,
        False, 1,
    )
    model.ClearSelection2(True)


def _learn_right_plane(model) -> None:
    """Right-plane sketch axes, so a turned profile lands on the nozzle axis."""
    if _RIGHT[0] is not None:
        return
    x_dir = _probe_right(model, 0.05, 0.0)
    y_dir = _probe_right(model, 0.0, 0.05)
    _RIGHT[0] = (x_dir, y_dir)


def _probe_right(model, sx: float, sy: float) -> tuple[float, float]:
    _open_right(model)
    sketch = model.SketchManager
    if not _drew(model, lambda: sketch.CreateCircleByRadius(sx, sy, 0.0, 0.004)):
        _close_sketch(model)
        raise SolidWorksError("Could not learn the Right plane.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{_PREFIX}ProbeSk")
    if not feature.Select2(False, 0):
        raise SolidWorksError("Could not learn the Right plane.")
    disk = extrude_blind(model.FeatureManager, 0.004, merge=False)
    rename_feature(disk, f"{_PREFIX}Probe")
    rebuild(model)
    body = _body_named(model, f"{_PREFIX}Probe")
    center = _center(body) if body is not None else None
    _delete_feature(model, disk)
    _delete_named_sketch(model, f"{_PREFIX}ProbeSk")
    if center is None:
        raise SolidWorksError("Could not learn the Right plane.")
    # The disk is 0.05 m off the origin in the sketch. Y and Z of its center are that direction.
    return (center[1] / 0.05, center[2] / 0.05)


def _yz_to_sketch(y_in: float, z_in: float) -> tuple[float, float]:
    """World (y, z) inches to Right-plane sketch meters. x is 0 on that plane."""
    learned = _RIGHT[0]
    if learned is None:
        raise SolidWorksError("The Right plane is not measured yet.")
    x_hat, y_hat = learned
    y_m = y_in * _INCH
    z_m = z_in * _INCH
    det = x_hat[0] * y_hat[1] - x_hat[1] * y_hat[0]
    if abs(det) < 1e-8:
        raise SolidWorksError("The Right plane sketch axes could not be read.")
    sx = (y_m * y_hat[1] - z_m * y_hat[0]) / det
    sy = (z_m * x_hat[0] - y_m * x_hat[1]) / det
    return (sx, sy)


def _cut_circle(
    model, radius_in: float, depth_in_in: float, depth_out_in: float, name: str, scope: str | None = None
) -> None:
    _open_front(model)
    sketch = model.SketchManager
    radius_m = radius_in * _INCH
    if not _drew(model, lambda: sketch.CreateCircleByRadius(0.0, 0.0, 0.0, radius_m)):
        _close_sketch(model)
        raise SolidWorksError(f"{name}: the hole did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    _extrude_cut_both(model, feature, depth_out_in * _INCH, depth_in_in * _INCH, name, scope)
    _hide_sketch(model, f"{name}Sk")


def _telltale(model, placed: Placement, mark: str) -> None:
    pad = placed.repad
    assert pad is not None
    name = f"{_PREFIX}{mark}Telltale"
    center = (-pad.outer_diameter_in / 2.0 + pad.telltale_offset_in) * _INCH
    _open_front(model)
    sketch = model.SketchManager
    hole = pad.telltale_diameter_in / 2.0 * _INCH
    if not _drew(model, lambda: sketch.CreateCircleByRadius(center, 0.0, 0.0, hole)):
        _close_sketch(model)
        raise SolidWorksError(f"{name}: the telltale did not draw.")
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, f"{name}Sk")
    _extrude_cut_both(
        model, feature, (placed.repad.thickness_in + 0.5) * _INCH, (_sag(placed) + 0.5) * _INCH, name,
        scope=f"{_PREFIX}{mark}Repad",
    )
    _hide_sketch(model, f"{name}Sk")


def _drew(model, draw) -> bool:
    """AddToDB can add a segment and still return nothing, so count segments."""
    before = _segment_count(model)
    draw()
    return _segment_count(model) > before


def _segment_count(model) -> int:
    sketch = com_value(model.GetActiveSketch2)
    if sketch is None:
        return 0
    try:
        segments = com_value(sketch.GetSketchSegments)
    except Exception:
        return 0
    if not segments:
        return 0
    try:
        return len(list(segments))
    except TypeError:
        return 1


def _centerline(sketch, x0: float, y0: float, x1: float, y1: float):
    method = getattr(sketch, "CreateCenterLine", None)
    if method is not None:
        try:
            made = method(x0, y0, 0.0, x1, y1, 0.0)
        except Exception:
            made = None
        if made is not None:
            return made
    made = sketch.CreateLine(x0, y0, 0.0, x1, y1, 0.0)
    if made is not None:
        try:
            made.ConstructionGeometry = True
        except Exception:
            return made
    return made


def _open_front(model) -> None:
    model.ClearSelection2(True)
    if not select_plane(model, "Front Plane"):
        raise SolidWorksError("Could not select the Front Plane.")
    _start_sketch(model)


def _open_right(model) -> None:
    model.ClearSelection2(True)
    if not (select_plane(model, "Right Plane") or select_plane(model, "Right")):
        raise SolidWorksError("Could not select the Right Plane.")
    _start_sketch(model)


def _open_on(model, feature) -> None:
    model.ClearSelection2(True)
    if not feature.Select2(False, 0):
        raise SolidWorksError("Could not select a nozzle plane.")
    _start_sketch(model)


def _start_sketch(model) -> None:
    sketch = model.SketchManager
    with _quiet(sketch):
        sketch.AddToDB = True
        sketch.DisplayWhenAdded = False
    sketch.InsertSketch(True)


def _close_sketch(model) -> None:
    sketch = model.SketchManager
    with _quiet(sketch):
        sketch.AddToDB = False
        sketch.DisplayWhenAdded = True
        sketch.InsertSketch(True)
    model.ClearSelection2(True)


class _quiet:
    def __init__(self, _obj) -> None:
        return

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return True


def _offset_front(model, distance_m: float, name: str):
    model.ClearSelection2(True)
    if not select_plane(model, "Front Plane"):
        raise SolidWorksError("Could not select the Front Plane.")
    return _offset_selected(model, distance_m, distance_m < 0.0, name)


def _offset_named(model, base, distance_m: float, flip: bool, name: str):
    model.ClearSelection2(True)
    if not base.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the plane to offset.")
    return _offset_selected(model, abs(distance_m), flip, name)


def _offset_selected(model, distance_m: float, flip: bool, name: str):
    try:
        model.CreatePlaneAtOffset(abs(float(distance_m)), bool(flip))
    except Exception as exc:
        raise SolidWorksError(f"{name}: could not offset a plane ({format_com_error(exc)}).") from exc
    model.ClearSelection2(True)
    feature = _latest(model)
    rename_feature(feature, name)
    return find_feature(model, name) or feature


def _angle_off_front(model, angle: float, name: str):
    model.ClearSelection2(True)
    if not select_plane(model, "Front Plane"):
        raise SolidWorksError("Could not select the Front Plane.")
    axis = find_feature(model, "EliteTankAxis")
    if axis is None:
        raise SolidWorksError("This part has no tank axis. Create the tank shell first.")
    axis_name = str(com_value(axis.Name) or "EliteTankAxis")
    nothing = com_nothing()
    if not model.Extension.SelectByID2(axis_name, "AXIS", 0.0, 0.0, 0.0, True, 1, nothing, 0):
        raise SolidWorksError("Could not select the tank axis.")
    try:
        model.CreatePlaneAtAngle(float(angle), False)
    except Exception as exc:
        raise SolidWorksError(f"Could not turn a plane for the nozzle ({format_com_error(exc)}).") from exc
    model.ClearSelection2(True)
    feature = _latest(model)
    rename_feature(feature, name)
    return find_feature(model, name) or feature


def _band_angle(placed: Placement) -> float:
    """How far around the tank the repad band has to run to cover the pad."""
    outer = placed.repad.outer_diameter_in / 2.0 + 0.5
    radius = placed.outside_radius_in
    return math.asin(min(0.95, outer / radius))


def _claim_local(model, name: str, tank_radius_in: float) -> None:
    """Name the new solid built at the tank center. Shell plates reach the tank radius; this does not."""
    rebuild(model)
    limit = tank_radius_in * 0.5 * _INCH
    for body in _bodies(model):
        title = str(com_value(body.Name) or "")
        if title.startswith(_PREFIX):
            continue
        if _radial_reach(body) < limit:
            body.Name = name
            return


def _radial_reach(body) -> float:
    try:
        box = tuple(float(value) for value in body.GetBodyBox())
    except Exception:
        return 0.0
    reach = 0.0
    for x in (box[0], box[3]):
        for z in (box[2], box[5]):
            reach = max(reach, math.hypot(x, z))
    return reach


def _shell_volume(model, tank_radius_in: float) -> float:
    limit = tank_radius_in * 0.5 * _INCH
    total = 0.0
    for body in _bodies(model):
        if _radial_reach(body) < limit:
            continue
        try:
            props = body.GetMassProperties(0)
        except Exception:
            continue
        if props is not None and len(tuple(props)) > 3:
            total += float(tuple(props)[3])
    return total


def _revolve(model, angle: float, *, both: bool = False):
    model = as_model_doc(model)
    feature_manager = model.FeatureManager
    args = (
        not both, True, False, False, False, both,
        0, 0, float(angle), float(angle if both else 0.0),
        False, False, 0.0, 0.0,
        0, 0.0, 0.0,
        False, True, True,
    )
    try:
        created = feature_manager.FeatureRevolve2(*args)
    except Exception as exc:
        created = None
        error = format_com_error(exc)
    else:
        error = "returned nothing"
    if created not in (None, False, 0) and not isinstance(created, bool):
        return created
    latest = _latest(model)
    # The newest feature stands in only when it is a revolve; the profile sketch would hide the failure.
    if latest is not None and str(com_value(latest.GetTypeName2) or "") in ("Revolution", "RevolutionThin"):
        return latest
    raise SolidWorksError(f"Revolve failed ({error}).")


def _extrude_both(model, sketch_feature, depth_pos: float, depth_neg: float, name: str) -> None:
    if not sketch_feature.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the sketch.")
    # Sd False: double-ended, so depth_neg is used. SW 2013 wants all 23 arguments,
    # the last three starting it from the sketch plane.
    feature = model.FeatureManager.FeatureExtrusion2(
        False, False, False,
        0, 0, float(depth_pos), float(depth_neg),
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        False, True, True,
        0, 0.0, False,
    )
    if feature is None:
        raise SolidWorksError(f"{name}: extrude failed.")
    rename_feature(feature, name)


def _extrude_cut_both(
    model, sketch_feature, depth_pos: float, depth_neg: float, name: str, scope: str | None = None
) -> None:
    """Cut both ways. With ``scope`` (a feature name) only the body that feature made is cut."""
    if not sketch_feature.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the sketch.")
    if scope is not None:
        body = _body_with_feature(model, scope)
        if body is None:
            raise SolidWorksError(f"{name}: the body to cut is missing.")
        # Feature scope bodies go in with mark 8.
        data = model.SelectionManager.CreateSelectData
        data.Mark = 8
        if not body.Select2(True, data):
            raise SolidWorksError(f"{name}: could not select the body to cut.")
    feature = _cut_both(model, depth_pos, depth_neg, scoped=scope is not None)
    rename_feature(feature, name)


def _cut(model, depth_m: float, *, flip: bool):
    """One-way cut, or None when that way finds no metal. ``flip`` reverses the direction."""
    # SW 2013 has no FeatureCut4; its FeatureCut3 takes these 26 arguments. Argument 2
    # would cut away everything outside the profile; argument 3 is the direction.
    return model.FeatureManager.FeatureCut3(
        True, False, bool(flip),
        0, 0, float(depth_m), 0.0,
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        False, True, True, True,
        True, False, 0, 0.0, False,
    )


def _cut_both(model, depth_pos: float, depth_neg: float, *, scoped: bool = False):
    # A cut's first direction is the reverse of an extrude's, so the depths go in swapped.
    feature = model.FeatureManager.FeatureCut3(
        False, False, False,
        0, 0, float(depth_neg), float(depth_pos),
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        False, True, not scoped, True,
        True, False, 0, 0.0, False,
    )
    if feature is None:
        raise SolidWorksError("The cut did not go through.")
    return feature


def _body_with_feature(model, feature_name: str):
    """The body built by ``feature_name``. Body names change as later features touch it."""
    for body in _bodies(model):
        with _swallow():
            features = com_value(body.GetFeatures)
            if any(str(com_value(f.Name) or "") == feature_name for f in features or ()):
                return body
    return None


def _pad_hole_radius(placed: Placement) -> float:
    pad = placed.repad
    assert pad is not None
    inner = pad.inner_diameter_in / 2.0
    pipe_r = placed.pipe.outside_diameter_in / 2.0
    return inner if inner > pipe_r else pipe_r


def _sag(placed: Placement) -> float:
    radius = placed.outside_radius_in
    outer = placed.repad.outer_diameter_in / 2.0 if placed.repad is not None else 0.0
    if outer <= 0.0 or outer >= radius:
        return 0.0
    return radius - math.sqrt(radius * radius - outer * outer)


def _axis_of(placed: Placement) -> tuple[float, float, float]:
    return placed.axis


def _is_new(body, before: list[tuple[float, float, float]], radius_in: float) -> bool:
    """A nozzle solid built at the tank center stays inside half the tank radius. Shell plates do not."""
    if _radial_reach(body) >= radius_in * 0.5 * _INCH:
        return False
    center = _center(body)
    if center is None:
        return False
    return all(_distance(center, old) > 0.01 for old in before)


def _centers(model) -> list[tuple[float, float, float]]:
    found = []
    for body in _bodies(model):
        center = _center(body)
        if center is not None:
            found.append(center)
    return found


def _center(body) -> tuple[float, float, float] | None:
    try:
        box = body.GetBodyBox()
    except Exception:
        return None
    if not box or len(tuple(box)) < 6:
        return None
    values = tuple(float(item) for item in box)
    return tuple((values[index] + values[index + 3]) / 2.0 for index in range(3))


def _bodies(model) -> list:
    try:
        from win32com.client import CastTo

        part = CastTo(model, "PartDoc")
    except Exception:
        part = model
    try:
        raw = part.GetBodies2(0, False)
    except Exception:
        return []
    if raw is None or isinstance(raw, (str, int, float, bool)):
        return []
    try:
        return [item for item in raw if item is not None]
    except TypeError:
        return [raw]


def _body_named(model, name: str):
    for body in _bodies(model):
        if str(com_value(body.Name) or "") == name:
            return body
    # A revolve body often keeps the feature name.
    for body in _bodies(model):
        title = str(com_value(body.Name) or "")
        if name in title:
            return body
    return None


def _delete_prefixed(model) -> None:
    named = []
    for feature in iter_features(model):
        title = str(com_value(feature.Name) or "")
        if title.startswith(_PREFIX):
            named.append(feature)
    for feature in reversed(named):
        _delete_feature(model, feature)
    _RIGHT[0] = None


def _delete_feature(model, feature) -> None:
    if feature is None:
        return
    model.ClearSelection2(True)
    with _swallow():
        feature.Select2(False, 0)
        model.Extension.DeleteSelection2(3)


def _delete_named_sketch(model, name: str) -> None:
    feature = find_feature(model, name)
    _delete_feature(model, feature)


def _latest(model):
    return model.FeatureByPositionReverse(0)


def _hide_sketch(model, name: str) -> None:
    feature = find_feature(model, name)
    if feature is None:
        return
    model.ClearSelection2(True)
    with _swallow():
        feature.Select2(False, 0)
        model.BlankSketch()
    model.ClearSelection2(True)


def _zoom_to_last(model) -> None:
    with _swallow():
        model.ViewZoomtofit2()


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _safe(mark: str) -> str:
    keep = "".join(ch if ch.isalnum() else "_" for ch in mark)
    return keep[:40] or "Nozzle"


class _swallow:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_args) -> bool:
        return exc_type is not None
