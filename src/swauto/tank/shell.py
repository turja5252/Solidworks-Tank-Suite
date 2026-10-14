"""Build / rebuild a multi-course tank shell in SolidWorks (2013-safe).

Discrete plates = limited FeatureRevolve of a wall rectangle on the Front plane
(true cylindrical surface). Stagger = rotation about the tank vertical axis (Y
in SW Front=XY convention) with an axis selected — never chorded Top extrudes
(those looked flat/faceted and tipped when Move/Copy used the wrong axis).

Fallbacks: single full revolve, then stacked thin rings.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from swauto.comutil import as_model_doc, com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature
from swauto.params import rebuild, rename_feature
from swauto.parts import extrude_thin_blind, new_part, select_front_plane, select_plane, select_top_plane
from swauto.tank.plates import PlateSector, layout_plates
from swauto.tank.profile import course_radii_m, shell_profile_meters
from swauto.tank.spec import TankSpec
from swauto.units import to_meters

FEATURE_PREFIX = "EliteTank"
SKETCH_NAME = f"{FEATURE_PREFIX}Profile"
REVOLVE_NAME = f"{FEATURE_PREFIX}Shell"
AXIS_NAME = f"{FEATURE_PREFIX}Axis"


@dataclass
class LiveTank:
    title: str
    spec: TankSpec
    model: object | None = None

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


@dataclass(frozen=True)
class TankResult:
    title: str
    spec: TankSpec
    live: LiveTank


def create_tank_shell(app, spec: TankSpec) -> TankResult:
    spec.validate()
    try:
        model = new_part(app)
        _build_shell_on_model(model, spec)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Tank shell failed: {format_com_error(exc)}") from exc

    title = str(com_value(model.GetTitle) or "Part")
    live = LiveTank(title=title, spec=spec, model=model)
    return TankResult(title=title, spec=spec, live=live)


def _safe_delete_elite(model) -> None:
    with contextlib.suppress(Exception):
        _delete_elite_tank_features(model)


def _safe_delete_named(model, *names: str) -> None:
    with contextlib.suppress(Exception):
        for name in names:
            if not name:
                continue
            feature = find_feature(model, name)
            if feature is None:
                continue
            with contextlib.suppress(Exception):
                feature.Select2(False, 0)
                model.EditDelete()


def _build_shell_on_model(model, spec: TankSpec) -> None:
    """Prefer a solid revolved wall on SW2013; plated solids are opt-in / best-effort.

    Discrete plate COM on 2013 has been unreliable (wrong-axis Move/Copy, faceted
    Top extrudes, CreateLine failures mid-build). Ship a correct upright shell
    first; plate solids stay available as a secondary attempt.
    """
    errors: list[str] = []

    try:
        _build_revolved_shell(model, spec)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
        return
    except Exception as exc:
        errors.append(f"revolve: {format_com_error(exc)}")
        _safe_delete_elite(model)

    try:
        _build_plated_shell(model, spec)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
        return
    except Exception as exc:
        errors.append(f"plates: {format_com_error(exc)}")
        _safe_delete_elite(model)

    try:
        _build_stacked_thin_shell(model, spec)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
        return
    except Exception as exc:
        errors.append(f"stacked: {format_com_error(exc)}")

    raise SolidWorksError("Could not build tank shell.\n" + "\n".join(errors))

def _build_plated_shell(model, spec: TankSpec) -> None:
    plates = layout_plates(spec)
    if not plates:
        raise SolidWorksError("No plates to build.")
    _ensure_tank_axis(model)
    first = True
    stagger_ok = True
    for plate in plates:
        try:
            _build_cylindrical_plate(model, plate, merge=not first)
            if abs(plate.start_rad) > 1e-9:
                try:
                    _rotate_about_tank_axis(model, plate.feature_name, float(plate.start_rad))
                except Exception:
                    stagger_ok = False
        except Exception as exc:
            raise SolidWorksError(
                f"{plate.feature_name} failed: {format_com_error(exc)}"
            ) from exc
        first = False
    if not stagger_ok:
        # Plates exist and are upright; clocking may be aligned to Front only.
        pass


def _ensure_tank_axis(model) -> None:
    """Vertical tank axis = Front ∩ Right (Y). Needed for upright stagger rotate."""
    if find_feature(model, AXIS_NAME) is not None:
        return
    model.ClearSelection2(True)
    nothing = com_nothing()
    # Front + Right → axis along Y (SW default: Front=XY, Right=YZ).
    selected = False
    if select_plane(model, "Front Plane") or select_plane(model, "Front"):
        with contextlib.suppress(Exception):
            # Add Right to selection
            for name in ("Right Plane", "Right", "Plane3"):
                try:
                    if model.Extension.SelectByID2(name, "PLANE", 0.0, 0.0, 0.0, True, 0, nothing, 0):
                        selected = True
                        break
                except Exception:
                    continue
    if not selected:
        return
    axis = None
    with contextlib.suppress(Exception):
        axis = model.InsertAxis2(True)
    if axis is None:
        with contextlib.suppress(Exception):
            axis = model.FeatureManager.InsertAxis2(True)
    if axis is not None:
        with contextlib.suppress(Exception):
            rename_feature(axis, AXIS_NAME)
    model.ClearSelection2(True)


def _build_cylindrical_plate(model, plate: PlateSector, *, merge: bool) -> None:
    """True cylindrical plate: Front sketch wall rect → limited revolve."""
    model = as_model_doc(model)
    z0 = float(plate.z_bot_m)
    z1 = z0 + float(plate.height_m)
    ri = float(plate.inner_r_m)
    ro = float(plate.outer_r_m)
    sweep = 2.0 * math.pi if plate.is_full_ring else float(plate.sweep_rad)
    if sweep <= 1e-9:
        raise SolidWorksError("Plate sweep is zero.")

    select_front_plane(model)
    sk = model.SketchManager
    sk.InsertSketch(True)
    _create_revolve_axis(sk, max(z1, 0.1))
    corners = ((ri, z0), (ro, z0), (ro, z1), (ri, z1), (ri, z0))
    for (x1, y1), (x2, y2) in zip(corners, corners[1:], strict=False):
        if sk.CreateLine(float(x1), float(y1), 0.0, float(x2), float(y2), 0.0) is None:
            raise SolidWorksError("Plate profile line failed.")
    model.ClearSelection2(True)
    sk.InsertSketch(True)

    sketch = model.FeatureByPositionReverse(0)
    if sketch is None:
        raise SolidWorksError("Missing plate sketch.")
    rename_feature(sketch, plate.sketch_name)
    if not sketch.Select2(False, 0):
        raise SolidWorksError("Could not select plate sketch.")
    _select_sketch_axis(model, plate.sketch_name)

    feat = _revolve_angle(model, sweep, merge=merge)
    if feat is None:
        feat = model.FeatureByPositionReverse(0)
    if feat is None:
        raise SolidWorksError("Limited revolve created no feature.")
    rename_feature(feat, plate.feature_name)


def _rotate_about_tank_axis(model, feature_name: str, angle_rad: float) -> None:
    """Spin plate about vertical tank axis (Y). Requires axis + body selection."""
    feature = find_feature(model, feature_name)
    if feature is None:
        raise SolidWorksError(f"Missing {feature_name} for rotate.")
    nothing = com_nothing()
    model.ClearSelection2(True)

    # Body/feature mark 1
    ok_body = False
    with contextlib.suppress(Exception):
        ok_body = bool(feature.Select2(False, 1))
    if not ok_body:
        with contextlib.suppress(Exception):
            ok_body = bool(
                model.Extension.SelectByID2(
                    feature_name, "BODYFEATURE", 0.0, 0.0, 0.0, False, 1, nothing, 0
                )
            )
    if not ok_body:
        raise SolidWorksError(f"Could not select {feature_name}.")

    # Axis mark 2 (rotation reference)
    ok_axis = False
    for axis_name in (AXIS_NAME, "Axis1", "Axis2"):
        for type_name in ("AXIS", "REFAXIS"):
            try:
                if model.Extension.SelectByID2(
                    axis_name, type_name, 0.0, 0.0, 0.0, True, 2, nothing, 0
                ):
                    ok_axis = True
                    break
            except Exception:
                continue
        if ok_axis:
            break

    fm = model.FeatureManager
    errors: list[str] = []
    # Front=XY → tank vertical is Y → RotY = angle, RotX=RotZ=0.
    for method_name in ("InsertMoveCopyBody2", "InsertMoveCopyBody"):
        method = getattr(fm, method_name, None)
        if method is None:
            continue
        attempts = (
            # trans, copy/flag, rotX, rotY, rotZ, ...
            (0.0, 0.0, 0.0, False, 0.0, float(angle_rad), 0.0, True),
            (0.0, 0.0, 0.0, 0, 0.0, float(angle_rad), 0.0, True),
            (0.0, 0.0, 0.0, False, 0.0, float(angle_rad), 0.0, True, False),
            (0.0, 0.0, 0.0, 0, 0.0, float(angle_rad), 0.0, True, 1),
        )
        for args in attempts:
            try:
                method(*args)
            except Exception as exc:
                errors.append(f"{method_name}/{len(args)}: {format_com_error(exc)}")
                continue
            latest = model.FeatureByPositionReverse(0)
            if latest is not None:
                name = str(com_value(latest.Name) or "")
                if "Move" in name or "Copy" in name or "Body" in name:
                    with contextlib.suppress(Exception):
                        rename_feature(latest, f"{feature_name}Rot")
            model.ClearSelection2(True)
            return
    model.ClearSelection2(True)
    raise SolidWorksError("Rotate about tank axis failed (" + "; ".join(errors) + ")")


def _build_revolved_shell(model, spec: TankSpec) -> None:
    model = as_model_doc(model)
    points = shell_profile_meters(spec)
    height = max(y for _x, y in points) if points else 1.0

    select_front_plane(model)
    sk = model.SketchManager
    sk.InsertSketch(True)
    _create_revolve_axis(sk, float(height))

    for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
        if abs(x1 - x2) < 1e-15 and abs(y1 - y2) < 1e-15:
            continue
        if sk.CreateLine(float(x1), float(y1), 0.0, float(x2), float(y2), 0.0) is None:
            raise SolidWorksError("Could not create a shell profile line.")

    model.ClearSelection2(True)
    sk.InsertSketch(True)

    sketch_feat = model.FeatureByPositionReverse(0)
    if sketch_feat is None:
        raise SolidWorksError("Could not find the tank profile sketch.")
    rename_feature(sketch_feat, SKETCH_NAME)
    if not sketch_feat.Select2(False, 0):
        raise SolidWorksError("Could not select the tank profile sketch.")
    _select_sketch_axis(model, SKETCH_NAME)

    feat = _revolve_angle(model, 2.0 * math.pi, merge=True)
    if feat is not None:
        rename_feature(feat, REVOLVE_NAME)
        return
    latest = model.FeatureByPositionReverse(0)
    if latest is None:
        raise SolidWorksError("Revolve created no feature.")
    name = str(com_value(latest.Name) or "")
    if name == SKETCH_NAME or name.startswith(SKETCH_NAME):
        raise SolidWorksError("Revolve did not create a boss feature.")
    rename_feature(latest, REVOLVE_NAME)


def _create_revolve_axis(sk, height: float) -> None:
    axis = None
    with contextlib.suppress(Exception):
        axis = sk.CreateCenterLine(0.0, 0.0, 0.0, 0.0, height, 0.0)
    if axis is None:
        axis = sk.CreateLine(0.0, 0.0, 0.0, 0.0, height, 0.0)
    if axis is None:
        raise SolidWorksError("Could not create the tank axis line.")
    with contextlib.suppress(Exception):
        axis.ConstructionGeometry = True


def _build_stacked_thin_shell(model, spec: TankSpec) -> None:
    z_m = 0.0
    for index, course in enumerate(spec.active_courses(), start=1):
        outer_r, inner_r = course_radii_m(spec, course)
        height_m = to_meters(course.height_in, "in")
        thickness_m = outer_r - inner_r
        select_top_plane(model)
        sk = model.SketchManager
        sk.InsertSketch(True)
        if sk.CreateCircleByRadius(0.0, 0.0, 0.0, float(outer_r)) is None:
            raise SolidWorksError(f"Course {index}: outer circle failed.")
        model.ClearSelection2(True)
        sk.InsertSketch(True)
        sketch = model.FeatureByPositionReverse(0)
        if sketch is None:
            raise SolidWorksError(f"Course {index}: missing sketch.")
        rename_feature(sketch, f"{FEATURE_PREFIX}C{index}Sketch")
        sketch.Select2(False, 0)
        boss = extrude_thin_blind(
            model.FeatureManager,
            height_m,
            thickness_m,
            start_offset_m=z_m,
        )
        rename_feature(boss, f"{FEATURE_PREFIX}C{index}Shell")
        z_m += height_m


def _select_sketch_axis(model, sketch_name: str) -> None:
    nothing = com_nothing()
    names = (f"Line1@{sketch_name}", "Line1", f"Line2@{sketch_name}")
    types = ("EXTSKETCHSEGMENT", "SKETCHSEGMENT", "CENTERLINE")
    for name in names:
        for type_name in types:
            for callout in (nothing, 0, None):
                try:
                    if model.Extension.SelectByID2(name, type_name, 0.0, 0.0, 0.0, True, 4, callout, 0):
                        return
                except Exception:
                    continue
    raise SolidWorksError("Could not select the tank axis for revolve.")


def _revolve_angle(model, angle: float, *, merge: bool = True):
    model = as_model_doc(model)
    errors: list[str] = []
    sketch_before = str(com_value(model.FeatureByPositionReverse(0).Name) or "")

    def _feature_if_new():
        latest = model.FeatureByPositionReverse(0)
        if latest is None:
            return None
        name = str(com_value(latest.Name) or "")
        if not name or name == sketch_before:
            return None
        return latest

    model_attempts = (
        ("FeatureRevolve2", (angle, False, 0.0, 0, bool(merge))),
        ("FeatureRevolve2", (angle, False, 0.0, 0)),
        ("FeatureRevolve", (angle, False, 0.0, 0)),
    )
    for method_name, args in model_attempts:
        method = getattr(model, method_name, None)
        if method is None:
            errors.append(f"model.{method_name}: not on this interface")
            continue
        try:
            result = method(*args)
        except Exception as exc:
            errors.append(f"model.{method_name}/{len(args)}: {format_com_error(exc)}")
            continue
        if result not in (None, False, 0) and not isinstance(result, bool):
            return result
        created = _feature_if_new()
        if created is not None:
            return created

    fm = model.FeatureManager
    modern = (
        True,
        True,
        False,
        False,
        False,
        False,
        True,
        False,
        angle,
        0.0,
        False,
        False,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        bool(merge),
        True,
        True,
    )
    method = getattr(fm, "FeatureRevolve2", None)
    if method is not None:
        for args in (modern, modern[:18]):
            try:
                feat = method(*args)
            except Exception as exc:
                errors.append(f"FeatureManager.FeatureRevolve2/{len(args)}: {format_com_error(exc)}")
                continue
            if feat is not None:
                return feat
            created = _feature_if_new()
            if created is not None:
                return created
    else:
        errors.append("FeatureManager.FeatureRevolve2: not available")

    raise SolidWorksError("Revolve failed (" + "; ".join(errors) + ")")


def _delete_elite_tank_features(model) -> None:
    names: list[str] = []
    feat = model.FirstFeature()
    while feat is not None:
        name = str(com_value(feat.Name) or "")
        if name.startswith(FEATURE_PREFIX):
            names.append(name)
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    for name in reversed(names):
        feature = find_feature(model, name)
        if feature is None:
            continue
        with contextlib.suppress(Exception):
            feature.Select2(False, 0)
            model.EditDelete()
