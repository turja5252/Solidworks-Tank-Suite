"""The one-part shell that Build on shell (nozzles, FTCOs) works on.

The shell the Tank Properties tab made in this run of the app is remembered in
``shared["live"]``. After the app restarts, the shell part is still open in
SolidWorks but nothing remembers it, so look for it there.
"""

from __future__ import annotations

from swauto.comutil import com_value
from swauto.features import find_feature
from swauto.tank.shell import AXIS_NAME, LiveTank
from swauto.tank.spec import TankSpec

_PART = 1
_ASSEMBLY = 2
PROJECT_PART_PROPERTY = "Elite item"  # project part files carry it; a one-part shell does not


def find_shell(shared: dict, app) -> LiveTank:
    """The shell to build on: the one made in this run, else the shell part open in SolidWorks.

    Raises ``ValueError`` saying what to do when there is none.
    """
    spec = shared.get("spec")
    if not isinstance(spec, TankSpec) or not spec.active_courses():
        raise ValueError("Set the tank on Tank Properties first.")
    live = shared.get("live")
    if isinstance(live, LiveTank) and _alive(live.model):
        return live
    active = com_value(app.ActiveDoc)
    shells = [doc for doc in _open_documents(app) if _is_shell_part(doc)]
    chosen = None
    if active is not None and any(_same(active, doc) for doc in shells):
        chosen = active
    elif len(shells) == 1:
        chosen = shells[0]
    elif len(shells) > 1:
        names = ", ".join(str(com_value(doc.GetTitle)) for doc in shells)
        raise ValueError(f"More than one tank shell is open ({names}). Click the one to build on, then try again.")
    if chosen is not None:
        live = LiveTank(title=str(com_value(chosen.GetTitle) or "Part"), spec=spec, model=chosen)
        shared["live"] = live
        return live
    project = shared.get("project")
    assembly = getattr(project, "assembly_path", None)
    if assembly is not None and assembly.exists():
        raise ValueError(
            f"This project's shell is built as parts, in {assembly.name}. Nozzles go into it from the "
            "Project tab: click Build changes there (the nozzles are on its list). Build on shell is "
            "for the one-part preview shell, made with Create tank shell in SolidWorks."
        )
    if active is not None and com_value(active.GetType) == _ASSEMBLY:
        raise ValueError(
            "The open document is an assembly. Build on shell works on the one-part shell for now: "
            "click Create tank shell in SolidWorks on Tank Properties. Nozzles and FTCOs join the "
            "project assembly in the next phase."
        )
    raise ValueError(
        "No tank shell to build on. Click Create tank shell in SolidWorks on Tank Properties, "
        "or open the shell part this app made, then try again."
    )


def _open_documents(app) -> list:
    docs = []
    doc = app.GetFirstDocument
    while doc is not None:
        docs.append(doc)
        doc = doc.GetNext
    return docs


def _is_shell_part(doc) -> bool:
    """A part made by Create tank shell: it has the tank axis, and is not one of a project's part files."""
    try:
        if com_value(doc.GetType) != _PART or find_feature(doc, AXIS_NAME) is None:
            return False
        names = com_value(doc.Extension.CustomPropertyManager("").GetNames) or ()
        return PROJECT_PART_PROPERTY not in [str(name) for name in names]
    except Exception:  # noqa: BLE001 - a document that cannot be read is not the shell
        return False


def _alive(model) -> bool:
    """The remembered document is still open in SolidWorks."""
    try:
        return bool(str(com_value(model.GetTitle) or ""))
    except Exception:  # noqa: BLE001 - closed: its COM object is gone
        return False


def _same(a, b) -> bool:
    try:
        return str(com_value(a.GetTitle)) == str(com_value(b.GetTitle))
    except Exception:  # noqa: BLE001
        return False
