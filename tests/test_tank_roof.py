import math

from swauto.tank.roof import (
    RING_ANGLE,
    RING_BAR,
    RoofSpec,
    cone_profile_in,
    cone_point_in,
    flat_outline_in,
    flat_pattern,
    flat_radius_for_plan,
    layout_roof_plates,
    plan_angle_for_flat,
    plan_radius_for_flat,
    ring_profile_in,
    roof_from_tank,
)
from swauto.tank.spec import Course, TankSpec


def test_slope_raises_the_peak_one_inch_per_foot():
    spec = RoofSpec(inside_radius_in=120, outside_radius_in=121, shell_height_in=100, slope_in_per_ft=12, thickness_in=2 * math.sqrt(2))
    assert spec.rise_in() == pytest_approx(120)
    assert spec.peak_height_in() == pytest_approx(220)
    underside_eave, underside_peak, outer_peak, outer_eave = cone_profile_in(spec)
    assert underside_eave == (pytest_approx(120), pytest_approx(100))
    assert underside_peak == (pytest_approx(0), pytest_approx(220))
    assert outer_peak == (pytest_approx(0), pytest_approx(222))
    assert outer_eave == (pytest_approx(122), pytest_approx(102))


def test_flat_roof_offsets_straight_up():
    profile = cone_profile_in(
        RoofSpec(inside_radius_in=100, outside_radius_in=101, shell_height_in=50, slope_in_per_ft=0, thickness_in=0.25)
    )
    assert profile[0] == (pytest_approx(100), pytest_approx(50))
    assert profile[1] == (pytest_approx(0), pytest_approx(50))
    assert profile[2] == (pytest_approx(0), pytest_approx(50.25))
    assert profile[3] == (pytest_approx(100), pytest_approx(50.25))


def test_bearing_is_the_inside_of_the_top_course():
    tank = TankSpec(
        diameter_in=100,
        diameter_basis="mw",
        courses=[Course(48, 1), Course(32, 2)],
    )
    roof = roof_from_tank(tank, slope_in_per_ft=0.75, thickness_in=0.25)
    assert roof.inside_radius_in == pytest_approx(49)
    assert roof.outside_radius_in == pytest_approx(51)
    assert roof.shell_height_in == pytest_approx(80)
    assert roof.landing_radius_in() == pytest_approx(49)
    assert roof.slope_in_per_ft == pytest_approx(0.75)


def test_flat_bar_moves_the_landing_out_onto_the_ring():
    spec = RoofSpec(
        inside_radius_in=100,
        outside_radius_in=101,
        shell_height_in=200,
        slope_in_per_ft=12,
        thickness_in=0.25,
        ring=RING_BAR,
        ring_top_offset_in=0.5,
        landing_inset_in=2,
        bar_width_in=4,
        bar_height_in=0.5,
    )
    assert spec.landing_radius_in() == pytest_approx(103)
    assert spec.landing_height_in() == pytest_approx(200.5)
    assert spec.rise_in() == pytest_approx(103)
    ring = ring_profile_in(spec)
    assert ring[0] == (pytest_approx(101), pytest_approx(200))
    assert ring[1] == (pytest_approx(105), pytest_approx(200))
    assert ring[2] == (pytest_approx(105), pytest_approx(200.5))
    assert cone_profile_in(spec)[0] == (pytest_approx(103), pytest_approx(200.5))


def test_angle_ring_uses_the_same_landing():
    spec = RoofSpec(
        inside_radius_in=100,
        outside_radius_in=102,
        shell_height_in=80,
        ring=RING_ANGLE,
        landing_inset_in=1,
        angle_horizontal_in=3,
        angle_vertical_in=4,
        angle_thickness_in=0.5,
    )
    assert spec.landing_radius_in() == pytest_approx(103)
    ring = ring_profile_in(spec)
    assert ring[0] == (pytest_approx(102), pytest_approx(80))
    assert ring[1] == (pytest_approx(105), pytest_approx(80))
    assert ring[3] == (pytest_approx(102.5), pytest_approx(79.5))
    assert ring[5] == (pytest_approx(102), pytest_approx(76))


def test_zoom_window_opens_the_angle_leg():
    from swauto.tank.roof_gui import _fit_window, _ring_window

    spec = RoofSpec(
        inside_radius_in=100,
        outside_radius_in=102,
        shell_height_in=80,
        ring=RING_ANGLE,
        angle_horizontal_in=3,
        angle_vertical_in=4,
        angle_thickness_in=0.5,
    )
    r0, r1, y0, y1 = _ring_window(spec)
    assert r1 - r0 < 20
    scale, cx, base = _fit_window(r0, r1, y0, y1)
    ring = ring_profile_in(spec)
    toe = cx + ring[1][0] * scale
    heel = cx + ring[0][0] * scale
    assert toe - heel > 40
    assert (base - ring[5][1] * scale) - (base - ring[0][1] * scale) > 40


