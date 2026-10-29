"""Roof nozzles placed on the cone, checked against the lisp's ROOFNOZZLES rules (Roof Nozzle Inserter.lsp)."""

import math

import pytest

from swauto.nozzle.roof_place import (
    AUTO_CLEAR_IN,
    outside_y,
    pad_outline,
    place_on_roof,
    plan_point,
    tombstone_corners,
    underside_y,
)
from swauto.nozzle.roof_spec import DIRECT, RoofNozzle, normalize_projection, read_isp
from swauto.nozzle.shape import inside_flange_loop, stations, weld_neck_loop
from swauto.tank.roof import RoofSpec

# The worked example: landing 600 in (no ring, so the shell inside), 3/4 in per ft, 3/16 in plate.
ROOF = RoofSpec(inside_radius_in=600.0, outside_radius_in=600.5, shell_height_in=480.0, slope_in_per_ft=0.75,
                thickness_in=0.1875)
BEARING = 480.0


def _six(**kw):
    values = {"mark": "R1", "nps": "6", "degree": 90.0, "radial_in": 300.0, "projection_in": 30.0}
    values.update(kw)
    return RoofNozzle(**values)


def test_the_worked_example_from_the_lisp_rules():
    placed = place_on_roof(_six(), ROOF)
    assert placed.underside_in - BEARING == pytest.approx(18.75)
    assert placed.surface_in - BEARING == pytest.approx(18.9379, abs=1e-3)  # t·k above the underside
    assert placed.outside_projection_in == pytest.approx(11.0621, abs=1e-3)
    assert placed.end_in - BEARING == pytest.approx(18.2935, abs=1e-4)  # AUTO: 1/4 in square to the roof
    assert placed.underside_in - placed.end_in == pytest.approx(0.4565, abs=1e-4)
    assert placed.inside_projection_in == pytest.approx(0.6444, abs=1e-3)  # the block's ISP
    assert placed.isp_in == AUTO_CLEAR_IN  # what the schedule prints for AUTO
    assert placed.height_in == pytest.approx(30.0)
    assert placed.location_c_in == pytest.approx(300.5971, abs=1e-3)
    direct = place_on_roof(_six(projection=DIRECT, projection_in=12.0), ROOF)
    assert direct.height_in == pytest.approx(30.9379, abs=1e-3)


def test_the_offset_moves_the_plan_point_clockwise_as_the_lisp_does():
    placed = place_on_roof(_six(degree=45.0, radial_in=300.0, offset_in=10.0), ROOF)
    assert placed.angle_deg == pytest.approx(46.9092, abs=1e-4)
    assert placed.radius_in == pytest.approx(300.1666, abs=1e-4)
    # 0 deg is +Z and the angle grows toward -X, as for a shell nozzle; + offset at 0 deg moves toward -X.
    assert plan_point(0.0, 100.0, 0.0) == pytest.approx((0.0, 100.0))
    assert plan_point(90.0, 100.0, 0.0) == pytest.approx((-100.0, 0.0))
    assert plan_point(0.0, 100.0, 5.0) == pytest.approx((-5.0, 100.0))


def test_the_roof_surfaces_follow_the_modeled_cone():
    assert underside_y(ROOF, 600.0) == pytest.approx(BEARING)
    assert underside_y(ROOF, 0.0) == pytest.approx(BEARING + 37.5)
    k = math.hypot(1.0, 0.0625)
    for r in (0.0, 150.0, 599.0):
        assert outside_y(ROOF, r) - underside_y(ROOF, r) == pytest.approx(0.1875 * k, abs=2e-3)


def test_a_typed_isp_is_measured_down_from_the_underside_and_must_clear_the_low_side():
    placed = place_on_roof(_six(isp_in=6.0), ROOF)
    assert placed.underside_in - placed.end_in == pytest.approx(6.0)
    assert placed.isp_in == 6.0
    with pytest.raises(ValueError, match="low side of the pipe"):
        place_on_roof(_six(isp_in=0.2), ROOF)  # 3/4 in per ft over half of 6.625 in is 0.207 in
    assert read_isp("AUTO") is None and read_isp("") is None and read_isp("0") is None
    assert read_isp(" 4.5 ") == 4.5


def test_the_flange_face_has_to_stand_clear_of_the_roof():
    with pytest.raises(ValueError, match="at or under the roof"):
        place_on_roof(_six(projection_in=18.0), ROOF)  # the roof is 18.94 in over the bearing line there
    with pytest.raises(ValueError, match=r"hub would go into the roof\. The OSP needs to be at least"):
        place_on_roof(_six(projection=DIRECT, projection_in=2.0), ROOF)  # a 6 in weld neck is 3.5 in face to hub
    loop = weld_neck_loop(place_on_roof(_six(projection=DIRECT, projection_in=8.0), ROOF))
    assert max(z for z, _r in loop) == pytest.approx(8.0)


def test_the_pipe_and_a_round_pad_stay_inside_the_roof_landing():
    with pytest.raises(ValueError, match="past the roof landing"):
        place_on_roof(_six(radial_in=597.0), ROOF)
    with pytest.raises(ValueError, match="pad runs past the roof landing"):
        place_on_roof(_six(radial_in=595.0, repad_mode="default"), ROOF)  # 15.75 in pad: out to 602.875 in
    placed = place_on_roof(_six(repad_mode="default"), ROOF)
    assert placed.repad.thickness_in == pytest.approx(0.1875)  # a blank pad thickness is the roof plate


def test_a_roof_tombstone_points_its_round_end_at_the_center_and_runs_out_to_the_landing():
    placed = place_on_roof(_six(degree=0.0, radial_in=560.0, repad_mode="default", repad_style="tombstone"), ROOF)
    feet, tangents = tombstone_corners(placed)
    for x, z in feet:
        assert math.hypot(x, z) == pytest.approx(600.0)
    assert sorted(x for x, _z in tangents) == pytest.approx([-7.875, 7.875])
    outline = pad_outline(placed)
    nearest = min(math.hypot(x, z) for x, z in outline)
    assert nearest == pytest.approx(560.0 - 7.875, abs=1e-6)  # the round end, toward the tank center
    assert max(math.hypot(x, z) for x, z in outline) == pytest.approx(600.0)


def test_an_inside_flange_needs_a_typed_isp_long_enough_for_its_hub_under_the_roof():
    with pytest.raises(ValueError, match="type the ISP"):
        _six(inside_flange="so")
    with pytest.raises(ValueError, match="inside flange's hub would go into the roof"):
        place_on_roof(_six(inside_flange="so", isp_in=1.0), ROOF)
    placed = place_on_roof(_six(inside_flange="so", isp_in=6.0), ROOF)
    loop = inside_flange_loop(placed)
    face = min(z for z, _r in loop)
    assert face == pytest.approx(-placed.inside_projection_in)
    assert placed.underside_in - (placed.surface_in + face) == pytest.approx(6.0)  # ISP runs to the raised face
    assert stations(placed).pipe_z == pytest.approx(face + 0.06)  # a slip-on's pipe stops under its face


def test_projection_labels_from_the_lisp_and_a_direct_osp_must_be_typed():
    assert normalize_projection("Height above bearing / CR") == "height"
    assert normalize_projection(1) == "osp"
    assert normalize_projection("Direct OSP") == "osp"
    with pytest.raises(ValueError, match="direct OSP must be greater than zero"):
        _six(projection=DIRECT, projection_in=0.0)
