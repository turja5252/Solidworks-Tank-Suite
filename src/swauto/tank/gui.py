"""Live Tank Properties menu — AMETank-style shell inputs driving SolidWorks."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from swauto.errors import SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import connect
from swauto.tank.shell import LiveTank, create_tank_shell
from swauto.tank.spec import MAX_COURSES, Course, TankSpec

_DEBOUNCE_MS = 600


def build_tank_tab(parent: ttk.Frame, status_var: tk.StringVar) -> None:
    spec = TankSpec()
    state: dict[str, object] = {"live": None, "after_id": None, "busy": False}

    top = ttk.Frame(parent, padding=8)
    top.grid(row=0, column=0, sticky="nsew")
    parent.columnconfigure(0, weight=1)

    ttk.Label(top, text="Tank Properties (Shell)", font=("", 11, "bold")).grid(
        row=0, column=0, columnspan=6, sticky="w"
    )
    ttk.Label(
        top,
        text="Same idea as Elite ETP / AMETank shell setup: diameter + courses → 3D shell.\n"
        "Create once, then edit values to update the SolidWorks model.",
        justify="left",
    ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(0, 8))

    ttk.Label(top, text="Diameter").grid(row=2, column=0, sticky="w")
    diameter_var = tk.StringVar(value=f"{spec.diameter_in:g}")
    ttk.Entry(top, textvariable=diameter_var, width=10).grid(row=2, column=1, sticky="w")
    ttk.Label(top, text="in").grid(row=2, column=2, sticky="w")

    ttk.Label(top, text="Basis").grid(row=2, column=3, sticky="w", padx=(12, 0))
    basis_var = tk.StringVar(value=spec.diameter_basis)
    ttk.Combobox(
        top,
        textvariable=basis_var,
        values=("outside", "inside", "centerline"),
        width=12,
        state="readonly",
    ).grid(row=2, column=4, sticky="w")

    height_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=height_var).grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 8))

    course_frame = ttk.LabelFrame(top, text="Shell courses (bottom → top)", padding=6)
    course_frame.grid(row=4, column=0, columnspan=6, sticky="ew")
    ttk.Label(course_frame, text="#").grid(row=0, column=0)
    ttk.Label(course_frame, text="Height (in)").grid(row=0, column=1)
    ttk.Label(course_frame, text="Thickness (in)").grid(row=0, column=2)

    height_vars: list[tk.StringVar] = []
    thk_vars: list[tk.StringVar] = []
    for i in range(MAX_COURSES):
        course = spec.courses[i]
        ttk.Label(course_frame, text=str(i + 1)).grid(row=i + 1, column=0, padx=4)
        hv = tk.StringVar(value=f"{course.height_in:g}")
        tv = tk.StringVar(value=f"{course.thickness_in:g}")
        ttk.Entry(course_frame, textvariable=hv, width=10).grid(row=i + 1, column=1, padx=4, pady=1)
        ttk.Entry(course_frame, textvariable=tv, width=10).grid(row=i + 1, column=2, padx=4, pady=1)
        height_vars.append(hv)
        thk_vars.append(tv)

    btn_row = ttk.Frame(top)
    btn_row.grid(row=5, column=0, columnspan=6, sticky="ew", pady=(10, 0))
    create_btn = ttk.Button(btn_row, text="Create tank shell in SolidWorks")
    create_btn.pack(side="left")
    ttk.Button(btn_row, text="Save…", command=lambda: _save(read_spec)).pack(side="left", padx=6)
    ttk.Button(btn_row, text="Load…", command=lambda: _load(apply_spec)).pack(side="left")

    def read_spec() -> TankSpec:
        courses = []
        for hv, tv in zip(height_vars, thk_vars, strict=True):
            try:
                h = float(hv.get().strip() or 0)
                t = float(tv.get().strip() or 0)
            except ValueError as exc:
                raise ValueError("Course height/thickness must be numeric.") from exc
            courses.append(Course(h, t))
        try:
            dia = float(diameter_var.get().strip())
        except ValueError as exc:
            raise ValueError("Diameter must be numeric.") from exc
        return TankSpec(diameter_in=dia, diameter_basis=basis_var.get(), courses=courses)

    def apply_spec(loaded: TankSpec) -> None:
        diameter_var.set(f"{loaded.diameter_in:g}")
        basis_var.set(loaded.diameter_basis)
        for i in range(MAX_COURSES):
            course = loaded.courses[i] if i < len(loaded.courses) else Course(0.0, 0.0)
            height_vars[i].set(f"{course.height_in:g}")
            thk_vars[i].set(f"{course.thickness_in:g}")
        refresh_height()

    def refresh_height(*_args) -> None:
        try:
            current = read_spec()
            height_var.set(f"Shell height: {current.shell_height_in():g} in  ({current.shell_height_in() / 12:g} ft)")
        except ValueError:
            height_var.set("Shell height: —")

    def schedule_update(*_args) -> None:
        refresh_height()
        if state["live"] is None:
            return
        after_id = state["after_id"]
        if after_id is not None:
            parent.after_cancel(after_id)  # type: ignore[arg-type]
        state["after_id"] = parent.after(_DEBOUNCE_MS, lambda: apply_live(False))

    def apply_live(show_errors: bool) -> None:
        live = state["live"]
        if not isinstance(live, LiveTank) or state["busy"]:
            return
        try:
            spec_now = read_spec()
            spec_now.validate()
        except ValueError as exc:
            if show_errors:
                messagebox.showerror("Tank Properties", str(exc))
            return

        state["busy"] = True
        status_var.set("Updating tank shell in SolidWorks…")
        parent.update_idletasks()
        root = parent.winfo_toplevel()
        try:
            root.iconify()
            session = connect()
            live.update(session.app, spec_now)
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            status_var.set("Tank update failed.")
            if show_errors:
                messagebox.showerror("Tank Properties", str(exc))
            else:
                status_var.set(str(exc))
        except Exception as exc:  # noqa: BLE001
            status_var.set("Tank update failed.")
            if show_errors:
                messagebox.showerror("Tank Properties", f"Unexpected error:\n{exc}")
        else:
            status_var.set(f"Live tank → {live.title}   ({spec_now.shell_height_in():g}\" shell)")
        finally:
            state["busy"] = False
            root.deiconify()
            root.lift()

    def create() -> None:
        try:
            spec_now = read_spec()
            spec_now.validate()
        except ValueError as exc:
            messagebox.showerror("Tank Properties", str(exc))
            return

        create_btn.configure(state="disabled")
        status_var.set("Creating tank shell… click SolidWorks if a dialog appears.")
        root = parent.winfo_toplevel()
        root.update_idletasks()
        root.iconify()
        try:
            session = connect()
            result = create_tank_shell(session.app, spec_now)
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            root.deiconify()
            root.lift()
            create_btn.configure(state="normal")
            status_var.set("Create failed.")
            messagebox.showerror("Tank Properties", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            root.deiconify()
            root.lift()
            create_btn.configure(state="normal")
            status_var.set("Create failed.")
            messagebox.showerror("Tank Properties", f"Unexpected error:\n{exc}")
            return

        state["live"] = result.live
        create_btn.configure(text="Recreate tank shell", state="normal")
        root.deiconify()
        root.lift()
        status_var.set(f"Live tank → {result.title}   (edit courses to update)")

    create_btn.configure(command=create)
    diameter_var.trace_add("write", schedule_update)
    basis_var.trace_add("write", schedule_update)
    for hv, tv in zip(height_vars, thk_vars, strict=True):
        hv.trace_add("write", schedule_update)
        tv.trace_add("write", schedule_update)
    refresh_height()


def _save(read_spec) -> None:
    try:
        spec = read_spec()
        spec.validate()
    except ValueError as exc:
        messagebox.showerror("Tank Properties", str(exc))
        return
    path = filedialog.asksaveasfilename(
        title="Save Tank Properties",
        defaultextension=".json",
        filetypes=[("JSON", "*.json"), ("All", "*.*")],
    )
    if not path:
        return
    spec.save_json(path)
    # Also write ETP-style sidecar for future AutoCAD round-trip.
    etp_path = Path(path).with_suffix(".etp.json")
    etp_path.write_text(json.dumps(spec.to_etp_dict(), indent=2), encoding="utf-8")
    messagebox.showinfo("Tank Properties", f"Saved:\n{path}\n{etp_path}")


def _load(apply_spec) -> None:
    path = filedialog.askopenfilename(
        title="Load Tank Properties",
        filetypes=[("JSON", "*.json"), ("All", "*.*")],
    )
    if not path:
        return
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if "SHELL_COURSE_1" in data or "DIAMETER_FT" in data:
            spec = TankSpec.from_etp_dict(data)
        else:
            spec = TankSpec.load_json(path)
        apply_spec(spec)
    except Exception as exc:  # noqa: BLE001
        messagebox.showerror("Tank Properties", f"Could not load file:\n{exc}")
