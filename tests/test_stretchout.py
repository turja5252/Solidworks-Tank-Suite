"""The shell stretchout: plates, nozzles, FTCOs and the stair on the shell, seen from outside, and what clashes."""

import math
import tkinter as tk
from tkinter import ttk

import pytest

from swauto.cleanout.spec import Cleanout
from swauto.nozzle.spec import Nozzle
from swauto.stair.landings import CLIP_PAD, KNEE_PAD, PLATFORM_KNEE_PAD, PLATFORM_PAD, StairArrangement, shell_marks
from swauto.stair.stringer import StringerMock
from swauto.stretchout.checks import clearance, find_clashes
from swauto.stretchout.gui import build_stretchout_tab
from swauto.stretchout.model import KNEES, NOZZLES, PLATES, TREADS, build_stretchout
from swauto.stretchout.svg import to_svg
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import Course, TankSpec


def _tank() -> TankSpec:
    return TankSpec(diameter_in=600.0, diameter_basis="od", courses=[Course(96.0, 1.0)] + [Course(96.0, 0.5)] * 4)


def _od(tank: TankSpec) -> float:
    return course_radii_m(tank, tank.active_courses()[0])[0] / 0.0254


def _stair(tank: TankSpec, **more) -> StairArrangement:
    stair = StringerMock(shell_od_in=_od(tank), gap_in=8.0, treads=65, rise_in=480.0 / 65, run_in=10.5)
    return StairArrangement(stair, **more)


def test_the_shell_is_seen_from_outside_with_0_degrees_at_the_right_end():
    out = build_stretchout(_tank())
    assert out.girth_in == pytest.approx(2.0 * math.pi * _od(_tank()))  # the OD, as the LISP's outline
    assert out.x_of_degrees(90.0) == pytest.approx(0.75 * out.girth_in)
    assert out.x_of_degrees(10.0) > out.x_of_degrees(20.0)  # the orientation grows to the left
    for degrees in (0.0, 45.0, 270.0, 359.0):
        assert out.degrees_of_x(out.x_of_degrees(degrees)) == pytest.approx(degrees)
    for course in range(1, 6):  # every course's plates fill the girth
        plates = [item for item in out.items if item.layer == PLATES and item.label.startswith(f"C{course} ")]
        assert sum(item.box[2] - item.box[0] for item in plates) == pytest.approx(out.girth_in)


def test_a_nozzle_lands_at_its_orientation_and_elevation():
    nozzle = Nozzle("N1", "6", elevation_in=30.0, rotation_deg=45.0, outside_projection_in=8.0, repad_mode="default")
    out = build_stretchout(_tank(), nozzles=[nozzle])
    repad = next(item for item in out.items if item.label == "N1 repad")
    x0, y0, x1, y1 = repad.box
    assert (x0 + x1) / 2.0 == pytest.approx(out.x_of_degrees(45.0), abs=0.01)
    assert (y0 + y1) / 2.0 == pytest.approx(30.0, abs=0.01)
    assert repad.lands and repad.layer == NOZZLES
    assert not [clash for clash in find_clashes(out) if clash.label.startswith("N1")]


def test_a_repad_on_a_seam_or_on_another_repad_is_flagged():
    on_seam = Nozzle("N2", "24", elevation_in=96.0, rotation_deg=180.0, outside_projection_in=10.0,
                     repad_mode="default")
    twin = Nozzle("N3", "24", elevation_in=110.0, rotation_deg=181.0, outside_projection_in=10.0,
                  repad_mode="default")
    problems = [clash.text for clash in find_clashes(build_stretchout(_tank(), nozzles=[on_seam, twin]))]
    assert "N2 repad crosses the horizontal seam under course 2" in problems
    assert any(text.startswith("N2 repad overlaps N3 repad") for text in problems)


def test_an_ftco_insert_is_a_plate_its_edges_are_seams_not_clashes():
    out = build_stretchout(_tank(), cleanouts=[Cleanout("C1", size="10'-10\"", orientation_deg=270.0,
                                                         annular_width_in=24.0)])
    insert = next(item for item in out.items if item.label == "C1 insert plate")
    assert insert.lands and not insert.on_seams
    assert not find_clashes(out)


def test_the_stairs_pads_land_where_the_build_puts_them_and_one_below_the_floor_is_flagged():
    tank = _tank()
    stair = _stair(tank, platforms=1, top_platform=True, braces=(2, 12, 30))
    marks, notes = shell_marks(stair)
    kinds = {mark.kind for mark in marks}
    assert {KNEE_PAD, CLIP_PAD, PLATFORM_PAD, PLATFORM_KNEE_PAD} <= kinds
    out = build_stretchout(tank, stair=stair)
    assert len([item for item in out.items if item.layer == TREADS]) == 66  # 65 treads and the platform's pan
    low = next(item for item in out.items if item.label == "Knee brace pad, tread 2")
    assert low.layer == KNEES and low.box[1] < 0.0
    assert any(clash.label == "Knee brace pad, tread 2" and "below the floor" in clash.problem
               for clash in find_clashes(out))
    pad = next(item for item in out.items if item.label == "Knee brace pad, tread 12")
    gap, _seam = clearance(pad, out)
    assert gap > 0.0
    assert not notes or all("tops its flight" in note for note in notes)


