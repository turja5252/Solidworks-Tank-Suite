"""The run log: everything a run of the app shows, with the error behind each failure.

One file a day in ``logs`` beside the app (``logs/2026-10-28.log``) and, while a project is
open, the same lines in ``<project name>.log`` in the project's folder. Every status line,
every message box (with the traceback of the error it reports, when there is one), every
error a button lets slip, and the inputs of each build go in, so a failed run can be read
back afterwards.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import platform
import sys
import traceback
from pathlib import Path

LOG = logging.getLogger("swauto")
APP_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = APP_DIR / "logs"
_FORMAT = "%(asctime)s  %(levelname)-7s  %(message)s"
_BOXES = {
    "showerror": logging.ERROR,
    "showwarning": logging.WARNING,
    "showinfo": logging.INFO,
    "askyesno": logging.INFO,
    "askyesnocancel": logging.INFO,
    "askokcancel": logging.INFO,
    "askquestion": logging.INFO,
    "askretrycancel": logging.INFO,
}
_project: dict[str, logging.Handler | None] = {"handler": None}


def start(root, status_var, log_dir: Path | None = None) -> Path:
    """Open today's log and send the app's status line, message boxes and loose errors into it."""
    folder = LOG_DIR if log_dir is None else Path(log_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.date.today():%Y-%m-%d}.log"
    _add_file(path)
    LOG.setLevel(logging.INFO)
    LOG.info("Elite SW Auto started: Python %s, code %s", platform.python_version(), code_version())
    status_var.trace_add("write", lambda *_args: LOG.info("Status: %s", status_var.get()))
    log_message_boxes()
    root.report_callback_exception = _callback_error
    previous = sys.excepthook

    def hook(exc_type, value, tb) -> None:
        LOG.critical("Error:\n%s", _trace(exc_type, value, tb))
        previous(exc_type, value, tb)

    sys.excepthook = hook
    return path


def use_project(folder, name: str) -> None:
    """Write the log into the open project's folder too, as ``<name>.log``. A later project takes its place."""
    target = (Path(folder) / f"{name}.log").resolve()
    old = _project["handler"]
    if old is not None and getattr(old, "baseFilename", "") == str(target):
        return
    if old is not None:
        LOG.removeHandler(old)
        old.close()
        _project["handler"] = None
    try:
        _project["handler"] = _add_file(target)
    except OSError as exc:
        LOG.warning("Could not write the log into the project folder %s: %s", folder, exc)
        return
    LOG.info("Project %s is open; this log is also in %s", name, target)


def inputs(what: str, values: dict) -> None:
    """One line with everything a build was given, to repeat it."""
    LOG.info("%s with %s", what, ", ".join(f"{key}={value!r}" for key, value in values.items()))


def log_message_boxes() -> None:
    """Log every message box as it is shown, and what was answered. Called inside an ``except``, a box also
    logs the error it reports, with its traceback: the tabs show errors that way."""
    from tkinter import messagebox

    for name, level in _BOXES.items():
        shown = getattr(messagebox, name, None)
        if shown is None or getattr(shown, "_logged", False):
            continue
        setattr(messagebox, name, _logged_box(shown, name, level))


def code_version() -> str:
    """The git commit the app runs from, read from .git; "unknown" if it cannot be read."""
    try:
        head = (APP_DIR / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            ref_file = APP_DIR / ".git" / ref
            if ref_file.exists():
                return f"{ref.rsplit('/', 1)[-1]} {ref_file.read_text(encoding='utf-8').strip()[:7]}"
            packed = (APP_DIR / ".git" / "packed-refs").read_text(encoding="utf-8")
            for line in packed.splitlines():
                if line.endswith(f" {ref}"):
                    return f"{ref.rsplit('/', 1)[-1]} {line[:7]}"
        return head[:7]
    except OSError:
        return "unknown"


def _add_file(path: Path) -> logging.Handler:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    LOG.addHandler(handler)
    return handler


def _logged_box(shown, name: str, level: int):
    def box(title=None, message=None, **options):
        handling = sys.exc_info()[1]
        LOG.log(level, "Message box (%s) %s: %s", name, title, message)
        if handling is not None:
            LOG.log(level, "It reports:\n%s", _trace(type(handling), handling, handling.__traceback__))
        answer = shown(title, message, **options)
        if name.startswith("ask"):
            LOG.info("Answered: %r", answer)
        return answer

    box._logged = True
    return box


def _callback_error(exc_type, value, tb) -> None:
    """An error a button let slip: into the log, and in front of the user (under pythonw it would go nowhere)."""
    LOG.error("Unhandled error:\n%s", _trace(exc_type, value, tb))
    from tkinter import messagebox

    with contextlib.suppress(Exception):
        messagebox.showerror(
            "Elite SW Auto", f"{exc_type.__name__}: {value}\n\nThe details are in the log, in {LOG_DIR}."
        )


def _trace(exc_type, value, tb) -> str:
    return "".join(traceback.format_exception(exc_type, value, tb)).rstrip()
