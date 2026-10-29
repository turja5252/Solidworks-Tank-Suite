"""Rafters, dollar plate and center column, checked against the lisp's worked example (50'-6" CL tank,
1 in course, 3/4 in per ft, 1/4 in roof, no ring)."""

import math

import pytest

from swauto.tank.framing import (
    EXTERNAL,
    INTERNAL,
    RIGHT,
    Column,
    Framing,
    clip_outlines,
    layout,
    mode_for_roof_type,
    radial,
    rafter_outline,
)
from swauto.tank.roof import RoofSpec

ROOF = RoofSpec(inside_radius_in=302.5, outside_radius_in=303.5, shell_height_in=480.0, slope_in_per_ft=0.75,
                thickness_in=0.25)
K = math.hypot(1.0, 0.0625)


def test_the_worked_example_slant_and_dollar_rule():
    plan = layout(Framing(setback_in=12.0351, column=Column(dollar_dia_in=36.0, dollar_thk_in=0.5)), ROOF)
    assert plan.slant_in == pytest.approx(303.0902, abs=1e-4)  # R1
    assert plan.warnings == ()  # the rafters reach 6 in over the 36 in dollar plate
    short = layout(Framing(setback_in=12.5, column=Column(dollar_dia_in=36.0, dollar_thk_in=0.5)), ROOF)
    assert "at most 12.035 in" in short.warnings[0]
    # Internal: the dollar plate's top is on the rafters' bottom chord, 6 x k = 6.0117 in under the roof.
    (name, loop), = plan.column
    under = ROOF.landing_height_in() + (302.5 - 18.0) * 0.0625
    assert name == "Dollar plate" and max(y for _r, y in loop) == pytest.approx(under - 6.0117, abs=1e-4)


def test_rafters_are_even_and_half_a_space_off_the_first_seam_at_90_deg():
    plan = layout(Framing(rafter_count=13, setback_in=12.0), ROOF)
    assert len(plan.rafters) == 12
    assert [r.angle_deg for r in plan.rafters[:3]] == pytest.approx([105.0, 135.0, 165.0])
    turned = layout(Framing(setback_in=12.0, rotation_deg=10.0), ROOF)
    assert turned.rafters[0].angle_deg == pytest.approx(115.0)
    assert radial(90.0) == pytest.approx((-1.0, 0.0))  # the app's angles: 90 deg is -X


def test_rafters_that_meet_at_the_center_are_refused():
    with pytest.raises(ValueError, match="run into each other near the center"):
        layout(Framing(), ROOF)  # the lisp's defaults run every rafter to the apex
    with pytest.raises(ValueError, match="outer end is not beyond the inner end"):
        layout(Framing(inner_trim_in=200.0, outer_trim_in=110.0), ROOF)


def test_internal_rafters_hang_square_under_the_roof_and_external_ones_sit_on_it():
    inside = layout(Framing(setback_in=12.0), ROOF)
    (ra, _ya), (rb, yb), (rb2, yb2), _corner = inside.section
    assert ra == pytest.approx(12.0 * 302.5 / inside.slant_in)
    assert rb == pytest.approx(302.5)  # no outer trim: out to the landing
    assert math.hypot(rb - rb2, yb - yb2) == pytest.approx(6.0)  # depth square to the roof
    assert yb2 < yb and rb2 < rb  # down and in
    outside = layout(Framing(mode=EXTERNAL, setback_in=12.0), ROOF)
    (_ra, ya), _b, _c, (_ra2, ya2) = outside.section
    assert ya2 > ya  # up off the plate
    assert ya == pytest.approx(ROOF.landing_height_in() + (302.5 - outside.section[0][0]) * 0.0625 + 0.25 * K,
                               abs=2e-3)


def test_clips_stand_off_the_chosen_side_between_the_rafter_ends():
    plan = layout(Framing(setback_in=12.0, clips_per_rafter=2), ROOF)
    assert plan.clip_slants_in == pytest.approx([12.0 + (303.0902 - 12.0) / 3, 12.0 + 2 * (303.0902 - 12.0) / 3],
                                                abs=1e-3)
    rafter = plan.rafters[0]
    left = clip_outlines(plan, rafter)
    right = clip_outlines(layout(Framing(setback_in=12.0, clip_side=RIGHT), ROOF), rafter)
    body = rafter_outline(plan, rafter)
    ux, uz = radial(rafter.angle_deg)
    cw = (-uz, ux)

    def side(points):
        return sum((x * cw[0] + z * cw[1]) for x, z in points) / len(points)

    assert side(left[0]) < side(body) < side(right[0])  # left is counterclockwise
    assert abs(side(left[0])) == pytest.approx(2.0 + 5.75 / 2.0)


