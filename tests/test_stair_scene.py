"""The 3D preview: the scene's faces sit where the build puts things, and the camera draws them back to front."""

import math

from swauto.stair.attachments import INNER, OUTER, Rules, plan, shell_from
from swauto.stair.landings import StairArrangement
from swauto.stair.scene import CLIP_COLOR, POST_COLOR, SHELL, TREAD, Face, Rails, scene
from swauto.stair.splitter import SplitSettings
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import THICKNESS_IN, StringerMock
from swauto.stretchout.model import x_of_angle
from swauto.stretchout.view3d_gui import project
from swauto.tank.spec import Course, TankSpec

STAIR = StringerMock(treads=16)


def _radius(point) -> float:
    return math.hypot(point[0], point[2])


def test_every_tread_and_the_shell_are_where_the_build_puts_them():
    arrangement = StairArrangement(STAIR)
    faces = scene(arrangement)
    where = stair_places(STAIR, STAIR.shell_od_in)
    treads = [f for f in faces if f.color == TREAD]
    assert {f.label for f in treads} == {f"Tread {i}" for i in range(1, 17)}
    for face in (f for f in treads if f.label == "Tread 5"):
        place = where.places[4]
        assert all(place.y0 - 1e-6 <= p[1] <= place.y1 + 1e-6 for p in face.points)
        assert all(where.layout.inner_face_in - 1e-6 <= _radius(p) <= where.layout.inner_face_in
                   + where.layout.clear_in + 1e-6 for p in face.points)
    assert all(abs(_radius(p) - STAIR.shell_od_in) < 1e-6 for f in faces if f.color == SHELL for p in f.points)


def test_the_stair_turns_and_mirrors_with_its_arrangement():
    plain = scene(StairArrangement(STAIR))
    turned = scene(StairArrangement(STAIR, turn=math.radians(90.0)))
    mirrored = scene(StairArrangement(STAIR, ccw=True))
    a, b, c = plain[0].points[0], turned[0].points[0], mirrored[0].points[0]
    turn = math.atan2(-b[0], b[2]) - math.atan2(-a[0], a[2])  # angles the nozzles' way, 0 toward +Z
    assert math.isclose(math.remainder(turn - math.radians(90.0), 2 * math.pi), 0.0, abs_tol=1e-9)
    assert math.isclose(c[0], -a[0]) and math.isclose(c[2], a[2])


def test_the_plan_adds_posts_on_both_sides_and_the_clips():
    arrangement = StairArrangement(STAIR, splits=SplitSettings())
    result = plan(arrangement, rules=Rules(sides=(OUTER, INNER)))
    faces = scene(arrangement, result)
    posts = {f.label for f in faces if f.color == POST_COLOR}
    assert any(label.startswith("Outer post") for label in posts) and any(label.startswith("Inner post")
                                                                          for label in posts)
    assert any(f.color == CLIP_COLOR for f in faces)


def test_the_camera_draws_far_faces_first():
    faces = scene(StairArrangement(STAIR))
    view = {"center": (0.0, 60.0, 130.0), "size": 200.0, "yaw": 0.3, "pitch": 0.2, "zoom": 1.0, "pan": (0.0, 0.0)}
    drawn = project(faces, view, 800, 600)
    depths = [d for d, *_rest in drawn]
    assert drawn and depths == sorted(depths, reverse=True)
    assert all(len(points) % 2 == 0 and len(points) >= 6 for _d, points, _c, _l, _w in drawn)


def _view(center=(0.0, 0.0, 0.0), yaw=0.0, pitch=0.0) -> dict:
    return {"center": center, "size": 200.0, "yaw": yaw, "pitch": pitch, "zoom": 1.0, "pan": (0.0, 0.0)}


def _square(x: float, y: float, z: float, label: str) -> Face:
    """A small level square about (x, y, z)."""
    return Face(((x - 5, y, z - 5), (x + 5, y, z - 5), (x + 5, y, z + 5), (x - 5, y, z + 5)), "#888888", label)


def _middles(drawn) -> dict:
    return {label: (sum(p[0::2]) / len(p[0::2]), sum(p[1::2]) / len(p[1::2])) for _d, p, _c, label, _w in drawn}


