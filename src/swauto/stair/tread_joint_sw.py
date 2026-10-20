"""Build the tread-to-stringer joint in SolidWorks (2013-safe).

Two straight 3/8 in stringer pieces, one pan tread with no bottom between
them, and the two 7/16 in bolts per side cut from each stringer's outside face
through the plate, across the 1/16 in gap, and through the tread end wall.
"""

from __future__ import annotations

import contextlib

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature
from swauto.params import rename_feature
from swauto.parts import extrude_blind, new_part
from swauto.stair.stringer import THICKNESS_IN
from swauto.stair.stringer_sw import (
    _activate,
    _create_circle,
    _delete_named,
    _names,
    _offset_plane,
    _rename_new,
    _select_feature,
)
from swauto.stair.tread_joint import TreadJointLayout, TreadJointSpec, layout_tread_joint
from swauto.tank.shell import _clear_selection, _close_sketch, _open_sketch

PREFIX = "EliteJoint"
_INCH = 0.0254


class TreadJointResult:
    def __init__(self, title: str, model, note: str) -> None:
        self.title = title
        self.model = model
        self.note = note


def create_tread_joint(app, spec: TreadJointSpec) -> TreadJointResult:
    layout = layout_tread_joint(spec)
    model = new_part(app)
    _activate(app, model)
    try:
        _stringer(model, layout, f"{PREFIX}StringerIn", layout.inner_face_z, layout.inner_back_z)
        _stringer(model, layout, f"{PREFIX}StringerOut", layout.outer_face_z, layout.outer_back_z)
        _tread(model, layout)
        inner_ok = _bolts(model, layout, "In", layout.inner_back_z, "inner")
        outer_ok = _bolts(model, layout, "Out", layout.outer_back_z, "outer")
        _name_bodies(model)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Tread joint failed: {format_com_error(exc)}") from exc
    with contextlib.suppress(Exception):
        model.ShowNamedView2("*Isometric", 7)
        model.ViewZoomtofit2()
        model.ViewDisplayShaded()
        model.GraphicsRedraw2()
    done = int(inner_ok) + int(outer_ok)
    note = (
        f"Pan tread with {layout.wall_in:g} in walls between two {layout.stringer_length_in:g} in "
        f"stringer pieces. Bolt pairs through {done} of 2 stringers into the tread end walls."
    )
    return TreadJointResult(title=str(com_value(model.GetTitle) or "Part"), model=model, note=note)


def _bodies(model):
    raw = model.GetBodies2(0, False)
    if raw is None:
        return []
    return list(raw) if isinstance(raw, (list, tuple)) else [raw]


def _box_in(body) -> list[float]:
    return [float(v) / _INCH for v in com_value(body.GetBodyBox)]


def _classify(model) -> dict[str, object]:
    """Bodies by where they sit. A cut renames bodies, so names are not stable."""
    found: dict[str, object] = {}
    for body in _bodies(model):
        box = _box_in(body)
        if box[5] - box[2] < 1.0:
            key = "inner" if (box[2] + box[5]) / 2.0 < 1.0 else "outer"
        else:
            key = "tread"
        found[key] = body
    return found


def _face_counts(model) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, body in _classify(model).items():
        with contextlib.suppress(Exception):
            counts[key] = int(body.GetFaceCount())
    return counts


def _name_bodies(model) -> None:
    for key, name in (("inner", f"{PREFIX}StringerIn"), ("outer", f"{PREFIX}StringerOut"), ("tread", f"{PREFIX}Tread")):
        body = _classify(model).get(key)
        if body is not None:
            with contextlib.suppress(Exception):
                body.Name = name


def _rect(sketch, x0: float, y0: float, x1: float, y1: float) -> None:
    points = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    for (ax, ay), (bx, by) in zip(points, points[1:], strict=False):
        segment = sketch.CreateLine(ax * _INCH, ay * _INCH, 0.0, bx * _INCH, by * _INCH, 0.0)
        if segment is None:
            with contextlib.suppress(Exception):
                sketch.AddToDB = True
            segment = sketch.CreateLine(ax * _INCH, ay * _INCH, 0.0, bx * _INCH, by * _INCH, 0.0)
        if segment is None:
            raise SolidWorksError("Could not draw a joint sketch line.")


def _extrude(model, sketch, depth_in: float, name: str, *, merge: bool, reverse: bool = False):
    _clear_selection(model)
    if not _select_feature(model, sketch, "SKETCH", mark=0, append=False):
        raise SolidWorksError(f"{name}: could not select the sketch.")
    feature = extrude_blind(model.FeatureManager, depth_in * _INCH, merge=merge, reverse=reverse)
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    return feature


def _front(model):
    plane = find_feature(model, "Front Plane") or find_feature(model, "Front")
    if plane is None:
        raise SolidWorksError("Could not find the Front Plane.")
    return plane


def _top(model):
    plane = find_feature(model, "Top Plane") or find_feature(model, "Top")
    if plane is None:
        raise SolidWorksError("Could not find the Top Plane.")
    return plane


