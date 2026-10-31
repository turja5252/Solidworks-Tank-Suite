"""ASME B16.21 flat ring gaskets for Class 150 and Class 300 raised-face flanges, in inches.

The ring's inside diameter is the pipe outside diameter; its outside diameter
reaches the bolts, so it centers on them. The thickness and the material are
typed on the nozzle; a blank thickness is 1/8 in. NPS 22 is not in every
B16.21 edition: its outside diameters are the bolt circle less one bolt's
diameter, the rule every other size follows.
"""

from __future__ import annotations

from dataclasses import dataclass

from swauto.nozzle.flange import normalize_rating
from swauto.nozzle.pipe import normalize_nps

DEFAULT_THICKNESS_IN = 0.125

# nps: (inside diameter, outside diameter for Class 150, outside diameter for Class 300)
_RINGS: dict[str, tuple[float, float, float]] = {
    "1/2": (0.84, 1.88, 2.12),
    "3/4": (1.06, 2.25, 2.62),
    "1": (1.31, 2.62, 2.88),
    "1-1/4": (1.66, 3.00, 3.25),
    "1-1/2": (1.91, 3.38, 3.75),
    "2": (2.38, 4.12, 4.38),
    "2-1/2": (2.88, 4.88, 5.12),
    "3": (3.50, 5.38, 5.88),
    "3-1/2": (4.00, 6.38, 6.50),
    "4": (4.50, 6.88, 7.12),
    "5": (5.56, 7.75, 8.50),
    "6": (6.62, 8.75, 9.88),
    "8": (8.62, 11.00, 12.12),
    "10": (10.75, 13.38, 14.25),
    "12": (12.75, 16.12, 16.62),
    "14": (14.00, 17.75, 19.12),
    "16": (16.00, 20.25, 21.25),
    "18": (18.00, 21.62, 23.50),
    "20": (20.00, 23.88, 25.75),
    "22": (22.00, 26.00, 28.00),
    "24": (24.00, 28.25, 30.50),
}


@dataclass(frozen=True)
class Gasket:
    """One flat ring gasket on the raised face."""

    inner_diameter_in: float
    outer_diameter_in: float
    thickness_in: float
    material: str

    @property
    def label(self) -> str:
        size = f"{self.inner_diameter_in:g} ID x {self.outer_diameter_in:g} OD"
        return f"{self.material}, {self.thickness_in:g} in, {size}"


def gasket(nps: object, rating: object, material: str, thickness_in: float | None = None) -> Gasket:
    """Look up the ring for one flange. ``material`` is whatever the user typed."""
    size = normalize_nps(nps)
    pressure = normalize_rating(rating)
    text = " ".join(str(material).split())
    if not text:
        raise ValueError("Type the gasket material.")
    thickness = DEFAULT_THICKNESS_IN if thickness_in is None else float(thickness_in)
    if not 0.0 < thickness <= 1.0:
        raise ValueError(f"Gasket thickness {thickness:g} in must be over 0 and at most 1 in.")
    inner, outer_150, outer_300 = _RINGS[size]
    return Gasket(
        inner_diameter_in=inner,
        outer_diameter_in=outer_150 if pressure == 150 else outer_300,
        thickness_in=thickness,
        material=text,
    )
