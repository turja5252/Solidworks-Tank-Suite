import math

from swauto.tank.plates import (
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
