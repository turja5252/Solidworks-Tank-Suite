"""The inside handrail like the outside (the user, 2026-10-30): the outer rails' pieces mirrored onto the inner
stringer and each platform's channel C."""

import math
from dataclasses import replace

import pytest

from swauto.stair import rail_sw as r
from swauto.stair.grab_sw import GrabRail
from swauto.stair.platform_sw import _radial, platform_lines
from swauto.stair.post_sw import LEG_IN, THK_IN, platform_post_frame
from swauto.stair.rail_split_sw import gap_radii
from swauto.stair.stair_sw import InnerRail, stair_places
from swauto.stair.stringer import CLEAR_IN, THICKNESS_IN, PlatformSpec, StringerMock


def _stair(spec=PlatformSpec(96.0)):
    stair = replace(StringerMock(treads=13), platform_specs=(spec,))
    where = stair_places(stair, stair.shell_od_in, 1)
    r_a = where.layout.inner_face_in
    return where, r_a, r_a + where.layout.clear_in


def _plan_r(point) -> float:
    return math.hypot(point[0], point[2])


def test_the_inside_rails_run_over_the_inner_stringers_tank_face():
    where, r_a, r_b = _stair()
    face_r, flights = r._rails_on(where.places, where.per_flight, r_a, r_b, (), 42.0, None, inner=True)
    assert face_r == pytest.approx(r_a - THICKNESS_IN)
    assert all(flight.side == -1.0 and flight.r_b == r_a for flight in flights)
    outer_r, outer = r._rails_on(where.places, where.per_flight, r_a, r_b, (), 42.0, None, inner=False)
    assert outer_r == pytest.approx(r_b + THICKNESS_IN)
    assert all(flight.side == 1.0 for flight in outer)
    # Each side climbs over its own stringer's top edge: the same rise a turn, from its own tread fronts.
    assert flights[0].rise_per_rad == pytest.approx(outer[0].rise_per_rad)
    assert flights[0].front(flights[0].first) < outer[0].front(outer[0].first)


@pytest.mark.parametrize("spec", [PlatformSpec(96.0), PlatformSpec()])
def test_an_inside_end_post_stands_on_channel_c_its_outstanding_leg_toward_the_shell(spec):
    where, r_a, r_b = _stair(spec)
    _face_r, flights = r._rails_on(where.places, where.per_flight, r_a, r_b, (spec,), 42.0, None, inner=True)
    lines = platform_lines(phi=flights[0].last.phi, tread_top=flights[0].last.y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                           spec=spec)
    for side in ("A", "B"):
        post = r._post(flights[0], r_a, r_a + CLEAR_IN, 4.0, side)
        assert post.way == -1.0
        heel = post.world(0.0, 0.0, 0.0)
        if lines.rolled:  # on C's concave back, stood off by the flat leg's sag
            assert _plan_r(heel) == pytest.approx(lines.r_in - LEG_IN * LEG_IN / (2.0 * lines.r_in) - 0.001)
            assert lines.r_in * abs(post.mid - (lines.phi_a if side == "A" else lines.phi_b)) == pytest.approx(4.0)
        else:  # on C's straight back, 4 in in from its end
            half = (lines.phi_b - lines.phi_a) / 2.0
            assert post.web_r == pytest.approx(lines.r_in * math.cos(half))
            assert abs(post.heel_t) == pytest.approx(lines.r_in * math.sin(half) - 4.0)


def test_the_outer_posts_frame_is_unchanged():
    where, r_a, _r_b = _stair()
    lines = platform_lines(phi=where.places[6].phi, tread_top=where.places[6].y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                           spec=PlatformSpec(96.0))
    angle, web_r, heel_t = platform_post_frame(lines, "A", None, 4.0)
    assert (angle, web_r, heel_t) == (lines.phi_a + 4.0 / lines.r_out, lines.r_out, 0.0)


def test_off_the_walk_is_toward_the_tank_on_the_inside():
    along = (1.0, 0.0, 0.0)
    out_side = r._outward(along, 0.0)
    in_side = r._outward(along, 0.0, -1.0)
    assert out_side[2] > 0 > in_side[2]  # at angle 0 the radial is +Z
    assert in_side == tuple(-v for v in out_side)


def test_an_inside_level_piece_runs_from_its_miter_to_the_post_on_c():
    where, r_a, r_b = _stair()
    pb = r_a + CLEAR_IN
    face_r, flights = r._rails_on(where.places, where.per_flight, r_a, r_b, (PlatformSpec(96.0),), 42.0, None, True)
    joint, normal = r._joint(flights[0], flights[1], face_r, r_a, pb, 4.0, "A")
    assert _plan_r(joint) == pytest.approx(face_r)
    assert joint[1] == pytest.approx(flights[0].last.y1 + 42.0)
    post = r._post(flights[0], r_a, pb, 4.0, "A")
    to_post = r._unit(tuple(post.world(0.0, 0.0, joint[1])[i] - joint[i] for i in range(3)))
    assert sum(normal[i] * to_post[i] for i in range(3)) > 0.5  # the miter faces the level piece's run


