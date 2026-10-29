"""The Roof Nozzles tab: a grid like the shell one, placed on the Roof tab's cone and drawn in plan."""

import tkinter as tk
from tkinter import ttk

from swauto.nozzle.gui import MORE_ROWS, START_ROWS
from swauto.nozzle.roof_gui import blank_row, build_roof_nozzle_tab, check_rows, draw_plan, nozzle_from_row, row_values
from swauto.nozzle.roof_spec import DIRECT
from swauto.tank.roof import RoofSpec

ROOF = RoofSpec(inside_radius_in=600.0, outside_radius_in=600.5, shell_height_in=480.0, slope_in_per_ft=0.75,
                thickness_in=0.1875)


def _texts(widget) -> list[str]:
    """What the widgets show: their text, or their text variable's value."""
    found: list[str] = []
    for child in widget.winfo_children():
        if "textvariable" in child.keys() and str(child.cget("textvariable")):
            found.append(str(child.getvar(str(child.cget("textvariable")))))
        elif "text" in child.keys():
            found.append(str(child.cget("text")))
        found.extend(_texts(child))
    return found


def _find(widget, text: str):
    for child in widget.winfo_children():
        if "text" in child.keys() and str(child.cget("text")) == text:
            return child
        found = _find(child, text)
        if found is not None:
            return found
    return None


def _row(**typed) -> dict:
    values = blank_row()
    values.update(typed)
    return values


def test_roof_nozzles_tab_opens_with_thirty_rows_and_reads_the_roof_tab(tk_window):
    page = ttk.Frame(tk_window)
    shared: dict = {"roof": ROOF}
    build_roof_nozzle_tab(page, tk.StringVar(), shared)
    page.update_idletasks()
    texts = _texts(page)
    assert "Build on roof" in texts
    assert str(START_ROWS) in texts and str(START_ROWS + 1) not in texts
    assert any(text.startswith("Cone roof, 0.75 in/ft") for text in texts)
    assert shared["roof_nozzles"] == []
    _find(page, f"Add {MORE_ROWS} rows").invoke()
    assert str(START_ROWS + MORE_ROWS) in _texts(page)
    shared["load_roof_nozzles"]([nozzle_from_row(_row(mark="R1", size="6", radial="300", value="30"))])
    assert [nozzle.mark for nozzle in shared["roof_nozzles"]] == ["R1"]


def test_grid_rows_skip_blanks_and_flag_what_is_wrong():
    checks = check_rows(
        [
            _row(mark="R1", size="6", degree="90", radial="300", value="30"),
            blank_row(),
            _row(mark="R2", size="4", value="30"),  # no radial
            _row(mark="R3", size="6", radial="598", value="30"),  # past the landing
            _row(mark="R4", size="6", radial="300", value="30", isp="0.1"),  # short of the underside
        ],
        ROOF,
    )
    assert checks[0].ok and checks[0].message.startswith("OK") and "ISP AUTO" in checks[0].message
    assert checks[0].placed is not None and abs(checks[0].placed.outside_projection_in - 11.062) < 0.01
    assert checks[1].blank
    assert not checks[2].ok and "radial" in checks[2].message
    assert not checks[3].ok and "landing" in checks[3].message
    assert not checks[4].ok and "low side" in checks[4].message


def test_a_mark_on_two_rows_and_rows_without_a_roof():
    row = _row(mark="R1", size="6", radial="300", value="30")
    checks = check_rows([row, dict(row, degree="45")], ROOF)
    assert [check.ok for check in checks] == [False, False] and "rows 1, 2" in checks[0].message
    alone = check_rows([row], None)
    assert alone[0].ok and alone[0].nozzle is not None and "Roof tab" in alone[0].message


def test_a_row_reads_back_from_its_saved_nozzle():
    typed = _row(mark="R7", service="Vent", item="Class 300 slip-on", size="8", schedule="XS", degree="120",
                 radial="250", offset="-6", mode="Direct OSP", value="10", isp="7", inside_flange="Weld neck",
                 repad="Custom", pad_od="22", pad_id="9", pad_thk="0.25", style="Tombstone")
    nozzle = nozzle_from_row(typed)
    assert nozzle.projection == DIRECT and nozzle.isp_in == 7.0 and nozzle.inside_flange == "wn"
    assert nozzle.rating == 300 and nozzle.kind == "so" and nozzle.repad_style == "tombstone"
    assert nozzle_from_row(row_values(nozzle)) == nozzle


def test_the_plan_draws_the_roof_the_nozzles_and_their_pads(tk_window):
    canvas = tk.Canvas(tk_window, width=340, height=340)
    rows = [_row(mark="R1", size="6", radial="300", value="30", repad="Default"),
            _row(mark="R2", size="6", degree="180", radial="560", value="30", repad="Default", style="Tombstone")]
    placed = [check.placed for check in check_rows(rows, ROOF)]
    draw_plan(canvas, ROOF, placed)
    kinds = [canvas.type(item) for item in canvas.find_all()]
    assert kinds.count("polygon") == 2  # the two pads
    assert {"R1", "R2"} <= {canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text"}
    draw_plan(canvas, None, [])
    assert [canvas.type(item) for item in canvas.find_all()] == ["text"]


def test_the_plan_puts_0_at_12_oclock_and_grows_clockwise(tk_window):
    canvas = tk.Canvas(tk_window, width=340, height=340)
    rows = [_row(mark="N0", size="6", degree="0", radial="300", value="30"),
            _row(mark="N90", size="6", degree="90", radial="300", value="30")]
    draw_plan(canvas, ROOF, [check.placed for check in check_rows(rows, ROOF)])
    at = {canvas.itemcget(item, "text"): canvas.coords(item) for item in canvas.find_all()
          if canvas.type(item) == "text"}
    assert at["0°"][1] < at["180°"][1] and at["90°"][0] > at["270°"][0]  # 0 at the top, 90 on the right
    assert at["N0"][1] < at["N90"][1] and at["N90"][0] > at["N0"][0]


def test_the_plan_shows_the_roof_framing_rafters_under_the_nozzles(tk_window):
    from swauto.tank.framing import Framing, layout

    canvas = tk.Canvas(tk_window, width=340, height=340)
    framing = layout(Framing(setback_in=12.0), ROOF)
    draw_plan(canvas, ROOF, [], framing)
    assert sum(1 for item in canvas.find_all() if canvas.type(item) == "polygon") == 12
