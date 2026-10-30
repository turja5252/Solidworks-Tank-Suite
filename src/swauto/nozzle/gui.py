"""Shell Nozzles tab: a grid of nozzles for the shell on Tank Properties, typed straight into the cells."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

from swauto.errors import SolidWorksError
from swauto.nozzle.nozzle_sw import add_nozzles
from swauto.nozzle.pipe import nps_sizes
from swauto.nozzle.place import Placement, place
from swauto.nozzle.repad import default_repad_size
from swauto.nozzle.shape import stations
from swauto.nozzle.spec import Nozzle
from swauto.tank.open_shell import find_shell
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import TankSpec

_IN_PER_M = 1.0 / 0.0254

_ITEMS = (
    "Class 150 weld neck",
    "Class 300 weld neck",
    "Class 150 slip-on",
    "Class 300 slip-on",
)
_ITEM_PARTS = {
    "Class 150 weld neck": (150, "wn"),
    "Class 300 weld neck": (300, "wn"),
    "Class 150 slip-on": (150, "so"),
    "Class 300 slip-on": (300, "so"),
}
_SCHEDULES = ("STD", "XS", "XXS")
_STYLES = ("Circular", "Tombstone")
_REPADS = ("None", "Default", "Custom")
_INSIDE = ("None", "Weld neck", "Slip-on")  # RNC's break flange, in the nozzle's class

START_ROWS = 30
MORE_ROWS = 10
_CHECK_MS = 300
_OK = "#1a7f37"
_BAD = "#c62828"
_NOTE = "#666666"


@dataclass(frozen=True)
class _Column:
    key: str
    heading: str
    pixels: int
    kind: str = "entry"  # entry, combo, or check
    choices: tuple[str, ...] = ()
    default: str = ""


_COLUMNS = (
    _Column("mark", "Mark", 56),
    _Column("service", "Service", 110),
    _Column("item", "Item", 150, "combo", _ITEMS, _ITEMS[0]),
    _Column("size", "Size, in", 62, "combo", nps_sizes()),
    _Column("schedule", "Sch", 54, "combo", _SCHEDULES, "XS"),
    _Column("elevation", "Elev, in", 60),
    _Column("rotation", "Rot, deg", 60),
    _Column("osp", "OSP, in", 54),
    _Column("isp", "ISP, in", 54),
    _Column("inside_flange", "ISP flange", 80, "combo", _INSIDE, "None"),
    _Column("offset", "Offset, in", 64),
    _Column("match", "Match radial", 84, "check"),
    _Column("repad", "Repad", 78, "combo", _REPADS, "None"),
    _Column("pad_od", "Pad OD", 56),
    _Column("pad_id", "Pad ID", 56),
    _Column("pad_thk", "Pad thk", 56),
    _Column("style", "Style", 92, "combo", _STYLES, "Circular"),
    _Column("telltale", "Telltale", 56),
    _Column("blind", "Blind", 44, "check"),
    _Column("gasket", "Gasket", 50, "check"),
    _Column("gasket_material", "Gasket material", 140),
    _Column("gasket_thk", "Gskt thk", 58),
)
_NUMBER_PX = 30
_DOT_PX = 16
_CHECK_PX = 300
_CLEAR_PX = 30
# Typed cells. A row with all of these blank is skipped.
_TYPED = tuple(column.key for column in _COLUMNS if column.kind == "entry") + ("size",)


@dataclass(frozen=True)
class RowCheck:
    """One grid row read: its nozzle when it is good, and what to show in its Check cell."""

    nozzle: Nozzle | None
    message: str
    ok: bool

    @property
    def blank(self) -> bool:
        return self.nozzle is None and self.ok


def blank_row() -> dict[str, object]:
    """An empty row. Its dropdowns stay blank until the row is used; then they show their defaults."""
    return {column.key: (False if column.kind == "check" else "") for column in _COLUMNS}


def _with_defaults(values: dict[str, object]) -> dict[str, object]:
    filled = dict(values)
    for column in _COLUMNS:
        if column.kind == "combo" and column.default and not str(filled.get(column.key, "")).strip():
            filled[column.key] = column.default
    return filled


def check_rows(rows: list[dict[str, object]], spec) -> list[RowCheck]:
    """Read every grid row. Blank rows come back blank; a mark on two rows is wrong on both."""
    shell = spec if isinstance(spec, TankSpec) and spec.active_courses() else None
    checks: list[RowCheck] = []
    for values in rows:
        if all(not str(values.get(key, "")).strip() for key in _TYPED):
            checks.append(RowCheck(None, "", True))
            continue
        try:
            nozzle = _row_nozzle(values)
            if shell is None:
                checks.append(RowCheck(nozzle, "Set a shell on Tank Properties to place it.", True))
                continue
            placed = place(nozzle, shell)
            stations(placed)
        except ValueError as exc:
            checks.append(RowCheck(None, str(exc), False))
            continue
        checks.append(RowCheck(nozzle, _row_summary(placed), True))
    rows_by_mark: dict[str, list[int]] = {}
    for index, check in enumerate(checks):
        if check.nozzle is not None:
            rows_by_mark.setdefault(check.nozzle.mark, []).append(index)
    for mark, indexes in rows_by_mark.items():
        if len(indexes) > 1:
            others = ", ".join(str(i + 1) for i in indexes)
            for index in indexes:
                checks[index] = RowCheck(None, f"{mark} is on rows {others}. Marks must differ.", False)
    return checks


def _row_nozzle(values: dict[str, object]) -> Nozzle:
    values = _with_defaults(values)
    if not str(values.get("mark", "")).strip():
        raise ValueError("Enter a mark, like N1.")
    if not str(values.get("size", "")).strip():
        raise ValueError("Choose a size.")
    return nozzle_from_fields(
        str(values["mark"]).strip(),
        str(values["item"]),
        str(values["size"]),
        str(values["schedule"]),
        str(values["elevation"]),
        str(values["rotation"]),
        str(values["osp"]),
        str(values["isp"]),
        str(values["offset"]),
        bool(values["match"]),
        str(values["repad"]).lower(),
        str(values["pad_od"]),
        str(values["pad_id"]),
        str(values["pad_thk"]),
        str(values["style"]),
        str(values["telltale"]),
        str(values["service"]),
        blind=bool(values["blind"]),
        gasket=bool(values["gasket"]),
        gasket_material=str(values["gasket_material"]),
        gasket_thickness=str(values["gasket_thk"]),
        inside_flange=str(values["inside_flange"]),
    )


def _row_summary(placed: Placement) -> str:
    nozzle = placed.nozzle
    shape = "WN" if nozzle.kind == "wn" else "SO"
    pad = placed.repad
    pad_text = "no pad" if pad is None else f"pad {pad.outer_diameter_in:g} x {pad.thickness_in:g}"
    extras = "".join(
        text
        for text in (
            ", blind" if nozzle.blind else "",
            f", {placed.gasket.material} gasket" if placed.gasket is not None else "",
            f", inside {'WN' if nozzle.inside_flange == 'wn' else 'SO'} flange"
            if nozzle.inside_flange != "none" else "",
        )
    )
    matched = (f", face {placed.chord_in:.3f} in out to the radial plane"
               if nozzle.match_plane and nozzle.offset_in and placed.chord_in else "")
    return (f"OK  {nozzle.nps} in {nozzle.rating}# {shape}, course {placed.course_number}, {pad_text}{extras}"
            f"{matched}")


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
        """Once a row is used its blank dropdowns show what it will be built with."""
        for column in _COLUMNS:
            if column.kind == "combo" and column.default:
                var = self.vars[column.key]
                if used and not var.get():
                    var.set(column.default)
                elif not used and var.get() == column.default:
                    var.set("")

    def sync_repad(self) -> None:
        """Default fills and locks the standard pad for the size; Custom is typed; None greys the pad out."""
        mode = self.vars["repad"].get() or "None"
        if mode == "Default":
            standard = default_repad_size(self.vars["size"].get()) if self.vars["size"].get() else None
            texts = ("", "", "") if standard is None else tuple(f"{value:g}" for value in standard)
            for key, text in zip(("pad_od", "pad_id", "telltale"), texts, strict=True):
                if self.vars[key].get() != text:
                    self.vars[key].set(text)
        for key in ("pad_od", "pad_id", "telltale"):
            self.widgets[key].state(["!disabled"] if mode == "Custom" else ["disabled"])
        self.widgets["pad_thk"].state(["!disabled"] if mode != "None" else ["disabled"])
        self.widgets["style"].configure(state="readonly" if mode != "None" else "disabled")
        gasket = bool(self.vars["gasket"].get())
        for key in ("gasket_material", "gasket_thk"):
            self.widgets[key].state(["!disabled"] if gasket else ["disabled"])
        # Match radial moves an offset nozzle's face and inner end; a radial nozzle (no offset) has nothing to match.
        try:
            offset = float(self.vars["offset"].get().strip() or "0")
        except ValueError:
            offset = 0.0
        self.widgets["match"].state(["!disabled"] if offset else ["disabled"])

    def show(self, check: RowCheck) -> None:
        self.message = check.message
        if not check.ok:
            color = _BAD
        elif check.message.startswith("OK"):
            color = _OK
        else:
            color = _NOTE  # blank, or no shell yet to place it on
        text = check.message if len(check.message) <= 48 else check.message[:46] + "…"
        self.check.configure(text=text, foreground=color)
        self.dot.configure(text="" if check.blank else "●", foreground=color)


def build_nozzle_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    """Fill the Shell Nozzles tab. ``shared["spec"]`` is the Tank Properties shell."""
    if shared is None:
        shared = {}
    nozzles: list[Nozzle] = []
    shared["nozzles"] = nozzles

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    frame = ttk.Frame(parent, padding=8)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(3, weight=1)

    ttk.Label(frame, text="Shell nozzles", font=("", 11, "bold")).grid(row=0, column=0, sticky="w")
    shell_var = tk.StringVar()
    ttk.Label(frame, textvariable=shell_var, justify="left").grid(row=1, column=0, sticky="w", pady=(2, 6))

    bar = ttk.Frame(frame)
    bar.grid(row=2, column=0, sticky="ew", pady=(0, 4))
    bar.columnconfigure(3, weight=1)
    count_var = tk.StringVar()
    ttk.Label(
        bar,
        text="OSP: shell outside to the flange face.  ISP: shell inside to the inner end.  Match radial (an offset "
             "nozzle only): its flange face and inner end go where a radial nozzle's with the same OSP and ISP would.",
        foreground=_NOTE,
        wraplength=620,
        justify="left",
    ).grid(row=0, column=3, sticky="e")

    # Header and body are separate canvases on one horizontal scrollbar, so the header stays put.
    table = ttk.Frame(frame)
    table.grid(row=3, column=0, sticky="nsew")
    table.columnconfigure(0, weight=1)
    table.rowconfigure(1, weight=1)
    head_canvas = tk.Canvas(table, highlightthickness=0, height=24)
    body_canvas = tk.Canvas(table, highlightthickness=0, height=360)
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
    headings = ("#", "", *(column.heading for column in _COLUMNS), "Check", "")
    for col, text in enumerate(headings):
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
        """Scroll so the cell with the cursor is in view."""
        body.update_idletasks()
        total_h = max(body.winfo_reqheight(), 1)
        total_w = max(body.winfo_reqwidth(), 1)
        top = body_canvas.canvasy(0)
        left = body_canvas.canvasx(0)
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

    rows: list[_Row] = []
    pending = {"after": None}

    def current_spec():
        return shared.get("spec")

    def check_all() -> list[RowCheck]:
        pending["after"] = None
        for row in rows:
            values = row.values()
            row.show_defaults(any(str(values[key]).strip() for key in _TYPED))
            row.sync_repad()
        checks = check_rows([row.values() for row in rows], current_spec())
        for row, check in zip(rows, checks, strict=True):
            row.show(check)
        nozzles[:] = [check.nozzle for check in checks if check.nozzle is not None]
        bad = sum(1 for check in checks if not check.ok)
        count_var.set(f"{len(nozzles)} ready" + (f", {bad} to fix" if bad else ""))
        return checks

    def changed() -> None:
        if pending["after"] is not None:
            frame.after_cancel(pending["after"])
        pending["after"] = frame.after(_CHECK_MS, check_all)

    def clear_row(row: _Row) -> None:
        row.clear()
        status_var.set(f"Cleared row {row.number}.")

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
                    # A combobox turns the wheel into a new value; scroll the grid instead.
                    widget.bind("<MouseWheel>", wheel)
                    widget.bind("<Return>", lambda _e, r=row, k=column.key: move(r, k, 1))
        fit_scroll()
        check_all()

    def add_more() -> None:
        first = len(rows)
        add_rows(MORE_ROWS)
        rows[first].widgets["mark"].focus_set()
        status_var.set(f"Added rows {first + 1} to {len(rows)}.")

    busy = {"on": False}

    def build_on_shell() -> None:
        if busy["on"]:
            return
        checks = check_all()
        wrong = [(index, check) for index, check in enumerate(checks) if not check.ok]
        if wrong:
            lines = [f"Row {index + 1}: {check.message}" for index, check in wrong[:8]]
            if len(wrong) > 8:
                lines.append(f"…and {len(wrong) - 8} more.")
            messagebox.showerror("Shell nozzle", "Fix these rows first:\n\n" + "\n".join(lines))
            rows[wrong[0][0]].widgets["mark"].focus_set()
            return
        if not nozzles:
            messagebox.showerror("Shell nozzle", "Fill in at least one row first.")
            return
        try:
            from swauto.session import connect

            live = find_shell(shared, connect().app)  # this run's shell, or the shell part open in SolidWorks
        except (ValueError, SolidWorksError) as exc:
            messagebox.showerror("Shell nozzle", str(exc))
            return
        model, spec = live.model, live.spec
        busy["on"] = True
        status_var.set(f"Building {len(nozzles)} nozzle(s) on the shell...")
        frame.update_idletasks()
        try:
            status_var.set(add_nozzles(model, spec, list(nozzles)))
        except (SolidWorksError, ValueError) as exc:
            status_var.set(str(exc))
            messagebox.showerror("Shell nozzle", str(exc))
        finally:
            busy["on"] = False

    ttk.Button(bar, text="Build on shell", command=build_on_shell).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(bar, text=f"Add {MORE_ROWS} rows", command=add_more).grid(row=0, column=1, padx=(0, 10))
    ttk.Label(bar, textvariable=count_var).grid(row=0, column=2, sticky="w")

    def load_nozzles(saved) -> None:
        """Fill the grid from a saved project; rows past the saved nozzles are cleared."""
        if len(saved) > len(rows):
            add_rows(len(saved) - len(rows))
        for row in rows:
            row.clear()
        for row, nozzle in zip(rows, saved):
            for key, value in row_values(nozzle).items():
                row.vars[key].set(value)
        check_all()

    shared["load_nozzles"] = load_nozzles

    def refresh_shell() -> None:
        shell_var.set(shell_summary(current_spec()))
        check_all()

    add_rows(START_ROWS)
    refresh_shell()
    book = parent.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", lambda _event: refresh_shell(), add="+")


def row_values(nozzle: Nozzle) -> dict[str, object]:
    """A saved nozzle as grid cells: what reading the row gives back. Default repads fill themselves in."""

    def num(value) -> str:
        return "" if value is None else f"{value:g}"

    custom = nozzle.repad_mode == "custom"
    return {
        "mark": nozzle.mark,
        "service": nozzle.description,
        "item": f"Class {nozzle.rating} {'weld neck' if nozzle.kind == 'wn' else 'slip-on'}",
        "size": nozzle.nps,
        "schedule": nozzle.schedule,
        "elevation": num(nozzle.elevation_in),
        "rotation": num(nozzle.rotation_deg),
        "osp": num(nozzle.outside_projection_in),
        "isp": num(nozzle.inside_projection_in),
        "offset": num(nozzle.offset_in),
        "match": nozzle.match_plane,
        "repad": nozzle.repad_mode.capitalize(),
        "pad_od": num(nozzle.repad_outer_in) if custom else "",
        "pad_id": num(nozzle.repad_inner_in) if custom else "",
        "pad_thk": num(nozzle.repad_thickness_in) if nozzle.repad_mode != "none" else "",
        "style": "Tombstone" if nozzle.repad_style == "tombstone" else "Circular",
        "telltale": num(nozzle.telltale_offset_in) if custom else "",
        "blind": nozzle.blind,
        "gasket": nozzle.gasket,
        "gasket_material": nozzle.gasket_material,
        "gasket_thk": num(nozzle.gasket_thickness_in) if nozzle.gasket else "",
        "inside_flange": {"wn": "Weld neck", "so": "Slip-on"}.get(nozzle.inside_flange, "None"),
    }


def nozzle_from_fields(
    mark: str,
    item: str,
    nps: str,
    schedule: str,
    elevation: str,
    rotation: str,
    osp: str,
    isp: str,
    offset: str,
    match_plane: bool,
    repad_mode: str,
    outer: str,
    inner: str,
    thickness: str,
    style: str,
    telltale: str,
    description: str,
    *,
    blind: bool = False,
    gasket: bool = False,
    gasket_material: str = "",
    gasket_thickness: str = "",
    inside_flange: str = "None",
) -> Nozzle:
    """Build a nozzle from the tab fields. Lengths are inches, rotation is degrees."""
    parts = _ITEM_PARTS.get(item)
    if parts is None:
        raise ValueError("Choose a weld neck or a slip-on, Class 150 or 300.")
    rating, kind = parts
    thickness_in = _optional_inches(thickness, "Repad thickness")
    telltale_in = _inches(telltale, "telltale offset", blank=1.0)
    return Nozzle(
        mark=mark,
        nps=nps,
        rating=rating,
        kind=kind,
        schedule=schedule,
        elevation_in=_inches(elevation, "elevation"),
        rotation_deg=_inches(rotation, "rotation", blank=0.0),
        outside_projection_in=_inches(osp, "outside projection"),
        inside_projection_in=_inches(isp, "inside projection"),
        offset_in=_inches(offset, "offset", blank=0.0),
        match_plane=bool(match_plane),
        repad_mode=repad_mode,
        repad_outer_in=_inches(outer, "repad outside diameter", blank=0.0),
        repad_inner_in=_inches(inner, "repad inside diameter", blank=0.0),
        repad_thickness_in=thickness_in,
        repad_style="tombstone" if style == "Tombstone" else "circular",
        telltale_offset_in=telltale_in,
        description=description,
        blind=bool(blind),
        gasket=bool(gasket),
        gasket_material=gasket_material if gasket else "",
        gasket_thickness_in=_optional_inches(gasket_thickness, "gasket thickness") if gasket else None,
        inside_flange=inside_flange,
    )


def shell_summary(spec) -> str:
    """The shell the nozzles go on, course by course from the bottom, as Tank Properties has it."""
    if not isinstance(spec, TankSpec) or not spec.active_courses():
        return "No shell yet: set one on Tank Properties."
    lines = [f"Diameter {spec.diameter_in:g} in ({spec.diameter_basis.upper()})"]
    bottom = 0.0
    for number, course in enumerate(spec.active_courses(), start=1):
        outer_m, _inner_m = course_radii_m(spec, course)
        lines.append(
            f"Course {number}: {bottom:g} to {bottom + course.height_in:g} in up, {course.thickness_in:g} in thick, "
            f"outside radius {outer_m * _IN_PER_M:.3f} in"
        )
        bottom += course.height_in
    return "\n".join(lines)


def _inches(text: str, what: str, *, blank: float | None = None) -> float:
    raw = str(text).strip()
    if not raw:
        if blank is None:
            raise ValueError(f"Enter the {what}.")
        return blank
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"The {what} must be a number.") from None


def _optional_inches(text: str, what: str) -> float | None:
    raw = str(text).strip()
    if not raw:
        return None
    return _inches(raw, what)