def _plane_at_z(model, z_in: float, name: str):
    if abs(z_in) < 1e-9:
        return _front(model)
    plane = _offset_plane(model, _front(model), abs(z_in) * _INCH, z_in < 0, name)
    if plane is None:
        raise SolidWorksError(f"Could not place the plane {name}.")
    return plane


def _stringer(model, layout: TreadJointLayout, name: str, face_z: float, back_z: float) -> None:
    """Vertical plate whose tread-side face is at ``face_z``, grown to ``back_z``."""
    plane = _plane_at_z(model, face_z, f"{name}Pln")
    half = layout.stringer_length_in / 2.0
    for reverse in (back_z < face_z, back_z > face_z):
        before = _names(model)
        _open_sketch(model, plane)
        _rect(model.SketchManager, -half, 0.0, half, layout.plate_width_in)
        _close_sketch(model)
        sketch = _rename_new(model, before, f"{name}Sk", "stringer sketch")
        _extrude(model, sketch, THICKNESS_IN, name, merge=False, reverse=reverse)
        box = _box_in(_bodies(model)[-1])
        low, high = sorted((face_z, back_z))
        if abs(box[2] - low) < 1e-3 and abs(box[5] - high) < 1e-3:
            return
        _delete_named(model, (name, f"{name}Sk"))
    raise SolidWorksError(f"{name} did not land between Z {face_z:g} and {back_z:g} in.")


def _tread(model, layout: TreadJointLayout) -> None:
    """Open-bottom pan: a wall ring, then the top plate merged onto it."""
    wall = layout.wall_in
    z0, z1 = layout.tread_z0, layout.tread_z1
    x0, x1 = layout.tread_x0, layout.tread_x1
    top = _top(model)
    # Top-plane sketch: sketch x = world x, sketch y = -world z.
    base = _offset_plane(model, top, layout.tread_y0 * _INCH, False, f"{PREFIX}TreadPln")
    if base is None:
        raise SolidWorksError("Could not place the tread bottom plane.")
    before = _names(model)
    _open_sketch(model, base)
    _rect(model.SketchManager, x0, -z1, x1, -z0)
    _rect(model.SketchManager, x0 + wall, -(z1 - wall), x1 - wall, -(z0 + wall))
    _close_sketch(model)
    walls_sketch = _rename_new(model, before, f"{PREFIX}TreadWallsSk", "tread walls sketch")
    height = layout.tread_y1 - layout.tread_y0
    _extrude(model, walls_sketch, height - wall, f"{PREFIX}TreadWalls", merge=False)
    lid = _offset_plane(model, top, (layout.tread_y1 - wall) * _INCH, False, f"{PREFIX}TreadTopPln")
    if lid is None:
        raise SolidWorksError("Could not place the tread top plane.")
    before = _names(model)
    _open_sketch(model, lid)
    _rect(model.SketchManager, x0, -z1, x1, -z0)
    _close_sketch(model)
    top_sketch = _rename_new(model, before, f"{PREFIX}TreadTopSk", "tread top sketch")
    _extrude(model, top_sketch, wall, f"{PREFIX}TreadTop", merge=True)


def _bolts(model, layout: TreadJointLayout, side: str, plane_z: float, stringer_key: str) -> bool:
    """Two bolts from the tread front face, cut from this stringer's outside face."""
    name = f"{PREFIX}Bolts{side}"
    plane = _plane_at_z(model, plane_z, f"{name}Pln")
    before = _names(model)
    _open_sketch(model, plane)
    for x_in in layout.bolt_xs:
        circle = _create_circle(
            model.SketchManager, x_in * _INCH, layout.bolt_y * _INCH, layout.bolt_dia_in / 2.0 * _INCH
        )
        if circle is None:
            _close_sketch(model)
            raise SolidWorksError(f"{name}: bolt circle was not created.")
    _close_sketch(model)
    sketch = _rename_new(model, before, f"{name}Sk", "bolt sketch")
    toward_tread_first = plane_z < layout.tread_z0
    for direction in (toward_tread_first, not toward_tread_first):
        counts_before = _face_counts(model)
        feature = _cut_blind(model, sketch, layout.cut_depth_in, direction)
        if feature is None:
            continue
        with contextlib.suppress(Exception):
            rename_feature(feature, name)
        counts_after = _face_counts(model)
        hit_stringer = counts_after.get(stringer_key, 0) > counts_before.get(stringer_key, 0)
        hit_tread = counts_after.get("tread", 0) > counts_before.get("tread", 0)
        if hit_stringer and hit_tread:
            return True
        _delete_named(model, (name,))
    return False


def _cut_blind(model, sketch, depth_in: float, reverse: bool):
    """Blind extruded cut of the selected sketch.

    SolidWorks 2013 needs the 26-arg FeatureCut3. Argument 2 only flips which
    side of the profile is removed; argument 3 is the cut direction.
    """
    method = getattr(model.FeatureManager, "FeatureCut3", None)
    if not callable(method):
        raise SolidWorksError("FeatureCut3 is not on this SolidWorks interface.")
    args = (
        True, False, bool(reverse), 0, 0, depth_in * _INCH, 0.0,
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
