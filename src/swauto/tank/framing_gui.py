"""Roof Framing tab: internal or external rafters, their clips, the dollar plate and the center column, on the
Roof tab's cone, with the plan drawn as it is typed."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox, ttk

from swauto.errors import SolidWorksError
from swauto.tank.framing import (
    EXTERNAL,
    INTERNAL,
    LEFT,
    RIGHT,
    Column,
    Framing,
    Layout,
    clip_outlines,
    layout,
    mode_for_roof_type,
    rafter_outline,
)
from swauto.tank.roof import RoofSpec

_CANVAS = 340
_NOTE = "#666666"
_BAD = "#c62828"
_RAFTERS = (
    ("rafter_count", "Rafters", "12", ""),
    ("rafter_width_in", "Rafter width", "4", "in"),
    ("rafter_height_in", "Rafter depth, square to the roof", "6", "in"),
    ("inner_trim_in", "Inner trim from the center, along the slope", "0", "in"),
    ("outer_trim_in", "Outer trim back from R1", "0", "in"),
    ("setback_in", "Rafter setback from the inner trim", "0", "in"),
    ("min_length_in", "Minimum rafter length (0: no check)", "0", "in"),
    ("rotation_deg", "Rotation, + clockwise", "0", "deg"),
    ("clips_per_rafter", "Clips per rafter", "2", ""),
)
_COLUMN = (
    ("dollar", "Dollar plate"),
    ("top_cap", "Top cap"),
    ("pipe", "Column pipe (OD, wall)"),
    ("bottom_cap", "Bottom cap"),
    ("base", "Base plate"),
)


def read_framing(values: dict[str, str], column_on: bool, mode: str, clips: bool, side: str) -> Framing:
    """The tab's fields as a Framing. Blank sizes are 0."""

    def number(key: str, what: str) -> float:
        text = str(values.get(key, "")).strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"{what} must be a number.") from None

    labels = {key: label for key, label, _default, _unit in _RAFTERS}
    count = number("rafter_count", "The rafter count")
    if count != int(count):
        raise ValueError("The rafter count must be a whole number.")
    clips_per = number("clips_per_rafter", "Clips per rafter")
    column = None
    if column_on:
        column = Column(
            dollar_dia_in=number("dollar_dia", "The dollar plate diameter"),
            dollar_thk_in=number("dollar_thk", "The dollar plate thickness"),
            top_cap_dia_in=number("top_cap_dia", "The top cap diameter"),
            top_cap_thk_in=number("top_cap_thk", "The top cap thickness"),
            pipe_od_in=number("pipe_dia", "The column OD"),
            pipe_wall_in=number("pipe_thk", "The column wall"),
            bottom_cap_dia_in=number("bottom_cap_dia", "The bottom cap diameter"),
            bottom_cap_thk_in=number("bottom_cap_thk", "The bottom cap thickness"),
            base_dia_in=number("base_dia", "The base plate diameter"),
            base_thk_in=number("base_thk", "The base plate thickness"),
        )
    return Framing(
        mode=mode,
        rafter_count=int(count),
        rafter_width_in=number("rafter_width_in", labels["rafter_width_in"]),
        rafter_height_in=number("rafter_height_in", labels["rafter_height_in"]),
        inner_trim_in=number("inner_trim_in", labels["inner_trim_in"]),
        outer_trim_in=number("outer_trim_in", labels["outer_trim_in"]),
        setback_in=number("setback_in", labels["setback_in"]),
        min_length_in=number("min_length_in", labels["min_length_in"]),
        rotation_deg=number("rotation_deg", labels["rotation_deg"]),
        clips=clips,
        clips_per_rafter=int(clips_per),
        clip_side=side,
        column=column,
        floor_top_in=number("floor_top", "The floor top"),
    )


