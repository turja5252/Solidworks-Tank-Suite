"""Where a roof nozzle sits on the cone roof from the Roof tab.

The tank frame is the shell's: Y up from the shell bottom, the tank axis at X = Z = 0. The roof is the
cone the Roof tab models (``tank.roof.cone_profile_in``): its underside runs from the bearing line at
the landing up toward the center at the slope, and its outside is that line offset square to it by the
plate.

Along a roof nozzle, z is vertical, 0 on the roof's outside at the centerline and + up. That is the
frame ``nozzle.shape`` turns its loops in, so a RoofPlacement stands in for a shell Placement there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.nozzle.flange import Flange, flange
from swauto.nozzle.gasket import Gasket, gasket
from swauto.nozzle.pipe import Pipe, pipe
from swauto.nozzle.repad import Repad, resolve_repad
from swauto.nozzle.roof_spec import DIRECT, RoofNozzle
from swauto.nozzle.shape import inside_stations, stations
from swauto.tank.roof import RING_ANGLE, RoofSpec, cone_profile_in

AUTO_CLEAR_IN = 0.25  # the lisp's AUTO ISP: 1/4 in under the roof, square to it, at the low side of the pipe
_CIRCLE_STEPS = 48


@dataclass(frozen=True)
class RoofPlacement:
    """A roof nozzle ready to model. Elevations (Y) and plan points (X, Z) are inches in the tank frame."""

    nozzle: RoofNozzle
    roof: RoofSpec
    pipe: Pipe
    flange: Flange
    repad: Repad | None
    gasket: Gasket | None
    inside_flange: Flange | None
    plan_in: tuple[float, float]  # (X, Z) of the centerline
    radius_in: float  # plan radius of the centerline, after the offset
    angle_deg: float  # plan angle of the centerline, after the offset, measured as ``degree`` is
    bearing_in: float  # the roof bearing line: the shell top, or the compression ring's top
    surface_in: float  # the roof's outside at the centerline: z = 0
    underside_in: float  # the roof's underside at the centerline
    face_in: float  # the flange's raised face
    end_in: float  # the inside end: the neck's end, or an inside flange's raised face
    outside_projection_in: float  # z of the raised face
    inside_projection_in: float  # how far under z = 0 the inside end is, the plate included
    wall_in: float  # how far under z = 0 an inside flange's hub has to stay: the underside at its low edge
    auto_isp: bool

    @property
    def height_in(self) -> float:
        """B in the lisp's location table: the flange face above the bearing line."""
        return self.face_in - self.bearing_in

    @property
    def isp_in(self) -> float:
        """The ISP as the lisp's schedule lists it: the typed one, or 1/4 in for AUTO."""
        return AUTO_CLEAR_IN if self.auto_isp else float(self.nozzle.isp_in)

    @property
    def arc_length_in(self) -> float:
        """The location table's arc length: round the nozzle's own plan circle from 0 deg."""
        return self.radius_in * math.radians(self.angle_deg)

    @property
    def location_c_in(self) -> float:
        """C in the location table: in the radial section, from the reference point on the bearing line (the
        ring's outer edge, or the shell inside with no ring) to the roof's outside at the centerline."""
        roof = self.roof
        if roof.ring_active():
            reach = roof.angle_horizontal_in if roof.ring == RING_ANGLE else roof.bar_width_in
            reference = roof.outside_radius_in + reach
        else:
            reference = roof.inside_radius_in
        return math.hypot(reference - self.radius_in, self.surface_in - self.bearing_in)

    @property
    def outward(self) -> tuple[float, float]:
        """Plan (X, Z) unit vector out along the radial line through the centerline. The bolt holes
        straddle it. A nozzle on the tank axis uses its typed degree."""
        x, z = self.plan_in
        if math.hypot(x, z) < 1e-6:
            phi = math.radians(self.nozzle.degree)
            return (-math.sin(phi), math.cos(phi))
        return (x / math.hypot(x, z), z / math.hypot(x, z))


def slope(roof: RoofSpec) -> float:
    """Rise per unit of run."""
    return roof.slope_in_per_ft / 12.0


def underside_y(roof: RoofSpec, radius_in: float) -> float:
    """Elevation of the cone's underside at a plan radius."""
    return roof.landing_height_in() + (roof.landing_radius_in() - radius_in) * slope(roof)


def outside_y(roof: RoofSpec, radius_in: float) -> float:
    """Elevation of the cone's outside at a plan radius, on the line the Roof tab revolves."""
    profile = cone_profile_in(roof)
    (r0, y0), (r1, y1) = profile[2], profile[3]
    return y0 + (y1 - y0) * (radius_in - r0) / (r1 - r0)


