"""Where a shell nozzle sits on the tank from Tank Properties.

The shell outside radius is the course the centerline falls in. A centerline
exactly on a seam belongs to the course above that seam. The typed outside
projection runs from that course's outside surface to the far end of the
flange (the raised face); the typed inside projection runs from its inside
surface to the inner end. Both are along the nozzle centerline. ``place``
adds the wall to the inside projection, so a Placement measures both from the
shell outside. Plane match lengthens the outside projection and shortens the
inside one by the same amount, so an offset nozzle's face and inner end land
in the same planes as a radial nozzle with the typed projections.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.nozzle.flange import Flange, flange
from swauto.nozzle.gasket import Gasket, gasket
from swauto.nozzle.pipe import Pipe, pipe
from swauto.nozzle.repad import Repad, resolve_repad
from swauto.nozzle.spec import Nozzle
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import Course, TankSpec

_INCH = 0.0254


@dataclass(frozen=True)
class Placement:
    """A nozzle ready to model. Points are inches in the tank frame: Y up, axis at X = Z = 0."""

    nozzle: Nozzle
    pipe: Pipe
    flange: Flange
    repad: Repad | None
    gasket: Gasket | None
    course_number: int
    course_bottom_in: float
    outside_radius_in: float
    inside_radius_in: float
    shell_in: tuple[float, float, float]
    face_in: tuple[float, float, float]
    hub_end_in: tuple[float, float, float]
    inner_end_in: tuple[float, float, float]
    axis: tuple[float, float, float]
    outside_projection_in: float
    inside_projection_in: float  # from the shell outside, wall included
    chord_in: float
    wall_in: float  # shell wall along the centerline


def course_at(spec: TankSpec, elevation_in: float) -> tuple[int, Course, float]:
    """Return the course number from the bottom, the course, and the elevation of its bottom."""
    if elevation_in < 0.0:
        raise ValueError("Elevation is below the tank floor.")
    courses = spec.active_courses()
    if not courses:
        raise ValueError("The shell has no courses.")
    bottom = 0.0
    for number, course in enumerate(courses, start=1):
        top = bottom + course.height_in
        on_top_edge = number == len(courses) and elevation_in == top
        if elevation_in < top or on_top_edge:
            return number, course, bottom
        bottom = top
    raise ValueError(f"Elevation {elevation_in:g} in is above the shell ({bottom:g} in).")


def projections(
    outside_projection_in: float,
    inside_projection_in: float,
    outside_radius_in: float,
    offset_in: float,
    match_plane: bool,
) -> tuple[float, float, float]:
    """Return outside projection, inside projection, and the plane-match correction.

    The correction is how much closer the shell is along an offset centerline
    than it is along the radial line. It is zero for a radial nozzle.
    """
    if abs(offset_in) >= outside_radius_in:
        raise ValueError(
            f"Offset {offset_in:g} in does not meet a shell of radius {outside_radius_in:g} in."
        )
    if offset_in == 0.0 or not match_plane:
        return outside_projection_in, inside_projection_in, 0.0
    along_axis = math.sqrt(outside_radius_in * outside_radius_in - offset_in * offset_in)
    chord = outside_radius_in - along_axis
    inside = inside_projection_in - chord
    if inside < 0.0:
        raise ValueError(
            f"Plane match would pull the inside projection to {inside:g} in. "
            "The offset is too large for that inside projection."
        )
    return outside_projection_in + chord, inside, chord


def _axis(rotation_deg: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Outward axis, and the clockwise direction looking down on the tank."""
    phi = math.radians(rotation_deg)
    outward = (-math.sin(phi), 0.0, math.cos(phi))
    clockwise = (math.cos(phi), 0.0, math.sin(phi))
    return outward, clockwise


def _shift(
    point: tuple[float, float, float],
    direction: tuple[float, float, float],
    distance: float,
) -> tuple[float, float, float]:
    return (
        point[0] + direction[0] * distance,
        point[1] + direction[1] * distance,
        point[2] + direction[2] * distance,
    )


def place(nozzle: Nozzle, spec: TankSpec) -> Placement:
    """Put ``nozzle`` on the shell described by Tank Properties."""
    number, course, bottom = course_at(spec, nozzle.elevation_in)
    outer_m, inner_m = course_radii_m(spec, course)
    outside = outer_m / _INCH
    inside_radius = inner_m / _INCH
    if abs(nozzle.offset_in) >= inside_radius:
        raise ValueError(
            f"Offset {nozzle.offset_in:g} in does not reach the inside of a shell of radius {inside_radius:g} in."
        )
    along_axis = math.sqrt(outside * outside - nozzle.offset_in * nozzle.offset_in)
    wall = along_axis - math.sqrt(inside_radius * inside_radius - nozzle.offset_in * nozzle.offset_in)
    # The typed inside projection starts at the shell inside. Plane match keeps the inner end
    # in the plane of a radial nozzle, so there the wall is the radial one.
    through = (outside - inside_radius) if nozzle.match_plane and nozzle.offset_in != 0.0 else wall
    outside_projection, inside_projection, chord = projections(
        nozzle.outside_projection_in,
        nozzle.inside_projection_in + through,
        outside,
        nozzle.offset_in,
        nozzle.match_plane,
    )
    outward, clockwise = _axis(nozzle.rotation_deg)
    shell = _shift((0.0, nozzle.elevation_in, 0.0), outward, along_axis)
    shell = _shift(shell, clockwise, nozzle.offset_in)
    neck = pipe(nozzle.nps, nozzle.schedule)
    fitting = flange(nozzle.nps, nozzle.rating, nozzle.kind)
    pad = resolve_repad(
        nozzle.nps,
        nozzle.repad_mode,
        course_thickness_in=course.thickness_in,
        outer_in=nozzle.repad_outer_in,
        inner_in=nozzle.repad_inner_in,
        thickness_in=nozzle.repad_thickness_in,
        style=nozzle.repad_style,
        telltale_offset_in=nozzle.telltale_offset_in,
    )
    ring = (
        gasket(nozzle.nps, nozzle.rating, nozzle.gasket_material, nozzle.gasket_thickness_in)
        if nozzle.gasket
        else None
    )
    face = _shift(shell, outward, outside_projection)
    return Placement(
        nozzle=nozzle,
        pipe=neck,
        flange=fitting,
        repad=pad,
        gasket=ring,
        course_number=number,
        course_bottom_in=bottom,
        outside_radius_in=outside,
        inside_radius_in=inside_radius,
        shell_in=shell,
        face_in=face,
        hub_end_in=_shift(face, outward, -fitting.face_to_hub_end_in),
        inner_end_in=_shift(shell, outward, -inside_projection),
        axis=outward,
        outside_projection_in=outside_projection,
        inside_projection_in=inside_projection,
        chord_in=chord,
        wall_in=wall,
    )
