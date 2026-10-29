"""Tabs that take a value from Tank Properties keep it in step, unless it was typed over."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from swauto.tank.spec import TankSpec


def follow_tank(
    page: ttk.Frame,
    holder: dict | None,
    variables: Sequence[tk.Variable],
    values: Callable[[TankSpec], Sequence[str]],
) -> Callable[..., None]:
    """Set ``variables`` to the tank's values each time ``page``'s tab is shown.

    ``values(spec)`` gives the text each variable should hold for the tank on Tank
    Properties. A variable still at its default, or at what it was last filled with,
    follows the tank; one that was typed over is someone's own number (a floor wider
    than the shell, say) and is left alone. Returns the sync function.
    """
    filled = {str(var): var.get() for var in variables}

    def sync(_event=None) -> None:
        book = page.master
        if isinstance(book, ttk.Notebook) and book.select() != str(page):
            return
        spec = (holder or {}).get("spec")
        if not isinstance(spec, TankSpec) or not spec.active_courses():
            return
        try:
            wanted = list(values(spec))
        except (ValueError, ZeroDivisionError, IndexError):
            return
        for var, text in zip(variables, wanted, strict=True):
            if var.get() == filled[str(var)]:
                if var.get() != text:
                    var.set(text)
                filled[str(var)] = text

    book = page.master
    if isinstance(book, ttk.Notebook):
        book.bind("<<NotebookTabChanged>>", sync, add="+")
    return sync
