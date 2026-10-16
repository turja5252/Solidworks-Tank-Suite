"""Roof tab: one cone, previewed as a section, then revolved in SolidWorks."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox, ttk

from swauto.comutil import format_com_error
from swauto.errors import SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import connect
from swauto.tank.roof import (
    RING_ANGLE,
    RING_BAR,
    RING_NONE,
    RoofSpec,
    cone_profile_in,
    course_break_plan_radii,
    flat_outline_in,
    flat_pattern,
    layout_roof_plates,
    ring_profile_in,
    roof_from_tank,
)
from swauto.tank.roof_sw import create_roof
from swauto.tank.spec import TankSpec

_CANVAS = 280
_RING_LABELS = ("None", "Flat bar", "Angle")
_RING_VALUES = (RING_NONE, RING_BAR, RING_ANGLE)


def build_roof_tab(parent: ttk.Frame, status_var: tk.StringVar, holder: dict | None = None) -> None:
    spec = RoofSpec()
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    scroller = tk.Canvas(parent, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=scroller.yview)
    scroller.configure(yscrollcommand=scrollbar.set)
    scroller.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    top = ttk.Frame(scroller, padding=12)
    top_id = scroller.create_window((0, 0), window=top, anchor="nw")

    def _fit_scroll_width(event) -> None:
        scroller.itemconfigure(top_id, width=event.width)

    def _fit_scroll_region(_event=None) -> None:
        scroller.configure(scrollregion=scroller.bbox("all"))

    scroller.bind("<Configure>", _fit_scroll_width)
    top.bind("<Configure>", _fit_scroll_region)

    ttk.Label(top, text="Cone roof", font=("", 11, "bold")).grid(row=0, column=0, columnspan=8, sticky="w")
    ttk.Label(
        top,
        text=(
            "One cone, cone-up, the same shape as the GA cross-section. "
            "With no ring it bears on the inside of the top course. "
            "A flat bar or an angle sits outside the shell, and the cone bears on top of that ring. "
            "Landing inset is measured out from the shell outside face. "
            "The flat pattern is the cone unrolled to the slant diameter. "
            "Ignore pie cut closes a small gap in the seam laps."
        ),
        justify="left",
        wraplength=640,
    ).grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 8))

    inside_var = tk.StringVar(value=f"{spec.inside_radius_in:g}")
    outside_var = tk.StringVar(value=f"{spec.outside_radius_in:g}")
    height_var = tk.StringVar(value=f"{spec.shell_height_in:g}")
    slope_var = tk.StringVar(value=f"{spec.slope_in_per_ft:g}")
    thickness_var = tk.StringVar(value=f"{spec.thickness_in:g}")
    ring_var = tk.StringVar(value=_RING_LABELS[0])
    offset_var = tk.StringVar(value=f"{spec.ring_top_offset_in:g}")
    inset_var = tk.StringVar(value=f"{spec.landing_inset_in:g}")
    bar_width_var = tk.StringVar(value=f"{spec.bar_width_in:g}")
    bar_height_var = tk.StringVar(value=f"{spec.bar_height_in:g}")
    angle_h_var = tk.StringVar(value=f"{spec.angle_horizontal_in:g}")
    angle_v_var = tk.StringVar(value=f"{spec.angle_vertical_in:g}")
    angle_t_var = tk.StringVar(value=f"{spec.angle_thickness_in:g}")
    width_var = tk.StringVar(value=f"{spec.plate_width_in:g}")
    length_var = tk.StringVar(value=f"{spec.plate_length_in:g}")
    lap_var = tk.StringVar(value=f"{spec.plate_lap_in:g}")
    ignore_var = tk.BooleanVar(value=spec.ignore_pie)

    _field(top, 2, 0, "Inside radius", inside_var, "in")
    _field(top, 2, 3, "Outside radius", outside_var, "in")
    _field(top, 3, 0, "Shell height", height_var, "in")
    _field(top, 3, 3, "Slope", slope_var, "in/ft")
    _field(top, 4, 0, "Roof thickness", thickness_var, "in")
    ttk.Label(top, text="Compression ring").grid(row=5, column=0, sticky="w", pady=(6, 0))
    ttk.Combobox(top, textvariable=ring_var, values=_RING_LABELS, width=12, state="readonly").grid(
        row=5, column=1, columnspan=2, sticky="w", pady=(6, 0)
    )
    _field(top, 6, 0, "Top offset", offset_var, "in")
    _field(top, 6, 3, "Landing inset", inset_var, "in")
    _field(top, 7, 0, "Bar width", bar_width_var, "in")
    _field(top, 7, 3, "Bar height", bar_height_var, "in")
    _field(top, 8, 0, "Angle horizontal", angle_h_var, "in")
    _field(top, 8, 3, "Angle vertical", angle_v_var, "in")
    _field(top, 9, 0, "Angle thickness", angle_t_var, "in")
    _field(top, 10, 0, "Plate width", width_var, "in")
    _field(top, 10, 3, "Plate length", length_var, "in")
    _field(top, 11, 0, "Plate lap", lap_var, "in")
    ttk.Checkbutton(top, text="Ignore pie cut", variable=ignore_var).grid(
        row=11, column=3, columnspan=3, sticky="w", pady=(4, 0)
    )
    ttk.Button(
        top,
        text="Use tank shell",
        command=lambda: _use_tank(holder, inside_var, outside_var, height_var),
    ).grid(row=12, column=0, columnspan=3, sticky="w", pady=(6, 0))

    summary_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=summary_var, justify="left").grid(
        row=13, column=0, columnspan=8, sticky="w", pady=(6, 4)
    )

    previews = ttk.Frame(top)
    previews.grid(row=14, column=0, columnspan=8, sticky="w")

    section_box = ttk.Frame(previews)
    section_box.grid(row=0, column=0, sticky="n")
    ttk.Label(section_box, text="Section").grid(row=0, column=0, sticky="w")
    canvas = tk.Canvas(section_box, width=_CANVAS, height=_CANVAS, background="#f4f1ea", highlightthickness=1)
    canvas.grid(row=1, column=0, sticky="w")
    tools = ttk.Frame(section_box)
    tools.grid(row=2, column=0, sticky="w", pady=(4, 0))
    fit_btn = ttk.Button(tools, text="Fit tank")
    fit_btn.grid(row=0, column=0, sticky="w")
    ring_btn = ttk.Button(tools, text="Zoom to ring")
    ring_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))

    flat_box = ttk.Frame(previews)
    flat_box.grid(row=0, column=1, sticky="n", padx=(12, 0))
    ttk.Label(flat_box, text="Flat pattern").grid(row=0, column=0, sticky="w")
    flat_canvas = tk.Canvas(flat_box, width=_CANVAS, height=_CANVAS, background="#f4f1ea", highlightthickness=1)
    flat_canvas.grid(row=1, column=0, sticky="w")
    ttk.Label(flat_box, text="Dashed circle is the plan landing.").grid(row=2, column=0, sticky="w", pady=(4, 0))

    build_btn = ttk.Button(top, text="Build roof in SolidWorks")
    build_btn.grid(row=15, column=0, columnspan=3, sticky="w", pady=(8, 0))
    state: dict[str, object] = {"model": None, "busy": False, "drag": None, "flat_drag": None}
    view = {"scale": None, "cx": None, "base": None}
    flat_view = {"scale": None, "cx": None, "base": None}
    shown: dict[str, object] = {"spec": None, "profile": (), "ring": (), "plates": ()}

    def read_spec() -> RoofSpec:
        try:
            ring = _RING_VALUES[_RING_LABELS.index(ring_var.get())]
        except ValueError:
            ring = RING_NONE
        try:
            return RoofSpec(
                inside_radius_in=float(inside_var.get().strip()),
                outside_radius_in=float(outside_var.get().strip()),
                shell_height_in=float(height_var.get().strip()),
                slope_in_per_ft=float(slope_var.get().strip()),
                thickness_in=float(thickness_var.get().strip()),
                ring=ring,
                ring_top_offset_in=float(offset_var.get().strip() or 0),
                landing_inset_in=float(inset_var.get().strip() or 0),
                bar_width_in=float(bar_width_var.get().strip() or 0),
                bar_height_in=float(bar_height_var.get().strip() or 0),
                angle_horizontal_in=float(angle_h_var.get().strip() or 0),
                angle_vertical_in=float(angle_v_var.get().strip() or 0),
                angle_thickness_in=float(angle_t_var.get().strip() or 0),
                ignore_pie=bool(ignore_var.get()),
                plate_width_in=float(width_var.get().strip()),
                plate_length_in=float(length_var.get().strip()),
                plate_lap_in=float(lap_var.get().strip() or 0),
            )
        except ValueError as exc:
            raise ValueError("Roof values must be numeric.") from exc

    def refresh(*_args) -> None:
        if state["busy"]:
            return
        try:
            spec_now = read_spec()
            spec_now.validate()
            profile = cone_profile_in(spec_now)
            ring_profile = ring_profile_in(spec_now)
            plates = layout_roof_plates(spec_now)
        except ValueError as exc:
            summary_var.set(str(exc))
            canvas.delete("all")
            flat_canvas.delete("all")
            return
        pattern = flat_pattern(spec_now)
        landing = "on the compression ring" if spec_now.ring_active() else "on the shell inside"
        gap_deg = 360.0 - pattern.sector_deg
        pie = "pie cut ignored, closed in the laps" if spec_now.ignore_pie else "pie cut kept"
        summary_var.set(
            f"{_ring_name(spec_now)} · cone {landing} at {spec_now.landing_radius_in():.3f} in, "
            f"height {spec_now.landing_height_in():.3f} in · "
            f"rise {spec_now.rise_in():.3f} in · peak at {spec_now.peak_height_in():.3f} in\n"
            f"Flat diameter {pattern.diameter_in:.3f} in · pie cut {gap_deg:.2f}° · {pie} · "
            f"{len(plates)} plates"
        )
        shown["spec"] = spec_now
        shown["profile"] = profile
        shown["ring"] = ring_profile
        shown["plates"] = plates
        _draw(canvas, spec_now, profile, ring_profile, view)
        _draw_flat(flat_canvas, spec_now, flat_view, plates)

    def redraw() -> None:
        spec_now = shown["spec"]
        if not isinstance(spec_now, RoofSpec):
            return
        _draw(canvas, spec_now, shown["profile"], shown["ring"], view)

    def redraw_flat() -> None:
        spec_now = shown["spec"]
        if not isinstance(spec_now, RoofSpec):
            return
        _draw_flat(flat_canvas, spec_now, flat_view, shown.get("plates") or ())

    def fit_tank() -> None:
        view["scale"] = None
        redraw()

    def zoom_ring() -> None:
        spec_now = shown["spec"]
        if not isinstance(spec_now, RoofSpec):
            return
        view["scale"], view["cx"], view["base"] = _fit_window(*_ring_window(spec_now))
        redraw()

    def on_wheel(event) -> None:
        old = view["scale"]
        if old is None:
            return
        factor = 1.35 if event.delta > 0 else 1 / 1.35
        new = min(80.0, max(0.02, old * factor))
        world_r = (event.x - view["cx"]) / old
        world_y = (view["base"] - event.y) / old
        view["scale"] = new
        view["cx"] = event.x - world_r * new
        view["base"] = event.y + world_y * new
        redraw()

    def on_press(event) -> None:
        state["drag"] = (event.x, event.y, view["cx"], view["base"])

    def on_drag(event) -> None:
        drag = state["drag"]
        if drag is None or view["cx"] is None:
            return
        x0, y0, cx0, base0 = drag
        view["cx"] = cx0 + (event.x - x0)
        view["base"] = base0 + (event.y - y0)
        redraw()

    def on_double(_event) -> None:
        fit_tank()

    def on_flat_wheel(event) -> None:
        _wheel_view(flat_view, event)
        redraw_flat()

    def on_flat_press(event) -> None:
        state["flat_drag"] = (event.x, event.y, flat_view["cx"], flat_view["base"])

    def on_flat_drag(event) -> None:
        drag = state["flat_drag"]
        if drag is None or flat_view["cx"] is None:
            return
        x0, y0, cx0, base0 = drag
        flat_view["cx"] = cx0 + (event.x - x0)
        flat_view["base"] = base0 + (event.y - y0)
        redraw_flat()

    def on_flat_double(_event) -> None:
        flat_view["scale"] = None
        redraw_flat()

    def build() -> None:
        if state["busy"]:
            return
        try:
            spec_now = read_spec()
            spec_now.validate()
        except ValueError as exc:
            messagebox.showerror("Roof", str(exc))
            return
        state["busy"] = True
        build_btn.configure(state="disabled")
        status_var.set("Building cone roof…")
        parent.update_idletasks()
        try:
            session = connect()
            model = state["model"]
            if model is None and holder is not None:
                live = holder.get("live")
                model = getattr(live, "model", None)
            result = create_roof(session.app, spec_now, model=model)
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            state["busy"] = False
            build_btn.configure(state="normal")
            status_var.set("Roof build failed.")
            messagebox.showerror("Roof", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            state["busy"] = False
            build_btn.configure(state="normal")
            status_var.set("Roof build failed.")
            messagebox.showerror("Roof", format_com_error(exc))
            return
        state["model"] = result.model
        state["busy"] = False
        build_btn.configure(text="Rebuild roof", state="normal")
        status_var.set(f"Roof → {result.title}")
        refresh()

    build_btn.configure(command=build)
    fit_btn.configure(command=fit_tank)
    ring_btn.configure(command=zoom_ring)
    canvas.bind("<MouseWheel>", on_wheel)
    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<Double-Button-1>", on_double)
    flat_canvas.bind("<MouseWheel>", on_flat_wheel)
    flat_canvas.bind("<ButtonPress-1>", on_flat_press)
    flat_canvas.bind("<B1-Motion>", on_flat_drag)
    flat_canvas.bind("<Double-Button-1>", on_flat_double)

    def on_page_wheel(event) -> None:
        if event.widget in (canvas, flat_canvas):
            return
        scroller.yview_scroll(int(-event.delta / 120), "units")

    _bind_page_wheel(top, on_page_wheel, (canvas, flat_canvas))
    scroller.bind("<MouseWheel>", on_page_wheel)
    for var in (
        inside_var,
        outside_var,
        height_var,
        slope_var,
        thickness_var,
        ring_var,
        offset_var,
        inset_var,
        bar_width_var,
        bar_height_var,
        angle_h_var,
        angle_v_var,
        angle_t_var,
        width_var,
        length_var,
        lap_var,
        ignore_var,
    ):
        var.trace_add("write", refresh)
    refresh()


def _field(parent, row: int, column: int, label: str, variable: tk.StringVar, unit: str) -> None:
    ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=(4, 0))
    ttk.Entry(parent, textvariable=variable, width=10).grid(row=row, column=column + 1, sticky="w", pady=(4, 0))
    ttk.Label(parent, text=unit).grid(row=row, column=column + 2, sticky="w", padx=(2, 10), pady=(4, 0))


def _use_tank(
    holder: dict | None,
    inside_var: tk.StringVar,
    outside_var: tk.StringVar,
    height_var: tk.StringVar,
) -> None:
    spec = holder.get("spec") if holder else None
    if not isinstance(spec, TankSpec) or not spec.active_courses():
        messagebox.showerror("Roof", "Set a shell on Tank Properties first.")
        return
    try:
        roof = roof_from_tank(spec, slope_in_per_ft=0.0, thickness_in=0.25)
    except ValueError as exc:
        messagebox.showerror("Roof", str(exc))
        return
    inside_var.set(f"{roof.inside_radius_in:.6g}")
    outside_var.set(f"{roof.outside_radius_in:.6g}")
    height_var.set(f"{roof.shell_height_in:.6g}")


def _bind_page_wheel(widget, handler, skip: tuple) -> None:
    if widget in skip:
        return
    widget.bind("<MouseWheel>", handler)
    for child in widget.winfo_children():
        _bind_page_wheel(child, handler, skip)


def _wheel_view(view: dict, event) -> None:
    old = view["scale"]
    if old is None:
        return
    factor = 1.35 if event.delta > 0 else 1 / 1.35
    new = min(80.0, max(0.02, old * factor))
    world_x = (event.x - view["cx"]) / old
    world_y = (view["base"] - event.y) / old
    view["scale"] = new
    view["cx"] = event.x - world_x * new
    view["base"] = event.y + world_y * new


def _ring_name(spec: RoofSpec) -> str:
    if spec.ring == RING_BAR and spec.ring_active():
        return "Flat bar"
    if spec.ring == RING_ANGLE and spec.ring_active():
        return "Angle"
    if spec.ring == RING_NONE:
        return "No ring"
    return "Ring off until its sizes are filled in"


def _polygon(canvas: tk.Canvas, points: tuple[tuple[float, float], ...], locate, **style) -> None:
    coords: list[float] = []
    for radius, height in points:
        px, py = locate(radius, height)
        coords.extend((px, py))
    if len(coords) >= 6:
        canvas.create_polygon(*coords, **style)


def _both_sides(canvas: tk.Canvas, points: tuple[tuple[float, float], ...], locate, **style) -> None:
    _polygon(canvas, points, locate, **style)
    _polygon(canvas, tuple((-radius, height) for radius, height in points), locate, **style)


def _fit_all(outer: float, peak: float) -> tuple[float, float, float]:
    span = max(outer, peak, 1.0)
    margin = 28
    scale = (_CANVAS - 2 * margin) / (2.0 * span)
    return scale, _CANVAS / 2, _CANVAS - margin


def _fit_window(r0: float, r1: float, y0: float, y1: float) -> tuple[float, float, float]:
    margin = 28
    scale = min((_CANVAS - 2 * margin) / max(r1 - r0, 0.25), (_CANVAS - 2 * margin) / max(y1 - y0, 0.25))
    return scale, margin - r0 * scale, (_CANVAS - margin) + y0 * scale


def _ring_window(spec: RoofSpec) -> tuple[float, float, float, float]:
    outside = spec.outside_radius_in
    top = spec.landing_height_in() if spec.ring_active() else spec.shell_height_in
    stick = max(spec.landing_inset_in, spec.thickness_in, 1.0)
    drop = 1.0
    if spec.ring == RING_BAR:
        stick = max(stick, spec.bar_width_in)
        drop = max(drop, spec.bar_height_in)
    elif spec.ring == RING_ANGLE:
        stick = max(stick, spec.angle_horizontal_in)
        drop = max(drop, spec.angle_vertical_in)
    pad = max(stick, drop) * 0.6
    return outside - pad, outside + stick + pad, top - drop - pad, top + pad + spec.thickness_in


def _draw(
    canvas: tk.Canvas,
    spec: RoofSpec,
    profile: tuple[tuple[float, float], ...],
    ring: tuple[tuple[float, float], ...],
    view: dict,
) -> None:
    canvas.delete("all")
    radii = [point[0] for point in profile]
    heights = [point[1] for point in profile]
    radii.extend(abs(point[0]) for point in ring)
    heights.extend(point[1] for point in ring)
    radii.append(spec.outside_radius_in)
    if view["scale"] is None:
        view["scale"], view["cx"], view["base"] = _fit_all(max(radii), max(heights))
    scale = view["scale"]
    cx = view["cx"]
    base = view["base"]

    def locate(radius: float, height: float) -> tuple[float, float]:
        return cx + radius * scale, base - height * scale

    shell = (
        (spec.inside_radius_in, 0.0),
        (spec.outside_radius_in, 0.0),
        (spec.outside_radius_in, spec.shell_height_in),
        (spec.inside_radius_in, spec.shell_height_in),
    )
    _both_sides(canvas, shell, locate, fill="#d5dbe0", outline="#8d96a0", width=1)
    if ring:
        _both_sides(canvas, ring, locate, fill="#8a9aab", outline="#243038", width=2)
    _both_sides(canvas, profile, locate, fill="#c4b49a", outline="#243038", width=2)
    canvas.create_line(*locate(0.0, 0.0), *locate(0.0, max(heights)), fill="#2c3338", dash=(3, 3))
    for plan_radius in course_break_plan_radii(spec):
        rise = spec.rise_in()
        landing = spec.landing_radius_in()
        height = spec.landing_height_in() + rise * (1.0 - plan_radius / landing)
        for side in (1.0, -1.0):
            px, py = locate(side * plan_radius, height)
            canvas.create_oval(px - 3, py - 3, px + 3, py + 3, fill="#243038", outline="")


def _draw_flat(canvas: tk.Canvas, spec: RoofSpec, view: dict, plates) -> None:
    canvas.delete("all")
    pattern = flat_pattern(spec)
    outline = flat_outline_in(spec, step_deg=2.0)
    span = max(pattern.slant_in, 1.0)
    if view["scale"] is None:
        margin = 28
        view["scale"] = (_CANVAS - 2 * margin) / (2.0 * span)
        view["cx"] = _CANVAS / 2
        view["base"] = _CANVAS / 2
    scale = view["scale"]
    cx = view["cx"]
    base = view["base"]

    def locate(local_x: float, local_z: float) -> tuple[float, float]:
        return cx + local_x * scale, base - local_z * scale

    coords: list[float] = []
    for local_x, local_z in outline:
        px, py = locate(local_x, local_z)
        coords.extend((px, py))
    canvas.create_polygon(*coords, fill="#e7efe8", outline="")
    for plate in plates:
        plate_coords: list[float] = []
        for local_x, local_z in plate.polygon_in:
            px, py = locate(local_x, local_z)
            plate_coords.extend((px, py))
        red, green, blue = plate.color()
        fill = f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"
        canvas.create_polygon(*plate_coords, fill=fill, outline="#243038", width=1)
    plan = spec.landing_radius_in()
    steps = 72
    rim = [
        locate(plan * math.cos(2.0 * math.pi * index / steps), plan * math.sin(2.0 * math.pi * index / steps))
        for index in range(steps)
    ]
    for start, end in zip(rim, rim[1:] + rim[:1], strict=False):
        canvas.create_line(*start, *end, fill="#5c6770", dash=(4, 3))
    canvas.create_oval(cx - 3, base - 3, cx + 3, base + 3, fill="#243038", outline="")
