"""Turned nozzle profile, in inches. The shell face is z = 0 and +z points out of the tank.

These loops are revolved about the nozzle axis. A weld neck is one loop. A slip-on
is a pipe through a flange whose bore is larger than the pipe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.nozzle.place import Placement


@dataclass(frozen=True)
class Stations:
    """Stations along the nozzle, inches. z = 0 is the outside of the shell. ``inner_z`` is the inside end
    (the inside flange's raised face when there is one); ``pipe_z`` is where the pipe stops inside."""

    inner_z: float
    hub_z: float
    back_z: float
    seat_z: float
    face_z: float
    pipe_z: float


@dataclass(frozen=True)
class InsideStations:
    """The inside flange, turned to face into the tank: its raised face, seat and back, and its hub's end
    toward the shell. Inches along the nozzle, z = 0 at the shell outside."""

    face_z: float
    seat_z: float
    back_z: float
    hub_z: float


def stations(placed: Placement) -> Stations:
    """Hub, flange back, raised-face seat, and face measured from the shell."""
    face = placed.outside_projection_in
    inner = -placed.inside_projection_in
    fitting = placed.flange
    hub = face - fitting.face_to_hub_end_in
    back = face - fitting.raised_face_in - fitting.thickness_in
    seat = face - fitting.raised_face_in
    inside = inside_stations(placed)
    if inside is None:
        pipe = inner
    else:
        # A weld neck's hub takes the pipe end on; a slip-on's pipe runs in to under its raised face.
        pipe = inside.hub_z if placed.inside_flange.kind == "wn" else inside.seat_z
    if not pipe < hub < back < seat < face:
        need = fitting.face_to_hub_end_in
        raise ValueError(
            f"{placed.nozzle.mark}: the projection is shorter than the flange. "
            f"From the inner end to the raised face needs more than {need:g} in."
        )
    return Stations(inner_z=inner, hub_z=hub, back_z=back, seat_z=seat, face_z=face, pipe_z=pipe)


def inside_stations(placed: Placement) -> InsideStations | None:
    """Where the inside flange sits, or None without one. Its whole length has to be inside the shell."""
    fitting = placed.inside_flange
    if fitting is None:
        return None
    face = -placed.inside_projection_in
    seat = face + fitting.raised_face_in
    back = seat + fitting.thickness_in
    hub = face + fitting.face_to_hub_end_in
    if hub > -placed.wall_in + 1e-9:
        raise ValueError(
            f"{placed.nozzle.mark}: the inside flange needs {fitting.face_to_hub_end_in:g} in from its face to "
            "the end of its hub inside the shell; make the ISP at least that."
        )
    return InsideStations(face_z=face, seat_z=seat, back_z=back, hub_z=hub)


def inside_flange_loop(placed: Placement) -> list[tuple[float, float]] | None:
    """Closed (z, radius) of the inside flange, raised face toward the tank center, or None without one.

    It is the outside flange's shape turned end for end: a weld neck butts the pipe at its hub, a slip-on
    takes the pipe through its bore.
    """
    spot = inside_stations(placed)
    if spot is None:
        return None
    fitting = placed.inside_flange
    pipe_r = placed.pipe.outside_diameter_in / 2.0
    hub_r = fitting.hub_diameter_in / 2.0
    flange_r = fitting.outside_diameter_in / 2.0
    face_r = fitting.raised_face_diameter_in / 2.0
    if fitting.kind == "wn":
        bore = placed.pipe.inside_diameter_in / 2.0
        neck = [(spot.hub_z, bore), (spot.hub_z, pipe_r)]
    else:
        bore = fitting.slip_on_bore_in / 2.0
        if bore <= pipe_r:
            raise ValueError(f"{placed.nozzle.mark}: the inside slip-on's bore does not clear the pipe.")
        neck = [(spot.hub_z, bore), (spot.hub_z, hub_r)]
    return neck + [
        (spot.back_z, hub_r),
        (spot.back_z, flange_r),
        (spot.seat_z, flange_r),
        (spot.seat_z, face_r),
        (spot.face_z, face_r),
        (spot.face_z, bore),
    ]


def weld_neck_loop(placed: Placement) -> list[tuple[float, float]]:
    """Closed (z, radius) of a weld neck, bore included."""
    spot = stations(placed)
    neck = placed.pipe
    fitting = placed.flange
    bore = neck.inside_diameter_in / 2.0
    pipe_r = neck.outside_diameter_in / 2.0
    hub_r = fitting.hub_diameter_in / 2.0
    flange_r = fitting.outside_diameter_in / 2.0
    face_r = fitting.raised_face_diameter_in / 2.0
    return [
        (spot.pipe_z, bore),
        (spot.pipe_z, pipe_r),
        (spot.hub_z, pipe_r),
        (spot.back_z, hub_r),
        (spot.back_z, flange_r),
        (spot.seat_z, flange_r),
        (spot.seat_z, face_r),
        (spot.face_z, face_r),
        (spot.face_z, bore),
    ]


def slip_on_loops(placed: Placement) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Pipe loop, then the slip-on flange loop. The pipe stops under the raised face."""
    spot = stations(placed)
    neck = placed.pipe
    fitting = placed.flange
    bore = fitting.slip_on_bore_in / 2.0
    pipe_r = neck.outside_diameter_in / 2.0
    pipe_bore = neck.inside_diameter_in / 2.0
    if bore <= pipe_r:
        raise ValueError(f"{placed.nozzle.mark}: the slip-on bore does not clear the pipe.")
    hub_r = fitting.hub_diameter_in / 2.0
    flange_r = fitting.outside_diameter_in / 2.0
    face_r = fitting.raised_face_diameter_in / 2.0
    pipe = [
        (spot.pipe_z, pipe_bore),
        (spot.pipe_z, pipe_r),
        (spot.seat_z, pipe_r),
        (spot.seat_z, pipe_bore),
    ]
    flange = [
        (spot.hub_z, bore),
        (spot.hub_z, hub_r),
        (spot.back_z, hub_r),
        (spot.back_z, flange_r),
        (spot.seat_z, flange_r),
        (spot.seat_z, face_r),
        (spot.face_z, face_r),
        (spot.face_z, bore),
    ]
    return pipe, flange


def gasket_loop(placed: Placement) -> list[tuple[float, float]] | None:
    """Closed (z, radius) of the ring gasket on the raised face, or None without one."""
    ring = placed.gasket
    if ring is None:
        return None
    face = stations(placed).face_z
    inner = ring.inner_diameter_in / 2.0
    outer = ring.outer_diameter_in / 2.0
    top = face + ring.thickness_in
    return [(face, inner), (face, outer), (top, outer), (top, inner)]


def blind_loop(placed: Placement) -> list[tuple[float, float]] | None:
    """Closed (z, radius) of the blind flange, raised face down on the gasket or the flange face.

    A B16.5 blind has the same thickness, outside diameter, and raised face as the flange it closes.
    """
    if not placed.nozzle.blind:
        return None
    fitting = placed.flange
    seat = blind_seat_z(placed)
    face_r = fitting.raised_face_diameter_in / 2.0
    flange_r = fitting.outside_diameter_in / 2.0
    rise = seat + fitting.raised_face_in
    top = rise + fitting.thickness_in
    return [(seat, 0.0), (seat, face_r), (rise, face_r), (rise, flange_r), (top, flange_r), (top, 0.0)]


def blind_seat_z(placed: Placement) -> float:
    """Where the blind's raised face sits: on the gasket if there is one."""
    face = stations(placed).face_z
    return face + (placed.gasket.thickness_in if placed.gasket is not None else 0.0)


def outer_end_z(placed: Placement) -> float:
    """The outermost face of the nozzle: the blind's back, the gasket, or the flange face."""
    loops = [loop for loop in (blind_loop(placed), gasket_loop(placed)) if loop is not None]
    if not loops:
        return stations(placed).face_z
    return max(z for loop in loops for z, _r in loop)


def bolt_centers(bolt_circle_in: float, count: int) -> list[tuple[float, float]]:
    """Hole centers in the flange plane. They straddle the vertical centerline.

    x is to the right looking out of the tank, y is up. Inches.
    """
    if count < 4 or count % 4 != 0:
        raise ValueError(f"A flange needs a multiple of 4 bolt holes, not {count}.")
    radius = bolt_circle_in / 2.0
    step = 2.0 * math.pi / count
    start = math.pi / count
    centers = []
    for index in range(count):
        theta = start + index * step
        centers.append((-radius * math.sin(theta), radius * math.cos(theta)))
    return centers
