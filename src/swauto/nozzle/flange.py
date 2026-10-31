"""ASME B16.5 Class 150 and Class 300 flange dimensions, in inches.

Thickness and length through the hub do not include the raised face. The raised
face is 0.06 in, added on the gasket side (B16.5 para. 6.4). Bolt holes straddle
the centerlines. A weld neck bore is the pipe bore for the schedule on the
nozzle; the hub runs from the hub diameter at the back face out to the pipe
outside diameter. A slip-on bore is the standard bore the pipe slides into.
"""

from __future__ import annotations

from dataclasses import dataclass

from swauto.nozzle.pipe import normalize_nps

RAISED_FACE_IN = 0.06

# nps, outside diameter, thickness, hub diameter, slip-on length through hub,
# weld-neck length through hub, slip-on bore, raised-face diameter, bolt circle,
# bolt count, bolt-hole diameter, bolt diameter.
_Row = tuple[str, float, float, float, float, float, float, float, float, int, float, float]

_CLASS_150: tuple[_Row, ...] = (
    ("1/2", 3.50, 0.38, 1.19, 0.56, 1.82, 0.88, 1.375, 2.38, 4, 0.63, 0.50),
    ("3/4", 3.88, 0.44, 1.50, 0.56, 2.00, 1.09, 1.688, 2.75, 4, 0.63, 0.50),
    ("1", 4.25, 0.50, 1.94, 0.62, 2.12, 1.36, 2.000, 3.12, 4, 0.63, 0.50),
    ("1-1/4", 4.62, 0.56, 2.31, 0.75, 2.19, 1.70, 2.500, 3.50, 4, 0.63, 0.50),
    ("1-1/2", 5.00, 0.62, 2.56, 0.81, 2.38, 1.95, 2.875, 3.88, 4, 0.63, 0.50),
    ("2", 6.00, 0.69, 3.06, 0.94, 2.44, 2.44, 3.625, 4.75, 4, 0.75, 0.625),
    ("2-1/2", 7.00, 0.81, 3.56, 1.06, 2.69, 2.94, 4.125, 5.50, 4, 0.75, 0.625),
    ("3", 7.50, 0.88, 4.25, 1.12, 2.69, 3.57, 5.000, 6.00, 4, 0.75, 0.625),
    ("3-1/2", 8.50, 0.88, 4.81, 1.19, 2.75, 4.07, 5.500, 7.00, 8, 0.75, 0.625),
    ("4", 9.00, 0.88, 5.31, 1.25, 2.94, 4.57, 6.188, 7.50, 8, 0.75, 0.625),
    ("5", 10.00, 0.88, 6.44, 1.38, 3.44, 5.66, 7.312, 8.50, 8, 0.875, 0.75),
    ("6", 11.00, 0.94, 7.56, 1.50, 3.44, 6.72, 8.500, 9.50, 8, 0.875, 0.75),
    ("8", 13.50, 1.06, 9.69, 1.69, 3.94, 8.72, 10.625, 11.75, 8, 0.875, 0.75),
    ("10", 16.00, 1.12, 12.00, 1.88, 3.94, 10.88, 12.750, 14.25, 12, 1.000, 0.875),
    ("12", 19.00, 1.19, 14.38, 2.12, 4.44, 12.88, 15.000, 17.00, 12, 1.000, 0.875),
    ("14", 21.00, 1.31, 15.75, 2.19, 4.94, 14.14, 16.250, 18.75, 12, 1.125, 1.00),
    ("16", 23.50, 1.38, 18.00, 2.44, 4.94, 16.16, 18.500, 21.25, 16, 1.125, 1.00),
    ("18", 25.00, 1.50, 19.88, 2.62, 5.44, 18.18, 21.000, 22.75, 16, 1.250, 1.125),
    ("20", 27.50, 1.62, 22.00, 2.81, 5.62, 20.20, 23.000, 25.00, 20, 1.250, 1.125),
    ("22", 29.50, 1.75, 24.00, 3.06, 5.82, 22.22, 25.250, 27.25, 20, 1.375, 1.25),
    ("24", 32.00, 1.81, 26.12, 3.19, 5.94, 24.25, 27.250, 29.50, 20, 1.375, 1.25),
)

