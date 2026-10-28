import math

import pytest

from swauto.tank.plates import (
    CourseOneGap,
    course_one_pieces,
    course_seam_shift_in,
    developed_circumference_in,
    layout_plates,
    plate_count_and_length,
)
from swauto.tank.spec import (
    MODE_UNKNOWN,
    STAGGER_BASE,
    STAGGER_HALF,
    Course,
    TankSpec,
)


def test_plate_count_equal_mode():
    course = Course(96, 1.0, max_length_in=480.0, stagger=STAGGER_BASE)
    # ~50.5' OD tank mid-wall circ is large → several plates
    spec = TankSpec(diameter_in=606, diameter_basis="outside", courses=[course] + [Course(0, 0)] * 7)
    circ = developed_circumference_in(spec, course)
    count, length = plate_count_and_length(circ, course)
    assert count >= 4
    assert abs(count * length - circ) < 1e-6


def test_half_stagger_shifts_half_plate():
    course = Course(96, 1.0, max_length_in=100.0, stagger=STAGGER_HALF, adjust_in=0.0)
    assert course_seam_shift_in(course, 50.0) == 25.0
    base = Course(96, 1.0, max_length_in=100.0, stagger=STAGGER_BASE, adjust_in=10.0)
    assert course_seam_shift_in(base, 50.0) == 10.0


def test_layout_stagger_between_courses():
    c1 = Course(48, 0.5, max_length_in=200.0, stagger=STAGGER_BASE)
    c2 = Course(48, 0.5, max_length_in=200.0, stagger=STAGGER_HALF)
    spec = TankSpec(
        diameter_in=100.0,
        diameter_basis="outside",
        courses=[c1, c2] + [Course(0, 0)] * 6,
    )
    plates = layout_plates(spec)
    c1_plates = [p for p in plates if p.course_no == 1]
    c2_plates = [p for p in plates if p.course_no == 2]
    assert len(c1_plates) >= 1
    assert len(c2_plates) >= 1
    # Half stagger on C2 → first plate start ≈ half of C2 plate sweep
    expected = c2_plates[0].sweep_rad / 2.0
    assert abs(c2_plates[0].start_rad - expected) < 1e-6
    assert abs(c1_plates[0].start_rad) < 1e-6


def test_unknown_mode_one_full_ring():
    course = Course(96, 1.0, mode=MODE_UNKNOWN, stagger=STAGGER_BASE)
    spec = TankSpec(diameter_in=120, courses=[course] + [Course(0, 0)] * 7)
    plates = layout_plates(spec)
    assert len(plates) == 1
    assert plates[0].is_full_ring
    assert abs(plates[0].sweep_rad - 2 * math.pi) < 1e-9


def test_etp_roundtrip_includes_stagger():
    spec = TankSpec(
        diameter_in=606,
        diameter_basis="centerline",
        courses=[Course(96, 1.0, stagger=STAGGER_HALF, adjust_in=12.0, max_length_in=400.0)]
        + [Course(0, 0)] * 7,
        seam_offset_in=5.0,
    )
    data = spec.to_etp_dict()
    assert data["SHELL_COURSE_1_STAGGER"] == STAGGER_HALF
    assert data["SHELL_COURSE_1_ADJUST"] == "12"
    assert data["SHELL_STRETCH_OFFSET"] == "5"
    back = TankSpec.from_etp_dict(data)
    assert back.courses[0].stagger == STAGGER_HALF
    assert back.courses[0].adjust_in == 12.0
    assert back.seam_offset_in == 5.0


def test_plate_plane_contains_start_azimuth():
    from swauto.tank.shell import containing_plane_angle, radius_sign_for_azimuth

    assert abs(containing_plane_angle(0.0)) < 1e-9
    assert abs(containing_plane_angle(math.pi)) < 1e-9
    assert radius_sign_for_azimuth(0.0, 0.0) == 1.0
    assert radius_sign_for_azimuth(0.0, math.pi) == -1.0

    # pi/2 folds onto the Right plane (same plane as -pi/2). Sketch +X at -pi/2
    # is the opposite side, so the profile is drawn on negative radius.
    assert abs(containing_plane_angle(math.pi / 2) + math.pi / 2) < 1e-9
    assert radius_sign_for_azimuth(-math.pi / 2, math.pi / 2) == -1.0

    two_thirds = 2.0 * math.pi / 3.0
    plane = containing_plane_angle(two_thirds)
    assert abs(plane + math.pi / 3.0) < 1e-9
    assert radius_sign_for_azimuth(plane, two_thirds) == -1.0


