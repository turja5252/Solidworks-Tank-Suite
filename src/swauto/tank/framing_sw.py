"""Build the roof framing in SolidWorks, into the part with the cone roof.

Every rafter comes out of one band: the rafter's section revolved round the tank axis, then cut down, in
one scoped cut, to the rafters' plan outlines (islands in a circle that covers the roof). The clips are cut
from a second band the same way. The column stack is turned discs.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import com_value
from swauto.errors import SolidWorksError
from swauto.features import find_feature, iter_features
from swauto.params import rebuild, rename_feature
from swauto.parts import select_plane
from swauto.tank.framing import Layout, clip_outlines, radial, rafter_outline
from swauto.tank.roof_sw import ROOF_NAME, _revolve_profile

PREFIX = "EliteRoofFrame"  # starts like the roof's features, so rebuilding the roof takes the framing with it
_INCH = 0.0254


def add_framing(model, plan: Layout, progress=None) -> str:
    """Rebuild the rafters, clips and column on ``model``. Earlier framing goes first."""
    if model is None or find_feature(model, ROOF_NAME) is None:
        raise SolidWorksError("Build the roof on the Roof tab first; the framing goes into its part.")
    _delete_prefixed(model)
    rebuild(model)
    _say(progress, f"Rafters: one band, cut to {len(plan.rafters)} rafters...")
    _cut_band(model, plan.section, [rafter_outline(plan, r) for r in plan.rafters], f"{PREFIX}Rafters")
    # A body a cut splits off lists only that cut among its features, so the pieces are found by the cut.
    middle = plan.plan_radius((plan.inner_slant_in + plan.outer_slant_in) / 2.0)
    spots = [(_plan_point(r.angle_deg, middle), f"Rafter {r.number}") for r in plan.rafters]
    made = _name_pieces(model, f"{PREFIX}RaftersCut", spots)
    if made != len(plan.rafters):
        raise SolidWorksError(f"The rafter band came out as {made} pieces, not {len(plan.rafters)}.")
    notes = [f"{made} {plan.framing.mode} rafters"]
    if plan.clip_section:
        _say(progress, "Rafter clips...")
        outlines = [o for r in plan.rafters for o in clip_outlines(plan, r)]
        names = [(_plan_point(r.angle_deg, plan.plan_radius(slant)), f"Rafter {r.number} clip {j}")
                 for r in plan.rafters for j, slant in enumerate(plan.clip_slants_in, start=1)]
        _cut_band(model, plan.clip_section, outlines, f"{PREFIX}Clips")
        clips = _name_pieces(model, f"{PREFIX}ClipsCut", names)
        notes.append(f"{clips} clips")
    for piece, loop in plan.column:
        _say(progress, f"{piece}...")
        feature = f"{PREFIX}{piece.replace(' ', '')}"
        _revolve_profile(model, loop, f"{feature}Sk", feature)
        rebuild(model)
        body = _body_with_feature(model, feature)
        if body is None:
            raise SolidWorksError(f"The {piece.lower()} did not build.")
        with contextlib.suppress(Exception):
            body.Name = piece
        notes.append(piece.lower())
    rebuild(model)
    return "Roof framing: " + ", ".join(notes) + "."


def _cut_band(model, section, outlines, name: str) -> None:
    """Revolve ``section`` round the tank axis, then keep only what is inside the plan ``outlines``."""
    _revolve_profile(model, tuple(section), f"{name}BandSk", name)
    rebuild(model)
    band = _body_with_feature(model, name)
    if band is None:
        raise SolidWorksError(f"{name}: the band did not build.")
    low = min(y for _r, y in section)
    high = max(y for _r, y in section)
    middle = (low + high) / 2.0
    reach = max(r for r, _y in section) + 2.0
    plane = _level_plane(model, middle, f"{name}Level")
    model.ClearSelection2(True)
    if not plane.Select2(False, 0):
        raise SolidWorksError(f"{name}: could not select its sketch plane.")
    sketch = model.SketchManager
    with contextlib.suppress(Exception):
        sketch.AddToDB = True
    with contextlib.suppress(Exception):
        sketch.DisplayWhenAdded = False
    sketch.InsertSketch(True)
    try:
        transform = com_value(com_value(model.GetActiveSketch2).ModelToSketchTransform)
        data = [float(v) for v in com_value(transform.ArrayData)]

        def at(x: float, z: float) -> tuple[float, float]:
            p = (x * _INCH, middle * _INCH, z * _INCH)
            return (data[0] * p[0] + data[3] * p[1] + data[6] * p[2] + data[9],
                    data[1] * p[0] + data[4] * p[1] + data[7] * p[2] + data[10])

        c = at(0.0, 0.0)
        sketch.CreateCircleByRadius(c[0], c[1], 0.0, reach * _INCH)
        for outline in outlines:
            corners = [at(x, z) for x, z in outline]
            for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
                sketch.CreateLine(x0, y0, 0.0, x1, y1, 0.0)
        drawn = _segments(model)
    finally:
        with contextlib.suppress(Exception):
            sketch.AddToDB = False
        with contextlib.suppress(Exception):
            sketch.DisplayWhenAdded = True
        sketch.InsertSketch(True)
    want = 1 + sum(len(o) for o in outlines)
    feature = model.FeatureByPositionReverse(0)
    rename_feature(feature, f"{name}PlanSk")
    if drawn < want:
        raise SolidWorksError(f"{name}: only {drawn} of the {want} plan lines drew.")
    model.ClearSelection2(True)
    band = _body_with_feature(model, name)
    data_mark = model.SelectionManager.CreateSelectData
    data_mark.Mark = 8  # feature scope bodies go in with mark 8
    if not (feature.Select2(False, 0) and band.Select2(True, data_mark)):
        raise SolidWorksError(f"{name}: could not select the plan outline and the band.")
    depth = (high - low) / 2.0 + 2.0
    # SW 2013's FeatureCut3, both ways from the sketch, scoped to the band alone.
    cut = model.FeatureManager.FeatureCut3(
        False, False, False,
        0, 0, depth * _INCH, depth * _INCH,
        False, False, False, False,
        0.0, 0.0, False, False, False, False,
        False, True, False, True,
        True, False, 0, 0.0, False,
    )
    if cut is None:
        raise SolidWorksError(f"{name}: the cut to the plan outlines did not go through.")
    rename_feature(cut, f"{name}Cut")
    _hide(model, f"{name}PlanSk", sketch_kind=True)
    _hide(model, f"{name}Level", sketch_kind=False)
    rebuild(model)


def _name_pieces(model, feature: str, names: list[tuple[tuple[float, float], str]]) -> int:
    """Name each body ``feature`` made after the nearest of the named plan points (X, Z). Returns how many
    bodies there are."""
    bodies = _bodies_with_feature(model, feature)
    taken: set[int] = set()
    for body in bodies:
        try:
            props = tuple(body.GetMassProperties(0))
        except Exception:  # noqa: BLE001
            continue
        x, z = props[0] / _INCH, props[2] / _INCH
        best = min((i for i in range(len(names)) if i not in taken),
                   key=lambda i: math.hypot(names[i][0][0] - x, names[i][0][1] - z), default=None)
        if best is None:
            break
        taken.add(best)
        with contextlib.suppress(Exception):
            body.Name = names[best][1]
    return len(bodies)


def _plan_point(angle_deg: float, radius_in: float) -> tuple[float, float]:
    ux, uz = radial(angle_deg)
    return (ux * radius_in, uz * radius_in)


def _level_plane(model, y_in: float, name: str):
    model.ClearSelection2(True)
    if not select_plane(model, "Top Plane"):
        raise SolidWorksError("Could not select the Top Plane.")
    model.CreatePlaneAtOffset(abs(y_in) * _INCH, y_in < 0.0)
    model.ClearSelection2(True)
    feature = model.FeatureByPositionReverse(0)
    rename_feature(feature, name)
    return find_feature(model, name) or feature


def _segments(model) -> int:
    try:
        return len(list(com_value(com_value(model.GetActiveSketch2).GetSketchSegments) or ()))
    except Exception:  # noqa: BLE001
        return 0


def _bodies(model) -> list:
    try:
        from win32com.client import CastTo

        part = CastTo(model, "PartDoc")
    except Exception:  # noqa: BLE001
        part = model
    try:
        raw = part.GetBodies2(0, False)
    except Exception:  # noqa: BLE001
        return []
    if raw is None or isinstance(raw, (str, int, float, bool)):
        return []
    try:
        return [item for item in raw if item is not None]
    except TypeError:
        return [raw]


def _bodies_with_feature(model, feature_name: str) -> list:
    found = []
    for body in _bodies(model):
        with contextlib.suppress(Exception):
            features = com_value(body.GetFeatures)
            if any(str(com_value(f.Name) or "") == feature_name for f in features or ()):
                found.append(body)
    return found


def _body_with_feature(model, feature_name: str):
    found = _bodies_with_feature(model, feature_name)
    return found[0] if found else None


def _hide(model, name: str, *, sketch_kind: bool) -> None:
    feature = find_feature(model, name)
    if feature is None:
        return
    model.ClearSelection2(True)
    with contextlib.suppress(Exception):
        if feature.Select2(False, 0):
            if sketch_kind:
                model.BlankSketch()
            else:
                blank = model.BlankRefGeom
                blank() if callable(blank) else com_value(blank)
    model.ClearSelection2(True)


def _delete_prefixed(model) -> None:
    named = [f for f in iter_features(model) if str(com_value(f.Name) or "").startswith(PREFIX)]
    for feature in reversed(named):
        model.ClearSelection2(True)
        with contextlib.suppress(Exception):
            if feature.Select2(False, 0):
                model.Extension.DeleteSelection2(3)
    model.ClearSelection2(True)


def _say(progress, text: str) -> None:
    if progress is not None:
        with contextlib.suppress(Exception):
            progress(text)
