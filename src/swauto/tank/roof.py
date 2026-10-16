"""Cone roof section, matching the GA cross-section.

The roof is one cone, always cone-up. With no compression ring it bears on
the inside face at the top of the shell. A flat bar or an angle sits outside
the top course, and the cone then bears on top of that ring. The landing
inset is measured outward from the shell outside face. Slope is inches of
rise per foot of run. Thickness is a parallel offset outside the bearing line.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.tank.profile import course_radii_m
from swauto.tank.spec import TankSpec

_INCH = 0.0254

RING_NONE = "none"
RING_BAR = "bar"
RING_ANGLE = "angle"
_FLAT_GAP_IN = 24.0


@dataclass(frozen=True)
class RoofSpec:
    """Cone roof inputs. Lengths are inches. Slope is inches per foot."""

    inside_radius_in: float = 300.0
    outside_radius_in: float = 301.0
    shell_height_in: float = 384.0
    slope_in_per_ft: float = 0.75
    thickness_in: float = 0.25
    ring: str = RING_NONE
    ring_top_offset_in: float = 0.0
    landing_inset_in: float = 0.0
    bar_width_in: float = 3.0
    bar_height_in: float = 0.5
    angle_horizontal_in: float = 3.0
    angle_vertical_in: float = 3.0
    angle_thickness_in: float = 0.375
    ignore_pie: bool = True
    plate_width_in: float = 96.0
    plate_length_in: float = 240.0
    plate_lap_in: float = 2.0

    def validate(self) -> None:
        if self.inside_radius_in <= 0:
            raise ValueError("Inside radius must be greater than zero.")
        if self.outside_radius_in < self.inside_radius_in:
            raise ValueError("Outside radius must be at least the inside radius.")
        if self.shell_height_in < 0:
            raise ValueError("Shell height cannot be negative.")
        if self.slope_in_per_ft < 0:
            raise ValueError("Roof slope cannot be negative.")
        if self.thickness_in <= 0:
            raise ValueError("Roof thickness must be greater than zero.")
        if self.ring not in (RING_NONE, RING_BAR, RING_ANGLE):
            raise ValueError("Compression ring must be none, flat bar, or angle.")
        if self.landing_inset_in < 0:
            raise ValueError("Roof landing inset cannot be negative.")
        if self.ring == RING_ANGLE and self.ring_active():
            if self.angle_thickness_in >= self.angle_horizontal_in or self.angle_thickness_in >= self.angle_vertical_in:
                raise ValueError("Angle thickness must be smaller than both arms.")
        if self.ring_active() and self.landing_radius_in() <= 0:
            raise ValueError("Roof landing must sit outside the tank center.")
        if self.plate_width_in <= 0 or self.plate_length_in <= 0:
            raise ValueError("Plate width and plate length must be greater than zero.")
        if self.plate_lap_in < 0:
            raise ValueError("Plate lap cannot be negative.")
        if self.plate_lap_in >= self.plate_width_in or self.plate_lap_in >= self.plate_length_in:
            raise ValueError("Plate lap must be smaller than the plate width and the plate length.")

    def ring_active(self) -> bool:
        if self.ring == RING_BAR:
            return self.bar_width_in > 0 and self.bar_height_in > 0
        if self.ring == RING_ANGLE:
            return (
                self.angle_horizontal_in > 0
                and self.angle_vertical_in > 0
                and self.angle_thickness_in > 0
            )
        return False

    def landing_radius_in(self) -> float:
        """Where the cone underside meets the shell or the ring."""
        if self.ring_active():
            return self.outside_radius_in + self.landing_inset_in
        return self.inside_radius_in

    def landing_height_in(self) -> float:
        if self.ring_active():
            return self.shell_height_in + self.ring_top_offset_in
        return self.shell_height_in

    def rise_in(self) -> float:
        """Vertical rise from the landing line to the peak."""
        return (self.landing_radius_in() / 12.0) * self.slope_in_per_ft

    def peak_height_in(self) -> float:
        return self.landing_height_in() + self.rise_in()


def roof_from_tank(tank: TankSpec, slope_in_per_ft: float, thickness_in: float) -> RoofSpec:
    """Inside and outside radii are the top course. Height is the shell top."""
    tank.validate()
    courses = tank.active_courses()
    outer_m, inner_m = course_radii_m(tank, courses[-1])
    return RoofSpec(
        inside_radius_in=inner_m / _INCH,
        outside_radius_in=outer_m / _INCH,
        shell_height_in=tank.shell_height_in(),
        slope_in_per_ft=slope_in_per_ft,
        thickness_in=thickness_in,
    )


def cone_profile_in(spec: RoofSpec) -> tuple[tuple[float, float], ...]:
    """Closed right-half section, (radius, height) in inches.

    Order: underside at the landing, underside at the centerline, outside
    at the centerline, outside at the eave.
    """
    spec.validate()
    radius = spec.landing_radius_in()
    base = spec.landing_height_in()
    rise = spec.rise_in()
    length = math.hypot(radius, rise)
    if length <= 1e-9:
        raise ValueError("Roof run is too small to build a cone.")
    outward_r = (rise / length) * spec.thickness_in
    outward_y = (radius / length) * spec.thickness_in
    peak = base + rise
    return (
        (radius, base),
        (0.0, peak),
        (0.0, peak + outward_y),
        (radius + outward_r, base + outward_y),
    )


@dataclass(frozen=True)
class FlatPattern:
    """Unrolled underside of the cone, laid flat beside the tank.

    The plate radius is the slant length from peak to landing, so a sloped
    roof flattens larger than its plan diameter. The metal is a sector of
    360 * landing / slant degrees. A flat roof is a full circle of the
    landing diameter. Angle on the pattern, measured from the sector
    centerline, opens back to a plan angle by slant / landing.
    """

    slant_in: float
    sector_rad: float
    apex_x_in: float
    apex_z_in: float

    @property
    def diameter_in(self) -> float:
        return 2.0 * self.slant_in

    @property
    def sector_deg(self) -> float:
        return math.degrees(self.sector_rad)


def flat_pattern(spec: RoofSpec) -> FlatPattern:
    """Developed blank for the cone underside."""
    spec.validate()
    landing = spec.landing_radius_in()
    slant = math.hypot(landing, spec.rise_in())
    if slant <= 1e-9:
        raise ValueError("Roof run is too small to flatten.")
    outer = max(point[0] for point in cone_profile_in(spec))
    ring = ring_profile_in(spec)
    if ring:
        outer = max(outer, max(point[0] for point in ring))
    return FlatPattern(
        slant_in=slant,
        sector_rad=(2.0 * math.pi * landing / slant),
        apex_x_in=outer + _FLAT_GAP_IN + slant,
        apex_z_in=0.0,
    )


def pattern_sweep_rad(spec: RoofSpec) -> float:
    """Angle of metal on the flat pattern.

    Ignoring the pie cut uses a full circle. The extra arc becomes seam lap
    when the plates are formed onto the cone.
    """
    sector = flat_pattern(spec).sector_rad
    if spec.ignore_pie or sector >= 2.0 * math.pi - 1e-8:
        return 2.0 * math.pi
    return sector


def flat_outline_in(spec: RoofSpec, step_deg: float = 1.0) -> tuple[tuple[float, float], ...]:
    """Pattern outline in inches, relative to the apex. +X is the centerline."""
    pattern = flat_pattern(spec)
    step = max(float(step_deg), 0.25)
    if pattern_sweep_rad(spec) >= 2.0 * math.pi - 1e-8:
        count = max(8, math.ceil(360.0 / step))
        return tuple(
            (
                pattern.slant_in * math.cos(2.0 * math.pi * index / count),
                pattern.slant_in * math.sin(2.0 * math.pi * index / count),
            )
            for index in range(count)
        )
    count = max(2, math.ceil(math.degrees(pattern.sector_rad) / step))
    points = [(0.0, 0.0)]
    for index in range(count + 1):
        angle = -pattern.sector_rad / 2.0 + pattern.sector_rad * index / count
        points.append((pattern.slant_in * math.cos(angle), pattern.slant_in * math.sin(angle)))
    return tuple(points)


def flat_radius_for_plan(spec: RoofSpec, plan_radius_in: float) -> float:
    """Developed radius for a point this far from the peak in plan."""
    landing = spec.landing_radius_in()
    return plan_radius_in * flat_pattern(spec).slant_in / landing


def plan_radius_for_flat(spec: RoofSpec, developed_radius_in: float) -> float:
    """Plan radius, from the peak, for a point at this radius on the flat pattern."""
    return developed_radius_in * spec.landing_radius_in() / flat_pattern(spec).slant_in


def plan_angle_for_flat(spec: RoofSpec, flat_angle_rad: float) -> float:
    """Plan angle around the tank for an angle measured on the flat pattern.

    With the pie cut kept, the sector opens back up to a full circle.
    With the pie cut ignored, the flat angle is the plan angle, and the
    extra metal is taken up in the laps.
    """
    if spec.ignore_pie:
        return flat_angle_rad
    sector = flat_pattern(spec).sector_rad
    return flat_angle_rad * (2.0 * math.pi) / sector


_MAX_ROOF_PLATES = 64
_PLATE_ARC_STEP_DEG = 4.0
PLATE_COLORS = (
    (0.62, 0.70, 0.62),
    (0.76, 0.64, 0.48),
    (0.55, 0.66, 0.74),
    (0.72, 0.58, 0.62),
)


@dataclass(frozen=True)
class RoofPlate:
    """One developed roof plate, inches from the pattern apex. +X is the centerline."""

    course: int
    index: int
    polygon_in: tuple[tuple[float, float], ...]

    @property
    def feature_name(self) -> str:
        return f"EliteRoofP{self.course}{self.index:02d}"

    @property
    def sketch_name(self) -> str:
        return f"{self.feature_name}Sk"

    def color(self) -> tuple[float, float, float]:
        return PLATE_COLORS[(self.course - 1) % len(PLATE_COLORS)]


@dataclass(frozen=True)
class ConePoint:
    """A point on the outside of the cone, inches. Y is up."""

    x_in: float
    y_in: float
    z_in: float


def layout_roof_plates(spec: RoofSpec) -> list[RoofPlate]:
    """Radial courses on the flat pattern.

    Each course runs along the slant by the plate length, and is split around
    the pattern so the wide edge stays within the plate width. Neighbors
    overlap by the lap. Ignoring the pie cut lays the plates on a full circle.
    """
    spec.validate()
    pattern = flat_pattern(spec)
    sweep = pattern_sweep_rad(spec)
    closed = sweep >= 2.0 * math.pi - 1e-8
    plates: list[RoofPlate] = []
    for course, (inner, outer) in enumerate(_net_courses(pattern.slant_in, spec.plate_length_in), start=1):
        draw_outer = outer if course == 1 else min(pattern.slant_in, outer + spec.plate_lap_in / 2.0)
        draw_inner = 0.0 if inner <= 1e-9 else max(0.0, inner - spec.plate_lap_in / 2.0)
        count = max(1, math.ceil((sweep * draw_outer) / spec.plate_width_in - 1e-9))
        pitch = sweep / count
        lap_angle = (spec.plate_lap_in / draw_outer) if count > 1 and draw_outer > 1e-9 else 0.0
        start = -sweep / 2.0
        for index in range(count):
            left = start + index * pitch
            right = left + pitch
            if count > 1:
                if closed or index > 0:
                    left -= lap_angle / 2.0
                if closed or index < count - 1:
                    right += lap_angle / 2.0
            plates.append(
                RoofPlate(
                    course=course,
                    index=index + 1,
                    polygon_in=_annulus(draw_inner, draw_outer, left, right),
                )
            )
            if len(plates) > _MAX_ROOF_PLATES:
                raise ValueError(
                    f"That plate size makes more than {_MAX_ROOF_PLATES} plates. Use a wider or longer plate."
                )
    return plates


def course_break_plan_radii(spec: RoofSpec) -> tuple[float, ...]:
    """Plan radii where one plate course meets the next, not counting the eave."""
    spec.validate()
    slant = flat_pattern(spec).slant_in
    return tuple(
        plan_radius_for_flat(spec, inner)
        for inner, _outer in _net_courses(slant, spec.plate_length_in)
        if inner > 1e-6
    )


def cone_point_in(spec: RoofSpec, local_x_in: float, local_z_in: float) -> ConePoint:
    """Project a flat-pattern point onto the outside of the cone."""
    spec.validate()
    landing = spec.landing_radius_in()
    slant = flat_pattern(spec).slant_in
    developed = math.hypot(local_x_in, local_z_in)
    flat_angle = math.atan2(local_z_in, local_x_in)
    plan_radius = plan_radius_for_flat(spec, developed)
    plan_angle = plan_angle_for_flat(spec, flat_angle)
    rise = spec.rise_in()
    if landing <= 1e-9:
        height = spec.peak_height_in()
        radial = 0.0
    else:
        height = spec.landing_height_in() + rise * (1.0 - plan_radius / landing)
        radial = plan_radius
    if slant > 1e-9:
        height += (landing / slant) * spec.thickness_in
        radial += (rise / slant) * spec.thickness_in
    return ConePoint(
        x_in=radial * math.cos(plan_angle),
        y_in=height,
        z_in=radial * math.sin(plan_angle),
    )


def _net_courses(slant_in: float, plate_length_in: float) -> list[tuple[float, float]]:
    """Bands from the eave in, as (inner radius, outer radius) with no lap yet."""
    bands: list[tuple[float, float]] = []
    outer = slant_in
    while outer > 1e-6 and len(bands) < 12:
        inner = max(0.0, outer - plate_length_in)
        bands.append((inner, outer))
        if inner <= 0.0:
            break
        outer = inner
    return bands


def _annulus(inner: float, outer: float, angle0: float, angle1: float) -> tuple[tuple[float, float], ...]:
    span = max(angle1 - angle0, 1e-9)
    count = max(1, math.ceil(math.degrees(span) / _PLATE_ARC_STEP_DEG))
    outer_pts = tuple(_polar(outer, angle0 + span * index / count) for index in range(count + 1))
    if inner <= 1e-6:
        return ((0.0, 0.0),) + outer_pts
    inner_pts = tuple(_polar(inner, angle1 - span * index / count) for index in range(count + 1))
    return outer_pts + inner_pts


def _polar(radius: float, angle: float) -> tuple[float, float]:
    return (radius * math.cos(angle), radius * math.sin(angle))


def ring_profile_in(spec: RoofSpec) -> tuple[tuple[float, float], ...]:
    """Right-half compression ring, or an empty tuple when the ring is off."""
    spec.validate()
    if not spec.ring_active():
        return ()
    outside = spec.outside_radius_in
    top = spec.shell_height_in + spec.ring_top_offset_in
    if spec.ring == RING_BAR:
        bottom = top - spec.bar_height_in
        outer = outside + spec.bar_width_in
        return ((outside, bottom), (outer, bottom), (outer, top), (outside, top))
    thickness = spec.angle_thickness_in
    return (
        (outside, top),
        (outside + spec.angle_horizontal_in, top),
        (outside + spec.angle_horizontal_in, top - thickness),
        (outside + thickness, top - thickness),
        (outside + thickness, top - spec.angle_vertical_in),
        (outside, top - spec.angle_vertical_in),
    )
