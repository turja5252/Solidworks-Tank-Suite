"""Developed (flat) stringer plates, following SpiralStairTool.lsp.

Everything is in the development plane: X runs along the climb (tread 1 at
the low-X end), Y is up, inches. Each stringer is developed at its walk-side
face, the way the lisp does (inner stringer at ``inR``, outer at ``outR``).

Burn outline (per side):
  top edge      straight slope through the top trailing (-X) corners of tread 1
                and tread N
  top end       horizontal at tread-N top level across the tread plus the top
                extension, vertical drop, horizontal back to the bottom edge
  bottom end    top edge runs the bottom extension past tread 1's trailing
                corner, vertical drop to ``drop`` below tread 1's top,
                horizontal forward to the bottom edge
  bottom edge   parallel to the top edge, plate width perpendicular below

The inner stringer's ends are 1/8 in past tread 1 and tread N. The outer
stringer's extensions reach the radial lines through those ends (``dStart`` /
``dEnd`` in the lisp top view), so both stringers stop on the same radial line
and butt square against a platform frame there.

Holes: two tread bolts per tread from the tread's +X (leading) edge, and two
end holes at each end 2-1/4 below the tread bolt line, set back from that end.
Inner end holes are round, outer end holes are horizontal slots.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.stair.stringer import (
    BOLT_DIA_IN,
    BOLT_FROM_FRONT_IN,
    BOLT_SPACE_IN,
    BOLT_UP_IN,
    CLEAR_IN,
    THICKNESS_IN,
    TOP_HOLE_BACK_IN,
    TOP_HOLE_DIA_IN,
    TOP_HOLE_DROP_IN,
    TREAD_DEPTH_IN,
    TREAD_MARK_IN,
    StringerMock,
)

DROP_IN = 5.25
END_EXT_IN = 0.125
SLOT_LENGTH_IN = 1.625
PLATFORM_CLEAR_IN = 36.0

Point = tuple[float, float]


@dataclass(frozen=True)
class DevelopedStringer:
    side: str
    radius_in: float
    pitch_rad: float
    true_length_in: float
    outline: tuple[Point, ...]
    tread_centers: tuple[Point, ...]
    tread_bolts: tuple[Point, ...]
    end_holes: tuple[Point, ...]
    slotted: bool
    plate_width_in: float

    @property
    def pitch_deg(self) -> float:
        return math.degrees(self.pitch_rad)

    @property
    def length_in(self) -> float:
        xs = [p[0] for p in self.outline]
        return max(xs) - min(xs)

    @property
    def height_in(self) -> float:
        ys = [p[1] for p in self.outline]
        return max(ys) - min(ys)


def develop_stringer(
    *,
    side: str,
    radius_in: float,
    sweep_rad: float,
    rise_in: float,
    treads: int,
    plate_width_in: float = 9.0,
    bottom_ext_in: float = END_EXT_IN,
    top_ext_in: float = END_EXT_IN,
    drop_in: float = DROP_IN,
    slotted: bool = False,
) -> DevelopedStringer:
    plan = radius_in * sweep_rad
    pitch = math.atan2(rise_in, plan)
    length = math.hypot(plan, rise_in)
    ux, uy = math.cos(pitch), math.sin(pitch)
    hd = TREAD_DEPTH_IN / 2.0
    ht = TREAD_MARK_IN / 2.0

    centers = tuple((length * i / treads * ux, length * i / treads * uy) for i in range(1, treads + 1))
    first, last = centers[0], centers[-1]
    p_start = (first[0] - hd, first[1] + ht)
    p_end = (last[0] - hd, last[1] + ht)
    tan = uy / ux
    start_ext = (p_start[0] - bottom_ext_in, p_start[1] - bottom_ext_in * tan)
    p2 = (p_end[0] + 2.0 * hd + top_ext_in, p_end[1])
    p3 = (p2[0], p2[1] - drop_in)
    p4 = start_ext
    p5 = (p4[0], p_start[1] - drop_in)

    # Bottom edge: parallel to the top edge, plate width perpendicular below.
    nx, ny = uy, -ux
    l1 = (p_start[0] + plate_width_in * nx, p_start[1] + plate_width_in * ny)

    def l1_at_x(x: float) -> Point:
        t = (x - l1[0]) / ux
        return (x, l1[1] + t * uy)

    def l1_at_y(y: float) -> Point:
        t = (y - l1[1]) / uy
        return (l1[0] + t * ux, y)

    l2_end = l1_at_y(p3[1])
    if l2_end[0] >= p3[0]:
        l2_end = l1_at_x(p3[0])
    l3_end = l1_at_y(p5[1])
    if l3_end[0] <= p5[0]:
        l3_end = l1_at_x(p5[0])

    outline = (p4, p_start, p_end, p2, p3, l2_end, l3_end, p5)

    bolts: list[Point] = []
    for cx, cy in centers:
        y = cy - ht + BOLT_UP_IN
        x1 = cx + hd - BOLT_FROM_FRONT_IN
        bolts.append((x1, y))
        bolts.append((x1 - BOLT_SPACE_IN, y))

    y_top = last[1] - ht + BOLT_UP_IN - TOP_HOLE_DROP_IN
    y_bot = first[1] - ht + BOLT_UP_IN - TOP_HOLE_DROP_IN
    end_holes = tuple((p2[0] - back, y_top) for back in TOP_HOLE_BACK_IN) + tuple(
        (p4[0] + back, y_bot) for back in TOP_HOLE_BACK_IN
    )
    return DevelopedStringer(
        side=side,
        radius_in=radius_in,
        pitch_rad=pitch,
        true_length_in=length,
        outline=outline,
        tread_centers=centers,
        tread_bolts=tuple(bolts),
        end_holes=end_holes,
        slotted=slotted,
        plate_width_in=plate_width_in,
    )


def outer_end_ext_in(inner_face: float, outer_face: float) -> float:
    """Outer stringer extension past the tread that puts its end on the radial line
    through the inner stringer's end, measured on the outer development."""
    half = TREAD_DEPTH_IN / 2.0
    return (half + END_EXT_IN) * outer_face / inner_face - half


