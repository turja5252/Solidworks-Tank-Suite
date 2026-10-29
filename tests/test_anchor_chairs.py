"""Anchor chairs, checked against the lisp (Anchor Chairs.lsp): layout, offsets and the chair's pieces."""

import pytest

from swauto.tank.anchors import AnchorChairs, bolt_point, chairs, front_outlines, leg_profile, read_offsets, warnings

# A saved job's chair (the lisp's own defaults put the hole off the plate): 19 x 10 x 1 top plate, hole 4 in out.
JOB = AnchorChairs(top_plate_width_in=19.0, top_plate_depth_in=10.0, top_plate_thk_in=1.0, washer_width_in=19.0,
                   washer_thk_in=2.0, hole_from_shell_in=4.0)


def test_chairs_are_equally_spaced_from_the_rotation_and_nudged_by_their_offsets():
    spots = chairs(JOB)
    assert len(spots) == 24 and spots[1].angle_deg == pytest.approx(15.0) and spots[6].angle_deg == pytest.approx(90.0)
    nudged = chairs(AnchorChairs(**{**vars(JOB), "rotation_deg": 2.5, "offsets": "1:15, 4:-10, x, 4:-5"}))
    assert nudged[0].angle_deg == pytest.approx(17.5)
    assert nudged[3].angle_deg == pytest.approx(2.5 + 45.0 - 5.0)  # a chair named twice keeps its last offset
    assert read_offsets("") == {}
    with pytest.raises(ValueError, match="chair number and degrees"):
        read_offsets("a:5")


def test_the_lisp_worked_example_bolt_positions():
    # 50'-6" centerline tank, 1 in course 1: the outside radius is 303.5 in. Chair 2 at 15 deg, hole 8 in out.
    spec = AnchorChairs(top_plate_depth_in=12.5, washer_depth_in=4.0)  # deep enough for the lisp's 8 in hole
    x, z = bolt_point(spec, 303.5, chairs(spec)[1])
    assert (x, z) == pytest.approx((-80.622, 300.886), abs=1e-3)
    assert bolt_point(spec, 303.5, chairs(spec)[6]) == pytest.approx((-311.5, 0.0), abs=1e-9)


def test_the_lisp_defaults_are_refused_because_the_hole_is_off_the_top_plate():
    with pytest.raises(ValueError, match="off the 4 in deep top plate"):
        AnchorChairs().validate()
    with pytest.raises(ValueError, match="legs stand out past the ends"):
        AnchorChairs(**{**vars(JOB), "leg_gap_in": 18.0}).validate()


def test_the_legs_taper_from_the_top_plate_to_the_chime_with_a_weld_clip():
    assert leg_profile(JOB) == [(0.0, 19.0), (10.0, 19.0), (2.5, 0.0), (0.25, 0.0), (0.0, 0.25)]
    pieces = dict((name, outline) for name, outline in front_outlines(JOB) if name != "leg")
    assert pieces["washer"][0] == (-9.5, 20.0) and pieces["washer"][2] == (9.5, 22.0)
    legs = [outline for name, outline in front_outlines(JOB) if name == "leg"]
    assert sorted(outline[0][0] for outline in legs) == [-5.75, 5.0]


def test_warnings_for_what_the_lisp_does_not_check():
    assert warnings(JOB, 303.5, course_one_in=96.0) == []
    crowded = AnchorChairs(**{**vars(JOB), "count": 120})
    assert "overlap" in warnings(crowded, 303.5)[0]
    low = AnchorChairs(**{**vars(JOB), "hole_from_shell_in": 2.5})
    assert any("bottom plate" in text for text in warnings(low, 303.5))
    assert any("past the first course" in text for text in warnings(JOB, 303.5, course_one_in=20.0))


def test_chairs_go_on_the_stretchout_and_are_checked_against_what_else_lands_there():
    from swauto.cleanout.spec import Cleanout
    from swauto.stretchout.checks import find_clashes
    from swauto.stretchout.model import ANCHORS, build_stretchout
    from swauto.tank.spec import Course, TankSpec

    tank = TankSpec(diameter_in=607.0, diameter_basis="od", courses=[Course(96.0, 1.0), Course(96.0, 0.75)])
    out = build_stretchout(tank, anchors=JOB)
    placed = [item for item in out.items if item.layer == ANCHORS]
    assert len(placed) == 24 and placed[0].label == "Chair 1"
    seventh = placed[6]  # at 90 deg: a quarter of the way round, leftward from 0 at the right end
    middle = (min(x for x, _y in seventh.outline) + max(x for x, _y in seventh.outline)) / 2.0
    assert middle == pytest.approx(0.75 * out.girth_in)
    assert max(y for _x, y in seventh.outline) == pytest.approx(22.0) and min(y for _x, y in seventh.outline) == 0.0
    with_ftco = build_stretchout(tank, anchors=JOB, cleanouts=[Cleanout("C1", size="10'-10\"", orientation_deg=0.0,
                                                                         annular_width_in=24.0)])
    assert any("Chair 1" in clash.text for clash in find_clashes(with_ftco))


def test_the_tab_shares_good_chairs_with_the_stretchout_and_explains_bad_ones(tk_window):
    import tkinter as tk
    from tkinter import ttk

    from swauto.tank.anchors_gui import build_anchor_tab, read_chairs

    shared: dict = {}
    page = ttk.Frame(tk_window)
    build_anchor_tab(page, tk.StringVar(), shared)
    page.update_idletasks()
    assert shared["anchors"] is None  # the lisp's defaults: the hole is off the plate
    shared["refresh_anchors"]()
    fields = {key: str(value) for key, value in vars(JOB).items()}
    assert read_chairs(fields) == JOB
