"""The Stretchout tab: the shell unrolled with the nozzles, FTCOs and the stair on it, and what clashes;
or the developed stringers laid flat with their splitter pieces, splice plates and holes.

It reads the other tabs as they stand (``shared["spec"]``, ``shared["nozzles"]``,
``shared["cleanouts"]`` and ``shared["stairway"]``) each time it is shown or refreshed, so it
needs no SolidWorks. The wheel zooms at the pointer, dragging pans, Fit shows it all, and the
pointer shows what it is over and, on the shell, how far that is from the nearest seam.
"""

from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from swauto.stretchout.checks import Clash, clearance, find_clashes
from swauto.stretchout.model import LAYERS, PLATES, Item, Stretchout, build_stretchout
from swauto.stretchout.stringers import SHEET_LAYERS, build_stringer_sheet
from swauto.stretchout.svg import CLASH, COURSE_FILLS, STYLE, THICK, to_svg
from swauto.tank.spec import TankSpec

SHELL_VIEW = "Shell"
STRINGER_VIEW = "Stringers (developed)"
_SEAM = "#5f574a"
_MARGIN = 36
_SHELL_HINT = (
    "Seen from outside, as the Shell Plate Elevation drawing: 0° at the right end, the orientation growing to "
    "the left. Hover over anything for what it is."
)
_SHEET_HINT = "Each flight's stringers flat, inner below and outer above, as they are burned. Hover for the holes."


