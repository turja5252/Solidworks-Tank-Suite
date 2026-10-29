"""The FTCO tab: rows typed into a grid, read as FTCOs and checked on course 1."""

import tkinter as tk
from tkinter import ttk

from swauto.cleanout.gui import START_ROWS, blank_row, build_cleanout_tab, check_rows, cleanout_from_row
from swauto.tank.spec import Course, TankSpec


def _tank() -> TankSpec:
    return TankSpec(diameter_in=607.0, diameter_basis="od", courses=[Course(96.0, 1.0)])


def _row(**typed) -> dict:
    values = blank_row()
    values.update(mark="C1", orientation_deg="0", annular_width_in="24")
    values.update(typed)
    return values


def test_blank_thicknesses_take_the_engine_defaults():
    ftco = cleanout_from_row(_row(gasket_material="Garlock 3000", repad_thk_in="0.75"))
    assert ftco.size == "12'-5\""
    assert ftco.anchor == "none"
    assert (ftco.insert_thk_in, ftco.repad_thk_in, ftco.gasket_thk_in) == (1.0, 0.75, 0.125)
    assert ftco.gasket_material == "Garlock 3000"


def test_rows_are_checked_one_by_one_and_together():
    checks = check_rows(
        [
            _row(size="10'-10\"", anchor="Left"),
            blank_row(),
            _row(mark="C2", orientation_deg="", annular_width_in="24"),
            _row(mark="C3", orientation_deg="180", flange_thk_in="thick"),
        ],
        _tank(),
    )
    assert checks[0].ok and checks[0].message.startswith("OK  10'-10\" (48 x 36)")
    assert checks[1].ok and checks[1].cleanout is None and checks[1].message == ""
    assert not checks[2].ok and "orientation" in checks[2].message
    assert not checks[3].ok and "flange" in checks[3].message


def test_two_anchors_or_overlaps_fail_every_row():
    checks = check_rows([_row(anchor="Left"), _row(mark="C2", orientation_deg="180", anchor="Right")], _tank())
    assert [check.ok for check in checks] == [False, False]
    assert "one FTCO can be anchored" in checks[0].message


def test_tab_opens_with_four_rows_and_gives_the_tank_its_gaps(tk_window):
    root = tk_window
    page = ttk.Frame(root)
    shared: dict = {"spec": _tank()}
    build_cleanout_tab(page, tk.StringVar(), shared)
    page.update_idletasks()
    assert shared["cleanouts"] == []
    assert shared["course_one_gaps"](_tank()) == []
    texts = []

    def walk(widget):
        for child in widget.winfo_children():
            if "text" in child.keys():
                texts.append(str(child.cget("text")))
            walk(child)

    walk(page)
    assert str(START_ROWS) in texts and str(START_ROWS + 1) not in texts
    assert "Build on shell" in texts and "Add row" in texts
