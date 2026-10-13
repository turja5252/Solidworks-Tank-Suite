from swauto.comutil import com_value
from swauto.errors import SolidWorksNotRunning, SolidWorksUnavailable
from swauto.report import DocumentInfo, read_document

PROGID = "SldWorks.Application"


class Session:
    """A live SolidWorks application in this Windows session."""

    def __init__(self, app, *, started: bool) -> None:
        self.app = app
        self.started = started

    def revision(self) -> str:
        # SolidWorks 2013 exposes RevisionNumber as a COM property (a string).
        return str(com_value(self.app.RevisionNumber))

    def active_document(self) -> DocumentInfo | None:
        # ActiveDoc is a COM property. The Dispatch object is callable, so do not wrap it.
        return read_document(self.app.ActiveDoc)



def connect(
    *,
    start: bool = False,
    visible: bool = True,
    client=None,
    com_error: type[BaseException] | None = None,
) -> Session:
    """Attach to SolidWorks on this computer.

    SolidWorks exposes its API only in the Windows session where it is open.
    Run this on the Solidworks computer, inside the Remote Desktop session.
    """
    if client is None or com_error is None:
        try:
            import pythoncom
            import win32com.client as win32_client
        except ImportError as exc:
            raise SolidWorksUnavailable(
                "pywin32 is not installed on this computer. Run: python -m pip install pywin32"
            ) from exc
        if client is None:
            client = win32_client
        if com_error is None:
            com_error = pythoncom.com_error

    started = False
    try:
        app = client.GetActiveObject(PROGID)
    except com_error:
        if not start:
            raise SolidWorksNotRunning(
                "SolidWorks is not running in this Windows session. "
                "On the Solidworks computer, open SolidWorks, then run this again."
            ) from None
        try:
            app = client.Dispatch(PROGID)
        except com_error as exc:
            raise SolidWorksUnavailable(
                "SolidWorks is not installed on this computer. "
                "Run this inside the Remote Desktop session on the computer named Solidworks."
            ) from exc
        started = True

    if visible:
        app.Visible = True
    return Session(app, started=started)
