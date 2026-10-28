"""FTCO sizes and inputs, in inches. From the Elite AutoLISP FTCO Engine and Shell Plate Elevation.

Two sizes, named by the developed length of the shell insert plate. Outlines are
"stretchout" views looking at the shell from outside: x along the shell, y up
from the bottom of course 1, both measured from the FTCO centerline at the
course bottom. The opening is a 48 in wide arch: a half circle on straight
sides down to the course bottom.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.tank.plates import ANCHORS

OPENING_WIDTH_IN = 48.0
INSERT_TO_NECK_GAP_IN = 3.0 / 16.0  # insert cutout clears the neck OD by this
REPAD_TO_NECK_GAP_IN = 1.0 / 16.0  # repad cutout clears the neck OD by this
NECK_PAST_REPAD_IN = 5.0  # neck end (flange back) past the repad's outer face
BASEPLATE_PAST_INSERT_IN = 6.0  # bottom reinforcing plate past each insert end
FLANGE_HALF_WIDTH_IN = 28.5  # flange, gasket and cover: 57 in across, R28.5 arch
BOLT_HOLE_DIA_IN = 1.125
TELLTALE_DIA_IN = 0.25
LUG_BASE_HALF_IN = 2.5  # cover lifting lug, on top of the arch
LUG_TOP_HALF_IN = 1.0
LUG_RISE_IN = 31.39  # lug top above the arch center
LUG_HOLE_RISE_IN = 29.89
LUG_HOLE_DIA_IN = 1.5


@dataclass(frozen=True)
class Size:
    label: str
    insert_length_in: float  # developed, along the shell
    repad_length_in: float
    arch_center_in: float  # opening arch center above the course bottom
    repad_corner_x_in: float  # repad top corners: arcs centered at (+-x, y)
    repad_corner_y_in: float
    repad_corner_r_in: float
    telltale: tuple[float, float]
    flange_bottom_in: float  # flange, gasket and cover reach this far below the course bottom
    bolt_holes: tuple[tuple[float, float], ...]

    @property
    def opening_height_in(self) -> float:
        return self.arch_center_in + OPENING_WIDTH_IN / 2.0

    @property
    def repad_half_in(self) -> float:
        return self.repad_corner_x_in + self.repad_corner_r_in

    @property
    def repad_top_in(self) -> float:
        return self.repad_corner_y_in + self.repad_corner_r_in


def _mirror(right: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    """Bolt holes are symmetric about the centerline; the LISP lists both halves."""
    left = tuple((-x, y) for x, y in right if x > 1e-9)
    return tuple(sorted(right + left))


# Shell Plate Elevation SPE:draw-flange-item-125 / -1010 (right half, x >= 0).
_HOLES_125 = (
    (1.8, -3.5), (5.4, -3.5), (9.0, -3.5), (12.6, -3.5), (16.2, -3.5), (19.8, -3.5), (23.4, -3.5),
    (27.0, -3.0), (27.0, 1.5), (27.0, 5.2092), (27.0, 8.9185), (27.0, 12.6277), (27.0, 16.3369),
    (27.0, 20.0461), (27.0, 23.7554), (26.778, 27.4551), (26.0526, 31.0897), (24.8362, 34.5907),
    (23.1518, 37.8922), (21.0312, 40.9319), (18.5143, 43.6525), (15.6485, 46.0028), (12.4878, 47.9386),
    (9.0918, 49.4232), (5.5245, 50.4288), (1.8532, 50.9363),
)
_HOLES_1010 = (
    (1.8, -3.25), (5.4, -3.25), (9.0, -3.25), (12.6, -3.25), (16.2, -3.25), (19.8, -3.25), (23.4, -3.25),
    (27.0, -2.75), (27.0, 1.5), (27.0, 5.1491), (27.0, 8.7981), (26.9963, 12.4472), (26.6899, 16.0806),
    (25.8967, 19.6396), (24.6312, 23.0592), (22.9164, 26.2771), (20.7838, 29.2347), (18.272, 31.8779),
    (15.4271, 34.1586), (12.3008, 36.0352), (8.9501, 37.4734), (5.4362, 38.4471), (1.8231, 38.9384),
)

SIZES: dict[str, Size] = {
    "12'-5\"": Size(
        label="12'-5\"",
        insert_length_in=149.0,
        repad_length_in=125.0,
        arch_center_in=24.0,
        repad_corner_x_in=11.0,
        repad_corner_y_in=20.5,
        repad_corner_r_in=51.5,
        telltale=(44.5, 36.0),
        flange_bottom_in=-5.0,
        bolt_holes=_mirror(_HOLES_125),
    ),
    "10'-10\"": Size(
        label="10'-10\"",
        insert_length_in=130.0,
        repad_length_in=106.0,
        arch_center_in=12.0,
        repad_corner_x_in=12.0,
        repad_corner_y_in=13.0,
        repad_corner_r_in=41.0,
        telltale=(36.0, 21.0),
        flange_bottom_in=-4.75,
        bolt_holes=_mirror(_HOLES_1010),
    ),
}


def normalize_size(value: object) -> str:
    text = str(value).strip().replace("’", "'").replace("”", '"').replace(" ", "")
    found = {
        "12'-5\"": "12'-5\"", "12-5": "12'-5\"", "125": "12'-5\"", "48x48": "12'-5\"",
        "10'-10\"": "10'-10\"", "10-10": "10'-10\"", "1010": "10'-10\"", "48x36": "10'-10\"",
    }.get(text)
    if found is None:
        raise ValueError(f"FTCO size {value!s} must be 12'-5\" (48 x 48) or 10'-10\" (48 x 36).")
    return found


def normalize_anchor(value: object) -> str:
    text = str(value).strip().lower() or "none"
    if text not in ANCHORS:
        raise ValueError(f"Anchor {value!s} must be None, Left, Right or Short.")
    return text


@dataclass(frozen=True)
class Cleanout:
    """One FTCO. Thicknesses default to the FTCO Engine's; every one can be typed over.

    ``orientation_deg`` is measured like a nozzle's rotation: 0 points toward +Z and a
    positive angle swings toward -X, clockwise looking down on the tank.
    """

    mark: str
    size: str = "12'-5\""
    orientation_deg: float = 0.0
    anchor: str = "none"
    insert_thk_in: float = 1.0
    repad_thk_in: float = 1.0
    neck_wall_in: float = 0.5
    baseplate_thk_in: float = 0.375
    flange_thk_in: float = 1.25
    gasket_thk_in: float = 0.125
    cover_thk_in: float = 1.0
    gasket_material: str = ""
    annular_width_in: float = 0.0  # bottom reinforcing plate, shell outside + chime inward
    chime_in: float = 2.5  # bottom plate past the shell outside
    annular_thk_in: float = 0.0  # annular plate the bottom plate's ends bevel down to; 0 is none

    def __post_init__(self) -> None:
        mark = " ".join(str(self.mark).split())
        if not mark:
            raise ValueError("An FTCO needs a mark.")
        object.__setattr__(self, "mark", mark)
        object.__setattr__(self, "size", normalize_size(self.size))
        object.__setattr__(self, "anchor", normalize_anchor(self.anchor))
        object.__setattr__(self, "gasket_material", " ".join(str(self.gasket_material).split()))
        for name in ("insert_thk_in", "repad_thk_in", "neck_wall_in", "baseplate_thk_in",
                     "flange_thk_in", "gasket_thk_in", "cover_thk_in"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{mark}: {name.removesuffix('_in').replace('_', ' ')} must be over 0.")
        if self.annular_width_in <= self.chime_in:
            raise ValueError(f"{mark}: the bottom plate width must reach inside the shell past the chime.")
        if self.chime_in < 0.0 or self.annular_thk_in < 0.0:
            raise ValueError(f"{mark}: chime and annular thickness cannot be negative.")
        if self.annular_thk_in > self.baseplate_thk_in:
            raise ValueError(f"{mark}: the annular plate is thicker than the bottom reinforcing plate.")

    @property
    def dims(self) -> Size:
        return SIZES[self.size]

    @property
    def neck_od_half_in(self) -> float:
        return OPENING_WIDTH_IN / 2.0 + self.neck_wall_in


def developed_center_in(orientation_deg: float, circumference_in: float) -> float:
    """Where an FTCO at ``orientation_deg`` sits along course 1, from the shell's seam origin.

    The shell is developed from +X toward +Z (``swauto.tank.plates``); orientation 0 is +Z,
    a quarter turn on.
    """
    return ((orientation_deg + 90.0) / 360.0 * circumference_in) % circumference_in


def azimuth_rad(orientation_deg: float) -> float:
    """The shell azimuth (0 at +X, toward +Z) of an FTCO's centerline."""
    return math.radians(orientation_deg + 90.0) % (2.0 * math.pi)
