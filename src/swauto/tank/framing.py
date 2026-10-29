"""Rafters, the dollar plate and the center column of a cone roof, as Elite's lisp lays them out
(MS Roof External Rafters, GA4 Cross Section).

Rafters are radial and equally spaced, an even number of them. Each is a box W wide in plan and h deep
square to the roof: internal rafters hang under the roof plate, external ones sit on it. They run along
the slope from the inner trim plus the setback, out to the outer trim back from the eave (R1, the slant
length of the underside). The lisp gives no section shape, so neither does this.

The center column stack is turned discs, all free sizes: the dollar plate, a top cap, the pipe, a bottom
cap and a base plate on the floor. Its top lands under the rafters (internal) or under the roof (external).

Angles are the app's: 0 toward +Z, growing clockwise seen from above. The lisp's rotation 0 puts the first
pie seam at 90 deg (drawing +X), with the rafters half a space either side of the seams.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.tank.roof import RoofSpec, cone_profile_in, flat_pattern

INTERNAL = "internal"
EXTERNAL = "external"
MODES = (INTERNAL, EXTERNAL)
LEFT = "left"
RIGHT = "right"
DOLLAR_RAFTER_MIN_IN = 6.0  # the rafters' inner ends at least this far in over the dollar plate, along the roof
CLIP_THK_IN = 0.25


def mode_for_roof_type(roof_type: str) -> str | None:
    """Tank Properties' roof type: rafters inside or outside, or None for a roof with no rafters."""
    text = str(roof_type).strip().lower()
    if "internal" in text:
        return INTERNAL
    if "external" in text:
        return EXTERNAL
    return None


@dataclass(frozen=True)
class Column:
    """The center column stack. A piece with no diameter or no thickness is left out; a pipe wall of 0, or
    of half the diameter or more, is a solid bar."""

    dollar_dia_in: float = 0.0
    dollar_thk_in: float = 0.0
    top_cap_dia_in: float = 0.0
    top_cap_thk_in: float = 0.0
    pipe_od_in: float = 0.0
    pipe_wall_in: float = 0.0
    bottom_cap_dia_in: float = 0.0
    bottom_cap_thk_in: float = 0.0
    base_dia_in: float = 0.0
    base_thk_in: float = 0.0

    def validate(self) -> None:
        for name, value in vars(self).items():
            if value < 0.0:
                raise ValueError(f"The column's {name.removesuffix('_in').replace('_', ' ')} cannot be negative.")


@dataclass(frozen=True)
class Framing:
    """Rafter layout inputs, with the lisp's defaults. Lengths are inches; trims and setback are measured
    along the slope."""

    mode: str = INTERNAL
    rafter_count: int = 12
    rafter_width_in: float = 4.0
    rafter_height_in: float = 6.0
    inner_trim_in: float = 0.0
    outer_trim_in: float = 0.0
    setback_in: float = 0.0
    min_length_in: float = 0.0
    rotation_deg: float = 0.0
    clips: bool = True
    clips_per_rafter: int = 2
    clip_side: str = LEFT
    column: Column | None = None
    floor_top_in: float = 0.0  # where the column's base plate stands: the floor's top face

    def validate(self) -> None:
        if self.mode not in MODES:
            raise ValueError("Rafters are internal or external.")
        if self.rafter_count < 2:
            raise ValueError("A rafter roof needs at least 2 rafters.")
        if self.rafter_width_in <= 0.0 or self.rafter_height_in <= 0.0:
            raise ValueError("Rafter width and height must be greater than zero.")
        if min(self.inner_trim_in, self.outer_trim_in, self.setback_in, self.min_length_in) < 0.0:
            raise ValueError("Trims, setback and the minimum length cannot be negative.")
        if self.clips_per_rafter < 0:
            raise ValueError("Clips per rafter cannot be negative.")
        if self.clip_side not in (LEFT, RIGHT):
            raise ValueError("Clips go on the left or the right of each rafter.")
        if self.clips and self.rafter_height_in <= CLIP_THK_IN:
            raise ValueError("Clips need a rafter deeper than 1/4 in.")
        if self.column is not None:
            self.column.validate()

    @property
    def count(self) -> int:
        """The lisp drops an odd count by one, so each pie has two rafters."""
        return self.rafter_count - self.rafter_count % 2


@dataclass(frozen=True)
class Rafter:
    number: int
    angle_deg: float


