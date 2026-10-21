"""Flat developed stringer plates in SolidWorks (2013-safe).

Each plate is the lisp burn outline extruded 3/8 in off the Front plane. The
tread side profiles sit behind the plate as 1 in blocks so the tread position
against the plate edge can be checked. Tread bolts, end holes and end slots
are cut through.
"""

from __future__ import annotations

import contextlib

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature
from swauto.params import rename_feature
from swauto.parts import extrude_blind, new_part
from swauto.stair.development import (
    BOLT_RADIUS_IN,
    END_HOLE_RADIUS_IN,
    SLOT_LENGTH_IN,
    DevelopedStringer,
    develop_both,
    tread_rect,
)
from swauto.stair.stringer import THICKNESS_IN, StringerMock
from swauto.stair.stringer_sw import _activate, _create_circle, _names, _rename_new, _select_feature
from swauto.tank.shell import _clear_selection, _close_sketch, _open_sketch

_INCH = 0.0254
PREFIX = "EliteDev"
TREAD_BLOCK_IN = 0.5
INNER_ABOVE_IN = 30.0


class DevelopmentResult:
    def __init__(self, title: str, model, note: str) -> None:
        self.title = title
        self.model = model
        self.note = note


def create_development(app, stair: StringerMock) -> DevelopmentResult:
    inner, outer = develop_both(stair)
    model = new_part(app)
    _activate(app, model)
    try:
        _plate(model, outer, 0.0, f"{PREFIX}Out")
        _plate(model, inner, outer.height_in + INNER_ABOVE_IN, f"{PREFIX}In")
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Development failed: {format_com_error(exc)}") from exc
    with contextlib.suppress(Exception):
        model.ShowNamedView2("*Front", 1)
        model.ViewZoomtofit2()
        model.ViewDisplayShaded()
        model.GraphicsRedraw2()
    note = (
        f"Inner plate {inner.length_in:.2f} x {inner.height_in:.2f} in at pitch {inner.pitch_deg:.2f}°, "
        f"outer plate {outer.length_in:.2f} x {outer.height_in:.2f} in at pitch {outer.pitch_deg:.2f}°. "
        f"{len(outer.tread_bolts)} tread bolts and 4 end holes per plate; outer end holes are slots."
    )
    return DevelopmentResult(title=str(com_value(model.GetTitle) or "Part"), model=model, note=note)


def _plate(model, dev: DevelopedStringer, y_offset: float, name: str) -> None:
    front = find_feature(model, "Front Plane") or find_feature(model, "Front")
    if front is None:
        raise SolidWorksError("Could not find the Front Plane.")
    shift = (0.0, y_offset)

    # Burn outline.
    before = _names(model)
    _open_sketch(model, front)
    try:
        _polygon(model, [_add(p, shift) for p in dev.outline])
    except Exception:
        _recover(model)
        raise
    _close_sketch(model)
    outline_sk = _rename_new(model, before, f"{name}Sk", "outline sketch")
    _extrude(model, outline_sk, THICKNESS_IN, name, merge=False, reverse=False)

    # Tread side profiles on the face of the plate, so the Front view shows them.
    before = _names(model)
    _clear_selection(model)
    if not front.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select the Front Plane.")
    model.CreatePlaneAtOffset(THICKNESS_IN * _INCH, False)
    _clear_selection(model)
    face_plane = _rename_new(model, before, f"{name}FacePln", "face plane")
    before = _names(model)
    _open_sketch(model, face_plane)
    try:
        for center in dev.tread_centers:
            _polygon(model, [_add(p, shift) for p in tread_rect(center)])
    except Exception:
        _recover(model)
        raise
    _close_sketch(model)
    treads_sk = _rename_new(model, before, f"{name}TreadsSk", "tread sketch")
    bodies_before = _body_names(model)
    _extrude(model, treads_sk, TREAD_BLOCK_IN, f"{name}Treads", merge=False, reverse=False)
    _tint_new_bodies(model, bodies_before, (0.72, 0.42, 0.16))

    # Tread bolts, end holes / slots.
    before = _names(model)
    _open_sketch(model, front)
    try:
        sketch = model.SketchManager
        for point in dev.tread_bolts:
            x, y = _add(point, shift)
            if _create_circle(sketch, x * _INCH, y * _INCH, BOLT_RADIUS_IN * _INCH) is None:
                raise SolidWorksError(f"{name}: tread bolt circle failed.")
        for point in dev.end_holes:
            x, y = _add(point, shift)
            if dev.slotted:
                _slot(model, x, y, SLOT_LENGTH_IN, END_HOLE_RADIUS_IN)
            elif _create_circle(sketch, x * _INCH, y * _INCH, END_HOLE_RADIUS_IN * _INCH) is None:
                raise SolidWorksError(f"{name}: end hole circle failed.")
    except Exception:
        _recover(model)
        raise
    _close_sketch(model)
    holes_sk = _rename_new(model, before, f"{name}HolesSk", "holes sketch")
    feature = _cut_both_ways(model, holes_sk, THICKNESS_IN + TREAD_BLOCK_IN + 0.25)
    if feature is None:
        raise SolidWorksError(f"{name}: holes did not cut.")
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Holes")


