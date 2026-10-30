"""The stair game: the attachments as pieces to pick from a tray and drop on the stringers, without Tk.

``Game`` holds what the user did (pins and thrown-away items, with an undo history) and works the plan out
from it with ``attachments.plan``; ``slot`` turns a pointer on a lane into the tread a dragged piece would snap
to, and ``Game.try_drop`` says green or red and why. The Tk view (``stretchout.game_gui``) only draws it.

A lane is one stringer of one flight as the developed-stringer sheet draws it: x along the climb, y up,
inches, the flight's tread ``i`` at ``dev.tread_centers[i - 1]``. The view draws every flight's lanes on the
shell's stretchout, by angle round the tank (``view_x``) and height; ``pad_box`` puts a clip's or knee brace's
shell pad on its lane the same way, and ``lane_rails`` the handrail.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from swauto.stair.attachments import (
    CLIP,
    GROUND,
    INNER,
    KNEE,
    NO_CUTS,
    OUTER,
    POST,
    RAIL_SPLIT,
    SPLICE,
    Plan,
    Rules,
    Shell,
    Spot,
    check,
    plan,
)
from swauto.stair.development import DevelopedStringer
from swauto.stair.grab_sw import GRAB_TOP_IN, PIPE_OD_IN
from swauto.stair.landings import StairArrangement, clip_mark, knee_mark
from swauto.stair.post_sw import RAIL_TOP_IN, TOP_GAP_IN
from swauto.stair.rail_sw import BAR_IN, MID_TOP_IN
from swauto.stair.stair_sw import InnerRail
from swauto.stair.stringer import TREAD_DEPTH_IN

ANGLE_IN = 2.0  # the L2x2 top rail
INNER_POST_TOP_IN = InnerRail.post_top


@dataclass(frozen=True)
class Piece:
    """One thing in the tray: what it places and on which stringer."""

    name: str
    kind: str
    side: str = ""

    def lanes(self) -> tuple[str, ...]:
        """The stringers it can go on."""
        if self.kind in (POST, RAIL_SPLIT):
            return (self.side,)
        if self.kind in (CLIP, KNEE):
            return (INNER,)  # the clip and the knee brace go to the shell, by the inner stringer
        return (INNER, OUTER)


TRAY = (
    Piece("Post (outside)", POST, OUTER),
    Piece("Post (inside)", POST, INNER),
    Piece("Inner clip", CLIP),
    Piece("Knee brace", KNEE),
    Piece("Stringer splitter", SPLICE),
    Piece("Rail splitter (outside)", RAIL_SPLIT, OUTER),
    Piece("Rail splitter (inside)", RAIL_SPLIT, INNER),
)


@dataclass(frozen=True)
class Choice:
    pins: tuple[Spot, ...] = ()
    removed: tuple[tuple, ...] = ()


@dataclass
class Game:
    arrangement: StairArrangement
    shell: Shell | None = None
    rules: Rules = Rules()
    choice: Choice = Choice()
    history: list[Choice] = field(default_factory=list)
    _plan: Plan | None = None

    @property
    def plan(self) -> Plan:
        if self._plan is None:
            self._plan = plan(self.arrangement, self.shell, self.rules, self.choice.pins, self.choice.removed)
        return self._plan

    def _set(self, choice: Choice) -> None:
        self.history.append(self.choice)
        self.choice = choice
        self._plan = None

    def try_drop(self, piece: Piece, flight: int, tread: int, moving: Spot | None = None) -> tuple[bool, str]:
        """Green or red for ``piece`` dropped at ``tread`` of ``flight`` (``moving`` the item being moved), and why."""
        spot = Spot(piece.kind, flight, tread, _side(piece, moving))
        current = self.plan
        if moving is not None:
            current = replace(current, spots=tuple(s for s in current.spots if s.key() != moving.key()),
                              cuts=tuple(j for j in current.cuts if not (moving.kind == SPLICE and j == moving.tread)))
        if any(s.key() == spot.key() for s in current.spots):
            return False, "There is one there already."
        return check(self.arrangement, current, spot, self.shell, self.rules)

    def drop(self, piece: Piece, flight: int, tread: int, moving: Spot | None = None) -> tuple[bool, str]:
        """Place ``piece`` (or move ``moving`` there) if it goes; pinned, so the rules leave it. (placed, why)"""
        ok, reason = self.try_drop(piece, flight, tread, moving)
        if not ok:
            return False, reason
        spot = Spot(piece.kind, flight, tread, _side(piece, moving), pinned=True)
        pins = list(self.choice.pins)
        removed = list(self.choice.removed)
        if piece.kind == SPLICE:
            # Cuts are all the user's once one is placed: the rest stay where they are.
            kept = [j for j in self.plan.cuts if moving is None or j != moving.tread]
            pins = [p for p in pins if p.kind != SPLICE] + [Spot(SPLICE, 0, j, pinned=True) for j in kept]
            removed = [key for key in removed if key[0] != SPLICE]
            spot = Spot(SPLICE, 0, tread, pinned=True)
        elif moving is not None:
            pins, removed = _without(moving, pins, removed)
        self._set(Choice(tuple(pins) + (spot,), tuple(removed)))
        return True, reason

    def throw_away(self, spot: Spot) -> None:
        """Into the bin: a pin goes, and an item the rules placed is left out from now on."""
        pins, removed = list(self.choice.pins), list(self.choice.removed)
        if spot.kind == SPLICE:
            kept = [j for j in self.plan.cuts if j != spot.tread]
            pins = [p for p in pins if p.kind != SPLICE] + [Spot(SPLICE, 0, j, pinned=True) for j in kept]
            if not kept:  # no cut left, whatever the rules would cut round later pins
                removed = [key for key in removed if key[0] != SPLICE] + [NO_CUTS]
        else:
            pins, removed = _without(spot, pins, removed)
        self._set(Choice(tuple(pins), tuple(dict.fromkeys(removed))))

    def auto_place(self) -> None:
        """The rules again round the pinned items; the thrown-away ones come back."""
        self._set(Choice(self.choice.pins, ()))

    def start_over(self) -> None:
        self._set(Choice())

    def undo(self) -> bool:
        if not self.history:
            return False
        self.choice = self.history.pop()
        self._plan = None
        return True


def _side(piece: Piece, moving: Spot | None) -> str:
    """A moved piece keeps its side: the extra clip at the foot stays the foot's when it is moved."""
    if moving is not None and moving.kind == piece.kind and moving.side == GROUND:
        return GROUND
    return piece.side


