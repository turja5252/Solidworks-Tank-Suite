"""Stringer splitter: where a long stringer is cut into pieces and spliced, from the lisp's SPLITSTRING.

Everything is in one flight's development (``development.py``): x along the climb, y up,
inches, tread i centered at i rises. A flight is cut level (constant y) between two treads,
midway between their centers, with a 1/4 in gap. How many pieces: the flight's vertical span
(its treads plus the 5-1/4 in drop at the foot) over the max span, or a set number; the cuts
share the tread intervals out from tread 1, the same treads on the inner and outer stringer.

Each joint gets one splice plate: a parallelogram whose top and bottom are level and whose
sides lie on the stringer's top and bottom edges, so it covers the stringer's full depth. Four
13/16 holes go through plate and stringer alike, two rows 1-5/8 in above and below the cut,
each hole 1-1/2 in in from an edge, square to the slope. On the inner stringer the joint's two
acute corners get a 1 in relief radius, and so does the plate's top acute corner; the outer
stringer's are sharp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.stair.development import DROP_IN, DevelopedStringer
from swauto.stair.stringer import TREAD_DEPTH_IN, TREAD_MARK_IN

LIMIT = "limit"
SEGMENTS = "segments"
MAX_SPAN_FT = 8.5
SEGMENT_COUNT = 3
GAP_IN = 0.25  # the two burn lines at the cut
HOLE_ROW_IN = 1.625  # each hole row above and below the cut, vertically
HOLE_DIA_IN = 0.8125
HOLE_INSET_IN = 1.5  # in from each slanted edge, square to the slope
RELIEF_IN = 1.0  # inner stringer and its plate only
PLATE_TOP_IN = 0.6171 + 0.0273  # plate top below the upper tread's bolt row (auto height)
PLATE_BOTTOM_IN = 1.6717 - 0.0273  # plate bottom above the lower tread's bolt row
_BOLT_ROW_IN = TREAD_MARK_IN / 2.0 - 0.75  # a tread's bolt row below its center
_ARC_STEPS = 8

Point = tuple[float, float]


@dataclass(frozen=True)
class SplitSettings:
    """The launcher's Stringer splitters box. ``plate_height_in`` None is Auto: rise less 2.2888 in."""

    mode: str = LIMIT
    segments: int = SEGMENT_COUNT
    max_span_ft: float = MAX_SPAN_FT
    plate_height_in: float | None = None
    hole_row_in: float = HOLE_ROW_IN

    def __post_init__(self) -> None:
        if self.mode not in (LIMIT, SEGMENTS):
            raise ValueError("Split by Max span or by Segments.")
        if self.mode == SEGMENTS and self.segments < 1:
            raise ValueError("Enter a positive whole number of stringer segments.")
        if self.mode == LIMIT and self.max_span_ft <= 0:
            raise ValueError("Enter a positive maximum stringer vertical span in feet.")
        if self.plate_height_in is not None and self.plate_height_in <= 0:
            raise ValueError("The splice plate height must be greater than zero, or blank for Auto.")
        if self.hole_row_in <= 0:
            raise ValueError("The hole row offset must be greater than zero.")


@dataclass(frozen=True)
class Joint:
    """One cut in one stringer: between local treads ``tread`` and ``tread + 1`` of its flight."""

    tread: int
    y_cut: float
    plate: tuple[Point, ...]  # closed outline, the relief arc in it for the inner stringer
    holes: tuple[Point, ...]  # four centers, in the plate and the stringer alike


def segment_count(dev: DevelopedStringer, treads: int, settings: SplitSettings) -> int | None:
    """Pieces for this flight, or None when it cannot have that many (more pieces than treads)."""
    if settings.mode == SEGMENTS:
        count = max(1, settings.segments)
    else:
        span_ft = _vertical_span_in(dev, treads) / 12.0
        count = max(1, math.ceil(span_ft / max(settings.max_span_ft, 1e-6) - 1e-9))
    return None if count > treads else count


def cut_treads(treads: int, segments: int) -> list[int]:
    """The lower tread of each cut: the flight's tread intervals shared out from tread 1."""
    cuts: list[int] = []
    for i in range(1, segments):
        tread = 1 + int(i * (float(treads - 1) / float(segments)))
        if tread < treads and tread not in cuts:
            cuts.append(tread)
    return cuts


def joints(dev: DevelopedStringer, rise_in: float, treads: int, settings: SplitSettings) -> list[Joint]:
    """Every cut of one stringer in one flight, with its splice plate and holes."""
    count = segment_count(dev, treads, settings)
    if count is None or count < 2:
        return []
    inner = dev.side == "inner"
    found = []
    for tread in cut_treads(treads, count):
        y_cut = (tread + 0.5) * rise_in
        if settings.plate_height_in is None:
            y_bottom = tread * rise_in - _BOLT_ROW_IN + PLATE_BOTTOM_IN
            y_top = (tread + 1) * rise_in - _BOLT_ROW_IN - PLATE_TOP_IN
        else:
            y_bottom = y_cut - settings.plate_height_in / 2.0
            y_top = y_cut + settings.plate_height_in / 2.0
        corners = [
            (top_x(dev, y_bottom), y_bottom),
            (bottom_x(dev, y_bottom), y_bottom),
            (bottom_x(dev, y_top), y_top),
            (top_x(dev, y_top), y_top),
        ]
        plate = _fillet(corners, 2, RELIEF_IN) if inner else corners
        rows = (y_cut + settings.hole_row_in, y_cut - settings.hole_row_in)
        fallback = ((y_top + y_cut + GAP_IN / 2.0) / 2.0, (y_bottom + y_cut - GAP_IN / 2.0) / 2.0)
        rows = tuple(row if y_bottom < row < y_top else spare for row, spare in zip(rows, fallback, strict=True))
        slant = HOLE_INSET_IN / math.sin(dev.pitch_rad)
        holes = tuple(
            point for y in rows for point in ((top_x(dev, y) + slant, y), (bottom_x(dev, y) - slant, y))
        )
        found.append(Joint(tread, y_cut, tuple(plate), holes))
    return found