def build_stretchout_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    shared = {} if shared is None else shared
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)

    bar = ttk.Frame(parent, padding=(8, 6, 8, 0))
    bar.grid(row=0, column=0, sticky="ew")
    shown = {layer: tk.BooleanVar(value=True) for layer in LAYERS + SHEET_LAYERS}
    view_var = tk.StringVar(value=SHELL_VIEW)
    buttons = ttk.Frame(bar)
    buttons.pack(side="left")
    toggles = ttk.Frame(bar)
    toggles.pack(side="left", padx=(12, 0))

    body = ttk.Panedwindow(parent, orient="horizontal")
    body.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
    canvas = tk.Canvas(body, background="#ffffff", highlightthickness=1, width=760, height=420)
    side = ttk.Frame(body, padding=(6, 0, 0, 0))
    body.add(canvas, weight=4)
    body.add(side, weight=1)
    ttk.Label(side, text="What lands where").pack(anchor="w")
    clash_list = tk.Listbox(side, height=14, width=46, activestyle="none")
    clash_list.pack(fill="both", expand=True)
    notes_var = tk.StringVar(value="")
    ttk.Label(side, textvariable=notes_var, wraplength=320, justify="left").pack(anchor="w", pady=(6, 0))
    info_var = tk.StringVar(value=_SHELL_HINT)
    ttk.Label(parent, textvariable=info_var, padding=(8, 0, 8, 6), wraplength=1000, justify="left").grid(
        row=2, column=0, sticky="ew"
    )

    state: dict = {"out": None, "clashes": [], "bad": set(), "ids": {}, "scale": 1.0, "ox": _MARGIN, "oy": 0.0}

    def show_toggles(layers) -> None:
        for child in toggles.winfo_children():
            child.destroy()
        for index, layer in enumerate(layers):
            ttk.Checkbutton(toggles, text=layer, variable=shown[layer], command=lambda: draw()).grid(
                row=index // 5, column=index % 5, sticky="w", padx=(0, 10)
            )

    def stairway():
        source = shared.get("stairway")
        if not callable(source):
            return None, "There is no Stairway tab."
        try:
            return source(), ""
        except ValueError as exc:
            return None, f"Stairway not drawn: {exc}"

    def refresh() -> None:
        sheet = view_var.get() == STRINGER_VIEW
        info_var.set(_SHEET_HINT if sheet else _SHELL_HINT)
        show_toggles(SHEET_LAYERS if sheet else LAYERS)
        stair, problem = stairway()
        notes = [problem] if problem else []
        out: Stretchout | None = None
        if sheet:
            if stair is not None:
                out = build_stringer_sheet(stair)
        else:
            spec = shared.get("spec")
            if not isinstance(spec, TankSpec) or not spec.active_courses():
                notes.append("Set the tank on Tank Properties first.")
            else:
                try:
                    out = build_stretchout(
                        spec, nozzles=list(shared.get("nozzles") or []),
                        cleanouts=list(shared.get("cleanouts") or []), stair=stair,
                        anchors=shared.get("anchors"),
                    )
                except ValueError as exc:
                    notes.append(f"Cannot lay out the shell: {exc}")
        clashes = find_clashes(out) if out is not None and out.wraps else []
        state["out"], state["clashes"] = out, clashes
        state["bad"] = {clash.label for clash in clashes}
        clash_list.delete(0, "end")
        for clash in clashes:
            clash_list.insert("end", clash.text)
        if out is not None and out.wraps and not clashes:
            clash_list.insert("end", "Nothing crosses a seam or sits on anything else.")
        notes_var.set("\n".join(notes + (list(out.notes) if out is not None else [])))
        if out is not None:
            status_var.set(f"Stretchout: {len(out.items)} items, {len(clashes)} to look at.")
        fit()

    def fit() -> None:
        out: Stretchout | None = state["out"]
        width, height = max(canvas.winfo_width(), 200), max(canvas.winfo_height(), 160)
        if out is None:
            draw()
            return
        low = min([0.0] + [item.box[1] for item in out.items])
        high = max([out.height_in] + [item.box[3] for item in out.items])
        scale = min((width - 2 * _MARGIN) / max(out.girth_in, 1.0), (height - 2 * _MARGIN) / max(high - low, 1.0))
        state.update(scale=scale, ox=_MARGIN, oy=height - _MARGIN + low * scale)
        draw()

    def to_px(x: float, y: float) -> tuple[float, float]:
        return state["ox"] + x * state["scale"], state["oy"] - y * state["scale"]

    def draw() -> None:
        canvas.delete("all")
        state["ids"] = {}
        out: Stretchout | None = state["out"]
        if out is None:
            return
        shifts = (-out.girth_in, 0.0, out.girth_in) if out.wraps else (0.0,)
        for shift in shifts:
            for layer in out.layers:
                if not shown[layer].get():
                    continue
                fill, outline = STYLE[layer]
                for item in out.items:
                    if item.layer != layer:
                        continue
                    if layer == PLATES:
                        _shape(item, shift, COURSE_FILLS[int(item.label.split()[0][1:]) % 2], outline, 1)
                        continue
                    bad = item.label in state["bad"]
                    _shape(item, shift, "" if fill == "none" else fill, CLASH if bad else outline,
                           3 if bad else (2 if layer in THICK else 1))
                if layer == PLATES:
                    for seam in out.seams:
                        canvas.create_line(*to_px(seam.x0 + shift, seam.y0), *to_px(seam.x1 + shift, seam.y1),
                                           fill=_SEAM, width=1)
        for x, y, text in out.labels:
            canvas.create_text(*to_px(x, y), text=text, anchor="sw", font=("TkDefaultFont", 8), fill="#333333")
        if out.wraps:
            _axes(out)

    def _shape(item: Item, shift: float, fill: str, outline: str, width: int) -> None:
        x0, y0, x1, y1 = item.box
        px0, py1 = to_px(x0 + shift, y0)
        px1, py0 = to_px(x1 + shift, y1)
        # Skip what is off the canvas; before it is mapped, take the size Fit works to.
        if px1 < 0 or px0 > max(canvas.winfo_width(), 200) or py1 < 0 or py0 > max(canvas.winfo_height(), 160):
            return
        points = [v for x, y in item.outline for v in to_px(x + shift, y)]
        shape = canvas.create_polygon(*points, fill=fill, outline=outline, width=width)
        state["ids"][shape] = item

    def _axes(out: Stretchout) -> None:
        span = out.girth_in * state["scale"]
        step = 5 if span > 2400 else (15 if span > 900 else 30)
        top = to_px(0.0, out.height_in)[1] - 4
        for degrees in range(0, 361, step):
            x = out.girth_in * (1.0 - degrees / 360.0)
            for shift in (-out.girth_in, 0.0, out.girth_in):
                px = to_px(x + shift, 0.0)[0]
                if -40 < px < canvas.winfo_width() + 40:
                    canvas.create_line(px, top, px, top - 6, fill="#333333")
                    canvas.create_text(px, top - 8, text=f"{degrees % 360}°", anchor="s", font=("TkDefaultFont", 8))
        spec = shared.get("spec")
        level = 0.0
        for course in [0.0] + ([c.height_in for c in spec.active_courses()] if isinstance(spec, TankSpec) else []):
            level += course
            canvas.create_text(4, to_px(0.0, level)[1], text=f"{level:g}", anchor="w", font=("TkDefaultFont", 8),
                               fill="#555555")
        canvas.create_text(4, 4, text="EL (in) / orientation", anchor="nw", font=("TkDefaultFont", 8), fill="#555555")

    def at_pointer(event) -> Item | None:
        found = canvas.find_overlapping(event.x - 2, event.y - 2, event.x + 2, event.y + 2)
        items = [state["ids"][shape] for shape in found if shape in state["ids"]]
        landing = [item for item in items if item.layer != PLATES]
        return landing[-1] if landing else (items[-1] if items else None)

    def on_motion(event) -> None:
        out = state["out"]
        if out is None:
            return
        x = (event.x - state["ox"]) / state["scale"]
        y = (state["oy"] - event.y) / state["scale"]
        if out.wraps:
            where = f"{out.degrees_of_x(x % out.girth_in):.2f}°, EL {y:.2f} in"
        else:
            where = f"x {x:.2f}, y {y:.2f} in"
        item = at_pointer(event)
        if item is None:
            info_var.set(where)
            return
        text = item.info or item.label
        if item.lands and out.wraps:
            near = clearance(item, out)
            if near is not None:
                text += f" — {near[0]:.2f} in to {near[1]}"
        info_var.set(f"{where}: {text}")

    def on_wheel(event) -> None:
        factor = 1.25 if event.delta > 0 else 0.8
        x = (event.x - state["ox"]) / state["scale"]
        y = (state["oy"] - event.y) / state["scale"]
        state["scale"] *= factor
        state["ox"] = event.x - x * state["scale"]
        state["oy"] = event.y + y * state["scale"]
        draw()

    def on_press(event) -> None:
        state["drag"] = (event.x, event.y)

    def on_drag(event) -> None:
        last = state.get("drag")
        if last is None:
            return
        state["ox"] += event.x - last[0]
        state["oy"] += event.y - last[1]
        state["drag"] = (event.x, event.y)
        draw()

    def on_pick(_event=None) -> None:
        picked = clash_list.curselection()
        if not picked or picked[0] >= len(state["clashes"]):
            return
        clash: Clash = state["clashes"][picked[0]]
        scale = min(canvas.winfo_width(), canvas.winfo_height()) / 120.0  # about 10 ft across
        state.update(scale=scale, ox=canvas.winfo_width() / 2 - clash.x * scale,
                     oy=canvas.winfo_height() / 2 + clash.y * scale)
        draw()

    def save_picture() -> None:
        out: Stretchout | None = state["out"]
        if out is None:
            messagebox.showinfo("Stretchout", "There is nothing to save yet: set the tank or the stair, then Refresh.")
            return
        project = shared.get("project")
        folder = str(getattr(project, "folder", "") or "")
        name = str(getattr(project, "name", "") or "Tank")
        what = "stringers" if not out.wraps else "stretchout"
        path = filedialog.asksaveasfilename(
            title="Save the picture", defaultextension=".svg", initialdir=folder or None,
            initialfile=f"{name} {what}.svg", filetypes=[("SVG picture (opens in a browser)", "*.svg")],
        )
        if not path:
            return
        title = (f"{name}: shell stretchout seen from outside" if out.wraps else f"{name}: developed stringers")
        layers = [layer for layer in out.layers if shown[layer].get()]
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(to_svg(out, state["clashes"], shown=layers,
                                    title=f"{title}, {datetime.date.today():%Y-%m-%d}"))
        except OSError as exc:
            messagebox.showerror("Stretchout", f"Could not save {path}:\n{exc}")
            return
        status_var.set(f"Picture saved: {path}")

    ttk.Button(buttons, text="Refresh", command=refresh).pack(side="left")
    ttk.Button(buttons, text="Fit", command=fit).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Save picture…", command=save_picture).pack(side="left", padx=(6, 0))
    ttk.Label(buttons, text="View").pack(side="left", padx=(12, 0))
    view_box = ttk.Combobox(buttons, textvariable=view_var, values=(SHELL_VIEW, STRINGER_VIEW), width=20,
                            state="readonly")
    view_box.pack(side="left", padx=(4, 0))
    view_box.bind("<<ComboboxSelected>>", lambda _event: refresh())
    show_toggles(LAYERS)
    canvas.bind("<Motion>", on_motion)
    canvas.bind("<MouseWheel>", on_wheel)
    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<Configure>", lambda _event: fit() if state["out"] is not None else None)
    clash_list.bind("<<ListboxSelect>>", on_pick)
    book = parent.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", lambda _event: refresh() if book.select() == str(parent) else None,
                  add="+")
    shared["refresh_stretchout"] = refresh
