"""The stair as parts (2026-10-30): each piece's part placed where the one-part build puts that piece."""

import math

import pytest

from swauto.stair.parts_build import StairParts, jobs
from swauto.stair.platform_sw import _world
from swauto.stair.post_sw import _post_side
from swauto.stair.stringer import StringerMock

PARTS = StairParts(StringerMock(treads=13), StringerMock().shell_od_in, 0.1875, platforms=1, posts=(2, 4, 6))


def placed(placement, point_in):
    """Where SolidWorks puts a part's ``point_in`` (inches): row vector times the rotation, then the move."""
    t = placement.transform()
    p = [v * 0.0254 for v in point_in]
    return tuple((sum(p[i] * t[i * 3 + j] for i in range(3)) + t[9 + j]) / 0.0254 for j in range(3))


def test_the_tread_part_lands_on_every_pan_of_every_flight():
    where = PARTS.where
    tread = next(job for job in jobs(PARTS, "") if job.label == "Tread")
    first = where.places[0]
    assert len(tread.placements) == len(where.places) == 2 * where.per_flight
    for placement, place in zip(tread.placements, where.places, strict=True):
        assert placed(placement, first.center) == pytest.approx(place.center, abs=1e-9)


def test_the_post_part_lands_on_every_flight_post():
    posts = PARTS.flight_posts()
    job = next(job for job in jobs(PARTS, "") if job.label == "Flight post")
    _way, face_r = _post_side(PARTS.r_b, False)
    heel = _world(posts[0].phi, face_r, 0.0, posts[0].foot)
    assert len(job.placements) == len(posts) == 6
    for placement, post in zip(job.placements, posts, strict=True):
        assert placed(placement, heel) == pytest.approx(_world(post.phi, face_r, 0.0, post.foot), abs=1e-9)


def test_each_flight_gets_its_own_stringer_part_in_place_and_the_files_differ():
    built = jobs(PARTS, "")
    flights = [job for job in built if job.label.endswith("stringers")]
    assert [job.file for job in flights] == ["Stair Flight 1 Stringers.SLDPRT", "Stair Flight 2 Stringers.SLDPRT"]
    assert all(job.placements[0].azimuth_rad == 0.0 and job.placements[0].at_in == (0.0, 0.0, 0.0) for job in flights)
    assert len({job.file for job in built}) == len(built)


def test_a_turned_stair_turns_every_part_about_the_tank_axis():
    turned = StairParts(PARTS.stair, PARTS.shell_od, PARTS.wall_in, platforms=1, posts=(2, 4, 6), turn=math.radians(30))
    for plain, spun in zip(jobs(PARTS, ""), jobs(turned, ""), strict=True):
        for a, b in zip(plain.placements, spun.placements, strict=True):
            assert b.azimuth_rad - a.azimuth_rad == pytest.approx(math.radians(30))
            assert b.at_in == a.at_in


def _platform_parts(spec):
    from dataclasses import replace

    stair = replace(StringerMock(treads=13), platform_specs=(spec,))
    return StairParts(stair, StringerMock().shell_od_in, 0.1875, platforms=1)


def test_a_rolled_platform_gets_its_sides_its_end_radials_and_one_radial_for_all_between():
    from swauto.stair.parts_build import platform_jobs
    from swauto.stair.stringer import PlatformSpec

    parts = _platform_parts(PlatformSpec(96.0))
    (_k, lines), = parts.platform_lines()
    assert lines.rolled and len(lines.radials) == 2
    built = {job.file: job for job in platform_jobs(parts, "C4x5.4")}
    assert sorted(built) == [f"Stair Platform 1 {n}.SLDPRT" for n in ("C", "D", "Radial A", "Radial B", "Radial")]
    shared = built["Stair Platform 1 Radial.SLDPRT"]
    first = lines.radials[0]
    back = _world(first, lines.r_in + 3.0, 0.0, lines.top - 2.0)  # a point on R1's web back
    assert len(shared.placements) == len(lines.radials)
    for placement, angle in zip(shared.placements, lines.radials, strict=True):
        assert placed(placement, back) == pytest.approx(_world(angle, lines.r_in + 3.0, 0.0, lines.top - 2.0), abs=1e-9)


