"""Revolve one cone roof in SolidWorks, plus its flattened blank.

The section matches the GA cross-section. Roof plates are laid on the unrolled
cone, beside the tank, and their edges are projected onto the cone.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rename_feature
from swauto.parts import extrude_blind, select_top_plane
from swauto.tank.roof import (
    RoofSpec,
    cone_point_in,
    cone_profile_in,
    flat_pattern,
    layout_roof_plates,
    ring_profile_in,
)
from swauto.tank.shell import (
    _close_sketch,
    _create_axis_segment,
    _create_profile_line,
    _open_sketch,
    _revolve_angle,
    _select_sketch_axis,
)

FEATURE_PREFIX = "EliteRoof"
ROOF_NAME = FEATURE_PREFIX
SKETCH_NAME = f"{FEATURE_PREFIX}Sk"
RING_NAME = f"{FEATURE_PREFIX}Ring"
RING_SKETCH_NAME = f"{FEATURE_PREFIX}RingSk"
SEAM_NAME = f"{FEATURE_PREFIX}Seams"
_INCH = 0.0254


class RoofResult:
    def __init__(self, title: str, model, note: str = "") -> None:
        self.title = title
        self.model = model
        self.note = note


def create_roof(app, spec: RoofSpec, *, model=None) -> RoofResult:
    """Add one revolved cone to ``model``, or open a new part."""
    spec.validate()
    profile = cone_profile_in(spec)
    target = _resolve_model(app, model)
    _activate(app, target)
    try:
        _delete_roof_features(target)
        ring = ring_profile_in(spec)
        if ring:
            _revolve_profile(target, ring, RING_SKETCH_NAME, RING_NAME)
        _revolve_profile(target, profile, SKETCH_NAME, ROOF_NAME)
        plates = layout_roof_plates(spec)
        _extrude_plates(target, spec, plates)
        _project_seams(target, spec, plates)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Roof failed ({_where(exc)}): {format_com_error(exc)}") from exc
    title = str(com_value(target.GetTitle) or "Part")
    return RoofResult(title=title, model=target)


def _revolve_profile(model, profile_in: tuple[tuple[float, float], ...], sketch_name: str, feature_name: str) -> None:
    points = tuple((radius * _INCH, height * _INCH) for radius, height in profile_in)
    _open_sketch(model, None)
    try:
        low = min(point[1] for point in points) - 0.05
        high = max(point[1] for point in points) + 0.05
        _create_axis_segment(model.SketchManager, 0.0, low, 0.0, high)
        loop = points + (points[0],)
        for start, end in zip(loop, loop[1:], strict=False):
            if math.hypot(end[0] - start[0], end[1] - start[1]) <= 1e-9:
                continue
            _create_profile_line(model.SketchManager, start[0], start[1], end[0], end[1])
    except Exception:
        _close_sketch(model)
        raise
    _close_sketch(model)

    sketch = model.FeatureByPositionReverse(0)
    if sketch is None:
        raise SolidWorksError(f"{feature_name} sketch was not created.")
    rename_feature(sketch, sketch_name)
    if not sketch.Select2(False, 0):
        raise SolidWorksError(f"Could not select the {feature_name} sketch.")
    _select_sketch_axis(model, sketch_name)
    feature = _revolve_angle(model, 2.0 * math.pi, merge=False, reverse=False)
    if feature is None:
        raise SolidWorksError(f"{feature_name} revolve failed.")
    created = ""
    with contextlib.suppress(Exception):
        created = str(com_value(feature.Name) or "")
    if created == sketch_name:
        raise SolidWorksError(f"{feature_name} revolve did not create a solid.")
    with contextlib.suppress(Exception):
        rename_feature(feature, feature_name)
    _hide_sketch(model, sketch_name)


def _extrude_plates(model, spec: RoofSpec, plates) -> None:
    """Extrude each developed plate on the top plane, clear of the cone."""
    pattern = flat_pattern(spec)
    for plate in plates:
        points = tuple(
            ((pattern.apex_x_in + local_x) * _INCH, (pattern.apex_z_in + local_z) * _INCH)
            for local_x, local_z in plate.polygon_in
        )
        _sketch_loop(model, points, plate.sketch_name, f"{plate.feature_name} sketch")
        sketch_feature = model.FeatureByPositionReverse(0)
        if sketch_feature is None:
            raise SolidWorksError(f"{plate.feature_name} sketch was not created.")
        if not sketch_feature.Select2(False, 0):
            raise SolidWorksError(f"Could not select {plate.sketch_name}.")
        try:
            feature = extrude_blind(model.FeatureManager, spec.thickness_in * _INCH, merge=False, reverse=False)
        except SolidWorksError:
            raise
        except Exception as exc:
            raise SolidWorksError(
                f"{plate.feature_name} extrude failed ({_where(exc)}): {format_com_error(exc)}"
            ) from exc
        rename_feature(feature, plate.feature_name)
        _hide_sketch(model, plate.sketch_name)
        _tint(model, feature, plate.color())


def _project_seams(model, spec: RoofSpec, plates) -> None:
    """Draw each plate edge on the outside of the cone."""
    sketch = model.SketchManager
    opened = False
    try:
        sketch.Insert3DSketch(True)
        opened = True
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
        with contextlib.suppress(Exception):
            sketch.DisplayWhenAdded = False
        for plate in plates:
            corners = [cone_point_in(spec, local_x, local_z) for local_x, local_z in plate.polygon_in]
            loop = corners + corners[:1]
            for start, end in zip(loop, loop[1:], strict=False):
                if math.dist((start.x_in, start.y_in, start.z_in), (end.x_in, end.y_in, end.z_in)) <= 1e-6:
                    continue
                _create_space_line(
                    sketch,
                    start.x_in * _INCH,
                    start.y_in * _INCH,
                    start.z_in * _INCH,
                    end.x_in * _INCH,
                    end.y_in * _INCH,
                    end.z_in * _INCH,
                )
    except SolidWorksError:
        if opened:
            _close_3d_sketch(model)
        raise
    except Exception as exc:
        if opened:
            _close_3d_sketch(model)
        raise SolidWorksError(f"Roof seam projection failed ({_where(exc)}): {format_com_error(exc)}") from exc
    _close_3d_sketch(model)
    feature = model.FeatureByPositionReverse(0)
    if feature is None:
        raise SolidWorksError("Roof seam sketch was not created.")
    rename_feature(feature, SEAM_NAME)


def _sketch_loop(model, points: tuple[tuple[float, float], ...], sketch_name: str, label: str) -> None:
    try:
        select_top_plane(model)
        sketch = model.SketchManager
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
        with contextlib.suppress(Exception):
            sketch.DisplayWhenAdded = False
        sketch.InsertSketch(True)
        try:
            for start, end in zip(points, points[1:] + points[:1], strict=False):
                if math.hypot(end[0] - start[0], end[1] - start[1]) <= 1e-9:
                    continue
                _create_sketch_line(sketch, start[0], start[1], end[0], end[1])
        finally:
            _close_flat_sketch(model)
    except SolidWorksError:
        _close_flat_sketch(model)
        raise
    except Exception as exc:
        _close_flat_sketch(model)
        raise SolidWorksError(f"{label} failed ({_where(exc)}): {format_com_error(exc)}") from exc
    feature = model.FeatureByPositionReverse(0)
    if feature is not None:
        rename_feature(feature, sketch_name)


def _tint(model, feature, rgb: tuple[float, float, float]) -> None:
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)
        if not feature.Select2(False, 0):
            return
        model.MaterialPropertyValues = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0, 1.0, 0.8, 0.25, 0.0, 0.0)
        model.ClearSelection2(True)


def _create_space_line(sketch, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> None:
    for _ in range(2):
        segment = sketch.CreateLine(float(x0), float(y0), float(z0), float(x1), float(y1), float(z1))
        if segment is not None:
            return
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
    raise SolidWorksError("Roof seam line failed.")


def _close_3d_sketch(model) -> None:
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = False
    with contextlib.suppress(Exception):
        sketch.DisplayWhenAdded = True
    with contextlib.suppress(Exception):
        sketch.Insert3DSketch(True)
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)


def _create_sketch_line(sketch, x0: float, y0: float, x1: float, y1: float) -> None:
    for _ in range(2):
        segment = sketch.CreateLine(float(x0), float(y0), 0.0, float(x1), float(y1), 0.0)
        if segment is not None:
            return
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
    raise SolidWorksError(f"Flat pattern line failed ({x0:.4f}, {y0:.4f}) to ({x1:.4f}, {y1:.4f}).")


def _close_flat_sketch(model) -> None:
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = False
    with contextlib.suppress(Exception):
        sketch.DisplayWhenAdded = True
    with contextlib.suppress(Exception):
        sketch.InsertSketch(True)
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)


def _resolve_model(app, model):
    if model is not None:
        try:
            if str(com_value(model.GetTitle) or ""):
                return model
        except Exception:
            pass
    from swauto.parts import new_part

    return new_part(app)


def _activate(app, model) -> None:
    with contextlib.suppress(Exception):
        app.Visible = True
    title = str(com_value(model.GetTitle) or "")
    if not title:
        return
    for name, args in (
        ("ActivateDoc", (title,)),
        ("ActivateDoc3", (title, False, 0)),
    ):
        method = getattr(app, name, None)
        if not callable(method):
            continue
        try:
            method(*args)
            return
        except Exception:
            continue
    try:
        import pythoncom
        from win32com.client import VARIANT

        errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        app.ActivateDoc2(title, False, errors)
    except Exception:
        return


def _delete_roof_features(model) -> None:
    names: list[str] = []
    for feature in iter_features(model):
        name = str(com_value(feature.Name) or "")
        if name.startswith(FEATURE_PREFIX):
            names.append(name)
    for name in reversed(names):
        feature = find_feature(model, name)
        if feature is None:
            continue
        with contextlib.suppress(Exception):
            model.ClearSelection2(True)
            feature.Select2(False, 0)
            model.EditDelete()
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)


def _hide_sketch(model, name: str) -> None:
    feature = find_feature(model, name)
    if feature is None:
        return
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)
        feature.Select2(False, 0)
        model.BlankSketch()
        model.ClearSelection2(True)


def _where(exc: BaseException) -> str:
    tb = exc.__traceback__
    chosen = None
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename.replace("\\", "/")
        if "/swauto/" in filename:
            chosen = tb
        tb = tb.tb_next
    if chosen is None:
        return type(exc).__name__
    short = chosen.tb_frame.f_code.co_filename.replace("\\", "/").rsplit("/", 1)[-1]
    return f"{short} {chosen.tb_frame.f_code.co_name} line {chosen.tb_lineno}"
