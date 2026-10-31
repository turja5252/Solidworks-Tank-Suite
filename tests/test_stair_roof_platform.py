"""The roof platform's plan and heights (item 12, 2026-10-30): TK-701's platform as the example."""

import math

import pytest

from swauto.stair.platform_sw import GRATING_IN
from swauto.stair.roof_platform import (
    MIN_LEG_IN,
    RoofPlatformSpec,
    deck_y,
    legs,
    place,
    post_alongs,
    roof_top_y,
)
from swauto.tank.roof import roof_from_tank
from swauto.tank.spec import Course, TankSpec

# TK-701: a 78 ft tank, the 7 x 10 ft platform at 90 deg, its inner edge 29'-3 3/16" from the tank's centre line.
SHELL_R = 468.0
TK701 = RoofPlatformSpec(angle_deg=90.0, edge_in=SHELL_R - (351.1875 + 84.0))


def _roof():
    tank = TankSpec(diameter_in=2.0 * SHELL_R, diameter_basis="od", courses=[Course(96.0, 0.5)])
    return roof_from_tank(tank, 0.75, 0.1875)


def test_tk701_sits_where_its_drawing_puts_it():
    placed = place(TK701, SHELL_R)
    assert placed.d_in == pytest.approx(351.1875)
    assert placed.d_out == pytest.approx(435.1875)
    ax, az = placed.world(0.0, placed.d_in)  # C's middle, on the 90 deg radial line: toward -X
    assert (ax, az) == pytest.approx((-351.1875, 0.0), abs=1e-9)
    assert placed.extension() == [(23.0, 435.1875), (23.0, 477.0625), (60.0, 477.0625), (60.0, 435.1875)]
    assert placed.farthest_radius() > SHELL_R  # the extension reaches over the roof's edge toward the stair


def test_a_platform_too_long_for_its_place_is_refused():
    with pytest.raises(ValueError, match="past the shell"):
        place(RoofPlatformSpec(length_in=300.0, edge_in=2.0), SHELL_R)
    with pytest.raises(ValueError, match="channel"):
        place(RoofPlatformSpec(channel="C8"), SHELL_R)


def test_legs_go_by_the_lisps_area_rule_and_the_deck_clears_the_cone():
    assert TK701.area_ft2 == pytest.approx((120 * 84 + 37 * 41.875) / 144.0)
    assert TK701.leg_count == 4  # 81 sq ft would be 3; at least two under each of C and D
    assert RoofPlatformSpec(length_in=240.0, width_in=120.0, ext_reach_in=0.0).leg_count == 7
    roof = _roof()
    placed = place(TK701, SHELL_R)
    deck = deck_y(placed, roof)
    assert deck == pytest.approx(roof_top_y(roof, placed.d_in) + MIN_LEG_IN + 4.0 + GRATING_IN)
    standing = legs(placed, roof)
    assert sorted(leg.side for leg in standing) == ["C", "C", "D", "D"]
    for leg in standing:
        assert leg.length_in >= MIN_LEG_IN - 1e-9
        assert abs(leg.along) == pytest.approx(60.0 - 12.0)
    # The cone falls away outward: D's legs are the longer by the slope over the width.
    c_leg = next(leg for leg in standing if leg.side == "C")
    d_leg = next(leg for leg in standing if leg.side == "D")
    slope = 0.75 / 12.0
    rise = (math.hypot(c_leg.along, placed.d_out) - math.hypot(c_leg.along, placed.d_in)) * slope
    assert d_leg.length_in - c_leg.length_in == pytest.approx(rise, rel=1e-3)


def test_posts_stand_6_in_from_the_corners_and_no_more_than_60_apart():
    assert post_alongs(120.0) == [6.0, 60.0, 114.0]
    assert post_alongs(84.0) == [6.0, 42.0, 78.0]
    spots = post_alongs(300.0)
    assert spots[0] == 6.0 and spots[-1] == 294.0
    assert max(b - a for a, b in zip(spots, spots[1:])) <= 60.0
