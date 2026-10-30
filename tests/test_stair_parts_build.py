"""The stair as parts (2026-10-30): each piece's part placed where the one-part build puts that piece."""

import math
from dataclasses import replace

import pytest

from swauto.stair.parts_build import PartJob, StairParts, jobs, platform_jobs, stair_items
from swauto.stair.platform_sw import HOLE_DOWN_IN, _world
from swauto.stair.post_sw import _post_side
from swauto.stair.stringer import PlatformSpec, StringerMock

PARTS = StairParts(StringerMock(treads=13), StringerMock().shell_od_in, 0.1875, platforms=1, posts=(2, 4, 6))


def placed(placement, point_in):
    """Where SolidWorks puts a part's ``point_in`` (inches): row vector times the rotation, then the move."""
    t = placement.transform()
    p = [v * 0.0254 for v in point_in]
    return tuple((sum(p[i] * t[i * 3 + j] for i in range(3)) + t[9 + j]) / 0.0254 for j in range(3))


def _platform_parts(spec, **more):
    stair = replace(StringerMock(treads=13), platform_specs=(spec,))
    return StairParts(stair, StringerMock().shell_od_in, 0.1875, platforms=1, **more)


def _three_platforms(**more):
    """Two mid platforms and a top one, rolled."""
    stair = replace(StringerMock(treads=13), platform_specs=(PlatformSpec(96.0),) * 3)
    return StairParts(stair, StringerMock().shell_od_in, 0.1875, platforms=2, top_platform=True, **more)


def _job(built, label):
    return next(job for job in built if job.label == label)


def test_the_tread_part_lands_on_every_pan_of_every_flight():
    where = PARTS.where
    tread = _job(jobs(PARTS), "Tread")
    first = where.places[0]
    assert len(tread.placements) == len(where.places) == 2 * where.per_flight
    for placement, place in zip(tread.placements, where.places, strict=True):
        assert placed(placement, first.center) == pytest.approx(place.center, abs=1e-9)


def test_the_post_part_lands_on_every_flight_post():
    posts = PARTS.flight_posts()
    job = _job(jobs(PARTS), "Flight post")
    _way, face_r = _post_side(PARTS.r_b, False)
    heel = _world(posts[0].phi, face_r, 0.0, posts[0].foot)  # the seat: the first flight's second tread
    assert len(job.placements) == len(posts) == 6
    for placement, post in zip(job.placements, posts, strict=True):
        assert placed(placement, heel) == pytest.approx(_world(post.phi, face_r, 0.0, post.foot), abs=1e-9)


def test_each_stringer_is_its_own_file_modelled_on_the_first_flight_and_moved_onto_its_own():
    where = PARTS.where
    built = jobs(PARTS)
    stringers = [job for job in built if job.family in ("Stair stringer inner", "Stair stringer outer")]
    assert [job.label for job in stringers] == ["Flight 1 inner stringer", "Flight 1 outer stringer",
                                                "Flight 2 inner stringer", "Flight 2 outer stringer"]
    # A tread on the first flight lands on the same tread of the second.
    first, other = where.places[0], where.places[where.per_flight]
    for job in stringers[2:]:
        (placement,) = job.placements
        assert placed(placement, first.center) == pytest.approx(other.center, abs=1e-9)
    # The first flight stands on the ground, so its stringers have no foot holes and are files of their own.
    files = {item.label: item.file for item in stair_items(built)}
    assert files["Flight 1 inner stringer"] == "Stair stringer inner A.SLDPRT"
    assert files["Flight 2 inner stringer"] == "Stair stringer inner B.SLDPRT"
    assert files["Flight 2 outer stringer"] == "Stair stringer outer B.SLDPRT"


def test_flights_alike_share_one_stringer_file_placed_on_each():
    parts = replace(_three_platforms(), posts=(2, 4))
    items = stair_items(jobs(parts))
    inner = [item for item in items if item.file.startswith("Stair stringer inner")]
    assert [item.file for item in inner] == ["Stair stringer inner A.SLDPRT", "Stair stringer inner B.SLDPRT"]
    assert [len(item.placements) for item in inner] == [1, 2]  # the first flight, then the two above it
    assert inner[1].label == "Flight 2 inner stringer and 1 more alike"


