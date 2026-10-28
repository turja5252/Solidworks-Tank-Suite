import json
from pathlib import Path

from swauto.tank.floor import FloorSpec
from swauto.tank.project import StairParams, TankProject
from swauto.tank.roof import RoofSpec
from swauto.tank.spec import Course, TankSpec, WALL_OD


def test_derived_dims_follow_shell():
    shell = TankSpec(
        diameter_in=240.0,
        diameter_basis=WALL_OD,
        stack=WALL_OD,
        courses=[Course(96.0, 0.5), Course(96.0, 0.375)] + [Course(0.0, 0.0)] * 6,
    )
    project = TankProject(shell=shell)
    assert abs(project.course1_od_in() - 240.0) < 1e-6
    assert abs(project.floor.diameter_in - 240.0) < 1e-6
    assert abs(project.roof.shell_height_in - 192.0) < 1e-6
    assert abs(project.roof.outside_radius_in - 120.0) < 1e-6


def test_listeners_fire_on_shell_change():
    project = TankProject()
    seen: list[str] = []
    project.subscribe(lambda _p, reason: seen.append(reason))
    project.set_shell(
        TankSpec(
            diameter_in=120.0,
            diameter_basis=WALL_OD,
            courses=[Course(48.0, 0.25)] + [Course(0.0, 0.0)] * 7,
        )
    )
    assert "shell" in seen
    assert abs(project.floor.diameter_in - 120.0) < 1e-6


def test_dict_bridge_matches_legacy_holder():
    project = TankProject()
    shell = TankSpec(
        diameter_in=100.0,
        diameter_basis=WALL_OD,
        courses=[Course(40.0, 0.25)] + [Course(0.0, 0.0)] * 7,
    )
    project["spec"] = shell
    assert project.get("spec") is project.shell
    assert abs(project.course1_od_in() - 100.0) < 1e-6
    project["live"] = object()
    assert project.get("live") is project.live


def test_project_json_roundtrip(tmp_path: Path):
    project = TankProject(
        shell=TankSpec(
            diameter_in=180.0,
            diameter_basis=WALL_OD,
            courses=[Course(72.0, 0.5)] + [Course(0.0, 0.0)] * 7,
        ),
        floor=FloorSpec(diameter_in=180.0, thickness_in=0.375),
        roof=RoofSpec(slope_in_per_ft=1.0, thickness_in=0.3125),
        stair=StairParams(treads=12, gap_in=6.0),
    )
    path = tmp_path / "demo.tank.json"
    project.save_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert "shell" in raw and "floor" in raw and "roof" in raw and "stair" in raw
    loaded = TankProject.load_json(path)
    assert loaded.shell.diameter_in == 180.0
    assert loaded.stair.treads == 12
    assert abs(loaded.floor.diameter_in - 180.0) < 1e-6
