"""Build / rebuild a multi-course tank shell in SolidWorks (2013-safe).

Each shell plate is its own curved solid: a limited-angle revolve of the wall
rectangle. The sketch plane is the vertical plane that contains that plate's
start azimuth, so stagger is the revolve start — not a later body move, and
not 3D seam lines on one ring.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import as_model_doc, com_nothing, com_value, format_com_error
from swauto.display import display_frozen, redraw, set_display_live
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rebuild, rename_feature
from swauto.parts import new_part, select_front_plane, select_plane
from swauto.tank.plates import layout_plates
from swauto.tank.spec import TankSpec

FEATURE_PREFIX = "EliteTank"
AXIS_NAME = f"{FEATURE_PREFIX}Axis"
AXIS_SKETCH = f"{FEATURE_PREFIX}AxisSk"


def signed_angle_delta(start: float, end: float) -> float:
    """Signed angle from ``start`` to ``end``, wrapped to (-pi, pi]."""
    return (end - start + math.pi) % (2.0 * math.pi) - math.pi


def containing_plane_angle(azimuth: float) -> float:
    """Angle from the Front plane of the vertical plane that contains ``azimuth``.

    A plane through the tank axis is the same plane π radians later, so the
    result is folded into (-π/2, π/2]. Zero means the Front plane itself.
    """
    return (azimuth + math.pi / 2.0) % math.pi - math.pi / 2.0


def _com_attr(obj, name: str):
    """COM getattr. A missing member raises, it does not return None."""
    try:
        return getattr(obj, name)
    except Exception:
        return None


def radius_sign_for_azimuth(sketch_radial_azimuth: float, desired: float) -> float:
    """+1 when sketch +radial lies on ``desired``, -1 when it lies on the opposite side."""
    same = abs(signed_angle_delta(sketch_radial_azimuth, desired))
    flipped = abs(signed_angle_delta(sketch_radial_azimuth + math.pi, desired))
    return 1.0 if same <= flipped else -1.0


class LiveTank:
    def __init__(self, title: str, spec: TankSpec, model: object | None = None) -> None:
        self.title = title
        self.spec = spec
        self.model = model

    def update(self, app, spec: TankSpec) -> None:
        spec.validate()
        model = self._resolve_model(app)
        _delete_elite_tank_features(model)
        _build_shell_on_model(model, spec)
        self.spec = spec
        self.title = str(com_value(model.GetTitle) or self.title)
        self.model = model

    def _resolve_model(self, app):
        if self.model is not None:
            try:
                if str(com_value(self.model.GetTitle) or ""):
                    return self.model
            except Exception:
                self.model = None
        active = com_value(app.ActiveDoc)
        if active is not None:
            title = str(com_value(active.GetTitle) or "")
            if title == self.title or title.startswith(self.title.split(".")[0]):
                self.model = active
                return active
        raise SolidWorksError(
            f"Could not find open tank part {self.title!r}.\n"
            "Activate it in SolidWorks, then change values again."
        )


class TankResult:
    def __init__(self, title: str, spec: TankSpec, live: LiveTank, note: str = "") -> None:
        self.title = title
        self.spec = spec
        self.live = live
        self.note = note


def create_tank_shell(app, spec: TankSpec) -> TankResult:
    spec.validate()
    try:
        model = new_part(app)
        note = _build_shell_on_model(model, spec)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Tank shell failed ({_fail_site(exc)}): {format_com_error(exc)}") from exc

    title = str(com_value(model.GetTitle) or "Part")
    live = LiveTank(title=title, spec=spec, model=model)
    return TankResult(title=title, spec=spec, live=live, note=note)


def _fail_site(exc: BaseException) -> str:
    """Point at our code. COM errors are raised inside win32com's __call__."""
    tb = exc.__traceback__
    chosen = None
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename.replace("\\", "/")
        if "/swauto/" in filename or filename.endswith("/swauto"):
            chosen = tb
        tb = tb.tb_next
    if chosen is None:
        return type(exc).__name__
    short = chosen.tb_frame.f_code.co_filename.replace("\\", "/").rsplit("/", 1)[-1]
    return f"{short} {chosen.tb_frame.f_code.co_name} line {chosen.tb_lineno}"