def summary(plan: Layout) -> str:
    roof = plan.roof
    landing = roof.landing_radius_in()
    spacing = 2.0 * math.pi * landing / len(plan.rafters)
    r0, r1 = plan.plan_radius(plan.inner_slant_in), plan.plan_radius(plan.outer_slant_in)
    text = (
        f"{len(plan.rafters)} {plan.framing.mode} rafters, {plan.framing.rafter_width_in:g} x "
        f"{plan.framing.rafter_height_in:g} in, {plan.length_in:.3f} in long on the slope (R1 {plan.slant_in:.3f}). "
        f"In plan from {r0:.3f} to {r1:.3f} in out, {spacing:.2f} in apart at the landing."
    )
    if plan.column:
        text += "  Column: " + ", ".join(name.lower() for name, _loop in plan.column) + "."
    return text


def build_framing_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    """Fill the Roof Framing tab. ``shared["roof"]`` is the Roof tab's cone; ``shared["spec"]`` names the roof
    type, which sets internal or external."""
    if shared is None:
        shared = {}
    frame = ttk.Frame(parent, padding=10)
    frame.grid(row=0, column=0, sticky="nsew")
    ttk.Label(frame, text="Roof framing", font=("", 11, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
    ttk.Label(
        frame,
        text="As the lisp lays it out: radial box rafters (no section shape yet), clips, and the center column "
        "stack. Trims and setback run along the slope.",
        foreground=_NOTE, wraplength=760, justify="left",
    ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 6))

    mode_var = tk.StringVar(value="Internal")
    clips_var = tk.BooleanVar(value=True)
    side_var = tk.StringVar(value="Left")
    column_var = tk.BooleanVar(value=False)
    values: dict[str, tk.StringVar] = {}
    row = 2
    ttk.Label(frame, text="Rafters").grid(row=row, column=0, sticky="w")
    mode_box = ttk.Combobox(frame, textvariable=mode_var, values=("Internal", "External"), state="readonly", width=10)
    mode_box.grid(row=row, column=1, sticky="w")
    for key, label, default, unit in _RAFTERS:
        row += 1
        values[key] = tk.StringVar(value=default)
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(frame, textvariable=values[key], width=10).grid(row=row, column=1, sticky="w")
        ttk.Label(frame, text=unit, foreground=_NOTE).grid(row=row, column=2, sticky="w")
    row += 1
    ttk.Checkbutton(frame, text="Support clips, on the", variable=clips_var).grid(row=row, column=0, sticky="w")
    ttk.Combobox(frame, textvariable=side_var, values=("Left", "Right"), state="readonly", width=10).grid(
        row=row, column=1, sticky="w"
    )
    row += 1
    ttk.Checkbutton(frame, text="Center column (diameter, thickness)", variable=column_var).grid(
        row=row, column=0, sticky="w", pady=(8, 0)
    )
    for key, label in _COLUMN:
        row += 1
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(16, 0))
        for col, part in ((1, "dia"), (2, "thk")):
            values[f"{key}_{part}"] = tk.StringVar(value="0")
            ttk.Entry(frame, textvariable=values[f"{key}_{part}"], width=10).grid(row=row, column=col, sticky="w")
    row += 1
    values["floor_top"] = tk.StringVar(value="0")
    ttk.Label(frame, text="Floor top (the base plate stands on it)").grid(row=row, column=0, sticky="w", padx=(16, 0))
    ttk.Entry(frame, textvariable=values["floor_top"], width=10).grid(row=row, column=1, sticky="w")

    summary_var = tk.StringVar()
    summary_label = ttk.Label(frame, textvariable=summary_var, wraplength=760, justify="left")
    summary_label.grid(row=row + 1, column=0, columnspan=4, sticky="w", pady=(8, 4))
    build_btn = ttk.Button(frame, text="Build framing in SolidWorks")
    build_btn.grid(row=row + 2, column=0, sticky="w")
    canvas = tk.Canvas(frame, width=_CANVAS, height=_CANVAS, background="#f4f1ea", highlightthickness=1)
    canvas.grid(row=2, column=3, rowspan=row - 1, sticky="ne", padx=(16, 0))
    state: dict[str, object] = {"plan": None, "busy": False, "typed_mode": False}

    def current() -> Layout:
        roof = shared.get("roof")
        if not isinstance(roof, RoofSpec):
            raise ValueError("Set the roof on the Roof tab first.")
        framing = read_framing(
            {key: var.get() for key, var in values.items()}, column_var.get(),
            INTERNAL if mode_var.get() == "Internal" else EXTERNAL, clips_var.get(),
            LEFT if side_var.get() == "Left" else RIGHT,
        )
        return layout(framing, roof)

    def refresh(*_args) -> None:
        tank = shared.get("spec")
        if not state["typed_mode"] and tank is not None:
            chosen = mode_for_roof_type(getattr(tank, "roof_type", ""))
            if chosen is not None:
                mode_var.set("Internal" if chosen == INTERNAL else "External")
        try:
            plan = current()
        except ValueError as exc:
            state["plan"] = None
            shared["framing"] = None
            summary_var.set(str(exc))
            summary_label.configure(foreground=_BAD)
            draw(canvas, None)
            return
        state["plan"] = plan
        shared["framing"] = plan  # the Roof Nozzles plan draws the rafters under its nozzles
        warn = ("\n" + "\n".join(plan.warnings)) if plan.warnings else ""
        summary_var.set(summary(plan) + warn)
        summary_label.configure(foreground=_BAD if plan.warnings else "")
        draw(canvas, plan)

    def typed_mode(*_args) -> None:
        state["typed_mode"] = True
        refresh()

    def build() -> None:
        if state["busy"]:
            return
        refresh()
        plan = state["plan"]
        if plan is None:
            messagebox.showerror("Roof framing", summary_var.get())
            return
        try:
            from swauto.session import connect
            from swauto.tank.framing_sw import add_framing
            from swauto.tank.open_roof import find_roof_part

            model = find_roof_part(shared, connect().app)
        except (ValueError, SolidWorksError) as exc:
            messagebox.showerror("Roof framing", str(exc))
            return
        state["busy"] = True
        build_btn.configure(state="disabled")
        try:
            status_var.set(add_framing(model, plan, progress=lambda text: (status_var.set(text),
                                                                             frame.update_idletasks())))
        except (SolidWorksError, ValueError) as exc:
            status_var.set(str(exc))
            messagebox.showerror("Roof framing", str(exc))
        finally:
            state["busy"] = False
            build_btn.configure(state="normal")

    build_btn.configure(command=build)
    for var in (*values.values(), clips_var, side_var, column_var):
        var.trace_add("write", refresh)
    mode_box.bind("<<ComboboxSelected>>", typed_mode)  # picked by hand: Tank Properties' roof type no longer sets it
    shared["refresh_framing"] = refresh  # also keeps the tab's variables alive
    refresh()
    book = parent.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", lambda _event: refresh(), add="+")


