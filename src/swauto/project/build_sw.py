"""Build a project's part files and keep its assembly in step, in SolidWorks 2013.

A part is never edited while the assembly holds it: SolidWorks 2013 crashed
(slduiu.dll) deleting features of a part the assembly had loaded but that had
no window of its own. So a build saves and closes the assembly, rebuilds each
changed part in its own active window, saves and closes it, and only then opens
the assembly again to sync it. Components are matched to placements by file and
transform; new ones go in with one ``AddComponents3`` call, which turns them but
drops the move, so each one's transform is then set whole. Every component is
fixed, with no mates to break.

Nozzle pieces and the holes in shell plates are built with the nozzle engine's
own steps (``swauto.nozzle.nozzle_sw``), on parts of their own.
"""

from __future__ import annotations

import contextlib
import math
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.nozzle.nozzle_sw import (
    _close_sketch,
    _cut,
    _cut_shell,
    _drew,
    _latest,
    _learn_right_plane,
    _offset_front,
    _open_on,
    _repad,
    _revolve_loop,
    _safe,
)
from swauto.nozzle.nozzle_sw import _hide_sketch as _hide_nozzle_sketch
from swauto.nozzle.shape import bolt_centers
from swauto.params import rebuild, rename_feature
from swauto.parts import new_part
from swauto.project.items import FTCO_PIECE, REPAD, SHELL_PLATE, TURNED, Item
from swauto.project.project import BUILT, Project
from swauto.tank.open_shell import PROJECT_PART_PROPERTY
from swauto.tank.plates import PlateSector
from swauto.tank.shell import (
    _build_one_plate,
    _ensure_axis_sketch,
    _ensure_tank_axis,
    _hide_construction_geometry,
)

_INCH = 0.0254
_FAR_IN = 1.0e4  # a nozzle piece's own part has no shell: anything nearer than this is the piece
_DOC_PART = 1
_DOC_ASSEMBLY = 2
_OPEN_SILENT = 1
_SAVE_SILENT = 1
_TEMPLATE_ASSEMBLY = 9  # swDefaultTemplateAssembly
_TEXT = 30  # swCustomInfoText


def build_project(
    app,
    project: Project,
    *,
    force: bool = False,
    only: Sequence[str] = (),
    progress: Callable[[str], None] | None = None,
) -> str:
    """Build what changed (or ``only`` those files, or everything with ``force``), then sync the assembly."""
    project.folder.mkdir(parents=True, exist_ok=True)
    items = project.items()
    check_name_clashes(app, project, items)

    def wanted(item: Item) -> bool:
        if only:
            return item.file in only
        return force or project.status(item) != BUILT

    todo = [item for item in items if wanted(item)]
    failed: list[str] = []
    if todo:
        _close(app, project.assembly_path, save=True)  # nothing below is edited while the assembly holds it
    for index, item in enumerate(todo, start=1):
        _say(progress, f"Building {index} of {len(todo)}: {item.label}")
        path = project.folder / item.file
        try:
            build_part(app, path, item)
            project.mark(item)
        except Exception as exc:  # one bad part must not stop the rest
            message = str(exc) if isinstance(exc, SolidWorksError) else format_com_error(exc)
            project.mark(item, message)
            failed.append(f"{item.file}: {message}")
        project.save()  # status lands on disk after every part
    _say(progress, "Updating the assembly...")
    added, removed = sync_assembly(app, project, items)
    project.save()
    note = (f"Built {len(todo) - len(failed)} of {len(todo)} part(s); assembly: {added} placed, "
            f"{removed} removed.")
    current = {item.file for item in items}
    unused = sorted(name for name in project.built if name not in current and (project.folder / name).exists())
    if unused:
        note += (f" {len(unused)} part file(s) in the folder are no longer used: "
                 + ", ".join(unused[:3]) + (", ..." if len(unused) > 3 else "") + ".")
    if failed:
        note += f" {len(failed)} failed — {failed[0]}"
    return note


