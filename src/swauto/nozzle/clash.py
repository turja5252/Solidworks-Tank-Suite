"""Nozzles that run into each other (2026-10-31).

Each nozzle's footprint is its pad or, without one, its neck: on the shell unrolled at its outside (round from 0 deg,
up from the floor), or on the roof in plan. A tombstone pad runs on down to the floor, or out to the roof's landing.
Two footprints that overlap are said on both rows, as a warning like a pad over a course seam: the rows still build.
Flanges and anything inside the tank are not compared.
"""

from __future__ import annotations

import math

TOUCH_IN = 0.01  # overlapping by more than this is running into


def shell_clashes(placements) -> dict[int, list[int]]:
    """For each index into ``placements`` (nozzle.place.Placement), the indexes of those its footprint runs into."""
    prints = []
    for placed in placements:
        x, y, z = placed.shell_in
        pad = placed.repad
        radius = (pad.outer_diameter_in if pad is not None else placed.pipe.outside_diameter_in) / 2.0
        bottom = 0.0 if pad is not None and pad.style == "tombstone" else y
        prints.append((math.atan2(-x, z), y, bottom, radius, placed.outside_radius_in))
    found: dict[int, list[int]] = {i: [] for i in range(len(prints))}
    for i, (a1, y1, b1, r1, s1) in enumerate(prints):
        for j in range(i + 1, len(prints)):
            a2, y2, b2, r2, s2 = prints[j]
            dx = math.remainder(a2 - a1, 2.0 * math.pi) * (s1 + s2) / 2.0  # round the shell the short way
            if _apart((0.0, y1), (0.0, b1), (dx, y2), (dx, b2)) < r1 + r2 - TOUCH_IN:
                found[i].append(j)
                found[j].append(i)
    return found


def roof_clashes(placements) -> dict[int, list[int]]:
    """The same in plan for roof nozzles and manways (nozzle.roof_place.RoofPlacement)."""
    prints = []
    for placed in placements:
        centre = placed.plan_in
        pad = placed.repad
        radius = (pad.outer_diameter_in if pad is not None else placed.pipe.outside_diameter_in) / 2.0
        end = centre
        if pad is not None and pad.style == "tombstone" and placed.radius_in > 1e-9:
            out = placed.roof.landing_radius_in() / placed.radius_in
            end = (centre[0] * out, centre[1] * out)
        prints.append((centre, end, radius))
    found: dict[int, list[int]] = {i: [] for i in range(len(prints))}
    for i, (c1, e1, r1) in enumerate(prints):
        for j in range(i + 1, len(prints)):
            c2, e2, r2 = prints[j]
            if _apart(c1, e1, c2, e2) < r1 + r2 - TOUCH_IN:
                found[i].append(j)
                found[j].append(i)
    return found


def note(marks: list[str]) -> str:
    """The row's warning: ", runs into N2", ", runs into N2 and N5", ", runs into N2, N3 and N5"."""
    if not marks:
        return ""
    names = marks[0] if len(marks) == 1 else f"{', '.join(marks[:-1])} and {marks[-1]}"
    return f", runs into {names}"


def _apart(p0, p1, q0, q1) -> float:
    """The least distance between the segments p0-p1 and q0-q1 (either may be a point)."""
    if _cross(p0, p1, q0, q1):
        return 0.0
    return min(_to_segment(p0, q0, q1), _to_segment(p1, q0, q1), _to_segment(q0, p0, p1), _to_segment(q1, p0, p1))


def _to_segment(p, a, b) -> float:
    ax, ay = b[0] - a[0], b[1] - a[1]
    length = ax * ax + ay * ay
    t = 0.0 if length < 1e-18 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / length))
    return math.hypot(p[0] - (a[0] + t * ax), p[1] - (a[1] + t * ay))


def _cross(p0, p1, q0, q1) -> bool:
    """The two segments cross (properly, each one's ends on either side of the other)."""
    def side(a, b, c) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = side(q0, q1, p0), side(q0, q1, p1)
    d3, d4 = side(p0, p1, q0), side(p0, p1, q1)
    return d1 * d2 < 0.0 and d3 * d4 < 0.0
