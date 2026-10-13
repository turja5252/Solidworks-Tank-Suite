"""Find and edit SolidWorks features without relying on display-dimension names."""

from __future__ import annotations

import contextlib

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError

# swSketchSegments_e.swSketchARC
_SKETCH_ARC = 1


def find_feature(model, name: str):
    feat = model.FirstFeature()
    while feat is not None:
        if str(com_value(feat.Name) or "") == name:
            return feat
        try:
            feat = feat.GetNextFeature()
        except Exception:
            break
    return None


def set_sketch_circle_radius(model, sketch_name: str, radius_m: float) -> None:
    feat = find_feature(model, sketch_name)
    if feat is None:
        raise SolidWorksError(f"Sketch feature not found: {sketch_name}")

    if not feat.Select2(False, 0):
        raise SolidWorksError(f"Could not select sketch {sketch_name}")

    try:
        model.EditSketch()
    except Exception as exc:
        raise SolidWorksError(f"EditSketch failed: {format_com_error(exc)}") from exc

    try:
        sketch = model.GetActiveSketch2()
        if sketch is None:
            raise SolidWorksError("No active sketch to edit.")
        segments = sketch.GetSketchSegments()
        if not segments:
            raise SolidWorksError("Sketch has no segments.")

        updated = False
        for seg in _as_list(segments):
            try:
                seg_type = int(com_value(seg.GetType))
            except Exception:
                continue
            if seg_type != _SKETCH_ARC:
                continue
            # Circles are arcs; SetRadius is on ISketchArc (late-bound on the segment).
            try:
                seg.SetRadius(float(radius_m))
            except Exception:
                try:
                    seg.SetRadii(float(radius_m), float(radius_m))
                except Exception as exc:
                    raise SolidWorksError(
                        f"Could not set circle radius: {format_com_error(exc)}"
                    ) from exc
            updated = True
            break

        if not updated:
            raise SolidWorksError("No circle found in the cylinder sketch.")
    finally:
        # Always leave sketch mode, even when radius update fails.
        try:
            model.SketchManager.InsertSketch(True)
        except Exception:
            with contextlib.suppress(Exception):
                model.InsertSketch2(True)


def set_extrude_depth(model, extrude_name: str, depth_m: float) -> None:
    feat = find_feature(model, extrude_name)
    if feat is None:
        raise SolidWorksError(f"Extrude feature not found: {extrude_name}")

    try:
        definition = feat.GetDefinition()
    except Exception as exc:
        raise SolidWorksError(f"GetDefinition failed: {format_com_error(exc)}") from exc
    if definition is None:
        raise SolidWorksError(f"No definition on feature {extrude_name}")

    nothing = com_nothing()
    try:
        definition.AccessSelections(model, nothing)
    except Exception:
        try:
            definition.AccessSelections(model, None)
        except Exception as exc:
            raise SolidWorksError(f"AccessSelections failed: {format_com_error(exc)}") from exc

    try:
        if hasattr(definition, "SetDepth"):
            definition.SetDepth(True, float(depth_m))
        else:
            # Older wording on some type libraries.
            definition.Depth = float(depth_m)
    except Exception as exc:
        raise SolidWorksError(f"SetDepth failed: {format_com_error(exc)}") from exc

    try:
        ok = feat.ModifyDefinition(definition, model, nothing)
    except Exception:
        try:
            ok = feat.ModifyDefinition(definition, model, None)
        except Exception as exc:
            raise SolidWorksError(f"ModifyDefinition failed: {format_com_error(exc)}") from exc

    if ok is False:
        raise SolidWorksError("ModifyDefinition returned False for the extrude.")


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]