def plan_point(degree: float, radial_in: float, offset_in: float) -> tuple[float, float]:
    """(X, Z) of the centerline: ``radial_in`` out along ``degree``, then ``offset_in`` square to it,
    to the clockwise side (the shell nozzle's outward and clockwise directions)."""
    phi = math.radians(degree)
    return (
        -radial_in * math.sin(phi) - offset_in * math.cos(phi),
        radial_in * math.cos(phi) - offset_in * math.sin(phi),
    )


def place_on_roof(nozzle: RoofNozzle, roof: RoofSpec) -> RoofPlacement:
    """Put ``nozzle`` on the cone roof described by the Roof tab."""
    roof.validate()
    mark = nozzle.mark
    landing = roof.landing_radius_in()
    neck = pipe(nozzle.nps, nozzle.schedule)
    fitting = flange(nozzle.nps, nozzle.rating, nozzle.kind)
    x, z = plan_point(nozzle.degree, nozzle.radial_in, nozzle.offset_in)
    radius = math.hypot(x, z)
    angle = math.degrees(math.atan2(-x, z)) % 360.0 if radius > 1e-9 else nozzle.degree % 360.0
    half = neck.outside_diameter_in / 2.0
    if radius + half >= landing:
        raise ValueError(
            f"{mark}: the pipe reaches {radius + half:.3f} in from the tank center, past the roof landing at "
            f"{landing:.3f} in. Bring the radial in."
        )
    m = slope(roof)
    k = math.hypot(1.0, m)
    surface = outside_y(roof, radius)
    underside = underside_y(roof, radius)
    if nozzle.isp_in is None:
        end = underside_y(roof, radius + half) - AUTO_CLEAR_IN / k
    else:
        end = underside - nozzle.isp_in
        short = m * half
        if nozzle.inside_flange == "none" and nozzle.isp_in <= short + 1e-9:
            raise ValueError(
                f"{mark}: an ISP of {nozzle.isp_in:g} in leaves the low side of the pipe in the roof plate. "
                f"It needs more than {short:.3f} in, or AUTO."
            )
    bearing = roof.landing_height_in()
    face = surface + nozzle.projection_in if nozzle.projection == DIRECT else bearing + nozzle.projection_in
    if face <= surface + 1e-9:
        raise ValueError(
            f"{mark}: a height of {nozzle.projection_in:g} in puts the flange face at or under the roof, which is "
            f"{surface - bearing:.3f} in over the bearing line there."
        )
    inside = None if nozzle.inside_flange == "none" else flange(nozzle.nps, nozzle.rating, nozzle.inside_flange)
    hub_reach = inside.hub_diameter_in / 2.0 if inside is not None else half
    pad = resolve_repad(
        nozzle.nps,
        nozzle.repad_mode,
        course_thickness_in=roof.thickness_in,
        outer_in=nozzle.repad_outer_in,
        inner_in=nozzle.repad_inner_in,
        thickness_in=nozzle.repad_thickness_in,
        style=nozzle.repad_style,
    )
    ring = (
        gasket(nozzle.nps, nozzle.rating, nozzle.gasket_material, nozzle.gasket_thickness_in)
        if nozzle.gasket
        else None
    )
    placed = RoofPlacement(
        nozzle=nozzle,
        roof=roof,
        pipe=neck,
        flange=fitting,
        repad=pad,
        gasket=ring,
        inside_flange=inside,
        plan_in=(x, z),
        radius_in=radius,
        angle_deg=angle,
        bearing_in=bearing,
        surface_in=surface,
        underside_in=underside,
        face_in=face,
        end_in=end,
        outside_projection_in=face - surface,
        inside_projection_in=surface - end,
        wall_in=surface - underside_y(roof, radius + hub_reach),
        auto_isp=nozzle.isp_in is None,
    )
    if pad is not None:
        pad_reach(placed)  # the pad has to be on the roof
    _check_clear(placed)
    return placed


def pad_reach(placed: RoofPlacement) -> tuple[float, float]:
    """Plan radii the repad spans, inner and outer. A tombstone runs out to the landing."""
    pad = placed.repad
    assert pad is not None
    landing = placed.roof.landing_radius_in()
    half = pad.outer_diameter_in / 2.0
    mark = placed.nozzle.mark
    if pad.style == "tombstone":
        if placed.radius_in**2 + half**2 >= landing**2:
            raise ValueError(f"{mark}: the tombstone pad is too wide to run out to the roof landing from here.")
        return max(0.0, placed.radius_in - half), landing
    if placed.radius_in + half > landing:
        raise ValueError(
            f"{mark}: the {pad.outer_diameter_in:g} in pad runs past the roof landing. Bring the nozzle in or use "
            "a tombstone pad."
        )
    return max(0.0, placed.radius_in - half), placed.radius_in + half


