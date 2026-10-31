"""The type 2 platform knee brace (2026-10-30, Elite 2026-050-1 PL1A to PL2B): its pieces' shapes as drawn, and every
knee of a platform that asks for it built that way."""

import math
from dataclasses import replace

import pytest

from swauto.stair import knee2
from swauto.stair.landings import StairArrangement, shell_marks
from swauto.stair.parts_build import StairParts, jobs
from swauto.stair.platform_sw import CLIP_BOLT_OUT_IN, platform_knees, platform_lines
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import CLEAR_IN, PlatformSpec, StringerMock

STAIR = StringerMock(treads=21)


def _lines(spec: PlatformSpec):
    where = stair_places(STAIR, STAIR.shell_od_in, 1)
    last = where.places[where.per_flight - 1]
    r_a = where.layout.inner_face_in
    return platform_lines(phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_a + CLEAR_IN, spec=spec)


def _knees(spec: PlatformSpec):
    return platform_knees(_lines(spec), STAIR.shell_od_in)


def test_the_option_is_type_1_or_2_and_keeps_type_1s_knee_line():
    assert PlatformSpec().knee == 1
    PlatformSpec(knee=2).validate()
    with pytest.raises(ValueError, match="type 1 or 2"):
        PlatformSpec(knee=3).validate()
    for (_l1, _f1, one, _b1), (_l2, _f2, two, _b2) in zip(_knees(PlatformSpec(150.0)),
                                                          _knees(PlatformSpec(150.0, knee=2)), strict=True):
        assert (one.top, one.bottom) == (two.top, two.bottom)


def test_the_hanger_is_pc12():
    (r_in, top), (r_out, _), (_, outer), (point_r, point_y), (_, inner) = knee2.hanger_outline(150.0, 40.0)
    assert r_out == pytest.approx(150.0 - 0.25) and r_out - r_in == pytest.approx(6.0)
    assert (top - outer, top - inner) == pytest.approx((3.875, 5.6875))
    assert (point_r - r_in, top - point_y) == pytest.approx((2.125, 7.75))
    # The outer side of the V is 45 deg; the drawing's 7-3/4 label makes the inner side 44 deg (7-13/16 for 45).
    assert (r_out - point_r) == pytest.approx(outer - point_y)


def test_the_brace_bolts_pair_round_holes_with_slots_3_in_along_it():
    (_label, _frame, knee, _back) = _knees(PlatformSpec(knee=2))[0]
    top, top_slot, bottom_slot, bottom = knee2.brace_bolts(knee)
    assert (top, bottom) == (knee.top, knee.bottom)
    for a, b in ((top, top_slot), (bottom_slot, bottom)):
        assert math.dist(a, b) == pytest.approx(3.0)
        assert b[0] - a[0] == pytest.approx(b[1] - a[1])  # down the brace at 45 deg
        assert b[1] < a[1]
    # The bottom round hole is type 1's bolt, 5.766 in out from the shell OD.
    assert bottom[0] - knee.shell_r == pytest.approx(CLIP_BOLT_OUT_IN)


def test_the_shell_clip_is_pc11_and_its_pad_pc10b():
    (_label, _frame, knee, _back) = _knees(PlatformSpec(knee=2))[0]
    (u0, v0), (u1, _), (u2, v2), (u3, v3), (_u4, v4) = knee2.clip_outline(knee)
    assert u0 == pytest.approx(knee.shell_r + 0.25)  # on the 1/4 pad
    assert (u1 - u0, u3 - u0, v4 - v0) == pytest.approx((6.1875, 8.875, 6.0))
    assert (u2 - u1, v2 - v0, v3 - v2) == pytest.approx((2.6875, 2.6875, 3.3125))  # the 45 deg corner, outer edge
    assert knee.bottom[1] - v0 == pytest.approx(1.98)
    t_mid, y_mid = knee2.pad_middle(knee)
    assert y_mid == pytest.approx(v0 + 3.0) and knee2.PAD_TALL_IN == 8.0
    assert t_mid == pytest.approx(knee.t_face - knee.side * 0.375 / 2.0)


def test_each_slot_is_13_16_wide_on_a_3_in_radius_and_lets_the_brace_swing_7_3_4_deg():
    hole = (100.0, 50.0)
    arcs = knee2.slot_arcs(hole, 1.0)
    for shape, following in zip(arcs, arcs[1:] + arcs[:1], strict=True):
        assert shape[-1] == pytest.approx(following[0])  # closed
    outer, _cap, inner, _cap2 = arcs
    assert {round(math.dist(hole, p), 6) for p in outer} == {round(3.0 + 0.40625, 6)}
    assert {round(math.dist(hole, p), 6) for p in inner} == {round(3.0 - 0.40625, 6)}
    swing = math.degrees(math.atan2(outer[2][1] - hole[1], outer[2][0] - hole[0])
                         - math.atan2(outer[0][1] - hole[1], outer[0][0] - hole[0]))
    assert abs(swing) / 2.0 == pytest.approx(math.degrees(0.40625 / 3.0), abs=1e-6)
    assert abs(swing) / 2.0 == pytest.approx(7.76, abs=0.01)
    middle = outer[1]
    assert math.atan2(middle[1] - hole[1], middle[0] - hole[0]) == pytest.approx(math.radians(-135.0))


def test_a_type_2_platform_builds_its_knees_as_parts_with_8_in_pads(monkeypatch):
    built = []
    for piece in ("build_hanger", "build_brace", "build_clip"):
        monkeypatch.setattr(knee2, piece, lambda *args, piece=piece: built.append(piece))
    stair = replace(StringerMock(treads=13), platform_specs=(PlatformSpec(150.0, knee=2),))
    parts = StairParts(stair, StringerMock().shell_od_in, 0.1875, platforms=1)
    todo = jobs(parts, "", "C4x5.4", "L3x3", "L6x6")
    for job in todo:
        if job.family in ("Stair platform hanger", "Stair platform knee", "Stair platform knee clip"):
            job.build(None)
    assert sorted(set(built)) == ["build_brace", "build_clip", "build_hanger"]
    pads = {job.label: len(job.placements) for job in todo if job.family == "Stair shell pad"}
    (_k, lines), = parts.platform_lines()
    assert pads == {"Shell pad": len(lines.supports()), "Shell pad 8 in tall": len(lines.supports())}
    one = StairParts(replace(stair, platform_specs=(PlatformSpec(150.0),)), StringerMock().shell_od_in, 0.1875,
                     platforms=1)
    ones = {job.label: job.fingerprint for job in jobs(one, "", "C4x5.4", "L3x3", "L6x6")}
    twos = {job.label: job.fingerprint for job in todo}
    assert ones["Platform 1 knee brace at B"] != twos["Platform 1 knee brace at B"]  # its own files


def test_the_shell_marks_show_the_8_in_knee_pads_on_their_clips():
    arrangement = StairArrangement(StringerMock(treads=21, platform_specs=(PlatformSpec(150.0, knee=2),)),
                                   platforms=1)
    pads = [m for m in shell_marks(arrangement)[0] if "knee brace pad" in m.label]
    assert pads and all(m.size == (4.0, 8.0) for m in pads)
    knees = _knees(PlatformSpec(150.0, knee=2))
    assert sorted(m.center[1] for m in pads) == pytest.approx(sorted(knee2.pad_middle(k)[1] for _l, _f, k, _b in knees))
