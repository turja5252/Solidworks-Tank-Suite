"""Build / rebuild a multi-course tank shell in SolidWorks (2013-safe)."""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature
from swauto.params import rebuild, rename_feature
from swauto.parts import extrude_thin_blind, new_part, select_front_plane, select_top_plane
from swauto.tank.profile import course_radii_m, shell_profile_meters
from swauto.tank.spec import TankSpec
from swauto.units import to_meters

FEATURE_PREFIX = "EliteTank"
SKETCH_NAME = f"{FEATURE_PREFIX}Profile"
REVOLVE_NAME = f"{FEATURE_PREFIX}Shell"


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


def _build_shell_on_model(model, spec: TankSpec) -> None:
    """Prefer one revolved wall; fall back to stacked thin rings."""
    errors: list[str] = []
    try:
        _build_revolved_shell(model, spec)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
        return
    except Exception as exc:
        errors.append(f"revolve: {format_com_error(exc)}")
        _delete_elite_tank_features(model)

    try:
        _build_stacked_thin_shell(model, spec)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()
        return
    except Exception as exc:
        errors.append(f"stacked: {format_com_error(exc)}")

    raise SolidWorksError("Could not build tank shell.\n" + "\n".join(errors))


def _build_revolved_shell(model, spec: TankSpec) -> None:
    points = shell_profile_meters(spec)
    height = max(y for _x, y in points) if points else 1.0

    select_front_plane(model)
    sk = model.SketchManager
    sk.InsertSketch(True)

    # SW2013: CreateCenterLine often fails; use a normal line as the axis.
    axis = sk.CreateLine(0.0, 0.0, 0.0, 0.0, float(height), 0.0)
    if axis is None:
        raise SolidWorksError("Could not create the tank axis line.")
    # Property name varies; ignore if absent.
    with contextlib.suppress(Exception):
        axis.ConstructionGeometry = True

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

    feat = _revolve_full(model)
    if feat is not None:
        rename_feature(feat, REVOLVE_NAME)
    else:
        # Older ModelDoc revolve APIs may not return the feature object.
        latest = model.FeatureByPositionReverse(0)
        if latest is not None:
            rename_feature(latest, REVOLVE_NAME)


def _build_stacked_thin_shell(model, spec: TankSpec) -> None:
    """Stack thin-wall rings from Top Plane (course 1 only needs no offset)."""
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


def _revolve_full(model):
    """Create a full revolution. SolidWorks 2013 uses short ModelDoc FeatureRevolve2."""
    angle = 2.0 * math.pi
    errors: list[str] = []

    # IModelDoc2.FeatureRevolve2(Angle, ReverseDir, Angle2, RevType, Merge) — SW2013.
    # IModelDoc2.FeatureRevolve(Angle, ReverseDir, Angle2, RevType)
    model_attempts = (
        ("FeatureRevolve2", (angle, False, 0.0, 0, True)),
        ("FeatureRevolve2", (angle, False, 0.0, 0)),
        ("FeatureRevolve", (angle, False, 0.0, 0)),
    )
    for method_name, args in model_attempts:
        method = getattr(model, method_name, None)
        if method is None:
            continue
        try:
            result = method(*args)
        except Exception as exc:
            errors.append(f"model.{method_name}/{len(args)}: {format_com_error(exc)}")
            continue
        if result is not None:
            return result
        # Some builds return None/0 even on success — treat latest feature as OK later.
        latest = model.FeatureByPositionReverse(0)
        if latest is not None and "Revolve" in str(com_value(latest.Name) or ""):
            return latest
        if result is None or result == 0:
            # Still may have succeeded; return latest feature.
            return latest

    # Newer FeatureManager.FeatureRevolve2 (long form) — SolidWorks 2014+.
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
        True,
        True,
        True,
    )
    for args in (modern, modern[:18]):
        method = getattr(fm, "FeatureRevolve2", None)
        if method is None:
            break
        try:
            feat = method(*args)
        except Exception as exc:
            errors.append(f"FeatureManager.FeatureRevolve2/{len(args)}: {format_com_error(exc)}")
            continue
        if feat is not None:
            return feat

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
