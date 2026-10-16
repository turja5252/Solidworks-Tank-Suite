"""Stringer tab: build the formed helical plate in SolidWorks."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox, ttk

from swauto.comutil import format_com_error
from swauto.errors import SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import connect
from swauto.stair.stringer import StringerMock, StringerLayout, layout_stringer
from swauto.stair.stringer_sw import create_stringer_try

_PLAN = 280


def build_stringer_tab(parent: ttk.Frame, status_var: tk.StringVar) -> None:
    spec = StringerMock()
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    scroller = tk.Canvas(parent, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=scroller.yview)
    scroller.configure(yscrollcommand=scrollbar.set)
    scroller.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    top = ttk.Frame(scroller, padding=12)
    top_id = scroller.create_window((0, 0), window=top, anchor="nw")
    scroller.bind("<Configure>", lambda event: scroller.itemconfigure(top_id, width=event.width))
    top.bind("<Configure>", lambda _event: scroller.configure(scrollregion=scroller.bbox("all")))

    ttk.Label(top, text="Spiral stringer", font=("", 11, "bold")).grid(row=0, column=0, columnspan=8, sticky="w")
    ttk.Label(
        top,
        text=(
            "Create builds a bent 3/8 in outer stringer with the burn holes. "
            "It is already sheet metal. Click Flatten, then File > Save As > DXF. "
            "The bent plate stays on screen until you click Flatten."
        ),
        justify="left",
        wraplength=640,
    ).grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 8))

    shell_var = tk.StringVar(value=f"{spec.shell_od_in:g}")
    gap_var = tk.StringVar(value=f"{spec.gap_in:g}")
    treads_var = tk.StringVar(value=str(spec.treads))
    rise_var = tk.StringVar(value=f"{spec.rise_in:g}")
    run_var = tk.StringVar(value=f"{spec.run_in:g}")
    plate_var = tk.StringVar(value=f"{spec.plate_width_in:g}")

    _field(top, 2, 0, "Shell OD radius", shell_var, "in")
    _field(top, 2, 3, "Gap", gap_var, "in")
    _field(top, 3, 0, "Treads", treads_var, "")
    _field(top, 3, 3, "Rise", rise_var, "in")
    _field(top, 4, 0, "Run", run_var, "in")
    _field(top, 4, 3, "Plate width", plate_var, "in")

    state = {"busy": False}
    create_btn = ttk.Button(top, text="Create try model in SolidWorks")
    create_btn.grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 4))

    summary_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=summary_var, justify="left").grid(
        row=6, column=0, columnspan=8, sticky="w", pady=(4, 4)
    )

    ttk.Label(top, text="Plan of the formed stringer").grid(row=7, column=0, columnspan=8, sticky="w")
    plan = tk.Canvas(top, width=_PLAN, height=_PLAN, background="#f4f1ea", highlightthickness=1)
    plan.grid(row=8, column=0, columnspan=8, sticky="w")

    def read_spec() -> StringerMock:
        try:
            return StringerMock(
                shell_od_in=float(shell_var.get().strip()),
                gap_in=float(gap_var.get().strip()),
                treads=int(float(treads_var.get().strip())),
                rise_in=float(rise_var.get().strip()),
                run_in=float(run_var.get().strip()),
                plate_width_in=float(plate_var.get().strip()),
                outside_face=True,
            )
        except ValueError as exc:
            raise ValueError("Stringer values must be numeric.") from exc

    def refresh(*_args) -> None:
        try:
            current = read_spec()
            current.validate()
            drawn = layout_stringer(current)
        except ValueError as exc:
            summary_var.set(str(exc))
            plan.delete("all")
            status_var.set("Stringer needs a correction.")
            return
        summary_var.set(
            f"Outside face radius {drawn.outside_radius_in:.2f} in · "
            f"sweep {drawn.sweep_deg:.2f}° · rise {drawn.total_rise_in:.1f} in · "
            f"pitch {drawn.pitch_deg:.2f}°"
        )
        _draw_plan(plan, drawn)
        status_var.set("Stringer ready.")

    def create() -> None:
        if state["busy"]:
            return
        try:
            current = read_spec()
            current.validate()
        except ValueError as exc:
            messagebox.showerror("Stringer", str(exc))
            return
        state["busy"] = True
        create_btn.configure(state="disabled")
        status_var.set("Building the formed stringer…")
        parent.update_idletasks()
        try:
            session = connect()
            result = create_stringer_try(session.app, current)
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            state["busy"] = False
            create_btn.configure(state="normal")
            status_var.set("Stringer build failed.")
            messagebox.showerror("Stringer", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            state["busy"] = False
            create_btn.configure(state="normal")
            status_var.set("Stringer build failed.")
            messagebox.showerror("Stringer", format_com_error(exc))
            return
        state["busy"] = False
        create_btn.configure(state="normal")
        status_var.set(f"Stringer → {result.title}")
        messagebox.showinfo("Stringer", f"{result.title}\n\n{result.note}")

    create_btn.configure(command=create)
    for var in (shell_var, gap_var, treads_var, rise_var, run_var, plate_var):
        var.trace_add("write", refresh)

    def on_wheel(event) -> None:
        scroller.yview_scroll(int(-event.delta / 120), "units")

    _bind_wheel(top, on_wheel)
    scroller.bind("<MouseWheel>", on_wheel)
    refresh()


def _field(parent, row: int, column: int, label: str, variable: tk.StringVar, unit: str) -> None:
    ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=(4, 0))
    ttk.Entry(parent, textvariable=variable, width=10).grid(row=row, column=column + 1, sticky="w", pady=(4, 0))
    ttk.Label(parent, text=unit).grid(row=row, column=column + 2, sticky="w", padx=(2, 10), pady=(4, 0))


def _bind_wheel(widget, handler) -> None:
    widget.bind("<MouseWheel>", handler)
    for child in widget.winfo_children():
        _bind_wheel(child, handler)


def _draw_plan(canvas: tk.Canvas, layout: StringerLayout) -> None:
    canvas.delete("all")
    sweep = layout.sweep_rad
    radii = (layout.shell_od_in, layout.inner_face_in, layout.outside_radius_in)
    points = [
        (radius * math.cos(angle), radius * math.sin(angle))
        for radius in radii
        for step in range(17)
        for angle in (-0.12 + (sweep + 0.24) * step / 16,)
    ]
    _paint(canvas, _PLAN, _PLAN, points, lambda locate: _plan_marks(canvas, layout, locate))


def _plan_marks(canvas: tk.Canvas, layout: StringerLayout, locate) -> None:
    canvas.create_line(*_arc(layout.shell_od_in, layout.sweep_rad, locate), fill="#8d96a0", width=2, smooth=True)
    canvas.create_line(*_arc(layout.inner_face_in, layout.sweep_rad, locate), fill="#5c6770", width=1, smooth=True)
    canvas.create_line(*_arc(layout.outside_radius_in, layout.sweep_rad, locate), fill="#2f6f86", width=4, smooth=True)
    for tread in layout.treads:
        angle = (tread.index / len(layout.treads)) * layout.sweep_rad
        canvas.create_line(
            *locate(layout.inner_face_in * math.cos(angle), layout.inner_face_in * math.sin(angle)),
            *locate(layout.outside_radius_in * math.cos(angle), layout.outside_radius_in * math.sin(angle)),
            fill="#243038",
        )


def _paint(canvas: tk.Canvas, width: int, height: int, points: list[tuple[float, float]], draw) -> None:
    margin = 16
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)
    origin_x = margin - min_x * scale
    origin_y = height - margin + min_y * scale

    def locate(x_in: float, y_in: float) -> tuple[float, float]:
        return origin_x + x_in * scale, origin_y - y_in * scale

    draw(locate)


def _arc(radius: float, sweep: float, locate) -> list[float]:
    coords: list[float] = []
    for step in range(41):
        angle = sweep * step / 40
        coords.extend(locate(radius * math.cos(angle), radius * math.sin(angle)))
    return coords
