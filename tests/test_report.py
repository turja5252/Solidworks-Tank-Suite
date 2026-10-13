from swauto.report import DocumentInfo, format_revision, read_document, status_report


def test_format_revision_maps_major_number_to_year():
    assert format_revision("32.5.0") == "SOLIDWORKS 2024 (32.5.0)"
    assert format_revision("34.0.0") == "SOLIDWORKS 2026 (34.0.0)"


def test_format_revision_keeps_unknown_text():
    assert format_revision("sw2024_sp5") == "sw2024_sp5"


class _Doc:
    def __init__(self, title, path, kind):
        self._title = title
        self._path = path
        self._kind = kind

    def GetTitle(self):
        return self._title

    def GetPathName(self):
        return self._path

    def GetType(self):
        return self._kind


def test_read_document_none():
    assert read_document(None) is None


def test_read_document_part():
    info = read_document(_Doc("Bracket.SLDPRT", r"D:\Jobs\Bracket.SLDPRT", 1))
    assert info == DocumentInfo("Bracket.SLDPRT", r"D:\Jobs\Bracket.SLDPRT", "Part")


def test_status_report_without_document():
    text = status_report("32.5.0", None, started=False)
    assert text == "SOLIDWORKS 2024 (32.5.0)\nActive document: none"


def test_status_report_started_unsaved_drawing():
    document = DocumentInfo("Drawing1", "", "Drawing")
    text = status_report("33.1.0", document, started=True)
    assert text == "Started SolidWorks.\nSOLIDWORKS 2025 (33.1.0)\nActive document: Drawing1 (Drawing)\nNot saved yet."