def test_the_ground_turn_and_post_picks_move_parts_and_change_no_file():
    """Every piece is modelled at a seat its shape fixes, so these only change placements."""
    before = {job.label: job for job in jobs(PARTS)}
    moved = replace(PARTS, ground_in=-14.5, turn=math.radians(40))
    for job in jobs(moved):
        old = before[job.label]
        assert job.fingerprint == old.fingerprint
        for a, b in zip(old.placements, job.placements, strict=True):
            assert b.azimuth_rad - a.azimuth_rad == pytest.approx(math.radians(40))
            assert b.at_in[1] - a.at_in[1] == pytest.approx(-14.5)
    picked = {job.label: job.fingerprint for job in jobs(replace(PARTS, posts=(3, 5)))}
    for label in ("Tread", "Flight post", "Flight 1 inner stringer", "Flight 2 inner stringer"):
        assert picked[label] == before[label].fingerprint
    assert picked["Flight 1 outer stringer"] != before["Flight 1 outer stringer"].fingerprint  # its post holes moved


def test_a_rolled_platform_gets_its_sides_its_end_radials_and_one_radial_for_all_between():
    parts = _platform_parts(PlatformSpec(150.0))
    (_k, lines), = parts.platform_lines()
    assert lines.rolled and len(lines.radials) == 3
    built = {job.label: job for job in platform_jobs(parts, "C4x5.4")}
    assert sorted(built) == [f"Platform 1 {n}" for n in ("radial A", "radial B", "radials between", "side C",
                                                         "side D")]
    shared = built["Platform 1 radials between"]
    first = lines.radials[0]
    back = _world(first, lines.r_in + 3.0, 0.0, lines.top - 2.0)  # a point on R1's web back
    assert len(shared.placements) == len(lines.radials)
    for placement, angle in zip(shared.placements, lines.radials, strict=True):
        assert placed(placement, back) == pytest.approx(_world(angle, lines.r_in + 3.0, 0.0, lines.top - 2.0), abs=1e-9)


def test_a_straight_platform_gets_each_mitered_side_and_each_radial_on_its_own():
    parts = _platform_parts(PlatformSpec(60.0, rolled=False))
    (_k, lines), = parts.platform_lines()
    assert not lines.rolled and len(lines.radials) == 1
    labels = sorted(job.label for job in platform_jobs(parts, "C4x5.4"))
    assert labels == sorted([f"Platform 1 side {n}" for n in "ABCD"] + ["Platform 1 radial R1"])


def test_a_rolled_platforms_supports_at_the_radials_are_the_pieces_at_a_turned_about_the_tank_axis():
    from swauto.stair.platform_parts import C_FACE_IN
    from swauto.stair.platform_sw import _channel_ends, platform_knees

    parts = _platform_parts(PlatformSpec(150.0))  # the middle of its three radials is held
    (_k, lines), = parts.platform_lines()
    built = {job.label: job for job in jobs(parts, "", "C4x5.4", "L3x3", "L6x6")}
    stems = ("tab", "shell clip", "hanger", "knee brace", "knee clip")
    ends, knees = _channel_ends(lines), platform_knees(lines, parts.shell_od)
    for stem in stems:
        job = built[f"Platform 1 {stem} at A and the radials between"]
        assert len(job.placements) == len(lines.supports()) - 1 == 2  # A and the held radial
        for placement, end, (_l, frame, knee, _b) in zip(job.placements, ends, knees, strict=False):
            # The shell side's bolt and the knee's top bolt, carried from A's place to this support's.
            assert placed(placement, ends[0].world(C_FACE_IN, 2.0, lines.top - 2.0)) == pytest.approx(
                end.world(C_FACE_IN, 2.0, lines.top - 2.0), abs=1e-9)
            assert placed(placement, knees[0][1].world(*knees[0][2].top[:1], 0.0, knees[0][2].top[1])) == pytest.approx(
                frame.world(knee.top[0], 0.0, knee.top[1]), abs=1e-9)
        assert len(built[f"Platform 1 {stem} at B"].placements) == 1


def test_one_shell_pad_file_lands_on_every_pad_of_every_platform():
    from swauto.stair.platform_parts import pad_centres

    parts = _three_platforms()
    pad = _job(jobs(parts, "", "C4x5.4", "L3x3", "L6x6"), "Shell pad")
    centres = [c for _k, lines in parts.platform_lines() for c in pad_centres(lines, parts.shell_od)]
    assert len(pad.placements) == len(centres) == 3 * 2 * len(parts.platform_lines()[0][1].supports())
    for placement, (phi, y) in zip(pad.placements, centres, strict=True):
        assert placed(placement, _world(0.0, parts.shell_od, 0.0, 0.0)) == pytest.approx(
            _world(phi, parts.shell_od, 0.0, y), abs=1e-9)