_CLASS_300: tuple[_Row, ...] = (
    ("1/2", 3.75, 0.50, 1.50, 0.82, 2.00, 0.88, 1.375, 2.62, 4, 0.63, 0.50),
    ("3/4", 4.62, 0.56, 1.88, 0.94, 2.19, 1.09, 1.688, 3.25, 4, 0.75, 0.625),
    ("1", 4.88, 0.62, 2.12, 1.00, 2.38, 1.36, 2.000, 3.50, 4, 0.75, 0.625),
    ("1-1/4", 5.25, 0.69, 2.50, 1.00, 2.50, 1.70, 2.500, 3.88, 4, 0.75, 0.625),
    ("1-1/2", 6.12, 0.75, 2.75, 1.13, 2.63, 1.95, 2.875, 4.50, 4, 0.875, 0.75),
    ("2", 6.50, 0.81, 3.31, 1.25, 2.69, 2.44, 3.625, 5.00, 8, 0.75, 0.625),
    ("2-1/2", 7.50, 0.94, 3.94, 1.44, 2.94, 2.94, 4.125, 5.88, 8, 0.875, 0.75),
    ("3", 8.25, 1.06, 4.62, 1.63, 3.06, 3.57, 5.000, 6.62, 8, 0.875, 0.75),
    ("3-1/2", 9.00, 1.12, 5.25, 1.69, 3.13, 4.07, 5.500, 7.25, 8, 0.875, 0.75),
    ("4", 10.00, 1.19, 5.75, 1.82, 3.32, 4.57, 6.188, 7.88, 8, 0.875, 0.75),
    ("5", 11.00, 1.31, 7.00, 1.94, 3.82, 5.66, 7.312, 9.25, 8, 0.875, 0.75),
    ("6", 12.50, 1.38, 8.12, 2.00, 3.82, 6.72, 8.500, 10.62, 12, 0.875, 0.75),
    ("8", 15.00, 1.56, 10.25, 2.38, 4.32, 8.72, 10.625, 13.00, 12, 1.000, 0.875),
    ("10", 17.50, 1.81, 12.62, 2.56, 4.56, 10.88, 12.750, 15.25, 16, 1.125, 1.00),
    ("12", 20.50, 1.94, 14.75, 2.82, 5.06, 12.88, 15.000, 17.75, 16, 1.250, 1.125),
    ("14", 23.00, 2.06, 16.75, 2.94, 5.56, 14.14, 16.250, 20.25, 20, 1.250, 1.125),
    ("16", 25.50, 2.19, 19.00, 3.19, 5.69, 16.16, 18.500, 22.50, 20, 1.375, 1.25),
    ("18", 28.00, 2.31, 21.00, 3.44, 6.19, 18.18, 21.000, 24.75, 24, 1.375, 1.25),
    ("20", 30.50, 2.44, 23.12, 3.69, 6.32, 20.20, 23.000, 27.00, 24, 1.375, 1.25),
    ("22", 33.00, 2.56, 25.25, 3.94, 6.44, 22.22, 25.250, 29.50, 24, 1.625, 1.50),
    ("24", 36.00, 2.69, 27.62, 4.13, 6.56, 24.25, 27.250, 32.00, 24, 1.625, 1.50),
)

_TABLES: dict[int, dict[str, _Row]] = {
    150: {row[0]: row for row in _CLASS_150},
    300: {row[0]: row for row in _CLASS_300},
}


def normalize_rating(value: object) -> int:
    """Return ``150`` or ``300``."""
    text = str(value).strip().lower().replace("class", "").replace("#", "").replace("lb", "").strip()
    found = {"150": 150, "300": 300}.get(text)
    if found is None:
        raise ValueError(f"Flange class {value!s} must be 150 or 300.")
    return found


def normalize_kind(value: object) -> str:
    """Return ``wn`` for a weld neck or ``so`` for a slip-on."""
    text = str(value).strip().lower().replace("_", " ").replace("-", " ")
    text = " ".join(text.split())
    found = {
        "wn": "wn",
        "weld neck": "wn",
        "welding neck": "wn",
        "rfwn": "wn",
        "so": "so",
        "slip on": "so",
        "slipon": "so",
        "rfso": "so",
    }.get(text)
    if found is None:
        raise ValueError(f"Flange type {value!s} must be a weld neck or a slip-on.")
    return found


@dataclass(frozen=True)
class Flange:
    """One raised-face flange. Lengths are inches and do not include the 0.06 in face."""

    nps: str
    rating: int
    kind: str
    outside_diameter_in: float
    thickness_in: float
    hub_diameter_in: float
    length_through_hub_in: float
    slip_on_bore_in: float
    raised_face_diameter_in: float
    bolt_circle_in: float
    bolt_count: int
    bolt_hole_diameter_in: float
    bolt_diameter_in: float

    @property
    def raised_face_in(self) -> float:
        return RAISED_FACE_IN

    @property
    def overall_thickness_in(self) -> float:
        """Back of the flange to the top of the raised face."""
        return self.thickness_in + RAISED_FACE_IN

    @property
    def face_to_hub_end_in(self) -> float:
        """Raised face to the end of the hub."""
        return self.length_through_hub_in + RAISED_FACE_IN

    @property
    def hub_past_back_in(self) -> float:
        """How far the hub sticks past the back face of the flange."""
        return self.length_through_hub_in - self.thickness_in


def flange(nps: object, rating: object = 150, kind: object = "wn") -> Flange:
    """Look up one Class 150 or Class 300 weld neck or slip-on."""
    size = normalize_nps(nps)
    pressure = normalize_rating(rating)
    shape = normalize_kind(kind)
    row = _TABLES[pressure][size]
    length = row[4] if shape == "so" else row[5]
    return Flange(
        nps=size,
        rating=pressure,
        kind=shape,
        outside_diameter_in=row[1],
        thickness_in=row[2],
        hub_diameter_in=row[3],
        length_through_hub_in=length,
        slip_on_bore_in=row[6],
        raised_face_diameter_in=row[7],
        bolt_circle_in=row[8],
        bolt_count=row[9],
        bolt_hole_diameter_in=row[10],
        bolt_diameter_in=row[11],
    )