def draw(canvas: tk.Canvas, plan: Layout | None) -> None:
    """The framing in plan the way Elite draws one: 0° at 12 o'clock, growing clockwise (+X to the left, +Z up)."""
    canvas.delete("all")
    if plan is None:
        return
    landing = plan.roof.landing_radius_in()
    scale = (_CANVAS / 2.0 - 14.0) / max(plan.roof.outside_radius_in, landing)
    mid = _CANVAS / 2.0

    def at(x: float, z: float) -> tuple[float, float]:
        return (mid - x * scale, mid - z * scale)

    r = landing * scale
    canvas.create_oval(mid - r, mid - r, mid + r, mid + r, outline="#8a8a8a", dash=(4, 3))
    for rafter in plan.rafters:
        canvas.create_polygon(*[c for p in rafter_outline(plan, rafter) for c in at(*p)], outline="#7a4f1d",
                              fill="#d8b98a")
        for outline in clip_outlines(plan, rafter):
            canvas.create_polygon(*[c for p in outline for c in at(*p)], outline="#3b6ea8", fill="#3b6ea8")
    for name, loop in plan.column:
        if name == "Dollar plate":
            d = max(rr for rr, _y in loop) * scale
            canvas.create_oval(mid - d, mid - d, mid + d, mid + d, outline="#555555")
    canvas.create_text(mid, 4, text="0°", anchor="n", fill=_NOTE, font=("", 8))
