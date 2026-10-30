"""Where the stair's attachments go, by Elite's rules (2026-10-29), worked out without SolidWorks.

The order, so nothing waits on what comes after it:

1. The stringer cuts (``splitter.choose_cuts``), kept off the treads of pinned items only. Every flight is cut
   at the same treads, as the build cuts them.
2. Each stringer piece gets one knee brace (with its cross brace) and one inner clip, as near the piece's middle
   as they go: never beside a cut, and their shell pads off every weld seam by ``seam_clear_in`` (the floor and
   the shell's top count as welds), off the nozzles, FTCOs and anchor chairs, and off each other. The same tread
   for both when one suits both about as well.
3. The first piece from the ground gets an extra inner clip at tread 1, or the nearest tread above it that
   passes, so the stringer's foot is held (Anton).
4. Handrail posts, each flight and each side asked for: at the bottom of the run (local tread 2: a post stands
   on the tread below its own), at the top, and every ``post_every`` tread gaps between; one that would stand
   on a cut, beside a cross brace or, on the inner stringer, on an inner clip moves a tread up or down.
5. Rail splits, each flight and side: in the middle of a bay between two posts, wherever the rail would run past
   its stock length (40 ft angle and flat bar outside, 20 ft pipe inside).

``Spot``s the user pinned (dragged into place) stay where they are, and the rest re-flow round them; ``removed``
are the keys of placed items the user threw away, which the rules then leave out (a knee brace or clip thrown
off a piece leaves that piece without one). Treads are flight-local (1 the lowest of its flight) and flights are
0-based; ``Spot.pan`` is the app's brace numbering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from swauto.stair.development import flight_treads
from swauto.stair.landings import Mark, StairArrangement, clip_mark, knee_mark
from swauto.stair.splitter import SplitSettings, choose_cuts
from swauto.stair.stair_sw import StairPlaces, stair_places
from swauto.stair.stringer import THICKNESS_IN
from swauto.stretchout.checks import _outlines_meet, crosses
from swauto.stretchout.model import Item, Seam, Stretchout, _slot, build_stretchout, x_of_angle

KNEE = "knee brace"
CLIP = "inner clip"
POST = "handrail post"
SPLICE = "stringer splitter"
RAIL_SPLIT = "handrail splitter"
KINDS = (POST, CLIP, KNEE, SPLICE, RAIL_SPLIT)
OUTER = "outer"
INNER = "inner"
GROUND = "ground"  # the side of the extra inner clip at the foot of flight 1, kept apart from its piece's clip
NO_CUTS = (SPLICE, -1, 0, "")  # a removed key: every cut thrown away, whatever the rules would cut

SEAM_CLEAR_IN = 1.0  # a pad's edge to a weld seam's line; not in the lisp or the drawings: to confirm
POST_EVERY = 4  # tread gaps between posts (the user)
OUTER_RAIL_FT = 40.0  # stock lengths, Elite STWC (angle, flat bar) and STWE (inside pipe)
INNER_RAIL_FT = 20.0


@dataclass(frozen=True)
class Spot:
    """One placed item. ``tread`` is flight-local: the tread a knee brace, clip or post is at, the lower tread of
    a stringer cut's gap, or the lower post of a handrail split's bay. ``side`` is for posts and rail splits."""

    kind: str
    flight: int
    tread: int
    side: str = ""
    pinned: bool = False

    def key(self) -> tuple[str, int, int, str]:
        return (self.kind, self.flight, self.tread, self.side)

    def pan(self, per_flight: int) -> int:
        return self.flight * per_flight + self.tread

    def label(self) -> str:
        where = f"flight {self.flight + 1}, tread {self.tread}"
        if self.kind == SPLICE:
            where = f"flight {self.flight + 1}, between treads {self.tread} and {self.tread + 1}"
        elif self.kind == RAIL_SPLIT:
            where = f"flight {self.flight + 1}, in the bay above the tread {self.tread} post"
        side = f"{self.side} " if self.side else ""
        return f"{side}{self.kind}, {where}".capitalize()


@dataclass(frozen=True)
class Shell:
    """What the pads must keep off: the shell's weld seams, its height, and the nozzles, FTCOs and anchor
    chairs on it (``Stretchout`` items that land), in stretchout inches."""

    girth_in: float
    height_in: float
    seams: tuple[Seam, ...] = ()
    landings: tuple[Item, ...] = ()

    @staticmethod
    def of(out: Stretchout) -> Shell:
        return Shell(out.girth_in, out.height_in, out.seams, tuple(item for item in out.items if item.lands))


@dataclass(frozen=True)
class Rules:
    seam_clear_in: float = SEAM_CLEAR_IN
    post_every: int = POST_EVERY
    sides: tuple[str, ...] = (OUTER,)  # which stringers carry a handrail
    outer_rail_ft: float = OUTER_RAIL_FT
    inner_rail_ft: float = INNER_RAIL_FT
    ground_clip: bool = True


@dataclass(frozen=True)
class Plan:
    spots: tuple[Spot, ...]
    cuts: tuple[int, ...]  # the lower tread of each cut, every flight
    warnings: tuple[str, ...] = ()

    def of_kind(self, kind: str, side: str | None = None) -> list[Spot]:
        return [s for s in self.spots if s.kind == kind and (side is None or s.side == side)]


@dataclass
class _Context:
    arrangement: StairArrangement
    where: StairPlaces
    shell: Shell | None
    rules: Rules
    removed: frozenset = frozenset()
    pads: list[Item] = field(default_factory=list)  # the stair pads placed so far

    @property
    def per_flight(self) -> int:
        return self.where.per_flight

    @property
    def flights(self) -> int:
        return len(self.where.offsets)


def plan(arrangement: StairArrangement, shell: Shell | None = None, rules: Rules = Rules(),
         pins: tuple[Spot, ...] = (), removed: tuple[tuple, ...] = ()) -> Plan:
    """Every attachment by the rules, round the ``pins`` and leaving out the ``removed`` keys. ``shell`` None leaves
    the seams unchecked (no tank)."""
    where = stair_places(arrangement.stair, arrangement.stair.shell_od_in, arrangement.platforms,
                         arrangement.ground_in)
    ctx = _Context(arrangement, where, shell, rules, frozenset(removed))
    warnings: list[str] = []
    if shell is None:
        warnings.append("No tank: the pads are not checked against the shell's seams.")
    pins = tuple(replace(p, pinned=True) for p in pins
                 if 0 <= p.flight < ctx.flights and 1 <= p.tread <= ctx.per_flight  # a stair since made smaller
                 and (p.kind not in (POST, RAIL_SPLIT) or p.side in ctx.rules.sides))  # a handrail side not asked for
    spots: list[Spot] = []

    cuts = _cuts(ctx, pins, warnings)
    spots += [Spot(SPLICE, k, j, pinned=any(p.kind == SPLICE and p.tread == j for p in pins))
              for k in range(ctx.flights) for j in cuts]

    for pin in pins:
        if pin.kind in (KNEE, CLIP):
            ok, reason = _pad_ok(ctx, pin, cuts)
            if not ok:
                warnings.append(f"{pin.label()} (pinned): {reason}")
            pad = _pad_item(ctx, pin)
            if pad is not None:
                ctx.pads.append(pad)
            spots.append(pin)

    for k in range(ctx.flights):
        for low, high in _pieces(cuts, ctx.per_flight):
            spots += _piece_braces(ctx, k, low, high, cuts, pins, warnings)

    ground = ctx.rules.ground_clip and ctx.arrangement.inner_clips and ctx.flights
    if ground and not any(p.side == GROUND for p in pins) and not any(key[:1] == (CLIP,) and key[3] == GROUND
                                                                       for key in ctx.removed):
        low, high = _pieces(cuts, ctx.per_flight)[0]
        clips = [s.tread for s in spots if s.kind == CLIP and s.flight == 0 and low <= s.tread <= high]
        if not any(t <= 2 for t in clips):
            found = next((t for t in range(1, high + 1) if t not in clips
                          and _pad_ok(ctx, Spot(CLIP, 0, t, GROUND), cuts)[0]), None)
            if found is None:
                warnings.append("Flight 1: no tread near the foot takes the extra inner clip.")
            else:
                spot = Spot(CLIP, 0, found, GROUND)
                ctx.pads.append(_pad_item(ctx, spot))
                spots.append(spot)

    braces = {(s.flight, s.tread) for s in spots if s.kind == KNEE}
    clip_at = {(s.flight, s.tread) for s in spots if s.kind == CLIP}
    for side in ctx.rules.sides:
        for k in range(ctx.flights):
            posts = _posts(ctx, k, side, cuts, braces, clip_at, pins, warnings)
            spots += posts
            spots += _rail_splits(ctx, k, side, sorted(p.tread for p in posts), pins)
    return Plan(tuple(spots), tuple(cuts), tuple(warnings))


def check(arrangement: StairArrangement, current: Plan, spot: Spot, shell: Shell | None = None,
          rules: Rules = Rules()) -> tuple[bool, str]:
    """Would ``spot`` go where it is, with the rest of ``current`` as it stands? (ok, why not) for the
    drag-and-drop preview's green and red."""
    where = stair_places(arrangement.stair, arrangement.stair.shell_od_in, arrangement.platforms,
                         arrangement.ground_in)
    ctx = _Context(arrangement, where, shell, rules)
    if not 0 <= spot.flight < ctx.flights:
        return False, "That is not on the stair."
    others = [s for s in current.spots if s.key() != spot.key()]
    cuts = list(current.cuts)
    if spot.kind == SPLICE:
        if not 1 <= spot.tread < ctx.per_flight:
            return False, "A stringer is cut in a gap between two treads of its flight."
        if spot.tread in (1, ctx.per_flight - 1):
            return False, "Not in a flight's first or last tread gap: the end clips are there."
        # Only what the user pinned is in the way: the rules move their own posts and braces off a new cut. The cut
        # goes in every flight, so a pinned piece on any flight counts.
        beside = sorted((s.flight, s.tread) for s in others if s.kind in (POST, KNEE, CLIP) and s.pinned
                        and s.tread in (spot.tread, spot.tread + 1))
        if beside:
            k, tread = beside[0]
            return False, (f"Flight {k + 1}'s tread {tread} has a piece you placed: the cut and its splice plate "
                           "would be beside it.")
        return True, "The stringers are cut here, on every flight."
    if spot.kind == RAIL_SPLIT:
        if spot.side not in rules.sides:
            return False, f"The handrail is not on the {spot.side} stringer: set Handrail on, on the Stairway tab."
        posts = sorted(s.tread for s in others if s.kind == POST and s.flight == spot.flight and s.side == spot.side)
        if spot.tread not in posts or spot.tread == posts[-1]:
            return False, "A handrail splitter goes in a bay between two posts."
        return True, "The rail is split in the middle of this bay."
    if not 1 <= spot.tread <= ctx.per_flight:
        return False, "That is not on the stair."
    if spot.kind == POST:
        if spot.side not in rules.sides:
            return False, f"The handrail is not on the {spot.side} stringer: set Handrail on, on the Stairway tab."
        if spot.tread < 2:
            return False, "A post stands on the tread below its own, so not at tread 1."
        braces = {(s.flight, s.tread) for s in others if s.kind == KNEE}
        clip_at = {(s.flight, s.tread) for s in others if s.kind == CLIP}
        reason = _post_problem(spot, cuts, braces, clip_at)
        return (False, reason) if reason else (True, "The post fits here.")
    ctx.pads = [p for p in (_pad_item(ctx, s) for s in others if s.kind in (KNEE, CLIP)) if p is not None]
    ok, reason = _pad_ok(ctx, spot, cuts)
    return ok, reason if not ok else f"The {spot.kind}'s shell pad is clear here."


