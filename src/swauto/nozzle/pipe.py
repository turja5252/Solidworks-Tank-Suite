"""Pipe outside diameter and wall for a shell nozzle neck.

ASME B36.10 STD, XS, and XXS. Sizes are the regular nozzle sizes in the AutoCAD
program, 3/4 in through 24 in. XXS stops at 12 in; larger pipe has no XXS wall.
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical size, outside diameter, then STD, XS, and XXS wall. XXS is omitted
# where ASME B36.10 does not list one.
_PIPE: dict[str, tuple[float, dict[str, float]]] = {
    "3/4": (1.050, {"STD": 0.113, "XS": 0.154, "XXS": 0.308}),
    "1": (1.315, {"STD": 0.133, "XS": 0.179, "XXS": 0.358}),
    "1-1/2": (1.900, {"STD": 0.145, "XS": 0.200, "XXS": 0.400}),
    "2": (2.375, {"STD": 0.154, "XS": 0.218, "XXS": 0.436}),
    "2-1/2": (2.875, {"STD": 0.203, "XS": 0.276, "XXS": 0.552}),
    "3": (3.500, {"STD": 0.216, "XS": 0.300, "XXS": 0.600}),
    "4": (4.500, {"STD": 0.237, "XS": 0.337, "XXS": 0.674}),
    "6": (6.625, {"STD": 0.280, "XS": 0.432, "XXS": 0.864}),
    "8": (8.625, {"STD": 0.322, "XS": 0.500, "XXS": 0.875}),
    "10": (10.750, {"STD": 0.365, "XS": 0.500, "XXS": 1.000}),
    "12": (12.750, {"STD": 0.375, "XS": 0.500, "XXS": 1.000}),
    "14": (14.000, {"STD": 0.375, "XS": 0.500}),
    "16": (16.000, {"STD": 0.375, "XS": 0.500}),
    "18": (18.000, {"STD": 0.375, "XS": 0.500}),
    "20": (20.000, {"STD": 0.375, "XS": 0.500}),
    "22": (22.000, {"STD": 0.375, "XS": 0.500}),
    "24": (24.000, {"STD": 0.375, "XS": 0.500}),
}

_NPS_ALIASES = {
    "3/4": "3/4",
    "0.75": "3/4",
    ".75": "3/4",
    "1": "1",
    "1.0": "1",
    "1 1/2": "1-1/2",
    "1.5": "1-1/2",
    "2": "2",
    "2.0": "2",
    "2 1/2": "2-1/2",
    "2.5": "2-1/2",
    "3": "3",
    "3.0": "3",
    "4": "4",
    "4.0": "4",
    "6": "6",
    "6.0": "6",
    "8": "8",
    "8.0": "8",
    "10": "10",
    "10.0": "10",
    "12": "12",
    "12.0": "12",
    "14": "14",
    "14.0": "14",
    "16": "16",
    "16.0": "16",
    "18": "18",
    "18.0": "18",
    "20": "20",
    "20.0": "20",
    "22": "22",
    "22.0": "22",
    "24": "24",
    "24.0": "24",
}


def nps_sizes() -> tuple[str, ...]:
    """Regular shell nozzle sizes, 3/4 in through 24 in."""
    return tuple(_PIPE)


def normalize_nps(value: object) -> str:
    """Return the table key for a pipe size, such as ``6`` or ``1 1/2``."""
    text = str(value).strip().lower().replace('"', "")
    for word in ("inches", "inch"):
        text = text.replace(word, "")
    if text.endswith(" in"):
        text = text[: -len(" in")]
    text = " ".join(text.replace("-", " ").split())
    found = _NPS_ALIASES.get(text)
    if found is None:
        raise ValueError(f"Nozzle size {value!s} is not a regular shell nozzle size (3/4 through 24).")
    return found


def normalize_schedule(value: object) -> str:
    """Return ``STD``, ``XS``, or ``XXS``."""
    text = str(value).strip().upper().replace("-", "").replace(" ", "")
    found = {"STD": "STD", "XS": "XS", "XH": "XS", "XXS": "XXS", "XXH": "XXS"}.get(text)
    if found is None:
        raise ValueError(f"Schedule {value!s} must be STD, XS, or XXS.")
    return found


@dataclass(frozen=True)
class Pipe:
    """One neck: outside diameter and wall, in inches."""

    nps: str
    schedule: str
    outside_diameter_in: float
    wall_in: float

    @property
    def inside_diameter_in(self) -> float:
        return self.outside_diameter_in - 2.0 * self.wall_in


def pipe(nps: object, schedule: object = "XS") -> Pipe:
    """Look up the neck for a nominal size and schedule."""
    size = normalize_nps(nps)
    wall_name = normalize_schedule(schedule)
    outside, walls = _PIPE[size]
    wall = walls.get(wall_name)
    if wall is None:
        raise ValueError(f"ASME B36.10 has no {wall_name} wall for {size} in pipe.")
    return Pipe(nps=size, schedule=wall_name, outside_diameter_in=outside, wall_in=wall)