def test_a_straight_platform_gets_each_mitered_side_and_each_radial_on_its_own():
    from swauto.stair.parts_build import platform_jobs
    from swauto.stair.stringer import PlatformSpec

    parts = _platform_parts(PlatformSpec(60.0, rolled=False))
    (_k, lines), = parts.platform_lines()
    assert not lines.rolled and len(lines.radials) == 1
    files = sorted(job.file for job in platform_jobs(parts, "C4x5.4"))
    assert files == sorted([f"Stair Platform 1 {n}.SLDPRT" for n in ("A", "B", "C", "D", "Radial R1")])


def test_a_rolled_platforms_supports_at_the_radials_are_the_pieces_at_a_turned_about_the_tank_axis():
    from swauto.stair.parts_build import PartJob
    from swauto.stair.platform_parts import C_FACE_IN, support_jobs
    from swauto.stair.platform_sw import _channel_ends, platform_knees
    from swauto.stair.stringer import PlatformSpec

    parts = _platform_parts(PlatformSpec(96.0))
    (k, lines), = parts.platform_lines()
    built = {job.file: job for job in support_jobs(PartJob, k, lines, parts.shell_od, 0.0, "L3x3")}
    stems = ("Tab", "Shell Clip", "Hanger", "Knee", "Knee Clip")
    assert sorted(built) == sorted([f"Stair Platform 1 {stem}.SLDPRT" for stem in stems]
                                   + [f"Stair Platform 1 {stem} B.SLDPRT" for stem in stems])
    ends, knees = _channel_ends(lines), platform_knees(lines, parts.shell_od)
    for stem in stems:
        job = built[f"Stair Platform 1 {stem}.SLDPRT"]
        assert len(job.placements) == len(lines.supports()) - 1  # A and every radial between
        for placement, end, (_l, frame, knee, _b) in zip(job.placements, ends, knees, strict=False):
            # The shell side's bolt and the knee's top bolt, carried from A's place to this support's.
            assert placed(placement, ends[0].world(C_FACE_IN, 2.0, lines.top - 2.0)) == pytest.approx(
                end.world(C_FACE_IN, 2.0, lines.top - 2.0), abs=1e-9)
            assert placed(placement, knees[0][1].world(*knees[0][2].top[:1], 0.0, knees[0][2].top[1])) == pytest.approx(
                frame.world(knee.top[0], 0.0, knee.top[1]), abs=1e-9)
        assert len(built[f"Stair Platform 1 {stem} B.SLDPRT"].placements) == 1


def test_one_shell_pad_file_lands_on_every_pad_of_every_platform():
    from swauto.stair.platform_parts import pad_centres, pad_job_placements
    from swauto.stair.stringer import PlatformSpec

    parts = _platform_parts(PlatformSpec(96.0))
    platforms = parts.platform_lines()
    head, places = pad_job_placements(platforms, parts.shell_od, 0.0)
    centres = [c for _k, lines in platforms for c in pad_centres(lines, parts.shell_od)]
    assert len(places) == len(centres) == 2 * len(platforms[0][1].supports())  # a shell clip's and a knee's each
    for placement, (phi, y) in zip(places, centres, strict=True):
        assert placed(placement, _world(head[0], parts.shell_od, 0.0, head[1])) == pytest.approx(
            _world(phi, parts.shell_od, 0.0, y), abs=1e-9)


def test_a_straight_platforms_supports_each_get_their_own_files_and_every_file_name_is_unique():
    from swauto.stair.stringer import PlatformSpec

    parts = _platform_parts(PlatformSpec(60.0, rolled=False))
    files = [job.file for job in jobs(parts, "", "C4x5.4", "L3x3")]
    assert len(files) == len(set(files))
    for label in ("A", "R1", "B"):
        assert f"Stair Platform 1 Knee {label}.SLDPRT" in files
    assert files.count("Stair Shell Pad.SLDPRT") == 1