def shell_from(spec, nozzles=(), cleanouts=(), anchors=None) -> Shell | None:
    """The shell the pads keep to, from the Tank Properties, nozzle, FTCO and anchor chair tabs' contents; None
    without a tank."""
    if spec is None or not spec.active_courses():
        return None
    try:
        return Shell.of(build_stretchout(spec, nozzles=list(nozzles), cleanouts=list(cleanouts), anchors=anchors))
    except ValueError:
        return None


def applied(arrangement: StairArrangement, result: Plan) -> StairArrangement:
    """The arrangement as the plan places it: knee braces (with their cross braces) at its knee pans, inner clips at
    its clip pans, and the stringers cut where it cuts them."""
    per_flight = flight_count(arrangement)[1]
    splits = arrangement.splits
    if result.cuts or splits is not None:
        splits = replace(splits or SplitSettings(), fixed=tuple(result.cuts))
    return replace(arrangement, braces=tuple(sorted(s.pan(per_flight) for s in result.of_kind(KNEE))),
                   clips=tuple(sorted(s.pan(per_flight) for s in result.of_kind(CLIP))), splits=splits)


def flight_posts(arrangement: StairArrangement, result: Plan, side: str = OUTER) -> tuple[tuple[int, ...], ...]:
    """Each flight's post treads on ``side``, as ``post_sw.flight_picks`` takes them."""
    flights = flight_count(arrangement)[0]
    return tuple(tuple(sorted(s.tread for s in result.of_kind(POST, side) if s.flight == k)) for k in range(flights))


