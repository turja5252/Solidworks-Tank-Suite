"""Live Tank Properties menu — AMETank-style shell inputs driving SolidWorks."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from swauto.comutil import format_com_error
from swauto.errors import SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import connect
from swauto.tank.shell import LiveTank, create_tank_shell
from swauto.tank.spec import (
    DEFAULT_MAX_PLATE_IN,
    MAX_COURSES,
    MODE_EQUAL,
    STAGGER_BASE,
    STAGGER_CUSTOM,
    STAGGER_HALF,
    Course,
    TankSpec,
    default_stagger_for_course,
)

_DEBOUNCE_MS = 600

_STAGGER_LABELS = ("Base", "Half", "Custom")
_STAGGER_VALUES = (STAGGER_BASE, STAGGER_HALF, STAGGER_CUSTOM)


def build_tank_tab(parent: ttk.Frame, status_var: tk.StringVar) -> None:
    spec = TankSpec()
    state: dict[str, object] = {"live": None, "after_id": None, "busy": False}

    top = ttk.Frame(parent, padding=8)
    top.grid(row=0, column=0, sticky="nsew")
    parent.columnconfigure(0, weight=1)

    ttk.Label(top, text="Tank Properties (Shell)", font=("", 11, "bold")).grid(
        row=0, column=0, columnspan=8, sticky="w"
    )
    ttk.Label(
        top,
        text="Discrete shell plates per course (ETP stagger). Create once, then edit to update SolidWorks.",
        justify="left",
    ).grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 8))

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

    ttk.Label(top, text="Seam offset").grid(row=2, column=5, sticky="w", padx=(12, 0))
    offset_var = tk.StringVar(value=f"{spec.seam_offset_in:g}")
    ttk.Entry(top, textvariable=offset_var, width=8).grid(row=2, column=6, sticky="w")
    ttk.Label(top, text="in").grid(row=2, column=7, sticky="w")

    height_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=height_var).grid(row=3, column=0, columnspan=8, sticky="w", pady=(4, 8))

    course_frame = ttk.LabelFrame(top, text="Shell courses (bottom → top) — plates + stagger", padding=6)
    course_frame.grid(row=4, column=0, columnspan=8, sticky="ew")
    headers = ("#", "Height", "Thk", "Max len", "Stagger", "Adjust")
    for col, text in enumerate(headers):
        ttk.Label(course_frame, text=text).grid(row=0, column=col, padx=2)

    height_vars: list[tk.StringVar] = []
    thk_vars: list[tk.StringVar] = []
    max_vars: list[tk.StringVar] = []
    stagger_vars: list[tk.StringVar] = []
    adjust_vars: list[tk.StringVar] = []
    for i in range(MAX_COURSES):
        course = spec.courses[i]
        ttk.Label(course_frame, text=str(i + 1)).grid(row=i + 1, column=0, padx=2)
        hv = tk.StringVar(value=f"{course.height_in:g}")
        tv = tk.StringVar(value=f"{course.thickness_in:g}")
        mv = tk.StringVar(value=f"{course.max_length_in:g}")
        sv = tk.StringVar(value=_stagger_label(course.stagger))
        av = tk.StringVar(value=f"{course.adjust_in:g}")
        ttk.Entry(course_frame, textvariable=hv, width=8).grid(row=i + 1, column=1, padx=2, pady=1)
        ttk.Entry(course_frame, textvariable=tv, width=8).grid(row=i + 1, column=2, padx=2, pady=1)
        ttk.Entry(course_frame, textvariable=mv, width=8).grid(row=i + 1, column=3, padx=2, pady=1)
        ttk.Combobox(
            course_frame,
            textvariable=sv,
            values=_STAGGER_LABELS,
            width=8,
            state="readonly",
        ).grid(row=i + 1, column=4, padx=2, pady=1)
        ttk.Entry(course_frame, textvariable=av, width=8).grid(row=i + 1, column=5, padx=2, pady=1)
        height_vars.append(hv)
        thk_vars.append(tv)
        max_vars.append(mv)
        stagger_vars.append(sv)
        adjust_vars.append(av)

    btn_row = ttk.Frame(top)
    btn_row.grid(row=5, column=0, columnspan=8, sticky="ew", pady=(10, 0))
    create_btn = ttk.Button(btn_row, text="Create tank shell in SolidWorks")
    create_btn.pack(side="left")
    ttk.Button(btn_row, text="Save…", command=lambda: _save(read_spec)).pack(side="left", padx=6)
    ttk.Button(btn_row, text="Load…", command=lambda: _load(apply_spec)).pack(side="left")

    def read_spec() -> TankSpec:
        courses = []
        for hv, tv, mv, sv, av in zip(
            height_vars, thk_vars, max_vars, stagger_vars, adjust_vars, strict=True
        ):
            try:
                h = float(hv.get().strip() or 0)
                t = float(tv.get().strip() or 0)
                m = float(mv.get().strip() or DEFAULT_MAX_PLATE_IN)
                a = float(av.get().strip() or 0)
            except ValueError as exc:
                raise ValueError("Course height/thickness/max/adjust must be numeric.") from exc
            courses.append(
                Course(
                    height_in=h,
                    thickness_in=t,
                    max_length_in=m if m > 0 else DEFAULT_MAX_PLATE_IN,
                    mode=MODE_EQUAL,
                    stagger=_stagger_value(sv.get()),
                    adjust_in=a,
                )
            )
        try:
            dia = float(diameter_var.get().strip())
            off = float(offset_var.get().strip() or 0)
        except ValueError as exc:
            raise ValueError("Diameter / seam offset must be numeric.") from exc
        return TankSpec(
            diameter_in=dia,
            diameter_basis=basis_var.get(),
            courses=courses,
            seam_offset_in=off,
        )

    def apply_spec(loaded: TankSpec) -> None:
        diameter_var.set(f"{loaded.diameter_in:g}")
        basis_var.set(loaded.diameter_basis)
        offset_var.set(f"{loaded.seam_offset_in:g}")
        for i in range(MAX_COURSES):
            course = (
                loaded.courses[i]
                if i < len(loaded.courses)
                else Course(0.0, 0.0, stagger=default_stagger_for_course(i + 1))
            )
            height_vars[i].set(f"{course.height_in:g}")
            thk_vars[i].set(f"{course.thickness_in:g}")
            max_vars[i].set(f"{course.max_length_in:g}")
            stagger_vars[i].set(_stagger_label(course.stagger))
            adjust_vars[i].set(f"{course.adjust_in:g}")
        refresh_height()

    def refresh_height(*_args) -> None:
        try:
            current = read_spec()
            from swauto.tank.plates import layout_plates

            plates = layout_plates(current) if current.active_courses() else []
            n = len(plates)
            height_var.set(
                f"Shell height: {current.shell_height_in():g} in  "
                f"({current.shell_height_in() / 12:g} ft)  |  Plates: {n}"
            )
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
                messagebox.showerror("Tank Properties", format_com_error(exc))
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
        status_var.set("Creating plated shell… click SolidWorks if a dialog appears.")
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
            messagebox.showerror("Tank Properties", format_com_error(exc))
            return

        state["live"] = result.live
        create_btn.configure(text="Recreate tank shell", state="normal")
        root.deiconify()
        root.lift()
        status_var.set(f"Live tank → {result.title}   (edit courses / stagger to update)")

    create_btn.configure(command=create)
    for var in (diameter_var, basis_var, offset_var):
        var.trace_add("write", schedule_update)
    for row in zip(height_vars, thk_vars, max_vars, stagger_vars, adjust_vars, strict=True):
        for var in row:
            var.trace_add("write", schedule_update)
    refresh_height()


def _stagger_label(value: str) -> str:
    try:
        return _STAGGER_LABELS[_STAGGER_VALUES.index(value)]
    except ValueError:
        return "Base"


def _stagger_value(label: str) -> str:
    try:
        return _STAGGER_VALUES[_STAGGER_LABELS.index(label)]
    except ValueError:
        return STAGGER_BASE


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
