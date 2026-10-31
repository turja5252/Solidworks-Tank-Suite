"""The rails' heights, the user's to set (2026-10-30: "adjustable in the Stair game, make it easy"): what they are,
and that the one-part build, the parts build and the Stair game all take them."""

import pytest

from swauto.stair import rail_sw as r
from swauto.stair.development import develop_both
from swauto.stair.game import lane_rails, post_top
from swauto.stair.heights import RailHeights, snap
from swauto.stair.parts_build import StairParts, jobs
from swauto.stair.post_sw import TOP_GAP_IN
from swauto.stair.rail_parts import post_spots
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import PlatformSpec, StringerMock

STAIR = StringerMock(treads=13, platform_specs=(PlatformSpec(96.0),))


def test_the_defaults_are_the_lisps_and_the_flights_midrail_follows_the_top_rail():
    heights = RailHeights()
    assert (heights.top, heights.flight_mid, heights.platform_mid, heights.grab, heights.inner) == (42, 21, 24, 34, 34)
    assert RailHeights(top=45.0).flight_mid == 22.5 and RailHeights(top=45.0, mid=20.0).flight_mid == 20.0
    for wrong in (RailHeights(top=61.0), RailHeights(mid=40.0), RailHeights(grab=41.0), RailHeights(inner=10.0)):
        with pytest.raises(ValueError):
            wrong.validate()
    assert (snap(42.13), snap(42.124), snap(41.9)) == (42.25, 42.0, 42.0)


def test_each_flight_carries_the_heights_its_rails_and_joints_are_built_to():
    where = stair_places(STAIR, STAIR.shell_od_in, 1)
    plain = r._flights(where.places, where.per_flight, 160.0)
    high = r._flights(where.places, where.per_flight, 160.0, (), 45.0, None)
    for a, b in zip(plain, high, strict=True):
        assert b.top(a.first.phi) - a.top(a.first.phi) == pytest.approx(3.0)
        assert (b.rail_top, b.flight_mid) == (45.0, 22.5)
    with pytest.raises(ValueError, match="platform midrail"):
        r.check_platform_mid_top(24.0, 35.0)  # the end pieces would not take both bolts under so low a rail


def test_the_parts_build_takes_the_heights_and_gives_the_pieces_they_shape_their_own_files():
    def parts(**more):
        return StairParts(STAIR, STAIR.shell_od_in, 0.1875, platforms=1, posts=(2, 4, 6), top_rail=True,
                          mid_rail=True, **more)

    plain, high = parts(), parts(rail_top=45.0, flight_mid=20.0)
    rails = high.rails()
    assert (rails.rail_top, rails.flights[0].rail_top, rails.flights[0].flight_mid) == (45.0, 45.0, 20.0)
    assert high.rail_params()["rail_top"] == 45.0 and high.rail_params()["flight_mid"] == 20.0
    spot = post_spots(rails, 1)[0]
    assert spot.ys[1] == pytest.approx(rails.tread_top(1) + 45.0 - TOP_GAP_IN)
    assert high.flight_posts()[0].top(0.0) - plain.flight_posts()[0].top(0.0) == pytest.approx(3.0)
    files = {job.label: job.fingerprint for job in jobs(plain, "L2x2", "C4x5.4", "L3x3", "L6x6")}
    moved = {job.label: job.fingerprint for job in jobs(high, "L2x2", "C4x5.4", "L3x3", "L6x6")}
    for label in ("Flight post", "Flight 1 top rail", "Flight 1 midrail"):
        assert files[label] != moved[label]
    assert files["Tread"] == moved["Tread"]  # what the heights do not shape keeps its file


def test_the_game_draws_the_rails_and_posts_at_the_heights():
    dev = develop_both(STAIR)[1]
    posts = (2, 4, 6)
    plain = {rail.name: rail for rail in lane_rails(dev, "outer", posts)}
    high = {rail.name: rail for rail in lane_rails(dev, "outer", posts, heights=RailHeights(top=45.0, mid=20.0))}
    assert high["Top rail"].y0 - plain["Top rail"].y0 == pytest.approx(3.0)
    assert high["Midrail"].y0 - plain["Midrail"].y0 == pytest.approx(-1.0)
    assert post_top(dev, "outer", 10.0, RailHeights(top=45.0)) - post_top(dev, "outer", 10.0) == pytest.approx(3.0)
