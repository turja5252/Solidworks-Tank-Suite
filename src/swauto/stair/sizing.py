"""Stair sizing and placement, the way the lisp launcher's Height/Angle input does it.

The full height runs from the floor, where the shell's chime sits, to the top of the
shell. A top offset moves the top tread down from there and a bottom offset moves the
ground down from the floor (negative moves either up). The ground is tread zero, so
tread 1 is one rise up and the top tread's surface is at the stair's height. With the
number of treads and the slope at the walk centerline, the rise is that height over
the treads and the run is the rise over tan(slope).

Orientation is in degrees like a nozzle's: 0 toward +Z, positive clockwise seen from
above. Either end of the stair can be put there, as the lisp's Lock bot / Lock top.
"""

from __future__ import annotations

import math
from dataclasses import replace

from swauto.stair.development import END_EXT_IN, MAX_PLATFORMS, flight_step, flight_treads
from swauto.stair.stringer import THICKNESS_IN, TREAD_DEPTH_IN, StringerMock

AUTO_RISE_IN = 7.5  # the lisp's default rise; a tread count picked from the height keeps every rise at or under it
MAX_SLOPE_DEG = 89.0  # the lisp takes a slope over 0 and under 89 degrees


def stair_height_in(shell_height_in: float, top_offset_in: float = 0.0, bottom_offset_in: float = 0.0) -> float:
    """Ground to the top tread's walking surface: the full height less the top offset, plus the bottom one."""
    height = shell_height_in - top_offset_in + bottom_offset_in
    if height <= 0:
        raise ValueError("The offsets leave no height between the ground and the top tread.")
    return height


def rise_run(height_in: float, treads: int, slope_deg: float) -> tuple[float, float]:
    """Rise and run of every tread, at the walk centerline."""
    if height_in <= 0:
        raise ValueError("Height must be greater than zero.")
    if treads < 1:
        raise ValueError("Treads must be at least 1.")
    if not 0.0 < slope_deg < MAX_SLOPE_DEG:
        raise ValueError(f"Slope must be greater than 0 and less than {MAX_SLOPE_DEG:g} degrees.")
    rise = height_in / treads
    return rise, rise / math.tan(math.radians(slope_deg))


def auto_treads(height_in: float, platforms: int = 0, max_rise_in: float = AUTO_RISE_IN) -> int:
    """Fewest treads that keep every rise at or under ``max_rise_in`` and still split into equal flights
    around ``platforms`` mid platforms (the tread level with a platform belongs to both flights)."""
    if height_in <= 0:
        raise ValueError("Height must be greater than zero.")
    if not 0 <= platforms <= MAX_PLATFORMS:
        raise ValueError(f"Mid platforms must be 0 to {MAX_PLATFORMS}.")
    count = max(2, math.ceil(height_in / max_rise_in - 1e-9))
    flights = platforms + 1
    while (count + platforms) % flights or (count + platforms) // flights < 2:
        count += 1
    return count


def slopes_deg(stair: StringerMock) -> dict[str, float]:
    """Slope in degrees along the walk centerline, each stringer's mid-wall, and the shell OD,
    as the lisp's Audit lists them. The plan angle per tread is the run over the walk centerline radius."""
    inner_face = stair.shell_od_in + stair.gap_in + THICKNESS_IN
    center = inner_face + stair.clear_in / 2.0
    turn = stair.run_in / center

    def at(radius: float) -> float:
        return math.degrees(math.atan2(stair.rise_in, radius * turn))

    return {
        "centerline": at(center),
        "inner": at(inner_face - THICKNESS_IN / 2.0),
        "outer": at(inner_face + stair.clear_in + THICKNESS_IN / 2.0),
        "shell": at(stair.shell_od_in),
    }


def tread_lap_in(run_in: float) -> float:
    """How far each tread laps the one below at the walk centerline: the tread depth less the run.
    Negative is a gap between them."""
    return TREAD_DEPTH_IN - run_in


def end_angles(stair: StringerMock, platforms: int = 0) -> tuple[float, float]:
    """Plan angles, in radians from +Z where the clockwise build starts, of the radial lines the stringers
    end on: the foot of the first flight and the top of the last. Both stringers of a flight stop on the
    same radial line, 1/8 in past the end treads on the inner one (``development.outer_end_ext_in``)."""
    per_flight = flight_treads(stair.treads, platforms)
    turn, _lift = flight_step(replace(stair, treads=per_flight))
    inner_face = stair.shell_od_in + stair.gap_in + THICKNESS_IN
    step = stair.run_in / (inner_face + stair.clear_in / 2.0)
    cap = (TREAD_DEPTH_IN / 2.0 + END_EXT_IN) / inner_face
    return step - cap, platforms * turn + per_flight * step + cap


def world_angle(angle: float, turn: float = 0.0, ccw: bool = False) -> float:
    """Where a plan angle of the clockwise build ends up on the tank, in radians the nozzles' way: mirrored
    through the Right plane for a counterclockwise stair (that takes an angle to its negative), then turned."""
    return (-angle if ccw else angle) + turn


def placement_turn(orientation_deg: float, foot: float, top: float, *, at_top: bool, ccw: bool) -> float:
    """The turn about the tank axis, after any mirror, that puts the chosen end at ``orientation_deg``."""
    end = world_angle(top if at_top else foot, 0.0, ccw)
    return math.remainder(math.radians(orientation_deg) - end, 2.0 * math.pi)


def orientation_deg(angle: float) -> float:
    """A plan angle in radians as orientation degrees, 0 up to 360."""
    return math.degrees(angle) % 360.0
