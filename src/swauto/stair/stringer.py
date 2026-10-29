"""Outer stringer size and burn holes, following the spiral stair GUI.

The plate is 3/8 in thick. Stations are measured along the helical outside
face the way the lisp stretch-out does. The SolidWorks part is the formed
helix; these lengths place that helix and the holes in it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

THICKNESS_IN = 0.375
TREAD_PLATE_IN = 36.0  # the full tread, and every platform's width whatever the treads are
CLEAR_IN = TREAD_PLATE_IN + 0.125
TREAD_WIDTHS_IN = (36.0, 30.0)  # the lisp launcher's choices
TREAD_DEPTH_IN = 10.9375
TREAD_MARK_IN = 2.5
BOLT_DIA_IN = 0.4375
BOLT_SPACE_IN = 7.0
BOLT_FROM_FRONT_IN = 2.8125
BOLT_UP_IN = 0.75
TOP_HOLE_DIA_IN = 0.8125
TOP_HOLE_DROP_IN = 2.25
TOP_HOLE_BACK_IN = (2.1875, 4.6875)
END_CUT_IN = 0.125
MAX_TREADS = 200  # a 100 ft shell at 7.5 in rises is 160 treads


@dataclass(frozen=True)
class StringerMock:
    """Lengths are inches. ``outside_face`` develops the outer fiber. ``tread_in`` is the tread
    plate across the stair; the stringers stand 1/16 in clear of it each side."""

    shell_od_in: float = 120.0
    gap_in: float = 8.0
    treads: int = 8
    rise_in: float = 7.5
    run_in: float = 10.5
    plate_width_in: float = 9.0
    outside_face: bool = True
    tread_in: float = TREAD_PLATE_IN

    @property
    def clear_in(self) -> float:
        """Between the stringers' walk faces."""
        return self.tread_in + CLEAR_IN - TREAD_PLATE_IN

    def validate(self) -> None:
        if self.shell_od_in <= 0:
            raise ValueError("Shell outside radius must be greater than zero.")
        if self.gap_in < 0:
            raise ValueError("Gap cannot be negative.")
        if self.treads < 2 or self.treads > MAX_TREADS:
            raise ValueError(f"Use 2 to {MAX_TREADS} treads.")
        if self.rise_in <= 0 or self.run_in <= 0:
            raise ValueError("Rise and run must be greater than zero.")
        if self.plate_width_in <= 1:
            raise ValueError("Plate width must be greater than 1 in.")
        if not 12.0 <= self.tread_in <= TREAD_PLATE_IN:
            raise ValueError(f"Treads must be 12 to {TREAD_PLATE_IN:g} in across; the platforms are {TREAD_PLATE_IN:g} in.")


@dataclass(frozen=True)
class TreadHoles:
    index: int
    along_in: float
    hole_along_in: tuple[float, float]
    hole_offset_in: float


@dataclass(frozen=True)
class StringerLayout:
    outside_radius_in: float
    mid_radius_in: float
    inner_face_in: float
    shell_od_in: float
    sweep_rad: float
    pitch_rad: float
    total_rise_in: float
    outside_true_in: float
    mid_true_in: float
    developed_true_in: float
    plate_width_in: float
    x0_in: float
    x1_in: float
    treads: tuple[TreadHoles, ...]
    top_holes_in: tuple[tuple[float, float], ...]
    tread_in: float

    @property
    def clear_in(self) -> float:
        """Between the stringers' walk faces."""
        return self.tread_in + CLEAR_IN - TREAD_PLATE_IN

    @property
    def pitch_deg(self) -> float:
        return math.degrees(self.pitch_rad)

    @property
    def sweep_deg(self) -> float:
        return math.degrees(self.sweep_rad)


def layout_stringer(spec: StringerMock) -> StringerLayout:
    """Plan radii and the slanted flat plate for one outer stringer."""
    spec.validate()
    inner_face = spec.shell_od_in + spec.gap_in + THICKNESS_IN
    outer_near = inner_face + spec.clear_in
    outside_radius = outer_near + THICKNESS_IN
    mid_radius = outer_near + THICKNESS_IN / 2.0
    walk_center = inner_face + spec.clear_in / 2.0
    sweep = spec.treads * (spec.run_in / walk_center)
    total_rise = spec.treads * spec.rise_in
    outside_true = math.hypot(outside_radius * sweep, total_rise)
    mid_true = math.hypot(mid_radius * sweep, total_rise)
    developed = outside_true if spec.outside_face else mid_true
    develop_radius = outside_radius if spec.outside_face else mid_radius
    half_depth = TREAD_DEPTH_IN / 2.0
    hole_offset = -TREAD_MARK_IN / 2.0 + BOLT_UP_IN
    treads: list[TreadHoles] = []
    for index in range(1, spec.treads + 1):
        along = (index / spec.treads) * developed
        front = along + half_depth
        first = front - BOLT_FROM_FRONT_IN
        treads.append(TreadHoles(index, along, (first, first - BOLT_SPACE_IN), hole_offset))
    x0 = treads[0].along_in - half_depth - END_CUT_IN
    x1 = treads[-1].along_in + half_depth + END_CUT_IN
    top_holes = tuple((x1 - back, hole_offset - TOP_HOLE_DROP_IN) for back in TOP_HOLE_BACK_IN)
    return StringerLayout(
        outside_radius_in=outside_radius,
        mid_radius_in=mid_radius,
        inner_face_in=inner_face,
        shell_od_in=spec.shell_od_in,
        sweep_rad=sweep,
        pitch_rad=math.atan2(total_rise, develop_radius * sweep),
        total_rise_in=total_rise,
        outside_true_in=outside_true,
        mid_true_in=mid_true,
        developed_true_in=developed,
        plate_width_in=spec.plate_width_in,
        x0_in=x0,
        x1_in=x1,
        treads=tuple(treads),
        top_holes_in=top_holes,
        tread_in=spec.tread_in,
    )


def helix_end_along_in(layout: StringerLayout) -> float:
    """How far the formed helix must run so the top holes stay on the plate."""
    end = layout.x1_in
    for along, _offset in layout.top_holes_in:
        end = max(end, along)
    return end


def hole_point_in(layout: StringerLayout, along_in: float, offset_in: float) -> tuple[float, float, float]:
    """Point on the plate centerline, inches, Y up.

    The SolidWorks helix starts at +Z and turns toward −X. ``offset_in`` is
    across the plate, perpendicular to that helix.
    """
    theta = along_in / layout.developed_true_in * layout.sweep_rad
    alpha = math.atan2(layout.total_rise_in, layout.mid_radius_in * layout.sweep_rad)
    radius = layout.mid_radius_in
    binormal = (
        -math.sin(alpha) * math.cos(theta),
        -math.cos(alpha),
        -math.sin(alpha) * math.sin(theta),
    )
    return (
        -radius * math.sin(theta) + offset_in * binormal[0],
        along_in / layout.developed_true_in * layout.total_rise_in + offset_in * binormal[1],
        radius * math.cos(theta) + offset_in * binormal[2],
    )