def check_name_clashes(app, project: Project, items: Sequence[Item]) -> None:
    """Stop before anything is touched if a file of one of this project's names is open from elsewhere.

    SolidWorks holds one document per file name, so another project's "Shell C1 Plate A.SLDPRT"
    being open means this build would open, change and save that one instead.
    """
    ours = {item.file.lower(): project.folder / item.file for item in items}
    ours[project.assembly_path.name.lower()] = project.assembly_path
    doc = app.GetFirstDocument
    while doc is not None:
        path = str(com_value(doc.GetPathName) or "")
        mine = ours.get(os.path.basename(path).lower()) if path else None
        if mine is not None and not _same_file(path, str(mine)):
            raise SolidWorksError(
                f"{os.path.basename(path)} is open in SolidWorks from {os.path.dirname(path)}. SolidWorks holds "
                "one file of a name at a time, so this build would change that file instead. Close it (and any "
                "assembly that uses it), then build again."
            )
        doc = doc.GetNext


def build_part(app, path: Path, item: Item) -> str:
    """Build ``item`` into ``path``: the existing part opened and cleared, or a new part. Returns the title.

    The part must not be held by an open assembly (``build_project`` closes it first).
    """
    if path.exists():
        doc = _open(app, path, _DOC_PART)
        _activate(app, doc)
    else:
        doc = new_part(app)
    try:
        if path.exists():
            _clear(doc)
        if item.kind == SHELL_PLATE:
            _shell_plate(doc, item)
            for placed, mark in item.source or ():  # nozzles placed on this plate's own frame
                _cut_shell(doc, placed, _safe(mark))
        elif item.kind == TURNED:
            _turned(doc, item)
        elif item.kind == REPAD:
            placed, mark = item.source
            _learn_right_plane(doc)
            _repad(doc, placed, _safe(mark))
        elif item.kind == FTCO_PIECE:
            _ftco_piece(doc, item)
        else:
            raise SolidWorksError(f"{item.file}: no builder for {item.kind!r}.")
        bodies = doc.GetBodies2(0, False) or ()
        if len(bodies) != 1:
            raise SolidWorksError(f"{item.file}: built {len(bodies)} solids, not one.")
        _properties(doc, item)
        rebuild(doc)
        _save(doc, path)
        return str(com_value(doc.GetTitle) or path.name)
    finally:
        # Saved, or failed and left as it was on disk: either way the window goes, so nothing
        # is left loaded when the assembly opens it.
        with contextlib.suppress(Exception):
            app.CloseDoc(str(com_value(doc.GetTitle) or ""))


def _shell_plate(doc, item: Item) -> None:
    """The plate from azimuth 0 to its sweep, at its real height: placements only turn it."""
    p = item.params
    plate = PlateSector(
        course_no=int(p["course"]), plate_no=1, start_rad=0.0, sweep_rad=float(p["sweep_rad"]),
        z_bot_m=float(p["z_bot_m"]), height_m=float(p["height_m"]), outer_r_m=float(p["outer_r_m"]),
        inner_r_m=float(p["inner_r_m"]), length_in=float(p["length_in"]),
    )
    _ensure_axis_sketch(doc, plate.z_bot_m + plate.height_m)
    axis = _ensure_tank_axis(doc)
    warning = _build_one_plate(doc, plate, axis)
    _hide_construction_geometry(doc)
    _hide_sketch(doc, "EliteTankAxisSk")  # its line would show in the assembly
    bodies = doc.GetBodies2(0, False) or ()
    if len(bodies) != 1:
        raise SolidWorksError(f"{item.file}: the plate did not build ({warning or 'no solid'}).")


def _ftco_piece(doc, item: Item) -> None:
    """One FTCO piece, built facing +Z on the tank's own axis like the one-part build does it."""
    from swauto.cleanout import cleanout_sw

    upright, piece, r_mid, height, shell_outside = item.source
    _ensure_axis_sketch(doc, height * _INCH)
    axis = _ensure_tank_axis(doc)
    frame = cleanout_sw._Frame(phi=0.0, r_mid=r_mid, height=height)
    cleanout_sw.build_piece(doc, upright, piece, frame, shell_outside, axis)
    cleanout_sw.hide_planes(doc, cleanout_sw.tag_of(upright))
    _hide_construction_geometry(doc)
    _hide_sketch(doc, "EliteTankAxisSk")