def _error_text(exc: BaseException) -> str:
    return f"{_fail_site(exc)}: {format_com_error(exc)}"


def _build_shell_on_model(model, spec: TankSpec) -> str:
    """Curved plates only. A failure stays a failure — do not substitute seam lines."""
    try:
        warnings = _build_individual_curved_plates(model, spec)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Curved plates failed ({_fail_site(exc)}): {format_com_error(exc)}") from exc
    rebuild(model)
    with contextlib.suppress(Exception):
        model.ViewZoomtofit2()
    if not warnings:
        return ""
    if len(warnings) == 1:
        return warnings[0]
    return f"{len(warnings)} plates were not finished. {warnings[0]}"


def _build_individual_curved_plates(model, spec: TankSpec) -> list[str]:
    plates = layout_plates(spec)
    if not plates:
        raise SolidWorksError("No plates to build.")

    top = max(plate.z_bot_m + plate.height_m for plate in plates)
    _ensure_axis_sketch(model, top)
    axis = _ensure_tank_axis(model)
    warnings: list[str] = []
    built = 0
    # Freeze paints while a course's plates are created; flash the view at each
    # course boundary so the shell still "grows" without waiting on every plate.
    course_no = None
    set_display_live(model, False)
    try:
        for plate in plates:
            if course_no is not None and plate.course_no != course_no:
                redraw(model)
                set_display_live(model, False)
            course_no = plate.course_no
            try:
                warning = _build_one_plate(model, plate, axis)
            except SolidWorksError as exc:
                warnings.append(str(exc))
                continue
            built += 1
            if warning:
                warnings.append(warning)
    finally:
        redraw(model)
    _hide_construction_geometry(model)
    if built == 0:
        detail = "\n".join(warnings) if warnings else "No plate revolve succeeded."
        raise SolidWorksError(f"No curved plates were created.\n{detail}")
    return warnings


def _hide_construction_geometry(model) -> None:
    """The plate sketch needs its plane. Blank it so the plane is not drawn."""
    for feat in list(iter_features(model)):
        name = _feature_name(feat)
        if name == AXIS_NAME:
            kind = "AXIS"
        elif name.startswith(FEATURE_PREFIX) and name.endswith("Pln"):
            kind = "PLANE"
        else:
            continue
        _blank_reference(model, feat, name, kind)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()


def _blank_reference(model, feature, name: str, kind: str) -> None:
    _clear_selection(model)
    selected = False
    extension = _com_attr(model, "Extension")
    nothing = com_nothing()
    if extension is not None and name:
        with contextlib.suppress(Exception):
            selected = bool(extension.SelectByID2(name, kind, 0.0, 0.0, 0.0, False, 0, nothing, 0))
    if not selected:
        with contextlib.suppress(Exception):
            selected = bool(feature.Select2(False, 0))
    if not selected:
        return
    blank = _com_attr(model, "BlankRefGeom")
    if blank is not None:
        with contextlib.suppress(Exception):
            blank()
    _clear_selection(model)


