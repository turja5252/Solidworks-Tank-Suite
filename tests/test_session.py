import pytest

from swauto.errors import SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import PROGID, connect


class ComError(Exception):
    pass


class FakeApp:
    """Mirrors SolidWorks 2013 late binding: RevisionNumber is a string property."""

    def __init__(self, revision="32.5.0", doc=None):
        self.Visible = False
        self.RevisionNumber = revision
        self.ActiveDoc = doc


class FakeAppMethodRevision:
    def __init__(self, revision="32.5.0"):
        self.Visible = False
        self._revision = revision
        self.ActiveDoc = None

    def RevisionNumber(self):
        return self._revision


class FakeClient:
    def __init__(self, *, active=None, dispatch=None, fail_active=False, fail_dispatch=False):
        self.active = active
        self.dispatch = dispatch
        self.fail_active = fail_active
        self.fail_dispatch = fail_dispatch
        self.requested = []

    def GetActiveObject(self, progid):
        self.requested.append(("active", progid))
        if self.fail_active:
            raise ComError(progid)
        return self.active

    def Dispatch(self, progid):
        self.requested.append(("dispatch", progid))
        if self.fail_dispatch:
            raise ComError(progid)
        return self.dispatch


def test_connect_attaches_to_running_solidworks():
    app = FakeApp()
    client = FakeClient(active=app)
    session = connect(client=client, com_error=ComError)
    assert session.app is app
    assert session.started is False
    assert session.revision() == "32.5.0"
    assert app.Visible is True
    assert client.requested == [("active", PROGID)]


def test_connect_refuses_to_start_unless_asked():
    client = FakeClient(fail_active=True, dispatch=FakeApp())
    with pytest.raises(SolidWorksNotRunning):
        connect(client=client, com_error=ComError)
    assert client.requested == [("active", PROGID)]


def test_connect_can_start_solidworks():
    app = FakeApp(revision="34.2.0")
    client = FakeClient(fail_active=True, dispatch=app)
    session = connect(start=True, client=client, com_error=ComError)
    assert session.started is True
    assert session.revision() == "34.2.0"


def test_connect_reports_when_solidworks_is_missing():
    client = FakeClient(fail_active=True, fail_dispatch=True)
    with pytest.raises(SolidWorksUnavailable):
        connect(start=True, client=client, com_error=ComError)


def test_revision_accepts_method_style_binding():
    app = FakeAppMethodRevision(revision="21.5.0")
    client = FakeClient(active=app)
    session = connect(client=client, com_error=ComError)
    assert session.revision() == "21.5.0"
