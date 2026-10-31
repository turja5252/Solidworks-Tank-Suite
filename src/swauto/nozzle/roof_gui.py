"""Roof Nozzles tab: a grid of nozzles for the cone roof on the Roof tab, typed straight into the cells, with
the roof in plan under it.

It works like the Shell Nozzles grid. A nozzle is placed by its degree, its radial distance from the tank
center and an offset, as in the lisp's ROOFNOZZLES; its flange face by its height above the roof bearing
line, or by a direct OSP. A blank ISP is the lisp's AUTO.
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

from swauto.errors import SolidWorksError
from swauto.nozzle.gui import (
    _BAD,
    _CHECK_MS,
    _INSIDE,
    _ITEM_PARTS,
    _ITEMS,
    _NOTE,
    _OK,
    _REPADS,
    _SCHEDULES,
    _STYLES,
    MORE_ROWS,
    START_ROWS,
    RowCheck,
    _Column,
    _inches,
    _optional_inches,
)
from swauto.nozzle.pipe import nps_sizes
from swauto.nozzle.repad import default_repad_size
from swauto.nozzle.roof_place import RoofPlacement, pad_outline, place_on_roof
from swauto.nozzle.roof_spec import DIRECT, HEIGHT, PROJECTION_LABELS, RoofNozzle, read_isp
from swauto.parts import quiet
from swauto.tank.framing import Layout, rafter_outline
from swauto.tank.open_roof import find_roof_part
from swauto.tank.roof import RoofSpec, course_break_plan_radii

_MODES = (PROJECTION_LABELS[HEIGHT], PROJECTION_LABELS[DIRECT])
_COLUMNS = (
    _Column("mark", "Mark", 56),
    _Column("service", "Service", 110),
    _Column("item", "Item", 150, "combo", _ITEMS, _ITEMS[0]),
    _Column("size", "Size, in", 62, "combo", nps_sizes()),
    _Column("schedule", "Sch", 54, "combo", _SCHEDULES, "STD"),  # the lisp's roof default
    _Column("degree", "Deg", 54),
    _Column("radial", "Radial, in", 66),
    _Column("offset", "Offset, in", 64),
    _Column("mode", "Projection", 140, "combo", _MODES, _MODES[0]),
    _Column("value", "Value, in", 60),
    _Column("isp", "ISP, in", 54),
    _Column("inside_flange", "ISP flange", 80, "combo", _INSIDE, "None"),
    _Column("repad", "Repad", 78, "combo", _REPADS, "None"),
    _Column("pad_od", "Pad OD", 56),
    _Column("pad_id", "Pad ID", 56),
    _Column("pad_thk", "Pad thk", 56),
    _Column("style", "Style", 92, "combo", _STYLES, "Circular"),
    _Column("blind", "Blind", 44, "check"),
    _Column("gasket", "Gasket", 50, "check"),
    _Column("gasket_material", "Gasket material", 140),
    _Column("gasket_thk", "Gskt thk", 58),
)
_NUMBER_PX = 30
_DOT_PX = 16
_CHECK_PX = 330
_CLEAR_PX = 30
_PLAN_PX = 340
# Typed cells. A row with all of these blank is skipped.
_TYPED = tuple(column.key for column in _COLUMNS if column.kind == "entry") + ("size",)


def blank_row() -> dict[str, object]:
    """An empty row. Its dropdowns stay blank until the row is used; then they show their defaults."""
    return {column.key: (False if column.kind == "check" else "") for column in _COLUMNS}


def _with_defaults(values: dict[str, object]) -> dict[str, object]:
    filled = dict(values)
    for column in _COLUMNS:
        if column.kind == "combo" and column.default and not str(filled.get(column.key, "")).strip():
            filled[column.key] = column.default
    return filled


@dataclass(frozen=True)
class RoofRowCheck(RowCheck):
    """A row read, with where it lands on the roof when it is good and there is a roof."""

    placed: RoofPlacement | None = None


def check_rows(rows: list[dict[str, object]], roof) -> list[RoofRowCheck]:
    """Read every grid row. Blank rows come back blank; a mark on two rows is wrong on both."""
    cone = roof if isinstance(roof, RoofSpec) else None
    checks: list[RoofRowCheck] = []
    for values in rows:
        if all(not str(values.get(key, "")).strip() for key in _TYPED):
            checks.append(RoofRowCheck(None, "", True))
            continue
        try:
            nozzle = nozzle_from_row(values)
            if cone is None:
                checks.append(RoofRowCheck(nozzle, "Set the roof on the Roof tab to place it.", True))
                continue
            placed = place_on_roof(nozzle, cone)
        except ValueError as exc:
            checks.append(RoofRowCheck(None, str(exc), False))
            continue
        checks.append(RoofRowCheck(nozzle, row_summary(placed), True, placed))
    rows_by_mark: dict[str, list[int]] = {}
    for index, check in enumerate(checks):
        if check.nozzle is not None:
            rows_by_mark.setdefault(check.nozzle.mark, []).append(index)
    for mark, indexes in rows_by_mark.items():
        if len(indexes) > 1:
            others = ", ".join(str(i + 1) for i in indexes)
            for index in indexes:
                checks[index] = RoofRowCheck(None, f"{mark} is on rows {others}. Marks must differ.", False)
    return checks


def nozzle_from_row(values: dict[str, object]) -> RoofNozzle:
    """A roof nozzle from one grid row. Lengths are inches, the degree is degrees."""
    values = _with_defaults(values)
    mark = str(values.get("mark", "")).strip()
    if not mark:
        raise ValueError("Enter a mark, like R1.")
    if not str(values.get("size", "")).strip():
        raise ValueError("Choose a size.")
    parts = _ITEM_PARTS.get(str(values["item"]))
    if parts is None:
        raise ValueError("Choose a weld neck or a slip-on, Class 150 or 300.")
    rating, kind = parts
    gasket = bool(values["gasket"])
    projection = DIRECT if str(values["mode"]) == PROJECTION_LABELS[DIRECT] else HEIGHT
    return RoofNozzle(
        mark=mark,
        nps=str(values["size"]),
        rating=rating,
        kind=kind,
        schedule=str(values["schedule"]),
        degree=_inches(str(values["degree"]), "degree", blank=0.0),
        radial_in=_inches(str(values["radial"]), "radial distance"),
        offset_in=_inches(str(values["offset"]), "offset", blank=0.0),
        projection=projection,
        projection_in=_inches(str(values["value"]), "height" if projection == HEIGHT else "OSP"),
        isp_in=read_isp(values["isp"]),
        inside_flange=str(values["inside_flange"]),
        repad_mode=str(values["repad"]).lower(),
        repad_outer_in=_inches(str(values["pad_od"]), "repad outside diameter", blank=0.0),
        repad_inner_in=_inches(str(values["pad_id"]), "repad inside diameter", blank=0.0),
        repad_thickness_in=_optional_inches(str(values["pad_thk"]), "Repad thickness"),
        repad_style="tombstone" if str(values["style"]) == "Tombstone" else "circular",
        description=str(values["service"]),
        blind=bool(values["blind"]),
        gasket=gasket,
        gasket_material=str(values["gasket_material"]) if gasket else "",
        gasket_thickness_in=_optional_inches(str(values["gasket_thk"]), "gasket thickness") if gasket else None,
    )


def row_values(nozzle: RoofNozzle) -> dict[str, object]:
    """A saved roof nozzle as grid cells: what reading the row gives back. Default repads fill themselves in."""

    def num(value) -> str:
        return "" if value is None else f"{value:g}"

    custom = nozzle.repad_mode == "custom"
    return {
        "mark": nozzle.mark,
        "service": nozzle.description,
        "item": f"Class {nozzle.rating} {'weld neck' if nozzle.kind == 'wn' else 'slip-on'}",
        "size": nozzle.nps,
        "schedule": nozzle.schedule,
        "degree": num(nozzle.degree),
        "radial": num(nozzle.radial_in),
        "offset": num(nozzle.offset_in),
        "mode": PROJECTION_LABELS[nozzle.projection],
        "value": num(nozzle.projection_in),
        "isp": "" if nozzle.isp_in is None else num(nozzle.isp_in),
        "inside_flange": {"wn": "Weld neck", "so": "Slip-on"}.get(nozzle.inside_flange, "None"),
        "repad": nozzle.repad_mode.capitalize(),
        "pad_od": num(nozzle.repad_outer_in) if custom else "",
        "pad_id": num(nozzle.repad_inner_in) if custom else "",
        "pad_thk": num(nozzle.repad_thickness_in) if nozzle.repad_mode != "none" else "",
        "style": "Tombstone" if nozzle.repad_style == "tombstone" else "Circular",
        "blind": nozzle.blind,
        "gasket": nozzle.gasket,
        "gasket_material": nozzle.gasket_material,
        "gasket_thk": num(nozzle.gasket_thickness_in) if nozzle.gasket else "",
    }


def row_summary(placed: RoofPlacement) -> str:
    nozzle = placed.nozzle
    shape = "WN" if nozzle.kind == "wn" else "SO"
    isp = "ISP AUTO" if placed.auto_isp else f"ISP {placed.isp_in:g}"
    pad = placed.repad
    pad_text = "" if pad is None else f", pad {pad.outer_diameter_in:g} x {pad.thickness_in:g}"
    inside = ""
    if nozzle.inside_flange != "none":
        inside = f", inside {'WN' if nozzle.inside_flange == 'wn' else 'SO'} flange"
    return (
        f"OK  {nozzle.nps} in {nozzle.rating}# {shape} at {placed.angle_deg:.2f}°, R {placed.radius_in:.2f}: "
        f"B {placed.height_in:.3f}, OSP {placed.outside_projection_in:.3f}, {isp}{pad_text}{inside}"
    )


def roof_summary(roof) -> str:
    """The roof the nozzles go on, as the Roof tab has it."""
    if not isinstance(roof, RoofSpec):
        return "No roof yet: set one on the Roof tab."
    try:
        roof.validate()
    except ValueError as exc:
        return f"The Roof tab's roof is not ready: {exc}"
    ring = " on the compression ring" if roof.ring_active() else " on the shell"
    return (
        f"Cone roof, {roof.slope_in_per_ft:g} in/ft, {roof.thickness_in:g} in plate. Lands{ring} at a radius of "
        f"{roof.landing_radius_in():.3f} in, {roof.landing_height_in():.3f} in up (the bearing line); its peak is "
        f"{roof.rise_in():.3f} in higher."
    )


class _Row:
    """The cells of one grid row."""

    def __init__(self, body: ttk.Frame, number: int, on_change, on_clear) -> None:
        self.number = number
        self.vars: dict[str, tk.Variable] = {}
        self.widgets: dict[str, tk.Widget] = {}
        grid_row = number - 1
        ttk.Label(body, text=str(number), anchor="e", foreground=_NOTE).grid(
            row=grid_row, column=0, sticky="ew", padx=(0, 2)
        )
        self.dot = ttk.Label(body, text="", anchor="center")
        self.dot.grid(row=grid_row, column=1, sticky="ew")
        for col, column in enumerate(_COLUMNS, start=2):
            if column.kind == "check":
                var: tk.Variable = tk.BooleanVar(value=False)
                widget = ttk.Checkbutton(body, variable=var)
                widget.grid(row=grid_row, column=col)
            elif column.kind == "combo":
                var = tk.StringVar()
                widget = ttk.Combobox(body, textvariable=var, values=column.choices, width=1, state="readonly")
                widget.grid(row=grid_row, column=col, sticky="ew", padx=1, pady=1)
            else:
                var = tk.StringVar()
                widget = ttk.Entry(body, textvariable=var, width=1)
                widget.grid(row=grid_row, column=col, sticky="ew", padx=1, pady=1)
            var.trace_add("write", lambda *_args: on_change())
            self.vars[column.key] = var
            self.widgets[column.key] = widget
        self.check = ttk.Label(body, anchor="w")
        self.check.grid(row=grid_row, column=len(_COLUMNS) + 2, sticky="ew", padx=(6, 0))
        self.clear_button = ttk.Button(body, text="✕", width=2, command=lambda: on_clear(self))
        self.clear_button.grid(row=grid_row, column=len(_COLUMNS) + 3, padx=(2, 0))
        self.message = ""

    def values(self) -> dict[str, object]:
        return {key: var.get() for key, var in self.vars.items()}

    def clear(self) -> None:
        for key, value in blank_row().items():
            self.vars[key].set(value)

    def show_defaults(self, used: bool) -> None:
        for column in _COLUMNS:
            if column.kind == "combo" and column.default:
                var = self.vars[column.key]
                if used and not var.get():
                    var.set(column.default)
                elif not used and var.get() == column.default:
                    var.set("")

    def sync(self) -> None:
        """Default fills and locks the standard pad for the size; Custom is typed; None greys the pad out."""
        mode = self.vars["repad"].get() or "None"
        if mode == "Default":
            standard = default_repad_size(self.vars["size"].get()) if self.vars["size"].get() else None
            texts = ("", "") if standard is None else tuple(f"{value:g}" for value in standard[:2])
            for key, text in zip(("pad_od", "pad_id"), texts, strict=True):
                if self.vars[key].get() != text:
                    self.vars[key].set(text)
        for key in ("pad_od", "pad_id"):
            self.widgets[key].state(["!disabled"] if mode == "Custom" else ["disabled"])
        self.widgets["pad_thk"].state(["!disabled"] if mode != "None" else ["disabled"])
        self.widgets["style"].configure(state="readonly" if mode != "None" else "disabled")
        gasket = bool(self.vars["gasket"].get())
        for key in ("gasket_material", "gasket_thk"):
            self.widgets[key].state(["!disabled"] if gasket else ["disabled"])

    def show(self, check: RowCheck) -> None:
        self.message = check.message
        if not check.ok:
            color = _BAD
        elif check.message.startswith("OK"):
            color = _OK
        else:
            color = _NOTE
        text = check.message if len(check.message) <= 54 else check.message[:52] + "…"
        self.check.configure(text=text, foreground=color)
        self.dot.configure(text="" if check.blank else "●", foreground=color)


def build_roof_nozzle_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    """Fill the Roof Nozzles tab. ``shared["roof"]`` is the Roof tab's cone."""
    if shared is None:
        shared = {}
    nozzles: list[RoofNozzle] = []
    shared["roof_nozzles"] = nozzles

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    frame = ttk.Frame(parent, padding=8)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(3, weight=1)

    ttk.Label(frame, text="Roof nozzles", font=("", 11, "bold")).grid(row=0, column=0, sticky="w")
    roof_var = tk.StringVar()
    ttk.Label(frame, textvariable=roof_var, justify="left", wraplength=900).grid(
        row=1, column=0, sticky="w", pady=(2, 6)
    )
    bar = ttk.Frame(frame)
    bar.grid(row=2, column=0, sticky="ew", pady=(0, 4))
    bar.columnconfigure(3, weight=1)
    count_var = tk.StringVar()
    ttk.Label(
        bar,
        text="Deg and offset as for shell nozzles; Radial from the tank center.  Height: flange face over the "
        "bearing line.  ISP: down from the roof underside; blank is AUTO.",
        foreground=_NOTE,
    ).grid(row=0, column=3, sticky="e")

    table = ttk.Frame(frame)
    table.grid(row=3, column=0, sticky="nsew")
    table.columnconfigure(0, weight=1)
    table.rowconfigure(1, weight=1)
    head_canvas = tk.Canvas(table, highlightthickness=0, height=24)
    body_canvas = tk.Canvas(table, highlightthickness=0, height=260)
    head_canvas.grid(row=0, column=0, sticky="ew")
    body_canvas.grid(row=1, column=0, sticky="nsew")

    def scroll_x(*args) -> None:
        head_canvas.xview(*args)
        body_canvas.xview(*args)

    y_bar = ttk.Scrollbar(table, orient="vertical", command=body_canvas.yview)
    x_bar = ttk.Scrollbar(table, orient="horizontal", command=scroll_x)
    y_bar.grid(row=1, column=1, sticky="ns")
    x_bar.grid(row=2, column=0, sticky="ew")
    body_canvas.configure(yscrollcommand=y_bar.set, xscrollcommand=x_bar.set)
    head_canvas.configure(xscrollcommand=x_bar.set)
    head = ttk.Frame(head_canvas)
    body = ttk.Frame(body_canvas)
    head_canvas.create_window((0, 0), window=head, anchor="nw")
    body_canvas.create_window((0, 0), window=body, anchor="nw")
    widths = (_NUMBER_PX, _DOT_PX, *(column.pixels for column in _COLUMNS), _CHECK_PX, _CLEAR_PX)
    for grid in (head, body):
        for col, pixels in enumerate(widths):
            grid.columnconfigure(col, minsize=pixels)
    for col, text in enumerate(("#", "", *(column.heading for column in _COLUMNS), "Check", "")):
        ttk.Label(head, text=text, font=("", 9, "bold"), anchor="w").grid(row=0, column=col, sticky="ew", padx=1)

    def fit_scroll(_event=None) -> None:
        body.update_idletasks()
        width = max(body.winfo_reqwidth(), head.winfo_reqwidth())
        body_canvas.configure(scrollregion=(0, 0, width, body.winfo_reqheight()))
        head_canvas.configure(scrollregion=(0, 0, width, head.winfo_reqheight()), height=head.winfo_reqheight())

    body.bind("<Configure>", fit_scroll)

    def wheel(event) -> str:
        body_canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")
        return "break"

    body_canvas.bind("<Enter>", lambda _e: body_canvas.bind_all("<MouseWheel>", wheel))
    body_canvas.bind("<Leave>", lambda _e: body_canvas.unbind_all("<MouseWheel>"))

    def see(widget) -> None:
        body.update_idletasks()
        total_h = max(body.winfo_reqheight(), 1)
        total_w = max(body.winfo_reqwidth(), 1)
        top, left = body_canvas.canvasy(0), body_canvas.canvasx(0)
        y, h = widget.winfo_y(), widget.winfo_height()
        x, w = widget.winfo_x(), widget.winfo_width()
        view_h, view_w = body_canvas.winfo_height(), body_canvas.winfo_width()
        if y < top:
            body_canvas.yview_moveto(y / total_h)
        elif y + h > top + view_h:
            body_canvas.yview_moveto((y + h - view_h) / total_h)
        if x < left:
            scroll_x("moveto", x / total_w)
        elif x + w > left + view_w:
            scroll_x("moveto", (x + w - view_w) / total_w)

    plan_box = ttk.Frame(frame)
    plan_box.grid(row=4, column=0, sticky="w", pady=(8, 0))
    ttk.Label(plan_box, text="Plan from above: 0° at 12 o'clock, growing clockwise").grid(
        row=0, column=0, sticky="w"
    )
    plan = tk.Canvas(plan_box, width=_PLAN_PX, height=_PLAN_PX, background="#f4f1ea", highlightthickness=1)
    plan.grid(row=1, column=0, sticky="w")

    rows: list[_Row] = []
    pending = {"after": None}
    shown: dict[str, list] = {"placed": []}

    def check_all() -> list[RoofRowCheck]:
        pending["after"] = None
        for row in rows:
            values = row.values()
            row.show_defaults(any(str(values[key]).strip() for key in _TYPED))
            row.sync()
        checks = check_rows([row.values() for row in rows], shared.get("roof"))
        for row, check in zip(rows, checks, strict=True):
            row.show(check)
        nozzles[:] = [check.nozzle for check in checks if check.nozzle is not None]
        shown["placed"] = [check.placed for check in checks if check.placed is not None]
        bad = sum(1 for check in checks if not check.ok)
        count_var.set(f"{len(nozzles)} ready" + (f", {bad} to fix" if bad else ""))
        draw_plan(plan, shared.get("roof"), shown["placed"], shared.get("framing"))
        return checks

    def changed() -> None:
        if pending["after"] is not None:
            frame.after_cancel(pending["after"])
        pending["after"] = frame.after(_CHECK_MS, check_all)

    def clear_row(row: _Row) -> None:
        row.clear()
        status_var.set(f"Cleared roof nozzle row {row.number}.")

    def move(row: _Row, key: str, step: int) -> str:
        target = row.number - 1 + step
        if 0 <= target < len(rows):
            rows[target].widgets[key].focus_set()
        return "break"

    def add_rows(count: int) -> None:
        for _ in range(count):
            row = _Row(body, len(rows) + 1, changed, clear_row)
            rows.append(row)
            for column in _COLUMNS:
                widget = row.widgets[column.key]
                widget.bind("<FocusIn>", lambda _e, r=row, w=widget: (see(w), status_var.set(r.message or "")), add="+")
                if column.kind == "entry":
                    widget.bind("<Return>", lambda _e, r=row, k=column.key: move(r, k, 1))
                    widget.bind("<Down>", lambda _e, r=row, k=column.key: move(r, k, 1))
                    widget.bind("<Up>", lambda _e, r=row, k=column.key: move(r, k, -1))
                elif column.kind == "combo":
                    widget.bind("<MouseWheel>", wheel)
                    widget.bind("<Return>", lambda _e, r=row, k=column.key: move(r, k, 1))
        fit_scroll()
        check_all()

    def add_more() -> None:
        first = len(rows)
        add_rows(MORE_ROWS)
        rows[first].widgets["mark"].focus_set()
        status_var.set(f"Added roof nozzle rows {first + 1} to {len(rows)}.")

    busy = {"on": False}

    def build_on_roof() -> None:
        if busy["on"]:
            return
        checks = check_all()
        wrong = [(index, check) for index, check in enumerate(checks) if not check.ok]
        if wrong:
            lines = [f"Row {index + 1}: {check.message}" for index, check in wrong[:8]]
            if len(wrong) > 8:
                lines.append(f"…and {len(wrong) - 8} more.")
            messagebox.showerror("Roof nozzle", "Fix these rows first:\n\n" + "\n".join(lines))
            rows[wrong[0][0]].widgets["mark"].focus_set()
            return
        roof = shared.get("roof")
        if not isinstance(roof, RoofSpec):
            messagebox.showerror("Roof nozzle", "Set the roof on the Roof tab first.")
            return
        if not nozzles:
            messagebox.showerror("Roof nozzle", "Fill in at least one row first.")
            return
        try:
            from swauto.nozzle.roof_sw import add_roof_nozzles
            from swauto.session import connect

            app = connect().app
            model = find_roof_part(shared, app)
        except (ValueError, SolidWorksError) as exc:
            messagebox.showerror("Roof nozzle", str(exc))
            return
        busy["on"] = True
        status_var.set(f"Building {len(nozzles)} roof nozzle(s)...")
        frame.update_idletasks()

        def progress(text: str) -> None:
            status_var.set(text)
            frame.update_idletasks()

        try:
            with quiet(app, model):  # graphics and the feature tree off while it builds: many times faster
                status_var.set(add_roof_nozzles(model, roof, list(nozzles), progress=progress))
        except (SolidWorksError, ValueError) as exc:
            status_var.set(str(exc))
            messagebox.showerror("Roof nozzle", str(exc))
        finally:
            busy["on"] = False

    ttk.Button(bar, text="Build on roof", command=build_on_roof).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(bar, text=f"Add {MORE_ROWS} rows", command=add_more).grid(row=0, column=1, padx=(0, 10))
    ttk.Label(bar, textvariable=count_var).grid(row=0, column=2, sticky="w")

    def load_roof_nozzles(saved) -> None:
        """Fill the grid from a saved project; rows past the saved nozzles are cleared."""
        if len(saved) > len(rows):
            add_rows(len(saved) - len(rows))
        for row in rows:
            row.clear()
        for row, nozzle in zip(rows, saved):
            for key, value in row_values(nozzle).items():
                row.vars[key].set(value)
        check_all()

    shared["load_roof_nozzles"] = load_roof_nozzles

    def refresh_roof() -> None:
        roof_var.set(roof_summary(shared.get("roof")))
        check_all()

    shared["refresh_roof_nozzles"] = refresh_roof  # also keeps the tab's text variables alive
    add_rows(START_ROWS)
    refresh_roof()
    book = parent.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", lambda _event: refresh_roof(), add="+")