def _build_one_plate(model, plate, axis) -> str | None:
    name = plate.feature_name
    sweep = 2.0 * math.pi if plate.is_full_ring else float(plate.sweep_rad)
    if sweep <= 1e-9:
        raise SolidWorksError(f"{name}: zero sweep.")
    desired = 0.0 if plate.is_full_ring else float(plate.start_rad) % (2.0 * math.pi)
    plane_angle = 0.0 if plate.is_full_ring else containing_plane_angle(desired)

    try:
        _revolve_plate(
            model,
            name=name,
            ri=float(plate.inner_r_m),
            ro=float(plate.outer_r_m),
            y0=float(plate.z_bot_m),
            y1=float(plate.z_bot_m) + float(plate.height_m),
            sweep=sweep,
            desired=desired,
            plane_angle=plane_angle,
            axis=axis,
        )
        return None
    except Exception as first_exc:
        first_error = _error_text(first_exc)
        _safe_cleanup(model, name)

    # Angled plane was not available. Revolve on Front — the call that already
    # works on this SolidWorks — then spin that body about the tank axis.
    if plate.is_full_ring or abs(plane_angle) <= 1e-5:
        raise SolidWorksError(f"{name}: {first_error}")
    try:
        feature = _revolve_plate(
            model,
            name=name,
            ri=float(plate.inner_r_m),
            ro=float(plate.outer_r_m),
            y0=float(plate.z_bot_m),
            y1=float(plate.z_bot_m) + float(plate.height_m),
            sweep=sweep,
            desired=0.0,
            plane_angle=0.0,
            axis=axis,
        )
    except Exception as second_exc:
        raise SolidWorksError(
            f"{name}: curved plate was not created.\n{first_error}\n{_error_text(second_exc)}"
        ) from second_exc
    try:
        _rotate_body_about_y(model, feature, desired)
    except Exception as rot_exc:
        return (
            f"{name} is a curved plate, but stagger failed ({_error_text(rot_exc)}). "
            f"Angled plane was not used ({first_error})."
        )
    return None


def _revolve_plate(
    model,
    *,
    name: str,
    ri: float,
    ro: float,
    y0: float,
    y1: float,
    sweep: float,
    desired: float,
    plane_angle: float,
    axis,
) -> object:
    """Limited revolve. Profile sits at ``desired``; sweep grows in +azimuth."""
    model = as_model_doc(model)
    plane = None
    if abs(plane_angle) > 1e-5:
        plane = _create_angled_plane(model, axis, plane_angle, f"{name}Pln")

    _open_sketch(model, plane)
    try:
        # Same wall rectangle as the revolve that already works: sketch X is
        # radial, sketch Y is height. r_sign puts the profile on the start side.
        _draw_plate_profile(
            model.SketchManager,
            ri=ri,
            ro=ro,
            y0=y0,
            y1=y1,
            r_sign=radius_sign_for_azimuth(plane_angle, desired),
            radial_is_x=True,
            rad_len=1.0,
            height_scale=1.0,
        )
    except Exception:
        _recover_sketch(model)
        raise
    _close_sketch(model)

    sketch = model.FeatureByPositionReverse(0)
    if sketch is None:
        raise SolidWorksError(f"{name}: missing sketch.")
    sk_name = f"{name}Sk"
    rename_feature(sketch, sk_name)
    if not sketch.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select sketch.")
    _select_sketch_axis(model, sk_name)

    # +Y right-hand revolve decreases atan2(z, x). Reverse so the plate
    # occupies [desired, desired + sweep] in the layout's azimuth.
    feat = _revolve_angle(model, sweep, merge=False, reverse=True)
    if feat is None:
        raise SolidWorksError(f"{name}: revolve failed.")
    # Reading Feature.Name is missing on some SW2013 return values. The solid
    # already exists; a failed rename must not discard it or skip later plates.
    created = _feature_name(feat)
    if created == sk_name or (created.endswith("Sk") and created.startswith(name)):
        raise SolidWorksError(f"{name}: revolve did not create a solid.")
    with contextlib.suppress(Exception):
        rename_feature(feat, name)
    renamed = None
    with contextlib.suppress(Exception):
        renamed = find_feature(model, name)
    return renamed or feat


def _feature_name(feature) -> str:
    try:
        return str(com_value(feature.Name) or "")
    except Exception:
        return ""