def test_the_inside_splice_gap_is_cut_across_the_rails_toward_the_tank():
    assert gap_radii(100.0) == (99.5, 100.0 + LEG_IN)
    low, high = gap_radii(100.0, -1.0)
    assert (low, high) == (100.0 - LEG_IN, 100.5)
    assert low < 100.0 - (LEG_IN - THK_IN)  # past the inside top leg's edge


def test_the_inside_pipe_is_stwes_or_the_full_guardrails_grab_rail():
    assert InnerRail().full
    assert InnerRail().pipe_top is None
    assert InnerRail(grab=GrabRail(top=35.0)).pipe_top == 35.0
    assert InnerRail(full=False, top=33.0).pipe_top == 33.0


def test_the_inside_toe_plate_and_rail_hug_channel_c_on_its_walk_side():
    where, r_a, _r_b = _stair(PlatformSpec())
    lines = platform_lines(phi=where.places[6].phi, tread_top=where.places[6].y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                           spec=PlatformSpec())
    mid, run = r._outer_run(lines, inner=True)
    half = (lines.phi_b - lines.phi_a) / 2.0
    point = run(0.0, 0.0, 0.0)
    assert sum(point[i] * _radial(mid)[i] for i in range(3)) == pytest.approx(lines.r_in * math.cos(half))


@pytest.mark.parametrize("spec", [PlatformSpec(96.0), PlatformSpec()])
def test_an_inside_level_piece_clears_the_end_piece_along_c(spec):
    # Between the flight and the post a straight level piece bows toward the tank: outside, away from the end
    # piece's leg along D; inside, into the end piece's leg along C, so there it runs to the walk side of the heel.
    from swauto.stair.post_sw import LEG_IN as LEG

    where, r_a, r_b = _stair(spec)
    pb = r_a + CLEAR_IN
    for inner in (True, False):
        face_r, flights = r._rails_on(where.places, where.per_flight, r_a, r_b, (spec,), 42.0, None, inner)
        for side, (below, above) in (("A", (flights[0], flights[1])), ("B", (flights[0], flights[1]))):
            post = r._post(below, r_a, pb, 4.0, side)
            for tops in ((), (24.0, below.flight_mid)):  # the top rail's level piece, the midrail's
                joint, _normal = r._joint(below, above, face_r, r_a, pb, 4.0, side, *tops)
                aim = r._aim(post, joint, joint[1])
                if not inner:
                    assert aim == post.world(0.0, 0.0, joint[1])
                    continue
                radial, travel = _radial(post.mid), r._travel(post.mid)

                def frame(p, post=post, radial=radial, travel=travel):
                    return (sum(p[i] * radial[i] for i in range(3)) - post.web_r,
                            sum(p[i] * travel[i] for i in range(3)) - post.heel_t)

                (n0, t0), (n1, t1) = frame(joint), frame(aim)
                assert n0 < 0.0 < n1  # from the tank side of C's back to just off it on the walk side
                for k in range(11):  # along the end piece's leg, from the heel to its far edge, the line is off it
                    t = post.away * LEG * k / 10.0
                    assert n1 + (n0 - n1) * (t - t1) / (t0 - t1) >= -1e-9


def test_an_inside_connector_stands_off_the_rails_by_its_flat_legs_sag():
    from swauto.stair.rail_split_sw import connector_heel

    assert connector_heel(164.0) == 164.0
    heel = connector_heel(128.0, -1.0)
    assert 128.0 - heel == pytest.approx(LEG_IN * LEG_IN / 256.0 + 0.001)
    assert math.hypot(heel, LEG_IN) < 128.0  # the leg's far edge still clears the rails' concave face


def test_the_inside_platform_posts_keep_clear_of_the_shell_clips_tabs():
    from swauto.stair.platform_sw import SHELL_CLIP_THK_IN, TAB_FROM_END_IN, TAB_THK_IN
    from swauto.stair.post_sw import INNER_POST_IN_MIN, check_inner_post_in

    assert INNER_POST_IN_MIN > TAB_FROM_END_IN + TAB_THK_IN + SHELL_CLIP_THK_IN  # past the tab and its clip
    assert check_inner_post_in(4.0) == 4.0
    assert check_inner_post_in(0.5, inner=False) == 0.5  # outside there is nothing at D's ends
    with pytest.raises(ValueError, match="shell clips"):
        check_inner_post_in(0.5)