def draw_plan(canvas: tk.Canvas, roof, placed: list[RoofPlacement], framing: Layout | None = None) -> None:
    """The roof seen from above the way Elite draws a plan: 0° at 12 o'clock, growing clockwise (SolidWorks' Top
    view turned half round: +X to the left, +Z up). The Roof Framing tab's rafters go under the nozzles, as the
    lisp overlays them, to see what lands on one."""
    canvas.delete("all")
    if not isinstance(roof, RoofSpec):
        canvas.create_text(_PLAN_PX / 2, _PLAN_PX / 2, text="Set the roof on the Roof tab.", fill=_NOTE)
        return
    try:
        roof.validate()
        breaks = course_break_plan_radii(roof)
    except ValueError:
        return
    size = max(int(canvas.winfo_width()), _PLAN_PX) if canvas.winfo_ismapped() else _PLAN_PX
    landing = roof.landing_radius_in()
    shell = max(roof.outside_radius_in, landing)
    scale = (size / 2.0 - 26.0) / shell
    cx = cy = size / 2.0

    def at(x: float, z: float) -> tuple[float, float]:
        return (cx - x * scale, cy - z * scale)

    def circle(x, z, r, **style):
        sx, sy = at(x, z)
        canvas.create_oval(sx - r * scale, sy - r * scale, sx + r * scale, sy + r * scale, **style)

    circle(0.0, 0.0, roof.outside_radius_in, outline="#555555")
    circle(0.0, 0.0, landing, outline="#8a8a8a", dash=(4, 3))
    for radius in breaks:
        circle(0.0, 0.0, radius, outline="#b9b0a0", dash=(2, 3))
    for degree, anchor in ((0, "s"), (90, "w"), (180, "n"), (270, "e")):
        phi = math.radians(degree)
        x, y = at(-(shell + 8.0 / scale) * math.sin(phi), (shell + 8.0 / scale) * math.cos(phi))
        canvas.create_text(x, y, text=f"{degree}°", fill=_NOTE, anchor=anchor, font=("", 8))
    if isinstance(framing, Layout) and framing.roof == roof:
        for rafter in framing.rafters:
            corners = [c for p in rafter_outline(framing, rafter) for c in at(*p)]
            canvas.create_polygon(*corners, outline="#b08a5a", fill="#eadbc4")
    for spot in placed:
        if spot.repad is not None:
            outline = pad_outline(spot)
            if len(outline) >= 3:
                canvas.create_polygon(*[c for p in outline for c in at(*p)], outline="#2e7d32", fill="", width=1)
        px, pz = spot.plan_in
        circle(px, pz, spot.flange.outside_diameter_in / 2.0, outline="#1f4e79")
        circle(px, pz, spot.pipe.outside_diameter_in / 2.0, outline="#1f4e79", fill="#1f4e79")
        x, y = at(px, pz)
        canvas.create_text(x + 6, y - 6, text=spot.nozzle.mark, anchor="sw", fill="#1f4e79", font=("", 8, "bold"))
