"""Tank Preview tab — instant elevation / plan / 3/4 view, no SolidWorks."""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from swauto.tank.preview import PreviewScene, build_preview, isometric_ring, summary_line
from swauto.tank.project import TankProject

_SIZE = 320
_MARGIN = 18
_DEBOUNCE_MS = 120
_BG = "#f7f4ef"
_SHELL = "#3d4f5f"
_FLOOR = "#8a6a4a"
_ROOF = "#5a6e7a"
_STAIR = "#2f6f5e"
_GRID = "#d9d2c5"


def build_preview_tab(
    parent: ttk.Frame,
    status_var: tk.StringVar,
    project: TankProject | dict | None,
) -> None:
    top = ttk.Frame(parent, padding=8)
    top.grid(row=0, column=0, sticky="nsew")
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)

    ttk.Label(top, text="Tank preview", font=("", 11, "bold")).grid(row=0, column=0, columnspan=6, sticky="w")
    ttk.Label(
        top,
        text=(
            "Live check from Tank Properties / Floor / Roof — no SolidWorks wait. "
            "Change the shell and this updates. Use Build on other tabs only when the preview looks right."
        ),
        justify="left",
        wraplength=900,
    ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(0, 8))

    summary_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=summary_var, justify="left").grid(row=2, column=0, columnspan=6, sticky="w")

    views = ttk.Frame(top)
    views.grid(row=3, column=0, columnspan=6, sticky="nsew")
    top.rowconfigure(3, weight=1)

    elev_box = _view_frame(views, 0, "Elevation (section)")
    plan_box = _view_frame(views, 1, "Plan")
    iso_box = _view_frame(views, 2, "3/4 view")

    elev = tk.Canvas(elev_box, width=_SIZE, height=_SIZE, background=_BG, highlightthickness=1)
    plan = tk.Canvas(plan_box, width=_SIZE, height=_SIZE, background=_BG, highlightthickness=1)
    iso = tk.Canvas(iso_box, width=_SIZE, height=_SIZE, background=_BG, highlightthickness=1)
    elev.grid(row=1, column=0)
    plan.grid(row=1, column=0)
    iso.grid(row=1, column=0)

    show_floor = tk.BooleanVar(value=True)
    show_roof = tk.BooleanVar(value=True)
    show_plates = tk.BooleanVar(value=True)
    show_stair = tk.BooleanVar(value=True)
    toggles = ttk.Frame(top)
    toggles.grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
    ttk.Checkbutton(toggles, text="Floor", variable=show_floor).pack(side="left")
    ttk.Checkbutton(toggles, text="Roof", variable=show_roof).pack(side="left", padx=(8, 0))
    ttk.Checkbutton(toggles, text="Shell plate seams", variable=show_plates).pack(side="left", padx=(8, 0))
    ttk.Checkbutton(toggles, text="Stair OD", variable=show_stair).pack(side="left", padx=(8, 0))
    refresh_btn = ttk.Button(toggles, text="Refresh")
    refresh_btn.pack(side="left", padx=(16, 0))

    state: dict[str, object] = {"after_id": None, "scene": None}

    def tank() -> TankProject | None:
        if isinstance(project, TankProject):
            return project
        if isinstance(project, dict):
            p = project.get("project")
            return p if isinstance(p, TankProject) else None
        return None

    def paint(scene: PreviewScene) -> None:
        state["scene"] = scene
        summary_var.set(summary_line(scene))
        _draw_elevation(elev, scene, show_roof.get(), show_floor.get())
        _draw_plan(plan, scene, show_floor.get(), show_plates.get(), show_stair.get())
        _draw_iso(iso, scene, show_roof.get(), show_stair.get())

    def refresh(_reason: str = "manual") -> None:
        proj = tank()
        if proj is None:
            summary_var.set("Preview needs the shared TankProject.")
            return
        try:
            scene = build_preview(proj)
        except Exception as exc:  # noqa: BLE001
            summary_var.set(f"Preview failed: {exc}")
            return
        paint(scene)
        if _reason != "silent":
            status_var.set(f"Preview · {summary_line(scene)}")

    def schedule(_reason: str = "change") -> None:
        after_id = state["after_id"]
        if after_id is not None:
            parent.after_cancel(after_id)  # type: ignore[arg-type]
        state["after_id"] = parent.after(_DEBOUNCE_MS, lambda: refresh("silent"))

    def on_project(_proj: TankProject, reason: str) -> None:
        if reason in ("live",):
            return
        schedule(reason)

    refresh_btn.configure(command=lambda: refresh("manual"))
    for var in (show_floor, show_roof, show_plates, show_stair):
        var.trace_add("write", lambda *_: refresh("silent"))

    proj = tank()
    if proj is not None:
        proj.subscribe(on_project)
    refresh("manual")


