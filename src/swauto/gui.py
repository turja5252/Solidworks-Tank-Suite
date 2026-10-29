"""Elite SolidWorks Auto — the tank's tabs, from Project and Tank Properties to the stairway."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from swauto import runlog
from swauto.stair.stringer_gui import build_stringer_tab
from swauto.tank.floor_gui import build_floor_tab
from swauto.tank.gui import build_tank_tab
from swauto.tank.roof_gui import build_roof_tab


def main() -> int:
    root = tk.Tk()
    root.title("Elite SolidWorks Auto")
    root.minsize(680, 560)

    status_var = tk.StringVar(value="Open SolidWorks, then use a tab below.")
    shared: dict[str, object] = {}
    # Everything the app shows goes into logs\<date>.log beside it, and into the open project's folder.
    runlog.start(root, status_var)

    # The project is saved from here on every tab; the Project tab fills in the name and the save.
    project_bar = ttk.Frame(root, padding=(10, 6, 10, 0))
    project_bar.pack(fill="x")
    project_var = tk.StringVar(value="No project open — New project is on the Project tab.")
    ttk.Label(project_bar, textvariable=project_var).pack(side="left")
    shared["project_label"] = project_var

    def save_project(_event=None) -> None:
        save = shared.get("save_project")
        if callable(save):
            save()
        else:
            status_var.set("The Project tab did not load, so there is no project to save.")

    ttk.Button(project_bar, text="Save project  (Ctrl+S)", command=save_project).pack(side="right")
    root.bind_all("<Control-s>", save_project)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=8)
    notebook.bind(
        "<<NotebookTabChanged>>", lambda _event: runlog.LOG.info("Tab: %s", notebook.tab(notebook.select(), "text")),
        add="+",
    )

    project_tab = ttk.Frame(notebook)
    tank_tab = ttk.Frame(notebook)
    floor_tab = ttk.Frame(notebook)
    roof_tab = ttk.Frame(notebook)
    framing_tab = ttk.Frame(notebook)
    nozzle_tab = ttk.Frame(notebook)
    roof_nozzle_tab = ttk.Frame(notebook)
    ftco_tab = ttk.Frame(notebook)
    anchor_tab = ttk.Frame(notebook)
    stairway_tab = ttk.Frame(notebook)
    stretchout_tab = ttk.Frame(notebook)
    notebook.add(project_tab, text="Project")
    notebook.add(tank_tab, text="Tank Properties")
    notebook.add(floor_tab, text="Floor")
    notebook.add(roof_tab, text="Roof")
    notebook.add(framing_tab, text="Roof Framing")
    notebook.add(nozzle_tab, text="Shell Nozzles")
    notebook.add(roof_nozzle_tab, text="Roof Nozzles")
    notebook.add(ftco_tab, text="FTCO")
    notebook.add(anchor_tab, text="Anchor Chairs")
    notebook.add(stairway_tab, text="Stairway")
    notebook.add(stretchout_tab, text="Stretchout")
    build_tank_tab(tank_tab, status_var, shared)
    build_floor_tab(floor_tab, status_var, shared)
    build_roof_tab(roof_tab, status_var, shared)
    _build_framing_tab(framing_tab, status_var, shared)
    _build_nozzle_tab(nozzle_tab, status_var, shared)
    _build_roof_nozzle_tab(roof_nozzle_tab, status_var, shared)
    _build_cleanout_tab(ftco_tab, status_var, shared)
    _build_anchor_tab(anchor_tab, status_var, shared)
    build_stringer_tab(stairway_tab, status_var, shared)
    _build_stretchout_tab(stretchout_tab, status_var, shared)
    _build_project_tab(project_tab, status_var, shared)  # last: it reads what the other tabs share

    ttk.Label(root, textvariable=status_var, wraplength=660, justify="left").pack(
        fill="x", padx=10, pady=(0, 8)
    )
    root.mainloop()
    return 0


def _build_nozzle_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict[str, object]) -> None:
    """The nozzle engine is built apart from the rest: if its tab fails, say why there and keep the app up."""
    try:
        from swauto.nozzle.gui import build_nozzle_tab

        build_nozzle_tab(parent, status_var, shared)
    except Exception as exc:  # noqa: BLE001
        runlog.LOG.exception("The Shell Nozzles tab could not load")
        ttk.Label(
            parent,
            text=f"The Shell Nozzles tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")


def _build_framing_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict[str, object]) -> None:
    """Like the nozzle tab: if the Roof Framing tab fails to load, say why there and keep the app up."""
    try:
        from swauto.tank.framing_gui import build_framing_tab

        build_framing_tab(parent, status_var, shared)
    except Exception as exc:  # noqa: BLE001
        runlog.LOG.exception("The Roof Framing tab could not load")
        ttk.Label(
            parent,
            text=f"The Roof Framing tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")


def _build_roof_nozzle_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict[str, object]) -> None:
    """Like the nozzle tab: if the Roof Nozzles tab fails to load, say why there and keep the app up."""
    try:
        from swauto.nozzle.roof_gui import build_roof_nozzle_tab

        build_roof_nozzle_tab(parent, status_var, shared)
    except Exception as exc:  # noqa: BLE001
        runlog.LOG.exception("The Roof Nozzles tab could not load")
        ttk.Label(
            parent,
            text=f"The Roof Nozzles tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")


def _build_anchor_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict[str, object]) -> None:
    """Like the nozzle tab: if the Anchor Chairs tab fails to load, say why there and keep the app up."""
    try:
        from swauto.tank.anchors_gui import build_anchor_tab

        build_anchor_tab(parent, status_var, shared)
    except Exception as exc:  # noqa: BLE001
        runlog.LOG.exception("The Anchor Chairs tab could not load")
        ttk.Label(
            parent,
            text=f"The Anchor Chairs tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")


def _build_cleanout_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict[str, object]) -> None:
    """Like the nozzle tab: if the FTCO tab fails to load, say why there and keep the app up."""
    try:
        from swauto.cleanout.gui import build_cleanout_tab

        build_cleanout_tab(parent, status_var, shared)
    except Exception as exc:  # noqa: BLE001
        runlog.LOG.exception("The FTCO tab could not load")
        ttk.Label(
            parent,
            text=f"The FTCO tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")


def _build_stretchout_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict[str, object]) -> None:
    """Like the nozzle tab: if the Stretchout tab fails to load, say why there and keep the app up."""
    try:
        from swauto.stretchout.gui import build_stretchout_tab

        build_stretchout_tab(parent, status_var, shared)
    except Exception as exc:  # noqa: BLE001
        runlog.LOG.exception("The Stretchout tab could not load")
        ttk.Label(
            parent,
            text=f"The Stretchout tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")


def _build_project_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict[str, object]) -> None:
    """Like the nozzle tab: if the Project tab fails to load, say why there and keep the app up."""
    try:
        from swauto.project.gui import build_project_tab

        build_project_tab(parent, status_var, shared)
    except Exception as exc:  # noqa: BLE001
        runlog.LOG.exception("The Project tab could not load")
        ttk.Label(
            parent,
            text=f"The Project tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")
