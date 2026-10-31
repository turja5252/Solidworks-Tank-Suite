"""The outer handrail as parts (2026-10-30): which pieces a stair gets, and the bolt holes each part cuts for the piece
it meets."""

from dataclasses import replace

import pytest

from swauto.stair.parts_build import StairParts, jobs
from swauto.stair.platform_sw import _radial, _travel
from swauto.stair.post_sw import THK_IN
from swauto.stair.rail_parts import channel_holes, end_holes, frame_holes, post_spots
from swauto.stair.stringer import PlatformSpec, StringerMock


def _parts(spec=PlatformSpec(96.0), tread_in=None, platforms=1, **more):
    stair = replace(StringerMock(treads=13 if platforms == 1 else 16), platform_specs=(spec,) * platforms)
    if tread_in is not None:
        stair = replace(stair, tread_in=tread_in)
    options = {"posts": (2, 4, 6), "top_rail": True, "mid_rail": True} | more
    return StairParts(stair, StringerMock().shell_od_in, 0.1875, platforms=platforms, **options)


def _labels(parts):
    families = ("Stair platform post", "Stair toe plate", "Stair top rail", "Stair rail end", "Stair midrail")
    return [job.label for job in jobs(parts, "L2x2", "C4", "L3", "L6") if job.family in families]


def placed(placement, point_in):
    t = placement.transform()
    p = [v * 0.0254 for v in point_in]
    return tuple((sum(p[i] * t[i * 3 + j] for i in range(3)) + t[9 + j]) / 0.0254 for j in range(3))


def test_a_stair_with_a_rolled_platform_gets_every_piece_of_its_outer_handrail():
    assert _labels(_parts()) == [
        "Platform 1 post A", "Platform 1 post B", "Platform 1 post M1", "Platform 1 toe plate",
        "Flight 1 top rail", "Flight 2 top rail", "Platform 1 rail end A", "Platform 1 top rail level A",
        "Platform 1 rail end B", "Platform 1 top rail level B", "Platform 1 top rail",
        "Flight 1 midrail", "Flight 2 midrail", "Platform 1 midrail level A", "Platform 1 midrail level B",
        "Platform 1 midrail", "Foot end",
    ]


def test_a_stair_narrower_than_its_platform_gets_side_posts_and_the_corner_pieces():
    labels = _labels(_parts(tread_in=30.0))
    for label in ("Platform 1 side post A", "Platform 1 side post B", "Platform 1 toe plate A",
                  "Platform 1 toe plate run", "Platform 1 top rail B", "Platform 1 top rail run",
                  "Platform 1 midrail run", "Platform 1 rail end A"):
        assert label in labels
    assert "Platform 1 post A" not in labels  # the end posts are the side posts


def test_without_the_rails_only_the_platform_posts_and_toe_plates_go_on_and_no_post_carries_an_end_piece():
    parts = _parts(top_rail=False, mid_rail=False)
    assert _labels(parts) == ["Platform 1 post A", "Platform 1 post B", "Platform 1 post M1", "Platform 1 toe plate"]
    assert all(end_holes(parts.rails(), spot) is None for spot in post_spots(parts.rails(), 1))


def test_each_post_bolts_through_its_flat_leg_to_the_channel_behind_it():
    rails = _parts().rails()
    for spot in post_spots(rails, 1):
        points, axis = channel_holes(rails, spot)
        assert axis == _radial(spot.phi)
        for p in points:  # on the leg's outer face, a thickness out from the channel's back
            assert p[0] * axis[0] + p[2] * axis[2] == pytest.approx(spot.heel_r + THK_IN)
        assert points[1][1] - points[0][1] == pytest.approx(1.75)


def test_an_end_piece_bolts_to_the_end_post_wherever_a_flight_meets_the_platform():
    rails = _parts(platforms=2, top_platform=True).rails()
    for k in (1, 2, 3):
        met = {spot.label for spot in post_spots(rails, k) if end_holes(rails, spot) is not None}
        assert met == ({"A", "B"} if k < 3 else {"A"})  # no flight leaves the top platform
        for spot in post_spots(rails, k):
            holes = end_holes(rails, spot)
            if holes is not None:
                points, axis = holes
                assert axis == _travel(spot.phi)
                assert points[0][1] - points[1][1] == pytest.approx(11.5)


def test_the_posts_holes_carried_onto_a_platforms_seat_land_back_on_the_real_platform():
    parts = _parts(platforms=2)
    rails = parts.rails()
    for k, _seat, dphi, dy in parts.platform_seats():
        real = frame_holes(rails, k)["D"]
        seated = parts.seat_post_holes(k, dphi, dy)["D"]
        for (points, _axis), (seat_points, _seat_axis) in zip(real, seated, strict=True):
            for p, q in zip(points, seat_points, strict=True):
                assert placed(parts.place(dphi, dy), q) == pytest.approx(p, abs=1e-9)