# Course 1 around FTCO insert plates: a 1000 in course of four 250 in plates, seams from 0.


def _lengths(pieces):
    return [round(length, 6) for _start, length in pieces]


def test_left_anchor_puts_a_seam_on_the_near_edge_and_the_far_edge_cuts_a_plate_short():
    pieces = course_one_pieces(1000.0, 250.0, 0.0, 300.0, [CourseOneGap(500.0, 130.0, "left")])
    assert [round(start, 6) for start, _ in pieces] == [185.0, 565.0, 685.0, 935.0]
    assert _lengths(pieces) == [250.0, 120.0, 250.0, 250.0]


def test_right_anchor_puts_the_seam_on_the_far_edge():
    pieces = course_one_pieces(1000.0, 250.0, 0.0, 300.0, [CourseOneGap(500.0, 130.0, "right")])
    assert [round(start, 6) for start, _ in pieces] == [65.0, 315.0, 565.0, 815.0]
    assert _lengths(pieces) == [250.0, 120.0, 250.0, 250.0]


def test_short_anchor_takes_the_edge_already_nearest_a_seam():
    # Edges at 455 and 585; the seam at 500 is 45 from the left edge and 85 from the right.
    pieces = course_one_pieces(1000.0, 250.0, 0.0, 300.0, [CourseOneGap(520.0, 130.0, "short")])
    assert any(abs(start + length - 455.0) < 1e-6 for start, length in pieces)
    assert sum(length for _, length in pieces) == pytest.approx(870.0)


def test_unanchored_gaps_split_each_open_stretch_evenly():
    gaps = [CourseOneGap(250.0, 100.0), CourseOneGap(750.0, 100.0)]
    pieces = course_one_pieces(1000.0, 250.0, 0.0, 300.0, gaps)
    assert sorted(round(start, 6) for start, _ in pieces) == [0.0, 300.0, 500.0, 800.0]
    assert _lengths(pieces) == [200.0] * 4


def test_two_anchors_fall_back_to_even_stretches_like_the_lisp():
    gaps = [CourseOneGap(250.0, 100.0, "left"), CourseOneGap(750.0, 100.0, "right")]
    assert _lengths(course_one_pieces(1000.0, 250.0, 0.0, 300.0, gaps)) == [200.0] * 4


def test_a_gap_across_the_seam_origin_wraps():
    pieces = course_one_pieces(1000.0, 250.0, 0.0, 300.0, [CourseOneGap(0.0, 130.0, "left")])
    assert sum(length for _, length in pieces) == pytest.approx(870.0)
    # The gap runs from 935 round through 0 to 65; every plate stays between 65 and 935.
    assert all(65.0 - 1e-6 <= start and start + length <= 935.0 + 1e-6 for start, length in pieces)


def test_overlapping_inserts_are_refused():
    with pytest.raises(ValueError, match="overlap"):
        course_one_pieces(1000.0, 250.0, 0.0, 300.0, [CourseOneGap(500.0, 130.0), CourseOneGap(550.0, 130.0)])


def test_layout_leaves_the_gap_open_on_course_one_only():
    c1 = Course(96, 1.0, max_length_in=480.0, stagger=STAGGER_BASE)
    c2 = Course(96, 0.75, max_length_in=480.0, stagger=STAGGER_HALF)
    spec = TankSpec(diameter_in=606, diameter_basis="od", courses=[c1, c2] + [Course(0, 0)] * 6)
    plain = layout_plates(spec)
    circ = developed_circumference_in(spec, spec.courses[0])
    gapped = layout_plates(spec, [CourseOneGap(circ / 4.0, 149.0, "left")])
    course1 = [p for p in gapped if p.course_no == 1]
    assert sum(p.length_in for p in course1) == pytest.approx(circ - 149.0)
    assert sum(p.sweep_rad for p in course1) == pytest.approx(2 * math.pi * (1 - 149.0 / circ))
    assert [p for p in gapped if p.course_no == 2] == [p for p in plain if p.course_no == 2]
    assert [p.plate_no for p in course1] == list(range(1, len(course1) + 1))
