"""Stringer splitter: where a long stringer is cut into pieces and spliced, from the lisp's SPLITSTRING.

Everything is in one flight's development (``development.py``): x along the climb, y up,
inches, tread i centered at i rises. A flight is cut level (constant y) between two treads,
midway between their centers, with a 1/4 in gap. How many pieces: the flight's vertical span
(its treads plus the 5-1/4 in drop at the foot) over the max span, or a set number; the cuts
share the tread intervals out from tread 1, the same treads on the inner and outer stringer.

Each joint gets one splice plate: a parallelogram whose top and bottom are level and whose
sides lie on the stringer's top and bottom edges, so it covers the stringer's full depth. Four
13/16 holes go through plate and stringer alike, two rows, one each side of the cut (Auto, as
below, or where typed, such as the lisp's 1-5/8 in), each hole 1-1/2 in in from an edge, square to
the slope. On the inner stringer the joint's two acute corners get a 1 in relief radius, and so does
the plate's top acute corner; the outer stringer's are sharp.

The plate goes on the stringer's back face and the treads on its walk face. The app works the joint
out so nothing is in its way. The cuts are the lisp's even shares unless one is beside a tread with a
post or a cross brace (``SplitSettings.avoid``) or in a flight's end tread gap; then they move to
the clear gaps that keep the pieces within the max span. Each Auto hole row sits midway between the
cut's burn line and the plate's edge, the same steel each way, or nearer the cut (not under 1-1/8 in,
1 in of edge from the burn line) until its bolts' washers are off the treads' end walls and the tread
bolts' washers; the rows above and below the cut move on their own. ``clashes`` says what is still
in the way: a splice bolt's washer on a tread's end wall or a tread bolt's washer, the plate on a
tread bolt's washer (its nut is on the back face, with the plate), a hole off the plate, a post
or brace beside the cut, a cut by a flight's end clips, or a plate too short for its round.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass

from swauto.stair.development import DROP_IN, DevelopedStringer, tread_rect
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
# The treads are bolted on at the shop before the splices go on, so no socket has to reach past a plate: each bolt
# needs only its washer's room (Anton, 2026-10-29).
SPLICE_WASHER_OD_IN = 1.46875  # hardened washer of a 3/4 in splice bolt (13/16 in holes)
TREAD_WASHER_OD_IN = 1.0  # flat washer of a 3/8 in tread bolt (7/16 in holes)
MIN_ROW_IN = 1.125  # Auto hole rows come no nearer the cut: 1 in of edge from its burn line
MIN_PLATE_IN = 2.0  # a typed plate height: room for a 13/16 in hole each side of the 1/4 in gap
MIN_TYPED_ROW_IN = GAP_IN / 2.0 + HOLE_DIA_IN / 2.0  # a typed hole row nearer than this cuts into the gap
ROW_STEP_IN = 1.0 / 16.0
OVERCUT_IN = 0.25  # a round's cutter runs this far past both edges, so only its arc meets the metal
_BOLT_ROW_IN = TREAD_MARK_IN / 2.0 - 0.75  # a tread's bolt row below its center
_ARC_STEPS = 8

Point = tuple[float, float]


@dataclass(frozen=True)
class SplitSettings:
    """The launcher's Stringer splitters box. ``plate_height_in`` None is Auto: rise less 2.2888 in.
    ``hole_row_in`` None is Auto: the washers kept off the treads. ``avoid`` are the flight's treads with a post or
    a cross brace (with its knee brace or clip) on a stringer: no cut goes beside them."""

    mode: str = LIMIT
    segments: int = SEGMENT_COUNT
    max_span_ft: float = MAX_SPAN_FT
    plate_height_in: float | None = None
    hole_row_in: float | None = None
    avoid: tuple[int, ...] = ()
    fixed: tuple[int, ...] | None = None  # the cuts' lower treads as placed (by the rules or by hand), not searched

    def __post_init__(self) -> None:
        if self.mode not in (LIMIT, SEGMENTS):
            raise ValueError("Split by Max span or by Segments.")
        if self.mode == SEGMENTS and self.segments < 1:
            raise ValueError("Enter a positive whole number of stringer segments.")
        if self.mode == LIMIT and not (math.isfinite(self.max_span_ft) and self.max_span_ft > 0):
            raise ValueError("Enter a positive maximum stringer vertical span in feet.")
        if self.plate_height_in is not None and not (
            math.isfinite(self.plate_height_in) and self.plate_height_in >= MIN_PLATE_IN
        ):
            raise ValueError(f"The splice plate height must be at least {MIN_PLATE_IN:g} in, or blank for Auto.")
        if self.hole_row_in is not None and not (
            math.isfinite(self.hole_row_in) and self.hole_row_in > MIN_TYPED_ROW_IN
        ):
            raise ValueError(f"The hole rows must be more than {MIN_TYPED_ROW_IN:g} in off the cut, so each 13/16 "
                             "hole clears the 1/4 in gap, or blank for Auto.")
        object.__setattr__(self, "avoid", tuple(sorted({int(tread) for tread in self.avoid})))
        if self.fixed is not None:
            object.__setattr__(self, "fixed", tuple(sorted({int(tread) for tread in self.fixed})))


@dataclass(frozen=True)
class Joint:
    """One cut in one stringer: between local treads ``tread`` and ``tread + 1`` of its flight."""

    tread: int
    y_cut: float
    plate: tuple[Point, ...]  # closed outline, the relief arc in it for the inner stringer
    holes: tuple[Point, ...]  # four centers, in the plate and the stringer alike


@dataclass(frozen=True)
class Relief:
    """One 1 in relief round: the sliver it takes off between a corner and the arc, given by the corner and
    the arc's start, middle and end. ``piece`` is the "lower" or "upper" stringer piece, or the "plate"."""

    piece: str
    corner: Point
    start: Point
    middle: Point
    end: Point
    center: Point


