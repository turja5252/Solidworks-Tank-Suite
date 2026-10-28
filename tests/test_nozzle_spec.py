"""Nozzle dimensions and placement, with no SolidWorks."""

import math

import pytest

from swauto.nozzle.flange import flange
from swauto.nozzle.pipe import pipe
from swauto.nozzle.place import course_at, place, projections
from swauto.nozzle.repad import resolve_repad, tombstone_crown_in
from swauto.nozzle.spec import Nozzle
from swauto.tank.spec import Course, TankSpec


def _shell() -> TankSpec:
    return TankSpec(
        diameter_in=200.0,
        diameter_basis="od",
        courses=[Course(96.0, 0.50), Course(96.0, 0.375)],
    )


def test_pipe_extra_strong_six_inch():
    neck = pipe("6", "XS")
    assert neck.outside_diameter_in == 6.625
    assert neck.wall_in == 0.432
    assert neck.inside_diameter_in == pytest.approx(5.761)


def test_double_extra_strong_stops_at_twelve_inch():
    assert pipe(12, "XXS").wall_in == 1.0
    with pytest.raises(ValueError, match="no XXS"):
        pipe(14, "XXS")


def test_class_150_weld_neck_six_inch():
    fitting = flange(6, 150, "weld neck")
    assert fitting.outside_diameter_in == 11.00
    assert fitting.thickness_in == 0.94
    assert fitting.raised_face_in == 0.06
    assert fitting.overall_thickness_in == pytest.approx(1.00)
    assert fitting.length_through_hub_in == 3.44
    assert fitting.face_to_hub_end_in == pytest.approx(3.50)
    assert fitting.hub_diameter_in == 7.56
    assert fitting.bolt_count == 8
    assert fitting.bolt_hole_diameter_in == 0.875
    assert fitting.bolt_circle_in == 9.50
    assert fitting.raised_face_diameter_in == 8.50


def test_slip_on_uses_its_own_hub_length_and_bore():
    fitting = flange("6", 150, "slip-on")
    assert fitting.length_through_hub_in == 1.50
    assert fitting.slip_on_bore_in == 6.72
    assert fitting.slip_on_bore_in > pipe(6).outside_diameter_in


def test_class_300_is_a_larger_flange():
    fitting = flange(6, 300, "wn")
    assert fitting.outside_diameter_in == 12.50
    assert fitting.thickness_in == 1.38
    assert fitting.bolt_circle_in == 10.62
    assert fitting.bolt_count == 12


def test_standard_repad_and_blank_thickness():
    pad = resolve_repad(6, "default", course_thickness_in=0.5)
    assert pad is not None
    assert pad.outer_diameter_in == 15.75
    assert pad.inner_diameter_in == 6.75
    assert pad.thickness_in == 0.5
    assert pad.telltale_diameter_in == 0.25
    assert pad.telltale_offset_in == 1.0
    assert pad.telltale_from_center_in == pytest.approx(15.75 / 2.0 - 1.0)


def test_two_and_a_half_has_no_standard_repad():
    with pytest.raises(ValueError, match="no standard repad"):
        resolve_repad("2-1/2", "default", course_thickness_in=0.5)


def test_tombstone_runs_down_to_the_floor():
    assert tombstone_crown_in(40.0, 15.75) == pytest.approx(40.0 + 15.75 / 2.0)


def test_seam_belongs_to_the_course_above_it():
    spec = _shell()
    number, course, bottom = course_at(spec, 96.0)
    assert number == 2
    assert course.thickness_in == 0.375
    assert bottom == 96.0
    assert course_at(spec, 0.0)[0] == 1
    assert course_at(spec, 192.0)[0] == 2
    with pytest.raises(ValueError, match="above the shell"):
        course_at(spec, 192.1)


def test_radial_nozzle_points_out_on_z_at_rotation_zero():
    placed = place(
        Nozzle("N1", 6, elevation_in=48.0, outside_projection_in=8.0, inside_projection_in=4.0),
        _shell(),
    )
    assert placed.course_number == 1
    assert placed.outside_radius_in == pytest.approx(100.0)
    assert placed.inside_radius_in == pytest.approx(99.5)
    assert placed.shell_in == pytest.approx((0.0, 48.0, 100.0))
    assert placed.face_in == pytest.approx((0.0, 48.0, 108.0))
    # ISP is from the shell inside (99.5), OSP from the shell outside (100).
    assert placed.inner_end_in == pytest.approx((0.0, 48.0, 95.5))
    assert placed.inside_projection_in == pytest.approx(4.5)
    assert placed.wall_in == pytest.approx(0.5)
    assert placed.hub_end_in[2] == pytest.approx(108.0 - placed.flange.face_to_hub_end_in)
    assert placed.axis == pytest.approx((0.0, 0.0, 1.0))
    assert placed.pipe.schedule == "XS"
    assert placed.repad is None


def test_quarter_turn_points_toward_negative_x():
    placed = place(Nozzle("N2", 6, elevation_in=10.0, rotation_deg=90.0), _shell())
    assert placed.shell_in == pytest.approx((-100.0, 10.0, 0.0))
    assert placed.axis == pytest.approx((-1.0, 0.0, 0.0))


def test_positive_offset_is_the_clockwise_side():
    placed = place(
        Nozzle("N3", 6, elevation_in=10.0, offset_in=60.0, outside_projection_in=8.0),
        _shell(),
    )
    assert placed.shell_in == pytest.approx((60.0, 10.0, 80.0))
    assert math.hypot(placed.shell_in[0], placed.shell_in[2]) == pytest.approx(100.0)
    assert placed.chord_in == 0.0
    assert placed.face_in[2] == pytest.approx(80.0 + 8.0)


def test_inside_projection_starts_where_an_offset_centerline_leaves_the_shell():
    placed = place(
        Nozzle("N3", 6, elevation_in=10.0, offset_in=60.0, outside_projection_in=8.0, inside_projection_in=4.0),
        _shell(),
    )
    # The centerline crosses the 0.5 in wall on a slant, so it is longer than 0.5 there.
    inside_surface = math.sqrt(99.5 * 99.5 - 60.0 * 60.0)
    assert placed.wall_in == pytest.approx(80.0 - inside_surface)
    assert placed.inner_end_in[2] == pytest.approx(inside_surface - 4.0)
    with pytest.raises(ValueError, match="does not reach the inside"):
        place(Nozzle("N5", 6, elevation_in=10.0, offset_in=99.7), _shell())


def test_plane_match_moves_the_face_out_and_the_inner_end_back():
    outside, inside, chord = projections(10.0, 30.0, 100.0, 60.0, True)
    assert chord == pytest.approx(20.0)
    assert outside == pytest.approx(30.0)
    assert inside == pytest.approx(10.0)
    with pytest.raises(ValueError, match="Plane match"):
        projections(10.0, 6.0, 100.0, 60.0, True)

    placed = place(
        Nozzle(
            "N4",
            6,
            elevation_in=10.0,
            offset_in=60.0,
            outside_projection_in=10.0,
            inside_projection_in=30.0,
            match_plane=True,
            repad_mode="default",
        ),
        _shell(),
    )
    assert placed.outside_projection_in == pytest.approx(30.0)
    assert placed.inside_projection_in == pytest.approx(10.5)
    # Same planes as a radial nozzle with the typed 10 in outside and 30 in inside projections:
    # face 10 out from the outside (100), inner end 30 in from the inside (99.5).
    assert placed.face_in[2] == pytest.approx(110.0)
    assert placed.inner_end_in[2] == pytest.approx(69.5)
    assert placed.repad is not None
    assert placed.repad.thickness_in == 0.5
