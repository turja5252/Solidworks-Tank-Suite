"""The roof platform's plan and heights, without SolidWorks (item 12, started 2026-10-30).

From Elite's Roof Paltform.lsp (c:ROOFPLATFORMTOP, Type2) and its issued TK-701 platform (2025-033-1 PL1A-PL1C), and
the user's decisions of 2026-10-30. A rectangle on the cone roof, C its side nearest the tank axis and D the outer,
A and B its ends named clockwise, with an extension past D flush with B (the lisp's Type2) reaching over the roof's
edge toward the stair. C and D are straight, square to the platform's middle radial line; every channel's web back
is on the outline, its flanges in, the corners mitred. The deck (the grating's top) is level.

Lengths are inches. Plan points are (X, Z) in the build's frame: the tank axis on Y, 0 deg toward +Z, an angle
growing toward -X as the stair measures it. Here a point is also (along, out): ``along`` from the platform's middle
radial line toward B, ``out`` from the tank axis along that line.

Placed by the user's decisions: its size typed in, its place first at the stair's top and then dragged in the game
(``angle_deg``, ``edge_in``); legs by area, one per 30 sq ft as the lisp counts them (at least two under each of C
and D), under C and D 12 in in from their ends (TK-701) and evenly between; the deck high enough that the shortest
leg, at C's middle where the cone is highest, is still ``MIN_LEG_IN``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.stair.platform_sw import GRATING_IN, SECTIONS
from swauto.tank.roof import RoofSpec, cone_profile_in

AREA_PER_LEG_FT2 = 30.0  # the lisp: ceil(area x 100 / 3000)
LEG_IN_FROM_END_IN = 12.0  # TK-701: the first leg 1'-0" in from the end
MIN_LEG_IN = 6.0  # the shortest leg, clip to pad, under the frame's bottom (decision 5: computed, not guessed)
POST_FROM_CORNER_IN = 6.0  # the lisp and TK-701
POST_MOST_APART_IN = 60.0  # the lisp's auto spacing
GATE_IN = 37.125  # TK-701's opening for the 37 in safety gate, where the stair arrives


@dataclass(frozen=True)
class RoofPlatformSpec:
    """What the user types and drags: the rectangle's ``length_in`` along C and D and ``width_in`` from D in to C;
    the extension's ``ext_length_in`` along D from B and its ``ext_reach_in`` out past D (0: none); the channel; the
    braces from C to D between the ends; and where it is: its middle radial line at ``angle_deg`` and D's middle
    ``edge_in`` in from the shell's outside."""

    length_in: float = 120.0
    width_in: float = 84.0
    ext_length_in: float = 37.0  # TK-701: 3'-1"
    ext_reach_in: float = 41.875  # TK-701: 3'-5 7/8"
    channel: str = "C4"
    braces: int = 1
    angle_deg: float = 0.0
    edge_in: float = 30.0

    def validate(self) -> None:
        if not 24.0 <= self.length_in <= 480.0 or not 24.0 <= self.width_in <= 240.0:
            raise ValueError("A roof platform is 24 to 480 in long and 24 to 240 in wide.")
        if self.ext_reach_in < 0.0 or (self.ext_reach_in > 0.0 and not 12.0 <= self.ext_length_in <= self.length_in):
            raise ValueError("The extension is 12 in long at least and no longer than the platform.")
        if self.channel not in SECTIONS:
            raise ValueError(f"A roof platform's channel is {' or '.join(SECTIONS)}, not {self.channel}.")
        if not 0 <= self.braces <= 12:
            raise ValueError("A roof platform has 0 to 12 braces between its ends.")
        if self.edge_in < 0.0:
            raise ValueError("The platform's outer side cannot reach past the shell.")

    @property
    def area_ft2(self) -> float:
        return (self.length_in * self.width_in + self.ext_length_in * self.ext_reach_in) / 144.0

    @property
    def leg_count(self) -> int:
        """The lisp's count, at least four so each of C and D stands on two."""
        return max(4, math.ceil(self.area_ft2 / AREA_PER_LEG_FT2 - 1e-9))