def segment_count(dev: DevelopedStringer, treads: int, settings: SplitSettings) -> int | None:
    """Pieces for this flight, or None when it cannot have that many (more pieces than treads)."""
    return _count(_vertical_span_in(dev, treads), treads, settings)


def pieces_wanted(span_in: float, settings: SplitSettings) -> int:
    """The pieces the settings ask of a flight that spans ``span_in`` (the lisp's span), before checking the flight
    has that many treads."""
    if settings.mode == SEGMENTS:
        return max(1, settings.segments)
    return max(1, math.ceil(span_in / 12.0 / max(settings.max_span_ft, 1e-6) - 1e-9))


def flight_span_in(rise_in: float, treads: int) -> float:
    """A flight's span the lisp's way: tread 1 to the top tread, plus the drop at the foot."""
    return (treads - 1) * rise_in + DROP_IN


def _count(span_in: float, treads: int, settings: SplitSettings) -> int | None:
    count = pieces_wanted(span_in, settings)
    return None if count > treads else count


def choose_cuts(rise_in: float, treads: int, settings: SplitSettings) -> list[int] | None:
    """The lower tread of each cut in one flight, or None when it cannot have that many pieces.

    The lisp's even shares (``cut_treads``) unless one is beside a tread in ``settings.avoid`` or in the
    flight's first or last tread gap, by its end clips. Then the clear gaps that keep each piece within the
    max span (or make the set number of pieces) with the longest piece as short as can be, a piece more if it
    takes one. When no clear gaps keep the span (none at all, or a run of blocked gaps no piece can bridge
    within it), or too few make the set number of pieces, the lisp's shares, and ``clashes`` says what they
    are beside. Worked out once for each flight and settings: the tab asks for it on every keystroke.
    ``settings.fixed`` cuts are taken as they are.
    """
    if settings.fixed is not None:
        return [j for j in settings.fixed if 1 <= j < treads]
    cuts = _choose_cuts(rise_in, treads, settings)
    return None if cuts is None else list(cuts)


@functools.lru_cache(maxsize=64)
def _choose_cuts(rise_in: float, treads: int, settings: SplitSettings) -> tuple[int, ...] | None:
    count = _count(flight_span_in(rise_in, treads), treads, settings)
    if count is None:
        return None
    if count < 2:
        return ()
    even = cut_treads(treads, count)
    avoid = set(settings.avoid)
    blocked = {j for j in range(1, treads) if j in (1, treads - 1) or j in avoid or j + 1 in avoid}
    if not blocked & set(even):
        return tuple(even)
    free = [j for j in range(1, treads) if j not in blocked]
    if settings.mode == SEGMENTS:
        wanted = count - 1
    else:
        cap = max(settings.max_span_ft * 12.0, max(_spans(even, rise_in, treads)))
        # Some piece has to reach across each run of blocked gaps; cutting every clear gap gives the shortest
        # such reaches. When one is already over the cap no number of pieces meets it, so don't search.
        if not free or max(_spans(free, rise_in, treads)) > cap + 1e-9:
            return tuple(even)
        # The fewest cuts that keep the span, each as far up as it can go; more cuts never make the evenest
        # set's longest piece longer, so that many (or the count wanted, if more) is the answer.
        wanted = max(count - 1, _fewest_cuts(free, cap, rise_in, treads))
    cuts = _evenest(free, wanted, rise_in, treads)
    return tuple(cuts if cuts is not None else even)


