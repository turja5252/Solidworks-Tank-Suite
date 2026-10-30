"""Projects: the build list, part sharing, change tracking, and the project file."""

import math
from dataclasses import replace

import pytest

from swauto.cleanout.layout import course_one_gaps
from swauto.cleanout.spec import Cleanout
from swauto.nozzle.spec import Nozzle
from swauto.project.items import Placement, shell_items
from swauto.project.project import BUILT, CHANGED, FAILED, NEW, Project, safe_name
from swauto.tank.spec import Course, TankSpec


def _tank(c1_thk: float = 1.0, stack: str = "od") -> TankSpec:
    """Outsides stacked, so changing course 1 leaves course 2 where it is."""
    return TankSpec(diameter_in=607.0, diameter_basis="od", stack=stack,
                    courses=[Course(96.0, c1_thk), Course(96.0, 0.75)])


def _ftco(anchor: str = "left") -> Cleanout:
    return Cleanout("C1", size="10'-10\"", anchor=anchor, annular_width_in=24.0)


def test_equal_plates_share_one_file_placed_at_each_seam():
    items = shell_items(_tank())
    assert [item.file for item in items] == ["Shell C1 Plate A.SLDPRT", "Shell C2 Plate A.SLDPRT"]
    c1, c2 = items
    assert len(c1.placements) == len(c2.placements) == 4
    assert [round(math.degrees(p.azimuth_rad)) for p in c1.placements] == [0, 90, 180, 270]
    # Plates keep their real height in the part; placements only turn them.
    assert {p.at_in for p in c1.placements + c2.placements} == {(0.0, 0.0, 0.0)}
    assert c1.params["z_bot_m"] == 0.0
    assert c2.params["z_bot_m"] == pytest.approx(96.0 * 0.0254)


def test_an_ftco_splits_course_one_into_full_and_short_plates():
    tank = _tank()
    items = shell_items(tank, course_one_gaps(tank, [_ftco()]))
    c1 = sorted((item for item in items if item.file.startswith("Shell C1")), key=lambda item: -len(item.placements))
    assert [len(item.placements) for item in c1] == [3, 1]
    assert {item.file for item in c1} == {"Shell C1 Plate A.SLDPRT", "Shell C1 Plate B.SLDPRT"}
    full, short = (item.params["length_in"] for item in c1)
    assert full - short == pytest.approx(130.0)


def test_a_placement_turns_plus_x_to_its_azimuth_and_moves_it():
    t = Placement(math.radians(30.0), at_in=(10.0, 96.0, -5.0)).transform()
    # SolidWorks: row vector times the rotation, so +X goes to the first row.
    assert (t[0], t[1], t[2]) == pytest.approx((math.cos(math.radians(30)), 0.0, math.sin(math.radians(30))))
    assert (t[6], t[8]) == pytest.approx((-math.sin(math.radians(30)), math.cos(math.radians(30))))
    assert t[9:12] == pytest.approx([10.0 * 0.0254, 96.0 * 0.0254, -5.0 * 0.0254])
    assert t[12] == 1.0


def test_a_plate_keeps_the_file_that_already_holds_its_shape():
    tank = _tank()
    gaps = course_one_gaps(tank, [_ftco()])
    first = {item.file: item.fingerprint for item in shell_items(tank, gaps)}
    # Built once; the short plate is B. Lay it out again: nothing is renamed, nothing changes.
    again = {item.file: item.fingerprint for item in shell_items(tank, gaps, first)}
    assert again == first
    # Pretend the files were built the other way round: each shape still finds its own file.
    swapped = {"Shell C1 Plate A.SLDPRT": first["Shell C1 Plate B.SLDPRT"],
               "Shell C1 Plate B.SLDPRT": first["Shell C1 Plate A.SLDPRT"]}
    names = {item.fingerprint: item.file for item in shell_items(tank, gaps, swapped)}
    assert names[first["Shell C1 Plate A.SLDPRT"]] == "Shell C1 Plate B.SLDPRT"


