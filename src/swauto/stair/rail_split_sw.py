"""Handrail splitters: where a flight's rails are too long for their stock, they are made in pieces and joined.

From Elite's STWC detail D and STWD pc 8, 9 and 10 (the outside handrail) and STWE pc 3 (the inside one):

* The top rail and midrail are cut through in the middle of a bay between two posts, 1/8 in apart. Each rail
  end is welded to an L2x2x1/4 connector angle standing upright, one leg flat against the outside of the
  midrail and the top rail's hanging leg, the other standing out square to the rails at the cut; the two
  standing legs are back to back and bolted together with two 5/8 in bolts in 11/16 in holes 12 in apart, at
  the posts' gauge from the heel. They run from 1/4 in short of the midrail's bottom edge up to the posts' 3/4 in
  under the top rail's top edge, both square to the rails, so both ends are cut parallel to them (the drawings'
  45 and 135 degree ends). Like the posts' outstanding legs, the standing legs are cut back 45 degrees from the
  top at their root down to their toe, so fingers sliding along under the top rail clear them.
* The pipe is cut square at the same place, its ends 1/4 in apart, and a 1-1/2 in round bar 2 in long runs inside
  both ends across the gap, its upper end chamfered 45 degrees to lead the upper pipe on; the gap is welded in the
  field (the user, 2026-10-30. Elite's STWD pc 10 joint, pc 12 and STWE pc 20 put the bar in a 2 in gap instead).

Pure placement lives in ``attachments`` (which bays); this module only models them.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import as_model_doc, com_value
from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import BraceResult, _face_at, _progress
from swauto.stair.grab_sw import (
    BRACKET_IN,
    BRACKET_OVERALL_IN,
    GRAB_TOP_IN,
    PIPE_OD_IN,
    _Pipe,
    _sketch_through,
)
from swauto.stair.platform_sw import (
    _cut,
    _cut_both_ways_in,
    _radial,
    _sketch_on_face,
    _travel,
    _upright_angle,
    _world,
)
from swauto.stair.post_sw import HOLE_GAUGE_IN, LEG_IN, RAIL_TOP_IN, THK_IN, TOP_GAP_IN, Post, _post_side
from swauto.stair.rail_sw import BAR_IN, MID_TOP_IN, _flights, _miter_piece, _trim
from swauto.stair.stringer_sw import _create_circle

_INCH = 0.0254
GAP_IN = 0.125  # between the rail ends, 1/16 in a side of the cut (the field foreman, 2026-10-30)
FOOT_UP_IN = 0.25  # a connector's foot short of the midrail's bottom edge, square to the rails (the user)
BOLT_SPACE_IN = 12.0
BOLT_HOLE_IN = 0.6875
PIPE_GAP_IN = 0.25  # between the pipe ends, for the field weld
ROUND_BAR_DIA_IN = 1.5  # inside the pipe's 1.61 in bore
ROUND_BAR_IN = 2.0  # centred on the gap, so 7/8 in into each pipe end
ROUND_BAR_CHAMFER_IN = 0.125  # 45 degrees on its upper end (no size given; 1/8 in assumed)


def add_rail_splits(
    model, places, per_flight: int, splits, *, r_a: float, r_b: float, profile: str, rails: bool = True,
    outer_pipe_top: float | None = GRAB_TOP_IN, inner_pipe_top: float | None = None, progress=None,
) -> BraceResult:
    """Each split: ``splits`` are (side, low post, high post) with the posts from ``post_sw.post_layout`` (the outer
    stringer's, or the inner one's), the split in the middle of the bay between them. On the outer side the top
    rail and midrail get the bolted connectors when ``rails``, and the pipe, if ``outer_pipe_top`` is not None,
    its round bar; on the inner side only the pipe (``inner_pipe_top``)."""
    made, missed = [], []
    for side, low, high in splits:
        inner = side == "inner"
        name = f"EliteRailSplit{'In' if inner else ''}{low.index:02d}"
        try:
            parts = []
            if not inner and rails:
                _connectors(model, places, per_flight, low, high, r_b, profile, name)
                parts.append("the top rail and midrail on two L2x2x1/4 connectors flat on the rails' outside, their "
                             "standing legs back to back with two 5/8 in bolts in 11/16 holes 12 in apart")
            top = inner_pipe_top if inner else outer_pipe_top
            if top is not None:
                _pipe_joint(model, places, per_flight, low, high, r_a, r_b, inner, top, f"{name}Pipe")
                parts.append("the pipe ends 1/4 in apart on a 1-1/2 in round bar 2 in long inside both, its upper "
                             "end chamfered 45 degrees")
            if parts:
                made.append(f"between {side} posts {low.index} and {high.index}: {', '.join(parts)}")
            _progress(progress, f"{name} {'made' if parts else 'missed'}")
        except SolidWorksError as exc:
            missed.append(f"{side} {low.index}-{high.index} ({exc})")
            _progress(progress, f"{name} missed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = f"Handrail split {'; '.join(made)}." if made else ""
    if missed:
        note += f" Handrail splits missed: {'; '.join(missed)}."
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note.strip())


def split_angle(low: Post, high: Post) -> float:
    """The middle of the bay between two posts' heels."""
    return (low.phi + high.phi) / 2.0