def _draw_plate_profile(
    sk,
    *,
    ri: float,
    ro: float,
    y0: float,
    y1: float,
    r_sign: float,
    radial_is_x: bool,
    rad_len: float,
    height_scale: float,
) -> None:
    def xy(radius: float, height: float) -> tuple[float, float]:
        radial = (r_sign * radius) / rad_len
        along = height / height_scale
        if radial_is_x:
            return radial, along
        return along, radial

    y_axis = max(y1, y0, 0.05)
    x0, h0 = xy(0.0, 0.0)
    x1, h1 = xy(0.0, y_axis)
    _create_axis_segment(sk, x0, h0, x1, h1)

    points = (
        xy(ri, y0),
        xy(ro, y0),
        xy(ro, y1),
        xy(ri, y1),
        xy(ri, y0),
    )
    for (sx, sy), (ex, ey) in zip(points, points[1:], strict=False):
        _create_profile_line(sk, sx, sy, ex, ey)


def _create_profile_line(sk, x0: float, y0: float, x1: float, y1: float) -> None:
    """Draw one wall edge.

    CreateLine returns Nothing when SolidWorks tries to snap the line in the
    graphics window and the window is not driving the sketch. AddToDB writes
    the line into the sketch database instead. Retry once after turning that on.
    """
    for _ in range(2):
        segment = sk.CreateLine(float(x0), float(y0), 0.0, float(x1), float(y1), 0.0)
        if segment is not None:
            return
        with contextlib.suppress(Exception):
            sk.AddToDB = True
    raise SolidWorksError(
        f"Plate profile line failed ({x0:.4f}, {y0:.4f}) to ({x1:.4f}, {y1:.4f})."
    )


def _create_axis_segment(sk, x0: float, y0: float, x1: float, y1: float) -> None:
    axis = None
    with contextlib.suppress(Exception):
        axis = sk.CreateCenterLine(float(x0), float(y0), 0.0, float(x1), float(y1), 0.0)
    if axis is None:
        axis = sk.CreateLine(float(x0), float(y0), 0.0, float(x1), float(y1), 0.0)
    if axis is None:
        raise SolidWorksError("Could not create the tank axis line.")
    with contextlib.suppress(Exception):
        axis.ConstructionGeometry = True


def _open_sketch(model, plane) -> None:
    model.ClearSelection2(True)
    if plane is None:
        select_front_plane(model)
    elif not plane.Select2(False, 0):
        name = str(com_value(plane.Name) or "")
        if not select_plane(model, name):
            raise SolidWorksError(f"Could not select sketch plane {name or '(unnamed)'}.")
    sketch_manager = model.SketchManager
    # The Tank Properties window is in front while this runs. Sketch lines are
    # rejected unless they are written straight into the sketch database.
    with contextlib.suppress(Exception):
        sketch_manager.AddToDB = True
    with contextlib.suppress(Exception):
        sketch_manager.DisplayWhenAdded = False
    sketch_manager.InsertSketch(True)


def _close_sketch(model) -> None:
    sketch_manager = model.SketchManager
    with contextlib.suppress(Exception):
        sketch_manager.AddToDB = False
    with contextlib.suppress(Exception):
        sketch_manager.DisplayWhenAdded = True
    with contextlib.suppress(Exception):
        sketch_manager.InsertSketch(True)
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)


def _safe_cleanup(model, feature_name: str) -> None:
    with contextlib.suppress(Exception):
        _recover_sketch(model)
    with contextlib.suppress(Exception):
        _delete_plate_features(model, feature_name)


def _recover_sketch(model) -> None:
    if _active_sketch(model) is not None:
        _close_sketch(model)
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)