def flight_count(arrangement: StairArrangement) -> tuple[int, int]:
    """(flights, treads in a flight)."""
    return arrangement.platforms + 1, flight_treads(arrangement.stair.treads, arrangement.platforms)


# ----------------------------------------------------------------------------------------------- the cuts


def _cuts(ctx: _Context, pins: tuple[Spot, ...], warnings: list[str]) -> list[int]:
    splits = ctx.arrangement.splits
    pinned = sorted({p.tread for p in pins if p.kind == SPLICE})
    if pinned:
        return pinned
    if splits is None:
        return []
    if NO_CUTS in ctx.removed:
        return []
    gone = {key[2] for key in ctx.removed if key[0] == SPLICE}
    avoid = {p.tread for p in pins if p.kind in (POST, KNEE, CLIP)}
    found = choose_cuts(ctx.arrangement.stair.rise_in, ctx.per_flight, replace(splits, avoid=tuple(avoid)))
    if found is None:
        warnings.append("The stringers cannot be split into the pieces the splitter asks for; they stay whole.")
        return []
    return [j for j in found if j not in gone]


def _pieces(cuts: list[int], per_flight: int) -> list[tuple[int, int]]:
    """Each stringer piece's treads, (lowest, highest), flight-local."""
    edges = [0, *sorted(cuts), per_flight]
    return [(a + 1, b) for a, b in zip(edges, edges[1:], strict=False) if b > a]


