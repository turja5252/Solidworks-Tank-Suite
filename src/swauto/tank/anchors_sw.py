"""Build the anchor chairs onto the shell part in SolidWorks.

One chair is built facing +Z, on the principal planes: the top plate and washer from level sketches, the
legs from sketches parallel to the Right Plane. Every other chair is that one copied round the tank axis
(Move/Copy Body, a right-hand turn about +Y is the opposite of the app's angle), and then the first one is
turned to its own angle.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import com_nothing, com_value
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rebuild, rename_feature
from swauto.parts import select_plane
from swauto.tank.anchors import WASHER_HOLE_EXTRA_IN, AnchorChairs, chairs, leg_profile
from swauto.tank.framing_sw import _bodies_with_feature

PREFIX = "EliteAnchor"
_INCH = 0.0254
_PIECES = ("top plate", "washer", "leg A", "leg B")


def add_anchor_chairs(model, spec: AnchorChairs, shell_radius_in: float, progress=None) -> str:
    """Rebuild every anchor chair on ``model``, against a course 1 outside radius of ``shell_radius_in``."""
    if model is None:
        raise SolidWorksError("Create the tank shell in SolidWorks first.")
    spots = chairs(spec)
    _delete_prefixed(model)
    rebuild(model)
    _say(progress, "Anchor chair 1...")
    _build_chair(model, spec, shell_radius_in)
    for chair in spots[1:]:
        _say(progress, f"Anchor chair {chair.number} of {len(spots)}...")
        _move(model, chair.angle_deg, f"{PREFIX}Chair{chair.number}", copy=True)
        _label(model, f"{PREFIX}Chair{chair.number}", chair.number, chair.angle_deg)
    if abs(math.remainder(spots[0].angle_deg, 360.0)) > 1e-9:
        _move(model, spots[0].angle_deg, f"{PREFIX}Chair1Turn", copy=False)
        _label(model, f"{PREFIX}Chair1Turn", 1, spots[0].angle_deg)
    rebuild(model)
    return f"{len(spots)} anchor chairs round the shell."


def _build_chair(model, spec: AnchorChairs, radius: float) -> None:
    """Chair 1, facing +Z: r out is +Z from the shell's outside, t along the shell is X."""
    w, d, e = spec.top_plate_width_in / 2.0, spec.top_plate_depth_in, spec.hole_from_shell_in
    legs = spec.leg_height_in
    top_y = legs + spec.top_plate_thk_in / 2.0
    top = _level(model, top_y, f"{PREFIX}TopLevel")
    _slab(model, top, top_y, [(-w, radius), (w, radius), (w, radius + d), (-w, radius + d)], (0.0, radius + e),
          spec.hole_dia_in / 2.0, spec.top_plate_thk_in, f"{PREFIX}TopPlate")
    _name_body(model, f"{PREFIX}TopPlate", "Chair 1 top plate")
    ww, half = spec.washer_width_in / 2.0, spec.washer_depth_in / 2.0
    washer_y = spec.height_in + spec.washer_thk_in / 2.0
    washer = _level(model, washer_y, f"{PREFIX}WasherLevel")
    _slab(model, washer, washer_y, [(-ww, radius + e - half), (ww, radius + e - half), (ww, radius + e + half),
                          (-ww, radius + e + half)], (0.0, radius + e),
          (spec.hole_dia_in + WASHER_HOLE_EXTRA_IN) / 2.0, spec.washer_thk_in, f"{PREFIX}Washer")
    _name_body(model, f"{PREFIX}Washer", "Chair 1 washer")
    middle = spec.leg_gap_in / 2.0 + spec.leg_thk_in / 2.0
    for side, x in (("A", -middle), ("B", middle)):
        plane = _offset(model, "Right Plane", x, f"{PREFIX}Leg{side}Plane")
        _open(model, plane)
        at = _mapper(model, f"{PREFIX}Leg{side}")
        points = [at((x, y, radius + r)) for r, y in leg_profile(spec)]
        _polygon(model, points, f"{PREFIX}Leg{side}")
        sketch = _close(model, f"{PREFIX}Leg{side}Sk")
        _extrude_mid(model, sketch, spec.leg_thk_in, f"{PREFIX}Leg{side}")
        _hide(model, plane)
        _name_body(model, f"{PREFIX}Leg{side}", f"Chair 1 leg {side}")
    for plane in (top, washer):
        _hide(model, plane)


