"""Build / rebuild a multi-course tank shell in SolidWorks (2013-safe stacked rings)."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import find_feature
from swauto.params import rebuild, rename_feature
from swauto.parts import extrude_thin_blind, new_part, select_plane, select_top_plane
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import TankSpec
from swauto.units import to_meters

FEATURE_PREFIX = "EliteTank"


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
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Create part failed: {format_com_error(exc)}") from exc

    _build_shell_on_model(model, spec)
    title = str(com_value(model.GetTitle) or "Part")
    live = LiveTank(title=title, spec=spec, model=model)
    return TankResult(title=title, spec=spec, live=live)


def _build_shell_on_model(model, spec: TankSpec) -> None:
    """Stack annular course rings (outer boss + inner cut). Uses the same APIs as Live Cylinder."""
    z_m = 0.0
    for index, course in enumerate(spec.active_courses(), start=1):
        outer_r, inner_r = course_radii_m(spec, course)
        height_m = to_meters(course.height_in, "in")
        plane_name = _plane_for_height(model, z_m, index)
        _add_course_ring(model, index, plane_name, outer_r, inner_r, height_m)
        z_m += height_m

    rebuild(model)
    with contextlib.suppress(Exception):
        model.ViewZoomtofit2()


def _plane_for_height(model, z_m: float, index: int) -> str:
    if z_m <= 1e-12:
        select_top_plane(model)
        return "Top Plane"

    select_top_plane(model)
    plane = _insert_offset_plane(model, z_m)
    name = rename_feature(plane, f"{FEATURE_PREFIX}C{index}Plane")
    if not plane.Select2(False, 0) and not _select_plane_name(model, name):
        raise SolidWorksError(f"Could not select offset plane {name}")
    return name


def _insert_offset_plane(model, offset_m: float):
    fm = model.FeatureManager
    offset = float(offset_m)
    attempts = (
        (offset, 4, 0, 0, 0, 0),
        (offset, 1, 0, 0, 0, 0),
        (4, offset, 0, 0, 0, 0),
        (1, offset, 0, 0, 0, 0),
    )
    errors: list[str] = []
    for args in attempts:
        try:
            feat = fm.InsertRefPlane(*args)
        except Exception as exc:
            errors.append(f"{args}: {format_com_error(exc)}")
            continue
        if feat is not None:
            return feat
        errors.append(f"{args}: returned nothing")
    raise SolidWorksError(
        "Could not create an offset plane for the next shell course.\n" + "; ".join(errors[:4])
    )


def _select_plane_name(model, name: str) -> bool:
    return select_plane(model, name)


def _add_course_ring(
    model,
    index: int,
    plane_name: str,
    outer_r: float,
    inner_r: float,
    height_m: float,
) -> None:
    """One shell course: outer circle + thin-wall extrude inward (no FeatureCut)."""
    if plane_name == "Top Plane":
        select_top_plane(model)
    elif not _select_plane_name(model, plane_name):
        raise SolidWorksError(f"Could not select plane {plane_name}")

    thickness_m = float(outer_r) - float(inner_r)
    if thickness_m <= 0:
        raise SolidWorksError(f"Course {index}: thickness must be greater than zero.")

    try:
        sk = model.SketchManager
        sk.InsertSketch(True)
        if sk.CreateCircleByRadius(0.0, 0.0, 0.0, float(outer_r)) is None:
            raise SolidWorksError(f"Course {index}: outer circle failed.")
        model.ClearSelection2(True)
        sk.InsertSketch(True)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Course {index} sketch failed: {format_com_error(exc)}") from exc

    sketch = model.FeatureByPositionReverse(0)
    if sketch is None:
        raise SolidWorksError(f"Course {index}: missing sketch.")
    rename_feature(sketch, f"{FEATURE_PREFIX}C{index}Sketch")
    sketch.Select2(False, 0)
    boss = extrude_thin_blind(model.FeatureManager, height_m, thickness_m)
    rename_feature(boss, f"{FEATURE_PREFIX}C{index}Shell")


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
