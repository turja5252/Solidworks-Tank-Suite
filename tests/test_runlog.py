"""The run log: status lines, message boxes with the error they report, inputs, and the project's copy."""

import datetime
import sys
import tkinter as tk
from tkinter import messagebox

import pytest

from swauto import runlog


@pytest.fixture
def shown(monkeypatch):
    """Message boxes recorded instead of shown; the log and the hooks put back after."""
    boxes = []
    for name in ("showerror", "showwarning", "showinfo", "askyesno"):
        monkeypatch.setattr(
            messagebox, name,
            lambda title=None, message=None, _name=name, **_options: boxes.append((_name, title, message)) or True,
        )
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    yield boxes
    for handler in list(runlog.LOG.handlers):
        runlog.LOG.removeHandler(handler)
        handler.close()
    runlog._project["handler"] = None


def test_status_lines_and_message_boxes_go_in_the_days_log(shown, tk_window, tmp_path):
    status = tk.StringVar(master=tk_window)
    path = runlog.start(tk_window, status, tmp_path)
    assert path == tmp_path / f"{datetime.date.today():%Y-%m-%d}.log"
    status.set("50% — tread 3")
    try:
        raise ValueError("Use 2 to 80 treads.")
    except ValueError:
        messagebox.showerror("Stair", "Use 2 to 80 treads.")
    text = path.read_text(encoding="utf-8")
    assert "Elite SW Auto started" in text
    assert "Status: 50% — tread 3" in text
    assert "Message box (showerror) Stair: Use 2 to 80 treads." in text
    assert "Traceback" in text and "ValueError: Use 2 to 80 treads." in text  # the error behind the box
    assert shown == [("showerror", "Stair", "Use 2 to 80 treads.")]  # and the box still shows


def test_an_open_project_gets_the_log_in_its_folder(shown, tk_window, tmp_path):
    runlog.start(tk_window, tk.StringVar(master=tk_window), tmp_path / "logs")
    job = tmp_path / "job"
    job.mkdir()
    runlog.use_project(job, "Tank 12")
    runlog.inputs("Create stair", {"treads": "64", "climbs": "cw"})
    text = (job / "Tank 12.log").read_text(encoding="utf-8")
    assert "Create stair with treads='64', climbs='cw'" in text


def test_an_error_a_button_lets_slip_is_logged_and_shown(shown, tk_window, tmp_path):
    path = runlog.start(tk_window, tk.StringVar(master=tk_window), tmp_path)
    try:
        raise KeyError("diameter")
    except KeyError as exc:
        tk_window.report_callback_exception(KeyError, exc, exc.__traceback__)
    text = path.read_text(encoding="utf-8")
    assert "Unhandled error" in text and "KeyError: 'diameter'" in text
    assert shown[-1][0] == "showerror"


def test_the_log_names_the_code_it_ran():
    assert runlog.code_version()