def _slab(model, plane, y: float, corners, hole_at, hole_r: float, thickness: float, name: str) -> None:
    """A level plate, its middle on ``plane`` at ``y``: the plan outline (X, Z) with one round hole, extruded
    both ways."""
    _open(model, plane)
    at = _mapper(model, name)
    _polygon(model, [at((x, y, z)) for x, z in corners], name)
    cx, cy = at((hole_at[0], y, hole_at[1]))
    model.SketchManager.CreateCircleByRadius(cx, cy, 0.0, hole_r * _INCH)
    sketch = _close(model, f"{name}Sk")
    _extrude_mid(model, sketch, thickness, name)


def _move(model, angle_deg: float, feature_name: str, *, copy: bool) -> None:
    """Chair 1's bodies, copied or turned ``angle_deg`` the app's way about the tank axis."""
    model.ClearSelection2(True)
    nothing = com_nothing()
    originals = _originals(model)
    if len(originals) != len(_PIECES):
        raise SolidWorksError("Anchor chair 1 is not all there to copy round the shell.")
    for index, body in enumerate(originals):
        name = str(com_value(body.Name) or "")
        if not model.Extension.SelectByID2(name, "SOLIDBODY", 0.0, 0.0, 0.0, index > 0, 1, nothing, 0):
            raise SolidWorksError(f"Could not select {name} to copy it round the shell.")
    feature = model.FeatureManager.InsertMoveCopyBody2(
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -math.radians(angle_deg), 0.0, bool(copy), 1
    )
    model.ClearSelection2(True)
    if feature is None:
        raise SolidWorksError(f"Anchor chair 1 could not be {'copied' if copy else 'turned'} to {angle_deg:g} deg.")
    rename_feature(feature, feature_name)
    rebuild(model)


def _originals(model) -> list:
    """Chair 1's four bodies: the ones its own features made, and no copy."""
    found = []
    for feature in (f"{PREFIX}TopPlate", f"{PREFIX}Washer", f"{PREFIX}LegA", f"{PREFIX}LegB"):
        for body in _bodies_with_feature(model, feature):
            made_by = {str(com_value(f.Name) or "") for f in com_value(body.GetFeatures) or ()}
            if not any(name.startswith(f"{PREFIX}Chair") and not name.endswith("Turn") for name in made_by):
                found.append(body)
                break
    return found


def _label(model, feature_name: str, number: int, angle_deg: float) -> None:
    """Name the four bodies ``feature_name`` made: the washer is on top, then the top plate, then the legs, told
    apart by which side of the chair they are on."""
    pieces = _bodies_with_feature(model, feature_name)
    if len(pieces) != len(_PIECES):
        raise SolidWorksError(f"Anchor chair {number} came out as {len(pieces)} pieces, not {len(_PIECES)}.")
    boxes = [(tuple(float(v) / _INCH for v in body.GetBodyBox()), body) for body in pieces]
    boxes.sort(key=lambda item: -item[0][4])
    washer, top_plate, *legs = boxes
    cw = (-math.cos(math.radians(angle_deg)), -math.sin(math.radians(angle_deg)))
    legs.sort(key=lambda item: ((item[0][0] + item[0][3]) * cw[0] + (item[0][2] + item[0][5]) * cw[1]))
    labels = [(washer[1], "washer"), (top_plate[1], "top plate")]
    labels += [(legs[0][1], "leg B"), (legs[1][1], "leg A")]  # chair 1's leg A is on its clockwise side
    for body, label in labels:
        with contextlib.suppress(Exception):
            body.Name = f"Chair {number} {label}"


