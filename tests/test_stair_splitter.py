"""The stringer splitter, checked against the lisp's SPLITSTRING worked on the app's own developments."""

import math

import pytest

from swauto.stair.development import develop_both
from swauto.stair.splitter import (
    LIMIT,
    SEGMENTS,
    SplitSettings,
    cut_treads,
    holes_in,
    joints,
    pieces,
    segment_count,
)
from swauto.stair.stringer import StringerMock

STAIR = StringerMock(treads=20, rise_in=7.5)  # 120 in shell OD radius, 8 in gap, 10.5 in run, 9 in plate


def _developments():
    return develop_both(STAIR)


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
    (a,) = joints(inner, 7.5, 20, SplitSettings())
    (b,) = joints(outer, 7.5, 20, SplitSettings())
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
