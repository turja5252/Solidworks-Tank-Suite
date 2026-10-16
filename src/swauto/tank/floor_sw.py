"""Build a lap-welded floor in SolidWorks, one row at a time.

Plates are separate solids. They overlap in plan by the lap, and the
thickness goes down from the shell datum so a shell on the same part still
sits on Y = 0. Each row is redrawn before the next one starts.
"""

from __future__ import annotations

import contextlib
import time

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rename_feature
from swauto.parts import extrude_blind, select_top_plane
from swauto.tank.floor import ROW_COLORS, FloorPlate, FloorSpec, floor_rows, layout_floor

FEATURE_PREFIX = "EliteFloor"
RIM_NAME = f"{FEATURE_PREFIX}Rim"
_INCH = 0.0254


class FloorResult:
    def __init__(self, title: str, model, row_count: int, plate_count: int, note: str = "") -> None:
        self.title = title
        self.model = model
        self.row_count = row_count
        self.plate_count = plate_count
        self.note = note


def create_floor(
    app,
    spec: FloorSpec,
    *,
    model=None,
    on_row=None,
    pause_s: float = 0.65,
) -> FloorResult:
    """Add the floor to ``model``, or open a new part when ``model`` is omitted.

    ``on_row(row_number, row_count)`` runs after that row exists, before the pause.
    """
    spec.validate()
    plates = layout_floor(spec)
    rows = floor_rows(plates)
    if not rows:
        raise SolidWorksError("No floor plates to build.")

    target = _resolve_model(app, model)
    _activate(app, target)
    try:
        _delete_floor_features(target)
        _draw_rim(target, spec.trim_radius_in() * _INCH)
        _frame_view(target)
        warnings: list[str] = []
        built = 0
        for index, row in enumerate(rows, start=1):
            tint = ROW_COLORS[(index - 1) % len(ROW_COLORS)]
            for plate in row:
                try:
                    _build_plate(target, plate, spec.thickness_in * _INCH, tint)
                except SolidWorksError as exc:
                    warnings.append(str(exc))
                    continue
                built += 1
            _redraw(target)
            if on_row is not None:
                on_row(index, len(rows))
            if pause_s > 0:
                time.sleep(pause_s)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Floor failed ({_where(exc)}): {format_com_error(exc)}") from exc

    _hide_sketch(target, RIM_NAME)
    _redraw(target)
    if built == 0:
        detail = "\n".join(warnings) if warnings else "No plate extrude succeeded."
        raise SolidWorksError(f"No floor plates were created.\n{detail}")

    title = str(com_value(target.GetTitle) or "Part")
    note = ""
    if warnings:
        note = warnings[0] if len(warnings) == 1 else f"{len(warnings)} floor plates were not finished. {warnings[0]}"
    return FloorResult(title=title, model=target, row_count=len(rows), plate_count=built, note=note)


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


def _build_plate(model, plate: FloorPlate, thickness_m: float, tint: tuple[float, float, float]) -> None:
    polygon = plate.polygon_in
    if len(polygon) < 3:
        raise SolidWorksError(f"{plate.feature_name} has no outline.")
    try:
        select_top_plane(model)
        sketch = model.SketchManager
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
        with contextlib.suppress(Exception):
            sketch.DisplayWhenAdded = False
        sketch.InsertSketch(True)
        try:
            count = len(polygon)
            for index in range(count):
                x0, z0 = polygon[index]
                x1, z1 = polygon[(index + 1) % count]
                _create_line(sketch, x0 * _INCH, z0 * _INCH, x1 * _INCH, z1 * _INCH)
        finally:
            with contextlib.suppress(Exception):
                sketch.AddToDB = False
            with contextlib.suppress(Exception):
                sketch.DisplayWhenAdded = True
            with contextlib.suppress(Exception):
                sketch.InsertSketch(True)
            with contextlib.suppress(Exception):
                model.ClearSelection2(True)
    except SolidWorksError:
        _close_sketch(model)
        raise
    except Exception as exc:
        _close_sketch(model)
        raise SolidWorksError(f"{plate.feature_name} sketch failed ({_where(exc)}): {format_com_error(exc)}") from exc

    sketch_feature = model.FeatureByPositionReverse(0)
    if sketch_feature is None:
        raise SolidWorksError(f"{plate.feature_name} sketch was not created.")
    rename_feature(sketch_feature, plate.sketch_name)
    try:
        if not sketch_feature.Select2(False, 0):
            raise SolidWorksError(f"Could not select {plate.sketch_name}.")
        # Dir reversed: the plate hangs below the shell datum, top face at Y = 0.
        feature = extrude_blind(model.FeatureManager, thickness_m, merge=False, reverse=True)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"{plate.feature_name} extrude failed ({_where(exc)}): {format_com_error(exc)}") from exc
    rename_feature(feature, plate.feature_name)
    _hide_sketch(model, plate.sketch_name)
    _tint(model, feature, tint)


def _draw_rim(model, radius_m: float) -> None:
    try:
        select_top_plane(model)
        sketch = model.SketchManager
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
        with contextlib.suppress(Exception):
            sketch.DisplayWhenAdded = False
        sketch.InsertSketch(True)
        circle = sketch.CreateCircleByRadius(0.0, 0.0, 0.0, float(radius_m))
        if circle is None:
            _close_sketch(model)
            return
        with contextlib.suppress(Exception):
            circle.ConstructionGeometry = True
        _close_sketch(model)
    except Exception:
        _close_sketch(model)
        return
    feature = model.FeatureByPositionReverse(0)
    if feature is not None:
        rename_feature(feature, RIM_NAME)


def _frame_view(model) -> None:
    """Top view, framed on the floor circle, and left there while rows appear."""
    with contextlib.suppress(Exception):
        model.ShowNamedView2("*Top", 5)
    rim = find_feature(model, RIM_NAME)
    if rim is not None:
        with contextlib.suppress(Exception):
            model.ClearSelection2(True)
            rim.Select2(False, 0)
            model.ViewZoomtoselection()
            model.ClearSelection2(True)
            return
    with contextlib.suppress(Exception):
        model.ViewZoomtofit2()


def _create_line(sketch, x0: float, y0: float, x1: float, y1: float) -> None:
    for _ in range(2):
        segment = sketch.CreateLine(float(x0), float(y0), 0.0, float(x1), float(y1), 0.0)
        if segment is not None:
            return
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
    raise SolidWorksError(f"Floor line failed ({x0:.4f}, {y0:.4f}) to ({x1:.4f}, {y1:.4f}).")


def _close_sketch(model) -> None:
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = False
    with contextlib.suppress(Exception):
        sketch.DisplayWhenAdded = True
    with contextlib.suppress(Exception):
        sketch.InsertSketch(True)
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


def _tint(model, feature, rgb: tuple[float, float, float]) -> None:
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)
        if not feature.Select2(False, 0):
            return
        model.MaterialPropertyValues = (
            float(rgb[0]),
            float(rgb[1]),
            float(rgb[2]),
            1.0,
            1.0,
            0.8,
            0.25,
            0.0,
            0.0,
        )
        model.ClearSelection2(True)


def _redraw(model) -> None:
    with contextlib.suppress(Exception):
        view = model.ActiveView
        view.EnableGraphicsUpdate = True
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()
    with contextlib.suppress(Exception):
        model.WindowRedraw()


def _delete_floor_features(model) -> None:
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
