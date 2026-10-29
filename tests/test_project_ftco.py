"""FTCOs in a project: seven pieces as parts, turned to the FTCO's orientation, shared when identical."""

import math
from dataclasses import replace
from pathlib import Path

import pytest

from swauto.cleanout.spec import PIECES, Cleanout
from swauto.project.items import FTCO_PIECE, ftco_items
from swauto.project.project import Project
from swauto.tank.spec import Course, TankSpec


def _tank() -> TankSpec:
    return TankSpec(diameter_in=750.0, courses=[Course(96.0, 1.0), Course(96.0, 0.75)])


def _ftco(mark: str, orientation: float, **more) -> Cleanout:
    return Cleanout(mark, size="10'-10\"", orientation_deg=orientation, annular_width_in=24.0, **more)


def test_one_ftco_is_seven_parts_turned_to_its_orientation():
    items = ftco_items(_tank(), [_ftco("C1", 60.0)])
    assert len(items) == len(PIECES) == 7
    assert {item.kind for item in items} == {FTCO_PIECE}
    assert "FTCO 10-10 insert plate A.SLDPRT" in {item.file for item in items}
    for item in items:
        (placement,) = item.placements
        assert placement.azimuth_rad == pytest.approx(math.radians(60.0))
        upright, piece, *_ = item.source
        assert upright.orientation_deg == 0.0 and piece == item.params["piece"]


def test_identical_ftcos_share_every_file_and_a_gasket_change_splits_only_the_gasket():
    same = ftco_items(_tank(), [_ftco("C1", 60.0), _ftco("C2", 240.0)])
    assert len(same) == 7 and all(len(item.placements) == 2 for item in same)
    other = ftco_items(_tank(), [_ftco("C1", 60.0), _ftco("C2", 240.0, gasket_material="Garlock 3000")])
    by_family = {}
    for item in other:
        by_family.setdefault(item.file.rsplit(" ", 1)[0], []).append(item)
    assert len(by_family["FTCO 10-10 gasket"]) == 2
    assert all(len(files) == 1 for family, files in by_family.items() if family != "FTCO 10-10 gasket")


def test_a_project_with_an_ftco_leaves_course_one_open_for_its_insert(tmp_path: Path):
    project = Project(folder=tmp_path, name="T", spec=_tank(), cleanouts=[_ftco("C1", 0.0, anchor="left")])
    items = project.items()
    course1 = [item for item in items if item.file.startswith("Shell C1")]
    developed = sum(item.params["length_in"] * len(item.placements) for item in course1)
    circumference = math.pi * 750.0  # 750 in mid-wall
    assert developed == pytest.approx(circumference - 130.0)
    assert sum(1 for item in items if item.kind == FTCO_PIECE) == 7
    # A thicker repad rebuilds the repad, neck, flange, gasket, cover and bottom plate, not the insert.
    before = {item.params["piece"]: item.fingerprint for item in items if item.kind == FTCO_PIECE}
    project.cleanouts = [replace(project.cleanouts[0], repad_thk_in=1.25)]
    after = {item.params["piece"]: item.fingerprint for item in project.items() if item.kind == FTCO_PIECE}
    assert [piece for piece in PIECES if before[piece] == after[piece]] == ["Insert"]
