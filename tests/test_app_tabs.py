"""Every tab the main window adds builds, through the same guarded builders it uses."""

import tkinter as tk
from tkinter import ttk

from swauto import gui
from swauto.stair.stringer_gui import build_stringer_tab
from swauto.tank.floor_gui import build_floor_tab
from swauto.tank.gui import build_tank_tab
from swauto.tank.roof_gui import build_roof_tab


def _texts(widget) -> list[str]:
    found = []
    for child in widget.winfo_children():
        if "text" in child.keys():
            found.append(str(child.cget("text")))
        found.extend(_texts(child))
    return found


def test_every_tab_loads_without_its_could_not_load_note(tk_window):
    book = ttk.Notebook(tk_window)
    shared: dict = {}
    status = tk.StringVar()
    builders = (
        build_tank_tab, build_floor_tab, build_roof_tab, gui._build_framing_tab, gui._build_nozzle_tab,
        gui._build_roof_nozzle_tab, gui._build_cleanout_tab, gui._build_anchor_tab, build_stringer_tab,
        gui._build_stretchout_tab, gui._build_project_tab,
    )
    pages = []
    for builder in builders:
        page = ttk.Frame(book)
        book.add(page)
        builder(page, status, shared)
        pages.append(page)
    tk_window.update_idletasks()
    for page in pages:
        assert not any("could not load" in text for text in _texts(page))
    assert shared.get("roof") is not None  # the Roof tab hands its cone to the roof nozzles and the framing
    assert {"roof_nozzles", "refresh_framing", "refresh_anchors"} <= set(shared)
