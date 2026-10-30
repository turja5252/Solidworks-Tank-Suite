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


def test_the_splitters_show_in_the_summary_and_plan_and_keep_off_the_posts(tab):
    _type(_entry(tab, "Shell height"), "120")  # 16 treads of 7.5 in, one cut at the 8.5 ft max span
    split = next(w for w in _widgets(tab) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "Split stringers")
    split.invoke()
    assert "cut between treads 8 and 9 (2 pieces), the splice holes 1.365 in off the cut" in _summary(tab)
    assert "every bolt's washer clears the treads and their bolts" in _summary(tab)
    lines = [(canvas, item) for canvas in _widgets(tab) if isinstance(canvas, tk.Canvas)
             for item in canvas.find_all() if canvas.type(item) == "line"]
    assert sum(1 for canvas, item in lines if canvas.itemcget(item, "fill") == "#0f766e") == 2  # inner and outer
    _type(_entry(tab, "Posts at flight treads"), "8")
    assert "cut between treads 9 and 10" in _summary(tab)


def _box(tab, text: str):
    return next(w for w in _widgets(tab) if isinstance(w, ttk.Checkbutton | ttk.Radiobutton) and w.cget("text") == text)


def _arcs(tab, fill: str) -> list[tuple]:
    return [tuple(c.coords(i)) for c in _widgets(tab) if isinstance(c, tk.Canvas) for i in c.find_all()
            if c.type(i) == "line" and c.itemcget(i, "fill") == fill]


def test_the_splitters_count_brace_treads_over_every_flight_and_show_clashes(tab):
    _type(_entry(tab, "Shell height"), "232.5")
    _type(_entry(tab, "Mid platforms"), "1")  # two flights of 16, 32 pans
    assert _entry(tab, "Treads").get() == "31"
    _box(tab, "Split stringers").invoke()
    assert "cut between treads 8 and 9" in _summary(tab)
    teal = _arcs(tab, "#0f766e")
    assert len(teal) == 4 and len(set(teal)) == 4  # inner and outer, each flight in its own place
    _type(_entry(tab, "Braces under treads"), "24")  # pan 24 is flight 2's tread 8
    assert "cut between treads 9 and 10" in _summary(tab)
    _box(tab, "Knee brace to the shell").invoke()  # the inner clip alone still keeps the cut off
    assert "cut between treads 9 and 10" in _summary(tab)
    _box(tab, "Inner clip to the shell").invoke()  # the bare cross brace is bolted through both stringers
    assert "cut between treads 9 and 10" in _summary(tab)
    _type(_entry(tab, "Braces under treads"), "")
    assert "cut between treads 8 and 9" in _summary(tab)
    _type(_entry(tab, "plate height"), "6.5")  # its top edge runs over tread 9's bolts
    assert "Check:" in _summary(tab) and "the plate is on a tread 9 bolt's washer." in _summary(tab)
    assert len(_arcs(tab, "#d40000")) == 4 and not _arcs(tab, "#0f766e")


def test_a_max_span_too_short_for_the_flight_says_so(tab):
    _type(_entry(tab, "Shell height"), "120")  # 16 treads
    _box(tab, "Split stringers").invoke()
    max_span = _box(tab, "Max span")
    span = next(w for w in max_span.master.pack_slaves()[max_span.master.pack_slaves().index(max_span) + 1:]
                if isinstance(w, ttk.Entry))
    _type(span, "0.5")
    assert "Splitters: a 0.5 ft max span needs 20 pieces a flight, more than its 16 treads" in _summary(tab)


@pytest.mark.parametrize("typed", ["inf", "-inf", "1e400", "nan"])
def test_a_brace_tread_that_is_not_a_number_says_so_with_the_splitters_on(tab, typed):
    _type(_entry(tab, "Shell height"), "120")
    _box(tab, "Split stringers").invoke()
    _type(_entry(tab, "Braces under treads"), typed)
    shown = [str(w.cget("text")) for w in _widgets(tab) if isinstance(w, ttk.Label)]
    assert any("Brace treads are whole tread numbers" in text for text in shown)


def test_the_stage_plan_follows_the_splitter_steps_with_its_rounds():
    plan = _stair_stage_plan(16, shell=False, split_treads=(8,), split_rounds=((2, 1),))
    keys = [sorted(key)[0] for key, _label in plan if any(k.startswith("EliteSplit") for k in key)]
    # The plate's holes go in before its trims and round: the order in which it still flattens.
    assert keys[:7] == ["EliteSplitInT08 cut", "EliteSplitInT08 round 1", "EliteSplitInT08 round 2",
                        "EliteSplitInT08 splice placed", "EliteSplitInT08 holes cut", "EliteSplitIn splices trimmed",
                        "EliteSplitInT08 plate round"]
    assert "EliteSplitOutT08 round 1" not in keys  # the outer stringer has no rounds
    labels = [label for _key, label in plan]
    assert "inner stringer split" in labels and "outer stringer split" in labels


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


