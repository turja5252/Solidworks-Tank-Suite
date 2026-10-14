"""Build / rebuild a multi-course tank shell in SolidWorks (2013-safe).

Approach A: continuous revolved wall + 3D sketch vertical seam lines from the
AutoLISP-aligned plate/stagger layout (layout_plates). No discrete plate solids.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from swauto.comutil import as_model_doc, com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature
from swauto.params import rebuild, rename_feature
from swauto.parts import extrude_thin_blind, new_part, select_front_plane, select_top_plane
from swauto.tank.plates import layout_plates
from swauto.tank.profile import course_radii_m, shell_profile_meters
from swauto.tank.spec import TankSpec
from swauto.units import to_meters

FEATURE_PREFIX = "EliteTank"
SKETCH_NAME = f"{FEATURE_PREFIX}Profile"
REVOLVE_NAME = f"{FEATURE_PREFIX}Shell"
SEAMS_NAME = f"{FEATURE_PREFIX}Seams"


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


def _build_shell_on_model(model, spec: TankSpec) -> None:
    """Revolved multi-course wall, then Approach A plate seam sketch."""
    errors: list[str] = []

    try:
        _build_revolved_shell(model, spec)
        _try_build_seam_sketch(model, spec, errors)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
        return
    except Exception as exc:
        errors.append(f"revolve: {format_com_error(exc)}")
        _safe_delete_elite(model)

    try:
        _build_stacked_thin_shell(model, spec)
        _try_build_seam_sketch(model, spec, errors)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
        return
    except Exception as exc:
        errors.append(f"stacked: {format_com_error(exc)}")

    raise SolidWorksError("Could not build tank shell.\n" + "\n".join(errors))


def _try_build_seam_sketch(model, spec: TankSpec, errors: list[str]) -> None:
    """Seams are best-effort — shell still succeeds if the 3D sketch fails."""
    try:
        _build_plate_seam_sketch(model, spec)
    except Exception as exc:
        errors.append(f"seams: {format_com_error(exc)}")


def _build_plate_seam_sketch(model, spec: TankSpec) -> None:
    """3D sketch: one vertical line per plate start (OD), Y = tank height axis."""
    plates = layout_plates(spec)
    seams = [p for p in plates if not p.is_full_ring]
    if not seams:
        return

    model = as_model_doc(model)
    model.ClearSelection2(True)
    sk = model.SketchManager

    opened = False
    for opener in (
        lambda: sk.Insert3DSketch(True),
        lambda: getattr(model, "Insert3DSketch2", lambda *_: None)(True),
        lambda: getattr(model, "Insert3DSketch", lambda *_: None)(True),
    ):
        try:
            opener()
            opened = True
            break
        except Exception:
            continue
    if not opened:
        raise SolidWorksError("Could not open a 3D sketch for plate seams.")

    # Past course top/bottom a hair so seams read flush on the OD (SW trims
    # endpoints that sit exactly on a face edge; AutoLISP stretchout does the same).
    overhang = 0.002  # 2 mm

    drawn = 0
    for plate in seams:
        # Front-plane revolve uses Y as tank vertical: X=r·cosθ, Y=height, Z=r·sinθ.
        theta = float(plate.start_rad)
        r = float(plate.outer_r_m) * 1.0005  # sit just outside OD so the line stays visible
        y0 = float(plate.z_bot_m) - overhang
        y1 = float(plate.z_bot_m) + float(plate.height_m) + overhang
        if y0 < 0.0:
            y0 = 0.0
        x = r * math.cos(theta)
        z = r * math.sin(theta)
        line = None
        with contextlib.suppress(Exception):
            line = sk.CreateLine(x, y0, z, x, y1, z)
        if line is None:
            with contextlib.suppress(Exception):
                line = sk.CreateLine(float(x), float(y0), float(z), float(x), float(y1), float(z))
        if line is not None:
            drawn += 1

    # Close 3D sketch
    for closer in (
        lambda: sk.Insert3DSketch(True),
        lambda: getattr(model, "Insert3DSketch2", lambda *_: None)(True),
        lambda: sk.InsertSketch(True),
    ):
        with contextlib.suppress(Exception):
            closer()
            break

    if drawn == 0:
        raise SolidWorksError("No seam lines could be created in the 3D sketch.")

    feat = model.FeatureByPositionReverse(0)
    if feat is not None:
        rename_feature(feat, SEAMS_NAME)


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