def _fewest_cuts(free: list[int], cap: float, rise_in: float, treads: int) -> int:
    """How few of the ``free`` gaps keep every piece within ``cap``: up from the foot, each cut at the highest
    gap the piece below it reaches."""
    last, made, top = rise_in - DROP_IN, 0, treads * rise_in
    while top - last > cap + 1e-9:
        last = max((j + 0.5) * rise_in for j in free if last < (j + 0.5) * rise_in <= last + cap + 1e-9)
        made += 1
    return made


def _spans(cuts: list[int], rise_in: float, treads: int) -> list[float]:
    """Each piece's vertical span the lisp's way: the first from the foot's drop below tread 1, the last to the
    top tread."""
    levels = [rise_in - DROP_IN] + [(cut + 0.5) * rise_in for cut in cuts] + [treads * rise_in]
    return [b - a for a, b in zip(levels, levels[1:], strict=False)]


def _evenest(free: list[int], count: int, rise_in: float, treads: int) -> list[int] | None:
    """``count`` cuts from ``free`` (sorted), the longest piece as short as can be: for each number of cuts
    ending at each gap, the longest piece so far and the gap of the cut before, built up from the bottom."""
    if count < 1 or len(free) < count:
        return [] if count < 1 else None
    level = [(j + 0.5) * rise_in for j in free]
    foot = rise_in - DROP_IN
    best: list[list[tuple[float, int] | None]] = [[(y - foot, -1) for y in level]]
    for _made in range(2, count + 1):
        below, here = best[-1], []
        for i in range(len(free)):
            pick = None
            for p in range(i):
                if below[p] is not None:
                    longest = max(below[p][0], level[i] - level[p])
                    if pick is None or longest < pick[0]:
                        pick = (longest, p)
            here.append(pick)
        best.append(here)
    end = None
    for i, entry in enumerate(best[-1]):
        if entry is not None:
            longest = max(entry[0], treads * rise_in - level[i])
            if end is None or longest < end[0]:
                end = (longest, i)
    if end is None:
        return None
    cuts, i = [], end[1]
    for row in reversed(best):
        cuts.append(free[i])
        i = row[i][1]
    return cuts[::-1]


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
    return [_joint(dev, rise_in, tread, settings) for tread in choose_cuts(rise_in, treads, settings) or ()]


def _joint(dev: DevelopedStringer, rise_in: float, tread: int, settings: SplitSettings) -> Joint:
    """One cut's plate and holes. A typed hole row goes where it is typed, or midway between the plate's edge and
    the cut when the hole would not be wholly on the plate; Auto rows are ``_auto_row``'s."""
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
    rounded = _plate_round(dev, corners)
    # The round replaces the top acute corner, from its end on the slope to its start on the top edge.
    plate = corners if rounded is None else [*corners[:2], *_arc_points(rounded), corners[3]]
    slant = HOLE_INSET_IN / math.sin(dev.pitch_rad)

    def row(y: float) -> tuple[Point, Point]:
        """A row's two holes, each 1-1/2 in in from its edge, square to the slope."""
        return ((top_x(dev, y) + slant, y), (bottom_x(dev, y) - slant, y))

    if settings.hole_row_in is None:
        rows = (_auto_row(dev, row, y_cut, y_top), _auto_row(dev, row, y_cut, y_bottom))
    else:
        radius = HOLE_DIA_IN / 2.0
        typed = (y_cut + settings.hole_row_in, y_cut - settings.hole_row_in)
        fallback = ((y_top + y_cut + GAP_IN / 2.0) / 2.0, (y_bottom + y_cut - GAP_IN / 2.0) / 2.0)
        rows = tuple(y if y_bottom + radius <= y <= y_top - radius else spare
                     for y, spare in zip(typed, fallback, strict=True))
    return Joint(tread, y_cut, tuple(plate), tuple(point for y in rows for point in row(y)))