def _three_platforms():
    """Two mid platforms and a top one, rolled."""
    from dataclasses import replace

    from swauto.stair.stringer import PlatformSpec

    stair = replace(StringerMock(treads=13), platform_specs=(PlatformSpec(96.0),) * 3)
    return StairParts(stair, StringerMock().shell_od_in, 0.1875, platforms=2, top_platform=True)


def test_the_stringer_clips_are_four_files_turned_and_lifted_to_every_platform_a_flight_meets():
    from swauto.stair.parts_build import PartJob
    from swauto.stair.platform_parts import clip_frame, clip_jobs

    parts = _three_platforms()
    platforms = parts.platform_lines()
    assert [k for k, _lines in platforms] == [1, 2, 3]
    built = {job.file: job for job in clip_jobs(PartJob, platforms, parts.platforms, 0.0, "L6x6")}
    assert sorted(built) == sorted(f"Stair Platform Clip {side} {label}.SLDPRT"
                                   for side in "AB" for label in ("In", "Out"))
    for side, count in (("A", 3), ("B", 2)):  # no flight leaves the top platform
        mine = [lines for _k, lines in platforms][:count]
        for label in ("In", "Out"):
            job = built[f"Stair Platform Clip {side} {label}.SLDPRT"]
            assert len(job.placements) == count
            phi0, heel0, _inward, _away, y0 = clip_frame(mine[0], side, label)
            for placement, lines in zip(job.placements, mine, strict=True):
                phi, heel, _inward, _away, y = clip_frame(lines, side, label)
                assert heel == heel0  # every platform's clip is the same piece
                assert placed(placement, _world(phi0, heel0, 0.0, y0)) == pytest.approx(_world(phi, heel, 0.0, y),
                                                                                       abs=1e-9)


def test_the_end_channels_get_the_clip_holes_only_where_a_flight_meets_them(monkeypatch):
    import swauto.stair.parts_build as pb

    seen = []
    monkeypatch.setattr(pb, "_radial_member", lambda *args: None)
    monkeypatch.setattr(pb, "web_holes", lambda model, lines, side, name: seen.append(name))
    for job in pb.platform_jobs(_three_platforms(), "C4x5.4"):
        if " Radial A" in job.file or " Radial B" in job.file:
            job.build(None)
    assert sorted(seen) == ["ElitePlatform1WebA", "ElitePlatform1WebB", "ElitePlatform2WebA", "ElitePlatform2WebB",
                            "ElitePlatform3WebA"]


def test_the_outer_clips_sit_on_the_outer_stringer_as_the_one_part_build_puts_them():
    from swauto.stair.stringer import PlatformSpec

    parts = _platform_parts(PlatformSpec(96.0))
    (_k, lines), = parts.platform_lines()
    layout = parts.where.layout
    assert lines.stringer_b == pytest.approx(layout.inner_face_in + layout.clear_in)


def test_every_job_builds_its_own_piece_even_after_later_jobs_are_made(monkeypatch):
    """Each job's builder keeps its own piece: a later job reusing a name must not change an earlier one's."""
    import swauto.stair.parts_build as pb
    from swauto.stair.post_sw import Post
    from swauto.stair.stringer import PlatformSpec

    seen = {}
    monkeypatch.setattr(pb, "_post", lambda model, parts, post, profile: seen.setdefault("post", post))
    monkeypatch.setattr(pb, "build_pad", lambda model, phi, y, shell_r, name: seen.setdefault("pad", (phi, y)))
    parts = _platform_parts(PlatformSpec(96.0))
    parts = pb.StairParts(parts.stair, parts.shell_od, parts.wall_in, platforms=1, posts=(2, 4, 6))
    built = pb.jobs(parts, "L2x2", "C4x5.4", "L3x3")
    next(job for job in built if job.label == "Flight post").build(None)
    next(job for job in built if job.label == "Shell pad").build(None)
    assert isinstance(seen["post"], Post) and seen["post"] == parts.flight_posts()[0]
    assert isinstance(seen["pad"][0], float)