def test_platforms_alike_share_every_piece_and_a_straight_ones_supports_each_get_a_file():
    items = stair_items(jobs(_three_platforms(), "L2x2", "C4x5.4", "L3x3", "L6x6"))
    files = [item.file for item in items]
    assert len(files) == len(set(files))
    side_c = next(item for item in items if item.label.startswith("Platform 1 side C"))
    assert len(side_c.placements) == 3  # the three platforms are one shape
    radial_b = [item for item in items if "radial B" in item.label]
    assert len(radial_b) == 2  # the top platform's B has no clip holes: no flight leaves it
    straight = stair_items(jobs(_platform_parts(PlatformSpec(60.0, rolled=False)), "", "C4x5.4", "L3x3", "L6x6"))
    knees = [item for item in straight if item.params["family"] == "Stair platform knee"]
    assert [item.label for item in knees] == [f"Platform 1 knee brace at {s}" for s in ("A", "B")]  # 60 in
    assert sum(item.file == "Stair shell pad A.SLDPRT" for item in straight) == 1


def test_a_shape_keeps_the_file_that_already_holds_it():
    todo = jobs(PARTS)
    tread = _job(todo, "Tread")
    built = {"Stair tread A.SLDPRT": "0123456789abcdef", "Stair tread B.SLDPRT": tread.fingerprint}
    (item,) = [item for item in stair_items(todo, built) if item.file.startswith("Stair tread")]
    assert item.file == "Stair tread B.SLDPRT" and item.fingerprint == tread.fingerprint


def test_the_stringer_clips_are_four_files_turned_and_lifted_to_every_platform_a_flight_meets():
    from swauto.stair.platform_parts import clip_frame, clip_jobs

    parts = _three_platforms()
    platforms = parts.platform_lines()
    assert [k for k, _lines in platforms] == [1, 2, 3]
    built = {job.label: job for job in clip_jobs(PartJob, platforms, parts.platforms, "L6x6", {}, parts.place)}
    assert sorted(built) == sorted(f"Stringer clip {side} {label}" for side in "AB" for label in ("In", "Out"))
    for side, count in (("A", 3), ("B", 2)):  # no flight leaves the top platform
        mine = [lines for _k, lines in platforms][:count]
        seat = replace(mine[0], phi_a=0.0, phi_b=0.0, top=0.0, radials=())
        for label in ("In", "Out"):
            job = built[f"Stringer clip {side} {label}"]
            assert len(job.placements) == count
            _phi0, heel0, _inward, _away, y0 = clip_frame(seat, side, label)
            assert y0 == -HOLE_DOWN_IN
            for placement, lines in zip(job.placements, mine, strict=True):
                phi, heel, _inward, _away, y = clip_frame(lines, side, label)
                assert heel == heel0  # every platform's clip is the same piece
                assert placed(placement, _world(0.0, heel0, 0.0, y0)) == pytest.approx(_world(phi, heel, 0.0, y),
                                                                                      abs=1e-9)


def test_the_end_channels_get_the_clip_holes_only_where_a_flight_meets_them(monkeypatch):
    import swauto.stair.parts_build as pb

    seen = []
    monkeypatch.setattr(pb, "_radial_member", lambda *args: None)
    monkeypatch.setattr(pb, "web_holes", lambda model, lines, side, name: seen.append(name))
    for job in pb.platform_jobs(_three_platforms(), "C4x5.4"):
        if job.label.endswith(("radial A", "radial B")):
            job.build(None)
    assert sorted(seen) == ["ElitePlatform1WebA", "ElitePlatform1WebB", "ElitePlatform2WebA", "ElitePlatform2WebB",
                            "ElitePlatform3WebA"]


def test_the_outer_clips_sit_on_the_outer_stringer_as_the_one_part_build_puts_them():
    parts = _platform_parts(PlatformSpec(96.0))
    (_k, lines), = parts.platform_lines()
    layout = parts.where.layout
    assert lines.stringer_b == pytest.approx(layout.inner_face_in + layout.clear_in)


def test_every_job_builds_its_own_piece_even_after_later_jobs_are_made(monkeypatch):
    """Each job's builder keeps its own piece: a later job reusing a name must not change an earlier one's."""
    import swauto.stair.parts_build as pb
    import swauto.stair.platform_parts as pp
    from swauto.stair.post_sw import Post

    seen = {}
    monkeypatch.setattr(pb, "_post", lambda model, parts, post, profile: seen.setdefault("post", post))
    monkeypatch.setattr(pp, "build_pad", lambda model, phi, y, shell_r, name: seen.setdefault("pad", (phi, y)))
    parts = _platform_parts(PlatformSpec(96.0), posts=(2, 4, 6))
    built = pb.jobs(parts, "L2x2", "C4x5.4", "L3x3")
    _job(built, "Flight post").build(None)
    _job(built, "Shell pad").build(None)
    assert isinstance(seen["post"], Post) and seen["post"] == parts.flight_posts()[0]
    assert seen["pad"] == (0.0, 0.0)
