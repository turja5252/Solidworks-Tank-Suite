"""Read/write SolidWorks driving dimensions (meters) and rebuild."""

from __future__ import annotations

import contextlib

from swauto.comutil import com_value, format_com_error
from swauto.errors import SolidWorksError


def set_parameter_meters(model, full_name: str, meters: float) -> None:
    param = model.Parameter(full_name)
    if param is None:
        raise SolidWorksError(f"Parameter not found: {full_name}")
    try:
        param.SystemValue = float(meters)
    except Exception as exc:
        raise SolidWorksError(
            f"Could not set {full_name} to {meters} m: {format_com_error(exc)}"
        ) from exc


def rebuild(model) -> None:
    """Rebuild the model. On SW2013, EditRebuild3 is sometimes a bool, not a method."""
    errors: list[str] = []
    for name, args in (
        ("ForceRebuild3", (False,)),
        ("EditRebuild3", ()),
        ("EditRebuild2", ()),
        ("EditRebuild", ()),
    ):
        member = getattr(model, name, None)
        if member is None:
            continue
        if not callable(member):
            # Late-bound property / cached HRESULT — skip.
            continue
        try:
            member(*args)
            return
        except Exception as exc:
            errors.append(f"{name}: {format_com_error(exc)}")
            continue
    detail = "; ".join(errors) if errors else "no rebuild API worked"
    raise SolidWorksError(f"Rebuild failed: {detail}")


def rename_feature(feature, name: str) -> str:
    with contextlib.suppress(Exception):
        feature.Name = name
    return str(com_value(feature.Name) or name)


def first_dimension_full_name(feature) -> str | None:
    """Return FullName of the first display dimension on a feature, if any."""
    try:
        disp = feature.GetFirstDisplayDimension()
    except Exception:
        return None
    while disp is not None:
        try:
            dim = disp.GetDimension()
        except Exception:
            dim = None
        if dim is not None:
            full = str(com_value(dim.FullName) or "")
            if full:
                return full
        try:
            disp = disp.GetNext()
        except Exception:
            break
    return None


def rename_dimension(model, full_name: str, new_short_name: str) -> str:
    """Rename a dimension's short name; return the new FullName."""
    param = model.Parameter(full_name)
    if param is None:
        return full_name
    try:
        # IDimension.Name is the short name (before @Feature).
        param.Name = new_short_name
    except Exception:
        return full_name
    feature_part = ""
    if "@" in full_name:
        feature_part = full_name.split("@", 1)[1]
    if feature_part:
        return f"{new_short_name}@{feature_part}"
    return str(com_value(param.FullName) or full_name)
