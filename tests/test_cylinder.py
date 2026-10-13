import pytest

from swauto.cylinder import create_cylinder
from swauto.errors import SolidWorksError


class FakeSegment:
    def __init__(self):
        self.radius = None

    def GetType(self):
        return 1

    def SetRadius(self, radius):
        self.radius = radius


class FakeSketch:
    def __init__(self, segment):
        self._segment = segment

    def GetSketchSegments(self):
        return [self._segment]


class FakeFeature:
    def __init__(self, name="Feature", *, kind="sketch"):
        self._name = name
        self.kind = kind
        self.selected = False
        self.definition = FakeExtrudeDefinition() if kind == "extrude" else None

    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, value):
        self._name = value

    def Select2(self, append, mark):
        self.selected = True
        return True

    def GetDefinition(self):
        return self.definition

    def ModifyDefinition(self, definition, model, nothing):
        self.definition = definition
        return True

    def GetNextFeature(self):
        return None


class FakeExtrudeDefinition:
    def __init__(self):
        self.depth = None
        self.accessed = False

    def AccessSelections(self, model, nothing):
        self.accessed = True
        return True

    def SetDepth(self, forward, depth):
        self.depth = depth


class FakeSketchManager:
    def __init__(self, model):
        self.model = model
        self.radius = None

    def InsertSketch(self, update_edit):
        self.model.editing_sketch = False

    def CreateCircleByRadius(self, x, y, z, radius):
        self.radius = radius
        self.model.segment = FakeSegment()
        self.model.segment.radius = radius
        return self.model.segment


class FakeExtension:
    def SelectByID2(self, name, type_name, *_args):
        return name in {"Front Plane", "Plane1", "Front"} and type_name == "PLANE"


class FakeFeatureManager:
    def __init__(self, model):
        self.model = model
        self.depth = None
        self.arg_count = None

    def FeatureExtrusion2(self, *args):
        if len(args) not in {20, 23}:
            raise TypeError("wrong argument count")
        self.arg_count = len(args)
        self.depth = args[5]
        feat = FakeFeature("Boss-Extrude1", kind="extrude")
        self.model.features.insert(0, feat)
        return feat


class FakeModel:
    def __init__(self):
        self.Extension = FakeExtension()
        self.SketchManager = FakeSketchManager(self)
        self.FeatureManager = FakeFeatureManager(self)
        self.features: list[FakeFeature] = []
        self.segment = None
        self.editing_sketch = False
        self.zoomed = False
        self.rebuilt = False

    def ClearSelection2(self, flag):
        return None

    def FeatureByPositionReverse(self, index):
        if index == 0 and not any(f.kind == "sketch" for f in self.features):
            sketch = FakeFeature("Sketch1", kind="sketch")
            self.features.append(sketch)
            return sketch
        return self.features[index]

    def FirstFeature(self):
        return self.features[0] if self.features else None

    def GetNextFeature(self):
        return None

    def ViewZoomtofit2(self):
        self.zoomed = True

    def GetTitle(self):
        return "Part1"

    def EditSketch(self):
        self.editing_sketch = True

    def GetActiveSketch2(self):
        return FakeSketch(self.segment)

    def EditRebuild3(self):
        self.rebuilt = True


# Patch GetNextFeature chaining for find_feature
def _wire_feature_links(model: FakeModel) -> None:
    for i, feat in enumerate(model.features):
        next_feat = model.features[i + 1] if i + 1 < len(model.features) else None

        def _next(current_next=next_feat):
            return current_next

        feat.GetNextFeature = _next  # type: ignore[method-assign]


class FakeApp:
    def __init__(self, template=r"C:\Templates\Part.prtdot"):
        self.template = template
        self.model = FakeModel()

    def GetUserPreferenceStringValue(self, pref):
        return self.template

    def NewDocument(self, template, *_args):
        return self.model

    @property
    def ActiveDoc(self):
        return self.model


def test_create_cylinder_inches(monkeypatch):
    app = FakeApp()
    monkeypatch.setattr("swauto.parts.Path.is_file", lambda self: str(self) == app.template)
    result = create_cylinder(app, diameter=10, height=20, unit="in")
    _wire_feature_links(app.model)
    assert result.title == "Part1"
    assert result.live.sketch_feature == "EliteCylSketch"
    assert result.live.extrude_feature == "EliteCylExtrude"
    assert app.model.SketchManager.radius == pytest.approx(0.127)
    assert app.model.FeatureManager.depth == pytest.approx(0.508)


def test_live_update_edits_sketch_and_extrude(monkeypatch):
    app = FakeApp()
    monkeypatch.setattr("swauto.parts.Path.is_file", lambda self: str(self) == app.template)
    result = create_cylinder(app, diameter=10, height=20, unit="in")
    _wire_feature_links(app.model)
    # find_feature walks FirstFeature -> GetNextFeature; extrude is index 0, sketch next.
    extrude = app.model.features[0]
    sketch = app.model.features[1]
    extrude.GetNextFeature = lambda: sketch  # type: ignore[method-assign]
    sketch.GetNextFeature = lambda: None  # type: ignore[method-assign]
    app.model.FirstFeature = lambda: extrude  # type: ignore[method-assign]

    result.live.update(app, diameter=12, height=36, unit="in")
    assert app.model.segment.radius == pytest.approx(0.1524)
    assert extrude.definition.depth == pytest.approx(0.9144)
    assert app.model.rebuilt is True


def test_create_cylinder_requires_existing_template(monkeypatch):
    app = FakeApp(template=r"C:\missing\Part.prtdot")
    monkeypatch.setattr("swauto.parts.Path.is_file", lambda self: False)
    monkeypatch.setattr("swauto.parts.candidate_part_templates", lambda: [])
    with pytest.raises(SolidWorksError, match="no usable Part template"):
        create_cylinder(app, diameter=1, height=1, unit="in")
