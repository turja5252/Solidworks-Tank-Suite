"""The Shell Nozzles tab is a grid of nozzles typed straight into the cells."""

import math

import tkinter as tk
from tkinter import ttk

import pytest

from swauto.nozzle.gui import (
    MORE_ROWS,
    START_ROWS,
    blank_row,
    build_nozzle_tab,
    check_rows,
    nozzle_from_fields,
)
from swauto.nozzle.place import place
from swauto.nozzle.shape import bolt_centers, stations, weld_neck_loop
from swauto.tank.spec import Course, TankSpec


def _widget_texts(widget) -> list[str]:
    found: list[str] = []
    for child in widget.winfo_children():
        if "text" in child.keys():
            found.append(str(child.cget("text")))
        found.extend(_widget_texts(child))
    return found


def _find(widget, text: str):
    for child in widget.winfo_children():
        if "text" in child.keys() and str(child.cget("text")) == text:
            return child
        found = _find(child, text)
        if found is not None:
            return found
    return None


def test_shell_nozzles_tab_opens_with_thirty_rows_and_adds_more(tk_window):
    root = tk_window
    page = ttk.Frame(root)
    status = tk.StringVar()
    shared: dict = {}
    build_nozzle_tab(page, status, shared)
    page.update_idletasks()
    texts = _widget_texts(page)
    assert "Build on shell" in texts
    assert str(START_ROWS) in texts and str(START_ROWS + 1) not in texts
    assert shared["nozzles"] == []
    _find(page, f"Add {MORE_ROWS} rows").invoke()
    assert str(START_ROWS + MORE_ROWS) in _widget_texts(page)


def _row(**typed) -> dict:
    values = blank_row()
    values.update(typed)
    return values


def test_grid_rows_skip_blanks_and_flag_what_is_wrong():
    spec = TankSpec(diameter_in=200, diameter_basis="od", courses=[Course(96, 0.5)])
    good = _row(mark="N1", size="6", elevation="48", osp="8", isp="4", repad="Default")
    checks = check_rows(
        [
            good,
            blank_row(),
            _row(mark="N2", size="4", osp="8", isp="2"),  # no elevation
            _row(size="3", elevation="20", osp="8", isp="2"),  # no mark
            _row(mark="N3", size="2", elevation="500", osp="8", isp="2"),  # above the shell
        ],
        spec,
    )
    assert checks[0].ok and checks[0].nozzle is not None and checks[0].message.startswith("OK")
    assert checks[0].nozzle.repad_mode == "default"
    assert checks[1].blank and checks[1].message == ""
    assert not checks[2].ok and "elevation" in checks[2].message
    assert not checks[3].ok and "mark" in checks[3].message
    assert not checks[4].ok and "above the shell" in checks[4].message


def test_a_row_says_when_its_pad_crosses_a_course_seam():
    spec = TankSpec(diameter_in=200, diameter_basis="mw", courses=[Course(96, 0.5), Course(96, 0.375)])
    low, across, tomb = check_rows(
        [
            _row(mark="N1", size="12", elevation="40", osp="10", isp="2", repad="Default"),  # 27 in pad: 26.5 to 53.5
            _row(mark="N2", size="12", elevation="90", rotation="90", osp="10", isp="2",
                 repad="Default"),  # 76.5 to 103.5
            _row(mark="N3", size="6", elevation="100", rotation="180", osp="8", isp="2", repad="Default",
                 style="Tombstone"),  # from the floor up; round the shell from the others, which it would run into
        ],
        spec,
    )
    assert low.ok and "seam" not in low.message
    assert across.ok and across.message.endswith(", pad crosses the seam at 96 in")
    assert tomb.ok and tomb.message.endswith(", pad crosses the seam at 96 in")


def test_grid_rows_with_one_mark_twice_are_both_wrong():
    spec = TankSpec(diameter_in=200, diameter_basis="od", courses=[Course(96, 0.5)])
    row = _row(mark="N1", size="6", elevation="48", osp="8", isp="4")
    checks = check_rows([row, dict(row, elevation="60")], spec)
    assert [check.ok for check in checks] == [False, False]
    assert "rows 1, 2" in checks[0].message


def test_grid_rows_without_a_shell_still_read_the_nozzle():
    checks = check_rows([_row(mark="N1", size="6", elevation="48", osp="8", isp="4")], None)
    assert checks[0].ok and checks[0].nozzle is not None
    assert "Tank Properties" in checks[0].message


def test_adder_fields_place_a_six_inch_weld_neck():
    nozzle = nozzle_from_fields(
        "N1",
        "Class 150 weld neck",
        "6",
        "XS",
        "48",
        "0",
        "8",
        "4",
        "0",
        False,
        "default",
        "",
        "",
        "",
        "Circular",
        "1",
        "outlet",
    )
    spec = TankSpec(diameter_in=200, diameter_basis="od", courses=[Course(96, 0.5)])
    placed = place(nozzle, spec)
    assert placed.course_number == 1
    assert placed.flange.outside_diameter_in == 11.0
    assert placed.repad is not None
    assert placed.repad.outer_diameter_in == 15.75
    assert nozzle.description == "outlet"
    spot = stations(placed)
    assert spot.inner_z == -4.5  # 4 in ISP from the inside of the 0.5 in course
    assert spot.face_z == 8.0
    assert spot.hub_z < spot.back_z < spot.seat_z < spot.face_z
    loop = weld_neck_loop(placed)
    assert loop[0] == (spot.inner_z, placed.pipe.inside_diameter_in / 2.0)
    assert loop[-1] == (spot.face_z, placed.pipe.inside_diameter_in / 2.0)
    holes = bolt_centers(placed.flange.bolt_circle_in, placed.flange.bolt_count)
    assert len(holes) == 8
    # Half a bolt space off the vertical, so the holes straddle the centerline.
    assert math.degrees(math.atan2(-holes[0][0], holes[0][1])) == pytest.approx(22.5)


def test_match_radial_says_how_far_it_moves_an_offset_nozzles_face_and_is_off_for_a_radial_one(tk_window):
    """The user, 2026-10-30: "it is not clear if you match on the radial nozzles who is matching who"."""
    spec = TankSpec(diameter_in=200, diameter_basis="od", courses=[Course(96, 0.5)])
    offset = _row(mark="N1", size="6", elevation="48", osp="8", isp="4", offset="20", match=True)
    radial = _row(mark="N2", size="6", elevation="48", rotation="90", osp="8", isp="4", match=True)
    moved, still = check_rows([offset, radial], spec)
    chord = 100.0 - math.sqrt(100.0 ** 2 - 20.0 ** 2)
    assert f"face {chord:.3f} in out to the radial plane" in moved.message
    assert "radial plane" not in still.message
    page = ttk.Frame(tk_window)
    build_nozzle_tab(page, tk.StringVar(), {})
    page.update_idletasks()
    texts = _widget_texts(page)
    assert "Match radial" in texts
    assert any("Match radial (an offset nozzle only)" in text for text in texts)
