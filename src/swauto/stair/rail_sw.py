"""Outer top rail: a helical L2x2x1/4 along each flight, the level and end pieces where it
meets a platform, and each platform's own rail.

From SpiralStairHandrail.lsp (HR_TOPMID), SpiralStairHandrailWrap.lsp, Stair Platform
Streatchout.lsp and Stair Platform Top View.lsp. The top edge is 42 in above the stringer's
top edge on the stair and 42 in above the grating on a platform. One leg is on top, reaching
out over the post tops; the other hangs on the walk side against the posts' flat legs. On the
stair the section is square to the slope and the angle is rolled to a helix.

Where a flight meets a platform the helix is mitered to a short level piece at the front edge
of the flight's tread that is level with the platform. The level piece runs to a vertical
L2x2 standing back to back with the platform post's outstanding leg, from the platform
midrail's bottom up under the rail, bolted to the post with two 13/16 bolts 11-1/2 in apart.
The platform's rail is its own piece between its two posts. The bottom flight starts one
tread run below its first tread, where the stringer's top edge comes down to tread zero, as
the lisp's automatic lower overhang does.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from swauto.comutil import com_nothing, com_value
from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import (
    BraceResult,
    _body_points,
    _end_face,
    _face_at,
    _knee_fits,
    _new_body,
    _progress,
    _set_turn,
    _turn_off,
)
from swauto.stair.inner_clip_sw import _member
from swauto.stair.platform_sw import _cut, _radial, _travel, _upright_angle, _world, platform_lines
from swauto.stair.post_sw import HOLE_DIA_IN, HOLE_GAUGE_IN, LEG_IN, PLATFORM_POST_IN, RAIL_TOP_IN, THK_IN
from swauto.stair.stringer import THICKNESS_IN, TREAD_DEPTH_IN
from swauto.stair.stringer_sw import _create_circle, _names, _rename_new, _select_feature
from swauto.tank.shell import _clear_selection, _close_sketch, _open_sketch

_INCH = 0.0254
OVERHANG_IN = 3.0  # past a miter, cut back after
BAR_IN = 2.0  # midrail flat bar, 2 x 1/4
BAR_THK_IN = 0.25
MID_TOP_IN = RAIL_TOP_IN / 2.0  # the lisp's automatic midrail: top edge halfway up to the top rail's
PLATFORM_MID_TOP_IN = 24.0  # the lisp's default over the grating; the end pieces come down to its bottom
END_BOLT_SPACE_IN = 11.5  # centered on the end piece
END_BOLT_EDGE_IN = 1.0  # end piece past each bolt, at the least
WELD_GAP_IN = 0.25  # a level flat bar stops this short of the end piece's edge
# Outlines from the top outer corner, as (out, up); up is stretched by 1/cos of the slope on a flight.
ANGLE_SECTION = (
    (-THK_IN, 0.0), (LEG_IN - THK_IN, 0.0), (LEG_IN - THK_IN, -THK_IN), (0.0, -THK_IN), (0.0, -LEG_IN), (-THK_IN, -LEG_IN),
)
BAR_SECTION = ((-BAR_THK_IN, 0.0), (0.0, 0.0), (0.0, -BAR_IN), (-BAR_THK_IN, -BAR_IN))


@dataclass(frozen=True)
class _Flight:
    first: object  # TreadPlace
    last: object
    rise_per_rad: float
    step: float
    r_b: float

    def front(self, place) -> float:
        """Angle of a tread's front edge on the outer stringer, where the lisp develops it."""
        return place.phi - TREAD_DEPTH_IN / 2.0 / self.r_b

    def top(self, phi: float) -> float:
        """Rail top: 42 in over the stringer's top edge, which runs through every tread's top front corner."""
        return self.first.y1 + (phi - self.front(self.first)) * self.rise_per_rad + RAIL_TOP_IN

    def tangent(self, phi: float, radius: float) -> tuple[float, float, float]:
        """Up the stair along the rail at ``radius``."""
        alpha = math.atan(self.rise_per_rad / radius)
        t = _travel(phi)
        return (t[0] * math.cos(alpha), math.sin(alpha), t[2] * math.cos(alpha))


