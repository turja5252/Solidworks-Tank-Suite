from swauto.cli import main
from swauto.cylinder import CylinderResult, LiveCylinder


class _App:
    pass


class _Session:
    started = False
    app = _App()


def test_cylinder_command(monkeypatch, capsys):
    monkeypatch.setattr("swauto.cli.connect", lambda *, start: _Session())

    def fake_create(app, *, diameter, height, unit):
        live = LiveCylinder("Part2", "EliteCylSketch", "EliteCylExtrude", unit)
        return CylinderResult(24, 48, "in", 0.6096, 1.2192, "Part2", live)

    monkeypatch.setattr("swauto.cli.create_cylinder", fake_create)
    assert main(["cylinder", "--diameter", "24", "--height", "48", "--unit", "in"]) == 0
    out = capsys.readouterr().out
    assert "Part2" in out
    assert "24" in out
