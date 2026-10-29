"""The Stairway tab: the height drives the treads, rise and run, and the stair climbs either way."""

import math
import tkinter as tk
from tkinter import ttk

import pytest

from swauto.stair.stringer_gui import _stair_stage_plan, build_stringer_tab, plan_xy
from swauto.tank.spec import Course, TankSpec


def _widgets(widget):
    for child in widget.winfo_children():
        yield child
        yield from _widgets(child)


def _label(tab, text: str) -> ttk.Label:
    for widget in _widgets(tab):
        if isinstance(widget, ttk.Label) and str(widget.cget("text")) == text:
            return widget
    raise AssertionError(f"no label {text!r}")


def _entry(tab, label: str) -> ttk.Entry:
    """The entry beside a label, on the tab's grid or in the label's own row of packed widgets."""
    found = _label(tab, label)
    if found.winfo_manager() == "grid":
        info = found.grid_info()
        for widget in found.master.grid_slaves(row=int(info["row"]), column=int(info["column"]) + 1):
            if isinstance(widget, ttk.Entry):
                return widget
    siblings = found.master.pack_slaves()
    for widget in siblings[siblings.index(found) + 1:]:
        if isinstance(widget, ttk.Entry):
            return widget
    raise AssertionError(f"no entry beside {label!r}")


def _type(entry: ttk.Entry, text: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, text)


def _treads_note(tab) -> str:
    info = _label(tab, "Treads").grid_info()
    (note,) = _label(tab, "Treads").master.grid_slaves(row=int(info["row"]), column=int(info["column"]) + 2)
    return str(note.cget("text"))


def _summary(tab) -> str:
    for widget in _widgets(tab):
        text = str(widget.cget("text")) if isinstance(widget, ttk.Label) else ""
        if text.startswith(("Climbs clockwise", "Climbs counter")):
            return text
    raise AssertionError("no summary")


@pytest.fixture
def tab(tk_window):
    page = ttk.Frame(tk_window)
    build_stringer_tab(page, tk.StringVar(master=tk_window))
    return page


def test_the_height_picks_the_treads_and_works_out_the_rise_and_run(tab):
    assert _entry(tab, "Treads").get() == "8" and _treads_note(tab) == "auto"
    assert (_entry(tab, "Rise").get(), _entry(tab, "Run").get()) == ("7.5", "10.5")
    _type(_entry(tab, "Shell height"), "480")
    assert _entry(tab, "Treads").get() == "64"
    assert (_entry(tab, "Rise").get(), _entry(tab, "Run").get()) == ("7.5", "10.5")
    assert "the top tread 480.000 in above the ground and at the top of the shell" in _summary(tab)


def test_typed_treads_stay_until_cleared(tab):
    _type(_entry(tab, "Treads"), "70")
    assert _treads_note(tab) == "typed"
    _type(_entry(tab, "Shell height"), "300")
    assert _entry(tab, "Treads").get() == "70"
    assert _entry(tab, "Rise").get() == _fmt(300 / 70)
    _type(_entry(tab, "Treads"), "")
    assert _entry(tab, "Treads").get() == ""  # not while typing
    _entry(tab, "Treads").event_generate("<FocusOut>")
    assert _entry(tab, "Treads").get() == "40" and _treads_note(tab) == "auto"


def test_mid_platforms_pick_treads_that_split_into_equal_flights(tab):
    _type(_entry(tab, "Shell height"), "300")
    _type(_entry(tab, "Mid platforms"), "1")
    assert _entry(tab, "Treads").get() == "41"
    assert "2 flights of 21" in _summary(tab)


def test_the_climb_can_turn_either_way(tab):
    assert _summary(tab).startswith("Climbs clockwise")
    (ccw,) = [w for w in _widgets(tab) if isinstance(w, ttk.Radiobutton) and w.cget("text") == "Counterclockwise"]
    ccw.invoke()
    assert _summary(tab).startswith("Climbs counterclockwise")


def test_the_height_and_diameter_follow_tank_properties(tk_window):
    book = ttk.Notebook(tk_window)
    first, page = ttk.Frame(book), ttk.Frame(book)
    book.add(first)
    book.add(page)
    tank = TankSpec(diameter_in=600.0, diameter_basis="od", courses=[Course(96.0, 1.0)] * 5)
    build_stringer_tab(page, tk.StringVar(master=tk_window), {"spec": tank})
    book.select(page)
    tk_window.update()
    assert (_entry(page, "Diameter").get(), _entry(page, "Shell height").get()) == ("600", "480")
    assert _entry(page, "Treads").get() == "64"


def test_the_plan_puts_0_at_12_oclock_and_grows_clockwise():
    assert plan_xy(100.0, 0.0) == pytest.approx((0.0, 100.0))  # 0 deg is +Z, at the top
    assert plan_xy(100.0, math.pi / 2) == pytest.approx((100.0, 0.0))  # 90 deg is -X, at 3 o'clock
    assert plan_xy(100.0, -0.1)[0] < 0 < plan_xy(100.0, 0.1)[0]  # clockwise turns right from the top


def test_offsets_move_the_ends_and_the_treads_follow_the_stair_height(tab):
    _type(_entry(tab, "Shell height"), "480")
    _type(_entry(tab, "Top offset"), "8")
    _type(_entry(tab, "Bottom offset"), "6")
    assert _entry(tab, "Stair height").get() == "478"
    assert _entry(tab, "Treads").get() == "64"
    assert _entry(tab, "Rise").get() == _fmt(478 / 64)
    summary = _summary(tab)
    assert "the ground 6 in below the floor" in summary
    assert "8 in below the top of the shell" in summary


def test_either_end_goes_to_the_orientation(tab):
    assert "The foot is at 0.00°" in _summary(tab)
    _type(_entry(tab, "Orientation"), "90")
    (end,) = [w for w in _widgets(tab) if isinstance(w, ttk.Radiobutton) and w.cget("text") == "End (top)"]
    end.invoke()
    assert "the top end at 90.00°" in _summary(tab)
    (ccw,) = [w for w in _widgets(tab) if isinstance(w, ttk.Radiobutton) and w.cget("text") == "Counterclockwise"]
    ccw.invoke()
    (start,) = [w for w in _widgets(tab) if isinstance(w, ttk.Radiobutton) and w.cget("text") == "Start (foot)"]
    start.invoke()
    _type(_entry(tab, "Orientation"), "185")
    assert "The foot is at 185.00°" in _summary(tab)


def _fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def test_a_counterclockwise_build_ends_with_the_mirror():
    plain = _stair_stage_plan(8)
    mirrored = _stair_stage_plan(8, ccw=True)
    assert mirrored[: len(plain)] == plain
    assert [label for _keys, label in mirrored[len(plain):]] == ["counterclockwise mirror", "clockwise stair deleted"]