def check_platform_mid_top(mid_top: float) -> float:
    """The platform midrail's top over the grating, if the end pieces down to its bottom still take both bolts."""
    # The bolts center on the span up to the rail's top, 1/4 in over the end piece's, so its top margin binds.
    highest = RAIL_TOP_IN - 2.0 * THK_IN - END_BOLT_SPACE_IN - 2.0 * END_BOLT_EDGE_IN + BAR_IN
    lowest = BAR_IN + 10.0
    if not lowest <= mid_top <= highest:
        raise ValueError(
            f"The platform midrail top must be {lowest:g} to {highest:g} in over the grating, so the end piece "
            "down to it still takes both bolts to the post."
        )
    return mid_top


def add_top_rails(
    model, places, per_flight: int, *, r_a: float, r_b: float, platforms: int, top_platform: bool, profile: str,
    post_in: float = PLATFORM_POST_IN, mid_top: float = PLATFORM_MID_TOP_IN, progress=None,
) -> BraceResult:
    """The outer top rail along every flight and across every platform.

    ``places`` are every pan, lowest first; ``profile`` is the L2x2x1/4 file
    (``post_sw.post_profile``); ``post_in`` is where the platform posts stand in from the ends;
    ``mid_top`` is the platform midrail's top, where the end pieces come down to.
    """
    check_platform_mid_top(mid_top)
    face_r = r_b + THICKNESS_IN
    flights = _flights(places, per_flight, r_b)
    landings = len(flights) - 1 + (1 if top_platform else 0)
    for k, flight in enumerate(flights):
        name = f"EliteRailF{k + 1}"
        start = flight.front(flight.first) - (flight.step if k == 0 else OVERHANG_IN / face_r)
        end = flight.front(flight.last) + (OVERHANG_IN / face_r if k < landings else 0.0)
        bodies0 = s._body_names(model)
        _helix_rail(model, flight, face_r, start, end, name, ANGLE_SECTION)
        if k > 0:
            joint, normal = _joint(flights[k - 1], flight, face_r, r_a, r_b, post_in, "B")
            _trim(model, bodies0, joint, tuple(-v for v in normal), f"{name}StartTrim")
        if k < landings:
            joint, normal = _joint(flight, None, face_r, r_a, r_b, post_in, "A")
            _trim(model, bodies0, joint, normal, f"{name}EndTrim")
        _progress(progress, f"{name} placed")
        if k < landings:
            above = flights[k + 1] if k + 1 < len(flights) else None
            _landing(model, flight, above, face_r, r_a, r_b, post_in, profile, mid_top, progress)
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"L2x2x1/4 outer top rail 42 in above the stringer's top edge, rolled along {len(flights)} "
        f"flight{'s' if len(flights) > 1 else ''}"
        + (
            f", with level pieces bolted to the posts at {landings} platform{'s' if landings > 1 else ''} "
            "and each platform's own rail between its posts."
            if landings else "."
        )
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def add_mid_rails(
    model, places, per_flight: int, *, r_a: float, r_b: float, platforms: int, top_platform: bool,
    post_in: float = PLATFORM_POST_IN, mid_top: float = PLATFORM_MID_TOP_IN, progress=None,
) -> BraceResult:
    """The outer 2 x 1/4 flat bar midrail along every flight and across every platform, on the walk
    side of the posts in line with the top rail's hanging leg.

    On a flight its top edge is 21 in over the stringer's top edge; on a platform ``mid_top`` over
    the grating, so a flight's bar turns level where it climbs to that, past the top rail's miter.
    The level pieces run to the end pieces the top rail is bolted to the posts with, so the top
    rail goes in first, with the same ``mid_top``.
    """
    check_platform_mid_top(mid_top)
    face_r = r_b + THICKNESS_IN
    flights = _flights(places, per_flight, r_b)
    landings = len(flights) - 1 + (1 if top_platform else 0)
    tops = (mid_top, MID_TOP_IN)
    for k, flight in enumerate(flights):
        name = f"EliteMidF{k + 1}"
        climb = (mid_top - MID_TOP_IN) / flight.rise_per_rad
        start = flight.front(flight.first) - flight.step if k == 0 else (
            flight.front(flight.first) + climb - OVERHANG_IN / face_r
        )
        end = flight.front(flight.last) + (climb + OVERHANG_IN / face_r if k < landings else 0.0)
        bodies0 = s._body_names(model)
        _helix_rail(model, flight, face_r, start, end, name, BAR_SECTION, RAIL_TOP_IN - MID_TOP_IN)
        if k > 0:
            joint, normal = _joint(flights[k - 1], flight, face_r, r_a, r_b, post_in, "B", *tops)
            _trim(model, bodies0, joint, tuple(-v for v in normal), f"{name}StartTrim")
        if k < landings:
            joint, normal = _joint(flight, None, face_r, r_a, r_b, post_in, "A", *tops)
            _trim(model, bodies0, joint, normal, f"{name}EndTrim")
        _progress(progress, f"{name} placed")
        if k < landings:
            above = flights[k + 1] if k + 1 < len(flights) else None
            _mid_landing(model, flight, above, face_r, r_a, r_b, post_in, mid_top, progress)
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"2 x 1/4 flat bar midrail 21 in above the stringer's top edge along {len(flights)} "
        f"flight{'s' if len(flights) > 1 else ''}"
        + (
            f", level at {mid_top:g} in across {landings} platform{'s' if landings > 1 else ''} to the end "
            "pieces and between each platform's posts."
            if landings else "."
        )
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _flights(places, per_flight: int, r_b: float) -> list[_Flight]:
    flights = []
    for first in range(0, len(places), per_flight):
        a, b = places[first], places[first + 1]
        flights.append(
            _Flight(places[first], places[first + per_flight - 1], (b.y1 - a.y1) / (b.phi - a.phi), b.phi - a.phi, r_b)
        )
    return flights


