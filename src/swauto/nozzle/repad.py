"""Reinforcing pad for a shell nozzle, from the AutoCAD repad table.

A blank thickness uses the shell course at the nozzle elevation. The telltale
is a 1/4 in hole. Its center is measured from the left-hand point of the repad
outside diameter, toward the nozzle, by the telltale offset (1 in when blank).
A tombstone pad is that outside diameter as a semicircle above the nozzle,
with the sides run straight down to the tank floor.
"""

from __future__ import annotations

from dataclasses import dataclass

from swauto.nozzle.pipe import normalize_nps

TELLTALE_DIAMETER_IN = 0.25

# Nominal size, outside diameter, inside diameter, telltale offset. Inches.
# 2-1/2 in and anything under 2 in are not in the table.
_DEFAULTS: dict[str, tuple[float, float, float]] = {
    "2": (7.0, 2.5, 1.0),
    "3": (10.5, 3.625, 1.0),
    "4": (12.0, 4.625, 1.0),
    "6": (15.75, 6.75, 1.0),
    "8": (19.0, 8.75, 2.0),
    "10": (23.0, 10.875, 2.0),
    "12": (27.0, 12.875, 2.0),
    "14": (29.5, 14.125, 2.0),
    "16": (33.5, 16.125, 2.0),
    "18": (37.5, 18.125, 2.0),
    "20": (41.5, 20.125, 2.0),
    "22": (45.5, 22.125, 2.0),
    "24": (49.5, 24.125, 2.0),
}


def normalize_repad_mode(value: object) -> str:
    """Return ``none``, ``default``, or ``custom``."""
    text = str(value).strip().lower()
    found = {
        "none": "none",
        "0": "none",
        "default": "default",
        "1": "default",
        "custom": "custom",
        "2": "custom",
    }.get(text)
    if found is None:
        raise ValueError(f"Repad {value!s} must be none, default, or custom.")
    return found


def normalize_repad_style(value: object) -> str:
    """Return ``circular`` or ``tombstone``."""
    text = str(value).strip().lower()
    found = {"circular": "circular", "0": "circular", "tombstone": "tombstone", "1": "tombstone"}.get(text)
    if found is None:
        raise ValueError(f"Repad style {value!s} must be circular or tombstone.")
    return found


def default_repad_size(nps: object) -> tuple[float, float, float] | None:
    """Return (outside diameter, inside diameter, telltale offset), or None when the size has no standard pad."""
    return _DEFAULTS.get(normalize_nps(nps))


@dataclass(frozen=True)
class Repad:
    """One pad on the outside of the shell. Diameters and thickness are inches."""

    outer_diameter_in: float
    inner_diameter_in: float
    thickness_in: float
    style: str
    telltale_offset_in: float

    @property
    def telltale_diameter_in(self) -> float:
        return TELLTALE_DIAMETER_IN

    @property
    def telltale_from_center_in(self) -> float:
        """Distance from the pad center to the telltale center, toward the left edge."""
        return self.outer_diameter_in / 2.0 - self.telltale_offset_in


def resolve_repad(
    nps: object,
    mode: object,
    *,
    course_thickness_in: float,
    outer_in: float = 0.0,
    inner_in: float = 0.0,
    thickness_in: float | None = None,
    style: object = "circular",
    telltale_offset_in: float = 1.0,
) -> Repad | None:
    """The pad to build, or None when the nozzle has no pad.

    A blank thickness uses the shell course. Default sizes come from the AutoCAD table.
    """
    chosen = normalize_repad_mode(mode)
    shape = normalize_repad_style(style)
    if chosen == "none":
        return None
    if chosen == "default":
        standard = default_repad_size(nps)
        if standard is None:
            size = normalize_nps(nps)
            raise ValueError(f"{size} in has no standard repad. Use a custom diameter or no repad.")
        outer_in, inner_in, telltale_offset_in = standard
    if outer_in <= 0.0:
        raise ValueError("Repad outside diameter must be greater than zero.")
    if inner_in < 0.0 or inner_in >= outer_in:
        raise ValueError("Repad inside diameter must be smaller than the outside diameter.")
    if telltale_offset_in < 0.0:
        raise ValueError("Telltale offset cannot be negative.")
    thickness = course_thickness_in if thickness_in is None else thickness_in
    if thickness <= 0.0:
        raise ValueError("Repad thickness must be greater than zero.")
    return Repad(
        outer_diameter_in=outer_in,
        inner_diameter_in=inner_in,
        thickness_in=thickness,
        style=shape,
        telltale_offset_in=telltale_offset_in,
    )


def tombstone_crown_in(elevation_in: float, outer_diameter_in: float) -> float:
    """Height of the top of a tombstone pad. The sides run from the nozzle down to the floor."""
    return elevation_in + outer_diameter_in / 2.0
