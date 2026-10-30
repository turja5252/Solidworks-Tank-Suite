"""Handrail split connectors (2026-10-30): flat on the rails' outside, their ends cut parallel to the rails."""

import math

import pytest

from swauto.stair.platform_sw import _radial
from swauto.stair.post_sw import RAIL_TOP_IN, THK_IN, TOP_GAP_IN
from swauto.stair.grab_sw import PIPE_OD_IN, PIPE_WALL_IN
from swauto.stair.rail_split_sw import (
    FOOT_UP_IN,
    PIPE_GAP_IN,
    ROUND_BAR_CHAMFER_IN,
    ROUND_BAR_DIA_IN,
    ROUND_BAR_IN,
    connector_ends,
    round_bar_section,
)
from swauto.stair.rail_sw import ANGLE_SECTION, BAR_SECTION, MID_TOP_IN, _flights
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import THICKNESS_IN, StringerMock


def _split():
    where = stair_places(StringerMock(treads=12), StringerMock().shell_od_in)
    r_b = where.layout.inner_face_in + where.layout.clear_in
    flight = _flights(where.places, where.per_flight, r_b)[0]
    phi = (where.places[3].phi + where.places[5].phi) / 2.0
    face_r = r_b + THICKNESS_IN
    return flight, phi, face_r, 1.0 / math.cos(math.atan(flight.rise_per_rad / face_r))


def test_a_connector_runs_from_just_short_of_the_midrails_bottom_to_the_posts_gap_under_the_top_rail():
    flight, phi, face_r, stretch = _split()
    top, foot, _up = connector_ends(flight, phi, face_r)
    # The rails' sections as the sweep draws them: stretched up by 1/cos of the slope.
    mid_bottom = flight.top(phi) - (RAIL_TOP_IN - MID_TOP_IN) + min(up for _out, up, _r in BAR_SECTION) * stretch
    assert foot == pytest.approx(mid_bottom + FOOT_UP_IN * stretch)  # 1/4 in short of it, square to the rails
    assert top == pytest.approx(flight.top(phi) - TOP_GAP_IN * stretch)  # 3/4 in under, as the posts stop
    under_root = flight.top(phi) - (THK_IN + next(r for out, _up, r in ANGLE_SECTION if out == 0.0 and r)) * stretch
    assert top < under_root  # clear of the top rail's top leg and its root fillet


def test_the_round_bar_runs_mostly_into_the_upper_pipe_across_the_gap_and_leads_in_at_its_upper_end():
    section = round_bar_section()
    along = [a for a, _off in section]
    assert max(along) - min(along) == pytest.approx(ROUND_BAR_IN)
    in_upper, in_lower = max(along) - PIPE_GAP_IN / 2.0, -PIPE_GAP_IN / 2.0 - min(along)
    assert in_upper / (in_upper + in_lower) == pytest.approx(0.7)  # 70% of what is inside, in the upper pipe
    assert max(off for _a, off in section) * 2.0 < PIPE_OD_IN - 2.0 * PIPE_WALL_IN  # it fits the bore
    # Square at the lower end; at the upper the corner is cut back as far along as in: 45 degrees.
    lower = [off for a, off in section if a == pytest.approx(min(along))]
    upper_corner = [(a, off) for a, off in section if 0.0 < off and a > 0.0]
    assert max(lower) == pytest.approx(ROUND_BAR_DIA_IN / 2.0)
    (a0, r0), (a1, r1) = sorted(upper_corner)
    assert a1 - a0 == pytest.approx(r0 - r1) == pytest.approx(ROUND_BAR_CHAMFER_IN)


def test_a_connectors_ends_are_cut_parallel_to_the_rails():
    flight, phi, face_r, _stretch = _split()
    _top, _foot, up = connector_ends(flight, phi, face_r)
    along = flight.tangent(phi, face_r)
    assert math.hypot(*up) == pytest.approx(1.0)
    assert up[1] > 0.0
    assert sum(a * b for a, b in zip(up, along, strict=True)) == pytest.approx(0.0, abs=1e-12)
    assert sum(a * b for a, b in zip(up, _radial(phi), strict=True)) == pytest.approx(0.0, abs=1e-12)