def develop_both(
    stair: StringerMock,
    *,
    outer_bottom_ext_in: float | None = None,
    outer_top_ext_in: float | None = None,
) -> tuple[DevelopedStringer, DevelopedStringer]:
    """Inner and outer developments for the stair. The outer extensions default to
    the radial ones from ``outer_end_ext_in``."""
    stair.validate()
    inner_face = stair.shell_od_in + stair.gap_in + THICKNESS_IN
    outer_face = inner_face + CLEAR_IN
    walk_center = inner_face + CLEAR_IN / 2.0
    sweep = stair.treads * (stair.run_in / walk_center)
    rise = stair.treads * stair.rise_in
    radial_ext = outer_end_ext_in(inner_face, outer_face)
    if outer_bottom_ext_in is None:
        outer_bottom_ext_in = radial_ext
    if outer_top_ext_in is None:
        outer_top_ext_in = radial_ext
    inner = develop_stringer(
        side="inner",
        radius_in=inner_face,
        sweep_rad=sweep,
        rise_in=rise,
        treads=stair.treads,
        plate_width_in=stair.plate_width_in,
        slotted=False,
    )
    outer = develop_stringer(
        side="outer",
        radius_in=outer_face,
        sweep_rad=sweep,
        rise_in=rise,
        treads=stair.treads,
        plate_width_in=stair.plate_width_in,
        bottom_ext_in=outer_bottom_ext_in,
        top_ext_in=outer_top_ext_in,
        slotted=True,
    )
    return inner, outer


MAX_PLATFORMS = 3


def flight_treads(treads: int, platforms: int) -> int:
    """Treads in each flight when ``platforms`` mid platforms split ``treads`` steps into equal flights.

    As in SpiralStairTool.lsp, the tread level with each platform belongs to
    both flights beside it, so every flight has (treads + platforms) /
    (platforms + 1) treads and the stair has treads + platforms pans in all.
    """
    if platforms < 0 or platforms > MAX_PLATFORMS:
        raise ValueError(f"Mid platforms must be 0 to {MAX_PLATFORMS}.")
    if platforms == 0:
        return treads
    flights = platforms + 1
    if (treads + platforms) % flights:
        fits = [n for n in range(max(treads - flights, 2), treads + flights + 1) if (n + platforms) % flights == 0]
        raise ValueError(
            f"{treads} treads do not split into {flights} equal flights around {platforms} mid "
            f"platform{'s' if platforms > 1 else ''}. Try {' or '.join(str(n) for n in fits[:2])} treads."
        )
    per_flight = (treads + platforms) // flights
    if per_flight < 2:
        raise ValueError("Each flight needs at least 2 treads.")
    return per_flight


def stair_plan(
    stair: StringerMock, platforms: int = 0, top_platform: bool = False
) -> tuple[list[float], list[tuple[float, float]]]:
    """Plan angles: every tread centerline, and each platform's two radial sides (mid ones, then the top one)."""
    per_flight = flight_treads(stair.treads, platforms)
    flight = StringerMock(
        shell_od_in=stair.shell_od_in, gap_in=stair.gap_in, treads=per_flight, rise_in=stair.rise_in,
        run_in=stair.run_in, plate_width_in=stair.plate_width_in,
    )
    turn, _lift = flight_step(flight)
    inner_face = stair.shell_od_in + stair.gap_in + THICKNESS_IN
    walk_center = inner_face + CLEAR_IN / 2.0
    step = stair.run_in / walk_center
    cap = (TREAD_DEPTH_IN / 2.0 + END_EXT_IN) / inner_face
    treads = [k * turn + i * step for k in range(platforms + 1) for i in range(1, per_flight + 1)]
    spans = []
    for k in range(platforms + (1 if top_platform else 0)):
        side_a = k * turn + per_flight * step + cap
        spans.append((side_a, side_a + PLATFORM_CLEAR_IN / walk_center))
    return treads, spans


def flight_step(stair: StringerMock, clear_in: float = PLATFORM_CLEAR_IN) -> tuple[float, float]:
    """Turn (radians) and lift (inches) from one flight to the next over a mid platform.

    ``stair.treads`` is the treads in one flight. The flight below stops 1/8 in
    past its top tread, the platform runs ``clear_in`` along the walk centerline
    from there, and the next flight starts on the far side with its first tread
    level with the platform, as the lisp shares that tread between flights.
    """
    inner_face = stair.shell_od_in + stair.gap_in + THICKNESS_IN
    walk_center = inner_face + CLEAR_IN / 2.0
    step = stair.run_in / walk_center
    cap = (TREAD_DEPTH_IN / 2.0 + END_EXT_IN) / inner_face
    turn = (stair.treads - 1) * step + 2.0 * cap + clear_in / walk_center
    return turn, (stair.treads - 1) * stair.rise_in


def tread_rect(center: Point) -> tuple[Point, Point, Point, Point]:
    cx, cy = center
    hd = TREAD_DEPTH_IN / 2.0
    ht = TREAD_MARK_IN / 2.0
    return ((cx - hd, cy - ht), (cx + hd, cy - ht), (cx + hd, cy + ht), (cx - hd, cy + ht))


BOLT_RADIUS_IN = BOLT_DIA_IN / 2.0
END_HOLE_RADIUS_IN = TOP_HOLE_DIA_IN / 2.0
