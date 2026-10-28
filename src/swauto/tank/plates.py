"""Plate-per-course layout (ported from AutoLISP Shell Plate Elevation)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from swauto.tank.profile import course_radii_m
from swauto.tank.spec import (
    MODE_UNKNOWN,
    STAGGER_HALF,
    Course,
    TankSpec,
)
from swauto.units import to_meters


def ceil_div(length: float, max_len: float) -> int:
    if max_len <= 0:
        return 1
    n = int(math.ceil(length / max_len - 1e-12))
    return max(1, n)


def developed_circumference_in(spec: TankSpec, course: Course) -> float:
    """Mid-wall / basis circumference in inches (matches stretchout tiling girth)."""
    outer_r_m, inner_r_m = course_radii_m(spec, course)
    mid_r_m = 0.5 * (outer_r_m + inner_r_m)
    return mid_r_m * 2.0 * math.pi / 0.0254


def plate_count_and_length(circ_in: float, course: Course) -> tuple[int, float]:
    if course.mode == MODE_UNKNOWN or circ_in <= 0:
        return 1, circ_in if circ_in > 0 else course.max_length_in
    count = ceil_div(circ_in, course.max_length_in)
    return count, circ_in / count


def course_seam_shift_in(course: Course, plate_len_in: float) -> float:
    """Half-plate stagger (AutoLISP shifted) plus Adjust inches."""
    half = (plate_len_in / 2.0) if course.stagger == STAGGER_HALF else 0.0
    return half + float(course.adjust_in)


@dataclass(frozen=True)
class PlateSector:
    """One solid shell plate as an annular sector."""

    course_no: int  # 1-based
    plate_no: int  # 1-based within course
    start_rad: float
    sweep_rad: float
    z_bot_m: float
    height_m: float
    outer_r_m: float
    inner_r_m: float
    length_in: float

    @property
    def feature_name(self) -> str:
        return f"EliteTankC{self.course_no}P{self.plate_no:02d}"

    @property
    def sketch_name(self) -> str:
        return f"{self.feature_name}Sk"

    @property
    def is_full_ring(self) -> bool:
        return self.sweep_rad >= (2.0 * math.pi - 1e-6)


ANCHORS = ("none", "left", "right", "short")


@dataclass(frozen=True)
class CourseOneGap:
    """A stretch of course 1 taken by an insert plate (an FTCO), in developed inches from the seam origin.

    ``anchor`` moves the course-1 seams so one lands on an edge of this gap: ``left`` the edge at
    the smaller distance, ``right`` the larger, ``short`` whichever edge is already nearer a seam.
    """

    center_in: float
    length_in: float
    anchor: str = "none"

    def __post_init__(self) -> None:
        if self.anchor not in ANCHORS:
            raise ValueError(f"Anchor {self.anchor!r} must be one of {', '.join(ANCHORS)}.")
        if self.length_in <= 0.0:
            raise ValueError("An insert plate needs a length.")


def layout_plates(spec: TankSpec, gaps: Sequence[CourseOneGap] = ()) -> list[PlateSector]:
    """Compute discrete plates for all active courses (Equal / unknown modes).

    ``gaps`` are course-1 stretches left open for insert plates (Shell Plate Elevation
    SPE:ftco-*): with one anchored gap the normal plates are shifted onto its edge and cut by
    it; otherwise the open stretches between gaps are tiled with equal plates.
    """
    spec.validate()
    plates: list[PlateSector] = []
    z_m = 0.0
    global_offset = float(spec.seam_offset_in)

    for course_no, course in enumerate(spec.active_courses(), start=1):
        outer_r_m, inner_r_m = course_radii_m(spec, course)
        height_m = to_meters(course.height_in, "in")
        circ_in = developed_circumference_in(spec, course)
        count, plate_len = plate_count_and_length(circ_in, course)
        # Global unwrap offset + half-plate stagger + Adjust (AutoLISP seamOffset).
        start_dist = global_offset + course_seam_shift_in(course, plate_len)

        if course_no == 1 and gaps:
            if course.mode == MODE_UNKNOWN:
                raise ValueError("Course 1 needs a plate layout to take an insert plate, not Unknown.")
            pieces = course_one_pieces(circ_in, plate_len, start_dist, course.max_length_in, gaps)
            for p, (dist0, length) in enumerate(pieces):
                plates.append(
                    PlateSector(
                        course_no=course_no,
                        plate_no=p + 1,
                        start_rad=(dist0 / circ_in) * 2.0 * math.pi,
                        sweep_rad=(length / circ_in) * 2.0 * math.pi,
                        z_bot_m=z_m,
                        height_m=height_m,
                        outer_r_m=outer_r_m,
                        inner_r_m=inner_r_m,
                        length_in=length,
                    )
                )
            z_m += height_m
            continue

        for p in range(count):
            dist0 = start_dist + p * plate_len
            # Wrap into [0, circ)
            dist0 = dist0 % circ_in if circ_in > 0 else 0.0
            start_rad = (dist0 / circ_in) * 2.0 * math.pi if circ_in > 0 else 0.0
            sweep_rad = (plate_len / circ_in) * 2.0 * math.pi if circ_in > 0 else 2.0 * math.pi
            if course.mode == MODE_UNKNOWN:
                sweep_rad = 2.0 * math.pi
                start_rad = 0.0
            plates.append(
                PlateSector(
                    course_no=course_no,
                    plate_no=p + 1,
                    start_rad=start_rad,
                    sweep_rad=min(sweep_rad, 2.0 * math.pi),
                    z_bot_m=z_m,
                    height_m=height_m,
                    outer_r_m=outer_r_m,
                    inner_r_m=inner_r_m,
                    length_in=plate_len if course.mode != MODE_UNKNOWN else circ_in,
                )
            )
        z_m += height_m
    return plates


def course_one_pieces(
    circ_in: float,
    plate_len: float,
    start_dist: float,
    max_len: float,
    gaps: Sequence[CourseOneGap],
) -> list[tuple[float, float]]:
    """Course-1 plates around insert-plate gaps, as (start, length) in developed inches.

    One anchored gap: the normal seams run from its anchored edge, and both its edges are seams
    too, so the far edge cuts a normal plate short (SPE:ftco-anchored-boundaries). Otherwise each
    open stretch between gaps gets equal plates no longer than ``max_len``
    (SPE:ftco-segment-boundaries). Nothing is laid inside a gap.
    """
    eps = 1e-6
    taken = _taken(circ_in, gaps)
    seams = {start % circ_in for start, _length in taken} | {(start + length) % circ_in for start, length in taken}
    anchored = [gap for gap in gaps if gap.anchor != "none"]
    if len(anchored) == 1:
        first = _anchor_seam(anchored[0], circ_in, plate_len, start_dist)
        count = max(1, round(circ_in / plate_len))
        seams.update((first + k * plate_len) % circ_in for k in range(count))
    else:
        for start, length in _open_stretches(circ_in, taken):
            count = ceil_div(length, max_len)
            step = length / count
            seams.update((start + k * step) % circ_in for k in range(1, count))
    ordered: list[float] = []
    for seam in sorted(seams):
        if not ordered or seam - ordered[-1] > eps:
            ordered.append(seam)
    if len(ordered) > 1 and ordered[0] + circ_in - ordered[-1] <= eps:
        ordered.pop()
    pieces = []
    for index, start in enumerate(ordered):
        end = ordered[(index + 1) % len(ordered)]
        length = (end - start) % circ_in or circ_in
        middle = (start + length / 2.0) % circ_in
        if length > eps and not any((middle - a) % circ_in < span for a, span in taken):
            pieces.append((start, length))
    return pieces


def _taken(circ_in: float, gaps: Sequence[CourseOneGap]) -> list[tuple[float, float]]:
    """Each gap as (start, length), start wrapped into the circumference, sorted. Overlaps are refused."""
    taken = sorted(((gap.center_in - gap.length_in / 2.0) % circ_in, gap.length_in) for gap in gaps)
    if sum(length for _start, length in taken) >= circ_in:
        raise ValueError("The insert plates take the whole of course 1.")
    for (a, span), (b, _next) in zip(taken, taken[1:] + taken[:1]):
        if len(taken) > 1 and (b - a) % circ_in < span - 1e-6:
            raise ValueError("Two insert plates overlap on course 1.")
    return taken


def _open_stretches(circ_in: float, taken: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The course-1 stretches between gaps, as (start, length)."""
    stretches = []
    for (a, span), (b, _next) in zip(taken, taken[1:] + taken[:1]):
        start = (a + span) % circ_in
        length = (b - start) % circ_in if len(taken) > 1 else circ_in - span
        if length > 1e-6:
            stretches.append((start, length))
    return stretches


def _anchor_seam(gap: CourseOneGap, circ_in: float, plate_len: float, start_dist: float) -> float:
    """Where the anchored normal seam goes (SPE:course1-anchor-offset)."""
    left = (gap.center_in - gap.length_in / 2.0) % circ_in
    right = (gap.center_in + gap.length_in / 2.0) % circ_in
    if gap.anchor == "left":
        return left
    if gap.anchor == "right":
        return right

    # Short: the edge that moves the seams least. The LISP measures from seams at whole plate
    # lengths from zero; this measures from where the seams actually are.
    def nearest(edge: float) -> float:
        off = (edge - start_dist) % plate_len
        return min(off, plate_len - off)

    return left if nearest(left) < nearest(right) else right