def _add(point, shift):
    return (point[0] + shift[0], point[1] + shift[1])


def _body_names(model) -> set[str]:
    raw = model.GetBodies2(0, False)
    if raw is None:
        return set()
    bodies = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    names = set()
    for body in bodies:
        with contextlib.suppress(Exception):
            names.add(str(body.Name))
    return names


def _tint_new_bodies(model, before: set[str], rgb: tuple[float, float, float]) -> None:
    raw = model.GetBodies2(0, False)
    if raw is None:
        return
    bodies = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    for body in bodies:
        try:
            if str(body.Name) in before:
                continue
            body.MaterialPropertyValues = (rgb[0], rgb[1], rgb[2], 1.0, 1.0, 0.6, 0.3, 0.0, 0.0)
        except Exception:
            continue


def snapshot(model, path: str, box_in: tuple[float, float, float, float] | None = None, size=(1600, 900)) -> bool:
    """Save a BMP of the Front view, zoomed to ``box_in`` (x0, y0, x1, y1) when given."""
    with contextlib.suppress(Exception):
        model.ShowNamedView2("*Front", 1)
    if box_in is None:
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
    else:
        x0, y0, x1, y1 = (v * _INCH for v in box_in)
        with contextlib.suppress(Exception):
            model.ViewZoomTo2(x0, y0, -0.1, x1, y1, 0.1)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()
    try:
        return bool(model.SaveBMP(path, size[0], size[1]))
    except Exception:
        return False


def _polygon(model, points) -> None:
    sketch = model.SketchManager
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1], strict=False):
        segment = sketch.CreateLine(ax * _INCH, ay * _INCH, 0.0, bx * _INCH, by * _INCH, 0.0)
        if segment is None:
            with contextlib.suppress(Exception):
                sketch.AddToDB = True
            segment = sketch.CreateLine(ax * _INCH, ay * _INCH, 0.0, bx * _INCH, by * _INCH, 0.0)
        if segment is None:
            raise SolidWorksError("Could not draw an outline line.")


def _slot(model, cx: float, cy: float, length_in: float, radius_in: float) -> None:
    """Horizontal stadium: two lines and two end arcs through three points each."""
    sketch = model.SketchManager
    half = max(length_in / 2.0 - radius_in, 0.0)
    left, right = cx - half, cx + half
    top, bottom = cy + radius_in, cy - radius_in
    for (ax, ay), (bx, by) in (((left, top), (right, top)), ((right, bottom), (left, bottom))):
        if sketch.CreateLine(ax * _INCH, ay * _INCH, 0.0, bx * _INCH, by * _INCH, 0.0) is None:
            raise SolidWorksError("Could not draw a slot line.")
    for (sx, sy), (ex, ey), (mx, my) in (
        ((right, top), (right, bottom), (right + radius_in, cy)),
        ((left, bottom), (left, top), (left - radius_in, cy)),
    ):
        arc = sketch.Create3PointArc(sx * _INCH, sy * _INCH, 0.0, ex * _INCH, ey * _INCH, 0.0, mx * _INCH, my * _INCH, 0.0)
        if arc is None:
            raise SolidWorksError("Could not draw a slot arc.")


def _extrude(model, sketch, depth_in: float, name: str, *, merge: bool, reverse: bool):
    _clear_selection(model)
    if not _select_feature(model, sketch, "SKETCH", mark=0, append=False):
        raise SolidWorksError(f"{name}: could not select the sketch.")
    feature = extrude_blind(model.FeatureManager, depth_in * _INCH, merge=merge, reverse=reverse)
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    return feature


def _cut_both_ways(model, sketch, depth_in: float):
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
        raise SolidWorksError("Could not select the holes sketch.")
    try:
        feature = method(*args)
    except Exception:
        return None
    return feature if feature not in (None, False) else None


def _recover(model) -> None:
    with contextlib.suppress(Exception):
        if com_value(model.GetActiveSketch2) is not None:
            _close_sketch(model)
    _clear_selection(model)
