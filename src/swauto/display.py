"""SolidWorks display throttling — keep animation, spend time on modeling not redraws."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextlib import contextmanager


def set_display_live(model, live: bool) -> None:
    """When ``live`` is False, SolidWorks skips view/feature-tree paints between features.

    The COM calls still run (and use the SW process harder). Turn live back on
    and redraw when you want the user to see a step of the animation.
    """
    with contextlib.suppress(Exception):
        view = model.ActiveView
        if view is not None:
            view.EnableGraphicsUpdate = bool(live)
    feature_manager = getattr(model, "FeatureManager", None)
    if feature_manager is not None:
        with contextlib.suppress(Exception):
            feature_manager.EnableFeatureTree = bool(live)
        with contextlib.suppress(Exception):
            feature_manager.EnableFeatureTreeWindow = bool(live)


def redraw(model) -> None:
    """Force a paint after a burst of feature work."""
    set_display_live(model, True)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()
    with contextlib.suppress(Exception):
        model.WindowRedraw()


@contextmanager
def display_frozen(model) -> Iterator[None]:
    """Freeze paints for the duration of the block, then restore and redraw."""
    set_display_live(model, False)
    try:
        yield
    finally:
        redraw(model)