# ----------------------------------------------------------------------------------- knee braces and clips


def _piece_braces(ctx: _Context, k: int, low: int, high: int, cuts: list[int], pins: tuple[Spot, ...],
                  warnings: list[str]) -> list[Spot]:
    """One knee brace and one inner clip for the piece of flight ``k`` from tread ``low`` to ``high``, nearest its
    middle, unless one is pinned on it."""
    pinned = {p.kind for p in pins if p.kind in (KNEE, CLIP) and p.flight == k and low <= p.tread <= high
              and p.side != GROUND}
    thrown = {key[0] for key in ctx.removed if key[1] == k and low <= key[2] <= high and key[3] != GROUND}
    wanted = [kind for kind in (KNEE, CLIP) if kind not in pinned and kind not in thrown
              and (kind == KNEE and ctx.arrangement.knees or kind == CLIP and ctx.arrangement.inner_clips)]
    if not wanted:
        return []
    middle = (low + high) / 2.0
    order = sorted(range(low, high + 1), key=lambda t: (abs(t - middle), t))
    # A cross brace by a flight's end posts (bottom at 2, top at the top tread) would push them off; there only
    # when nothing else in the piece takes it.
    ends = {1, 2, ctx.per_flight - 1, ctx.per_flight} if ctx.rules.sides else set()
    best: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for kind in wanted:
        tries = sorted(order, key=lambda t: t in ends) if kind == KNEE else order
        for t in tries:
            ok, reason = _pad_ok(ctx, Spot(kind, k, t), cuts)
            if ok:
                best[kind] = t
                break
            reasons.setdefault(kind, reason)
    if len(best) == 2 and best[KNEE] != best[CLIP]:
        # The same tread for both when that is no further from the middle than the farther of the two.
        reach = max(abs(best[KNEE] - middle), abs(best[CLIP] - middle))
        for t in order:
            if abs(t - middle) > reach:
                break
            if (t in ends) <= (best[KNEE] in ends) and all(_pad_ok(ctx, Spot(kind, k, t), cuts)[0]
                                                           for kind in (KNEE, CLIP)):
                best = {KNEE: t, CLIP: t}
                break
    spots = []
    for kind in wanted:
        if kind not in best:
            warnings.append(f"Flight {k + 1}, treads {low} to {high}: no tread takes the {kind}"
                            f" ({reasons.get(kind, 'no room')}).")
            continue
        spot = Spot(kind, k, best[kind])
        ctx.pads.append(_pad_item(ctx, spot))
        spots.append(spot)
    return spots


