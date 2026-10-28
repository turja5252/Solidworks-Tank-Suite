from swauto.tank.preview import build_preview, summary_line
from swauto.tank.project import TankProject
from swauto.tank.spec import Course, TankSpec, WALL_OD


def test_preview_builds_from_default_project():
    scene = build_preview(TankProject())
    assert scene.ok
    assert scene.shell_od_in > 0
    assert scene.shell_height_in > 0
    assert len(scene.shell_section_in) >= 4
    assert len(scene.course_bands_in) >= 1
    assert "OD" in summary_line(scene)


def test_preview_tracks_shell_change():
    project = TankProject()
    project.set_shell(
        TankSpec(
            diameter_in=120.0,
            diameter_basis=WALL_OD,
            courses=[Course(48.0, 0.25), Course(48.0, 0.25)] + [Course(0.0, 0.0)] * 6,
        )
    )
    scene = build_preview(project)
    assert abs(scene.shell_od_in - 120.0) < 1e-6
    assert abs(scene.shell_height_in - 96.0) < 1e-6
    assert len(scene.shell_plates) >= 2
    assert scene.floor_plates  # follow-shell floor diameter