def test_a_changed_plate_is_rebuilt_in_its_old_file():
    built = {item.file: item.fingerprint for item in shell_items(_tank(1.0))}
    thicker = shell_items(_tank(1.25), built=built)
    c1 = next(item for item in thicker if item.file.startswith("Shell C1"))
    assert c1.file == "Shell C1 Plate A.SLDPRT"
    assert c1.fingerprint != built[c1.file]
    c2 = next(item for item in thicker if item.file.startswith("Shell C2"))
    assert c2.fingerprint == built[c2.file]  # outsides stacked: course 2 did not move
    # Mid-walls stacked: course 2 sits on course 1's mid-wall, which moved, so it is rebuilt too.
    built_mw = {item.file: item.fingerprint for item in shell_items(_tank(1.0, "mw"))}
    c2_mw = next(item for item in shell_items(_tank(1.25, "mw"), built=built_mw) if item.file.startswith("Shell C2"))
    assert c2_mw.fingerprint != built_mw[c2_mw.file]


def test_project_statuses_follow_the_files(tmp_path):
    project = Project(folder=tmp_path, name="Tank 101", spec=_tank())
    item = project.items()[0]
    assert project.status(item) == NEW
    (tmp_path / item.file).write_bytes(b"part")
    project.mark(item)
    assert project.status(item) == BUILT
    project.spec = _tank(1.25)
    changed = project.items()[0]
    assert changed.file == item.file and project.status(changed) == CHANGED
    project.mark(changed, "the revolve failed")
    assert project.status(changed) == FAILED
    (tmp_path / item.file).unlink()
    assert project.status(changed) == NEW


def test_the_project_file_round_trips(tmp_path):
    nozzle = Nozzle("N1", 6, elevation_in=48.0, outside_projection_in=8.0, inside_projection_in=4.0,
                    repad_mode="default", gasket=True, gasket_material="CNAF")
    project = Project(folder=tmp_path / "job", name=safe_name("Tank 101 / East"), spec=_tank(),
                      cleanouts=[_ftco("short")], nozzles=[nozzle])
    project.mark(project.items()[0])
    path = project.save()
    assert path.name == "Tank 101 East.elite.json"
    back = Project.load(path)
    assert back.name == project.name and back.folder == project.folder
    assert back.spec.courses[:2] == project.spec.courses[:2]
    assert back.cleanouts == project.cleanouts
    assert back.nozzles == project.nozzles
    assert back.built == project.built
    assert [item.file for item in back.items()] == [item.file for item in project.items()]
    assert replace(back.nozzles[0], mark="N2").gasket_material == "CNAF"
    assert back.roof_nozzles == []  # a project saved before roof nozzles still opens


def test_roof_nozzles_are_kept_with_the_project(tmp_path):
    from swauto.nozzle.roof_spec import RoofNozzle

    vent = RoofNozzle("R1", "8", degree=135.0, radial_in=240.0, projection_in=30.0, repad_mode="default",
                      description="Vent")
    hatch = RoofNozzle("R2", "6", kind="so", radial_in=100.0, projection="osp", projection_in=8.0, isp_in=6.0,
                       inside_flange="so")
    project = Project(folder=tmp_path, name="Tank 102", spec=_tank(), roof_nozzles=[vent, hatch])
    back = Project.load(project.save())
    assert back.roof_nozzles == [vent, hatch]
    assert back.roof_nozzles[0].isp_in is None  # AUTO stays AUTO


def test_project_names_are_safe_file_names():
    assert safe_name("  Tank: 101?  ") == "Tank 101"
    with pytest.raises(ValueError):
        safe_name(" /?* ")


def test_saved_nozzles_go_back_into_the_grid_unchanged():
    from swauto.nozzle.gui import _row_nozzle, blank_row, row_values

    custom = Nozzle("N1", "6", rating=300, kind="so", elevation_in=48.0, rotation_deg=30.0,
                    outside_projection_in=8.0, inside_projection_in=4.0, offset_in=12.0, match_plane=True,
                    repad_mode="custom", repad_outer_in=16.0, repad_inner_in=7.0, repad_thickness_in=0.5,
                    repad_style="tombstone", telltale_offset_in=1.5, blind=True, gasket=True,
                    gasket_material="CNAF", gasket_thickness_in=0.0625, description="Outlet")
    plain = Nozzle("N2", "2", elevation_in=20.0, outside_projection_in=6.0, inside_projection_in=0.0)
    for nozzle in (custom, plain):
        values = row_values(nozzle)
        assert set(values) == set(blank_row())
        assert _row_nozzle(values) == nozzle


