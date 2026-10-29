"""Tabs follow the diameter on Tank Properties, unless it was typed over."""

import tkinter as tk
from tkinter import ttk

from swauto.tank.floor_gui import build_floor_tab
from swauto.tank.follow import follow_tank
from swauto.tank.spec import Course, TankSpec


def _tank(diameter: float) -> TankSpec:
    return TankSpec(diameter_in=diameter, diameter_basis="od", courses=[Course(96.0, 1.0)])


def test_a_value_follows_the_tank_until_it_is_typed_over(tk_window):
    root = tk_window
    book = ttk.Notebook(root)
    first, page = ttk.Frame(book), ttk.Frame(book)
    book.add(first)
    book.add(page)
    holder = {"spec": _tank(607.0)}
    var = tk.StringVar(master=root, value="606")
    sync = follow_tank(page, holder, [var], lambda tank: [f"{tank.diameter_in:g}"])
    sync()  # the tab is not showing: nothing changes
    assert var.get() == "606"
    book.select(page)
    sync()
    assert var.get() == "607"
    holder["spec"] = _tank(620.0)
    sync()
    assert var.get() == "620"  # still what was filled in, so it keeps following
    var.set("640")  # typed over: someone's own number
    holder["spec"] = _tank(700.0)
    sync()
    assert var.get() == "640"


def test_the_floor_tab_takes_the_shell_od_when_it_is_shown(tk_window):
    root = tk_window
    book = ttk.Notebook(root)
    first, floor = ttk.Frame(book), ttk.Frame(book)
    book.add(first)
    book.add(floor)
    holder = {"spec": _tank(607.0)}
    build_floor_tab(floor, tk.StringVar(master=root), holder)
    book.select(floor)
    root.update()
    texts = []

    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Entry):
                texts.append(child.get())
            walk(child)

    walk(floor)
    assert "607" in texts