def _without(spot: Spot, pins: list[Spot], removed: list[tuple]) -> tuple[list[Spot], list[tuple]]:
    if any(p.key() == spot.key() for p in pins):
        return [p for p in pins if p.key() != spot.key()], removed
    return pins, removed + [spot.key()]


def slot(dev: DevelopedStringer, kind: str, x: float, posts: tuple[int, ...] = ()) -> int:
    """The tread a piece of ``kind`` snaps to with the pointer at ``x`` along the lane: a post to the gap it stands
    in (below its tread), a stringer splitter to the gap it cuts (its lower tread), a rail splitter to the bay it
    is in (the post below it, of ``posts``), the rest to the nearest tread."""
    centers = [c[0] for c in dev.tread_centers]
    n = len(centers)
    if kind == RAIL_SPLIT:
        below = [t for t in sorted(posts) if spot_xy(dev, Spot(POST, 0, t))[0] <= x]
        return below[-1] if below else (min(posts) if posts else 1)
    if kind == POST:
        x += _step(centers) / 2.0  # a post stands half a tread below its own tread
    if kind == SPLICE:
        x -= _step(centers) / 2.0  # the gap above the tread
    nearest = min(range(n), key=lambda i: abs(centers[i] - x))
    return nearest + 1


def _step(centers: list[float]) -> float:
    return (centers[-1] - centers[0]) / (len(centers) - 1) if len(centers) > 1 else 10.0


def spot_xy(dev: DevelopedStringer, spot: Spot, posts: tuple[int, ...] = ()) -> tuple[float, float]:
    """Where a placed item is drawn on its lane: a post's foot, a clip's middle, a knee brace's top, a cut's
    middle, a rail split at rail height in the middle of its bay (up to the next of ``posts``)."""
    centers = dev.tread_centers
    x, y = centers[min(spot.tread, len(centers)) - 1]
    step = _step([c[0] for c in centers])
    rise = (centers[-1][1] - centers[0][1]) / (len(centers) - 1) if len(centers) > 1 else 7.5
    if spot.kind == POST:
        return x - step / 2.0, y - rise / 2.0
    if spot.kind == CLIP:
        return x + 2.9, y + 4.25
    if spot.kind == KNEE:
        return x, y - 4.0
    if spot.kind == SPLICE:
        return x + step / 2.0, y + rise / 2.0
    low = spot_xy(dev, Spot(POST, 0, spot.tread))
    above = [t for t in sorted(posts) if t > spot.tread]
    high = spot_xy(dev, Spot(POST, 0, above[0])) if above else (low[0] + step, low[1] + rise)
    x = (low[0] + high[0]) / 2.0
    if spot.side == INNER:
        return x, edge_y(dev, x) + GRAB_TOP_IN - PIPE_OD_IN / 2.0
    return x, edge_y(dev, x) + RAIL_TOP_IN - ANGLE_IN / 2.0


