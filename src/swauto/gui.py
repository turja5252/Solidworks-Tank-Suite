"""Elite SolidWorks Auto — live menus for cylinder practice + tank shell."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from swauto.cylinder import LiveCylinder, create_cylinder
from swauto.errors import SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import connect
from swauto.tank.floor_gui import build_floor_tab
from swauto.tank.gui import build_tank_tab
from swauto.stair.stringer_gui import build_stringer_tab, build_tread_joint_tab
from swauto.tank.roof_gui import build_roof_tab

_DEBOUNCE_MS = 450


def main() -> int:
    root = tk.Tk()
    root.title("Elite SolidWorks Auto")
    root.minsize(680, 560)

    status_var = tk.StringVar(value="Open SolidWorks, then use a tab below.")
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=8)

    shared: dict[str, object] = {}
    tank_tab = ttk.Frame(notebook)
    floor_tab = ttk.Frame(notebook)
    roof_tab = ttk.Frame(notebook)
    nozzle_tab = ttk.Frame(notebook)
    stringer_tab = ttk.Frame(notebook)
    joint_tab = ttk.Frame(notebook)
    cyl_tab = ttk.Frame(notebook)
    notebook.add(tank_tab, text="Tank Properties")
    notebook.add(floor_tab, text="Floor")
    notebook.add(roof_tab, text="Roof")
    notebook.add(nozzle_tab, text="Shell Nozzles")
    notebook.add(stringer_tab, text="Stringer")
    notebook.add(joint_tab, text="Tread Joint")
    notebook.add(cyl_tab, text="Live Cylinder")
    build_tank_tab(tank_tab, status_var, shared)
    build_floor_tab(floor_tab, status_var, shared)
    build_roof_tab(roof_tab, status_var, shared)
    _build_nozzle_tab(nozzle_tab, status_var, shared)
    build_stringer_tab(stringer_tab, status_var, shared)
    build_tread_joint_tab(joint_tab, status_var)
    _build_cylinder_tab(cyl_tab, status_var)

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
        ttk.Label(
            parent,
            text=f"The Shell Nozzles tab could not load:\n{type(exc).__name__}: {exc}",
            wraplength=640,
            justify="left",
            padding=12,
        ).pack(anchor="w")


def _build_cylinder_tab(parent: ttk.Frame, status_var: tk.StringVar) -> None:
    frame = ttk.Frame(parent, padding=12)
    frame.grid(row=0, column=0)

    ttk.Label(frame, text="Live Cylinder", font=("", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        frame,
        text="Practice live updates. Create once, then change diameter/height.",
        justify="left",
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))

    ttk.Label(frame, text="Diameter").grid(row=2, column=0, sticky="w")
    diameter_var = tk.StringVar(value="24")
    ttk.Entry(frame, textvariable=diameter_var, width=12).grid(row=2, column=1, sticky="w")

    ttk.Label(frame, text="Height").grid(row=3, column=0, sticky="w", pady=(6, 0))
    height_var = tk.StringVar(value="48")
    ttk.Entry(frame, textvariable=height_var, width=12).grid(row=3, column=1, sticky="w", pady=(6, 0))

    unit_var = tk.StringVar(value="in")
    ttk.Combobox(frame, textvariable=unit_var, values=("in", "ft", "mm", "m"), width=6, state="readonly").grid(
        row=2, column=2, rowspan=2, padx=(8, 0)
    )

    create_btn = ttk.Button(frame, text="Create in SolidWorks")
    create_btn.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
    state: dict[str, object] = {"live": None, "after_id": None, "busy": False}

    def parse_sizes() -> tuple[float, float] | None:
        try:
            diameter = float(diameter_var.get().strip())
            height = float(height_var.get().strip())
        except ValueError:
            return None
        if diameter <= 0 or height <= 0:
            return None
        return diameter, height

    def apply_live(show_errors: bool) -> None:
        live = state["live"]
        if not isinstance(live, LiveCylinder) or state["busy"]:
            return
        sizes = parse_sizes()
        if sizes is None:
            if show_errors:
                messagebox.showerror("Live Cylinder", "Enter numeric diameter and height greater than zero.")
            return
        diameter, height = sizes
        state["busy"] = True
        status_var.set("Updating cylinder…")
        parent.update_idletasks()
        try:
            session = connect()
            live.update(session.app, diameter=diameter, height=height, unit=unit_var.get())
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            status_var.set("Cylinder update failed.")
            if show_errors:
                messagebox.showerror("Live Cylinder", str(exc))
        except Exception as exc:  # noqa: BLE001
            status_var.set("Cylinder update failed.")
            if show_errors:
                messagebox.showerror("Live Cylinder", f"Unexpected error:\n{exc}")
        else:
            status_var.set(f"Live cylinder → {live.title}   ({diameter:g} × {height:g} {live.unit})")
        finally:
            state["busy"] = False

    def schedule_live_update(*_args) -> None:
        if state["live"] is None:
            return
        after_id = state["after_id"]
        if after_id is not None:
            parent.after_cancel(after_id)  # type: ignore[arg-type]
        state["after_id"] = parent.after(_DEBOUNCE_MS, lambda: apply_live(False))

    def create() -> None:
        sizes = parse_sizes()
        if sizes is None:
            messagebox.showerror("Live Cylinder", "Enter numeric diameter and height greater than zero.")
            return
        diameter, height = sizes
        create_btn.configure(state="disabled")
        status_var.set("Creating cylinder…")
        root = parent.winfo_toplevel()
        root.iconify()
        try:
            session = connect()
            result = create_cylinder(session.app, diameter=diameter, height=height, unit=unit_var.get())
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            root.deiconify()
            create_btn.configure(state="normal")
            messagebox.showerror("Live Cylinder", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            root.deiconify()
            create_btn.configure(state="normal")
            messagebox.showerror("Live Cylinder", f"Unexpected error:\n{exc}")
            return
        state["live"] = result.live
        create_btn.configure(text="Recreate (new part)", state="normal")
        root.deiconify()
        root.lift()
        status_var.set(f"Live cylinder → {result.title}")

    create_btn.configure(command=create)
    diameter_var.trace_add("write", schedule_live_update)
    height_var.trace_add("write", schedule_live_update)
    unit_var.trace_add("write", schedule_live_update)
