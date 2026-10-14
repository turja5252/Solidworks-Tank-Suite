"""Plate-per-course layout (ported from AutoLISP Shell Plate Elevation)."""

from __future__ import annotations

import math
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


def layout_plates(spec: TankSpec) -> list[PlateSector]:
    """Compute discrete plates for all active courses (Equal / unknown modes)."""
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
