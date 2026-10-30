"""The stringer splitter, checked against the lisp's SPLITSTRING worked on the app's own developments."""

import math

import pytest

from swauto.stair.development import develop_both
from swauto.stair.splitter import (
    HOLE_INSET_IN,
    LIMIT,
    OVERCUT_IN,
    RELIEF_IN,
    SEGMENTS,
    Joint,
    SplitSettings,
    _inside,
    bottom_x,
    choose_cuts,
    clashes,
    cut_span,
    cut_treads,
    holes_in,
    joints,
    pieces,
    relief_cutter,
    reliefs,
    segment_count,
    top_x,
)
from swauto.stair.stringer import StringerMock

STAIR = StringerMock(treads=20, rise_in=7.5)  # 120 in shell OD radius, 8 in gap, 10.5 in run, 9 in plate


def _developments():
    return develop_both(STAIR)


def _side(point, a, b) -> float:
    """Which side of the line through ``a`` and ``b`` the point is on (the sign), times the line's length."""
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])


def _off_line(point, a, b) -> float:
    """How far ``point`` is from the line through ``a`` and ``b``."""
    return abs(_side(point, a, b)) / math.dist(a, b)


def test_max_span_counts_the_vertical_span_with_the_foot_drop():
    inner, outer = _developments()
    assert inner.height_in == pytest.approx(147.75)  # (20 - 1) x 7.5 + 5.25
    assert segment_count(inner, 20, SplitSettings(LIMIT, max_span_ft=8.5)) == 2  # 12.3125 ft
    assert segment_count(outer, 20, SplitSettings(LIMIT, max_span_ft=6.0)) == 3
    assert segment_count(inner, 20, SplitSettings(SEGMENTS, segments=21)) is None  # more pieces than treads


def test_cuts_share_the_tread_intervals_out_from_tread_1():
    assert cut_treads(20, 2) == [10]
    assert cut_treads(20, 3) == [7, 13]
    assert cut_treads(4, 4) == [1, 2, 3]


def test_the_joint_matches_the_lisp_on_both_stringers():
    inner, outer = _developments()
    lisp = SplitSettings(hole_row_in=1.625)  # the lisp's rows; Auto evens the steel and clears the washers
    (a,) = joints(inner, 7.5, 20, lisp)
    (b,) = joints(outer, 7.5, 20, lisp)
    assert a.tread == b.tread == 10
    assert a.y_cut == b.y_cut == pytest.approx(78.75)  # midway between the two tread centers
    assert sorted(round(x, 4) for x, y in a.holes if y > 79) == [94.0173, 103.5161]
    assert sorted(round(x, 4) for x, y in a.holes if y < 78) == [90.0285, 99.5273]
    assert sorted(round(x, 4) for x, y in b.holes if y > 79) == [121.7655, 132.9476]
    assert sorted(round(x, 4) for x, y in b.holes if y < 78) == [116.6542, 127.8364]
    assert sorted({round(y, 4) for _x, y in a.holes}) == [77.125, 80.375]


def test_the_plate_is_a_level_parallelogram_over_the_full_depth():
    inner, outer = _developments()
    (b,) = joints(outer, 7.5, 20, SplitSettings())
    assert [(round(x, 4), round(y, 4)) for x, y in b.plate] == [
        (112.3165, 76.1444), (129.0897, 76.1444), (137.2853, 81.3556), (120.5121, 81.3556)
    ]
    (a,) = joints(inner, 7.5, 20, SplitSettings())
    corners = {(round(x, 4), round(y, 4)) for x, y in a.plate}
    assert {(86.4503, 76.1444), (100.6985, 76.1444), (92.8461, 81.3556)} <= corners
    assert (107.0943, 81.3556) not in corners  # the inner plate's top acute corner is rounded
    assert len(a.plate) > 4


def test_a_typed_plate_height_stays_centered_on_the_cut():
    _inner, outer = _developments()
    (b,) = joints(outer, 7.5, 20, SplitSettings(plate_height_in=3.0))
    ys = sorted({round(y, 4) for _x, y in b.plate})
    assert ys == [77.25, 80.25]
    # The 1-5/8 rows fall outside a 3 in plate, so they move midway between its edge and the cut.
    rows = [round((77.25 + 78.625) / 2, 4), round((80.25 + 78.875) / 2, 4)]
    assert sorted({round(y, 4) for _x, y in b.holes}) == rows