# ------------------------------------------------------------------ the helix


def _helix_rail(
    model, flight: _Flight, face_r: float, start: float, end: float, name: str, section, drop: float = 0.0,
) -> None:
    """Sweep the slice of ``section`` in the radial plane at ``start`` along a helix to ``end``,
    its top ``drop`` below the top rail's.

    The slice is the true section stretched up by 1/cos of the slope, so the rolled section is square to it.
    """
    stretch = 1.0 / math.cos(math.atan(flight.rise_per_rad / face_r))
    top = flight.top(start) - drop
    helix = s._helix(model, face_r, flight.rise_per_rad * (end - start), (end - start) / (2.0 * math.pi), name, start)
    # The bottom flight starts a little before the Right plane, where a turned radial plane cannot go.
    plane = _plane_through(model, _world(start, face_r, 0.0, top), _travel(start), f"{name}Prof")
    before = _names(model)
    _open_sketch(model, plane)
    try:
        sketch = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]
        corners = [(face_r + out, top + up * stretch) for out, up in section]
        pts = [s._to_sketch(data, [v * _INCH for v in _world(start, r, 0.0, y)])[:2] for r, y in corners]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if model.SketchManager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: rail profile edge failed.")
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    profile = _rename_new(model, before, f"{name}Prof", "rail profile")
    _clear_selection(model)
    if not (
        _select_feature(model, profile, "SKETCH", mark=1, append=False)
        and _select_feature(model, helix, "REFERENCECURVES", mark=4, append=True)
    ):
        raise SolidWorksError(f"{name}: could not select the rail profile and its helix.")
    feature = model.FeatureManager.InsertProtrusionSwept3(
        False, False, 0, False, False, 0, 0, False, 0.0, 0.0, 0, 0, False, True, True, 0.0, True
    )
    if feature is None:
        raise SolidWorksError(f"{name}: the rail sweep was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)


# ------------------------------------------------------------------ landings


@dataclass(frozen=True)
class _Post:
    """A platform post's heel along the outer channel, in the bisector frame of the platform."""

    mid: float  # bisector angle
    web_r: float  # outer channel's back on the bisector
    heel_t: float  # heel along the channel from the bisector
    away: float  # toward the platform end it faces: -1 at A, +1 at B
    grating: float  # platform walking surface

    def world(self, n: float, t: float, y: float) -> tuple[float, float, float]:
        """n out from the channel's back, t along it from the heel."""
        return _world(self.mid, self.web_r + n, self.heel_t + t, y)


def _post(flight: _Flight, r_a: float, r_b: float, post_in: float, side: str) -> _Post:
    lines = platform_lines(phi=flight.last.phi, tread_top=flight.last.y1, r_a=r_a, r_b=r_b)
    half = (lines.phi_b - lines.phi_a) / 2.0
    end_t = lines.r_out * math.sin(half) - post_in
    away = -1.0 if side == "A" else 1.0
    return _Post(lines.phi_a + half, lines.r_out * math.cos(half), away * end_t, away, flight.last.y1)


def _joint(
    below: _Flight, above: _Flight | None, face_r: float, r_a, r_b, post_in, side: str,
    level_top: float = RAIL_TOP_IN, stair_top: float = RAIL_TOP_IN,
):
    """Miter point and plane normal where a flight's helix meets a level piece at the platform
    after ``below``, for a rail ``stair_top`` over the stringer's top edge and ``level_top`` over the
    grating: where the helix climbs to the level, past the lower flight's top tread front (A) or the
    upper flight's first tread front (B). The normal points up the stair from the helix (A) or from
    the level piece (B)."""
    post = _post(below, r_a, r_b, post_in, side)
    top = below.last.y1 + level_top
    rail, place = (below, below.last) if side == "A" else (above, above.first)
    phi = rail.front(place) + (level_top - stair_top) / rail.rise_per_rad
    joint = _world(phi, face_r, 0.0, top)
    at_post = post.world(0.0, 0.0, top)
    level = _unit(tuple(at_post[i] - joint[i] for i in range(3)))
    if side == "B":
        level = tuple(-v for v in level)
    helix = rail.tangent(phi, face_r)
    return joint, _unit(tuple(helix[i] + level[i] for i in range(3)))


def _landing(
    model, below: _Flight, above: _Flight | None, face_r, r_a, r_b, post_in, profile, mid_top, progress,
) -> None:
    """Level piece and end piece at A, the platform's own rail, and at B the same for the flight above."""
    tag = f"ElitePlatform{below.last.index:02d}Rail"
    sides = ("A", "B") if above is not None else ("A",)
    posts = {side: _post(below, r_a, r_b, post_in, side) for side in ("A", "B")}
    for side in sides:
        post = posts[side]
        joint, normal = _joint(below, above, face_r, r_a, r_b, post_in, side)
        _end_piece(model, post, profile, mid_top, f"{tag}End{side}")
        _level_piece(model, post, joint, normal, side, profile, f"{tag}Level{side}")
        _progress(progress, f"{tag}{side} placed")
    a, b = posts["A"], posts["B"]
    top = a.grating + RAIL_TOP_IN
    _level_angle(
        model, a.world(-THK_IN, THK_IN, top), b.world(-THK_IN, -THK_IN, top), _radial(a.mid), profile, tag,
    )
    _progress(progress, f"{tag} placed")


def _mid_landing(
    model, below: _Flight, above: _Flight | None, face_r, r_a, r_b, post_in, mid_top, progress,
) -> None:
    """Level flat bars from the miters to the end pieces, and the platform's own bar between its posts."""
    tag = f"ElitePlatform{below.last.index:02d}Mid"
    for side in ("A", "B") if above is not None else ("A",):
        _mid_level(model, below, above, side, face_r, r_a, r_b, post_in, mid_top, f"{tag}Level{side}")
        _progress(progress, f"{tag}{side} placed")
    a, b = (_post(below, r_a, r_b, post_in, side) for side in ("A", "B"))
    top = a.grating + mid_top
    _flat_bar(model, a.world(0.0, THK_IN, top), b.world(0.0, -THK_IN, top), _radial(a.mid), tag)
    _progress(progress, f"{tag} placed")


def _mid_level(model, below, above, side: str, face_r, r_a, r_b, post_in, mid_top, name: str) -> None:
    """Level flat bar from its miter with the flight's bar to the end piece, a weld gap short of the end piece's edge."""
    post = _post(below, r_a, r_b, post_in, side)
    joint, normal = _joint(below, above, face_r, r_a, r_b, post_in, side, mid_top, MID_TOP_IN)
    top = joint[1]
    at_post = post.world(0.0, 0.0, top)
    along = _unit(tuple(at_post[i] - joint[i] for i in range(3)))
    out = _outward(along, post.mid)
    past = [joint[i] - OVERHANG_IN * along[i] for i in range(3)]
    stop = [at_post[i] - (WELD_GAP_IN + BAR_THK_IN * _skew(along, post.mid)) * along[i] for i in range(3)]
    a, b = (past, stop) if side == "A" else (stop, past)
    bodies0 = s._body_names(model)
    _flat_bar(model, tuple(a), tuple(b), out, name)
    _trim(model, bodies0, joint, tuple(-v for v in normal) if side == "A" else normal, f"{name}Trim")


def _outward(along, mid: float) -> tuple[float, float, float]:
    """Level and square to ``along``, away from the tank."""
    out = (along[2], 0.0, -along[0])
    if out[0] * _radial(mid)[0] + out[2] * _radial(mid)[2] < 0:
        out = (-out[0], 0.0, -out[2])
    return out


def _skew(along, mid: float) -> float:
    """Tangent of the angle between a level piece and the outer channel, which its square end turns off the post by."""
    cos = min(1.0, abs(along[0] * _travel(mid)[0] + along[2] * _travel(mid)[2]))
    return math.tan(math.acos(cos))


def _flat_bar(model, a, b, out, name: str) -> None:
    """Flat bar along a level line from ``a`` to ``b`` on its top outer edge, ``out`` away from the walk."""
    before = _names(model)
    manager = model.SketchManager
    with contextlib.suppress(Exception):
        manager.AddToDB = True
    _clear_selection(model)
    manager.Insert3DSketch(True)
    am, bm = [v * _INCH for v in a], [v * _INCH for v in b]
    line = manager.CreateLine(am[0], am[1], am[2], bm[0], bm[1], bm[2])
    manager.Insert3DSketch(True)
    if line is None:
        raise SolidWorksError(f"{name}: flat bar path was not drawn.")
    path = _rename_new(model, before, f"{name}Path", "flat bar path")
    plane = _plane_through(model, a, _unit(tuple(b[i] - a[i] for i in range(3))), f"{name}Prof")
    before = _names(model)
    _open_sketch(model, plane)
    try:
        sketch = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]
        corners = [tuple(a[i] + across * out[i] + (up if i == 1 else 0.0) for i in range(3)) for across, up in BAR_SECTION]
        pts = [s._to_sketch(data, [v * _INCH for v in p])[:2] for p in corners]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if model.SketchManager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: flat bar profile edge failed.")
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    profile = _rename_new(model, before, f"{name}ProfSk", "flat bar profile")
    _clear_selection(model)
    if not (
        _select_feature(model, profile, "SKETCH", mark=1, append=False)
        and _select_feature(model, path, "SKETCH", mark=4, append=True)
    ):
        raise SolidWorksError(f"{name}: could not select the flat bar profile and its path.")
    feature = model.FeatureManager.InsertProtrusionSwept3(
        False, False, 0, False, False, 0, 0, False, 0.0, 0.0, 0, 0, False, True, True, 0.0, True
    )
    if feature is None:
        raise SolidWorksError(f"{name}: the flat bar sweep was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if path.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)
    s._rebuild(model)


def _end_piece(model, post: _Post, profile: str, mid_top: float, name: str) -> None:
    """L2x2 back to back with the post's outstanding leg, its other leg along the channel toward the end,
    from the platform midrail's bottom up under the top rail, bolted to the post at its middle."""
    ys = (post.grating + mid_top - BAR_IN, post.grating + RAIL_TOP_IN - THK_IN)
    _upright_angle(model, post.mid, post.web_r, 1.0, post.away, ys, LEG_IN, profile, name, heel_t=post.heel_t)
    middle = (ys[0] + ys[1] + THK_IN) / 2.0  # the span up to the top rail's top, as the lisp centers it
    centers = [post.world(HOLE_GAUGE_IN, post.away * THK_IN, middle + dy)
               for dy in (END_BOLT_SPACE_IN / 2.0, -END_BOLT_SPACE_IN / 2.0)]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in centers:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: bolt hole circle failed.")

    face = _face_at(s._bodies(model), centers[0], _travel(post.mid))
    if not _cut(model, face, f"{name}Holes", draw, 2.0 * THK_IN + 0.1):
        raise SolidWorksError(f"{name}: the bolt holes to the post were not cut.")
    for point in centers:
        point_m = [v * _INCH for v in point]
        if sum(1 for b in s._bodies(model) if s._has_hole_axis(b, point_m, radius, 0.1 * _INCH) is True) < 2:
            raise SolidWorksError(f"{name}: a bolt hole is not through both the post and the end piece.")


def _level_piece(model, post: _Post, joint, normal, side: str, profile: str, name: str) -> None:
    """Straight level rail from the miter at ``joint`` to the end piece, square-cut a hair short of the post."""
    top = joint[1]
    at_post = post.world(0.0, 0.0, top)
    along = _unit(tuple(at_post[i] - joint[i] for i in range(3)))
    out = (along[2], 0.0, -along[0])
    if out[0] * _radial(post.mid)[0] + out[2] * _radial(post.mid)[2] < 0:
        out = (-out[0], 0.0, -out[2])
    # The square end turns off the post face by the piece's angle to the channel; stop short by what that sweeps.
    skew = math.acos(min(1.0, abs(along[0] * _travel(post.mid)[0] + along[2] * _travel(post.mid)[2])))
    short = LEG_IN * math.tan(skew) + 0.05
    past = [joint[i] - THK_IN * out[i] - OVERHANG_IN * along[i] for i in range(3)]  # beyond the miter, away from the post
    stop = [at_post[i] - THK_IN * out[i] - short * along[i] for i in range(3)]
    a, b = (past, stop) if side == "A" else (stop, past)
    bodies0 = s._body_names(model)
    _level_angle(model, tuple(a), tuple(b), out, profile, name)
    _trim(model, bodies0, joint, tuple(-v for v in normal) if side == "A" else normal, f"{name}Trim")


def _level_angle(model, a, b, out, profile: str, name: str) -> None:
    """L2x2 member on the heel line a to b, one leg straight down, the other out along ``out``."""
    feature, path_sketch, bodies_before = _member(model, profile, a, b, name)
    length = math.dist(a, b)
    down = tuple((b[i] - a[i]) / length for i in range(3))
    up = (0.0, 1.0, 0.0)
    body = _new_body(model, bodies_before)
    if body is None:
        s._rebuild(model)
        body = _new_body(model, bodies_before)
    end = [] if body is None else _end_face(body, a, down, up, out)
    off = _turn_off(end)
    if off is None:
        raise SolidWorksError(f"{name}: could not read how the rail angle is turned.")

    def end_after(turn):
        if not _set_turn(model, feature, turn):
            return []
        fresh = _new_body(model, bodies_before)
        return [] if fresh is None else _end_face(fresh, a, down, up, out)

    if not _knee_fits(end, 0.01, LEG_IN) and not any(_knee_fits(end_after(t), 0.01, LEG_IN) for t in (off, -off)):
        raise SolidWorksError(f"{name}: could not turn the rail angle with a leg down and a leg out.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if path_sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)


# ------------------------------------------------------------------ miters


def _unit(v):
    size = math.sqrt(sum(c * c for c in v))
    return tuple(c / size for c in v)


def _trim(model, bodies0: set[str], point, normal, name: str) -> None:
    """Cut away the newest body's material on the ``normal`` side of the plane through ``point``.

    Only that body: the piece on the other side of a miter is already there.
    """
    plane = _plane_through(model, point, normal, name)
    before = _names(model)
    _open_sketch(model, plane)
    try:
        sketch = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]
        u = _unit((normal[2], 0.0, -normal[0]) if abs(normal[1]) < 0.9 else (1.0, 0.0, 0.0))
        w = (
            normal[1] * u[2] - normal[2] * u[1],
            normal[2] * u[0] - normal[0] * u[2],
            normal[0] * u[1] - normal[1] * u[0],
        )
        span = 2.0 * LEG_IN + OVERHANG_IN
        corners = []
        for cu, cw in ((-span, -span), (span, -span), (span, span), (-span, span)):
            p = [(point[i] + cu * u[i] + cw * w[i]) * _INCH for i in range(3)]
            sx, sy, _sz = s._to_sketch(data, p)
            corners.append((sx, sy))
        for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
            if model.SketchManager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: miter cut edge failed.")
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    sketch = _rename_new(model, before, f"{name}Sk", "miter sketch")
    nothing = com_nothing()
    depth = (OVERHANG_IN + 2.0 * LEG_IN) * _INCH
    # A one-way cut runs against its sketch normal unless reversed. Cut the wrong way, it
    # takes a slab out of the piece and leaves the overhang as a second body, so check them all.
    for reverse in (True, False):
        body = _miter_piece(model, bodies0, point)
        if body is None:
            raise SolidWorksError(f"{name}: the piece to miter is missing.")
        # Rebuilds rename other bodies now and then; count pieces against the names just before this cut.
        others = s._body_names(model) - {str(body.Name)}
        _clear_selection(model)
        if not (
            _select_feature(model, sketch, "SKETCH", mark=0, append=False)
            and model.Extension.SelectByID2(str(body.Name), "SOLIDBODY", 0, 0, 0, True, 8, nothing, 0)
        ):
            raise SolidWorksError(f"{name}: could not select the miter sketch and its piece.")
        feature = model.FeatureManager.FeatureCut3(
            True, False, reverse, 0, 0, depth, 0.0,
            False, False, False, False, 0.0, 0.0, False, False, False, False,
            False, True, False, True, True, False, 0, 0.0, False,
        )
        s._rebuild(model)
        pieces = [b for b in s._bodies(model) if str(b.Name) not in others]
        reach = max(
            (sum((p[i] - point[i]) * normal[i] for i in range(3)) for b in pieces for p in _body_points(b)),
            default=None,
        )
        if feature is not None and len(pieces) == 1 and reach is not None and reach < 0.02:
            with contextlib.suppress(Exception):
                rename_feature(feature, name)
            return
        if feature is not None:
            s._delete_named(model, (s._feature_name(feature),))
            s._rebuild(model)
    raise SolidWorksError(f"{name}: the miter cut did not take the overhang.")


def _miter_piece(model, bodies0: set[str], point):
    """Of the bodies not in ``bodies0``, the one reaching nearest ``point``: the piece just made, even
    if a rebuild has renamed another body since."""
    best = None
    for body in s._bodies(model):
        if str(body.Name) in bodies0:
            continue
        points = _body_points(body)
        if not points:
            continue
        gap = min(math.dist(p, point) for p in points)
        if best is None or gap < best[0]:
            best = (gap, body)
    return None if best is None else best[1]


def _plane_through(model, point, normal, name: str):
    """Reference plane through ``point`` square to ``normal``: from a 3D sketch line along the normal."""
    a = [v * _INCH for v in point]
    b = [(point[i] + normal[i]) * _INCH for i in range(3)]
    before = _names(model)
    manager = model.SketchManager
    with contextlib.suppress(Exception):
        manager.AddToDB = True
    # With a sketch selected, Insert3DSketch opens that sketch instead of a new one.
    _clear_selection(model)
    manager.Insert3DSketch(True)
    line = manager.CreateLine(a[0], a[1], a[2], b[0], b[1], b[2])
    manager.Insert3DSketch(True)
    if line is None:
        raise SolidWorksError(f"{name}: the miter line was not drawn.")
    sketch = _rename_new(model, before, f"{name}LineSk", "miter line")
    sketch_name = s._feature_name(sketch)
    nothing = com_nothing()
    _clear_selection(model)
    extension = model.Extension
    if not (
        extension.SelectByID2(f"Line1@{sketch_name}", "EXTSKETCHSEGMENT", 0, 0, 0, False, 0, nothing, 0)
        and extension.SelectByID2(f"Point1@{sketch_name}", "EXTSKETCHPOINT", 0, 0, 0, True, 1, nothing, 0)
    ):
        raise SolidWorksError(f"{name}: could not select the miter line and its start.")
    before = _names(model)
    plane = model.FeatureManager.InsertRefPlane(2, 0.0, 4, 0.0, 0, 0.0)
    _clear_selection(model)
    if plane is None:
        raise SolidWorksError(f"{name}: the miter plane was not made.")
    plane = _rename_new(model, before, f"{name}Pln", "miter plane")
    rows = [float(v) for v in com_value(com_value(com_value(plane.GetSpecificFeature2).Transform).ArrayData)]
    if abs(abs(sum(rows[6 + i] * normal[i] for i in range(3))) - 1.0) > 1e-6:
        raise SolidWorksError(f"{name}: the miter plane is not square to the miter.")
    with contextlib.suppress(Exception):
        if sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)
    return plane
