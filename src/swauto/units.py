"""Length conversion. SolidWorks API distances are always meters."""

_TO_METERS = {
    "m": 1.0,
    "mm": 0.001,
    "in": 0.0254,
    "ft": 0.3048,
}


def to_meters(value: float, unit: str) -> float:
    key = unit.strip().lower()
    if key not in _TO_METERS:
        allowed = ", ".join(sorted(_TO_METERS))
        raise ValueError(f"Unsupported unit {unit!r}. Use one of: {allowed}")
    if value <= 0:
        raise ValueError("Length must be greater than zero.")
    return value * _TO_METERS[key]
