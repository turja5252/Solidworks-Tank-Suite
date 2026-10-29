"""Build on shell finds the one-part shell: this run's, or the shell part open in SolidWorks."""

import pytest

from swauto.tank.open_shell import PROJECT_PART_PROPERTY, find_shell
from swauto.tank.shell import AXIS_NAME, LiveTank
from swauto.tank.spec import Course, TankSpec

PART, ASSEMBLY = 1, 2


class _Feature:
    def __init__(self, name, nxt=None):
        self.Name = name
        self.GetNextFeature = nxt


class _Properties:
    def __init__(self, names):
        self.GetNames = tuple(names)


class _Extension:
    def __init__(self, names):
        self._names = names

    def CustomPropertyManager(self, _config):  # noqa: N802 - SolidWorks' name
        return _Properties(self._names)


class _Doc:
    def __init__(self, title, kind=PART, features=(), properties=()):
        self.GetTitle = title
        self.GetType = kind
        first = None
        for name in reversed(features):
            first = _Feature(name, first)
        self.FirstFeature = first
        self.Extension = _Extension(properties)
        self.GetNext = None


class _Closed:
    @property
    def GetTitle(self):  # noqa: N802
        raise RuntimeError("The object invoked has disconnected from its clients.")


class _App:
    def __init__(self, docs, active=None):
        for a, b in zip(docs, docs[1:]):
            a.GetNext = b
        self.GetFirstDocument = docs[0] if docs else None
        self.ActiveDoc = active


def _shell(title="Part3"):
    return _Doc(title, features=("Front Plane", AXIS_NAME, "EliteTankC1P01"))


def _shared():
    return {"spec": TankSpec(diameter_in=607.0, diameter_basis="od", courses=[Course(96.0, 1.0)])}


def test_the_shell_made_in_this_run_is_used():
    shared = _shared()
    live = LiveTank("Part3", shared["spec"], _shell())
    shared["live"] = live
    assert find_shell(shared, _App([])) is live


def test_after_a_restart_the_open_shell_part_is_used():
    shared = _shared()
    shell = _shell()
    found = find_shell(shared, _App([_Doc("Sketchy"), shell], active=shell))
    assert found.model is shell and found.title == "Part3"
    assert shared["live"] is found  # remembered from now on
    # The same when the shell is open but another document is active.
    shared = _shared()
    other = _Doc("Notes", features=("Front Plane",))
    assert find_shell(shared, _App([other, shell], active=other)).model is shell


def test_a_closed_shell_is_forgotten_and_the_open_one_found():
    shared = _shared()
    shared["live"] = LiveTank("Part1", shared["spec"], _Closed())
    shell = _shell("Part9")
    assert find_shell(shared, _App([shell], active=shell)).title == "Part9"


def test_project_plate_parts_are_not_mistaken_for_the_shell():
    shared = _shared()
    plate = _Doc("Shell C1 Plate A.SLDPRT", features=(AXIS_NAME, "EliteTankC1P01"),
                 properties=("Description", PROJECT_PART_PROPERTY))
    with pytest.raises(ValueError, match="No tank shell"):
        find_shell(shared, _App([plate], active=plate))


def test_an_open_assembly_gets_its_own_explanation():
    shared = _shared()
    assembly = _Doc("Tank 101.SLDASM", kind=ASSEMBLY)
    with pytest.raises(ValueError, match="assembly"):
        find_shell(shared, _App([assembly], active=assembly))


def test_two_open_shells_need_one_picked():
    shared = _shared()
    a, b = _shell("Part3"), _shell("Part4")
    with pytest.raises(ValueError, match="More than one"):
        find_shell(shared, _App([a, b], active=None))
    assert find_shell(shared, _App([a, b], active=b)).model is b


def test_no_tank_means_tank_properties_first():
    with pytest.raises(ValueError, match="Tank Properties"):
        find_shell({}, _App([]))


def test_a_project_built_as_parts_says_nozzles_are_not_there_yet(tmp_path):
    from swauto.project.project import Project

    shared = _shared()
    project = Project(folder=tmp_path, name="Tank 101", spec=shared["spec"])
    project.assembly_path.write_bytes(b"assembly")
    shared["project"] = project
    with pytest.raises(ValueError, match="built as parts, in Tank 101.SLDASM"):
        find_shell(shared, _App([]))
    # An open one-part shell still wins: the preview works alongside the project.
    shell = _shell()
    assert find_shell(shared, _App([shell], active=shell)).model is shell