def _pad_ok(ctx: _Context, spot: Spot, cuts: list[int]) -> tuple[bool, str]:
    """A knee brace or clip at its tread: not beside a cut, the build takes it, and its pad is clear."""
    if spot.tread - 1 in cuts or spot.tread in cuts:
        return False, "it is beside a stringer cut"
    mark = _mark(ctx, spot)
    if isinstance(mark, str):
        return False, mark.split(": ", 1)[-1]
    clear = ctx.rules.seam_clear_in
    angle, y = mark.center
    wide, tall = mark.size
    if y - tall / 2.0 < clear:
        return False, f"its shell pad is within {clear:g} in of the floor weld"
    if ctx.shell is None:
        return True, ""
    if y + tall / 2.0 > ctx.shell.height_in - clear:
        return False, f"its shell pad is within {clear:g} in of the shell's top"
    padded = _pad_outline(ctx, mark, clear)
    for seam in ctx.shell.seams:
        if crosses(padded, seam, ctx.shell.girth_in):
            return False, f"its shell pad is within {clear:g} in of {seam.label}"
    for other in (*ctx.shell.landings, *ctx.pads):
        if other.label != mark.label and _meets(padded, other, ctx.shell.girth_in):
            return False, f"its shell pad is on {other.label}"
    return True, ""


def _mark(ctx: _Context, spot: Spot) -> Mark | str:
    pan = spot.flight * ctx.per_flight + spot.tread
    of = knee_mark if spot.kind == KNEE else clip_mark
    return of(ctx.where, ctx.arrangement.platforms, pan)


def _pad_item(ctx: _Context, spot: Spot) -> Item | None:
    mark = _mark(ctx, spot)
    if isinstance(mark, str):
        return None
    return _pad_outline(ctx, mark, 0.0)


def build_angle(arrangement: StairArrangement, x_in: float, girth_in: float, near: float) -> float:
    """The clockwise build's plan angle of stretchout ``x_in`` on the shell (``_pad_outline``'s mapping turned
    round), the turn of it nearest ``near``."""
    angle = -x_in / girth_in * 2.0 * math.pi - arrangement.turn
    if arrangement.ccw:
        angle = -angle
    return angle + 2.0 * math.pi * round((near - angle) / (2.0 * math.pi))


def _pad_outline(ctx: _Context, mark: Mark, grow: float) -> Item:
    angle, y = mark.center
    wide, tall = mark.size
    girth = ctx.shell.girth_in if ctx.shell is not None else 2.0 * math.pi * ctx.arrangement.stair.shell_od_in
    x = x_of_angle(ctx.arrangement.world(angle), girth) % girth
    return Item("pad", mark.label, _slot(x, y, wide + 2.0 * grow, tall + 2.0 * grow), lands=True)


def _meets(a: Item, b: Item, girth: float) -> bool:
    ax0, ay0, ax1, ay1 = a.box
    for shift in (0.0, girth, -girth):
        bx0, by0, bx1, by1 = b.box
        if ax1 <= bx0 + shift or bx1 + shift <= ax0 or ay1 <= by0 or by1 <= ay0:
            continue
        if _outlines_meet(a.outline, tuple((x + shift, y) for x, y in b.outline)):
            return True
    return False


# ------------------------------------------------------------------------------------------------- posts