@dataclass(frozen=True)
class Layout:
    """Where the framing goes on one roof. Radii are plan inches from the tank axis, heights are Y."""

    framing: Framing
    roof: RoofSpec
    rafters: tuple[Rafter, ...]
    slant_in: float  # R1
    inner_slant_in: float
    outer_slant_in: float
    section: tuple[tuple[float, float], ...]  # one rafter, (radius, height), round the tank axis
    clip_section: tuple[tuple[float, float], ...]  # the band the clips are cut from, or ()
    clip_slants_in: tuple[float, ...]
    column: tuple[tuple[str, tuple[tuple[float, float], ...]], ...]  # (piece, (radius, height) loop)
    warnings: tuple[str, ...]

    @property
    def length_in(self) -> float:
        return self.outer_slant_in - self.inner_slant_in

    def plan_radius(self, slant_in: float) -> float:
        return slant_in * self.roof.landing_radius_in() / self.slant_in


def layout(framing: Framing, roof: RoofSpec) -> Layout:
    """Lay the rafters, clips and column out on ``roof``. Raises when they cannot be built; ``warnings`` lists
    what the lisp shows in red."""
    framing.validate()
    roof.validate()
    count = framing.count
    step = 360.0 / count
    rafters = tuple(Rafter(i + 1, (90.0 + framing.rotation_deg + (i + 0.5) * step) % 360.0) for i in range(count))
    slant = flat_pattern(roof).slant_in
    landing = roof.landing_radius_in()
    inner = framing.inner_trim_in + framing.setback_in
    outer = slant - framing.outer_trim_in
    if outer <= inner + 1e-9:
        raise ValueError("Rafter trims are too large: the outer end is not beyond the inner end.")
    m = roof.slope_in_per_ft / 12.0
    k = math.hypot(1.0, m)
    h = framing.rafter_height_in
    scale = landing / slant
    r_a, r_b = inner * scale, outer * scale
    if framing.mode == INTERNAL:
        surface, sign = _underside(roof), -1.0
    else:
        surface, sign = _outside(roof), 1.0

    def offset(r: float, depth: float) -> tuple[float, float]:
        """The point ``depth`` square off the roof surface over plan radius ``r``, away from the plate."""
        return (r + sign * depth * m / k, surface(r) + sign * depth / k)

    section = ((r_a, surface(r_a)), (r_b, surface(r_b)), offset(r_b, h), offset(r_a, h))
    half = framing.rafter_width_in / 2.0
    meet = half / math.tan(math.radians(step) / 2.0)
    nearest = min(r for r, _y in section)
    if nearest < meet + 0.75:  # the plan outlines start 1/2 in short of the rafter, and must not touch
        need = (meet + 0.75 + max(0.0, r_a - nearest)) / scale
        raise ValueError(
            f"The rafters run into each other near the center. Start them at least {need:.2f} in up the slope "
            "(inner trim plus setback)."
        )
    warnings = []
    if framing.min_length_in > 0.0 and outer - inner < framing.min_length_in:
        warnings.append(f"The rafters are {outer - inner:.3f} in long, under the {framing.min_length_in:g} in minimum.")
    column = framing.column
    if column is not None and column.dollar_dia_in > 0.0:
        station = column.dollar_dia_in / 2.0 * k
        if station - inner < DOLLAR_RAFTER_MIN_IN - 1e-9:
            warnings.append(
                f"The rafters reach {station - inner:.3f} in over the dollar plate; the lisp asks for at least "
                f"{DOLLAR_RAFTER_MIN_IN:g} in (a setback of at most {station - framing.inner_trim_in - 6.0:.3f} in)."
            )
    if framing.mode == INTERNAL and r_b > roof.inside_radius_in + 1e-6 and surface(r_b) - h / k < roof.shell_height_in:
        # Landing on a ring, out past the shell's inside face: the rafter's outer end hangs into the shell top.
        warnings.append("The rafters' outer ends hang into the shell: add an outer trim.")
    clip_slants: tuple[float, ...] = ()
    clip_section: tuple[tuple[float, float], ...] = ()
    if framing.clips and framing.clips_per_rafter > 0:
        n = framing.clips_per_rafter
        clip_slants = tuple(inner + (outer - inner) * j / (n + 1) for j in range(1, n + 1))
        depth = h - CLIP_THK_IN
        d0, d1 = (0.0, depth) if framing.clip_side == LEFT else (h - depth, h)
        a = (clip_slants[0] - 1.0) * scale
        b = (clip_slants[-1] + 1.0) * scale
        clip_section = (offset(a, d0), offset(b, d0), offset(b, d1), offset(a, d1))
    pieces = _column_loops(framing, roof, surface, k) if column is not None else ()
    return Layout(framing, roof, rafters, slant, inner, outer, section, clip_section, clip_slants, pieces,
                  tuple(warnings))


