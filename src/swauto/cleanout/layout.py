"""Course 1 around the FTCO insert plates."""

from __future__ import annotations

from collections.abc import Sequence

from swauto.cleanout.spec import Cleanout, developed_center_in
from swauto.tank.plates import CourseOneGap, developed_circumference_in, layout_plates
from swauto.tank.spec import TankSpec


def course_one_gaps(spec: TankSpec, cleanouts: Sequence[Cleanout]) -> list[CourseOneGap]:
    """One course-1 gap per FTCO, the length of its insert plate, centered on its orientation."""
    courses = spec.active_courses()
    if not courses:
        raise ValueError("Set a shell on Tank Properties first.")
    marks = [cleanout.mark for cleanout in cleanouts]
    twice = sorted({mark for mark in marks if marks.count(mark) > 1})
    if twice:
        raise ValueError(f"{', '.join(twice)} is on the list more than once.")
    anchored = [cleanout.mark for cleanout in cleanouts if cleanout.anchor != "none"]
    if len(anchored) > 1:
        raise ValueError(
            f"Only one FTCO can be anchored ({', '.join(anchored)} are); the seams can only start from one."
        )
    circumference = developed_circumference_in(spec, courses[0])
    gaps = []
    for cleanout in cleanouts:
        dims = cleanout.dims
        if dims.opening_height_in + 0.5 > courses[0].height_in:
            raise ValueError(f"{cleanout.mark}: course 1 is shorter than the {dims.label} opening.")
        if dims.repad_top_in > courses[0].height_in:
            raise ValueError(f"{cleanout.mark}: the {dims.label} repad is taller than course 1.")
        gaps.append(
            CourseOneGap(
                center_in=developed_center_in(cleanout.orientation_deg, circumference),
                length_in=dims.insert_length_in,
                anchor=cleanout.anchor,
            )
        )
    layout_plates(spec, gaps)  # refuses overlapping inserts
    return gaps