def connector_ends(flight, phi: float, face_r: float) -> tuple[float, float, tuple[float, float, float]]:
    """(top, foot, up) of the connectors at a split: the heights of their ends on the rails' outside face at the
    cut, and the normal of the planes their ends are cut on, parallel to the rails' climb there. The rails'
    sections are stretched up by 1/cos of the slope (``rail_sw._helix_rail``), so their edges are too."""
    alpha = math.atan(flight.rise_per_rad / face_r)
    stretch = 1.0 / math.cos(alpha)
    rail_top = flight.top(phi)
    top = rail_top - TOP_GAP_IN * stretch  # the posts' gap under the top rail's top edge
    foot = rail_top - RAIL_TOP_IN + MID_TOP_IN - (BAR_IN - FOOT_UP_IN) * stretch
    travel = _travel(phi)
    up = (-math.sin(alpha) * travel[0], math.cos(alpha), -math.sin(alpha) * travel[2])
    return top, foot, up


def _connectors(model, places, per_flight: int, low: Post, high: Post, r_b: float, profile: str, name: str) -> None:
    face_r = r_b + s.THICKNESS_IN  # the rails' outside face, on the posts' walk side
    flight = _flights(places, per_flight, r_b)[(low.index - 1) // per_flight]
    phi = split_angle(low, high)
    top, foot, up = connector_ends(flight, phi, face_r)
    half = GAP_IN / 2.0 / face_r
    s._sector_cut(model, (face_r - 0.5, face_r + LEG_IN), phi - half, phi + half, foot - BAR_IN,
                  flight.top(phi) + 1.0, f"{name}Gap")
    s._rebuild(model)
    # Stood long enough to take both ends' slope over a leg, then cut parallel to the rails.
    climb = LEG_IN * flight.rise_per_rad / face_r + 0.5
    ys = (foot - climb, top + climb)
    for label, away in (("Low", -1.0), ("High", 1.0)):
        before = s._body_names(model)
        # The heel on the rails' outside face: the leg along the rails lies flat on them, the other stands out
        # square to them at the cut, back to back with the other connector's.
        _upright_angle(model, phi, face_r, 1.0, away, ys, LEG_IN, profile, f"{name}{label}")
        _trim(model, before, _world(phi, face_r, 0.0, top), up, f"{name}{label}Top")
        _trim(model, before, _world(phi, face_r, 0.0, foot), tuple(-v for v in up), f"{name}{label}Foot")
        body = _miter_piece(model, before, _world(phi, face_r, 0.0, foot))
        standing_cutback(model, body, phi, face_r, away, top, foot, f"{name}{label}")
    middle = (foot + top) / 2.0
    points = [_world(phi, face_r + HOLE_GAUGE_IN, -THK_IN, middle + d)
              for d in (-BOLT_SPACE_IN / 2.0, BOLT_SPACE_IN / 2.0)]
    radius = BOLT_HOLE_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: bolt hole circle failed.")

    normal = tuple(-v for v in _travel(phi))
    face = _face_at(s._bodies(model), points[0], normal)
    if face is None or not _cut(model, face, f"{name}Holes", draw, 2.0 * THK_IN + 0.1):
        raise SolidWorksError(f"{name}: the connector bolt holes were not cut.")


def standing_cutback(model, body, phi: float, face_r: float, away: float, top: float, foot: float, name: str) -> None:
    """A connector's standing leg cut back 45 degrees from ``top`` at its root down to its toe, as the posts'
    outstanding legs are (``post_sw._cutback``). ``top`` is the connectors' top at the cut, so the two butted legs
    are cut back flush, one 45 degree face across both. Cut on ``body`` alone: the other connector's standing leg is
    right behind it, and the top climbs with the rails across the leg, so the cut reaches well over it.
    ``away`` is the way its flat leg runs along the rails; ``foot`` is where its foot is at the cut.
    """
    face_t = away * THK_IN
    normal = tuple(away * v for v in _travel(phi))
    face = _face_at([body], _world(phi, face_r + THK_IN + LEG_IN / 2.0, face_t, foot + 2.5), normal)
    root, past = face_r + THK_IN, face_r + LEG_IN + 0.5
    corners = ((root, top + 0.5), (root, top), (past, top - (past - root)), (past, top + 0.5))

    def draw(manager, to_sketch):
        pts = [to_sketch(_world(phi, r, face_t, y)) for r, y in corners]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1], strict=True):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: cutback edge failed.")

    sketch = _sketch_on_face(model, face, f"{name}Cutback", draw)
    feature = _cut_both_ways_in(model, sketch, THK_IN + 0.1, body)
    if feature is None:
        raise SolidWorksError(f"{name}: the standing leg was not cut back 45 degrees.")
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Cutback")
    s._rebuild(model)