def test_the_column_stack_stands_on_the_floor_up_to_the_roof():
    column = Column(dollar_dia_in=36.0, dollar_thk_in=0.5, top_cap_dia_in=12.0, top_cap_thk_in=0.75,
                    pipe_od_in=8.625, pipe_wall_in=0.322, bottom_cap_dia_in=12.0, bottom_cap_thk_in=0.75,
                    base_dia_in=18.0, base_thk_in=1.0)
    plan = layout(Framing(mode=EXTERNAL, setback_in=12.0, column=column), ROOF)
    names = [name for name, _loop in plan.column]
    assert names == ["Dollar plate", "Top cap", "Column", "Bottom cap", "Base plate"]
    loops = dict(plan.column)
    under = ROOF.landing_height_in() + (302.5 - 18.0) * 0.0625
    assert max(y for _r, y in loops["Dollar plate"]) == pytest.approx(under)  # external: under the roof plate
    assert min(y for _r, y in loops["Base plate"]) == 0.0
    pipe = loops["Column"]
    assert min(y for _r, y in pipe) == pytest.approx(1.75) and max(y for _r, y in pipe) == pytest.approx(under - 1.25)
    assert min(r for r, _y in pipe) == pytest.approx(8.625 / 2 - 0.322)


def test_roof_types_from_tank_properties():
    assert mode_for_roof_type("Internal Rafter Roof") == INTERNAL
    assert mode_for_roof_type("external rafter roof") == EXTERNAL
    assert mode_for_roof_type("Self Supporting Dome Roof") is None


def test_the_framing_tab_follows_the_roof_type_and_draws_the_plan(tk_window):
    import tkinter as tk
    from tkinter import ttk

    from swauto.tank.framing_gui import build_framing_tab, read_framing
    from swauto.tank.spec import Course, TankSpec

    tank = TankSpec(diameter_in=606.0, courses=[Course(96.0, 1.0)], roof_type="External Rafter Roof")
    shared: dict = {"roof": ROOF, "spec": tank}
    page = ttk.Frame(tk_window)
    build_framing_tab(page, tk.StringVar(), shared)
    page.update_idletasks()
    entries = [w for w in page.winfo_children()[0].winfo_children()
               if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
    texts = {str(w.getvar(str(w.cget("textvariable")))) for w in page.winfo_children()[0].winfo_children()
             if "textvariable" in w.keys() and str(w.cget("textvariable"))}
    assert "External" in texts  # from Tank Properties' roof type
    assert any("run into each other" in text for text in texts)  # the lisp's defaults: no setback
    setback = entries[5]  # rafter count, width, depth, inner trim, outer trim, setback
    setback.delete(0, "end")
    setback.insert(0, "12")
    page.update_idletasks()
    canvas = next(w for w in page.winfo_children()[0].winfo_children() if isinstance(w, tk.Canvas))
    assert sum(1 for item in canvas.find_all() if canvas.type(item) == "polygon") == 12 * 3  # rafters and 2 clips
    framing = read_framing({"rafter_count": "8", "setback_in": "12", "pipe_dia": "8.625"}, True, INTERNAL, False,
                           RIGHT)
    assert framing.count == 8 and framing.column.pipe_od_in == 8.625 and not framing.clips


def test_the_plan_puts_0_at_12_oclock_and_grows_clockwise(tk_window):
    import tkinter as tk

    from swauto.tank.framing_gui import draw

    canvas = tk.Canvas(tk_window, width=300, height=300)
    draw(canvas, layout(Framing(setback_in=12.0), ROOF))
    items = canvas.find_all()
    x0, y0, x1, y1 = canvas.coords(next(i for i in items if canvas.type(i) == "oval"))  # the landing circle
    label = next(i for i in items if canvas.type(i) == "text" and canvas.itemcget(i, "text") == "0°")
    assert canvas.coords(label)[1] < (y0 + y1) / 2.0
    xs = canvas.coords(next(i for i in items if canvas.type(i) == "polygon"))[0::2]  # rafter 1, at 105°
    assert sum(xs) / len(xs) > (x0 + x1) / 2.0  # just past 3 o'clock
