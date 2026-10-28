"""FTCO tab: flush-type cleanouts typed into a grid, built into course 1 of the tank on Tank Properties."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, fields
from tkinter import messagebox, ttk

from swauto.cleanout.layout import course_one_gaps
from swauto.cleanout.spec import SIZES, Cleanout
from swauto.errors import SolidWorksError
from swauto.tank.spec import TankSpec

START_ROWS = 4  # the FTCO Engine's slots
_CHECK_MS = 300
_OK = "#1a7f37"
_BAD = "#c62828"
_NOTE = "#666666"
_ANCHORS = ("None", "Left", "Right", "Short")
_DEFAULTS = {f.name: f.default for f in fields(Cleanout)}


@dataclass(frozen=True)
class _Column:
    key: str  # Cleanout field, or "" for none
    heading: str
    pixels: int
    kind: str = "entry"  # entry or combo
    choices: tuple[str, ...] = ()


def _heading(text: str, key: str) -> str:
    return f"{text}\n({_DEFAULTS[key]:g})"


_COLUMNS = (
    _Column("mark", "Mark", 56),
    _Column("size", "Size", 70, "combo", tuple(SIZES)),
    _Column("orientation_deg", "Orient,\ndeg", 56),
    _Column("anchor", "Anchor", 70, "combo", _ANCHORS),
    _Column("insert_thk_in", _heading("Insert", "insert_thk_in"), 54),
    _Column("repad_thk_in", _heading("Repad", "repad_thk_in"), 54),
    _Column("neck_wall_in", _heading("Neck", "neck_wall_in"), 54),
    _Column("flange_thk_in", _heading("Flange", "flange_thk_in"), 54),
    _Column("gasket_thk_in", _heading("Gasket", "gasket_thk_in"), 54),
    _Column("gasket_material", "Gasket\nmaterial", 120),
    _Column("cover_thk_in", _heading("Cover", "cover_thk_in"), 54),
    _Column("baseplate_thk_in", _heading("Bottom", "baseplate_thk_in"), 54),
    _Column("annular_width_in", "Bottom\nwidth", 58),
    _Column("chime_in", _heading("Chime", "chime_in"), 54),
    _Column("annular_thk_in", _heading("Annular", "annular_thk_in"), 58),
)
_NUMBERS = tuple(c.key for c in _COLUMNS if c.kind == "entry" and c.key not in ("mark", "gasket_material"))
_TYPED = tuple(c.key for c in _COLUMNS if c.kind == "entry")


@dataclass(frozen=True)
class RowCheck:
    cleanout: Cleanout | None
    message: str
    ok: bool


def blank_row() -> dict[str, str]:
    return {column.key: "" for column in _COLUMNS}


def cleanout_from_row(values: dict[str, str]) -> Cleanout:
    """One grid row as an FTCO. Blank thicknesses take the FTCO Engine defaults."""
    if not str(values.get("mark", "")).strip():
        raise ValueError("Enter a mark, like C1.")
    if not str(values.get("orientation_deg", "")).strip():
        raise ValueError("Enter the orientation.")
    if not str(values.get("annular_width_in", "")).strip():
        raise ValueError("Enter the bottom plate width (the annular width).")
    kwargs: dict[str, object] = {
        "mark": str(values["mark"]).strip(),
        "size": str(values.get("size") or "12'-5\""),
        "anchor": str(values.get("anchor") or "None"),
        "gasket_material": str(values.get("gasket_material", "")),
    }
    for key in _NUMBERS:
        raw = str(values.get(key, "")).strip()
        if not raw:
            continue
        try:
            kwargs[key] = float(raw)
        except ValueError:
            label = next(c.heading for c in _COLUMNS if c.key == key).split("\n")[0].lower()
            raise ValueError(f"The {label} must be a number.") from None
    return Cleanout(**kwargs)


def check_rows(rows: list[dict[str, str]], spec) -> list[RowCheck]:
    """Read every row; blank rows are skipped. The FTCOs that read are checked together on course 1."""
    checks: list[RowCheck] = []
    for values in rows:
        if all(not str(values.get(key, "")).strip() for key in _TYPED):
            checks.append(RowCheck(None, "", True))
            continue
        try:
            cleanout = cleanout_from_row(values)
        except ValueError as exc:
            checks.append(RowCheck(None, str(exc), False))
            continue
        dims = cleanout.dims
        checks.append(RowCheck(cleanout, f"OK  {dims.label} (48 x {dims.opening_height_in:g}) at "
                                         f"{cleanout.orientation_deg:g} deg, anchor {cleanout.anchor}", True))
    good = [check.cleanout for check in checks if check.cleanout is not None]
    if good and isinstance(spec, TankSpec) and spec.active_courses():
        try:
            course_one_gaps(spec, good)
        except ValueError as exc:
            checks = [RowCheck(None, str(exc), False) if check.cleanout is not None else check for check in checks]
    return checks


def build_cleanout_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    """Fill the FTCO tab. ``shared["spec"]`` and ``shared["live"]`` come from Tank Properties."""
    if shared is None:
        shared = {}
    cleanouts: list[Cleanout] = []
    shared["cleanouts"] = cleanouts
    shared["course_one_gaps"] = lambda spec: course_one_gaps(spec, cleanouts) if cleanouts else []

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    frame = ttk.Frame(parent, padding=8)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(3, weight=1)
    ttk.Label(frame, text="Flush-type cleanouts (FTCO)", font=("", 11, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(
        frame,
        text=("Each FTCO's insert plate is a course-1 shell plate. Anchor puts a course-1 seam on one edge "
              "of it (one FTCO only). Orientation is measured like a nozzle's rotation. Blank thicknesses "
              "use the defaults in brackets."),
        foreground=_NOTE, wraplength=900, justify="left",
    ).grid(row=1, column=0, sticky="w", pady=(2, 6))
    bar = ttk.Frame(frame)
    bar.grid(row=2, column=0, sticky="ew", pady=(0, 4))
    count_var = tk.StringVar()

    table = ttk.Frame(frame)
    table.grid(row=3, column=0, sticky="nsew")
    canvas = tk.Canvas(table, highlightthickness=0, height=220)
    canvas.grid(row=0, column=0, sticky="nsew")
    table.columnconfigure(0, weight=1)
    table.rowconfigure(0, weight=1)
    x_bar = ttk.Scrollbar(table, orient="horizontal", command=canvas.xview)
    x_bar.grid(row=1, column=0, sticky="ew")
    canvas.configure(xscrollcommand=x_bar.set)
    grid = ttk.Frame(canvas)
    canvas.create_window((0, 0), window=grid, anchor="nw")
    widths = (30, *(c.pixels for c in _COLUMNS), 330)
    for col, pixels in enumerate(widths):
        grid.columnconfigure(col, minsize=pixels)
    for col, text in enumerate(("#", *(c.heading for c in _COLUMNS), "Check")):
        ttk.Label(grid, text=text, font=("", 9, "bold"), anchor="w", justify="left").grid(
            row=0, column=col, sticky="sw", padx=1
        )
    grid.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

    rows: list[dict] = []
    pending = {"after": None}

    def check_all() -> list[RowCheck]:
        pending["after"] = None
        checks = check_rows([{k: v.get() for k, v in row["vars"].items()} for row in rows], shared.get("spec"))
        for row, check in zip(rows, checks, strict=True):
            color = _BAD if not check.ok else (_OK if check.cleanout is not None else _NOTE)
            text = check.message if len(check.message) <= 56 else check.message[:54] + "…"
            row["check"].configure(text=text, foreground=color)
            row["message"] = check.message
        cleanouts[:] = [check.cleanout for check in checks if check.cleanout is not None]
        bad = sum(1 for check in checks if not check.ok)
        count_var.set(f"{len(cleanouts)} ready" + (f", {bad} to fix" if bad else ""))
        return checks

    def changed() -> None:
        if pending["after"] is not None:
            frame.after_cancel(pending["after"])
        pending["after"] = frame.after(_CHECK_MS, check_all)

    def add_row() -> None:
        number = len(rows) + 1
        ttk.Label(grid, text=str(number), foreground=_NOTE, anchor="e").grid(row=number, column=0, sticky="ew")
        row: dict = {"vars": {}, "message": ""}
        for col, column in enumerate(_COLUMNS, start=1):
            var = tk.StringVar()
            if column.kind == "combo":
                widget = ttk.Combobox(grid, textvariable=var, values=column.choices, width=1, state="readonly")
            else:
                widget = ttk.Entry(grid, textvariable=var, width=1)
            widget.grid(row=number, column=col, sticky="ew", padx=1, pady=1)
            widget.bind("<FocusIn>", lambda _e, r=row: status_var.set(r["message"]), add="+")
            var.trace_add("write", lambda *_a: changed())
            row["vars"][column.key] = var
        row["check"] = ttk.Label(grid, anchor="w")
        row["check"].grid(row=number, column=len(_COLUMNS) + 1, sticky="ew", padx=(6, 0))
        rows.append(row)
        check_all()

    busy = {"on": False}

    def build_on_shell() -> None:
        if busy["on"]:
            return
        checks = check_all()
        wrong = [(i, check) for i, check in enumerate(checks) if not check.ok]
        if wrong:
            messagebox.showerror("FTCO", "Fix these rows first:\n\n" + "\n".join(
                f"Row {i + 1}: {check.message}" for i, check in wrong[:8]))
            return
        if not cleanouts:
            messagebox.showerror("FTCO", "Fill in at least one row first.")
            return
        live = shared.get("live")
        model = getattr(live, "model", None)
        spec = getattr(live, "spec", None)
        if model is None or not isinstance(spec, TankSpec):
            messagebox.showerror("FTCO", "Create the tank shell on Tank Properties first.")
            return
        busy["on"] = True
        status_var.set("Rebuilding course 1 around the FTCOs, then building them...")
        frame.update_idletasks()
        try:
            status_var.set(rebuild_with_cleanouts(live, spec, list(cleanouts), list(shared.get("nozzles") or [])))
        except (SolidWorksError, ValueError) as exc:
            status_var.set(str(exc))
            messagebox.showerror("FTCO", str(exc))
        finally:
            busy["on"] = False

    ttk.Button(bar, text="Build on shell", command=build_on_shell).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(bar, text="Add row", command=add_row).grid(row=0, column=1, padx=(0, 10))
    ttk.Label(bar, textvariable=count_var).grid(row=0, column=2, sticky="w")
    for _ in range(START_ROWS):
        add_row()
    book = parent.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", lambda _e: check_all(), add="+")


def rebuild_with_cleanouts(live, spec: TankSpec, cleanouts: list[Cleanout], nozzles: list) -> str:
    """Course 1 laid out around the FTCOs, the FTCOs, then the nozzles again: their holes were in the old shell."""
    from swauto.cleanout.cleanout_sw import add_cleanouts, delete_cleanouts
    from swauto.features import iter_features
    from swauto.nozzle.nozzle_sw import _delete_prefixed, add_nozzles
    from swauto.session import connect

    model = live.model
    has_nozzles = any(str(f.Name).startswith("EliteNozzle") for f in iter_features(model))
    if has_nozzles and not nozzles:
        raise ValueError(
            "This shell has nozzles. List them on Shell Nozzles first so they are rebuilt with the new shell."
        )
    gaps = course_one_gaps(spec, cleanouts)
    delete_cleanouts(model)
    if has_nozzles:
        _delete_prefixed(model)
    live.update(connect().app, spec, gaps)
    note = add_cleanouts(live.model, spec, cleanouts)
    if nozzles:
        note += " " + add_nozzles(live.model, spec, nozzles)
    return note
