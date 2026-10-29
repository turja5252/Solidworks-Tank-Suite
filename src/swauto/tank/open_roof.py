"""The part with the Roof tab's cone in it, for whatever is built onto the roof (nozzles, framing)."""

from __future__ import annotations

from swauto.comutil import com_value
from swauto.features import find_feature
from swauto.tank.roof_sw import ROOF_NAME

_PART = 1


def find_roof_part(shared: dict, app):
    """The tank shell part made in this run when it has the roof, else the one part open in SolidWorks that has
    it (the active one when there are several). Raises ``ValueError`` saying what to do when there is none."""
    live = shared.get("live")
    model = getattr(live, "model", None)
    if model is not None:
        try:
            if find_feature(model, ROOF_NAME) is not None:
                return model
        except Exception:  # noqa: BLE001 - closed since: look among the open documents
            pass
    roofs = []
    doc = app.GetFirstDocument
    while doc is not None:
        try:
            if com_value(doc.GetType) == _PART and find_feature(doc, ROOF_NAME) is not None:
                roofs.append(doc)
        except Exception:  # noqa: BLE001 - a document that cannot be read has no roof for us
            pass
        doc = doc.GetNext
    if len(roofs) == 1:
        return roofs[0]
    active = com_value(app.ActiveDoc)
    for doc in roofs:
        try:
            if active is not None and str(com_value(doc.GetTitle)) == str(com_value(active.GetTitle)):
                return doc
        except Exception:  # noqa: BLE001
            continue
    if roofs:
        names = ", ".join(str(com_value(doc.GetTitle)) for doc in roofs)
        raise ValueError(f"More than one open part has a roof ({names}). Click the one to build on, then try again.")
    raise ValueError("No roof to build on. Build the roof on the Roof tab first (into the tank shell part).")
