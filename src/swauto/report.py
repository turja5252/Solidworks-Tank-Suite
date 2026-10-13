from dataclasses import dataclass

from swauto.comutil import com_value

# SolidWorks major revision 23 is SOLIDWORKS 2015. Later years follow the same step.
_REVISION_YEAR_OFFSET = 1992
_MIN_YEAR = 2012
_MAX_YEAR = 2040

DOC_PART = 1
DOC_ASSEMBLY = 2
DOC_DRAWING = 3

_DOC_KINDS = {
    DOC_PART: "Part",
    DOC_ASSEMBLY: "Assembly",
    DOC_DRAWING: "Drawing",
}


@dataclass(frozen=True)
class DocumentInfo:
    title: str
    path: str
    kind: str


def format_revision(revision: str) -> str:
    """Turn an API revision such as '32.5.0' into 'SOLIDWORKS 2024 (32.5.0)'."""
    text = revision.strip()
    major_text = text.split(".", 1)[0]
    try:
        year = int(major_text) + _REVISION_YEAR_OFFSET
    except ValueError:
        return text
    if year < _MIN_YEAR or year > _MAX_YEAR:
        return text
    return f"SOLIDWORKS {year} ({text})"


def read_document(doc) -> DocumentInfo | None:
    if doc is None:
        return None
    kind_code = int(com_value(doc.GetType))
    path = str(com_value(doc.GetPathName) or "")
    return DocumentInfo(
        title=str(com_value(doc.GetTitle)),
        path=path,
        kind=_DOC_KINDS.get(kind_code, f"Type {kind_code}"),
    )


def status_report(revision: str, document: DocumentInfo | None, *, started: bool) -> str:
    lines: list[str] = []
    if started:
        lines.append("Started SolidWorks.")
    lines.append(format_revision(revision))
    if document is None:
        lines.append("Active document: none")
        return "\n".join(lines)
    lines.append(f"Active document: {document.title} ({document.kind})")
    lines.append(document.path or "Not saved yet.")
    return "\n".join(lines)