def pad_thickness_vertical(placed: RoofPlacement) -> float:
    """The repad's thickness, square to the roof, as it stands vertically on the slope."""
    if placed.repad is None:
        return 0.0
    return placed.repad.thickness_in * math.hypot(1.0, slope(placed.roof))


def _check_clear(placed: RoofPlacement) -> None:
    """The flange stays above the roof and its pad; an inside flange stays below the roof."""
    mark = placed.nozzle.mark
    fitting = placed.flange
    hub_r = fitting.hub_diameter_in / 2.0
    roof_top = outside_y(placed.roof, max(0.0, placed.radius_in - hub_r)) - placed.surface_in
    under_hub = roof_top + pad_thickness_vertical(placed)
    hub_z = placed.outside_projection_in - fitting.face_to_hub_end_in
    if hub_z < under_hub - 1e-9:
        least = placed.outside_projection_in + under_hub - hub_z
        what = "its pad" if placed.repad is not None else "the roof"
        raise ValueError(
            f"{mark}: the flange's hub would go into {what}. The OSP needs to be at least {least:.3f} in "
            f"(it is {placed.outside_projection_in:.3f} in)."
        )
    inside = placed.inside_flange
    if inside is not None:
        hub_end = -placed.inside_projection_in + inside.face_to_hub_end_in
        if hub_end > -placed.wall_in + 1e-9:
            least = float(placed.nozzle.isp_in) + hub_end + placed.wall_in
            raise ValueError(
                f"{mark}: the inside flange's hub would go into the roof. The ISP needs to be at least "
                f"{least:.3f} in."
            )
        inside_stations(placed)
    stations(placed)


def pad_outline(placed: RoofPlacement) -> list[tuple[float, float]]:
    """The repad in plan, (X, Z) points around it, as the lisp draws it.

    A circle on the centerline, or the roof's tombstone: a half circle with its round end toward the tank
    center and straight sides run out, parallel to the radial line, to the landing circle.
    """
    pad = placed.repad
    if pad is None:
        return []
    px, pz = placed.plan_in
    half = pad.outer_diameter_in / 2.0
    if pad.style != "tombstone":
        return [
            (px + half * math.cos(a), pz + half * math.sin(a))
            for a in (2.0 * math.pi * i / _CIRCLE_STEPS for i in range(_CIRCLE_STEPS))
        ]
    feet, _tangents = tombstone_corners(placed)
    ux, uz = placed.outward
    nx, nz = -uz, ux
    # From the +n tangent point round the inboard end to the -n one, out that side to the landing, along
    # the landing circle the short way, and back in the +n side.
    arc = [
        (px + half * (math.cos(a) * nx - math.sin(a) * ux), pz + half * (math.cos(a) * nz - math.sin(a) * uz))
        for a in (math.pi * i / (_CIRCLE_STEPS // 2) for i in range(_CIRCLE_STEPS // 2 + 1))
    ]
    landing = placed.roof.landing_radius_in()
    a0 = math.atan2(feet[1][1], feet[1][0])
    a1 = math.atan2(feet[0][1], feet[0][0])
    sweep = math.remainder(a1 - a0, 2.0 * math.pi)
    rim = [
        (landing * math.cos(a0 + sweep * i / 12), landing * math.sin(a0 + sweep * i / 12)) for i in range(1, 12)
    ]
    return arc + [feet[1]] + rim + [feet[0]]


def tombstone_corners(placed: RoofPlacement):
    """The tombstone's feet on the landing circle and the tangent points the sides leave the half circle
    at: ((foot +n, foot -n), (tangent +n, tangent -n)), with n square to the radial line."""
    pad = placed.repad
    assert pad is not None
    half = pad.outer_diameter_in / 2.0
    px, pz = placed.plan_in
    ux, uz = placed.outward
    nx, nz = -uz, ux
    landing = placed.roof.landing_radius_in()
    along = math.sqrt(landing * landing - half * half) - placed.radius_in
    tangents = ((px + half * nx, pz + half * nz), (px - half * nx, pz - half * nz))
    feet = tuple((tx + along * ux, tz + along * uz) for tx, tz in tangents)
    return feet, tangents
