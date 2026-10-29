"""Anchor Chairs tab: the lisp's chair inputs, the chair drawn in section, and Build on shell. The chairs also
go on the Stretchout tab (``shared["anchors"]``)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from swauto.errors import SolidWorksError
from swauto.tank.anchors import AnchorChairs, chairs, leg_profile, warnings
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import TankSpec

_NOTE = "#666666"
_BAD = "#c62828"
_CANVAS = 300
# key, label, the lisp's default. The lisp's defaults put the hole off the top plate: they do not build.
_FIELDS = (
    ("count", "Count", "24"),
    ("rotation_deg", "Global rotation, deg", "0"),
    ("offsets", "Offsets (1:15,4:-10)", ""),
    ("top_plate_width_in", "Top plate width, along the shell", "12.5"),
    ("top_plate_depth_in", "Top plate radial depth", "4.0"),
    ("top_plate_thk_in", "Top plate thk", "0.25"),
    ("height_in", "Anchor height (floor to top of the top plate)", "20.0"),
    ("leg_thk_in", "Leg width (thickness)", "0.75"),
    ("leg_gap_in", "Leg gap (clear)", "10.0"),
    ("washer_width_in", "Washer width, along the shell", "12.5"),
    ("washer_thk_in", "Washer thk", "1.75"),
    ("washer_depth_in", "Washer radial depth", "4.0"),
    ("hole_dia_in", "Hole dia", "1.0"),
    ("hole_from_shell_in", "Hole from shell", "8.0"),
    ("weld_leg_in", "Shell-to-bottom weld leg (the legs' clip)", "0.25"),
    ("chime_in", "Chime (bottom plate past the shell)", "2.5"),
)


def read_chairs(values: dict[str, str]) -> AnchorChairs:
    def number(key: str, label: str) -> float:
        text = str(values.get(key, "")).strip()
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"{label} must be a number.") from None

    labels = {key: label for key, label, _default in _FIELDS}
    count = number("count", "Count")
    if count != int(count):
        raise ValueError("Count must be a whole number.")
    sizes = {key: number(key, labels[key]) for key, _label, _default in _FIELDS if key not in ("count", "offsets")}
    return AnchorChairs(count=int(count), offsets=str(values.get("offsets", "")), **sizes)


def build_anchor_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    if shared is None:
        shared = {}
    frame = ttk.Frame(parent, padding=10)
    frame.grid(row=0, column=0, sticky="nsew")
    ttk.Label(frame, text="Anchor chairs", font=("", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="The lisp's inputs and defaults. Its defaults put the bolt hole off the top plate, so "
              "type the chair's real sizes.", foreground=_NOTE, wraplength=700, justify="left").grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
    values: dict[str, tk.StringVar] = {}
    for row, (key, label, default) in enumerate(_FIELDS, start=2):
        values[key] = tk.StringVar(value=default)
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(frame, textvariable=values[key], width=16 if key == "offsets" else 10).grid(
            row=row, column=1, sticky="w")
    last = len(_FIELDS) + 2
    summary_var = tk.StringVar()
    summary = ttk.Label(frame, textvariable=summary_var, wraplength=700, justify="left")
    summary.grid(row=last, column=0, columnspan=3, sticky="w", pady=(8, 4))
    build_btn = ttk.Button(frame, text="Build on shell")
    build_btn.grid(row=last + 1, column=0, sticky="w")
    canvas = tk.Canvas(frame, width=_CANVAS, height=_CANVAS, background="#f4f1ea", highlightthickness=1)
    canvas.grid(row=2, column=2, rowspan=len(_FIELDS), sticky="ne", padx=(16, 0))
    state: dict[str, object] = {"busy": False}

    def shell():
        tank = shared.get("spec")
        if not isinstance(tank, TankSpec) or not tank.active_courses():
            return None, None
        first = tank.active_courses()[0]
        return course_radii_m(tank, first)[0] / 0.0254, first.height_in

    def refresh(*_args) -> None:
        try:
            spec = read_chairs({key: var.get() for key, var in values.items()})
            spots = chairs(spec)
        except ValueError as exc:
            shared["anchors"] = None
            summary_var.set(str(exc))
            summary.configure(foreground=_BAD)
            draw_chair(canvas, None)
            return
        shared["anchors"] = spec
        radius, course_one = shell()
        text = f"{len(spots)} chairs, {360.0 / spec.count:g}° apart, chair 1 at {spots[0].angle_deg:g}°."
        notes = warnings(spec, radius, course_one) if radius is not None else ["Set the tank on Tank Properties."]
        summary_var.set(text + ("\n" + "\n".join(notes) if notes else ""))
        summary.configure(foreground=_BAD if notes and radius is not None else "")
        draw_chair(canvas, spec)

    def build() -> None:
        if state["busy"]:
            return
        refresh()
        spec = shared.get("anchors")
        if not isinstance(spec, AnchorChairs):
            messagebox.showerror("Anchor chairs", summary_var.get())
            return
        try:
            from swauto.session import connect
            from swauto.tank.anchors_sw import add_anchor_chairs
            from swauto.tank.open_shell import find_shell

            live = find_shell(shared, connect().app)
        except (ValueError, SolidWorksError) as exc:
            messagebox.showerror("Anchor chairs", str(exc))
            return
        radius, _course = shell()
        state["busy"] = True
        build_btn.configure(state="disabled")
        try:
            status_var.set(add_anchor_chairs(live.model, spec, radius, progress=lambda text: (
                status_var.set(text), frame.update_idletasks())))
        except (SolidWorksError, ValueError) as exc:
            status_var.set(str(exc))
            messagebox.showerror("Anchor chairs", str(exc))
        finally:
            state["busy"] = False
            build_btn.configure(state="normal")

    build_btn.configure(command=build)
    for var in values.values():
        var.trace_add("write", refresh)
    shared["refresh_anchors"] = refresh  # also keeps the tab's variables alive
    refresh()
    book = parent.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", lambda _event: refresh(), add="+")


def draw_chair(canvas: tk.Canvas, spec: AnchorChairs | None) -> None:
    """One chair in section, the shell on the left: legs, top plate, washer and the bolt's centerline."""
    canvas.delete("all")
    if spec is None:
        return
    reach = max(spec.top_plate_depth_in, spec.hole_from_shell_in + spec.washer_depth_in / 2.0) + 4.0
    tall = spec.height_in + spec.washer_thk_in + 4.0
    scale = (_CANVAS - 30.0) / max(reach, tall)
    x0, y0 = 20.0, _CANVAS - 12.0

    def at(r: float, y: float) -> tuple[float, float]:
        return (x0 + r * scale, y0 - y * scale)

    canvas.create_line(*at(-1.0, 0.0), *at(reach, 0.0), fill="#8a8a8a")  # the floor's top
    canvas.create_line(*at(0.0, 0.0), *at(0.0, tall), fill="#555555", width=2)  # the shell's outside
    canvas.create_polygon(*[c for p in leg_profile(spec) for c in at(*p)], fill="#ddd3c4", outline="#5b4636")
    legs, top = spec.leg_height_in, spec.height_in
    canvas.create_rectangle(*at(0.0, legs), *at(spec.top_plate_depth_in, top), fill="#c9b79c", outline="#5b4636")
    e, half = spec.hole_from_shell_in, spec.washer_depth_in / 2.0
    canvas.create_rectangle(*at(e - half, top), *at(e + half, top + spec.washer_thk_in), fill="#b8a383",
                            outline="#5b4636")
    canvas.create_line(*at(e, legs - 3.0), *at(e, top + spec.washer_thk_in + 3.0), fill="#c62828", dash=(6, 3))
    canvas.create_text(_CANVAS - 6, 6, anchor="ne", fill=_NOTE, font=("", 8),
                       text=f"hole {spec.hole_dia_in:g} at {e:g} out; {spec.count} chairs")
