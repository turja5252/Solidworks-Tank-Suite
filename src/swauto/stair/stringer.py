"""Outer stringer size and burn holes, following the spiral stair GUI.

The plate is 3/8 in thick. Stations are measured along the helical outside
face the way the lisp stretch-out does. The SolidWorks part is the formed
helix; these lengths place that helix and the holes in it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

THICKNESS_IN = 0.375
TREAD_PLATE_IN = 36.0  # the full tread, and every platform's width whatever the treads are
CLEAR_IN = TREAD_PLATE_IN + 0.125
TREAD_WIDTHS_IN = (36.0, 30.0)  # the lisp launcher's choices
TREAD_DEPTH_IN = 10.9375
TREAD_MARK_IN = 2.5
BOLT_DIA_IN = 0.4375
BOLT_SPACE_IN = 7.0
BOLT_FROM_FRONT_IN = 2.8125
BOLT_UP_IN = 0.75
TOP_HOLE_DIA_IN = 0.8125
TOP_HOLE_DROP_IN = 2.25
TOP_HOLE_BACK_IN = (2.1875, 4.6875)
END_CUT_IN = 0.125
MAX_TREADS = 200  # a 100 ft shell at 7.5 in rises is 160 treads
PLATFORM_LENGTH_IN = 36.0  # along the centreline: the lisp launcher's "centerline arc" default
# Chris Samm, 2026-10-30: radials no more than 48 in apart along the centreline, and a knee brace and shell clip on
# a radial at least every 96 in (the ends always have them).
PLATFORM_SPACING_IN = 48.0
SUPPORT_SPACING_IN = 96.0
POST_BESIDE_IN = 4.0  # a platform post toward B from a radial, clear of the radial's coped end and its bolts


@dataclass(frozen=True)
class PlatformSpec:
    """One platform's shape, as Stair Platform Top View.lsp's RADIALPLATFORM draws it: radial ends A and B, the
    inner side C on the inner stringer by the shell, the outer side D.

    ``length_in`` runs along the centreline, halfway between C and D. ``width_in`` is nominal, as the treads are:
    36 is the stair's own platform, and more puts D further out (C never moves). ``rolled`` rolls C and D about the
    tank axis; None takes the lisp's default, rolled when longer than 36 in. A long platform gets radials between
    A and B, no more than ``spacing_in`` apart along the centreline; ``radials`` are where they are, in from A along
    the centreline (None: equal bays). The ends carry a knee brace and a shell clip, and so do enough radials between
    that no two supports are more than ``support_spacing_in`` apart (Chris Samm, 2026-10-30): ``supports`` are those
    radials, the same way (None: the fewest that do, nearest the middle of their bays). ``posts`` are the outer
    side's posts between its two end posts, the same way (None: one beside each radial)."""

    length_in: float = PLATFORM_LENGTH_IN
    width_in: float = TREAD_PLATE_IN
    rolled: bool | None = None
    spacing_in: float = PLATFORM_SPACING_IN
    radials: tuple[float, ...] | None = None
    posts: tuple[float, ...] | None = None
    supports: tuple[float, ...] | None = None
    support_spacing_in: float = SUPPORT_SPACING_IN

    @property
    def is_rolled(self) -> bool:
        return self.length_in > PLATFORM_LENGTH_IN + 1e-9 if self.rolled is None else self.rolled

    @property
    def extra_in(self) -> float:
        """How much further out D is than on the stair's own platform."""
        return self.width_in - TREAD_PLATE_IN

    def radial_positions(self) -> tuple[float, ...]:
        """The radials between A and B, in from A along the centreline: where they were put, or equal bays."""
        if self.radials is not None:
            return tuple(sorted(self.radials))
        bays = max(1, math.ceil(self.length_in / self.spacing_in - 1e-9))
        return tuple(self.length_in * i / bays for i in range(1, bays))

    def support_positions(self) -> tuple[float, ...]:
        """The radials between A and B with a knee brace and a shell clip, in from A along the centreline: those
        chosen, or the fewest that keep every bay between supports within ``support_spacing_in``."""
        radials = self.radial_positions()
        if self.supports is not None:
            return tuple(sorted(along for along in self.supports if any(abs(along - r) < 1e-6 for r in radials)))
        return held_radials(radials, self.length_in, self.support_spacing_in)

    def post_positions(self) -> tuple[float, ...]:
        """The outer side's posts between its end posts, in from A along the centreline: where they were put, or
        one beside each radial."""
        if self.posts is not None:
            return tuple(sorted(self.posts))
        return tuple(along + POST_BESIDE_IN for along in self.radial_positions())

    def validate(self) -> None:
        if not 12.0 <= self.length_in <= 1200.0:
            raise ValueError("A platform's length must be 12 to 1200 in along its centreline.")
        if not TREAD_PLATE_IN <= self.width_in <= 120.0:
            raise ValueError(f"A platform's width must be {TREAD_PLATE_IN:g} to 120 in; it is never narrower than "
                             "the stair's own platform.")
        if not 12.0 <= self.spacing_in <= 240.0:
            raise ValueError("The most between a platform's radials must be 12 to 240 in.")