@dataclass(frozen=True)
class RoofPlatform:
    """A placed platform: ``d_out`` is the distance from the tank axis to D's line (its web backs), ``d_in`` to C's,
    on the middle radial line at ``angle`` (radians)."""

    spec: RoofPlatformSpec
    angle: float
    d_out: float
    d_in: float

    def world(self, along: float, out: float) -> tuple[float, float]:
        """(X, Z) of the point ``along`` toward B from the middle radial line and ``out`` from the tank axis."""
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (-out * s - along * c, out * c - along * s)

    @property
    def half(self) -> float:
        return self.spec.length_in / 2.0

    def corners(self) -> list[tuple[float, float]]:
        """The rectangle's web-back corners as (along, out): A-C, A-D, B-D, B-C."""
        return [(-self.half, self.d_in), (-self.half, self.d_out), (self.half, self.d_out), (self.half, self.d_in)]

    def extension(self) -> list[tuple[float, float]] | None:
        """The extension's web-back outline as (along, out), from D at its A' end out and round to D at B: A'-D,
        A'-D', B'-D', B'-D (B' in line with B); None without one."""
        spec = self.spec
        if spec.ext_reach_in <= 0.0:
            return None
        a = self.half - spec.ext_length_in
        far = self.d_out + spec.ext_reach_in
        return [(a, self.d_out), (a, far), (self.half, far), (self.half, self.d_out)]

    def brace_alongs(self) -> list[float]:
        """Where the braces from C to D stand between the ends, evenly: the lisp's i/(n + 1)."""
        n = self.spec.braces
        return [-self.half + self.spec.length_in * i / (n + 1) for i in range(1, n + 1)]

    def nearest_radius(self) -> float:
        """The platform's point nearest the tank axis: C's middle."""
        return self.d_in

    def farthest_radius(self) -> float:
        """The frame's point farthest out: the extension's outer corner at B, or D's ends."""
        ext = self.extension()
        points = self.corners() + (ext or [])
        return max(math.hypot(a, o) for a, o in points)


def place(spec: RoofPlatformSpec, shell_r: float) -> RoofPlatform:
    """``spec`` on a shell of outside radius ``shell_r``: D's middle ``edge_in`` in from the shell, C ``width_in`` in
    from D. Refused if a corner of the rectangle would reach past the shell."""
    spec.validate()
    d_out = shell_r - spec.edge_in
    d_in = d_out - spec.width_in
    if d_in <= 0.0:
        raise ValueError("The platform reaches past the tank axis: make it narrower or move it out.")
    placed = RoofPlatform(spec, math.radians(spec.angle_deg), d_out, d_in)
    corner = math.hypot(placed.half, d_out)
    if corner > shell_r - 1e-9:
        raise ValueError(f"The platform's outer corners would be {corner - shell_r:.2f} in past the shell: move it in "
                         f"at least that far, or shorten it.")
    return placed


def roof_top_y(roof: RoofSpec, radius: float) -> float:
    """The roof's outside at plan ``radius``, on the cone the Roof tab revolves."""
    profile = cone_profile_in(roof)
    (r0, y0), (r1, y1) = profile[2], profile[3]
    return y0 + (y1 - y0) * (radius - r0) / (r1 - r0)


def deck_y(placed: RoofPlatform, roof: RoofSpec) -> float:
    """The grating's top: high enough over the cone's highest point under the frame (C's middle) for the shortest
    leg, under the channel and the grating (the user, decision 5: computed, not guessed)."""
    section = SECTIONS[placed.spec.channel]
    return roof_top_y(roof, placed.nearest_radius()) + MIN_LEG_IN + section.depth_in + GRATING_IN


@dataclass(frozen=True)
class Leg:
    """One leg under a side channel: at ``along`` on side ``side`` ("C" or "D"), its plan point, and how long it is
    from the channel's bottom down to the roof."""

    side: str
    along: float
    point: tuple[float, float]
    length_in: float


def legs(placed: RoofPlatform, roof: RoofSpec) -> list[Leg]:
    """The legs: half under C and half under D (D gets the odd one), 12 in in from the ends and evenly between, each
    from the frame's bottom to the cone under it."""
    count = placed.spec.leg_count
    per_side = {"D": math.ceil(count / 2), "C": count // 2}
    bottom = deck_y(placed, roof) - GRATING_IN - SECTIONS[placed.spec.channel].depth_in
    out = []
    for side, n in per_side.items():
        d = placed.d_out if side == "D" else placed.d_in
        first = -placed.half + LEG_IN_FROM_END_IN
        last = placed.half - LEG_IN_FROM_END_IN
        for i in range(n):
            along = first + (last - first) * (i / (n - 1) if n > 1 else 0.5)
            point = placed.world(along, d)
            out.append(Leg(side, along, point, bottom - roof_top_y(roof, math.hypot(*point))))
    return out


def post_alongs(length_in: float) -> list[float]:
    """Posts along a side ``length_in`` long, from one end: 6 in from each corner and no more than 60 in apart."""
    span = length_in - 2.0 * POST_FROM_CORNER_IN
    if span <= 0.0:
        return [length_in / 2.0]
    bays = max(1, math.ceil(span / POST_MOST_APART_IN - 1e-9))
    return [POST_FROM_CORNER_IN + span * i / bays for i in range(bays + 1)]