def _plate_round(dev: DevelopedStringer, corners) -> Relief | None:
    """The inner plate's 1 in round at its top acute corner (``corners[2]``, where its top edge meets the
    stringer's bottom edge), the one the build cuts; None on the outer stringer, or when a side next to the
    corner is too short for it (``clashes`` says so)."""
    if dev.side != "inner":
        return None
    ux, uy = math.cos(dev.pitch_rad), math.sin(dev.pitch_rad)
    rounded = _relief("plate", corners[2], (-1.0, 0.0), (-ux, -uy))
    reach = math.dist(rounded.corner, rounded.start)
    fits = reach < math.dist(corners[2], corners[1]) - 1e-9 and reach < math.dist(corners[2], corners[3]) - 1e-9
    return rounded if fits else None


def _arc_points(relief: Relief) -> list[Point]:
    """A round as points from its end to its start, its middle the middle point."""
    a0 = math.atan2(relief.end[1] - relief.center[1], relief.end[0] - relief.center[0])
    a1 = math.atan2(relief.start[1] - relief.center[1], relief.start[0] - relief.center[0])
    sweep = math.remainder(a1 - a0, 2.0 * math.pi)
    radius = math.dist(relief.center, relief.start)
    return [(relief.center[0] + radius * math.cos(a0 + sweep * k / _ARC_STEPS),
             relief.center[1] + radius * math.sin(a0 + sweep * k / _ARC_STEPS)) for k in range(_ARC_STEPS + 1)]


def _auto_row(dev: DevelopedStringer, row, y_cut: float, edge: float) -> float:
    """An Auto hole row's level on the plate's side toward ``edge``: midway between the cut's burn line and the
    plate's edge, the same steel each way; else nearer the cut a sixteenth at a time, not under ``MIN_ROW_IN``,
    until its bolts' washers are clear. When nothing clears, the even row, which ``clashes`` then reports."""
    sign = 1.0 if edge > y_cut else -1.0
    even = (abs(edge - y_cut) + GAP_IN / 2.0) / 2.0
    offset = even
    while True:
        if not _washers_meet(dev, row(y_cut + sign * offset)):
            return y_cut + sign * offset
        if offset <= MIN_ROW_IN + 1e-9:
            return y_cut + sign * even
        offset = max(MIN_ROW_IN, offset - ROW_STEP_IN)


def _washers_meet(dev: DevelopedStringer, holes) -> bool:
    """Whether any of these splice bolts' washers meets a tread's end wall or a tread bolt's washer."""
    splice, tread = SPLICE_WASHER_OD_IN / 2.0, TREAD_WASHER_OD_IN / 2.0
    return any(_circle_meets_box(hole, splice, tread_rect(center)) for center in dev.tread_centers
               for hole in holes) or any(math.dist(bolt, hole) < splice + tread - 1e-9
                                         for bolt in dev.tread_bolts for hole in holes)


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


def cut_span(dev: DevelopedStringer, joint: Joint) -> tuple[float, float]:
    """The stringer's x extent through the joint's 1/4 in gap, its end shapes included. Near a flight's end the
    stringer runs past its sloped edges there, and a cut that stops at them leaves the two pieces joined."""
    band = _clip(_clip(list(dev.outline), joint.y_cut - GAP_IN / 2.0, keep_above=True),
                 joint.y_cut + GAP_IN / 2.0, keep_above=False)
    xs = [x for x, _y in band] or [top_x(dev, joint.y_cut), bottom_x(dev, joint.y_cut)]
    return min(xs), max(xs)


