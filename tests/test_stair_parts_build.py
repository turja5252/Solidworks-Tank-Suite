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
