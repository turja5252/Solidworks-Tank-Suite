"""The roof platform in SolidWorks (item 12, first steps 2026-10-30): its frame, its extension, its braces, and its legs
on pads on the cone. The plan and the heights are ``roof_platform``'s; the builders are the stair platforms'.

The rectangle is one closed loop of its channel, mitred at the corners, web backs on the outline and flanges in
(``platform_sw._frame``). The extension past D is one open run of three, A', D', B': mitred at its two outer corners,
square where A' and B' meet D's back (the lisp's Type2). A brace from C to D is the same channel, its web toward B
and its flanges toward A (the lisp), coped at both ends to the side it meets with Chris Samm's 1/16 in all round.
Each leg is an L3x3x3/8 (the lisp's) under C or D, its heel on the channel's back, one leg along the channel and the
other in under it, from the channel's bottom down to a 1/4 x 6 x 6 pad lying on the cone, cut to the pad's slope.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import com_nothing, com_value
from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import BraceResult, _extrude_to, _progress
from swauto.stair.platform_sw import (
    COPE_GAP_IN,
    GRATING_IN,
    SECTIONS,
    _channel_member,
    _cut_both_ways_in,
    _frame,
    _grown_section,
    _plane_across,
    _sketch_on_face,
    _upright_angle,
    _vertices,
    _world,
    section_file,
)
from swauto.stair.rail_sw import _plane_through, _trim
from swauto.stair.roof_platform import RoofPlatform, deck_y, legs, roof_top_y
from swauto.tank.roof import RoofSpec

_INCH = 0.0254
LEG_ANGLE_IN = 3.0  # L3x3x3/8
PAD_IN = 6.0
PAD_THK_IN = 0.25


def _sketch_xy(point) -> tuple[float, float]:
    """A plan point (X, Z) in inches in Top-plane sketch coordinates (x, -z), meters."""
    return point[0] * _INCH, -point[1] * _INCH


def _counterclockwise(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """In the sketch a counterclockwise loop puts a weldment's flanges inside it."""
    area = 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1], strict=True))
    return points if area > 0 else list(reversed(points))