def test_pieces_meet_the_cut_with_a_quarter_inch_gap_and_keep_their_own_holes():
    inner, outer = _developments()
    for dev in (inner, outer):
        cuts = joints(dev, 7.5, 20, SplitSettings())
        low, high = pieces(dev, cuts)
        assert max(y for _x, y in low) == pytest.approx(78.625)
        assert min(y for _x, y in high) == pytest.approx(78.875)
        tread_holes = list(dev.tread_bolts)
        kept = holes_in(low, tread_holes, 7.0 / 32.0) + holes_in(high, tread_holes, 7.0 / 32.0)
        assert len(kept) == len(tread_holes)  # no tread bolt is on a cut
    low, high = pieces(inner, joints(inner, 7.5, 20, SplitSettings()))
    assert len(low) > 4 and len(high) > 4  # the inner stringer's acute joint corners are relieved
    sharp = pieces(outer, joints(outer, 7.5, 20, SplitSettings()))
    assert all(any(math.isclose(y, 78.625) for _x, y in piece) or any(math.isclose(y, 78.875) for _x, y in piece)
               for piece in sharp)


def test_the_cut_runs_across_the_end_shape_where_a_joint_is_near_a_flight_end():
    inner, _outer = develop_both(StringerMock(treads=3))
    (joint,) = joints(inner, 7.5, 3, SplitSettings(SEGMENTS, segments=2))
    x0, x1 = cut_span(inner, joint)
    assert x0 == pytest.approx(top_x(inner, joint.y_cut), abs=0.2)
    assert x1 > bottom_x(inner, joint.y_cut) + 2.0  # the top end's drop, past the sloped bottom edge


def _steel(joint):
    """Steel above and below each row's holes: to the plate's edge one way, to the cut's burn line the other."""
    top, bottom = max(y for _x, y in joint.plate), min(y for _x, y in joint.plate)
    up, down = max(y for _x, y in joint.holes), min(y for _x, y in joint.holes)
    return (top - up, up - (joint.y_cut + 0.125)), (down - bottom, joint.y_cut - 0.125 - down)


@pytest.mark.parametrize(("rise", "row"), [(7.5, 1.3653), (7.0, 1.2403), (6.5, 1.1153)])
def test_auto_hole_rows_leave_even_steel_and_clear_washers(rise, row):
    for dev in develop_both(StringerMock(treads=24, rise_in=rise)):
        cuts = joints(dev, rise, 24, SplitSettings())
        assert {round(abs(y - joint.y_cut), 4) for joint in cuts for _x, y in joint.holes} == {row}
        for above, below in _steel(cuts[0]):
            assert above == pytest.approx(below)  # the same steel up and down
        assert clashes(dev, cuts) == []


def test_an_auto_row_moves_nearer_the_cut_when_its_washer_needs_it():
    for dev in develop_both(StringerMock(treads=16)):
        cuts = joints(dev, 7.5, 16, SplitSettings(plate_height_in=7.0))  # its even rows' washers reach the treads
        assert {round(abs(y - cuts[0].y_cut), 4) for _x, y in cuts[0].holes} == {1.75}
        assert not any("washer runs into" in note for note in clashes(dev, cuts))


@pytest.mark.parametrize("slope", [30.0, 45.0, 60.0])
def test_the_hole_pattern_follows_the_slope(slope):
    rise = 7.0
    for dev in develop_both(StringerMock(treads=24, rise_in=rise, run_in=rise / math.tan(math.radians(slope)))):
        cuts = joints(dev, rise, 24, SplitSettings())
        assert cuts and clashes(dev, cuts) == []
        for x, y in cuts[0].holes:  # 1-1/2 in in from the nearer edge, square to the slope
            inset = min(x - top_x(dev, y), bottom_x(dev, y) - x) * math.sin(dev.pitch_rad)
            assert inset == pytest.approx(HOLE_INSET_IN)


def test_what_no_hole_row_clears_is_reported():
    inner, _outer = develop_both(StringerMock(treads=24, rise_in=5.5))
    cuts = joints(inner, 5.5, 24, SplitSettings())
    for above, below in _steel(cuts[0]):  # nothing clears: the even rows stay
        assert above == pytest.approx(below)
    assert any("a splice bolt's washer runs into tread" in note for note in clashes(inner, cuts))
    seven, _outer = develop_both(StringerMock(treads=16, rise_in=7.0))
    typed = joints(seven, 7.0, 16, SplitSettings(hole_row_in=1.625))
    assert {round(abs(y - typed[0].y_cut), 4) for _x, y in typed[0].holes} == {1.625}  # a typed row stays