def test_the_channels_get_the_posts_holes_only_with_the_handrail():
    with_posts = {job.label: job for job in jobs(_parts(), "L2x2", "C4", "L3", "L6")}
    assert len(with_posts["Platform 1 side D"].params["post_holes"]) == 3  # A, B and the one by the radial
    assert with_posts["Platform 1 side C"].params["post_holes"] == []
    bare = {job.label: job for job in jobs(_parts(posts=()), "", "C4", "L3", "L6")}
    assert bare["Platform 1 side D"].params["post_holes"] == []
    narrow = {job.label: job for job in jobs(_parts(tread_in=30.0), "L2x2", "C4", "L3", "L6")}
    assert len(narrow["Platform 1 radial A"].params["post_holes"]) == 1  # the side post on the side channel


def test_the_grab_rail_is_each_flights_pipe_and_caps_and_one_bracket_under_every_post_it_reaches():
    from swauto.stair.grab_sw import GrabRail
    from swauto.stair.rail_parts import bracket_posts

    parts = _parts(grab=GrabRail())
    built = {job.label: job for job in jobs(parts, "L2x2", "C4", "L3", "L6") if job.family.startswith("Stair grab")}
    assert sorted(built) == sorted(["Flight 1 grab rail", "Flight 2 grab rail", "Grab rail bracket"]
                                   + [f"Flight {k} grab rail cap {end}" for k in (1, 2) for end in ("low", "high")])
    posts = parts.flight_posts()
    bracket = built["Grab rail bracket"]
    assert len(bracket.placements) == len(bracket_posts(parts.rails(), GrabRail(), posts)) == 6
    for placement, post in zip(bracket.placements, posts, strict=True):  # each post's bracket, turned and raised
        assert placement.azimuth_rad == pytest.approx(post.phi - posts[0].phi)
        assert placement.at_in[1] == pytest.approx(post.foot - posts[0].foot)


def test_a_spliced_flight_has_a_part_for_each_piece_of_its_rails_and_the_splice_its_connectors_and_bar():
    from swauto.stair.grab_sw import GrabRail
    from swauto.stair.rail_parts import flight_cuts, split_pairs
    from swauto.stair.rail_split_sw import split_angle

    parts = _parts(grab=GrabRail(), rail_splits=(("outer", 9), ("outer", 13), ("inner", 4)))
    posts = parts.flight_posts()
    pairs = split_pairs(parts.rails(), posts, parts.rail_splits)
    assert [(low.index, high.index) for low, high in pairs] == [(9, 11)]  # post 13 is the flight's last; inner later
    assert flight_cuts(parts.rails(), pairs, 1) == [split_angle(*pairs[0])]
    assert flight_cuts(parts.rails(), pairs, 0) == []
    labels = [job.label for job in jobs(parts, "L2x2", "C4", "L3", "L6")]
    for label in ("Flight 2 top rail piece 1 of 2", "Flight 2 top rail piece 2 of 2", "Flight 2 midrail piece 2 of 2",
                  "Flight 2 grab rail piece 1 of 2", "Splice at post 9, low connector",
                  "Splice at post 9, high connector", "Splice at post 9, round bar", "Flight 1 top rail"):
        assert label in labels
    assert "Flight 2 top rail" not in labels


def test_the_inside_full_guardrail_is_the_outsides_pieces_mirrored_onto_c():
    from swauto.stair.stair_sw import InnerRail

    parts = _parts(inner_rail=InnerRail(posts=(2, 4, 6)))
    labels = [job.label for job in jobs(parts, "L2x2", "C4", "L3", "L6")]
    for label in ("Inside flight post", "Platform 1 inside post A", "Platform 1 inside post B",
                  "Platform 1 inside post M1", "Platform 1 inside toe plate", "Flight 1 inside top rail",
                  "Flight 2 inside top rail", "Platform 1 inside rail end A", "Platform 1 inside top rail level B",
                  "Platform 1 inside top rail", "Flight 1 inside midrail", "Platform 1 inside midrail level A",
                  "Platform 1 inside midrail", "Inside foot end"):
        assert label in labels
    assert "Flight 1 inside grab rail" not in labels  # no inside grab rail unless asked
    inner = parts.inner_rails()
    for spot in post_spots(inner, 1):  # on C's tank side, its holes through the flat leg into C
        points, axis = channel_holes(inner, spot)
        assert spot.way == -1.0
        for p in points:
            assert p[0] * axis[0] + p[2] * axis[2] == pytest.approx(spot.heel_r - THK_IN)
    built = {job.label: job for job in jobs(parts, "L2x2", "C4", "L3", "L6")}
    assert len(built["Platform 1 side C"].params["post_holes"]) == 3
    assert len(built["Flight 1 inner stringer"].params["posts"]) == 3  # the inside posts bolt through it
    # Every inside piece has a file of its own: none shares an outside piece's.
    outside = {job.fingerprint for job in jobs(_parts(), "L2x2", "C4", "L3", "L6")}
    for job in jobs(parts, "L2x2", "C4", "L3", "L6"):
        if "nside" in job.label:
            assert job.fingerprint not in outside