def _view_frame(parent: ttk.Frame, column: int, title: str) -> ttk.Frame:
    box = ttk.Frame(parent)
    box.grid(row=0, column=column, sticky="nw", padx=(0, 12))
    ttk.Label(box, text=title).grid(row=0, column=0, sticky="w")
    return box


def _fit(points: list[tuple[float, float]], size: int) -> tuple[float, float, float]:
    """Return scale, offset_x, offset_y mapping model (x right, y up) → canvas."""
    if not points:
        return 1.0, size / 2, size / 2
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    usable = size - 2 * _MARGIN
    scale = min(usable / span_x, usable / span_y)
    # Center.
    mid_x = 0.5 * (min_x + max_x)
    mid_y = 0.5 * (min_y + max_y)
    ox = size / 2 - mid_x * scale
    oy = size / 2 + mid_y * scale  # flip Y
    return scale, ox, oy


def _xy(scale: float, ox: float, oy: float, x: float, y: float) -> tuple[float, float]:
    return ox + x * scale, oy - y * scale


def _poly(canvas: tk.Canvas, scale, ox, oy, points, **style) -> None:
    if len(points) < 2:
        return
    coords: list[float] = []
    for x, y in points:
        px, py = _xy(scale, ox, oy, x, y)
        coords.extend((px, py))
    canvas.create_line(*coords, **style)


def _draw_elevation(canvas: tk.Canvas, scene: PreviewScene, roof: bool, floor: bool) -> None:
    canvas.delete("all")
    pts: list[tuple[float, float]] = []
    # Mirror shell section both sides.
    for r, z in scene.shell_section_in:
        pts.append((r, z))
        pts.append((-r, z))
    if roof and scene.roof_section_in:
        for r, z in scene.roof_section_in:
            pts.append((r, z))
            pts.append((-r, z))
    if floor:
        t = scene.floor.thickness_in
        r = scene.floor.trim_radius_in()
        pts.extend(((-r, 0.0), (r, 0.0), (-r, -t), (r, -t)))
    if not pts:
        canvas.create_text(_SIZE / 2, _SIZE / 2, text="No shell yet", fill="#888")
        return
    scale, ox, oy = _fit(pts, _SIZE)
    # Ground line.
    x0, y0 = _xy(scale, ox, oy, -scene.shell_od_in, 0.0)
    x1, y1 = _xy(scale, ox, oy, scene.shell_od_in, 0.0)
    canvas.create_line(x0, y0, x1, y1, fill=_GRID)
    # Shell both halves.
    right = list(scene.shell_section_in)
    left = [(-r, z) for r, z in scene.shell_section_in]
    _poly(canvas, scale, ox, oy, right, fill=_SHELL, width=2)
    _poly(canvas, scale, ox, oy, left, fill=_SHELL, width=2)
    if floor:
        t = scene.floor.thickness_in
        r = scene.floor.trim_radius_in()
        floor_poly = [(-r, 0.0), (r, 0.0), (r, -t), (-r, -t), (-r, 0.0)]
        _poly(canvas, scale, ox, oy, floor_poly, fill=_FLOOR, width=2)
    if roof and scene.roof_section_in:
        right_r = list(scene.roof_section_in)
        left_r = [(-r, z) for r, z in scene.roof_section_in]
        # Close roof fill lightly via outline.
        _poly(canvas, scale, ox, oy, right_r + [(right_r[0][0], right_r[0][1])], fill=_ROOF, width=2)
        _poly(canvas, scale, ox, oy, left_r + [(left_r[0][0], left_r[0][1])], fill=_ROOF, width=2)
    canvas.create_text(8, 8, anchor="nw", text="CL", fill="#888", font=("", 8))


def _draw_plan(
    canvas: tk.Canvas,
    scene: PreviewScene,
    floor: bool,
    plates: bool,
    stair: bool,
) -> None:
    canvas.delete("all")
    r_shell = scene.shell_od_in / 2.0
    if r_shell <= 0:
        canvas.create_text(_SIZE / 2, _SIZE / 2, text="No shell yet", fill="#888")
        return
    pts = [(-r_shell, -r_shell), (r_shell, r_shell)]
    if floor:
        rt = scene.floor.trim_radius_in()
        pts.extend(((-rt, -rt), (rt, rt)))
    scale, ox, oy = _fit(pts, _SIZE)
    # Shell OD / ID hint.
    _circle(canvas, scale, ox, oy, 0, 0, r_shell, outline=_SHELL, width=2)
    if scene.course_bands_in:
        _circle(
            canvas,
            scale,
            ox,
            oy,
            0,
            0,
            scene.course_bands_in[0][3],
            outline="#9aa7b2",
            dash=(3, 2),
        )
    if floor:
        for plate in scene.floor_plates:
            poly = list(plate.polygon_in)
            if len(poly) >= 3:
                # polygon_in is (x, z) in plan.
                coords = []
                for x, z in poly + [poly[0]]:
                    px, py = _xy(scale, ox, oy, x, z)
                    coords.extend((px, py))
                canvas.create_line(*coords, fill=_FLOOR, width=1)
        _circle(canvas, scale, ox, oy, 0, 0, scene.floor.trim_radius_in(), outline=_FLOOR, dash=(4, 2))
    if plates:
        # Radial seams for course 1 only (readable).
        for plate in scene.shell_plates:
            if plate.course_no != 1:
                continue
            for az in (plate.start_rad, plate.start_rad + plate.sweep_rad):
                x = r_shell * math.cos(az)
                z = r_shell * math.sin(az)
                _poly(canvas, scale, ox, oy, [(0.0, 0.0), (x, z)], fill="#b0b8c0", width=1)
    if stair:
        walk = scene.stair_od_in / 2.0 + scene.stair_gap_in
        _circle(canvas, scale, ox, oy, 0, 0, walk, outline=_STAIR, dash=(5, 3), width=2)


def _draw_iso(canvas: tk.Canvas, scene: PreviewScene, roof: bool, stair: bool) -> None:
    canvas.delete("all")
    if scene.shell_od_in <= 0 or not scene.course_bands_in:
        canvas.create_text(_SIZE / 2, _SIZE / 2, text="No shell yet", fill="#888")
        return
    rings: list[tuple[float, float]] = []
    for z0, z1, r_out, _r_in in scene.course_bands_in:
        rings.extend(isometric_ring(r_out, z0))
        rings.extend(isometric_ring(r_out, z1))
    if roof and scene.roof_section_in:
        peak_z = max(z for _r, z in scene.roof_section_in)
        land_r = scene.roof.landing_radius_in()
        rings.extend(isometric_ring(land_r, scene.roof.landing_height_in()))
        rings.extend(isometric_ring(0.05, peak_z))
    scale, ox, oy = _fit(rings, _SIZE)
    for z0, z1, r_out, _r_in in scene.course_bands_in:
        bot = isometric_ring(r_out, z0)
        top = isometric_ring(r_out, z1)
        _poly(canvas, scale, ox, oy, bot, fill=_SHELL, width=1)
        _poly(canvas, scale, ox, oy, top, fill=_SHELL, width=2)
        # Generators at cardinal angles.
        for i in (0, len(bot) // 4, len(bot) // 2, 3 * len(bot) // 4):
            _poly(canvas, scale, ox, oy, [bot[i], top[i]], fill="#7a8792", width=1)
    if roof and scene.roof_section_in:
        land_r = scene.roof.landing_radius_in()
        land = isometric_ring(land_r, scene.roof.landing_height_in())
        peak_z = max(z for _r, z in scene.roof_section_in)
        peak = isometric_ring(0.05, peak_z)[0]
        _poly(canvas, scale, ox, oy, land, fill=_ROOF, width=2)
        for i in (0, len(land) // 4, len(land) // 2, 3 * len(land) // 4):
            _poly(canvas, scale, ox, oy, [land[i], peak], fill=_ROOF, width=1)
    if stair:
        walk = scene.stair_od_in / 2.0 + scene.stair_gap_in
        _poly(canvas, scale, ox, oy, isometric_ring(walk, 0.0), fill=_STAIR, width=2, dash=(4, 2))


def _circle(canvas, scale, ox, oy, cx, cy, radius, **style) -> None:
    x0, y0 = _xy(scale, ox, oy, cx - radius, cy + radius)
    x1, y1 = _xy(scale, ox, oy, cx + radius, cy - radius)
    canvas.create_oval(x0, y0, x1, y1, **style)