def test_the_plate_on_a_tread_bolt_washer_is_reported():
    _inner, outer = develop_both(StringerMock(treads=16))
    cuts = joints(outer, 7.5, 16, SplitSettings(plate_height_in=6.5))
    assert clashes(outer, cuts) == ["Outer stringer splice over tread 8: the plate is on a tread 9 bolt's washer."]
    assert clashes(outer, joints(outer, 7.5, 16, SplitSettings())) == []  # the Auto plate keeps 0.644 in off


def test_cuts_keep_off_treads_with_a_post_brace_or_clip():
    assert choose_cuts(7.5, 16, SplitSettings()) == [8]
    assert choose_cuts(7.5, 16, SplitSettings(avoid=(8, 12))) == [9]
    assert choose_cuts(7.5, 20, SplitSettings(avoid=(5, 10, 15))) == [11]
    inner, _outer = develop_both(StringerMock(treads=16))
    assert clashes(inner, joints(inner, 7.5, 16, SplitSettings(avoid=(8, 12))), (8, 12)) == []
    # With no clear gap left, the lisp's cut stays and the check says what is beside it.
    (stuck,) = joints(inner, 7.5, 16, SplitSettings(avoid=tuple(range(2, 16))))
    assert stuck.tread == 8
    assert clashes(inner, [stuck], tuple(range(2, 16)))[-1].endswith("treads 8 and 9 have a post or brace.")


def test_a_piece_more_when_the_clear_gaps_cannot_keep_the_max_span():
    avoid = (11, 12, 13, 14)  # round the middle of a 24 tread flight, where its one cut would go
    cuts = choose_cuts(7.5, 24, SplitSettings(avoid=avoid))
    assert cuts == [8, 16]  # pieces of 61.5, 60 and 56.25 in: the longest as short as it can be
    levels = [7.5 - 5.25] + [(cut + 0.5) * 7.5 for cut in cuts] + [24 * 7.5]
    assert max(b - a for a, b in zip(levels, levels[1:])) <= 8.5 * 12


def test_segments_keep_off_posts_and_the_end_gaps_too():
    assert choose_cuts(7.5, 20, SplitSettings(SEGMENTS, segments=3, avoid=(7,))) == [5, 12]  # the lisp's 7, 13
    assert choose_cuts(7.5, 12, SplitSettings(SEGMENTS, segments=4, avoid=(3,))) == [4, 5, 8]  # not 1: end clip
    assert choose_cuts(7.5, 7, SplitSettings(max_span_ft=4.0, avoid=(3, 5))) == [4]  # all blocked: the lisp's


def test_a_flight_no_cut_can_keep_within_the_span_falls_back_at_once():
    # A post at 5 blocks gaps 4 and 5; bridging 3 to 6 is over a 1 ft span, so no number of pieces works.
    settings = SplitSettings(max_span_ft=1.0, avoid=(5,))
    assert choose_cuts(7.5, 96, settings) == cut_treads(96, 60)


def test_a_cut_left_in_an_end_gap_is_reported():
    for dev in develop_both(StringerMock(treads=3)):
        cuts = joints(dev, 7.5, 3, SplitSettings(SEGMENTS, segments=2))
        assert [joint.tread for joint in cuts] == [2]
        assert any(note.endswith("the cut is in the flight's last tread gap, by its end clips.")
                   for note in clashes(dev, cuts))


def test_a_cut_left_in_the_first_gap_is_reported():
    for dev in develop_both(StringerMock(treads=3)):
        cuts = joints(dev, 7.5, 3, SplitSettings(SEGMENTS, segments=3))
        assert [joint.tread for joint in cuts] == [1, 2]
        notes = clashes(dev, cuts)
        assert any(note.endswith("the cut is in the flight's first tread gap, by its end clips.") for note in notes)
        assert any(note.endswith("the cut is in the flight's last tread gap, by its end clips.") for note in notes)


def test_a_typed_hole_row_must_clear_the_cut():
    with pytest.raises(ValueError, match="clears the 1/4 in gap"):
        SplitSettings(hole_row_in=0.5)
    assert SplitSettings(hole_row_in=0.6).hole_row_in == 0.6


def test_the_sheet_and_the_build_round_a_short_end_piece_alike():
    # A cut in the last gap of a short, shallow flight: the upper piece's top edge is short, but the R1 fits.
    for stair in (StringerMock(treads=4, rise_in=5.0, run_in=13.74, shell_od_in=600.0),
                  StringerMock(treads=6, rise_in=6.0)):
        inner, _outer = develop_both(stair)
        cuts = joints(inner, stair.rise_in, stair.treads, SplitSettings(SEGMENTS, segments=stair.treads - 1))
        outlines = pieces(inner, cuts)
        for joint in cuts:
            for r in (r for r in reliefs(inner, joint) if r.piece != "plate"):
                assert any(all(any(math.dist(p, q) < 1e-6 for q in outline) for p in (r.start, r.middle, r.end))
                           for outline in outlines)