def _posts(ctx: _Context, k: int, side: str, cuts: list[int], braces, clip_at, pins: tuple[Spot, ...],
           warnings: list[str]) -> list[Spot]:
    """The posts of flight ``k`` on ``side``: bottom, top and every ``post_every`` gaps, each moved off what it would
    stand on, with the pinned ones in place of any within a tread of them and the removed ones left out."""
    pinned = [p for p in pins if p.kind == POST and p.flight == k and p.side == side]
    for pin in pinned:
        problem = _post_problem(pin, cuts, braces, clip_at)
        if problem:
            warnings.append(f"{pin.label()} (pinned): {problem}")
    n = ctx.per_flight
    if n < 2:
        return pinned
    gone = {key[2] for key in ctx.removed if key[:2] == (POST, k) and key[3] == side}
    every = max(1, ctx.rules.post_every)
    wanted = [2, *range(2 + every, n - 1, every), n]
    placed: list[Spot] = []
    for t in dict.fromkeys(wanted):
        if t in gone or any(abs(p.tread - t) <= 1 for p in pinned):
            continue
        taken = {p.tread for p in placed} | {p.tread for p in pinned} | gone
        for step in (0, 1, -1, 2, -2):
            u = t + step
            if not 2 <= u <= n or u in taken:
                continue
            spot = Spot(POST, k, u, side)
            if _post_problem(spot, cuts, braces, clip_at) is None:
                placed.append(spot)
                break
        else:
            spot = Spot(POST, k, t, side)
            warnings.append(f"{spot.label()}: {_post_problem(spot, cuts, braces, clip_at)} No tread near it is clear.")
            if t not in taken:
                placed.append(spot)
    return sorted(placed + pinned, key=lambda p: p.tread)


def _post_problem(spot: Spot, cuts, braces, clip_at) -> str | None:
    """Why a post at its tread would clash: it stands in the gap below its tread, so a cut there, a cross brace
    on either tread of that gap or, inside, an inner clip at the tread below is in its way."""
    t = spot.tread
    if t - 1 in cuts:
        return "It would stand on a stringer cut."
    hit = sorted({t - 1, t} & {tread for flight, tread in braces if flight == spot.flight})
    if hit:
        return f"The cross brace at tread {hit[0]} is in its way."
    if spot.side == INNER and (spot.flight, t - 1) in clip_at:
        return f"The inner clip at tread {t - 1} is in its way."
    return None


# -------------------------------------------------------------------------------------------- rail splits


def _rail_splits(ctx: _Context, k: int, side: str, posts: list[int], pins: tuple[Spot, ...]) -> list[Spot]:
    """Where flight ``k``'s ``side`` rail is split: pinned, or in the middle of the farthest bay the rail from the
    last split reaches within its stock length, as few splits as that takes."""
    pinned = [p for p in pins if p.kind == RAIL_SPLIT and p.flight == k and p.side == side and p.tread in posts[:-1]]
    gone = {key[2] for key in ctx.removed if key[:2] == (RAIL_SPLIT, k) and key[3] == side}
    stock = 12.0 * (ctx.rules.outer_rail_ft if side == OUTER else ctx.rules.inner_rail_ft)
    step = rail_step_in(ctx.where, side)
    spots: list[Spot] = []
    if len(posts) < 2:
        return spots
    mids = [((low + high) / 2.0, low) for low, high in zip(posts, posts[1:], strict=False)]
    # The pinned splits break the rail into stretches; each stretch longer than the stock gets the rules' splits.
    breaks = sorted(m[0] for m in mids if m[1] in {p.tread for p in pinned})
    for start, end in zip([posts[0], *breaks], [*breaks, posts[-1]], strict=True):
        while (end - start) * step > stock + 1e-9:
            # The farthest bay middle the rail from the last split reaches; the next bay if none does.
            reach = [m for m in mids if start < m[0] < end and (m[0] - start) * step <= stock + 1e-9]
            pick = reach[-1] if reach else next((m for m in mids if start < m[0] < end), None)
            if pick is None:
                break
            if pick[1] not in gone:
                spots.append(Spot(RAIL_SPLIT, k, pick[1], side))
            start = pick[0]
    return sorted(spots + pinned, key=lambda p: p.tread)


def rail_step_in(where: StairPlaces, side: str) -> float:
    """How much rail one tread takes along the slope on ``side``: the tread's arc at the rail's radius and a
    rise."""
    layout = where.layout
    r_a = layout.inner_face_in
    radius = r_a - THICKNESS_IN if side == INNER else r_a + layout.clear_in + THICKNESS_IN
    sweep = where.places[1].phi - where.places[0].phi if len(where.places) > 1 else 0.0
    return math.hypot(sweep * radius, where.flight.rise_in)
