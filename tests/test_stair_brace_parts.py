"""The braces and inner clips as parts (2026-10-30): one part per piece, modelled at the first tread and placed at
every tread that has it, and the stringers' halves of their bolt holes."""

from dataclasses import replace

import pytest

from swauto.errors import SolidWorksError
from swauto.project.items import Placement
from swauto.stair import brace_sw as b
from swauto.stair.brace_parts import brace_holes, brace_jobs, cap_hole, inner_clip, tread_frame
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import PlatformSpec, StringerMock

STAIR = replace(StringerMock(treads=13), platform_specs=(PlatformSpec(96.0),))
WHERE = stair_places(STAIR, STAIR.shell_od_in, 1, 0.0)


class Job:
    def __init__(self, family, label, params, build, placements):
        self.family, self.label, self.params, self.build, self.placements = family, label, params, build, placements


def placed(placement, point_in):
    t = placement.transform()
    p = [v * 0.0254 for v in point_in]
    return tuple((sum(p[i] * t[i * 3 + j] for i in range(3)) + t[9 + j]) / 0.0254 for j in range(3))


def test_a_treads_brace_frame_is_its_own_numbers():
    place = WHERE.places[4]
    frame = tread_frame(WHERE, place)
    assert frame.phi == place.phi and frame.y_top == pytest.approx(place.y0 - b.DROP_IN)
    assert frame.r_b - frame.r_a == pytest.approx(WHERE.layout.clear_in)


def test_every_brace_piece_is_one_part_turned_and_lifted_to_each_braced_tread():
    built, pads = brace_jobs(Job, WHERE, (3, 5, 10), True, (2, 4), STAIR.shell_od_in, "L3x3", "L4x3", {},
                             lambda dphi=0.0, dy=0.0: Placement(dphi, (0.0, dy, 0.0)))
    labels = {job.label: job for job in built}
    assert sorted(labels) == sorted(["Cross brace", "Cross brace cap in", "Cross brace cap out", "Knee brace",
                                     "Knee brace clip", "Inner clip angle", "Inner clip landing",
                                     "Inner clip shell pad"])
    seat = tread_frame(WHERE, WHERE.places[0])
    point = seat.world(seat.r_b - 3.0, 0.5, seat.y_top - 1.0)
    for placement, index in zip(labels["Cross brace"].placements, (3, 5, 10), strict=True):
        own = tread_frame(WHERE, WHERE.places[index - 1])
        assert placed(placement, point) == pytest.approx(own.world(own.r_b - 3.0, 0.5, own.y_top - 1.0), abs=1e-9)
    assert len(pads) == 3  # each knee's shell pad, for the shared pad part
    assert len(labels["Inner clip shell pad"].placements) == 2


def test_the_caps_and_inner_clips_holes_go_through_the_stringers_too():
    holes = brace_holes(WHERE, (3, 5), (2,), STAIR.shell_od_in)
    assert [index for index, _points, _axis in holes["Out"]] == [3, 5]
    assert [index for index, _points, _axis in holes["In"]] == [3, 5, 2]
    frame = tread_frame(WHERE, WHERE.places[2])
    (point, axis), (_i, points, out_axis) = cap_hole(frame, "Out"), holes["Out"][0]
    assert points == [point] and out_axis == axis == frame.radial
    assert point[0] * axis[0] + point[2] * axis[2] == pytest.approx(frame.r_b)  # on the outer stringer's walk face


def test_no_inner_clip_at_the_top_of_a_flight():
    with pytest.raises(SolidWorksError):
        inner_clip(WHERE, WHERE.per_flight, STAIR.shell_od_in)


def test_the_parts_build_puts_the_braces_in_and_their_holes_in_the_stringers_on_the_first_flight():
    from swauto.stair.parts_build import StairParts, _seat, jobs, stair_items

    parts = StairParts(STAIR, STAIR.shell_od_in, 0.1875, platforms=1, braces=(3, 10), knees=True,
                       inner_clips=(2, 9))
    built = {job.label: job for job in jobs(parts, "", "C4", "L3x3", "L6", "L4x3")}
    for label in ("Cross brace", "Cross brace cap in", "Cross brace cap out", "Knee brace", "Knee brace clip",
                  "Inner clip angle", "Inner clip landing", "Inner clip shell pad"):
        assert label in built
    # The second flight's braced tread 10 carries its holes back onto the first flight, where its stringers are made.
    holes = brace_holes(WHERE, (3, 10), (2, 9), STAIR.shell_od_in)
    dphi, dy = parts.flight_move(1)
    (_index, points, _axis), = [h for h in holes["Out"] if h[0] == 10]
    assert built["Flight 2 outer stringer"].params["braces"] == [[_seat(points[0], dphi, dy)]]
    assert len(built["Flight 2 inner stringer"].params["braces"]) == 2  # tread 10's cap, tread 9's clip
    # The knees' pads are the platform's shell pad piece, placed at theirs too.
    assert len(built["Shell pad"].placements) == 8 + 2
    files = [item.file for item in stair_items(list(built.values()))]
    assert len(files) == len(set(files))