def held_radials(radials: tuple[float, ...], length_in: float, spacing_in: float) -> tuple[float, ...]:
    """The fewest of ``radials`` (in from A along the centreline) that, with the ends at 0 and ``length_in``, leave
    no bay between supports longer than ``spacing_in``: as many as the length needs, each the radial nearest its
    even share of the length. All of them when no fewer will do."""
    def fits(chosen):
        stops = [0.0, *chosen, length_in]
        return all(b - a <= spacing_in + 1e-9 for a, b in zip(stops, stops[1:], strict=False))

    need = max(0, math.ceil(length_in / spacing_in - 1e-9) - 1)
    for count in range(need, len(radials) + 1):
        chosen: list[float] = []
        for i in range(1, count + 1):
            want = length_in * i / (count + 1)
            free = [r for r in radials if r not in chosen]
            chosen.append(min(free, key=lambda r: (abs(r - want), r)))
        if fits(sorted(chosen)):
            return tuple(sorted(chosen))
    return tuple(radials)


@dataclass(frozen=True)
class StringerMock:
    """Lengths are inches. ``outside_face`` develops the outer fiber. ``tread_in`` is the tread
    plate across the stair; the stringers stand 1/16 in clear of it each side. ``platform_specs`` are the
    platforms' shapes, the mid ones from the bottom and then the top one; one not given is the stair's own."""

    shell_od_in: float = 120.0
    gap_in: float = 8.0
    treads: int = 8
    rise_in: float = 7.5
    run_in: float = 10.5
    plate_width_in: float = 9.0
    outside_face: bool = True
    tread_in: float = TREAD_PLATE_IN
    platform_specs: tuple[PlatformSpec, ...] = ()

    @property
    def clear_in(self) -> float:
        """Between the stringers' walk faces."""
        return self.tread_in + CLEAR_IN - TREAD_PLATE_IN

    def platform(self, k: int) -> PlatformSpec:
        """The shape of platform ``k`` (0 the lowest; the top platform after the mid ones)."""
        return self.platform_specs[k] if 0 <= k < len(self.platform_specs) else PlatformSpec()

    def validate(self) -> None:
        if self.shell_od_in <= 0:
            raise ValueError("Shell outside radius must be greater than zero.")
        if self.gap_in < 0:
            raise ValueError("Gap cannot be negative.")
        if self.treads < 2 or self.treads > MAX_TREADS:
            raise ValueError(f"Use 2 to {MAX_TREADS} treads.")
        if self.rise_in <= 0 or self.run_in <= 0:
            raise ValueError("Rise and run must be greater than zero.")
        if self.plate_width_in <= 1:
            raise ValueError("Plate width must be greater than 1 in.")
        if not 12.0 <= self.tread_in <= TREAD_PLATE_IN:
            raise ValueError(f"Treads must be 12 to {TREAD_PLATE_IN:g} in across; the platforms are {TREAD_PLATE_IN:g} in.")
        for spec in self.platform_specs:
            spec.validate()


@dataclass(frozen=True)
class TreadHoles:
    index: int
    along_in: float
    hole_along_in: tuple[float, float]
    hole_offset_in: float


