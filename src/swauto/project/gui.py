"""Project tab: save a tank as a project, see what each part file needs, build only what changed."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from swauto import runlog
from swauto.errors import SolidWorksError
from swauto.project.project import BUILT, CHANGED, FAILED, NEW, SUFFIX, Project, safe_name
from swauto.tank.spec import TankSpec

_SHOW = {
    BUILT: "✔ built",
    CHANGED: "⟳ changed — rebuilds next build",
    NEW: "• new — builds next build",
    FAILED: "✖ failed",
}


def build_project_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    """Fill the Project tab. Inputs come live from the other tabs through ``shared``."""
    if shared is None:
        shared = {}
    state: dict[str, Project | None] = {"project": None}

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    frame = ttk.Frame(parent, padding=8)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(3, weight=1)

    ttk.Label(frame, text="Project", font=("", 11, "bold")).grid(row=0, column=0, sticky="w")
    where_var = tk.StringVar(value="No project open. New project saves this tank's inputs in a folder you pick.")
    ttk.Label(frame, textvariable=where_var, foreground="#555555", wraplength=900, justify="left").grid(
        row=1, column=0, sticky="w", pady=(2, 6)
    )
    bar = ttk.Frame(frame)
    bar.grid(row=2, column=0, sticky="ew", pady=(0, 6))

    table = ttk.Frame(frame)
    table.grid(row=3, column=0, sticky="nsew")
    table.columnconfigure(0, weight=1)
    table.rowconfigure(0, weight=1)
    columns = ("file", "what", "copies", "status")
    tree = ttk.Treeview(table, columns=columns, show="headings", height=14)
    for column, heading, width in zip(
        columns, ("Part file", "What", "Copies", "Status"), (220, 360, 60, 300), strict=True
    ):
        tree.heading(column, text=heading)
        tree.column(column, width=width, anchor="w", stretch=column in ("what", "status"))
    tree.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    summary_var = tk.StringVar()
    ttk.Label(frame, textvariable=summary_var).grid(row=4, column=0, sticky="w", pady=(6, 0))

    def inputs() -> tuple[TankSpec, list, list]:
        spec = shared.get("spec")
        if not isinstance(spec, TankSpec) or not spec.active_courses():
            raise ValueError("Set the tank on Tank Properties first.")
        return spec, list(shared.get("cleanouts") or []), list(shared.get("nozzles") or [])

    def take_inputs(project: Project) -> None:
        project.spec, project.cleanouts, project.nozzles = inputs()
        project.roof_nozzles = list(shared.get("roof_nozzles") or [])

    def show(project: Project, saved: bool) -> None:
        """Name the open project here and in the bar over every tab."""
        shared["project"] = project  # other tabs can tell when the shell is the project's parts
        runlog.use_project(project.folder, project.name)
        where_var.set(f"{project.name} — {project.folder}")
        label = shared.get("project_label")
        if isinstance(label, tk.StringVar):
            label.set(f"Project: {project.name}  ({project.folder})" + ("  — saved" if saved else ""))

    def refresh(_event=None) -> None:
        tree.delete(*tree.get_children())
        project = state["project"]
        if project is None:
            summary_var.set("")
            return
        where_var.set(f"{project.name} — {project.folder}")
        try:
            take_inputs(project)
            items = project.items()
        except ValueError as exc:
            summary_var.set(str(exc))
            return
        counts: dict[str, int] = {}
        for item in items:
            status = project.status(item)
            counts[status] = counts.get(status, 0) + 1
            shown = _SHOW[status]
            if status == FAILED:
                shown += f": {project.built.get(item.file, {}).get('error', '')}"
            tree.insert("", "end", values=(item.file, item.label, len(item.placements), shown))
        copies = sum(len(item.placements) for item in items)
        todo = counts.get(NEW, 0) + counts.get(CHANGED, 0) + counts.get(FAILED, 0)
        summary_var.set(
            f"{len(items)} part files, {copies} pieces in the assembly. "
            + (f"{todo} part file(s) to build." if todo else "Everything is built.")
        )

    def new_project() -> None:
        try:
            spec, cleanouts, nozzles = inputs()
        except ValueError as exc:
            messagebox.showerror("Project", str(exc))
            return
        folder = filedialog.askdirectory(title="Folder for this tank's project (part files go here too)")
        if not folder:
            return
        name = simpledialog.askstring("Project", "Project name:", initialvalue=os.path.basename(folder),
                                      parent=frame)
        if name is None:
            return
        try:
            project = Project(folder=Path(folder), name=safe_name(name), spec=spec, cleanouts=cleanouts,
                              nozzles=nozzles, roof_nozzles=list(shared.get("roof_nozzles") or []))
        except ValueError as exc:
            messagebox.showerror("Project", str(exc))
            return
        if project.path.exists() and not messagebox.askyesno(
            "Project", f"{project.path.name} is already in that folder. Replace it with this tank?"
        ):
            return
        project.save()
        state["project"] = project
        show(project, saved=True)
        status_var.set(f"Saved {project.path}")
        refresh()

    def open_project() -> None:
        path = filedialog.askopenfilename(title="Open a tank project",
                                          filetypes=[("Elite tank project", f"*{SUFFIX}")])
        if not path:
            return
        try:
            project = Project.load(path)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            messagebox.showerror("Project", f"Could not read {os.path.basename(path)}:\n{exc}")
            return
        # Fill the other tabs; each one feeds its inputs back through ``shared`` as it reads them.
        missing = []
        for hook, value in (("apply_spec", project.spec), ("load_cleanouts", project.cleanouts),
                            ("load_nozzles", project.nozzles), ("load_roof_nozzles", project.roof_nozzles)):
            fill = shared.get(hook)
            if callable(fill):
                fill(value)
            elif value:
                missing.append(hook)
        if missing:
            messagebox.showwarning("Project", "Some tabs could not take the saved values: " + ", ".join(missing))
        state["project"] = project
        show(project, saved=True)
        status_var.set(f"Opened {project.path}")
        frame.after(400, refresh)  # the grids check their rows a moment after they change

    def save_project() -> None:
        project = state["project"]
        if project is None:
            new_project()
            return
        try:
            take_inputs(project)
        except ValueError as exc:
            messagebox.showerror("Project", str(exc))
            return
        project.save()
        show(project, saved=True)
        status_var.set(f"Saved {project.path}")
        refresh()

    shared["save_project"] = save_project  # the Save project bar over every tab calls this

    busy = {"on": False}

    def build(force: bool) -> None:
        project = state["project"]
        if project is None:
            messagebox.showerror("Project", "Make a project first (New project), so the parts have a folder.")
            return
        if busy["on"]:
            return
        if force and not messagebox.askyesno("Project", "Rebuild every part file, changed or not?"):
            return
        try:
            take_inputs(project)
            project.items()
        except ValueError as exc:
            messagebox.showerror("Project", str(exc))
            return
        from swauto.project.build_sw import build_project
        from swauto.session import connect

        busy["on"] = True
        root = frame.winfo_toplevel()

        def progress(text: str) -> None:
            status_var.set(text)
            root.update_idletasks()

        try:
            status_var.set(build_project(connect().app, project, force=force, progress=progress))
        except (SolidWorksError, ValueError) as exc:
            status_var.set(str(exc))
            messagebox.showerror("Project", str(exc))
        except Exception as exc:  # noqa: BLE001 - keep the app up, say what went wrong
            from swauto.comutil import format_com_error

            status_var.set(format_com_error(exc))
            messagebox.showerror("Project", format_com_error(exc))
        finally:
            busy["on"] = False
            refresh()

    def open_assembly() -> None:
        project = state["project"]
        if project is None or not project.assembly_path.exists():
            messagebox.showerror("Project", "Build the project first; the assembly is made then.")
            return
        from swauto.project.build_sw import _DOC_ASSEMBLY, _open
        from swauto.session import connect

        try:
            _open(connect().app, project.assembly_path, _DOC_ASSEMBLY)
        except Exception as exc:  # noqa: BLE001 - keep the app up, say what went wrong
            messagebox.showerror("Project", str(exc))

    for col, (text, command) in enumerate((
        ("New project…", new_project),
        ("Open project…", open_project),
        ("Save", save_project),
        ("Build changes", lambda: build(False)),
        ("Rebuild all", lambda: build(True)),
        ("Open assembly", open_assembly),
    )):
        ttk.Button(bar, text=text, command=command).grid(row=0, column=col, padx=(0, 6))

    book = parent.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", refresh, add="+")