def pieces(dev: DevelopedStringer, cuts: list[Joint]) -> list[tuple[Point, ...]]:
    """The stringer's burn outline between its cuts, lowest piece first. The inner stringer's joint
    corners that make an acute angle get the relief radius."""
    inner = dev.side == "inner"
    outline = list(dev.outline)
    result = []
    lows = [-math.inf] + [joint.y_cut + GAP_IN / 2.0 for joint in cuts]
    highs = [joint.y_cut - GAP_IN / 2.0 for joint in cuts] + [math.inf]
    for low, high in zip(lows, highs, strict=True):
        piece = _clip(_clip(outline, low, keep_above=True), high, keep_above=False)
        if inner:
            piece = _relieve(piece, dev, low, high)
        result.append(tuple(piece))
    return result


def holes_in(piece: tuple[Point, ...], centers, radius: float) -> list[Point]:
    """The holes wholly inside a piece: a hole across a cut belongs to neither."""
    kept = []
    for cx, cy in centers:
        probes = [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in
                  (2.0 * math.pi * k / 24 for k in range(24))]
        if all(_inside(point, piece) for point in probes):
            kept.append((cx, cy))
    return kept


def _vertical_span_in(dev: DevelopedStringer, treads: int) -> float:
    """Tread 1 to the top tread, plus the drop at the foot: the lisp's SPLITCOUNT span."""
    first, last = dev.tread_centers[0], dev.tread_centers[treads - 1]
    return abs(last[1] - first[1]) + DROP_IN


def top_x(dev: DevelopedStringer, y: float) -> float:
    """Where the stringer's top edge is at height y: it runs through tread 1's top trailing corner."""
    first = dev.tread_centers[0]
    return first[0] - TREAD_DEPTH_IN / 2.0 + (y - (first[1] + TREAD_MARK_IN / 2.0)) / math.tan(dev.pitch_rad)


def bottom_x(dev: DevelopedStringer, y: float) -> float:
    """The bottom edge, the stringer's depth square to the slope below the top (the lisp's 9 in)."""
    return top_x(dev, y) + dev.plate_width_in / math.sin(dev.pitch_rad)


def _clip(outline: list[Point], level: float, *, keep_above: bool) -> list[Point]:
    """Sutherland-Hodgman against the level line y = ``level``."""
    if math.isinf(level):
        return outline

    def keep(point: Point) -> bool:
        return point[1] >= level if keep_above else point[1] <= level

    out: list[Point] = []
    for i, current in enumerate(outline):
        previous = outline[i - 1]
        if keep(current):
            if not keep(previous):
                out.append(_cross(previous, current, level))
            out.append(current)
        elif keep(previous):
            out.append(_cross(previous, current, level))
    return out


def _cross(a: Point, b: Point, level: float) -> Point:
    t = (level - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), level)


def _relieve(piece: list[Point], dev: DevelopedStringer, low: float, high: float) -> list[Point]:
    """Round the cut's acute corners: on a piece's top cut, where it meets the bottom edge; on its bottom
    cut, where it meets the top edge."""
    for level, x_at in ((high, bottom_x), (low, top_x)):
        if math.isinf(level):
            continue
        corner = (x_at(dev, level), level)
        for index, point in enumerate(piece):
            if math.dist(point, corner) < 1e-6:
                piece = _fillet(piece, index, RELIEF_IN)
                break
    return piece


def _fillet(outline: list[Point], index: int, radius: float) -> list[Point]:
    """Replace the corner at ``index`` with a tangent arc of ``radius``, as points."""
    corner = outline[index]
    before, after = outline[index - 1], outline[(index + 1) % len(outline)]
    u = _unit(before[0] - corner[0], before[1] - corner[1])
    v = _unit(after[0] - corner[0], after[1] - corner[1])
    angle = math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1])))
    reach = radius / math.tan(angle / 2.0)
    reach = min(reach, 0.45 * math.dist(corner, before), 0.45 * math.dist(corner, after))
    radius = reach * math.tan(angle / 2.0)
    start = (corner[0] + u[0] * reach, corner[1] + u[1] * reach)
    end = (corner[0] + v[0] * reach, corner[1] + v[1] * reach)
    bisector = _unit(u[0] + v[0], u[1] + v[1])
    middle = math.hypot(radius, reach)
    center = (corner[0] + bisector[0] * middle, corner[1] + bisector[1] * middle)
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = math.remainder(a1 - a0, 2.0 * math.pi)
    arc = [(center[0] + radius * math.cos(a0 + sweep * k / _ARC_STEPS),
            center[1] + radius * math.sin(a0 + sweep * k / _ARC_STEPS)) for k in range(_ARC_STEPS + 1)]
    return outline[:index] + arc + outline[index + 1:]


def _unit(x: float, y: float) -> Point:
    length = math.hypot(x, y)
    return (x / length, y / length)


def _inside(point: Point, outline) -> bool:
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(outline, list(outline[1:]) + [outline[0]], strict=True):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside
