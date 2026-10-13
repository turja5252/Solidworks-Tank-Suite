from swauto.comutil import com_nothing, com_value, format_com_error


def test_com_value_returns_plain_values():
    assert com_value("21.5.0") == "21.5.0"
    assert com_value(None) is None


def test_com_value_calls_callables():
    assert com_value(lambda: "21.5.0") == "21.5.0"


class com_error(Exception):
    """Stand-in for pywintypes.com_error."""


def test_com_value_keeps_dispatch_objects_that_fail_when_called():
    class FakeDispatch:
        def __call__(self):
            raise com_error(-2147352573, "Member not found.", None, None)

    doc = FakeDispatch()
    assert com_value(doc) is doc


def test_format_com_error():
    assert format_com_error(com_error(-2147352571, "Type mismatch.", None, 8)) == (
        "-2147352571: Type mismatch."
    )


def test_com_nothing_without_pywin32(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"pythoncom", "win32com", "win32com.client"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert com_nothing() is None
