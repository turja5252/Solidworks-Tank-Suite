"""Pipe outside diameter and wall for a shell nozzle neck.

ASME B36.10M (carbon steel: schedules 5 through 160, STD, XS and XXS) and B36.19M (stainless: 5S, 10S, 40S and 80S),
for every size B16.5 has a flange for, 1/2 in through 24 in. A wall the standards do not list for a size (XXS over
12 in, Sch 160 at 3-1/2 in, the S schedules' heavier walls over 12 in, ...) is refused, not guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

# The schedules, thinnest family first. Sch 5 and 10 below 14 in are the 5S and 10S walls; STD and XS part from
# Sch 40 and 80 from 10 in up.
SCHEDULES = ("5S", "5", "10S", "10", "20", "30", "STD", "40", "40S", "60", "XS", "80", "80S", "100", "120", "140",
             "160", "XXS")
_ = None
# Canonical size: outside diameter, then the wall in each of SCHEDULES (None where the standards list none).
_ROWS: dict[str, tuple[float, tuple[float | None, ...]]] = {
    # 5S, 5, 10S, 10, 20, 30, STD, 40, 40S, 60, XS, 80, 80S, 100, 120, 140, 160, XXS
    "1/2": (0.840, (0.065, 0.065, 0.083, 0.083, _, 0.095, 0.109, 0.109, 0.109, _, 0.147, 0.147, 0.147, _, _, _,
                    0.188, 0.294)),
    "3/4": (1.050, (0.065, 0.065, 0.083, 0.083, _, 0.095, 0.113, 0.113, 0.113, _, 0.154, 0.154, 0.154, _, _, _,
                    0.219, 0.308)),
    "1": (1.315, (0.065, 0.065, 0.109, 0.109, _, 0.114, 0.133, 0.133, 0.133, _, 0.179, 0.179, 0.179, _, _, _, 0.250,
                  0.358)),
    "1-1/4": (1.660, (0.065, 0.065, 0.109, 0.109, _, 0.117, 0.140, 0.140, 0.140, _, 0.191, 0.191, 0.191, _, _, _,
                      0.250, 0.382)),
    "1-1/2": (1.900, (0.065, 0.065, 0.109, 0.109, _, 0.125, 0.145, 0.145, 0.145, _, 0.200, 0.200, 0.200, _, _, _,
                      0.281, 0.400)),
    "2": (2.375, (0.065, 0.065, 0.109, 0.109, _, 0.125, 0.154, 0.154, 0.154, _, 0.218, 0.218, 0.218, _, _, _, 0.344,
                  0.436)),
    "2-1/2": (2.875, (0.083, 0.083, 0.120, 0.120, _, 0.188, 0.203, 0.203, 0.203, _, 0.276, 0.276, 0.276, _, _, _,
                      0.375, 0.552)),
    "3": (3.500, (0.083, 0.083, 0.120, 0.120, _, 0.188, 0.216, 0.216, 0.216, _, 0.300, 0.300, 0.300, _, _, _, 0.438,
                  0.600)),
    "3-1/2": (4.000, (0.083, 0.083, 0.120, 0.120, _, 0.188, 0.226, 0.226, 0.226, _, 0.318, 0.318, 0.318, _, _, _, _,
                      0.636)),
    "4": (4.500, (0.083, 0.083, 0.120, 0.120, _, 0.188, 0.237, 0.237, 0.237, _, 0.337, 0.337, 0.337, _, 0.438, _,
                  0.531, 0.674)),
    "5": (5.563, (0.109, 0.109, 0.134, 0.134, _, _, 0.258, 0.258, 0.258, _, 0.375, 0.375, 0.375, _, 0.500, _, 0.625,
                  0.750)),
    "6": (6.625, (0.109, 0.109, 0.134, 0.134, _, _, 0.280, 0.280, 0.280, _, 0.432, 0.432, 0.432, _, 0.562, _, 0.719,
                  0.864)),
    "8": (8.625, (0.109, 0.109, 0.148, 0.148, 0.250, 0.277, 0.322, 0.322, 0.322, 0.406, 0.500, 0.500, 0.500, 0.594,
                  0.719, 0.812, 0.906, 0.875)),
    "10": (10.750, (0.134, 0.134, 0.165, 0.165, 0.250, 0.307, 0.365, 0.365, 0.365, 0.500, 0.500, 0.594, 0.500, 0.719,
                    0.844, 1.000, 1.125, 1.000)),
    "12": (12.750, (0.156, 0.156, 0.180, 0.180, 0.250, 0.330, 0.375, 0.406, 0.375, 0.562, 0.500, 0.688, 0.500, 0.844,
                    1.000, 1.125, 1.312, 1.000)),
    "14": (14.000, (0.156, 0.156, 0.188, 0.250, 0.312, 0.375, 0.375, 0.438, _, 0.594, 0.500, 0.750, _, 0.938, 1.094,
                    1.250, 1.406, _)),
    "16": (16.000, (0.165, 0.165, 0.188, 0.250, 0.312, 0.375, 0.375, 0.500, _, 0.656, 0.500, 0.844, _, 1.031, 1.219,
                    1.438, 1.594, _)),
    "18": (18.000, (0.165, 0.165, 0.188, 0.250, 0.312, 0.438, 0.375, 0.562, _, 0.750, 0.500, 0.938, _, 1.156, 1.375,
                    1.562, 1.781, _)),
    "20": (20.000, (0.188, 0.188, 0.218, 0.250, 0.375, 0.500, 0.375, 0.594, _, 0.812, 0.500, 1.031, _, 1.281, 1.500,
                    1.750, 1.969, _)),
    "22": (22.000, (0.188, 0.188, 0.218, 0.250, 0.375, 0.500, 0.375, _, _, 0.875, 0.500, 1.125, _, 1.375, 1.625,
                    1.875, 2.125, _)),
    "24": (24.000, (0.218, 0.218, 0.250, 0.250, 0.375, 0.562, 0.375, 0.688, _, 0.969, 0.500, 1.219, _, 1.531, 1.812,
                    2.062, 2.344, _)),
}
_PIPE: dict[str, tuple[float, dict[str, float]]] = {
    size: (outside, {name: wall for name, wall in zip(SCHEDULES, walls, strict=True) if wall is not None})
    for size, (outside, walls) in _ROWS.items()
}


def _aliases(size: str) -> set[str]:
    """How a size may be typed: 1-1/4, 1 1/4, 1.25, 1.250; 1/2, 0.5, .5; 6, 6.0."""
    whole, _dash, part = size.partition("-")
    if "/" in size:
        top, _slash, bottom = (part or whole).partition("/")
        value = (float(whole) if part else 0.0) + float(top) / float(bottom)
    else:
        value = float(size)
    decimal = f"{value:g}"
    typed = {size, size.replace("-", " "), decimal, decimal.removeprefix("0"), f"{value:.2f}", f"{value:.3f}"}
    if float(f"{value:.1f}") == value:
        typed.add(f"{value:.1f}")
    return typed


_NPS_ALIASES: dict[str, str] = {alias: size for size in _ROWS for alias in _aliases(size)}


def nps_sizes() -> tuple[str, ...]:
    """Shell nozzle sizes, every one B16.5 has a flange for: 1/2 in through 24 in."""
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
        raise ValueError(f"Nozzle size {value!s} is not a pipe size B16.5 has a flange for (1/2 through 24).")
    return found


def normalize_schedule(value: object) -> str:
    """Return one of ``SCHEDULES``. Takes 40, Sch 40, S-40, STD, Standard, XS, XH, Extra Strong, XXS, XXH, 10S..."""
    text = str(value).strip().upper().replace("-", "").replace(" ", "").replace(".", "")
    for word in ("SCHEDULE", "SCH", "S"):
        if text.startswith(word) and text[len(word):len(word) + 1].isdigit():
            text = text[len(word):]
            break
    words = {"STANDARD": "STD", "XH": "XS", "EXTRASTRONG": "XS", "XXH": "XXS", "DOUBLEEXTRASTRONG": "XXS"}
    text = words.get(text, text)
    if text not in SCHEDULES:
        raise ValueError(f"Schedule {value!s} is not an ASME B36.10M or B36.19M schedule ({', '.join(SCHEDULES)}).")
    return text


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
        standard = "B36.19M" if wall_name in ("5S", "10S", "40S", "80S") else "B36.10M"
        raise ValueError(f"ASME {standard} has no {wall_name} wall for {size} in pipe.")
    return Pipe(nps=size, schedule=wall_name, outside_diameter_in=outside, wall_in=wall)