@dataclass(frozen=True)
class StringerLayout:
    outside_radius_in: float
    mid_radius_in: float
    inner_face_in: float
    shell_od_in: float
    sweep_rad: float
    pitch_rad: float
    total_rise_in: float
    outside_true_in: float
    mid_true_in: float
    developed_true_in: float
    plate_width_in: float
    x0_in: float
    x1_in: float
    treads: tuple[TreadHoles, ...]
    top_holes_in: tuple[tuple[float, float], ...]
    tread_in: float

    @property
    def clear_in(self) -> float:
        """Between the stringers' walk faces."""
        return self.tread_in + CLEAR_IN - TREAD_PLATE_IN

    @property
    def pitch_deg(self) -> float:
        return math.degrees(self.pitch_rad)

    @property
    def sweep_deg(self) -> float:
        return math.degrees(self.sweep_rad)


def layout_stringer(spec: StringerMock) -> StringerLayout:
    """Plan radii and the slanted flat plate for one outer stringer."""
    spec.validate()
    inner_face = spec.shell_od_in + spec.gap_in + THICKNESS_IN
    outer_near = inner_face + spec.clear_in
    outside_radius = outer_near + THICKNESS_IN
    mid_radius = outer_near + THICKNESS_IN / 2.0
    walk_center = inner_face + spec.clear_in / 2.0
    sweep = spec.treads * (spec.run_in / walk_center)
    total_rise = spec.treads * spec.rise_in
    outside_true = math.hypot(outside_radius * sweep, total_rise)
    mid_true = math.hypot(mid_radius * sweep, total_rise)
    developed = outside_true if spec.outside_face else mid_true
    develop_radius = outside_radius if spec.outside_face else mid_radius
    half_depth = TREAD_DEPTH_IN / 2.0
    hole_offset = -TREAD_MARK_IN / 2.0 + BOLT_UP_IN
    treads: list[TreadHoles] = []
    for index in range(1, spec.treads + 1):
        along = (index / spec.treads) * developed
        front = along + half_depth
        first = front - BOLT_FROM_FRONT_IN
        treads.append(TreadHoles(index, along, (first, first - BOLT_SPACE_IN), hole_offset))
    x0 = treads[0].along_in - half_depth - END_CUT_IN
    x1 = treads[-1].along_in + half_depth + END_CUT_IN
    top_holes = tuple((x1 - back, hole_offset - TOP_HOLE_DROP_IN) for back in TOP_HOLE_BACK_IN)
    return StringerLayout(
        outside_radius_in=outside_radius,
        mid_radius_in=mid_radius,
        inner_face_in=inner_face,
        shell_od_in=spec.shell_od_in,
        sweep_rad=sweep,
        pitch_rad=math.atan2(total_rise, develop_radius * sweep),
        total_rise_in=total_rise,
        outside_true_in=outside_true,
        mid_true_in=mid_true,
        developed_true_in=developed,
        plate_width_in=spec.plate_width_in,
        x0_in=x0,
        x1_in=x1,
        treads=tuple(treads),
        top_holes_in=top_holes,
        tread_in=spec.tread_in,
    )


def helix_end_along_in(layout: StringerLayout) -> float:
    """How far the formed helix must run so the top holes stay on the plate."""
    end = layout.x1_in
    for along, _offset in layout.top_holes_in:
        end = max(end, along)
    return end


def hole_point_in(layout: StringerLayout, along_in: float, offset_in: float) -> tuple[float, float, float]:
    """Point on the plate centerline, inches, Y up.

    The SolidWorks helix starts at +Z and turns toward −X. ``offset_in`` is
    across the plate, perpendicular to that helix.
    """
    theta = along_in / layout.developed_true_in * layout.sweep_rad
    alpha = math.atan2(layout.total_rise_in, layout.mid_radius_in * layout.sweep_rad)
    radius = layout.mid_radius_in
    binormal = (
        -math.sin(alpha) * math.cos(theta),
        -math.cos(alpha),
        -math.sin(alpha) * math.sin(theta),
    )
    return (
        -radius * math.sin(theta) + offset_in * binormal[0],
        along_in / layout.developed_true_in * layout.total_rise_in + offset_in * binormal[1],
        radius * math.cos(theta) + offset_in * binormal[2],
    )