def _create_angled_plane(model, axis, angle: float, name: str):
    """Plane through the tank axis, folded off the Front plane by ``angle``.

    InsertRefPlane on this SolidWorks 2013 returns a second Front plane and
    ignores the angle, which stacks the side plates on the front ones.
    CreatePlaneAtAngle is the call that rotates. It returns Nothing even when
    the plane exists, so the new feature is taken from the tree.

    A Front∩Right axis and the axis sketch line spin in opposite directions.
    The angle passed in already matches the axis. The sketch line needs the
    opposite sign so sketch +X still lies on ``angle``.
    """
    sense = _select_plane_pivot(model, axis)
    if sense is None:
        raise SolidWorksError("Could not select a tank axis for the plate plane.")
    method = _com_attr(model, "CreatePlaneAtAngle")
    if method is None:
        raise SolidWorksError("CreatePlaneAtAngle is not on this SolidWorks interface.")

    api_angle = float(angle) if sense == "axis" else -float(angle)
    before = _feature_name(_latest_feature(model))
    try:
        method(api_angle, False)
    except Exception as exc:
        _clear_selection(model)
        raise SolidWorksError(f"Could not create a plate plane ({format_com_error(exc)}).") from exc
    _clear_selection(model)

    feat = _latest_feature(model)
    if feat is None or _feature_name(feat) in ("", before):
        raise SolidWorksError("Plate plane did not appear in the feature tree.")
    if _plane_is_front_copy(feat):
        _delete_feature(model, feat)
        raise SolidWorksError("CreatePlaneAtAngle left the plate on the Front plane.")
    with contextlib.suppress(Exception):
        rename_feature(feat, name)
    return find_feature(model, name) or feat


def _select_plane_pivot(model, axis) -> str | None:
    """Select Front plus the pivot. Return 'axis' or 'line'."""
    _clear_selection(model)
    if not (select_plane(model, "Front Plane") or select_plane(model, "Front")):
        return None
    if _select_axis_feature(model, axis):
        return "axis"
    if _select_named_line(model, f"Line1@{AXIS_SKETCH}", append=True, mark=1):
        return "line"
    return None


def _select_axis_feature(model, axis) -> bool:
    names: list[str] = []
    if axis is not None and not isinstance(axis, bool):
        named = _feature_name(axis)
        if named:
            names.append(named)
    names.extend((AXIS_NAME, "Axis1", "Axis2"))
    nothing = com_nothing()
    extension = _com_attr(model, "Extension")
    if extension is None:
        return False
    seen: set[str] = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            if extension.SelectByID2(name, "AXIS", 0.0, 0.0, 0.0, True, 1, nothing, 0):
                return True
        except Exception:
            continue
    if axis is None or isinstance(axis, bool):
        return False
    with contextlib.suppress(Exception):
        return bool(axis.Select2(True, 1))
    return False


def _plane_is_front_copy(feat) -> bool:
    """True when the new plane is still the Front plane (angle was ignored)."""
    try:
        specific = com_value(feat.GetSpecificFeature2)
        raw = com_value(specific.GetRefPlaneParams)
        vals = [float(v) for v in raw]
    except Exception:
        return False
    if len(vals) < 9:
        return False
    x_axis, normal = vals[3:6], vals[6:9]
    return (
        abs(x_axis[0] - 1.0) < 1e-3
        and abs(x_axis[1]) < 1e-3
        and abs(x_axis[2]) < 1e-3
        and abs(normal[0]) < 1e-3
        and abs(normal[1]) < 1e-3
        and abs(abs(normal[2]) - 1.0) < 1e-3
    )


def _latest_feature(model):
    with contextlib.suppress(Exception):
        return model.FeatureByPositionReverse(0)
    return None


def _feature_added(model, before: set[str], prefer_prefix: str = ""):
    """First feature whose name was not in ``before``.

    Sheet-metal parts keep Flat-Pattern at the tree tip, so the feature just
    inserted is not FeatureByPositionReverse(0).
    """
    added = []
    for feature in iter_features(model):
        name = _feature_name(feature)
        if name and name not in before:
            added.append(feature)
    if prefer_prefix:
        for feature in added:
            if _feature_name(feature).startswith(prefer_prefix):
                return feature
    return added[0] if added else None


def _clear_selection(model) -> None:
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)


def _delete_feature(model, feature) -> None:
    with contextlib.suppress(Exception):
        _clear_selection(model)
        feature.Select2(False, 0)
        model.EditDelete()


def _ensure_axis_sketch(model, height_m: float) -> None:
    """Front-plane line on the tank axis. Used when InsertAxis2 is missing."""
    if find_feature(model, AXIS_SKETCH) is not None:
        return
    try:
        select_front_plane(model)
        sk = model.SketchManager
        sk.InsertSketch(True)
        _create_axis_segment(sk, 0.0, 0.0, 0.0, max(float(height_m), 0.1))
        _close_sketch(model)
        feat = model.FeatureByPositionReverse(0)
        if feat is not None:
            rename_feature(feat, AXIS_SKETCH)
    except Exception:
        _recover_sketch(model)