def build_roof_platform(model, placed: RoofPlatform, roof: RoofSpec, channel_profile: str, leg_profile: str,
                        progress=None, name: str = "EliteRoofPlatform") -> BraceResult:
    """Frame, extension, braces, and legs on pads, into ``model`` (the tank part with its roof, or a part of its
    own). ``channel_profile`` is any channel file in the weldment library (``platform_sw.platform_profile``): the
    spec's own channel is the file beside it."""
    section = SECTIONS[placed.spec.channel]
    channel = section_file(channel_profile, section)
    deck = deck_y(placed, roof)
    base = deck - GRATING_IN - section.depth_in
    corners = [_sketch_xy(placed.world(*p)) for p in placed.corners()]
    _frame(model, _counterclockwise(corners), base, channel, name, section)
    _progress(progress, f"{name} frame placed")
    extension = placed.extension()
    if extension is not None:
        _extension(model, placed, extension, base, channel, f"{name}Ext")
        _progress(progress, f"{name}Ext placed")
    for i, along in enumerate(placed.brace_alongs(), start=1):
        _brace(model, placed, along, base, channel, f"{name}Brace{i}")
        _progress(progress, f"{name}Brace{i} placed")
    standing = legs(placed, roof)
    for i, leg in enumerate(standing, start=1):
        _leg(model, placed, roof, leg, base, leg_profile, f"{name}Leg{i}")
        _progress(progress, f"{name}Leg{i} placed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    spec = placed.spec
    note = (
        f"Roof platform {spec.length_in:g} x {spec.width_in:g} in"
        + (f" with a {spec.ext_length_in:g} x {spec.ext_reach_in:g} in extension past D" if extension else "")
        + f", {section.name} mitred, {len(placed.brace_alongs())} brace(s) coped to C and D, its deck at "
        f"{deck:.3f} in; {len(standing)} L3x3x3/8 legs ({spec.area_ft2:.1f} sq ft, one per 30 as the lisp counts, "
        f"two a side at least) on 1/4 x 6 x 6 pads on the roof, {min(leg.length_in for leg in standing):.2f} to "
        f"{max(leg.length_in for leg in standing):.2f} in long."
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _extension(model, placed: RoofPlatform, outline, base: float, channel: str, name: str) -> None:
    """A', D', B' as one structural member on an open run, counterclockwise so the flanges come inside it."""
    section = SECTIONS[placed.spec.channel]
    points = [_sketch_xy(placed.world(*p)) for p in outline]
    loop = _counterclockwise(points)
    # The run leaves out the side along D: from D at one end, round the three outer sides, back to D.
    start = next(i for i in range(4) if {loop[i], loop[(i + 1) % 4]} == {points[3], points[0]})
    run = [loop[(start + 1 + k) % 4] for k in range(4)]
    plane = s._offset_from(model, s._plane(model, "Top"), base, f"{name}Pln")

    def draw():
        manager = model.SketchManager
        with contextlib.suppress(Exception):
            manager.AddToDB = True
        for (ax, ay), (bx, by) in zip(run, run[1:]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: extension line failed.")

    sketch = s._sketch_on(model, plane, f"{name}Sk", draw)
    before = s._body_names(model)
    s._select_segments(model, sketch, name, 3)
    feature = model.FeatureManager.InsertStructuralWeldment2(channel, 1, False, 0.0)
    if feature is None:
        raise SolidWorksError(f"{name}: the extension's channels were not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
    made = [b for b in s._bodies(model) if str(b.Name) not in before]
    if len(made) != 3 or any(abs(s._box_in(b)[4] - s._box_in(b)[1] - section.depth_in) > 0.01 for b in made):
        raise SolidWorksError(f"{name}: expected three {section.depth_in:g} in channels, got {len(made)} bodies.")
    # Their flanges inside the extension: nothing of them inside D's back. An open run may take its flanges the
    # other way; then it is turned over about its path.
    radial = (-math.sin(placed.angle), math.cos(placed.angle))

    def inside_d() -> bool:
        bodies = [b for b in s._bodies(model) if str(b.Name) not in before]
        return min(p[0] * radial[0] + p[2] * radial[1] for b in bodies for p in _vertices(b)) < placed.d_out - 0.01

    if inside_d():
        data = com_value(feature.GetDefinition)
        data.AccessSelections(model, com_nothing())
        data.RotationAngle = math.pi
        if not feature.ModifyDefinition(data, model, com_nothing()):
            raise SolidWorksError(f"{name}: could not turn the extension's channels over.")
        s._rebuild(model)
        if inside_d():
            raise SolidWorksError(f"{name}: the extension's channels came in past D's back.")


def _brace(model, placed: RoofPlatform, along: float, base: float, channel: str, name: str) -> None:
    """A channel from C to D at ``along``, its web toward B and its flanges toward A, coped to C and D."""
    section = SECTIONS[placed.spec.channel]
    near = placed.d_in + section.web_in
    far = placed.d_out - section.web_in
    plane = s._offset_from(model, s._plane(model, "Top"), base, f"{name}Pln")
    a, b = _sketch_xy(placed.world(along, near)), _sketch_xy(placed.world(along, far))  # out from C: flanges to A

    def draw():
        if model.SketchManager.CreateLine(a[0], a[1], 0.0, b[0], b[1], 0.0) is None:
            raise SolidWorksError(f"{name}: brace line failed.")

    before = s._body_names(model)
    body = _channel_member(model, s._sketch_on(model, plane, f"{name}Sk", draw), channel, 0.0, name, section)
    travel = (-math.cos(placed.angle), -math.sin(placed.angle))
    alongs = [p[0] * travel[0] + p[2] * travel[1] for p in _vertices(body)]
    if min(alongs) > along - 0.9 * section.flange_in:
        # Drawn the other way, its flanges came out toward B: turn it over.
        s._delete_named(model, (name,))
        s._rebuild(model)
        sketch = s._sketch_on(model, plane, f"{name}Sk2", lambda: model.SketchManager.CreateLine(
            b[0], b[1], 0.0, a[0], a[1], 0.0))
        body = _channel_member(model, sketch, channel, 0.0, name, section)
    for inner in (True, False):
        _cope(model, before, placed, along, base, inner, f"{name}Cope{'C' if inner else 'D'}")


def _cope(model, before: set[str], placed: RoofPlatform, along: float, base: float, inner: bool, name: str) -> None:
    """The brace at ``along`` coped to C (``inner``) or D: whatever of it lies in the side's section grown 1/16 in
    all round is cut away, from the plane square to the side through the middle of the brace's flange width."""
    section = SECTIONS[placed.spec.channel]
    at_along = along - section.flange_in / 2.0  # the flanges are toward A
    plane = _plane_across(model, placed.angle, at_along, f"{name}Pln")
    back, out = (placed.d_in, 1.0) if inner else (placed.d_out, -1.0)

    def at(t: float, y: float):
        return _world(placed.angle, back + out * t, at_along, base + y)

    def draw(manager, to_sketch):
        for shape in _grown_section(COPE_GAP_IN, section):
            points = [to_sketch(at(*p)) for p in shape[1:]]
            if shape[0] == "line":
                (ax, ay), (bx, by) = points
                made = manager.CreateLine(ax, ay, 0.0, bx, by, 0.0)
            else:
                (ax, ay), (mx, my), (bx, by) = points
                made = manager.Create3PointArc(ax, ay, 0.0, bx, by, 0.0, mx, my, 0.0)
            if made is None:
                raise SolidWorksError(f"{name}: the cope's outline failed.")

    sketch = _sketch_on_face(model, plane, f"{name}Sk", draw)
    made = [b for b in s._bodies(model) if str(b.Name) not in before]
    if len(made) != 1:
        raise SolidWorksError(f"{name}: expected the one brace, found {len(made)} new bodies.")
    feature = _cut_both_ways_in(model, sketch, section.flange_in / 2.0 + 0.25, made[0])
    if feature is None:
        raise SolidWorksError(f"{name}: the cope was not cut.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)


def _roof_normal(roof: RoofSpec, point) -> tuple[float, float, float]:
    """The cone's outward normal at plan ``point``: up, leaning out from the axis by the slope."""
    slope = roof.slope_in_per_ft / 12.0
    r = math.hypot(*point)
    rx, rz = (point[0] / r, point[1] / r) if r > 1e-9 else (0.0, 0.0)
    k = math.hypot(1.0, slope)
    return (slope * rx / k, 1.0 / k, slope * rz / k)


def _leg(model, placed: RoofPlatform, roof: RoofSpec, leg, base: float, profile: str, name: str) -> None:
    """The pad on the cone under the leg, then the L3x3 from below the pad's top up to the channel's bottom, its
    foot cut to the pad's top."""
    inward = 1.0 if leg.side == "C" else -1.0  # under the channel, in toward the platform
    back = placed.d_in if leg.side == "C" else placed.d_out
    middle = placed.world(leg.along + LEG_ANGLE_IN / 2.0, back + inward * LEG_ANGLE_IN / 2.0)
    normal = _roof_normal(roof, middle)
    surface = (middle[0], roof_top_y(roof, math.hypot(*middle)), middle[1])
    plane = _plane_through(model, surface, normal, f"{name}PadPln")
    u = (normal[2], 0.0, -normal[0])
    size = math.sqrt(u[0] ** 2 + u[2] ** 2)
    u = (u[0] / size, 0.0, u[2] / size) if size > 1e-9 else (1.0, 0.0, 0.0)
    w = (normal[1] * u[2] - normal[2] * u[1], normal[2] * u[0] - normal[0] * u[2], normal[0] * u[1] - normal[1] * u[0])

    def draw(manager, to_sketch):
        half = PAD_IN / 2.0
        pts = [to_sketch(tuple(surface[i] + cu * half * u[i] + cw * half * w[i] for i in range(3)))
               for cu, cw in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1], strict=True):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: pad edge failed.")

    sketch = _sketch_on_face(model, plane, f"{name}Pad", draw)
    centre = tuple(surface[i] + normal[i] * PAD_THK_IN / 2.0 for i in range(3))
    _extrude_to(model, sketch, PAD_THK_IN, centre, PAD_IN, f"{name}Pad")
    top = tuple(surface[i] + normal[i] * PAD_THK_IN for i in range(3))
    low = top[1] - LEG_ANGLE_IN * 0.2 - 0.5  # below the pad's top under the whole angle, to be cut to it
    before = s._body_names(model)
    _upright_angle(model, placed.angle, back, inward, 1.0, (low, base), LEG_ANGLE_IN, profile, name,
                   heel_t=leg.along)
    _trim(model, before, top, tuple(-v for v in normal), f"{name}Foot")