def _pipe_joint(model, places, per_flight: int, low: Post, high: Post, r_a: float, r_b: float, inner: bool,
                top: float, name: str) -> None:
    way, face_r = _post_side(r_a if inner else r_b, inner)
    radius = face_r - way * (BRACKET_OVERALL_IN - BRACKET_IN / 2.0)
    flight = _flights(places, per_flight, r_a if inner else r_b)[(low.index - 1) // per_flight]
    pipe = _Pipe(flight, radius, top)
    phi = split_angle(low, high)
    center, tangent = pipe.center(phi), pipe.tangent(phi)

    def disc(radius_in: float, what: str):
        def draw(manager, to_sketch):
            cx, cy = to_sketch(center)
            if manager.CreateCircleByRadius(cx, cy, 0.0, radius_in * _INCH) is None:
                raise SolidWorksError(f"{name}: {what} circle failed.")

        return draw

    # The gap is cut square to the pipe.
    gap = _sketch_through(model, center, tangent, f"{name}Gap", disc(PIPE_OD_IN / 2.0 + 0.25, "gap"))
    feature = s._cut_both_ways(model, gap, PIPE_GAP_IN / 2.0)
    if feature is None:
        raise SolidWorksError(f"{name}: the pipe gap was not cut.")
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Gap")
    s._rebuild(model)
    _round_bar(model, center, tangent, _radial(phi), f"{name}Bar")


def round_bar_section(axis_in: float = ROUND_BAR_IN) -> list[tuple[float, float]]:
    """The round bar's half section as (along the pipe from the gap's middle, out from its axis), closed along the
    axis: square at the lower end, chamfered 45 degrees at the upper."""
    half, radius, chamfer = axis_in / 2.0, ROUND_BAR_DIA_IN / 2.0, ROUND_BAR_CHAMFER_IN
    return [(-half, 0.0), (-half, radius), (half - chamfer, radius), (half, radius - chamfer), (half, 0.0)]


def _round_bar(model, center, tangent, radial, name: str) -> None:
    """The round bar, its own body: its half section turned about the pipe's axis, sketched on the plane through
    the axis square to ``radial`` (the radial is square to the pipe's run)."""
    out = (
        radial[1] * tangent[2] - radial[2] * tangent[1],
        radial[2] * tangent[0] - radial[0] * tangent[2],
        radial[0] * tangent[1] - radial[1] * tangent[0],
    )

    def at(along: float, off: float):
        return tuple(center[i] + along * tangent[i] + off * out[i] for i in range(3))

    def draw(manager, to_sketch):
        ends = [to_sketch(at(along, 0.0)) for along in (-ROUND_BAR_IN, ROUND_BAR_IN)]
        if manager.CreateCenterLine(ends[0][0], ends[0][1], 0.0, ends[1][0], ends[1][1], 0.0) is None:
            raise SolidWorksError(f"{name}: round bar axis failed.")
        pts = [to_sketch(at(along, off)) for along, off in round_bar_section()]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1], strict=True):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: round bar section failed.")

    sketch = _sketch_through(model, center, radial, name, draw)
    doc = as_model_doc(model)
    # A full turn, not merged: (single way, solid, ..., 2 pi, ..., merge off, scope, auto-select), as the nozzles turn.
    args = (
        True, True, False, False, False, False, 0, 0, 2.0 * math.pi, 0.0,
        False, False, 0.0, 0.0, 0, 0.0, 0.0, False, True, True,
    )
    feature = None
    for _attempt in range(2):  # SW 2013 now and then turns down a good profile once; a rebuild takes it
        s._clear_selection(model)
        if not s._select_feature(model, sketch, "SKETCH", mark=0, append=False):
            raise SolidWorksError(f"{name}: could not select the round bar's section.")
        with contextlib.suppress(Exception):
            feature = doc.FeatureManager.FeatureRevolve2(*args)
        if feature not in (None, False):
            break
        s._rebuild(model)
    if feature in (None, False):
        raise SolidWorksError(f"{name}: the round bar was not turned.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