def test_saved_ftcos_go_back_into_the_grid_unchanged():
    from swauto.cleanout.gui import cleanout_from_row, row_values

    ftco = Cleanout("C2", size="10'-10\"", orientation_deg=135.0, anchor="short", insert_thk_in=1.25,
                    gasket_material="Garlock 3000", annular_width_in=30.0, chime_in=3.0, annular_thk_in=0.25)
    assert cleanout_from_row(row_values(ftco)) == ftco


def test_project_tab_opens_with_its_buttons(tk_window):
    import tkinter as tk
    from tkinter import ttk

    from swauto.project.gui import build_project_tab

    root = tk_window
    page = ttk.Frame(root)
    build_project_tab(page, tk.StringVar(), {"spec": _tank()})
    page.update_idletasks()
    texts = []

    def walk(widget):
        for child in widget.winfo_children():
            if "text" in child.keys():
                texts.append(str(child.cget("text")))
            walk(child)

    walk(page)
    for button in ("New project…", "Open project…", "Save", "Build changes", "Rebuild all", "Open assembly"):
        assert button in texts


def test_opening_a_project_fills_the_real_tabs_and_they_hand_the_inputs_back(tk_window):
    import tkinter as tk
    from tkinter import ttk

    from swauto.cleanout.gui import build_cleanout_tab
    from swauto.nozzle.gui import build_nozzle_tab
    from swauto.tank.gui import build_tank_tab

    root = tk_window
    book = ttk.Notebook(root)
    shared: dict = {}
    status = tk.StringVar()
    for builder in (build_tank_tab, build_nozzle_tab, build_cleanout_tab):
        page = ttk.Frame(book)
        book.add(page)
        builder(page, status, shared)
    saved_tank = _tank(1.25)
    nozzle = Nozzle("N7", "4", elevation_in=30.0, rotation_deg=60.0, outside_projection_in=8.0,
                    inside_projection_in=2.0, blind=True)
    ftco = Cleanout("C1", size="10'-10\"", orientation_deg=200.0, anchor="right", annular_width_in=24.0)
    shared["apply_spec"](saved_tank)
    shared["load_nozzles"]([nozzle])
    shared["load_cleanouts"]([ftco])
    root.update()
    assert shared["spec"].courses[:2] == saved_tank.courses[:2]
    assert shared["spec"].diameter_in == saved_tank.diameter_in
    assert shared["nozzles"] == [nozzle]
    assert shared["cleanouts"] == [ftco]


def test_a_same_named_file_open_from_another_folder_stops_the_build(tmp_path):
    from swauto.errors import SolidWorksError
    from swauto.project.build_sw import check_name_clashes

    class Doc:
        def __init__(self, path):
            self.GetPathName = str(path)
            self.GetNext = None

    class App:
        def __init__(self, *docs):
            for a, b in zip(docs, docs[1:]):
                a.GetNext = b
            self.GetFirstDocument = docs[0] if docs else None

    project = Project(folder=tmp_path / "tank 2", name="Tank 2", spec=_tank())
    items = project.items()
    mine = Doc(project.folder / items[0].file)
    other_folder = Doc(tmp_path / "tank 1" / items[0].file)
    unrelated = Doc(tmp_path / "tank 1" / "Bracket.SLDPRT")
    check_name_clashes(App(mine, unrelated), project, items)  # its own files and others are fine
    with pytest.raises(SolidWorksError, match="is open in SolidWorks from"):
        check_name_clashes(App(unrelated, other_folder), project, items)
    with pytest.raises(SolidWorksError, match="Tank 2.SLDASM"):
        check_name_clashes(App(Doc(tmp_path / "elsewhere" / "Tank 2.SLDASM")), project, items)


def test_the_stairway_and_its_game_are_kept_with_the_project(tmp_path):
    stairway = {"shell_height": "480", "by_the_rules": True, "handrail_on": "Both",
                "game": {"pins": [["handrail post", 0, 12, "outer"]], "removed": [["knee brace", 0, 7, ""]]}}
    project = Project(folder=tmp_path, name="Tank 103", spec=_tank(), stairway=stairway)
    back = Project.load(project.save())
    assert back.stairway == stairway