def _turned(doc, item: Item) -> None:
    """A nozzle piece: its (z, radius) loop turned about the part's Z axis, then its bolt holes."""
    _learn_right_plane(doc)
    loop = [(float(z), float(r)) for z, r in item.params["loop"]]
    _revolve_loop(doc, loop, "EliteNozzlePiece", _FAR_IN)
    bolts = item.params.get("bolts")
    if bolts:
        _bolt_holes(doc, *bolts)


def _bolt_holes(doc, circle_in: float, count: float, hole_in: float, plane_z: float, depth_in: float) -> None:
    """The flange's bolt holes, sketched at ``plane_z`` and cut ``depth_in`` whichever way finds metal."""
    name = "EliteNozzleBolts"
    plane = _offset_front(doc, plane_z * _INCH, f"{name}Plane")
    _open_on(doc, plane)
    sketch = doc.SketchManager
    radius = hole_in / 2.0 * _INCH
    for x, y in bolt_centers(circle_in, int(count)):
        if not _drew(doc, lambda x=x, y=y: sketch.CreateCircleByRadius(x * _INCH, y * _INCH, 0.0, radius)):
            _close_sketch(doc)
            raise SolidWorksError("A bolt hole did not draw.")
    _close_sketch(doc)
    profile = _latest(doc)
    rename_feature(profile, f"{name}Sk")
    for flip in (False, True):  # a cut the wrong way finds no metal and comes back empty
        doc.ClearSelection2(True)
        if not profile.Select2(False, 0):
            raise SolidWorksError("Could not select the bolt holes.")
        cut = _cut(doc, depth_in * _INCH, flip=flip)
        if cut is not None:
            rename_feature(cut, name)
            _hide_nozzle_sketch(doc, f"{name}Sk")
            return
    raise SolidWorksError("The bolt holes did not cut the flange.")


def _hide_sketch(doc, name: str) -> None:
    from swauto.features import find_feature

    feature = find_feature(doc, name)
    if feature is None:
        return
    with contextlib.suppress(Exception):
        doc.ClearSelection2(True)
        feature.Select2(False, 0)
        doc.BlankSketch()
        doc.ClearSelection2(True)


def _clear(doc) -> None:
    """Everything the last build made (all of it is named Elite...); the part is built again from scratch."""
    from swauto.features import find_feature, iter_features

    names = [str(com_value(feature.Name) or "") for feature in iter_features(doc)]
    for name in reversed([name for name in names if name.startswith("Elite")]):
        feature = find_feature(doc, name)
        if feature is None:  # went with a feature deleted before it
            continue
        with contextlib.suppress(Exception):
            doc.ClearSelection2(True)
            feature.Select2(False, 0)
            doc.EditDelete()
    rebuild(doc)


def _properties(doc, item: Item) -> None:
    with contextlib.suppress(Exception):
        manager = doc.Extension.CustomPropertyManager("")
        for name, value in (("Description", item.label), (PROJECT_PART_PROPERTY, item.kind),
                            ("Elite fingerprint", item.fingerprint)):
            manager.Add2(name, _TEXT, value)
            manager.Set(name, value)


# ------------------------------------------------------------------ assembly