def radial(angle_deg: float) -> tuple[float, float]:
    """Plan (X, Z) unit vector out along ``angle_deg``."""
    phi = math.radians(angle_deg)
    return (-math.sin(phi), math.cos(phi))


def rafter_outline(layout_: Layout, rafter: Rafter) -> list[tuple[float, float]]:
    """A rafter's footprint in plan, (X, Z) corners, a little past both of its ends."""
    rs = [r for r, _y in layout_.section]
    return _box(rafter.angle_deg, min(rs) - 0.5, max(rs) + 0.5, -layout_.framing.rafter_width_in / 2.0,
                layout_.framing.rafter_width_in / 2.0)


def clip_outlines(layout_: Layout, rafter: Rafter) -> list[list[tuple[float, float]]]:
    """The rafter's clips in plan: 1/4 in along it, standing out from its left (counterclockwise) or right
    side by the rafter depth less 1/4 in."""
    framing = layout_.framing
    half = framing.rafter_width_in / 2.0
    depth = framing.rafter_height_in - CLIP_THK_IN
    side = -1.0 if framing.clip_side == LEFT else 1.0  # counterclockwise is toward a smaller angle
    lo, hi = sorted((side * half, side * (half + depth)))
    out = []
    for slant in layout_.clip_slants_in:
        r = layout_.plan_radius(slant)
        half_t = CLIP_THK_IN / 2.0 * layout_.roof.landing_radius_in() / layout_.slant_in
        out.append(_box(rafter.angle_deg, r - half_t, r + half_t, lo, hi))
    return out


def _box(angle_deg: float, r0: float, r1: float, t0: float, t1: float) -> list[tuple[float, float]]:
    """Plan rectangle along the radial line at ``angle_deg``: r0..r1 out, t0..t1 to the clockwise side."""
    ux, uz = radial(angle_deg)
    cx, cz = -uz, ux  # clockwise: the way the angle grows
    return [(ux * r + cx * t, uz * r + cz * t) for r, t in ((r0, t0), (r1, t0), (r1, t1), (r0, t1))]


def _underside(roof: RoofSpec):
    base, landing, m = roof.landing_height_in(), roof.landing_radius_in(), roof.slope_in_per_ft / 12.0
    return lambda r: base + (landing - r) * m


def _outside(roof: RoofSpec):
    (r0, y0), (r1, y1) = cone_profile_in(roof)[2:4]
    return lambda r: y0 + (y1 - y0) * (r - r0) / (r1 - r0)


def _column_loops(framing: Framing, roof: RoofSpec, surface, k: float):
    """(piece, closed (radius, height) loop) from the top down, each sitting on the next. The top lands on the
    rafters' bottom chord (internal) or the roof's underside (external), at the piece's own rim."""
    column = framing.column
    under = _underside(roof)

    def landing_y(radius: float) -> float:
        if framing.mode == INTERNAL:
            return under(radius) - framing.rafter_height_in * k
        return under(radius)

    pieces = []
    top = None
    for name, dia, thk in (("Dollar plate", column.dollar_dia_in, column.dollar_thk_in),
                           ("Top cap", column.top_cap_dia_in, column.top_cap_thk_in)):
        if dia > 0.0 and thk > 0.0:
            y1 = landing_y(dia / 2.0) if top is None else top
            pieces.append((name, _disc(0.0, dia / 2.0, y1 - thk, y1)))
            top = y1 - thk
    bottom = framing.floor_top_in
    below = []
    for name, dia, thk in (("Base plate", column.base_dia_in, column.base_thk_in),
                           ("Bottom cap", column.bottom_cap_dia_in, column.bottom_cap_thk_in)):
        if dia > 0.0 and thk > 0.0:
            below.append((name, _disc(0.0, dia / 2.0, bottom, bottom + thk)))
            bottom += thk
    if column.pipe_od_in > 0.0:
        r = column.pipe_od_in / 2.0
        y1 = landing_y(r) if top is None else top
        if y1 <= bottom + 1e-6:
            raise ValueError("The column has no room between the floor and the roof.")
        bore = r - column.pipe_wall_in if 0.0 < column.pipe_wall_in < r else 0.0
        pieces.append(("Column", _disc(bore, r, bottom, y1)))
    return tuple(pieces + list(reversed(below)))


def _disc(r0: float, r1: float, y0: float, y1: float) -> tuple[tuple[float, float], ...]:
    return ((r0, y0), (r1, y0), (r1, y1), (r0, y1))
