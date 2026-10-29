"""Stair sizing from the height, as the lisp launcher's Height/Angle input does it."""

import math

import pytest

from swauto.stair.development import flight_treads, stair_plan
from swauto.stair.sizing import (
    auto_treads,
    end_angles,
    orientation_deg,
    placement_turn,
    rise_run,
    slopes_deg,
    stair_height_in,
    tread_lap_in,
    world_angle,
)
from swauto.stair.stringer import StringerMock


def test_the_rise_is_the_height_over_the_treads_and_the_run_follows_the_slope():
    rise, run = rise_run(480.0, 64, math.degrees(math.atan(7.5 / 10.5)))
    assert rise == pytest.approx(7.5)
    assert run == pytest.approx(10.5)


@pytest.mark.parametrize(
    ("height", "treads", "slope"), [(0.0, 8, 35.0), (60.0, 0, 35.0), (60.0, 8, 0.0), (60.0, 8, 89.0)]
)
def test_sizing_needs_a_height_treads_and_a_slope_under_89_degrees(height, treads, slope):
    with pytest.raises(ValueError):
        rise_run(height, treads, slope)


def test_treads_picked_from_the_height_keep_every_rise_at_7_5_in_or_under():
    assert auto_treads(60.0) == 8
    assert auto_treads(480.0) == 64
    assert auto_treads(482.0) == 65
    assert 482.0 / auto_treads(482.0) <= 7.5


def test_treads_picked_with_mid_platforms_split_into_equal_flights():
    for platforms in range(4):
        count = auto_treads(480.0, platforms)
        assert 480.0 / count <= 7.5
        flight_treads(count, platforms)  # equal flights, or it raises
    assert auto_treads(480.0, 1) == 65  # 64 would be flights of 32.5
    assert auto_treads(480.0, 2) == 64


def test_slopes_are_steeper_nearer_the_tank_and_the_centerline_is_the_slope():
    stair = StringerMock(shell_od_in=300.0, gap_in=8.0, treads=40, rise_in=7.5, run_in=10.5)
    slopes = slopes_deg(stair)
    assert slopes["centerline"] == pytest.approx(math.degrees(math.atan(7.5 / 10.5)))
    assert slopes["shell"] > slopes["inner"] > slopes["centerline"] > slopes["outer"]


def test_a_tread_laps_the_next_by_its_depth_less_the_run():
    assert tread_lap_in(10.5) == pytest.approx(10.9375 - 10.5)
    assert tread_lap_in(11.5) < 0  # a gap


def test_the_offsets_move_the_ends_of_the_full_height_down():
    assert stair_height_in(480.0) == 480.0
    assert stair_height_in(480.0, top_offset_in=8.0, bottom_offset_in=6.0) == 478.0  # top down 8, ground down 6
    assert stair_height_in(480.0, bottom_offset_in=-6.0) == 474.0  # ground 6 up from the floor
    with pytest.raises(ValueError):
        stair_height_in(480.0, top_offset_in=480.0)


def _stair(treads: int = 9) -> StringerMock:
    return StringerMock(shell_od_in=300.0, gap_in=8.0, treads=treads, rise_in=7.5, run_in=10.5)


def test_the_ends_are_where_the_stringers_stop():
    foot, top = end_angles(_stair())
    assert 0.0 < foot < 0.1  # just short of tread 1's centerline
    treads, _spans = stair_plan(_stair())
    assert foot < treads[0] and top > treads[-1]
    for platforms, count in ((1, 9), (2, 10)):
        _treads, spans = stair_plan(_stair(count), platforms, top_platform=True)
        assert end_angles(_stair(count), platforms)[1] == pytest.approx(spans[-1][0])  # where a top platform starts


@pytest.mark.parametrize("ccw", [False, True])
@pytest.mark.parametrize("at_top", [False, True])
def test_the_chosen_end_lands_on_the_orientation(ccw, at_top):
    foot, top = end_angles(_stair(), 1)
    turn = placement_turn(185.0, foot, top, at_top=at_top, ccw=ccw)
    assert orientation_deg(world_angle(top if at_top else foot, turn, ccw)) == pytest.approx(185.0)
    climbs = world_angle(top, turn, ccw) - world_angle(foot, turn, ccw)
    assert (climbs < 0) == ccw  # counterclockwise climbs to smaller angles
