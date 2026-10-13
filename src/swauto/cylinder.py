"""Create and live-update a solid cylinder in SolidWorks."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import set_extrude_depth, set_sketch_circle_radius
from swauto.params import rebuild, rename_feature
from swauto.parts import extrude_blind, new_part, select_front_plane
from swauto.units import to_meters

SKETCH_FEATURE = "EliteCylSketch"
EXTRUDE_FEATURE = "EliteCylExtrude"


@dataclass
class LiveCylinder:
    """A cylinder part whose diameter/height can be changed from the menu."""

    title: str
    sketch_feature: str
    extrude_feature: str
    unit: str
    model: object | None = None

    def update(self, app, *, diameter: float, height: float, unit: str | None = None) -> None:
        if unit is not None:
            self.unit = unit
        diameter_m = to_meters(diameter, self.unit)
        height_m = to_meters(height, self.unit)
        model = self._resolve_model(app)
        set_sketch_circle_radius(model, self.sketch_feature, diameter_m / 2.0)
        set_extrude_depth(model, self.extrude_feature, height_m)
        rebuild(model)
        with contextlib.suppress(Exception):
            model.ViewZoomtofit2()

    def _resolve_model(self, app):
        if self.model is not None:
            try:
                title = str(com_value(self.model.GetTitle) or "")
                if title:
                    return self.model
            except Exception:
                self.model = None

        active = com_value(app.ActiveDoc)
        if active is not None:
            title = str(com_value(active.GetTitle) or "")
            if title == self.title or title.startswith(self.title.split(".")[0]):
                self.model = active
                return active

        getter = getattr(app, "GetOpenDocumentByName", None)
        if getter is not None:
            try:
                opened = getter(self.title)
            except Exception:
                opened = None
            if opened is not None:
                self.model = opened
                return opened

        raise SolidWorksError(
            f"Could not find open part {self.title!r}.\n"
            "Activate the cylinder part in SolidWorks, then change values again."
        )


@dataclass(frozen=True)
class CylinderResult:
    diameter: float
    height: float
    unit: str
    diameter_m: float
    height_m: float
    title: str
    live: LiveCylinder


def create_cylinder(app, *, diameter: float, height: float, unit: str = "in") -> CylinderResult:
    """Sketch a circle on the Front Plane, extrude it, and return a live handle."""
    diameter_m = to_meters(diameter, unit)
    height_m = to_meters(height, unit)
    radius_m = diameter_m / 2.0

    try:
        model = new_part(app)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Create part failed: {format_com_error(exc)}") from exc

    try:
        select_front_plane(model)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Select Front Plane failed: {format_com_error(exc)}") from exc

    try:
        sketch_manager = model.SketchManager
        sketch_manager.InsertSketch(True)
        segment = sketch_manager.CreateCircleByRadius(0.0, 0.0, 0.0, float(radius_m))
        if segment is None:
            raise SolidWorksError("Could not create the circle sketch.")
        model.ClearSelection2(True)
        sketch_manager.InsertSketch(True)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Sketch circle failed: {format_com_error(exc)}") from exc

    sketch_feature = model.FeatureByPositionReverse(0)
    if sketch_feature is None:
        raise SolidWorksError("Could not find the cylinder sketch feature.")
    sketch_name = rename_feature(sketch_feature, SKETCH_FEATURE)

    try:
        sketch_feature.Select2(False, 0)
        extrude_feature = extrude_blind(model.FeatureManager, height_m)
        model.ViewZoomtofit2()
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"Extrude failed: {format_com_error(exc)}") from exc

    extrude_name = rename_feature(extrude_feature, EXTRUDE_FEATURE)

    title = str(com_value(model.GetTitle) or "Part")
    live = LiveCylinder(
        title=title,
        sketch_feature=sketch_name,
        extrude_feature=extrude_name,
        unit=unit,
        model=model,
    )
    return CylinderResult(
        diameter=diameter,
        height=height,
        unit=unit,
        diameter_m=diameter_m,
        height_m=height_m,
        title=title,
        live=live,
    )