def test_the_camera_sees_the_frame_as_solidworks_does_and_looks_down():
    # From the front (the camera out on +Z), +X is on the right; a positive pitch looks down, so the near side of
    # a level floor is lower on the screen than the far side.
    seen = _middles(project([_square(45.0, 0.0, 0.0, "+x")], _view(yaw=math.pi), 800, 600))
    assert seen["+x"][0] > 400
    seen = _middles(project([_square(0.0, 0.0, -50.0, "near"), _square(0.0, 0.0, 50.0, "far")],
                            _view(pitch=0.3), 800, 600))
    assert seen["near"][1] > seen["far"][1]


def test_seen_from_outside_a_clockwise_stair_climbs_to_the_left():
    treads = [f for f in scene(StairArrangement(STAIR)) if f.color == TREAD]
    points = [p for f in treads for p in f.points]
    center = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
    outside = math.pi + math.atan2(center[0], center[2])  # the view's own square-on yaw
    seen = _middles(project(treads, _view(center, yaw=outside, pitch=0.2), 800, 600))
    assert seen["Tread 1"][0] > seen["Tread 16"][0]


def test_the_handrail_is_drawn_as_the_stairway_tab_asks():
    arrangement = StairArrangement(STAIR, splits=SplitSettings())
    result = plan(arrangement, rules=Rules(sides=(OUTER, INNER)))
    faces = scene(arrangement, result)
    names = {f.label.split(",")[0] for f in faces}
    # Inside is the full guardrail by default, as outside (the user, 2026-10-30).
    assert {"Outer top rail", "Outer midrail", "Grab rail", "Inside top rail", "Inside midrail"} <= names
    assert "Inside pipe" not in names and "Inside grab rail" not in names
    layout = stair_places(STAIR, STAIR.shell_od_in).layout
    r_a, r_b = layout.inner_face_in, layout.inner_face_in + layout.clear_in
    piped = scene(arrangement, result, rails=Rails(inner_full=False))
    both = scene(arrangement, result, rails=Rails(inner_grab=True))
    # The pipes are over the treads, on their PC #34s: between the stringers.
    for name, drawn in (("Grab rail", faces), ("Inside pipe", piped), ("Inside grab rail", both)):
        radii = [_radius(p) for f in drawn if f.label.startswith(name) for p in f.points]
        assert radii and r_a < min(radii) and max(radii) < r_b, name
    # The inside rails stand off the inner stringer's tank face, toward the shell.
    radii = [_radius(p) for f in faces if f.label.startswith("Inside top rail") for p in f.points]
    assert max(radii) <= r_a - THICKNESS_IN + 1e-6
    fewer = {f.label.split(",")[0] for f in scene(arrangement, result, rails=Rails(mid=False, grab=False,
                                                                                  inner_full=False))}
    assert "Outer midrail" not in fewer and "Grab rail" not in fewer
    assert {"Outer top rail", "Inside pipe"} <= fewer


def test_the_shell_is_cut_at_its_weld_seams():
    tank = TankSpec(diameter_in=2.0 * STAIR.shell_od_in, diameter_basis="od", courses=[Course(96.0, 0.5)] * 3)
    shell = shell_from(tank)
    arrangement = StairArrangement(STAIR, turn=math.radians(40.0))
    faces = [f for f in scene(arrangement, shell=shell) if f.color == SHELL]
    welds = [(f.points[i], f.points[j]) for f in faces for i, j in f.welds]
    levels = {round(a[1], 6) for a, b in welds if abs(a[1] - b[1]) < 1e-9}
    assert levels == {0.0, 96.0, 192.0}  # the floor weld and the two course seams
    plumb = [a for a, b in welds if abs(a[1] - b[1]) > 1e-9]
    assert plumb  # the stair passes plate seams
    seams = [seam.x0 for seam in shell.seams if seam.vertical]
    for point in plumb:
        x = x_of_angle(math.atan2(-point[0], point[2]), shell.girth_in) % shell.girth_in
        assert min(min(abs(x - s), shell.girth_in - abs(x - s)) for s in seams) < 1e-6