def sync_assembly(app, project: Project, items: Sequence[Item]) -> tuple[int, int]:
    """Make the assembly hold exactly the items' placements. Returns (placed, removed).

    Only components of this project's part files are touched; anything else in the
    assembly is left alone. A component whose transform no longer matches is removed
    and placed again: components are fixed, so there are no mates to lose.
    """
    path = project.assembly_path
    if path.exists():
        asm = _open(app, path, _DOC_ASSEMBLY)
    else:
        template = str(com_value(app.GetUserPreferenceStringValue(_TEMPLATE_ASSEMBLY)) or "")
        asm = app.NewDocument(template, 0, 0, 0) if template else None
        if asm is None:
            raise SolidWorksError("Could not start a new assembly. Set a default Assembly template in SolidWorks.")
    asm._FlagAsMethod("AddComponents3", "FixComponent", "GetComponents")
    ours = {item.file.lower() for item in items} | {name.lower() for name in project.built}
    wanted: list[tuple[str, list[float]]] = []
    for item in items:
        file = project.folder / item.file
        if file.exists():
            wanted.extend((str(file), placement.transform()) for placement in item.placements)

    stale = []
    for comp in asm.GetComponents(True) or ():
        file = str(com_value(comp.GetPathName) or "")
        if os.path.basename(file).lower() not in ours:
            continue
        transform = [float(v) for v in com_value(com_value(comp.Transform2).ArrayData)]
        match = next((i for i, (w_file, w_t) in enumerate(wanted)
                      if _same_file(w_file, file) and _same_transform(w_t, transform)), None)
        if match is None:
            stale.append(comp)
        else:
            wanted.pop(match)

    if stale:
        asm.ClearSelection2(True)
        for comp in stale:
            comp.Select4(True, com_nothing(), False)
        asm.EditDelete()
    if wanted:
        import pythoncom
        from win32com.client import VARIANT

        added = asm.AddComponents3(
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [file for file, _ in wanted]),
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [v for _, t in wanted for v in t]),
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [""] * len(wanted)),
        )
        if not added or len(added) != len(wanted):
            raise SolidWorksError(f"Only {len(added or ())} of {len(wanted)} parts went into the assembly.")
        # AddComponents3 turns a component but drops the move; the component's own
        # transform, set afterwards, takes both.
        for comp, (_file, transform) in zip(added, wanted, strict=True):
            placed = com_value(comp.Transform2)
            placed.ArrayData = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(transform))
            comp.Transform2 = placed
        rebuild(asm)
        asm.ClearSelection2(True)
        for comp in added:
            comp.Select4(True, com_nothing(), False)
        asm.FixComponent()
        asm.ClearSelection2(True)
    rebuild(asm)
    with contextlib.suppress(Exception):
        asm.ViewZoomtofit2()
    _save(asm, path)
    return len(wanted), len(stale)


def _same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _same_transform(a: Sequence[float], b: Sequence[float]) -> bool:
    return all(math.isclose(x, y, abs_tol=1e-6) for x, y in zip(a[:12], b[:12], strict=True))


# ------------------------------------------------------------------ documents


def _open(app, path: Path, kind: int):
    """The document for ``path``; SolidWorks hands back the loaded one if it is open already."""
    import pythoncom
    from win32com.client import VARIANT

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = app.OpenDoc6(str(path), kind, _OPEN_SILENT, "", errors, warnings)
    if doc is None:
        raise SolidWorksError(f"Could not open {path.name} (error {errors.value}).")
    return doc


def _activate(app, doc) -> None:
    """Make ``doc`` the active window: feature edits go through SolidWorks' interface."""
    import pythoncom
    from win32com.client import VARIANT

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    app.ActivateDoc3(str(com_value(doc.GetTitle) or ""), False, 1, errors)  # 1: don't rebuild on activation


def _close(app, path: Path, *, save: bool) -> None:
    """Close the document for ``path`` if SolidWorks has it open; save it first if asked."""
    doc = app.GetOpenDocumentByName(str(path))
    if doc is None:
        return
    if save:
        _save(doc, path)
    app.CloseDoc(str(com_value(doc.GetTitle) or path.name))


def _save(doc, path: Path) -> None:
    """Save to ``path``: Save As the first time, plain Save after."""
    current = str(com_value(doc.GetPathName) or "")
    if current and _same_file(current, str(path)):
        import pythoncom
        from win32com.client import VARIANT

        errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        if not doc.Save3(_SAVE_SILENT, errors, warnings):
            raise SolidWorksError(f"Could not save {path.name} (error {errors.value}).")
        return
    code = doc.SaveAs3(str(path), 0, _SAVE_SILENT)
    if code:
        raise SolidWorksError(f"Could not save {path.name} (error {code}); is a file of that name open?")


def _say(progress, text: str) -> None:
    if progress is not None:
        with contextlib.suppress(Exception):
            progress(text)