@pytest.mark.parametrize("ccw", [False, True])
def test_the_stair_climbs_left_when_clockwise_and_right_when_counterclockwise(ccw):
    tank = _tank()
    out = build_stretchout(tank, stair=_stair(tank, turn=math.radians(90.0), ccw=ccw))
    treads = [item for item in out.items if item.layer == TREADS]
    first, last = treads[0].box, treads[1].box
    centers = ((first[0] + first[2]) / 2.0, (last[0] + last[2]) / 2.0)
    assert (centers[1] > centers[0]) == ccw  # seen from outside, clockwise is to the left


def test_a_stair_on_another_shell_size_is_noted():
    tank = _tank()
    stair = StringerMock(shell_od_in=200.0, gap_in=8.0, treads=10, rise_in=7.5, run_in=10.5)
    out = build_stretchout(tank, stair=StairArrangement(stair))
    assert any("Stairway tab's shell OD radius" in note for note in out.notes)


def test_the_picture_has_the_clashes_written_under_it():
    on_seam = Nozzle("N2", "24", elevation_in=96.0, rotation_deg=180.0, outside_projection_in=10.0,
                     repad_mode="default")
    out = build_stretchout(_tank(), nozzles=[on_seam])
    picture = to_svg(out, find_clashes(out), title="Test tank")
    assert picture.startswith("<svg") and picture.rstrip().endswith("</svg>")
    assert "N2 repad crosses the horizontal seam under course 2" in picture
    assert ">0°<" in picture and ">360°<" in picture


def test_the_tab_draws_what_the_other_tabs_hold(tk_window):
    book = ttk.Notebook(tk_window)
    first, page = ttk.Frame(book), ttk.Frame(book)
    book.add(first)
    book.add(page)
    tank = _tank()
    nozzle = Nozzle("N1", "6", elevation_in=30.0, rotation_deg=45.0, outside_projection_in=8.0)
    shared = {"spec": tank, "nozzles": [nozzle], "cleanouts": [], "stairway": lambda: _stair(tank, braces=(12,))}
    build_stretchout_tab(page, tk.StringVar(master=tk_window), shared)
    book.select(page)
    tk_window.update()
    canvas = next(child for child in page.winfo_children() if isinstance(child, ttk.Panedwindow)).panes()[0]
    assert len(tk_window.nametowidget(canvas).find_all()) > 50


def test_the_stringer_sheet_shows_each_flights_pieces_plates_and_holes():
    from swauto.stair.splitter import SplitSettings
    from swauto.stretchout.stringers import HOLES, PIECES, SPLICES, build_stringer_sheet

    stair = StringerMock(shell_od_in=300.0, gap_in=8.0, treads=39, rise_in=7.5, run_in=10.5)
    sheet = build_stringer_sheet(StairArrangement(stair, platforms=1, splits=SplitSettings()))
    assert not sheet.wraps
    parts = [item for item in sheet.items if item.layer == PIECES]
    assert [item.label for item in parts[:2]] == ["INNER Flight 1 Part 1", "INNER Flight 1 Part 2"]
    assert len(parts) == 8 and len([item for item in sheet.items if item.layer == SPLICES]) == 4
    assert "7/16 in holes 20, 13/16 in holes 4, slotted holes 0" in parts[0].info  # 10 treads, splice, ends
    outer = next(item for item in parts if item.label == "OUTER Flight 2 Part 2")
    assert "13/16 in holes 2, slotted holes 2" in outer.info
    assert any(item.layer == HOLES for item in sheet.items)
    whole = build_stringer_sheet(StairArrangement(stair, platforms=1))
    assert len([item for item in whole.items if item.layer == PIECES]) == 4  # not split: one piece a stringer


def test_the_tab_switches_to_the_developed_stringers(tk_window):
    from swauto.stretchout.gui import STRINGER_VIEW

    book = ttk.Notebook(tk_window)
    first, page = ttk.Frame(book), ttk.Frame(book)
    book.add(first)
    book.add(page)
    tank = _tank()
    shared = {"spec": tank, "nozzles": [], "cleanouts": [], "stairway": lambda: _stair(tank)}
    build_stretchout_tab(page, tk.StringVar(master=tk_window), shared)
    book.select(page)
    tk_window.update()
    (view,) = [w for w in _all(page) if isinstance(w, ttk.Combobox)]
    view.set(STRINGER_VIEW)
    view.event_generate("<<ComboboxSelected>>")
    tk_window.update()
    canvas = next(child for child in page.winfo_children() if isinstance(child, ttk.Panedwindow)).panes()[0]
    assert len(tk_window.nametowidget(canvas).find_all()) > 10


def _all(widget):
    for child in widget.winfo_children():
        yield child
        yield from _all(child)