def _ensure_tank_axis(model):
    """Vertical axis through Front ∩ Right. Never abort plate creation if this is missing."""
    try:
        doc = as_model_doc(model)
    except Exception:
        doc = model
    try:
        return _create_tank_axis(doc)
    except Exception:
        return None


def _create_tank_axis(model):
    existing = find_feature(model, AXIS_NAME)
    if existing is not None:
        return existing
    for fallback in ("Axis1", "Axis2"):
        feat = find_feature(model, fallback)
        if feat is not None:
            rename_feature(feat, AXIS_NAME)
            return find_feature(model, AXIS_NAME) or feat

    _clear_selection(model)
    nothing = com_nothing()
    if not (select_plane(model, "Front Plane") or select_plane(model, "Front")):
        return None
    selected_right = False
    extension = _com_attr(model, "Extension")
    if extension is None:
        return None
    for plane_name in ("Right Plane", "Right", "Plane3"):
        try:
            if extension.SelectByID2(plane_name, "PLANE", 0.0, 0.0, 0.0, True, 0, nothing, 0):
                selected_right = True
                break
        except Exception:
            continue
    if not selected_right:
        _clear_selection(model)
        return None

    # InsertAxis2 returns True, not the feature. On a sheet-metal part the
    # flat pattern stays at the tree tip, so the new axis is found by name.
    before = {_feature_name(feature) for feature in iter_features(model)}
    created = None
    for method in (
        lambda: model.InsertAxis2(True),
        lambda: model.FeatureManager.InsertAxis2(True),
    ):
        try:
            method()
        except Exception:
            continue
        created = _feature_added(model, before, prefer_prefix="Axis")
        if created is not None:
            break
    _clear_selection(model)
    if created is None:
        return None
    with contextlib.suppress(Exception):
        rename_feature(created, AXIS_NAME)
    return find_feature(model, AXIS_NAME) or created


def _rotate_body_about_y(model, feature, azimuth: float):
    """Spin a Front-revolved plate onto ``azimuth``.

    InsertMoveCopyBody2 RotAngleY is a right-hand rotation about +Y, which
    decreases atan2(z, x). The layout azimuth increases toward +Z, so the
    body angle is the opposite of ``azimuth``.
    """
    if not _select_feature_body(model, feature):
        raise SolidWorksError("Could not select the plate body to stagger.")
    feature_manager = _com_attr(model, "FeatureManager")
    method = _com_attr(feature_manager, "InsertMoveCopyBody2") if feature_manager is not None else None
    if method is None:
        raise SolidWorksError("InsertMoveCopyBody2 is not on this SolidWorks interface.")
    # 12 arguments, RotAngleY 9th. An 11-argument call raises "Parameter not optional"
    # on this SolidWorks and does not move the body. Mark 1 on the body is required;
    # without it this call returns nothing.
    before = _feature_name(_latest_feature(model))
    moved = None
    error = ""
    try:
        moved = method(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -float(azimuth), 0.0, False, 1)
    except Exception as exc:
        error = _error_text(exc)
        moved = None
    if moved is None:
        latest = _latest_feature(model)
        if latest is not None and _feature_name(latest) not in ("", before):
            moved = latest
    if moved is None:
        detail = error or "returned nothing"
        raise SolidWorksError(f"Move/Copy Body did not stagger the plate ({detail}).")
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)
    with contextlib.suppress(Exception):
        rename_feature(moved, f"{com_value(feature.Name) or 'Plate'}Rot")
    return moved