def test_the_inside_pipe_handrail_is_only_the_pipe_on_its_posts():
    from swauto.stair.grab_sw import GrabRail
    from swauto.stair.stair_sw import InnerRail

    parts = _parts(inner_rail=InnerRail(posts=(2, 4, 6), full=False), rail_splits=(("inner", 9),))
    labels = [job.label for job in jobs(parts, "L2x2", "C4", "L3", "L6")]
    assert "Inside flight post" in labels and "Inside grab rail bracket" in labels
    assert "Flight 1 inside grab rail" in labels and "Flight 2 inside grab rail piece 2 of 2" in labels
    assert "Inside splice at post 9, round bar" in labels
    assert not any(label.startswith("Platform 1 inside") or "inside top rail" in label for label in labels)
    built = {job.label: job for job in jobs(parts, "L2x2", "C4", "L3", "L6")}
    assert built["Platform 1 side C"].params["post_holes"] == []
    # STWE's pipe runs from each flight's first tread to its top tread: no platform rail stops it.
    from swauto.stair.rail_parts import grab_pipes

    inner = parts.inner_rails()
    for held in grab_pipes(inner, GrabRail(top=34.0), parts.inner_posts()):
        _k, pipe, lo, hi = held
        flight = pipe.flight
        assert lo < flight.front(flight.first) + 0.01 and hi > flight.front(flight.last) - 0.01


def test_on_a_stair_narrower_than_its_platform_the_inside_still_meets_c_at_its_corner():
    from swauto.stair.stair_sw import InnerRail

    labels = [job.label for job in jobs(_parts(tread_in=30.0, inner_rail=InnerRail(posts=(2, 4, 6))),
                                        "L2x2", "C4", "L3", "L6")]
    assert "Platform 1 side post A" in labels  # the outside wraps the corners
    for label in ("Platform 1 inside post A", "Platform 1 inside rail end A", "Platform 1 inside top rail level A",
                  "Platform 1 inside top rail", "Platform 1 inside toe plate"):
        assert label in labels  # the inside does not
    assert not any("inside side post" in label or "inside top rail run" in label for label in labels)


def test_on_a_platform_wider_than_the_stair_the_inside_does_not_wrap_its_corners():
    # A wider platform puts D further out, not C: the outside wraps D's corners, the inside meets C at its corner as
    # ever (it took the outside's corner pieces, and stacked a second set of them on the first; found 2026-10-31).
    from swauto.stair import rail_sw as r
    from swauto.stair.stair_sw import InnerRail, stair_places

    parts = _parts(PlatformSpec(60.0, width_in=48.0, rolled=False), inner_rail=InnerRail(posts=(2, 4, 6)))
    labels = [job.label for job in jobs(parts, "L2x2", "C4", "L3", "L6")]
    assert "Platform 1 side post A" in labels and "Platform 1 top rail run" in labels  # the outside wraps
    for label in ("Platform 1 inside post A", "Platform 1 inside rail end A", "Platform 1 inside top rail level B",
                  "Platform 1 inside top rail", "Platform 1 inside toe plate", "Platform 1 inside midrail level A"):
        assert label in labels
    for label in ("Platform 1 inside side post A", "Platform 1 inside top rail run", "Platform 1 inside toe plate run",
                  "Platform 1 inside midrail run", "Platform 1 inside top rail A"):
        assert label not in labels
    inner = parts.inner_rails()
    assert not inner.wraps(1) and parts.rails().wraps(1)
    assert all(not spot.side for spot in post_spots(inner, 1))
    # And so in the one-part build: the inside flight's joint runs to its post on C, not to the side's corner.
    where = stair_places(parts.stair, parts.shell_od, 1)
    r_a = where.layout.inner_face_in
    face_r, flights = r._rails_on(where.places, where.per_flight, r_a, parts.r_b, parts.stair.platform_specs, 42.0,
                                  None, True)
    assert not r._wraps(flights[0], r._lines_of(flights[0], r_a, r_a + 36.0))