def test_a_splice_hole_off_the_plate_is_reported():
    inner, _outer = develop_both(StringerMock(treads=16))
    (joint,) = joints(inner, 7.5, 16, SplitSettings())
    assert len(holes_in(joint.plate, joint.holes, 13 / 32)) == 4 and clashes(inner, [joint]) == []
    shifted = Joint(joint.tread, joint.y_cut, joint.plate, tuple((x, y + 1.5) for x, y in joint.holes))
    assert any("a splice hole runs off the plate" in note for note in clashes(inner, [shifted]))


def test_a_typed_row_that_would_cross_the_plate_edge_moves_on_the_plate():
    for dev in develop_both(StringerMock(treads=16)):
        (joint,) = joints(dev, 7.5, 16, SplitSettings(plate_height_in=3.5, hole_row_in=1.625))
        assert len(holes_in(joint.plate, joint.holes, 13 / 32)) == 4  # 1.625 + 13/32 is past the 1.75 in half
        assert not any("off the plate" in note for note in clashes(dev, [joint]))


def test_a_tread_bolt_wholly_under_a_typed_plate_is_reported():
    for dev in develop_both(StringerMock(treads=16)):
        notes = clashes(dev, joints(dev, 7.5, 16, SplitSettings(plate_height_in=10.0)))
        where = f"{dev.side.capitalize()} stringer splice over tread 8"
        assert f"{where}: the plate is on a tread 8 bolt's washer." in notes
        assert f"{where}: the plate is on a tread 9 bolt's washer." in notes


@pytest.mark.parametrize(("field", "value"), [("max_span_ft", math.nan), ("plate_height_in", math.inf),
                                              ("hole_row_in", math.nan), ("plate_height_in", 1.0)])
def test_settings_refuse_numbers_that_are_not_a_size(field, value):
    with pytest.raises(ValueError):
        SplitSettings(**{field: value})


def test_the_inner_joint_rounds_are_the_ones_its_burn_pieces_have():
    inner, outer = develop_both(StringerMock(treads=16))
    (joint,) = joints(inner, 7.5, 16, SplitSettings())
    rounds = reliefs(inner, joint)
    assert [r.piece for r in rounds] == ["lower", "upper", "plate"]
    low, high = pieces(inner, [joint])
    for r, outline in zip(rounds, (low, high, joint.plate), strict=True):
        assert all(math.dist(r.center, p) == pytest.approx(RELIEF_IN) for p in (r.start, r.middle, r.end))
        # the burn outline has the very arc the build cuts: start, middle and end
        assert all(any(math.dist(p, q) < 1e-6 for q in outline) for p in (r.start, r.middle, r.end))
    assert reliefs(outer, joints(outer, 7.5, 16, SplitSettings())[0]) == []
    # The cutter runs 1/4 in past both edges and round the corner outside the metal; only its arc touches it.
    for r, outline in zip(rounds, (low, high, joint.plate), strict=True):
        start, out_u, apex, out_v, end = relief_cutter(r)
        assert (start, end) == (r.start, r.end)
        for point, edge_end in ((out_u, r.start), (out_v, r.end)):
            assert _off_line(point, r.corner, edge_end) == pytest.approx(OVERCUT_IN)
            assert _side(point, r.corner, edge_end) * _side(r.center, r.corner, edge_end) < 0  # out of the metal
        assert _off_line(apex, r.corner, r.start) == pytest.approx(OVERCUT_IN)
        assert _off_line(apex, r.corner, r.end) == pytest.approx(OVERCUT_IN)
        for edge_end in (r.start, r.end):  # the apex is outside the corner, past both edges
            assert _side(apex, r.corner, edge_end) * _side(r.center, r.corner, edge_end) < 0
        # so the cutter's loop takes the corner: a point just inside it is in the loop
        just_in = (r.corner[0] + (r.middle[0] - r.corner[0]) * 0.05, r.corner[1] + (r.middle[1] - r.corner[1]) * 0.05)
        assert _inside(just_in, [*relief_cutter(r), r.middle])
        assert not any(_inside(p, outline) for p in (out_u, apex, out_v))
    # By a flight's end the cut meets the end shape, not the bottom edge: no round there.
    short, _outer = develop_both(StringerMock(treads=3))
    (end_joint,) = joints(short, 7.5, 3, SplitSettings(SEGMENTS, segments=2))
    assert [r.piece for r in reliefs(short, end_joint)] == ["upper", "plate"]
