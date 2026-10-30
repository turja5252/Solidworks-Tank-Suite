"""Handrail splitters: where a flight's rails are too long for their stock, they are made in pieces and joined.

From Elite's STWC detail D and STWD pc 8, 9 and 10 (the outside handrail) and STWE pc 3 (the inside one):

* The top rail and midrail are cut through in the middle of a bay between two posts, 1/2 in apart. Each rail
  end is welded to an L2x2x1/4 connector angle standing upright, one leg across the rail's end (in the radial
  plane) and the other along the rail out past the top rail's outstanding leg; the two connectors stand back to
  back and are bolted together with two 5/8 in bolts in 11/16 in holes 12 in apart. They run from just under
  the midrail up to the underside of the top rail's top leg (the drawings' 45 and 135 degree ends are cut
  level here).
* The pipe is cut with a 2 in gap at the same place, and a 1-1/2 in round bar 2 in long sits in the gap in line
  with the pipe, welded to both ends (STWD pc 10 joint, pc 12; STWE pc 20).

Pure placement lives in ``attachments`` (which bays); this module only models them.
"""

from __future__ import annotations

import contextlib
import math

from swauto.comutil import com_value
from swauto.errors import SolidWorksError
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import BraceResult, _face_at, _progress
from swauto.stair.grab_sw import (
    BRACKET_IN,
    BRACKET_OVERALL_IN,
    GRAB_TOP_IN,
    _extrude_mid,
    _Pipe,
    _sketch_through,
)
from swauto.stair.platform_sw import _cut, _travel, _upright_angle, _world
from swauto.stair.post_sw import LEG_IN, RAIL_TOP_IN, THK_IN, Post, _post_side
from swauto.stair.rail_sw import BAR_IN, MID_TOP_IN, _flights
from swauto.stair.stringer_sw import _create_circle

_INCH = 0.0254
GAP_IN = 0.5  # the two connectors' legs, back to back
BOLT_SPACE_IN = 12.0
BOLT_HOLE_IN = 0.6875
PIPE_GAP_IN = 2.0
ROUND_BAR_DIA_IN = 1.5
ROUND_BAR_IN = 2.0


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
                parts.append("the top rail and midrail on two L2x2x1/4 connectors back to back with two 5/8 in bolts "
                             "in 11/16 holes 12 in apart")
            top = inner_pipe_top if inner else outer_pipe_top
            if top is not None:
                _pipe_joint(model, places, per_flight, low, high, r_a, r_b, inner, top, f"{name}Pipe")
                parts.append("the pipe joined by a 1-1/2 in round bar 2 in long in a 2 in gap")
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


def _connectors(model, places, per_flight: int, low: Post, high: Post, r_b: float, profile: str, name: str) -> None:
    face_r = r_b + s.THICKNESS_IN  # the rails' walk side, on the posts
    flight = _flights(places, per_flight, r_b)[(low.index - 1) // per_flight]
    phi = split_angle(low, high)
    top = flight.top(phi)
    bottom = top - RAIL_TOP_IN + MID_TOP_IN - BAR_IN
    half = GAP_IN / 2.0 / face_r
    s._sector_cut(model, (face_r - 0.5, face_r + LEG_IN), phi - half, phi + half, bottom - 1.0, top + 1.0,
                  f"{name}Gap")
    s._rebuild(model)
    ys = (bottom - 0.5, top - THK_IN)
    heel_r = face_r - THK_IN + LEG_IN  # the leg across the rail's end spans the rail's whole width
    for label, away in (("Low", -1.0), ("High", 1.0)):
        _upright_angle(model, phi, heel_r, -1.0, away, ys, LEG_IN, profile, f"{name}{label}")
    middle = (ys[0] + ys[1]) / 2.0
    points = [_world(phi, face_r + 0.75, -THK_IN, middle + d) for d in (-BOLT_SPACE_IN / 2.0, BOLT_SPACE_IN / 2.0)]
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


def _pipe_joint(model, places, per_flight: int, low: Post, high: Post, r_a: float, r_b: float, inner: bool,
                top: float, name: str) -> None:
    way, face_r = _post_side(r_a if inner else r_b, inner)
    radius = face_r - way * (BRACKET_OVERALL_IN - BRACKET_IN / 2.0)
    flight = _flights(places, per_flight, r_a if inner else r_b)[(low.index - 1) // per_flight]
    pipe = _Pipe(flight, radius, top)
    phi = split_angle(low, high)
    half = PIPE_GAP_IN / 2.0 * math.cos(pipe.alpha) / radius
    y = pipe.center_y(phi)
    s._sector_cut(model, (radius - 1.2, radius + 1.2), phi - half, phi + half, y - 3.0, y + 3.0, f"{name}Gap")
    s._rebuild(model)
    center, tangent = pipe.center(phi), pipe.tangent(phi)

    def draw(manager, to_sketch):
        cx, cy = to_sketch(center)
        if manager.CreateCircleByRadius(cx, cy, 0.0, ROUND_BAR_DIA_IN / 2.0 * _INCH) is None:
            raise SolidWorksError(f"{name}: round bar circle failed.")

    _extrude_mid(model, _sketch_through(model, center, tangent, f"{name}Bar", draw), ROUND_BAR_IN, f"{name}Bar")