def _select_feature_body(model, feature) -> bool:
    """Select the solid just created. SW2013 Move/Copy needs the body, mark 1."""
    with contextlib.suppress(Exception):
        model.ClearSelection2(True)
    with contextlib.suppress(Exception):
        rebuild(model)

    bodies = _solid_bodies(model)
    ordered = list(reversed(bodies))
    feature_name = _feature_name(feature)
    if feature_name:
        ordered.sort(key=lambda body: 0 if feature_name in _feature_name(body) else 1)

    for body in ordered:
        if _select_solid_body(model, body):
            return True

    nothing = com_nothing()
    extension = _com_attr(model, "Extension")
    if extension is None:
        return False
    for name in _body_name_guesses(feature_name, len(bodies)):
        try:
            if extension.SelectByID2(name, "SOLIDBODY", 0.0, 0.0, 0.0, False, 1, nothing, 0):
                return True
        except Exception:
            continue
    return False


def _body_name_guesses(feature_name: str, count: int) -> list[str]:
    names = []
    if feature_name:
        names.append(feature_name)
    for index in range(max(count, 1), 0, -1):
        names.extend(
            (
                f"Boss-Revolve{index}",
                f"Revolve{index}",
                f"Solid Body{index}",
                f"SolidBody{index}",
            )
        )
    return names


def _solid_bodies(model) -> list:
    targets = [model]
    with contextlib.suppress(Exception):
        from win32com.client import CastTo

        targets.insert(0, CastTo(model, "PartDoc"))
    for target in targets:
        getter = _com_attr(target, "GetBodies2")
        if getter is None:
            continue
        for args in ((0, False), (0, True)):
            try:
                raw = getter(*args)
            except Exception:
                raw = None
            bodies = _as_list(raw)
            if bodies:
                return bodies
    return []


def _as_list(raw) -> list:
    if raw is None or isinstance(raw, (str, int, float, bool)):
        return []
    try:
        return [item for item in raw if item is not None]
    except TypeError:
        return [raw]


def _select_solid_body(model, body) -> bool:
    """Select a solid with mark 1.

    Move/Copy ignores a body selected with no mark: InsertMoveCopyBody2 then
    returns nothing. SelectByID2(..., mark=1) is the selection it accepts.
    Select2(False, None) returns True and must not count.
    """
    name = _feature_name(body)
    extension = _com_attr(model, "Extension")
    nothing = com_nothing()
    if name and extension is not None:
        try:
            if extension.SelectByID2(name, "SOLIDBODY", 0.0, 0.0, 0.0, False, 1, nothing, 0):
                return True
        except Exception:
            pass
    data = _select_data(model, mark=1)
    if data is not None:
        with contextlib.suppress(Exception):
            if body.Select2(False, data):
                return True
    return False


def _select_data(model, mark: int):
    manager = _com_attr(model, "SelectionManager")
    if manager is None:
        return None
    with contextlib.suppress(Exception):
        if callable(manager):
            manager = manager()
    create = _com_attr(manager, "CreateSelectData")
    if create is None:
        return None
    try:
        data = create()
        data.Mark = int(mark)
    except Exception:
        return None
    return data


def _select_named_line(model, line_name: str, *, append: bool, mark: int) -> bool:
    nothing = com_nothing()
    extension = _com_attr(model, "Extension")
    if extension is None:
        return False
    for type_name in ("EXTSKETCHSEGMENT", "SKETCHSEGMENT", "CENTERLINE"):
        for callout in (nothing, 0):
            try:
                if extension.SelectByID2(line_name, type_name, 0.0, 0.0, 0.0, append, mark, callout, 0):
                    return True
            except Exception:
                continue
    return False


def _active_sketch(model):
    for getter in (
        lambda: model.GetActiveSketch2(),
        lambda: com_value(model.GetActiveSketch2),
        lambda: com_value(model.SketchManager.ActiveSketch),
    ):
        try:
            sketch = getter()
        except Exception:
            continue
        if sketch is not None:
            return sketch
    return None