def test_placing_by_the_rules_drives_the_arrangement_and_the_stage_plan(tk_window):
    from swauto.stair.game import TRAY, Game

    page = ttk.Frame(tk_window)
    shared: dict = {}
    build_stringer_tab(page, tk.StringVar(master=tk_window), shared)
    _type(_entry(page, "Shell height"), "480")  # 64 treads
    _box(page, "Split stringers").invoke()
    _box(page, "Place by the rules").invoke()
    assert "By the rules: knee braces at treads" in _summary(page)
    assert "No tank: the pads are not checked" in _summary(page)
    planned = shared["stairway"]()
    assert planned.clips is not None and 1 in planned.clips  # the ground clip
    assert planned.splits.fixed == (13, 26, 38, 51)  # the 8.5 ft span's five pieces, kept off the ground clip
    assert set(planned.braces) <= set(range(2, 64))
    # What the game pins is what the tab builds.
    game = Game(shared["stairway_base"](), None, shared["stair_rules"]())
    old = game.plan.of_kind("knee brace")[0]
    assert game.drop(next(p for p in TRAY if p.kind == "knee brace"), 0, old.tread + 1, moving=old)[0]
    shared["stair_game"] = game
    assert old.tread + 1 in shared["stairway"]().braces and old.tread not in shared["stairway"]().braces
    stages = _stair_stage_plan(64, braces=(10,), knees=True, inner=True, clips=(1, 10))
    labels = [label for _key, label in stages]
    assert "knee brace 10" in labels and "inner clip 1" in labels and "inner clip 10" in labels
    assert labels.index("knee brace 10") < labels.index("inner clip 1")


def test_the_tab_and_its_game_come_back_from_a_project(tk_window):
    from swauto.stair.attachments import POST, Spot
    from swauto.stair.game import TRAY, Game

    page = ttk.Frame(tk_window)
    shared: dict = {}
    build_stringer_tab(page, tk.StringVar(master=tk_window), shared)
    _type(_entry(page, "Shell height"), "480")
    _box(page, "Place by the rules").invoke()
    game = Game(shared["stairway_base"](), None, shared["stair_rules"]())
    assert game.drop(next(p for p in TRAY if p.kind == POST and p.side == "outer"), 0, 12)[0]
    shared["stair_game"] = game
    saved = shared["stairway_inputs"]()
    assert saved["shell_height"] == "480" and saved["by_the_rules"] is True
    assert saved["game"]["pins"] == [[POST, 0, 12, "outer"]]

    other = ttk.Frame(tk_window)
    fresh: dict = {}
    build_stringer_tab(other, tk.StringVar(master=tk_window), fresh)
    fresh["load_stairway"](saved)
    assert _entry(other, "Shell height").get() == "480" and _entry(other, "Treads").get() == "64"
    assert fresh["stair_game"].choice.pins == (Spot(POST, 0, 12, "outer", pinned=True),)
    assert any(s.tread == 12 and s.pinned for s in fresh["stair_game"].plan.of_kind(POST, "outer"))
    assert "By the rules:" in _summary(other)


def test_by_the_rules_the_typed_braces_are_not_read(tk_window):
    page = ttk.Frame(tk_window)
    shared: dict = {}
    build_stringer_tab(page, tk.StringVar(master=tk_window), shared)
    _type(_entry(page, "Shell height"), "480")
    _type(_entry(page, "Braces under treads"), "99")
    _box(page, "Place by the rules").invoke()
    assert "By the rules:" in _summary(page)
    assert shared["stairway"]().braces  # the plan's knee braces, not the typed 99


def test_opening_a_project_puts_its_treads_back_and_drops_the_last_game(tk_window):
    from swauto.stair.game import Game

    page = ttk.Frame(tk_window)
    shared: dict = {}
    build_stringer_tab(page, tk.StringVar(master=tk_window), shared)
    _type(_entry(page, "Shell height"), "480")
    _type(_entry(page, "Mid platforms"), "1")
    shared["stair_game"] = Game(shared["stairway_base"](), None, shared["stair_rules"]())
    shared["load_stairway"]({"shell_height": "480", "mid_platforms": "0", "treads": "65"})
    assert _entry(page, "Treads").get() == "65" and _entry(page, "Mid platforms").get() == "0"
    assert "stair_game" not in shared


def test_the_3d_view_draws_the_tabs_plan_and_survives_a_stale_game(tk_window):
    from swauto.stair.game import Game
    from swauto.stretchout.gui import VIEW_3D, build_stretchout_tab

    book = ttk.Notebook(tk_window)
    stairway, page = ttk.Frame(book), ttk.Frame(book)
    book.add(stairway)
    book.add(page)
    shared: dict = {}
    build_stringer_tab(stairway, tk.StringVar(master=tk_window), shared)
    _type(_entry(stairway, "Shell height"), "480")
    _type(_entry(stairway, "Treads"), "61")
    _type(_entry(stairway, "Mid platforms"), "2")
    _box(stairway, "Place by the rules").invoke()
    shared["stair_game"] = Game(shared["stairway_base"](), None, shared["stair_rules"]())
    _type(_entry(stairway, "Mid platforms"), "0")
    build_stretchout_tab(page, tk.StringVar(master=tk_window), shared)
    view = next(w for w in _widgets(page) if isinstance(w, ttk.Combobox) and VIEW_3D in w.cget("values"))
    view.set(VIEW_3D)
    view.event_generate("<<ComboboxSelected>>")
    tk_window.update()
    frame = next(w for w in page.winfo_children() if hasattr(w, "view_state"))
    labels = {f.label for f in frame.view_state["faces"]}
    assert any(label.startswith("Outer post") for label in labels)
