"""Part document helpers that work on SolidWorks 2013 and newer."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError

# swUserPreferenceStringValue_e.swDefaultTemplatePart
_DEFAULT_TEMPLATE_PART = 0

# Common English plane names, then first-feature fallbacks used by some installs.
_FRONT_PLANE_NAMES = ("Front Plane", "Plane1", "Front")
_TOP_PLANE_NAMES = ("Top Plane", "Plane2", "Top")

# swStartConditions_e.swStartOffset (used by FeatureExtrusionThin2)
_START_OFFSET = 3


@contextlib.contextmanager
def quiet(app, model):
    """While a build runs: tell SolidWorks an API command is in progress, and stop it redrawing ``model`` and its
    feature tree after every feature; all back on after, and one redraw. The stair parts built 6.5x faster with
    identical geometry (2026-10-30: 409 s to 63 s); a part watched while it builds is several times slower."""
    _quiet(app, model, True)
    try:
        yield
    finally:
        _quiet(app, model, False)
        with contextlib.suppress(Exception):
            model.GraphicsRedraw2()


def _quiet(app, model, on: bool) -> None:
    with contextlib.suppress(Exception):
        app.CommandInProgress = on
    with contextlib.suppress(Exception):
        model.FeatureManager.EnableFeatureTree = not on
    with contextlib.suppress(Exception):
        view = com_value(model.ActiveView)
        if view is not None:
            view.EnableGraphicsUpdate = not on


def new_part(app):
    """Create a new part from a real .prtdot path only.

    Do not call NewPart() — on many installs that opens a modal template dialog
    and looks like a hang when another window is on top.
    """
    tried: list[str] = []
    for template in _part_template_candidates(app):
        tried.append(template)
        try:
            model = app.NewDocument(template, 0, 0, 0)
        except Exception as exc:
            raise SolidWorksError(
                f"NewDocument failed for:\n{template}\n{format_com_error(exc)}"
            ) from exc
        if model is not None:
            return model

    hint = "\n".join(f"  - {path}" for path in tried[:6]) or "  (none found)"
    raise SolidWorksError(
        "Could not create a new SolidWorks part (no usable Part template).\n\n"
        "In SolidWorks:\n"
        "  Tools > Options > System Options > Default Templates\n"
        "  Browse to Part.prtdot, click OK, then try again.\n\n"
        "Paths tried:\n"
        f"{hint}"
    )


def _part_template_candidates(app) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    def add(path: str) -> None:
        text = str(path or "").strip().strip('"')
        if not text or text in seen:
            return
        seen.add(text)
        if Path(text).is_file():
            ordered.append(text)

    add(str(com_value(app.GetUserPreferenceStringValue(_DEFAULT_TEMPLATE_PART)) or ""))
    for path in candidate_part_templates():
        add(path)
    return ordered


def candidate_part_templates() -> list[str]:
    """Likely Part.prtdot locations for SolidWorks 2013 and later."""
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SolidWorks"
    if not program_data.is_dir():
        return []

    found: list[str] = []
    for folder in program_data.glob("SolidWorks *"):
        for relative in (
            Path("templates") / "Part.prtdot",
            Path("templates") / "part.prtdot",
            Path("lang") / "english" / "Document Templates" / "Part.prtdot",
        ):
            path = folder / relative
            if path.is_file():
                found.append(str(path))

    # Prefer older installs first so the Solidworks computer's 2013 template wins when present.
    found.sort(key=lambda path: (0 if "2013" in path else 1, path.lower()))
    return found


def select_front_plane(model) -> None:
    for name in _FRONT_PLANE_NAMES:
        if select_plane(model, name):
            return
    raise SolidWorksError(
        "Could not select the Front Plane. "
        "Open a blank part manually and confirm the plane is named Front Plane."
    )


def select_top_plane(model) -> None:
    for name in _TOP_PLANE_NAMES:
        if select_plane(model, name):
            return
    raise SolidWorksError(
        "Could not select the Top Plane. "
        "Open a blank part manually and confirm the plane is named Top Plane."
    )


def select_plane(model, name: str) -> bool:
    """Select a named plane. Returns True when selection succeeds."""
    return _select_plane(model, name)


def _select_plane(model, name: str) -> bool:
    """Select a plane. Avoid plain None for the Callout arg (type mismatch on SW2013)."""
    nothing = com_nothing()
    extension = model.Extension
    try:
        if extension.SelectByID2(name, "PLANE", 0.0, 0.0, 0.0, False, 0, nothing, 0):
            return True
    except Exception:
        pass

    select_by_id = getattr(model, "SelectByID", None)
    if select_by_id is not None:
        try:
            if select_by_id(name, "PLANE", 0.0, 0.0, 0.0):
                return True
        except Exception:
            pass

    try:
        if extension.SelectByID2(name, "PLANE", 0.0, 0.0, 0.0, False, 0, 0, 0):
            return True
    except Exception:
        pass
    return False


def extrude_blind(
    feature_manager,
    depth_m: float,
    *,
    merge: bool = True,
    flip: bool = False,
    reverse: bool = False,
    start_offset_m: float = 0.0,
    prefer_legacy: bool = True,
):
    """Blind boss-extrude the selected sketch. Tries newer then older FeatureExtrusion2 signatures.

    ``reverse`` flips the extrude off the sketch plane. On the Top plane that
    sends a floor plate downward from the shell datum.
    """
    depth = float(depth_m)
    start = float(start_offset_m)
    t0 = _START_OFFSET if start > 1e-12 else 0
    legacy = (
        True,
        bool(flip),
        bool(reverse),
        0,
        0,
        depth,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        bool(merge),
        True,
        True,
    )
    modern = legacy + (t0, start, False)
    # Prefer modern when a start offset is required (legacy has no Z lift).
    if start > 1e-12:
        order = (modern, legacy)
    elif prefer_legacy:
        order = (legacy, modern)
    else:
        order = (modern, legacy)

    errors: list[str] = []
    for args in order:
        try:
            feature = feature_manager.FeatureExtrusion2(*args)
        except Exception as exc:
            errors.append(f"{len(args)}-arg: {format_com_error(exc)}")
            continue
        if feature is not None:
            return feature
        errors.append(f"{len(args)}-arg: returned nothing")

    detail = "; ".join(errors) if errors else "unknown failure"
    raise SolidWorksError(f"Extrude failed ({detail}).")


def extrude_thin_blind(
    feature_manager,
    depth_m: float,
    thickness_m: float,
    *,
    start_offset_m: float = 0.0,
):
    """Blind thin-wall extrude of the selected circle sketch (SolidWorks 2013-safe).

    Optional start_offset_m raises the extrude above the sketch plane (no offset plane needed).
    """
    depth = float(depth_m)
    thk = float(thickness_m)
    start = float(start_offset_m)
    if thk <= 0 or depth <= 0:
        raise SolidWorksError("Thin extrude needs positive depth and thickness.")

    t0 = _START_OFFSET if start > 1e-12 else 0

    thin2 = (
        True,
        False,
        False,
        0,
        0,
        depth,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,  # Merge
        thk,
        0.0,
        0.0,
        0,  # RevThinDir
        0,  # CapEnds
        False,
        0.0,
        True,
        True,
        t0,
        start,
        False,
    )
    thin1 = (
        True,
        False,
        False,
        0,
        0,
        depth,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        thk,
        0.0,
        0.0,
        0,
        0,
        False,
        0.0,
    )

    errors: list[str] = []
    attempts: list[tuple[str, tuple]] = [
        ("FeatureExtrusionThin2", thin2),
    ]
    if start <= 1e-12:
        attempts.append(("FeatureExtrusionThin2", thin2[:27]))
        attempts.append(("FeatureExtrusionThin", thin1))

    for method_name, args in attempts:
        method = getattr(feature_manager, method_name, None)
        if method is None:
            continue
        try:
            feature = method(*args)
        except Exception as exc:
            errors.append(f"{method_name}/{len(args)}: {format_com_error(exc)}")
            continue
        if feature is not None:
            return feature
        errors.append(f"{method_name}/{len(args)}: returned nothing")

    # Try alternate start-condition enums if offset was requested.
    if start > 1e-12:
        for alt_t0 in (2, 1, 4):
            alt = list(thin2)
            alt[-3] = alt_t0
            method = getattr(feature_manager, "FeatureExtrusionThin2", None)
            if method is None:
                break
            try:
                feature = method(*alt)
            except Exception as exc:
                errors.append(f"Thin2/t0={alt_t0}: {format_com_error(exc)}")
                continue
            if feature is not None:
                return feature

    flipped = list(thin2)
    flipped[1] = True
    method = getattr(feature_manager, "FeatureExtrusionThin2", None)
    if method is not None:
        try:
            feature = method(*flipped)
            if feature is not None:
                return feature
        except Exception as exc:
            errors.append(f"FeatureExtrusionThin2/flip: {format_com_error(exc)}")

    detail = "; ".join(errors) if errors else "unknown failure"
    raise SolidWorksError(f"Thin extrude failed ({detail}).")


def cut_blind(
    feature_manager,
    depth_m: float,
    *,
    start_offset_m: float = 0.0,
):
    """Blind extruded cut of the selected sketch (SW2013-safe tries)."""
    depth = float(depth_m)
    start = float(start_offset_m)
    t0 = _START_OFFSET if start > 1e-12 else 0

    # Through-all first when no offset (separates a full ring in one go).
    through_all_3 = (
        True,
        False,
        False,
        1,
        0,
        0.01,
        0.01,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
    )
    blind = (
        True,
        False,
        False,
        0,
        0,
        depth,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
    )
    blind4 = blind + (True, False, 0, 0.0, False)  # FeatureCut4 extra
    blind4_off = (
        True,
        False,
        False,
        0,
        0,
        depth,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        True,
        False,
        t0,
        start,
        False,
    )

    errors: list[str] = []
    attempts: list[tuple[str, tuple]] = []
    if start <= 1e-12:
        attempts.append(("FeatureCut3", through_all_3))
        attempts.append(("FeatureCut4", through_all_3 + (True, False, 0, 0.0, False)))
        attempts.append(("FeatureCut3", blind))
        attempts.append(("FeatureCut4", blind4))
        attempts.append(("FeatureCut2", blind[:15]))
    else:
        attempts.append(("FeatureCut4", blind4_off))
        attempts.append(("FeatureCut3", blind))
        attempts.append(("FeatureCut4", blind4))

    for method_name, args in attempts:
        method = getattr(feature_manager, method_name, None)
        if method is None:
            continue
        try:
            feature = method(*args)
        except Exception as exc:
            errors.append(f"{method_name}/{len(args)}: {format_com_error(exc)}")
            continue
        if feature is not None:
            return feature
        errors.append(f"{method_name}/{len(args)}: returned nothing")

    detail = "; ".join(errors) if errors else "unknown failure"
    raise SolidWorksError(f"Cut failed ({detail}).")