def reliefs(dev: DevelopedStringer, joint: Joint) -> list[Relief]:
    """The inner stringer's rounds at a joint, as ``pieces`` and the plate outline draw them: the lower piece's
    top cut where it meets the bottom edge, the upper piece's bottom cut where it meets the top edge (each only
    where that corner is on the piece and the round fits it), and the plate's top acute corner. The outer
    stringer has none."""
    if dev.side != "inner":
        return []
    ux, uy = math.cos(dev.pitch_rad), math.sin(dev.pitch_rad)
    low, high = joint.y_cut - GAP_IN / 2.0, joint.y_cut + GAP_IN / 2.0
    lower = _clip(list(dev.outline), low, keep_above=False)
    upper = _clip(list(dev.outline), high, keep_above=True)
    found = []
    for piece, outline, corner, along, edge in (
        ("lower", lower, (bottom_x(dev, low), low), (-1.0, 0.0), (-ux, -uy)),
        ("upper", upper, (top_x(dev, high), high), (1.0, 0.0), (ux, uy)),
    ):
        index = _corner_index(outline, corner)
        if index is not None and _round_fits(outline, index, rounded := _relief(piece, corner, along, edge)):
            found.append(rounded)
    rounded = _plate_round(dev, _plate_corners(dev, joint))
    return found + ([rounded] if rounded is not None else [])


def _plate_corners(dev: DevelopedStringer, joint: Joint) -> list[Point]:
    """The plate's four corners before its round: level top and bottom, sides on the stringer's edges."""
    y_bottom, y_top = min(y for _x, y in joint.plate), max(y for _x, y in joint.plate)
    return [(top_x(dev, y_bottom), y_bottom), (bottom_x(dev, y_bottom), y_bottom),
            (bottom_x(dev, y_top), y_top), (top_x(dev, y_top), y_top)]


def relief_cutter(relief: Relief, margin: float = OVERCUT_IN) -> tuple[Point, ...]:
    """The straight part of a round's cutting loop: from the arc's start out past its edge, round the corner
    outside the metal, and in to the arc's end; the arc (end, middle, start) closes it. A cutter that stopped on
    the edges left slivers along them: the rolled stringer's edges are a hair off the flat development's lines."""
    corner = relief.corner
    u = _unit(relief.start[0] - corner[0], relief.start[1] - corner[1])
    v = _unit(relief.end[0] - corner[0], relief.end[1] - corner[1])
    n_u, n_v = _away(u, v), _away(v, u)
    half = math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))) / 2.0
    bisector = _unit(u[0] + v[0], u[1] + v[1])
    out = margin / math.sin(half)  # where the two edges, each moved out by the margin, meet
    return (
        relief.start,
        (relief.start[0] + n_u[0] * margin, relief.start[1] + n_u[1] * margin),
        (corner[0] - bisector[0] * out, corner[1] - bisector[1] * out),
        (relief.end[0] + n_v[0] * margin, relief.end[1] + n_v[1] * margin),
        relief.end,
    )


def _treads(numbers: list[int]) -> str:
    return f"tread {numbers[0]}" if len(numbers) == 1 else f"treads {' and '.join(map(str, numbers))}"


def _away(edge: Point, other: Point) -> Point:
    """The unit normal of ``edge`` on the side away from ``other``: out of the metal."""
    normal = (-edge[1], edge[0])
    return normal if normal[0] * other[0] + normal[1] * other[1] < 0 else (edge[1], -edge[0])


def clashes(dev: DevelopedStringer, cuts: list[Joint], avoid: tuple[int, ...] = ()) -> list[str]:
    """What each joint still runs into on this stringer, as notes: a splice bolt's washer on a tread's end wall
    (the treads are on the walk face) or on a tread bolt's washer, the plate on a tread bolt's washer (its nut is
    on the back face, with the plate), a splice hole off the plate, a post or cross brace at a tread beside
    the cut (``avoid``), a cut in the flight's first or last tread gap (by its end clips), or an inner plate too
    short for its 1 in round."""
    found: list[str] = []
    last = len(dev.tread_centers) - 1
    for joint in cuts:
        where = f"{dev.side.capitalize()} stringer splice over tread {joint.tread}"
        found.extend(f"{where}: {text}" for text in _row_clashes(dev, joint))
        for number in range(1, len(dev.tread_centers) + 1):
            bolts = dev.tread_bolts[2 * (number - 1):2 * number]
            if any(_circle_meets_outline(bolt, TREAD_WASHER_OD_IN / 2.0, joint.plate) for bolt in bolts):
                found.append(f"{where}: the plate is on a tread {number} bolt's washer.")
        if len(holes_in(joint.plate, joint.holes, HOLE_DIA_IN / 2.0)) < len(joint.holes):
            found.append(f"{where}: a splice hole runs off the plate; make the plate taller or the hole rows nearer.")
        beside = sorted({joint.tread, joint.tread + 1} & set(avoid))
        if beside:
            found.append(f"{where}: {_treads(beside)} {'has' if len(beside) == 1 else 'have'} a post or brace.")
        if joint.tread in (1, last):
            found.append(f"{where}: the cut is in the flight's {'first' if joint.tread == 1 else 'last'} tread gap, "
                         "by its end clips.")
        if dev.side == "inner" and _plate_round(dev, _plate_corners(dev, joint)) is None:
            found.append(f"{where}: the plate is too short for its 1 in round; its corner is left square.")
    return found


