"""Floor tab: lap-welded plate plan, animated one row at a time."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from swauto.comutil import format_com_error
from swauto.errors import SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import connect
from swauto.tank.floor import (
    CENTER_PLATE,
    CENTER_SEAM,
    FloorPlate,
    FloorSpec,
    floor_rows,
    layout_floor,
    row_color_hex,
)
from swauto.tank.floor_sw import create_floor
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import TankSpec

_CENTER_LABELS = ("Plate on centerline", "Seam on centerline")
_CENTER_VALUES = (CENTER_PLATE, CENTER_SEAM)
_PLAY_MS = 420
_BUILD_PAUSE_S = 0.65
_CANVAS = 340


def build_floor_tab(parent: ttk.Frame, status_var: tk.StringVar, holder: dict | None = None) -> None:
    spec = FloorSpec()
    state: dict[str, object] = {"model": None, "busy": False, "after_id": None}

    top = ttk.Frame(parent, padding=8)
    top.grid(row=0, column=0, sticky="nsew")
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)

    ttk.Label(top, text="Shoulder plates", font=("", 11, "bold")).grid(row=0, column=0, columnspan=8, sticky="w")
    ttk.Label(
        top,
        text=(
            "Plate width runs across the centerline. Max length is the plate length, square to that width. "
            "Plate on centerline centers one plate on the line, then adds full plates left and right until the next one would leave the circle. "
            "Seam on centerline centers the lap on the line, with the seam half a lap to the right. "
            "Rotation turns the whole row counterclockwise."
        ),
        justify="left",
        wraplength=640,
    ).grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 8))

    diameter_var = tk.StringVar(value=f"{spec.diameter_in:g}")
    thickness_var = tk.StringVar(value=f"{spec.thickness_in:g}")
    width_var = tk.StringVar(value=f"{spec.plate_width_in:g}")
    length_var = tk.StringVar(value=f"{spec.max_length_in:g}")
    lap_var = tk.StringVar(value=f"{spec.lap_in:g}")
    center_var = tk.StringVar(value=_CENTER_LABELS[0])
    shift_var = tk.StringVar(value=f"{spec.center_shift_in:g}")
    rotation_var = tk.StringVar(value=f"{spec.rotation_deg:g}")

    _field(top, 2, 0, "Diameter", diameter_var, "in")
    _field(top, 2, 3, "Thickness", thickness_var, "in")
    _field(top, 3, 0, "Plate width", width_var, "in")
    _field(top, 3, 3, "Max length", length_var, "in")
    _field(top, 4, 0, "Lap", lap_var, "in")
    _field(top, 4, 3, "Rotation", rotation_var, "deg")
    ttk.Label(top, text="Center").grid(row=5, column=0, sticky="w", pady=(6, 0))
    ttk.Combobox(top, textvariable=center_var, values=_CENTER_LABELS, width=18, state="readonly").grid(
        row=5, column=1, columnspan=2, sticky="w", pady=(6, 0)
    )
    _field(top, 6, 0, "Center shift", shift_var, "in")
    ttk.Button(top, text="Use course 1 OD", command=lambda: _use_shell_od(holder, diameter_var)).grid(
        row=7, column=3, columnspan=2, sticky="w", pady=(6, 0)
    )

    summary_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=summary_var, justify="left").grid(
        row=8, column=0, columnspan=8, sticky="w", pady=(6, 4)
    )

    canvas = tk.Canvas(top, width=_CANVAS, height=_CANVAS, background="#f4f1ea", highlightthickness=1)
    canvas.grid(row=9, column=0, columnspan=8, sticky="w")

    btn_row = ttk.Frame(top)
    btn_row.grid(row=10, column=0, columnspan=8, sticky="ew", pady=(8, 0))
    build_btn = ttk.Button(btn_row, text="Build floor in SolidWorks")
    build_btn.pack(side="left")
    play_btn = ttk.Button(btn_row, text="Play rows")
    play_btn.pack(side="left", padx=6)

    def read_spec() -> FloorSpec:
        try:
            center = _CENTER_VALUES[_CENTER_LABELS.index(center_var.get())]
        except ValueError:
            center = CENTER_PLATE
        try:
            return FloorSpec(
                diameter_in=float(diameter_var.get().strip()),
                thickness_in=float(thickness_var.get().strip()),
                plate_width_in=float(width_var.get().strip()),
                max_length_in=float(length_var.get().strip()),
                lap_in=float(lap_var.get().strip()),
                center=center,
                center_shift_in=float(shift_var.get().strip() or 0),
                rotation_deg=float(rotation_var.get().strip() or 0),
            )
        except ValueError as exc:
            raise ValueError("Floor values must be numeric.") from exc

    def current_rows() -> tuple[FloorSpec, list[list[FloorPlate]]]:
        spec_now = read_spec()
        spec_now.validate()
        return spec_now, floor_rows(layout_floor(spec_now))

    def refresh(*_args) -> None:
        if state["busy"]:
            return
        try:
            spec_now, rows = current_rows()
        except ValueError as exc:
            summary_var.set(str(exc))
            canvas.delete("all")
            return
        count = sum(len(row) for row in rows)
        note = spec_now.lap_note()
        text = (
            f"Shoulder {count} plates · rotate {spec_now.rotation_deg:g}°"
        )
        if note:
            text = f"{text}\n{note}"
        summary_var.set(text)
        _draw(canvas, spec_now, rows, highlight=None)

    def play() -> None:
        if state["busy"]:
            return
        try:
            spec_now, rows = current_rows()
        except ValueError as exc:
            messagebox.showerror("Floor", str(exc))
            return
        if not rows:
            messagebox.showerror("Floor", "No floor plates for these sizes.")
            return
        _cancel_play()
        state["busy"] = True
        play_btn.configure(state="disabled")
        build_btn.configure(state="disabled")

        def show(index: int) -> None:
            if index >= len(rows):
                state["busy"] = False
                state["after_id"] = None
                play_btn.configure(state="normal")
                build_btn.configure(state="normal")
                _draw(canvas, spec_now, rows, highlight=None)
                status_var.set(f"Floor layout · {len(rows)} rows")
                return
            _draw(canvas, spec_now, rows[: index + 1], highlight=index)
            status_var.set(f"Floor row {index + 1} of {len(rows)}")
            state["after_id"] = parent.after(_PLAY_MS, lambda: show(index + 1))

        _draw(canvas, spec_now, [], highlight=None)
        status_var.set("Floor row 0")
        state["after_id"] = parent.after(_PLAY_MS, lambda: show(0))

    def _cancel_play() -> None:
        after_id = state["after_id"]
        if after_id is not None:
            parent.after_cancel(after_id)  # type: ignore[arg-type]
            state["after_id"] = None

    def build() -> None:
        if state["busy"]:
            return
        try:
            spec_now, rows = current_rows()
        except ValueError as exc:
            messagebox.showerror("Floor", str(exc))
            return
        if not rows:
            messagebox.showerror("Floor", "No floor plates for these sizes.")
            return
        _cancel_play()
        state["busy"] = True
        build_btn.configure(state="disabled")
        play_btn.configure(state="disabled")
        _draw(canvas, spec_now, [], highlight=None)
        status_var.set("Starting floor…")
        parent.update()
        root = parent.winfo_toplevel()
        try:
            session = connect()
            model = state["model"]
            if model is None and holder is not None:
                live = holder.get("live")
                model = getattr(live, "model", None)

            def on_row(number: int, total: int) -> None:
                _draw(canvas, spec_now, rows[:number], highlight=number - 1)
                status_var.set(f"Floor row {number} of {total} — watch SolidWorks")
                root.update()

            result = create_floor(
                session.app,
                spec_now,
                model=model,
                on_row=on_row,
                pause_s=_BUILD_PAUSE_S,
            )
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            state["busy"] = False
            build_btn.configure(state="normal")
            play_btn.configure(state="normal")
            status_var.set("Floor build failed.")
            messagebox.showerror("Floor", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            state["busy"] = False
            build_btn.configure(state="normal")
            play_btn.configure(state="normal")
            status_var.set("Floor build failed.")
            messagebox.showerror("Floor", format_com_error(exc))
            return

        state["model"] = result.model
        state["busy"] = False
        build_btn.configure(text="Rebuild floor", state="normal")
        play_btn.configure(state="normal")
        _draw(canvas, spec_now, rows, highlight=None)
        if result.note:
            status_var.set(result.note)
            messagebox.showwarning("Floor", result.note)
        else:
            status_var.set(
                f"Floor → {result.title}   ({result.row_count} rows, {result.plate_count} plates)"
            )

    build_btn.configure(command=build)
    play_btn.configure(command=play)
    for var in (
        diameter_var,
        thickness_var,
        width_var,
        length_var,
        lap_var,
        rotation_var,
        center_var,
        shift_var,
    ):
        var.trace_add("write", refresh)
    refresh()


def _field(parent, row: int, column: int, label: str, variable: tk.StringVar, unit: str) -> None:
    ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=(4, 0))
    ttk.Entry(parent, textvariable=variable, width=8).grid(row=row, column=column + 1, sticky="w", pady=(4, 0))
    ttk.Label(parent, text=unit).grid(row=row, column=column + 2, sticky="w", padx=(2, 10), pady=(4, 0))


def _use_shell_od(holder: dict | None, diameter_var: tk.StringVar) -> None:
    spec = holder.get("spec") if holder else None
    if not isinstance(spec, TankSpec) or not spec.active_courses():
        messagebox.showerror("Floor", "Set a shell on Tank Properties first.")
        return
    outer_m, _inner_m = course_radii_m(spec, spec.active_courses()[0])
    diameter_var.set(f"{outer_m * 2.0 / 0.0254:.6g}")


def _draw(canvas: tk.Canvas, spec: FloorSpec, rows: list[list[FloorPlate]], highlight: int | None) -> None:
    canvas.delete("all")
    radius = spec.trim_radius_in()
    if radius <= 0:
        return
    size = _CANVAS
    margin = 16
    scale = (size / 2 - margin) / radius
    cx = size / 2
    cy = size / 2

    def point(x_in: float, z_in: float) -> tuple[float, float]:
        return cx + x_in * scale, cy - z_in * scale

    left, top = point(-radius, radius)
    right, bottom = point(radius, -radius)
    canvas.create_oval(left, top, right, bottom, outline="#2c3338", width=2)

    for index, row in enumerate(rows):
        if not row:
            continue
        color = row_color_hex(row[0].row)
        width = 3 if highlight == index else 1
        outline = "#8a5a12" if highlight == index else "#243038"
        for plate in row:
            coords: list[float] = []
            for x_in, z_in in plate.polygon_in:
                px, py = point(x_in, z_in)
                coords.extend((px, py))
            if len(coords) >= 6:
                canvas.create_polygon(*coords, fill=color, outline=outline, width=width)
