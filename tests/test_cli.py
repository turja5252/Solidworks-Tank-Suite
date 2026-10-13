from swauto.cli import main
from swauto.report import DocumentInfo


class _Session:
    started = False

    def revision(self):
        return "32.5.0"

    def active_document(self):
        return DocumentInfo("Bracket.SLDPRT", r"D:\Jobs\Bracket.SLDPRT", "Part")


def test_status_prints_version_and_active_document(monkeypatch, capsys):
    monkeypatch.setattr("swauto.cli.connect", lambda *, start: _Session())
    assert main(["status"]) == 0
    assert capsys.readouterr().out == (
        "SOLIDWORKS 2024 (32.5.0)\n"
        "Active document: Bracket.SLDPRT (Part)\n"
        r"D:\Jobs\Bracket.SLDPRT"
        "\n"
    )


def test_status_reports_when_solidworks_is_closed(monkeypatch, capsys):
    from swauto.errors import SolidWorksNotRunning

    def _closed(*, start):
        raise SolidWorksNotRunning("SolidWorks is not running in this Windows session.")

    monkeypatch.setattr("swauto.cli.connect", _closed)
    assert main(["status"]) == 2
    assert "not running" in capsys.readouterr().err