def _row_clashes(dev: DevelopedStringer, joint: Joint) -> list[str]:
    """What the splice bolts' washers run into, which the hole rows can move off: a tread's end wall on the walk
    face, or a tread bolt's washer (on the back face its nut sits beside the plate)."""
    splice, tread = SPLICE_WASHER_OD_IN / 2.0, TREAD_WASHER_OD_IN / 2.0
    found = []
    for number, center in enumerate(dev.tread_centers, start=1):
        bolts = dev.tread_bolts[2 * (number - 1):2 * number]
        if any(_circle_meets_box(hole, splice, tread_rect(center)) for hole in joint.holes):
            found.append(f"a splice bolt's washer runs into tread {number}'s end wall.")
        if any(math.dist(bolt, hole) < splice + tread - 1e-9 for bolt in bolts for hole in joint.holes):
            found.append(f"a splice bolt's washer meets a tread {number} bolt's washer.")
    return found


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
    cut, where it meets the top edge. The full 1 in round ``reliefs`` gives the build, or none where it does
    not fit."""
    for level, x_at in ((high, bottom_x), (low, top_x)):
        if math.isinf(level):
            continue
        corner = (x_at(dev, level), level)
        index = _corner_index(piece, corner)
        if index is None:
            continue
        before, after = piece[index - 1], piece[(index + 1) % len(piece)]
        # The arc runs end to start, so the end goes on the side of the point before the corner.
        rounded = _relief("", corner, _unit(after[0] - corner[0], after[1] - corner[1]),
                          _unit(before[0] - corner[0], before[1] - corner[1]))
        if _round_fits(piece, index, rounded):
            piece = piece[:index] + _arc_points(rounded) + piece[index + 1:]
    return piece


def _corner_index(outline, corner: Point) -> int | None:
    return next((index for index, point in enumerate(outline) if math.dist(point, corner) < 1e-6), None)


def _round_fits(outline, index: int, rounded: Relief) -> bool:
    """The round's tangent points fall short of the corner's neighbours on the outline."""
    reach = math.dist(rounded.corner, rounded.start)
    return all(reach < math.dist(rounded.corner, outline[k % len(outline)]) - 1e-9 for k in (index - 1, index + 1))


def _relief(piece: str, corner: Point, u: Point, v: Point) -> Relief:
    """The ``RELIEF_IN`` round in the corner whose edges leave ``corner`` along unit vectors ``u`` and ``v``."""
    angle = math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1])))
    reach = RELIEF_IN / math.tan(angle / 2.0)
    bisector = _unit(u[0] + v[0], u[1] + v[1])
    out = math.hypot(RELIEF_IN, reach)
    center = (corner[0] + bisector[0] * out, corner[1] + bisector[1] * out)
    return Relief(
        piece,
        corner,
        (corner[0] + u[0] * reach, corner[1] + u[1] * reach),
        (center[0] - bisector[0] * RELIEF_IN, center[1] - bisector[1] * RELIEF_IN),
        (corner[0] + v[0] * reach, corner[1] + v[1] * reach),
        center,
    )


def _circle_meets_box(center: Point, radius: float, box) -> bool:
    """Overlap, not touching: a washer just touching a wall still sits flat."""
    xs, ys = [x for x, _y in box], [y for _x, y in box]
    nearest = (min(max(center[0], min(xs)), max(xs)), min(max(center[1], min(ys)), max(ys)))
    return math.dist(center, nearest) < radius - 1e-9


def _circle_meets_outline(center: Point, radius: float, outline) -> bool:
    if _inside(center, outline):
        return True
    for a, b in zip(outline, list(outline[1:]) + [outline[0]], strict=True):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((center[0] - a[0]) * dx + (center[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
        if math.dist(center, (a[0] + t * dx, a[1] + t * dy)) < radius - 1e-9:
            return True
    return False


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
