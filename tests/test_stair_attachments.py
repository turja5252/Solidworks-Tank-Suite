"""The attachment rules: knee braces and inner clips per stringer piece off the seams, the ground clip, posts and
rail splits, and the drag-and-drop checks."""

import dataclasses
import math

import pytest

from swauto.stair.attachments import (
    CLIP,
    INNER,
    KNEE,
    OUTER,
    POST,
    RAIL_SPLIT,
    SPLICE,
    Plan,
    Rules,
    Shell,
    Spot,
    check,
    plan,
    rail_step_in,
)
from swauto.stair.landings import StairArrangement
from swauto.stair.splitter import SplitSettings
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import StringerMock
from swauto.stretchout.checks import clearance
from swauto.stretchout.model import build_stretchout
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import Course, TankSpec


def _tank() -> TankSpec:
    return TankSpec(diameter_in=600.0, diameter_basis="od", courses=[Course(96.0, 1.0)] + [Course(96.0, 0.5)] * 4)


def _arrangement(turn_deg: float = 30.0, **more) -> StairArrangement:
    tank = _tank()
    od = course_radii_m(tank, tank.active_courses()[0])[0] / 0.0254
    stair = StringerMock(shell_od_in=od, gap_in=8.0, treads=65, rise_in=480.0 / 65, run_in=10.5)
    return StairArrangement(stair, turn=math.radians(turn_deg), splits=SplitSettings(), **more)


SHELL = Shell.of(build_stretchout(_tank()))


def _pieces(cuts, n):
    edges = [0, *cuts, n]
    return list(zip([a + 1 for a in edges], edges[1:], strict=False))


def test_each_stringer_piece_gets_one_knee_brace_and_one_clip_near_its_middle():
    result = plan(_arrangement(), SHELL)
    assert result.cuts == (13, 26, 39, 52)
    for low, high in _pieces(result.cuts, 65):
        for kind in (KNEE, CLIP):
            inside = [s.tread for s in result.of_kind(kind) if low <= s.tread <= high and s.tread > 1]
            assert len(inside) == 1, (kind, low, high)
            assert abs(inside[0] - (low + high) / 2.0) <= 3
            assert inside[0] - 1 not in result.cuts and inside[0] not in result.cuts  # never beside a cut


def test_the_first_piece_gets_an_extra_clip_at_the_foot():
    result = plan(_arrangement(), SHELL)
    assert 1 in [s.tread for s in result.of_kind(CLIP)]
    assert 1 not in [s.tread for s in plan(_arrangement(), SHELL, Rules(ground_clip=False)).of_kind(CLIP)]


@pytest.mark.parametrize("turn_deg", range(0, 360, 15))
def test_every_pad_keeps_off_the_seams_wherever_the_stair_stands(turn_deg):
    arrangement = _arrangement(turn_deg)
    result = plan(arrangement, SHELL)
    for kind in (KNEE, CLIP):
        pans = tuple(s.tread for s in result.of_kind(kind))
        shown = dataclasses.replace(arrangement, braces=pans, knees=kind == KNEE, inner_clips=kind == CLIP)
        out = build_stretchout(_tank(), stair=shown)
        pads = [item for item in out.items if item.lands]
        assert len(pads) == len(pans)
        for pad in pads:
            gap, seam = clearance(pad, out)
            assert gap >= 1.0 - 1e-6, (pad.label, seam, gap)
            assert pad.box[1] >= 1.0 - 1e-6  # off the floor weld too


def test_a_pad_on_a_seam_moves_off_the_middle():
    # Somewhere round the tank the middle tread's pad must land on a seam; the planner then picks another.
    moved = 0
    for turn_deg in range(0, 360, 5):
        result = plan(_arrangement(turn_deg), SHELL)
        middles = {(low + high) // 2 for low, high in _pieces(result.cuts, 65)} | {
            (low + high + 1) // 2 for low, high in _pieces(result.cuts, 65)}
        moved += any(s.tread not in middles and s.tread != 1 for s in result.spots if s.kind in (KNEE, CLIP))
    assert moved > 0


def test_without_a_tank_only_the_floor_is_checked():
    result = plan(_arrangement())
    assert result.warnings[0].startswith("No tank")
    assert len(result.of_kind(KNEE)) == 5


def test_posts_stand_at_the_bottom_top_and_every_four_gaps_off_cuts_and_braces():
    result = plan(_arrangement(), SHELL, Rules(sides=(OUTER, INNER)))
    braces = {s.tread for s in result.of_kind(KNEE)}
    clips = {s.tread for s in result.of_kind(CLIP)}
    for side in (OUTER, INNER):
        posts = sorted(s.tread for s in result.of_kind(POST, side))
        assert posts[0] in (2, 3) and posts[-1] == 65
        assert max(b - a for a, b in zip(posts, posts[1:], strict=False)) <= 6
        for t in posts:
            assert t - 1 not in result.cuts
            assert not {t - 1, t} & braces
            if side == INNER:
                assert t - 1 not in clips
    assert sorted(s.tread for s in result.of_kind(POST, INNER))[0] == 3  # the ground clip at tread 1


def test_rails_are_split_mid_bay_within_their_stock_length():
    arrangement = _arrangement()
    result = plan(arrangement, SHELL, Rules(sides=(OUTER, INNER)))
    where = stair_places(arrangement.stair, arrangement.stair.shell_od_in)
    for side, stock_ft in ((OUTER, 40.0), (INNER, 20.0)):
        posts = sorted(s.tread for s in result.of_kind(POST, side))
        splits = sorted(s.tread for s in result.of_kind(RAIL_SPLIT, side))
        assert splits and set(splits) <= set(posts)
        ends = [posts[0]] + [(t + posts[posts.index(t) + 1]) / 2.0 for t in splits] + [posts[-1]]
        step = rail_step_in(where, side)
        assert max(b - a for a, b in zip(ends, ends[1:], strict=False)) * step <= stock_ft * 12.0 + 1e-6


def test_pins_stay_and_the_rest_reflow():
    arrangement = _arrangement()
    pinned = plan(arrangement, SHELL, pins=(Spot(SPLICE, 0, 20), Spot(KNEE, 0, 10)))
    assert pinned.cuts == (20,)
    knees = pinned.of_kind(KNEE)
    assert any(s.tread == 10 and s.pinned for s in knees)
    assert len([s for s in knees if 1 <= s.tread <= 20]) == 1  # the pinned one serves its piece
    assert len([s for s in knees if 21 <= s.tread <= 65]) == 1
    posts = [s.tread for s in plan(arrangement, SHELL, pins=(Spot(POST, 0, 5, OUTER),)).of_kind(POST, OUTER)]
    assert 5 in posts and 6 not in posts and posts[0] == 2 and posts[-1] == 65  # the pin stands in for post 6


def test_removed_items_stay_out():
    arrangement = _arrangement()
    full = plan(arrangement, SHELL)
    knee = full.of_kind(KNEE)[1]
    post = full.of_kind(POST, OUTER)[2]
    less = plan(arrangement, SHELL, removed=(knee.key(), post.key(), (SPLICE, 0, 26, "")))
    assert 26 not in less.cuts and len(less.cuts) == 3
    assert post.tread not in [s.tread for s in less.of_kind(POST, OUTER)]
    assert len(less.of_kind(KNEE)) == len(full.of_kind(KNEE)) - 2  # the thrown one, and one piece fewer


def test_the_game_checks_say_why():
    arrangement = _arrangement()
    current = plan(arrangement, SHELL)
    assert check(arrangement, current, Spot(SPLICE, 0, 1), SHELL) == (
        False, "Not in a flight's first or last tread gap: the end clips are there.")
    assert check(arrangement, current, Spot(POST, 0, 1, OUTER), SHELL)[0] is False
    ok, reason = check(arrangement, current, Spot(POST, 0, 14, OUTER), SHELL)
    assert not ok and "cut" in reason
    knee = current.of_kind(KNEE)[0]
    assert check(arrangement, current, knee, SHELL)[0] is True  # where the rules put it
    ok, reason = check(arrangement, current, Spot(KNEE, 0, 14), SHELL)
    assert not ok and "beside a stringer cut" in reason
    ok, reason = check(arrangement, current, Spot(KNEE, 0, 2), SHELL)
    assert not ok and "floor" in reason
    assert check(arrangement, Plan((), ()), Spot(RAIL_SPLIT, 0, 4, OUTER), SHELL)[0] is False


def test_removing_brace_10_leaves_brace_100_alone():
    from swauto.stair.brace_sw import brace_feature

    assert brace_feature("EliteBrace10", 10) and brace_feature("EliteBrace10Knee angle", 10)
    assert brace_feature("EliteBrace10Inner", 10) and brace_feature("EliteBrace05", 5)
    assert not brace_feature("EliteBrace100", 10) and not brace_feature("EliteBrace105Knee", 10)
    assert not brace_feature("EliteBrace1", 10)


def test_pins_off_a_smaller_stair_are_dropped():
    result = plan(_arrangement(), SHELL, pins=(Spot(KNEE, 0, 90), Spot(POST, 3, 5, OUTER)))
    assert not any(s.pinned for s in result.spots)


def test_pinned_clips_keep_the_reflowed_cuts_off():
    result = plan(_arrangement(), SHELL, pins=(Spot(CLIP, 0, 11), Spot(POST, 0, 13, OUTER)))
    assert not any("beside a stringer cut" in w for w in result.warnings)
    assert not {10, 11} & set(result.cuts)


def test_inner_clips_off_means_no_foot_clip_either():
    arrangement = _arrangement(inner_clips=False)
    result = plan(arrangement, SHELL)
    assert result.of_kind(CLIP) == []
    from swauto.stair.attachments import applied

    assert applied(arrangement, result).inner_clips is False


def test_a_pinned_rail_split_whose_post_is_gone_is_dropped():
    result = plan(_arrangement(), SHELL, pins=(Spot(RAIL_SPLIT, 0, 30, OUTER),),
                  removed=((POST, 0, 30, OUTER),))
    assert 30 not in [s.tread for s in result.of_kind(POST, OUTER)]
    assert 30 not in [s.tread for s in result.of_kind(RAIL_SPLIT, OUTER)]


def test_the_knee_brace_keeps_off_the_flights_end_posts_when_it_can():
    tank = _tank()
    od = course_radii_m(tank, tank.active_courses()[0])[0] / 0.0254
    stair = StringerMock(shell_od_in=od, gap_in=8.0, treads=8, rise_in=7.5, run_in=10.5)
    result = plan(StairArrangement(stair, turn=math.radians(30)), Shell.of(build_stretchout(tank)))
    posts = [s.tread for s in result.of_kind(POST, OUTER)]
    assert posts[-1] == 8 and not any("cross brace" in w for w in result.warnings)
