"""FTCO sizes, inputs and the course-1 gaps they make."""

import math

import pytest

from swauto.cleanout.layout import course_one_gaps
from swauto.cleanout.spec import (
    BOLT_HOLE_DIA_IN,
    FLANGE_HALF_WIDTH_IN,
    SIZES,
    Cleanout,
    azimuth_rad,
    developed_center_in,
    normalize_size,
)
from swauto.tank.plates import developed_circumference_in, layout_plates
from swauto.tank.spec import Course, TankSpec


def _ftco(**more) -> Cleanout:
    return Cleanout("C1", annular_width_in=24.0, **more)


def _tank() -> TankSpec:
    return TankSpec(diameter_in=607.0, diameter_basis="od", courses=[Course(96.0, 1.0), Course(96.0, 0.75)])


def test_sizes_match_the_api_openings():
    big, small = SIZES["12'-5\""], SIZES["10'-10\""]
    assert (big.insert_length_in, big.repad_length_in, big.opening_height_in) == (149.0, 125.0, 48.0)
    assert (small.insert_length_in, small.repad_length_in, small.opening_height_in) == (130.0, 106.0, 36.0)
    assert (big.repad_half_in * 2, big.repad_top_in) == (125.0, 72.0)
    assert (small.repad_half_in * 2, small.repad_top_in) == (106.0, 54.0)


def test_bolt_holes_are_symmetric_and_clear_the_flange_edge():
    for dims in SIZES.values():
        holes = set(dims.bolt_holes)
        assert {(-x, y) for x, y in holes} == holes
        for x, y in holes:
            # Inside the 57 in outline: straight sides below the arch center, R28.5 above it.
            reach = abs(x) if y <= dims.arch_center_in else math.hypot(x, y - dims.arch_center_in)
            assert reach + BOLT_HOLE_DIA_IN / 2.0 < FLANGE_HALF_WIDTH_IN
            assert y - BOLT_HOLE_DIA_IN / 2.0 > dims.flange_bottom_in
    # As many circles as Flange12-5.lsp and Flange10-10.lsp draw.
    assert len(SIZES["12'-5\""].bolt_holes) == 52
    assert len(SIZES["10'-10\""].bolt_holes) == 46


def test_inputs_are_checked():
    assert normalize_size("48x36") == "10'-10\""
    assert _ftco(anchor="Left").anchor == "left"
    with pytest.raises(ValueError, match="size"):
        _ftco(size="8x16")
    with pytest.raises(ValueError, match="bottom plate width"):
        Cleanout("C1")
    with pytest.raises(ValueError, match="annular plate is thicker"):
        _ftco(annular_thk_in=0.5)


def test_orientation_is_measured_like_a_nozzle_rotation():
    assert azimuth_rad(0.0) == pytest.approx(math.pi / 2.0)  # +Z
    assert azimuth_rad(90.0) == pytest.approx(math.pi)  # -X
    assert developed_center_in(0.0, 1000.0) == pytest.approx(250.0)
    assert developed_center_in(270.0, 1000.0) == pytest.approx(0.0)


def test_the_insert_plate_leaves_a_gap_in_course_one():
    tank = _tank()
    gaps = course_one_gaps(tank, [_ftco(anchor="left")])
    circ = developed_circumference_in(tank, tank.active_courses()[0])
    assert gaps[0].center_in == pytest.approx(circ / 4.0)
    course1 = [plate for plate in layout_plates(tank, gaps) if plate.course_no == 1]
    assert sum(plate.length_in for plate in course1) == pytest.approx(circ - 149.0)


def test_course_one_checks():
    tank = _tank()
    with pytest.raises(ValueError, match="one FTCO can be anchored"):
        course_one_gaps(tank, [_ftco(anchor="left"), Cleanout("C2", annular_width_in=24.0, anchor="right",
                                                              orientation_deg=180.0)])
    with pytest.raises(ValueError, match="overlap"):
        course_one_gaps(tank, [_ftco(), Cleanout("C2", annular_width_in=24.0, orientation_deg=5.0)])
    with pytest.raises(ValueError, match="more than once"):
        course_one_gaps(tank, [_ftco(), _ftco(orientation_deg=180.0)])
    low = TankSpec(diameter_in=607.0, diameter_basis="od", courses=[Course(40.0, 1.0)])
    with pytest.raises(ValueError, match="shorter than"):
        course_one_gaps(low, [_ftco()])