def edge_y(dev: DevelopedStringer, x: float) -> float:
    """The stringer's top edge at ``x``: the straight line its middle runs along, carried on past its ends."""
    xs = [c[0] for c in dev.tread_centers]
    middle = (min(xs) + max(xs)) / 2.0
    return max(_crossings(dev.outline, middle)) + (x - middle) * math.tan(dev.pitch_rad)


def post_top(dev: DevelopedStringer, side: str, x: float) -> float:
    """A post's top cut at ``x``: under the top rail outside, under the pipe's bracket inside."""
    if side == INNER:
        return edge_y(dev, x) + INNER_POST_TOP_IN
    return edge_y(dev, x) + RAIL_TOP_IN - TOP_GAP_IN


@dataclass(frozen=True)
class Rail:
    """One rail of a flight on its lane, along its top edge from x0 to x1, ``tall`` deep, in the lane's inches."""

    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    tall: float


def lane_rails(dev: DevelopedStringer, side: str, posts: tuple[int, ...], top: bool = True, mid: bool = True,
               grab: bool = True) -> list[Rail]:
    """The flight's handrail on ``side``'s lane, as the build runs it: outside, the top rail and the midrail from
    the first post to the last and the grab rail pipe from tread 1's front edge to the top tread's; inside, the
    pipe alone, as long. Nothing without posts on that side."""
    if not posts:
        return []
    feet = [spot_xy(dev, Spot(POST, 0, t))[0] for t in sorted(posts)]
    fronts = (dev.tread_centers[0][0] - TREAD_DEPTH_IN / 2.0, dev.tread_centers[-1][0] - TREAD_DEPTH_IN / 2.0)
    wanted = [("Pipe", GRAB_TOP_IN, PIPE_OD_IN, fronts)] if side == INNER else (
        ([("Top rail", RAIL_TOP_IN, ANGLE_IN, (feet[0], feet[-1]))] if top else [])
        + ([("Midrail", MID_TOP_IN, BAR_IN, (feet[0], feet[-1]))] if mid else [])
        + ([("Grab rail", GRAB_TOP_IN, PIPE_OD_IN, fronts)] if grab else []))
    return [Rail(name, a, edge_y(dev, a) + above, b, edge_y(dev, b) + above, tall)
            for name, above, tall, (a, b) in wanted if b > a]


def view_x(arrangement: StairArrangement, angle: float, girth_in: float) -> float:
    """Where the clockwise build's plan ``angle`` is across the shell's stretchout, seen from outside: the
    stretchout's x (``x_of_angle``), carried on past its ends rather than wrapped, so a stair runs on unbroken."""
    return -arrangement.world(angle) / (2.0 * math.pi) * girth_in


def view_angle(arrangement: StairArrangement, x_in: float, girth_in: float) -> float:
    """``view_x`` turned round: the build's plan angle at stretchout ``x_in``."""
    angle = -x_in / girth_in * 2.0 * math.pi - arrangement.turn
    return -angle if arrangement.ccw else angle


def pad_box(arrangement: StairArrangement, where, inner: DevelopedStringer, spot: Spot) -> tuple | None:
    """The shell pad of the clip or knee brace ``spot`` as (x0, y0, x1, y1) on its flight's inner lane, or None
    where the build would not place it. ``where`` is the stair's ``stair_places``, ``inner`` its inner
    development."""
    mark = (knee_mark if spot.kind == KNEE else clip_mark)(where, arrangement.platforms, spot.pan(where.per_flight))
    if isinstance(mark, str):
        return None
    turn, lift = where.offsets[spot.flight]
    (angle, y), (wide, tall) = mark.center, mark.size
    x = (angle - turn) * inner.radius_in
    half = wide / 2.0 / where.flight.shell_od_in * inner.radius_in
    return x - half, y - lift - tall / 2.0, x + half, y - lift + tall / 2.0


def _crossings(outline, x: float) -> list[float]:
    """The heights where the closed ``outline`` crosses the plumb line at ``x``."""
    ys = []
    for (x0, y0), (x1, y1) in zip(outline, list(outline[1:]) + list(outline[:1]), strict=True):
        if (x0 - x) * (x1 - x) <= 0 and x0 != x1:
            ys.append(y0 + (x - x0) / (x1 - x0) * (y1 - y0))
    return ys


def span_at(outline, x: float) -> tuple[float, float] | None:
    """The bottom and top of the closed ``outline`` over ``x``, or None past its ends."""
    ys = _crossings(outline, x)
    return (min(ys), max(ys)) if len(ys) >= 2 else None
