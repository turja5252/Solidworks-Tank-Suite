"""Rolled outer stringer in SolidWorks, with burn holes.

The plate is a sheet-metal loft between two arcs, so it is born as sheet metal.
Flatten and Save As DXF stay in SolidWorks. The flat pattern stays suppressed
so the bent plate stays on screen until Flatten is clicked.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rename_feature
from swauto.parts import new_part
from swauto.stair.stringer import (
    BOLT_DIA_IN,
    THICKNESS_IN,
    TOP_HOLE_DIA_IN,
    StringerMock,
    layout_stringer,
)
from swauto.tank.shell import (
    _clear_selection,
    _close_sketch,
    _delete_feature,
    _ensure_tank_axis,
    _feature_name,
    _latest_feature,
    _open_sketch,
    containing_plane_angle,
)

FEATURE_PREFIX = "EliteStringer"
BOTTOM_ARC = f"{FEATURE_PREFIX}Bot"
TOP_ARC = f"{FEATURE_PREFIX}Top"
TOP_PLANE = f"{FEATURE_PREFIX}TopPln"
_INCH = 0.0254


class StringerResult:
    def __init__(self, title: str, model, note: str) -> None:
        self.title = title
        self.model = model
        self.note = note


def create_stringer_try(app, spec: StringerMock) -> StringerResult:
    """Open a new part: rolled sheet-metal plate with burn holes."""
    spec.validate()
    layout = layout_stringer(spec)
    model = new_part(app)
    _activate(app, model)
    try:
        _loft_plate(model, layout)
        cut_count, hole_count = _cut_holes(model, layout)
        _keep_bent_view(model)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Stringer failed ({_where(exc)}): {format_com_error(exc)}") from exc
    with contextlib.suppress(Exception):
        model.ViewZoomtofit2()
    title = _title(model)
    note = (
        f"Bent 3/8 in plate, true length {layout.x1_in - layout.x0_in:.2f} in. "
        f"{cut_count} of {hole_count} burn holes are through it. "
        "Click Flatten, then File > Save As > DXF. "
        "The bent plate stays on screen until you click Flatten."
    )
    return StringerResult(title=title, model=model, note=note)


def _title(model) -> str:
    try:
        return str(com_value(model.GetTitle) or "Part")
    except Exception:
        return "Part"


def _loft_plate(model, layout) -> None:
    """Sheet-metal cylinder between two arcs. Thickness is the 3/8 in plate."""
    radius = layout.outside_radius_in * _INCH
    span = layout.x1_in - layout.x0_in
    angle = span / layout.outside_radius_in
    # Top-plane sketch +Y is world −Z, so negative sketch Y is world +Z.
    start = (radius, 0.0)
    end = (radius * math.cos(angle), -radius * math.sin(angle))
    top = find_feature(model, "Top Plane") or find_feature(model, "Top")
    if top is None:
        raise SolidWorksError("Could not find the Top Plane.")
    _open_sketch(model, top)
    try:
        _draw_arc(model, start, end)
    except Exception:
        _recover(model)
        raise
    _close_sketch(model)
    _rename_latest(model, BOTTOM_ARC, "bottom arc")
    raised = _offset_plane(model, top, layout.plate_width_in * _INCH, False, TOP_PLANE)
    if raised is None:
        raise SolidWorksError("Could not raise the top edge of the stringer.")
    _open_sketch(model, raised)
    try:
        _draw_arc(model, start, end)
    except Exception:
        _recover(model)
        raise
    _close_sketch(model)
    _rename_latest(model, TOP_ARC, "top arc")
    nothing = com_nothing()
    _clear_selection(model)
    if not model.Extension.SelectByID2(BOTTOM_ARC, "SKETCH", 0.0, 0.0, 0.0, False, 1, nothing, 0):
        raise SolidWorksError("Could not select the bottom arc.")
    if not model.Extension.SelectByID2(TOP_ARC, "SKETCH", 0.0, 0.0, 0.0, True, 1, nothing, 0):
        raise SolidWorksError("Could not select the top arc.")
    method = getattr(model.FeatureManager, "InsertSheetMetalLoftedBend", None)
    if not callable(method):
        raise SolidWorksError("Lofted bend is not on this SolidWorks interface.")
    errors: list[str] = []
    feature = None
    for args in ((THICKNESS_IN * _INCH, THICKNESS_IN * _INCH),):
        _clear_selection(model)
        model.Extension.SelectByID2(BOTTOM_ARC, "SKETCH", 0.0, 0.0, 0.0, False, 1, nothing, 0)
        model.Extension.SelectByID2(TOP_ARC, "SKETCH", 0.0, 0.0, 0.0, True, 1, nothing, 0)
        try:
            feature = method(*args)
        except Exception as exc:
            errors.append(format_com_error(exc))
            feature = None
            continue
        if feature is not None:
            break
    if feature is None:
        detail = "; ".join(errors) if errors else "returned nothing"
        raise SolidWorksError(f"Lofted bend failed ({detail}).")


def _draw_arc(model, start: tuple[float, float], end: tuple[float, float]) -> None:
    arc = model.SketchManager.CreateArc(0.0, 0.0, 0.0, start[0], start[1], 0.0, end[0], end[1], 0.0, -1)
    if arc is None:
        raise SolidWorksError("Could not draw the stringer arc.")


def _keep_bent_view(model) -> None:
    """Leave Flatten for the user. An unsuppressed flat pattern hides the bend."""
    for feature in iter_features(model):
        name = _feature_name(feature)
        if not name.startswith("Flat-Pattern"):
            continue
        with contextlib.suppress(Exception):
            if com_value(feature.IsSuppressed):
                continue
        with contextlib.suppress(Exception):
            feature.SetSuppression2(0, 2, None)


def _cut_holes(model, layout) -> tuple[int, int]:
    holes: list[tuple[float, float, float]] = []
    for tread in layout.treads:
        for along in tread.hole_along_in:
            holes.append((along, tread.hole_offset_in, BOLT_DIA_IN))
    for along, offset in layout.top_holes_in:
        holes.append((along, offset, TOP_HOLE_DIA_IN))
    axis = _ensure_tank_axis(model)
    cut_count = 0
    for index, (along, offset, diameter) in enumerate(holes, start=1):
        try:
            if _cut_one_hole(model, axis, layout, index, along, offset, diameter):
                cut_count += 1
        except Exception:
            _recover(model)
            _delete_named(
                model,
                (
                    f"{FEATURE_PREFIX}Ang{index:02d}",
                    f"{FEATURE_PREFIX}Face{index:02d}",
                    f"{FEATURE_PREFIX}H{index:02d}Sk",
                ),
            )
    return cut_count, len(holes)


def _cut_one_hole(model, axis, layout, index: int, along_in: float, offset_in: float, diameter_in: float) -> bool:
    theta = (along_in - layout.x0_in) / layout.outside_radius_in
    y_m = (layout.plate_width_in / 2.0 + offset_in) * _INCH
    radius_m = layout.outside_radius_in * _INCH
    face_name = f"{FEATURE_PREFIX}Face{index:02d}"
    sketch_name = f"{FEATURE_PREFIX}H{index:02d}Sk"
    cut_name = f"{FEATURE_PREFIX}H{index:02d}"
    ang_name = f"{FEATURE_PREFIX}Ang{index:02d}"
    plane = _tangent_plane(model, axis, theta, radius_m, ang_name, face_name)
    if plane is None:
        return False
    before_sketch = _names(model)
    _open_sketch(model, plane)
    try:
        circle = _create_circle(model.SketchManager, 0.0, y_m, (diameter_in / 2.0) * _INCH)
        if circle is None:
            raise SolidWorksError("Hole circle was not created.")
    except Exception:
        _recover(model)
        _delete_named(model, (face_name, sketch_name, ang_name))
        return False
    _close_sketch(model)
    sketch = _rename_new(model, before_sketch, sketch_name, "hole sketch")
    if _cut_through(model, sketch, cut_name):
        return True
    _delete_named(model, (face_name, sketch_name, cut_name, ang_name))
    return False


def _tangent_plane(model, axis, theta: float, radius_m: float, ang_name: str, face_name: str):
    """Plane on the outside face, normal pointing outward (through-thickness).

    Shell's angled plane is radial (through the axis). The radial plane whose
    azimuth is ``theta + 90°`` has the same normal as the tangent at ``theta``.
    Offset that plane by the outside radius and it sits on the outer face.
    """
    fold = containing_plane_angle(theta + math.pi / 2.0)
    if abs(fold) <= 1e-5:
        base = find_feature(model, "Front Plane") or find_feature(model, "Front")
    else:
        base = _angled_plane(model, axis, fold, ang_name)
    for flip in (False, True):
        plane = _offset_plane(model, base, radius_m, flip, face_name)
        if plane is not None:
            return plane
    return None


def _angled_plane(model, axis, angle: float, name: str):
    """Fold a plane off Front. Flat-Pattern stays last, so the new plane is not the tree tip."""
    from swauto.parts import select_plane

    before = _names(model)
    _clear_selection(model)
    if not (select_plane(model, "Front Plane") or select_plane(model, "Front")):
        raise SolidWorksError("Could not select the Front Plane for a hole.")
    if not _select_feature(model, axis, "AXIS", mark=1, append=True):
        raise SolidWorksError("Could not select the tank axis for a hole.")
    method = getattr(model, "CreatePlaneAtAngle", None)
    if not callable(method):
        raise SolidWorksError("CreatePlaneAtAngle is not on this SolidWorks interface.")
    try:
        method(float(angle), False)
    except Exception as exc:
        _clear_selection(model)
        raise SolidWorksError(f"Could not create a hole plane ({format_com_error(exc)}).") from exc
    _clear_selection(model)
    return _rename_new(model, before, name, "hole plane")


def _offset_plane(model, base, distance_m: float, flip: bool, name: str):
    _delete_named(model, (name,))
    before = _names(model)
    _clear_selection(model)
    if not _select_feature(model, base, "PLANE", mark=0, append=False):
        return None
    method = getattr(model, "CreatePlaneAtOffset", None)
    if not callable(method):
        return None
    try:
        method(float(distance_m), bool(flip))
    except Exception:
        _clear_selection(model)
        return None
    _clear_selection(model)
    try:
        return _rename_new(model, before, name, "offset plane")
    except SolidWorksError:
        return None


def _names(model) -> set[str]:
    return {_feature_name(feature) for feature in iter_features(model)} - {""}


def _rename_new(model, before: set[str], name: str, what: str):
    feature = None
    for candidate in iter_features(model):
        current = _feature_name(candidate)
        if current and current not in before:
            feature = candidate
            break
    if feature is None:
        raise SolidWorksError(f"Missing {what}.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    # find_feature returns the oldest feature with this name. A failed earlier
    # attempt may still hold it, and handing that back selects the stale helix
    # or sketch. Use the lookup only when this new feature actually took the name.
    if _feature_name(feature) == name:
        return find_feature(model, name) or feature
    return feature


def _cut_through(model, sketch, name: str) -> bool:
    """Extruded cut. SW 2013 FeatureCut3 needs the 26-arg form or it rejects the call."""
    method = getattr(model.FeatureManager, "FeatureCut3", None)
    if not callable(method):
        return False
    extra = (True, False, 0, 0.0, False)
    depth = (THICKNESS_IN + 0.08) * _INCH
    attempts = (
        (True, False, False, 0, 0, depth, 0.0, False, False, False, False, 0.0, 0.0, False, False, False, False, False, True, True, True) + extra,
        (True, True, False, 0, 0, depth, 0.0, False, False, False, False, 0.0, 0.0, False, False, False, False, False, True, True, True) + extra,
        (True, False, False, 1, 0, 0.01, 0.01, False, False, False, False, 0.0, 0.0, False, False, False, False, False, True, True, True) + extra,
        (True, True, False, 1, 0, 0.01, 0.01, False, False, False, False, 0.0, 0.0, False, False, False, False, False, True, True, True) + extra,
    )
    for args in attempts:
        _clear_selection(model)
        if not _select_feature(model, sketch, "SKETCH", mark=0, append=False):
            return False
        try:
            feature = method(*args)
        except Exception:
            continue
        if feature is not None:
            with contextlib.suppress(Exception):
                rename_feature(feature, name)
            return True
    return False


def _convert_to_sheet_metal(model, layout) -> bool:
    r_mid = (layout.outside_radius_in - THICKNESS_IN / 2.0) * _INCH
    y_mid = (layout.plate_width_in / 2.0) * _INCH
    nothing = com_nothing()
    _clear_selection(model)
    try:
        ok = model.Extension.SelectByID2("", "FACE", r_mid, y_mid, 0.0, False, 0, nothing, 0)
    except Exception:
        ok = False
    if not ok:
        return False
    before = _feature_name(_latest_feature(model))
    method = getattr(model.FeatureManager, "InsertConvertToSheetMetal2", None)
    if not callable(method):
        return False
    thk = THICKNESS_IN * _INCH
    try:
        method(thk, False, False, 0.001, 0.001, 0, 0.5, 1, 0.5, False)
    except Exception:
        return False
    latest = _feature_name(_latest_feature(model))
    return bool(latest) and latest != before and "EliteStringerH" not in latest


def _create_circle(sketch, x_m: float, y_m: float, radius_m: float):
    for _ in range(2):
        circle = None
        with contextlib.suppress(Exception):
            circle = sketch.CreateCircleByRadius(float(x_m), float(y_m), 0.0, float(radius_m))
        if circle is None:
            with contextlib.suppress(Exception):
                circle = sketch.CreateCircle(
                    float(x_m), float(y_m), 0.0, float(x_m) + float(radius_m), float(y_m), 0.0
                )
        if circle is not None:
            return circle
        with contextlib.suppress(Exception):
            sketch.AddToDB = True
    return None


def _select_feature(model, feature, kind: str, *, mark: int, append: bool) -> bool:
    with contextlib.suppress(Exception):
        if feature.Select2(bool(append), int(mark)):
            return True
    name = _feature_name(feature)
    if not name:
        return False
    nothing = com_nothing()
    try:
        return bool(model.Extension.SelectByID2(name, kind, 0.0, 0.0, 0.0, bool(append), int(mark), nothing, 0))
    except Exception:
        return False


def _rename_latest(model, name: str, what: str):
    feature = _latest_feature(model)
    if feature is None:
        raise SolidWorksError(f"Missing {what}.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    return find_feature(model, name) or feature


def _delete_named(model, names: tuple[str, ...]) -> None:
    for name in names:
        feature = find_feature(model, name)
        if feature is not None:
            _delete_feature(model, feature)


def _recover(model) -> None:
    with contextlib.suppress(Exception):
        sketch = com_value(model.GetActiveSketch2)
        if sketch is not None:
            _close_sketch(model)
    _clear_selection(model)


def _activate(app, model) -> None:
    with contextlib.suppress(Exception):
        app.Visible = True
    title = str(com_value(model.GetTitle) or "")
    if not title:
        return
    for method_name, args in (
        ("ActivateDoc", (title,)),
        ("ActivateDoc3", (title, False, 0)),
    ):
        method = getattr(app, method_name, None)
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


def _where(exc: BaseException) -> str:
    tb = exc.__traceback__
    chosen = None
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename.replace("\\", "/")
        if "/swauto/" in filename or "/stair/" in filename:
            chosen = tb
        tb = tb.tb_next
    if chosen is None:
        return type(exc).__name__
    short = chosen.tb_frame.f_code.co_filename.replace("\\", "/").rsplit("/", 1)[-1]
    return f"{short} {chosen.tb_frame.f_code.co_name} line {chosen.tb_lineno}"
