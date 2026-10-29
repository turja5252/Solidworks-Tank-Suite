"""Shared test fixtures."""

import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def _tk():
    """One Tk for the whole run.

    Starting and destroying many Tk interpreters in one process now and then fails on
    this Python while Tk loads its library (TclError: invalid command name
    "tcl_findLibrary"). The app only ever starts one, so the tests do too.
    """
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def tk_window(_tk):
    """A hidden window of its own for one test, under the shared Tk."""
    window = tk.Toplevel(_tk)
    window.withdraw()
    yield window
    window.destroy()
