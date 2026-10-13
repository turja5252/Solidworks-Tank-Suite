"""Helpers for SolidWorks COM, where some members are properties and some are methods."""

from __future__ import annotations


def com_value(value):
    """Return a COM property value, or call a method when late binding needs it.

    win32com Dispatch objects are callable even when they are already the value
    (for example ActiveDoc). Calling those raises com_error; keep the object.
    """
    if not callable(value):
        return value
    try:
        return value()
    except Exception as exc:
        if type(exc).__name__ == "com_error":
            return value
        raise


def com_nothing():
    """COM Nothing for optional IDispatch arguments (SelectByID2 Callout, etc.)."""
    try:
        import pythoncom
        from win32com.client import VARIANT
    except ImportError:
        return None
    return VARIANT(pythoncom.VT_DISPATCH, None)


def format_com_error(exc: BaseException) -> str:
    args = getattr(exc, "args", ())
    if args:
        return f"{args[0]}: {args[1]}" if len(args) > 1 else str(args[0])
    return str(exc)