def _name_body(model, feature_name: str, name: str) -> str:
    rebuild(model)
    found = _bodies_with_feature(model, feature_name)
    if len(found) != 1:
        raise SolidWorksError(f"{name} did not build.")
    with contextlib.suppress(Exception):
        found[0].Name = name
    return str(com_value(found[0].Name) or name)


# ---------------------------------------------------------------- sketches, planes, features


def _level(model, y_in: float, name: str):
    return _offset(model, "Top Plane", y_in, name)


def _offset(model, base: str, distance_in: float, name: str):
    model.ClearSelection2(True)
    if not select_plane(model, base):
        raise SolidWorksError(f"Could not select the {base}.")
    model.CreatePlaneAtOffset(abs(distance_in) * _INCH, distance_in < 0.0)
    model.ClearSelection2(True)
    feature = model.FeatureByPositionReverse(0)
    rename_feature(feature, name)
    return find_feature(model, name) or feature


def _open(model, plane) -> None:
    model.ClearSelection2(True)
    if not plane.Select2(False, 0):
        raise SolidWorksError("Could not select an anchor chair sketch plane.")
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = True
    with contextlib.suppress(Exception):
        sketch.DisplayWhenAdded = False
    sketch.InsertSketch(True)


def _close(model, name: str):
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = False
    with contextlib.suppress(Exception):
        sketch.DisplayWhenAdded = True
    sketch.InsertSketch(True)
    model.ClearSelection2(True)
    feature = model.FeatureByPositionReverse(0)
    rename_feature(feature, name)
    with contextlib.suppress(Exception):
        if feature.Select2(False, 0):
            model.BlankSketch()
    model.ClearSelection2(True)
    return feature


def _transform(model) -> list[float]:
    transform = com_value(com_value(model.GetActiveSketch2).ModelToSketchTransform)
    return [float(v) for v in com_value(transform.ArrayData)]


def _mapper(model, name: str):
    """World inches to the open sketch's meters."""
    try:
        data = _transform(model)
    except Exception as exc:
        raise SolidWorksError(f"{name}: could not read the sketch plane.") from exc

    def at(point):
        p = [v * _INCH for v in point]
        return (data[0] * p[0] + data[3] * p[1] + data[6] * p[2] + data[9],
                data[1] * p[0] + data[4] * p[1] + data[7] * p[2] + data[10])

    return at


def _polygon(model, points, name: str) -> None:
    sketch = model.SketchManager
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        sketch.CreateLine(x0, y0, 0.0, x1, y1, 0.0)
    try:
        drawn = len(list(com_value(com_value(model.GetActiveSketch2).GetSketchSegments) or ()))
    except Exception:  # noqa: BLE001
        drawn = 0
    if drawn < len(points):
        raise SolidWorksError(f"{name}: the outline did not draw.")


def _extrude_mid(model, sketch, thickness_in: float, name: str) -> None:
    """Both ways from the sketch, half the thickness each, as its own body. SW 2013 wants all 23 arguments."""
    model.ClearSelection2(True)
    if not sketch.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the sketch.")
    half = thickness_in / 2.0 * _INCH
    feature = model.FeatureManager.FeatureExtrusion2(
        False, False, False,
        0, 0, half, half,
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        False, True, True,
        0, 0.0, False,
    )
    if feature is None:
        raise SolidWorksError(f"{name}: the extrude failed.")
    rename_feature(feature, name)


def _hide(model, plane) -> None:
    model.ClearSelection2(True)
    with contextlib.suppress(Exception):
        if plane.Select2(False, 0):
            blank = model.BlankRefGeom
            blank() if callable(blank) else com_value(blank)
    model.ClearSelection2(True)


def _delete_prefixed(model) -> None:
    named = [f for f in iter_features(model) if str(com_value(f.Name) or "").startswith(PREFIX)]
    for feature in reversed(named):
        model.ClearSelection2(True)
        with contextlib.suppress(Exception):
            if feature.Select2(False, 0):
                model.Extension.DeleteSelection2(3)
    model.ClearSelection2(True)


def _say(progress, text: str) -> None:
    if progress is not None:
        with contextlib.suppress(Exception):
            progress(text)