def _select_sketch_axis(model, sketch_name: str) -> None:
    nothing = com_nothing()
    names = (f"Line1@{sketch_name}", "Line1", f"Line2@{sketch_name}")
    types = ("EXTSKETCHSEGMENT", "SKETCHSEGMENT", "CENTERLINE")
    for line_name in names:
        for type_name in types:
            for callout in (nothing, 0, None):
                try:
                    if model.Extension.SelectByID2(
                        line_name, type_name, 0.0, 0.0, 0.0, True, 4, callout, 0
                    ):
                        return
                except Exception:
                    continue
    raise SolidWorksError("Could not select the tank axis for revolve.")


def _revolve_angle(model, angle: float, *, merge: bool = False, reverse: bool = True):
    model = as_model_doc(model)
    errors: list[str] = []
    sketch_before = ""
    with contextlib.suppress(Exception):
        latest = model.FeatureByPositionReverse(0)
        sketch_before = _feature_name(latest)

    def _feature_if_new():
        latest = model.FeatureByPositionReverse(0)
        if latest is None:
            return None
        created = _feature_name(latest)
        if not created or created == sketch_before:
            return None
        return latest

    def _rescue_new_feature():
        try:
            return _feature_if_new()
        except Exception:
            return None

    def _created(result):
        if result not in (None, False, 0) and not isinstance(result, bool):
            return result
        return _feature_if_new()

    # Merge=False lives on FeatureManager. Try it before the 4-arg ModelDoc
    # revolve, which has no merge flag and fuses later plates into the first.
    feature_manager = _com_attr(model, "FeatureManager")
    fm_revolve = _com_attr(feature_manager, "FeatureRevolve2") if feature_manager is not None else None
    modern = (
        True,
        True,
        False,
        False,
        bool(reverse),
        False,
        0,
        0,
        angle,
        0.0,
        False,
        False,
        0.0,
        0.0,
        0,
        0.0,
        0.0,
        bool(merge),
        True,
        True,
    )
    if fm_revolve is None:
        errors.append("FeatureManager.FeatureRevolve2: not on this interface")
    else:
        for args in (modern, modern[:18]):
            try:
                created = _created(fm_revolve(*args))
            except Exception as exc:
                errors.append(f"FeatureManager.FeatureRevolve2/{len(args)}: {format_com_error(exc)}")
                created = _rescue_new_feature()
            if created is not None:
                return created

    model_attempts = (
        ("FeatureRevolve2", (angle, bool(reverse), 0.0, 0)),
        ("FeatureRevolve", (angle, bool(reverse), 0.0, 0)),
        ("FeatureRevolve2", (angle, bool(reverse), 0.0, 0, bool(merge))),
    )
    for method_name, args in model_attempts:
        method = _com_attr(model, method_name)
        if method is None:
            errors.append(f"model.{method_name}: not on this interface")
            continue
        try:
            created = _created(method(*args))
        except Exception as exc:
            errors.append(f"model.{method_name}/{len(args)}: {format_com_error(exc)}")
            created = _rescue_new_feature()
        if created is not None:
            return created

    raise SolidWorksError("Revolve failed (" + "; ".join(errors) + ")")


def _delete_plate_features(model, feature_name: str) -> None:
    names: list[str] = []
    for feat in iter_features(model):
        name = str(com_value(feat.Name) or "")
        if _belongs_to_plate(name, feature_name):
            names.append(name)
    for name in reversed(names):
        feature = find_feature(model, name)
        if feature is None:
            continue
        with contextlib.suppress(Exception):
            feature.Select2(False, 0)
            model.EditDelete()


def _belongs_to_plate(name: str, feature_name: str) -> bool:
    if name == feature_name:
        return True
    if not name.startswith(feature_name):
        return False
    return not name[len(feature_name) : len(feature_name) + 1].isdigit()


def _delete_elite_tank_features(model) -> None:
    names: list[str] = []
    for feat in iter_features(model):
        name = str(com_value(feat.Name) or "")
        if name.startswith(FEATURE_PREFIX):
            names.append(name)
    for name in reversed(names):
        feature = find_feature(model, name)
        if feature is None:
            continue
        with contextlib.suppress(Exception):
            feature.Select2(False, 0)
            model.EditDelete()