def test_sloped_roof_flattens_to_the_slant_diameter():
    spec = RoofSpec(
        inside_radius_in=120,
        outside_radius_in=121,
        shell_height_in=100,
        slope_in_per_ft=12,
        thickness_in=1,
        ignore_pie=False,
    )
    pattern = flat_pattern(spec)
    assert pattern.slant_in == pytest_approx(120 * math.sqrt(2))
    assert pattern.diameter_in == pytest_approx(240 * math.sqrt(2))
    assert pattern.sector_deg == pytest_approx(360 / math.sqrt(2))
    assert pattern.diameter_in > 240
    assert pattern.apex_x_in - pattern.slant_in > 121
    outline = flat_outline_in(spec)
    assert outline[0] == (pytest_approx(0), pytest_approx(0))
    assert math.hypot(*outline[1]) == pytest_approx(pattern.slant_in)
    assert flat_radius_for_plan(spec, 120) == pytest_approx(pattern.slant_in)
    assert plan_radius_for_flat(spec, pattern.slant_in) == pytest_approx(120)
    assert plan_angle_for_flat(spec, pattern.sector_rad / 2) == pytest_approx(math.pi)


def test_ignored_pie_lays_plates_on_a_full_circle_and_projects_onto_the_cone():
    spec = RoofSpec(
        inside_radius_in=100,
        outside_radius_in=101,
        shell_height_in=80,
        slope_in_per_ft=0.75,
        thickness_in=0.25,
        ignore_pie=True,
        plate_width_in=80,
        plate_length_in=120,
        plate_lap_in=2,
    )
    plates = layout_roof_plates(spec)
    assert plates
    assert all(math.hypot(*point) <= flat_pattern(spec).slant_in + 1e-6 for plate in plates for point in plate.polygon_in)
    outer = [plate for plate in plates if plate.course == 1]
    assert len(outer) >= 3
    # Wide-edge lap: neighboring outer plates overlap in angle.
    first = _angles(outer[1].polygon_in)
    second = _angles(outer[2].polygon_in)
    assert min(second) < max(first)
    eave = cone_point_in(spec, flat_pattern(spec).slant_in, 0.0)
    assert math.hypot(eave.x_in, eave.z_in) == pytest_approx(100 + (spec.rise_in() / flat_pattern(spec).slant_in) * 0.25)
    assert eave.y_in > spec.shell_height_in


def test_kept_pie_stays_inside_the_sector():
    spec = RoofSpec(
        inside_radius_in=120,
        outside_radius_in=121,
        shell_height_in=100,
        slope_in_per_ft=12,
        thickness_in=0.25,
        ignore_pie=False,
        plate_width_in=96,
        plate_length_in=200,
        plate_lap_in=2,
    )
    sweep = flat_pattern(spec).sector_rad
    plates = layout_roof_plates(spec)
    limit = sweep / 2 + 1e-6
    for plate in plates:
        for x_in, z_in in plate.polygon_in:
            if math.hypot(x_in, z_in) < 1e-6:
                continue
            assert abs(math.atan2(z_in, x_in)) <= limit
    edge = cone_point_in(spec, *plates[0].polygon_in[-1])
    assert edge.z_in != pytest_approx(0)


def _angles(polygon):
    return [math.atan2(z_in, x_in) for x_in, z_in in polygon if math.hypot(x_in, z_in) > 1e-6]


def test_flat_roof_pattern_is_the_plan_circle():
    spec = RoofSpec(inside_radius_in=100, outside_radius_in=101, shell_height_in=50, slope_in_per_ft=0, thickness_in=0.25)
    pattern = flat_pattern(spec)
    assert pattern.diameter_in == pytest_approx(200)
    assert pattern.sector_deg == pytest_approx(360)
    outline = flat_outline_in(spec)
    assert outline[0] != (pytest_approx(0), pytest_approx(0))
    assert all(math.hypot(x, z) == pytest_approx(100) for x, z in outline)


def pytest_approx(value: float):
    class _Approx:
        def __eq__(self, other):
            return math.isclose(other, value, rel_tol=0, abs_tol=1e-6)

        def __repr__(self):
            return f"approx {value}"

    return _Approx()
