"""The shell stretchout: the shell plates unrolled, with everything that lands on them.

The shell is seen from outside, the way Elite's Shell Plate Elevation drawing shows it: 0°
(toward +Z) at the right end and the orientation growing to the left, on course 1's OD girth,
so x = girth x (1 - deg / 360), wrapped. y is up from the floor, where the shell's chime sits.
Degrees are the nozzles', FTCOs' and the stair's: 0 toward +Z, clockwise seen from above.
Plates are placed by their angles from ``tank.plates`` (azimuth from +X, a quarter turn back).

Each item is an outline in those inches. Items that sit on the shell (pads, repads, inserts)
are marked ``lands``, and ``checks`` looks at those against the seams and each other.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from swauto.cleanout.layout import course_one_gaps
from swauto.cleanout.spec import OPENING_WIDTH_IN, Cleanout
from swauto.nozzle.place import place
from swauto.nozzle.spec import Nozzle
from swauto.stair.landings import (
    CLIP_PAD,
    KNEE_PAD,
    PLATFORM,
    PLATFORM_KNEE_PAD,
    PLATFORM_PAD,
    SPLICE,
    STRINGER,
    TREAD,
    StairArrangement,
    shell_marks,
)
from swauto.tank.anchors import AnchorChairs, chairs, front_silhouette
from swauto.tank.plates import developed_circumference_in, layout_plates
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import TankSpec

PLATES = "Shell plates"
NOZZLES = "Nozzles"
FTCOS = "FTCOs"
ANCHORS = "Anchor chairs"
TREADS = "Treads"
STRINGERS = "Stringers"
PLATFORMS = "Platforms"
KNEES = "Knee brace pads"
CLIPS = "Inner clip pads"
PLATFORM_PADS = "Platform shell clip pads"
SPLICES = "Stringer splices"
LAYERS = (PLATES, NOZZLES, FTCOS, ANCHORS, TREADS, STRINGERS, SPLICES, PLATFORMS, KNEES, CLIPS, PLATFORM_PADS)
_LAYER_OF = {
    TREAD: TREADS, STRINGER: STRINGERS, PLATFORM: PLATFORMS, KNEE_PAD: KNEES, PLATFORM_KNEE_PAD: KNEES,
    CLIP_PAD: CLIPS, PLATFORM_PAD: PLATFORM_PADS, SPLICE: SPLICES,
}
_ARC_STEPS = 12
_INCH = 0.0254

Point = tuple[float, float]


@dataclass(frozen=True)
class Item:
    """One thing drawn on the stretchout: a closed ``outline`` of (x, y) inches. ``lands`` if it sits on the
    shell, so it is checked against the other landings and, unless it is a shell plate itself (``on_seams``
    False: an FTCO insert, whose edges are seams), against the seams."""

    layer: str
    label: str
    outline: tuple[Point, ...]
    info: str = ""
    lands: bool = False
    on_seams: bool = True

    @property
    def box(self) -> tuple[float, float, float, float]:
        xs = [x for x, _y in self.outline]
        ys = [y for _x, y in self.outline]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class Seam:
    """A weld seam: vertical between two plates of a course, or horizontal between courses."""

    x0: float
    y0: float
    x1: float
    y1: float
    label: str

    @property
    def vertical(self) -> bool:
        return abs(self.x1 - self.x0) < 1e-9


@dataclass(frozen=True)
class Stretchout:
    """A sheet to draw: the shell unrolled (``wraps`` round its girth, with orientation degrees), or the
    developed stringers laid flat. ``layers`` in drawing order; ``labels`` are (x, y, text) marks."""

    girth_in: float
    height_in: float
    items: tuple[Item, ...]
    seams: tuple[Seam, ...]
    notes: tuple[str, ...]
    layers: tuple[str, ...] = LAYERS
    wraps: bool = True
    labels: tuple[tuple[float, float, str], ...] = ()

    def x_of_degrees(self, orientation_deg: float) -> float:
        return x_of_angle(math.radians(orientation_deg), self.girth_in) % self.girth_in

    def degrees_of_x(self, x_in: float) -> float:
        return (-x_in / self.girth_in * 360.0) % 360.0


def x_of_angle(angle: float, girth_in: float) -> float:
    """x of a plan angle the nozzles' way (radians, 0 toward +Z), unwrapped: seen from outside, the angle
    grows to the left."""
    return -angle / (2.0 * math.pi) * girth_in


def build_stretchout(
    spec: TankSpec,
    *,
    nozzles: Sequence[Nozzle] = (),
    cleanouts: Sequence[Cleanout] = (),
    stair: StairArrangement | None = None,
    anchors: AnchorChairs | None = None,
) -> Stretchout:
    """The shell's plates and seams, with each nozzle, FTCO, anchor chair and stair item placed on them."""
    spec.validate()
    courses = spec.active_courses()
    girth = 2.0 * math.pi * _inches(course_radii_m(spec, courses[0])[0])  # the OD, as the LISP's outline
    tiling = developed_circumference_in(spec, courses[0])  # the girth the plates and FTCO gaps are laid on
    height = spec.shell_height_in()
    items: list[Item] = []
    seams: list[Seam] = []
    notes: list[str] = []

    gaps = course_one_gaps(spec, cleanouts) if cleanouts else []
    plates = layout_plates(spec, gaps)
    for plate in plates:
        y0 = plate.z_bot_m / _INCH
        y1 = y0 + plate.height_m / _INCH
        # The plate starts at its azimuth (orientation a quarter turn back) and runs on clockwise: leftward here.
        x1 = x_of_angle(plate.start_rad - math.pi / 2.0, girth) % girth
        x0 = x1 - plate.sweep_rad / (2.0 * math.pi) * girth
        name = f"C{plate.course_no} P{plate.plate_no}"
        items.append(Item(PLATES, name, _box(x0, y0, x1, y1),
                          f"Course {plate.course_no}, plate {plate.plate_no}: {plate.length_in:.3f} in long, "
                          f"{y1 - y0:g} in tall, {_inches(plate.outer_r_m - plate.inner_r_m):.4g} in thick"))
        if not plate.is_full_ring:
            seams.append(Seam(x1, y0, x1, y1, f"the vertical seam at the start of {name}"))
    for gap in gaps:
        for edge in (gap.center_in - gap.length_in / 2.0, gap.center_in + gap.length_in / 2.0):
            x = x_of_angle(edge / tiling * 2.0 * math.pi - math.pi / 2.0, girth) % girth
            seams.append(Seam(x, 0.0, x, courses[0].height_in, "an FTCO insert plate edge"))
    level = 0.0
    for number, course in enumerate(courses, start=1):
        if number > 1:
            seams.append(Seam(0.0, level, girth, level, f"the horizontal seam under course {number}"))
        level += course.height_in

    for nozzle in nozzles:
        try:
            items.extend(_nozzle_items(nozzle, spec, girth))
        except ValueError as exc:
            notes.append(f"{nozzle.mark}: {exc}")
    for cleanout in cleanouts:
        items.extend(_ftco_items(cleanout, girth, tiling, courses[0].height_in))
    if anchors is not None:
        try:
            items.extend(_anchor_items(anchors, girth))
        except ValueError as exc:
            notes.append(f"Anchor chairs: {exc}")
    if stair is not None:
        stair_items, stair_notes = _stair_items(stair, girth)
        items.extend(stair_items)
        notes.extend(stair_notes)
        shell_od = stair.stair.shell_od_in
        tank_od = _inches(course_radii_m(spec, courses[0])[0])
        if abs(shell_od - tank_od) > 0.01:
            notes.append(
                f"The Stairway tab's shell OD radius is {shell_od:.3f} in, Tank Properties' {tank_od:.3f} in: "
                "the stair is drawn where it would stand on its own shell."
            )
    return Stretchout(girth, height, tuple(items), tuple(seams), tuple(notes))


def _nozzle_items(nozzle: Nozzle, spec: TankSpec, girth: float) -> list[Item]:
    placed = place(nozzle, spec)
    sx, sy, sz = placed.shell_in
    angle = math.atan2(-sx, sz)
    x = x_of_angle(angle, girth) % girth
    neck = placed.pipe.outside_diameter_in / 2.0
    degrees = math.degrees(angle) % 360.0
    info = (
        f"{nozzle.mark}: {nozzle.nps} in {nozzle.rating}# {nozzle.kind.upper()} at {degrees:.2f}°, centerline "
        f"{sy:g} in up, course {placed.course_number}; OSP {nozzle.outside_projection_in:g} in, "
        f"ISP {nozzle.inside_projection_in:g} in"
    )
    items = [Item(NOZZLES, f"{nozzle.mark} neck", _circle(x, sy, neck), info, lands=placed.repad is None)]
    pad = placed.repad
    if pad is not None:
        radius = pad.outer_diameter_in / 2.0
        if pad.style == "tombstone":
            outline = ((x - radius, 0.0), (x + radius, 0.0)) + tuple(
                (x + radius * math.cos(a), sy + radius * math.sin(a))
                for a in (math.pi * k / (2 * _ARC_STEPS) for k in range(2 * _ARC_STEPS + 1))
            )
        else:
            outline = _circle(x, sy, radius)
        items.append(Item(NOZZLES, f"{nozzle.mark} repad", outline,
                          f"{info}; repad {pad.outer_diameter_in:g} in {pad.style}, {pad.thickness_in:g} in thick",
                          lands=True))
    return items


def _ftco_items(cleanout: Cleanout, girth: float, tiling: float, course_height: float) -> list[Item]:
    dims = cleanout.dims
    x = x_of_angle(math.radians(cleanout.orientation_deg), girth) % girth
    info = f"{cleanout.mark}: {dims.label} FTCO at {cleanout.orientation_deg:g}°"
    half = dims.insert_length_in / 2.0 * girth / tiling  # its gap's angle, to meet the plates' edges
    radius = OPENING_WIDTH_IN / 2.0
    arch = dims.arch_center_in
    opening = ((x - radius, 0.0), (x + radius, 0.0)) + tuple(
        (x + radius * math.cos(a), arch + radius * math.sin(a))
        for a in (math.pi * k / (2 * _ARC_STEPS) for k in range(2 * _ARC_STEPS + 1))
    )
    cx, cy, r = dims.repad_corner_x_in, dims.repad_corner_y_in, dims.repad_corner_r_in
    repad = (
        ((x - dims.repad_half_in, 0.0), (x + dims.repad_half_in, 0.0))
        + tuple((x + cx + r * math.cos(a), cy + r * math.sin(a))
                for a in (math.pi / 2.0 * k / _ARC_STEPS for k in range(_ARC_STEPS + 1)))
        + tuple((x - cx + r * math.cos(a), cy + r * math.sin(a))
                for a in (math.pi / 2.0 + math.pi / 2.0 * k / _ARC_STEPS for k in range(_ARC_STEPS + 1)))
    )
    return [
        Item(FTCOS, f"{cleanout.mark} insert plate", _box(x - half, 0.0, x + half, course_height),
             f"{info}; insert plate {dims.insert_length_in:g} in long, {cleanout.insert_thk_in:g} in thick",
             lands=True, on_seams=False),
        Item(FTCOS, f"{cleanout.mark} repad", repad, f"{info}; repad {dims.repad_length_in:g} in long"),
        Item(FTCOS, f"{cleanout.mark} opening", opening, f"{info}; opening {OPENING_WIDTH_IN:g} in wide"),
    ]


def _anchor_items(spec: AnchorChairs, girth: float) -> list[Item]:
    """Each chair as it is seen from outside, standing on the floor: t along the shell is clockwise, so it
    runs leftward here, inch for inch on the OD."""
    outline = front_silhouette(spec)
    items = []
    for chair in chairs(spec):
        x = x_of_angle(math.radians(chair.angle_deg), girth) % girth
        info = (f"Anchor chair {chair.number} at {chair.angle_deg:.3f}°: {spec.top_plate_width_in:g} in wide, "
                f"{spec.height_in + spec.washer_thk_in:g} in tall with its washer")
        items.append(Item(ANCHORS, f"Chair {chair.number}", tuple((x - t, y) for t, y in outline), info, lands=True))
    return items


def _stair_items(stair: StairArrangement, girth: float) -> tuple[list[Item], list[str]]:
    marks, notes = shell_marks(stair)
    items = []
    for mark in marks:
        layer = _LAYER_OF[mark.kind]
        if mark.center is not None:
            angle, y = mark.center
            x = x_of_angle(stair.world(angle), girth) % girth
            width, tall = mark.size
            degrees = math.degrees(stair.world(angle)) % 360.0
            info = f"{mark.label}: {width:g} x {tall:g} in at {degrees:.2f}°, middle {y:.3f} in up"
            items.append(Item(layer, mark.label, _slot(x, y, width, tall), info, lands=True))
            continue
        outline = [(x_of_angle(stair.world(angle), girth), y) for angle, y in mark.outline]
        shift = math.floor(min(x for x, _y in outline) / girth) * girth  # bring it into the first girth
        outline = [(x - shift, y) for x, y in outline]
        ys = [y for _x, y in mark.outline]
        info = f"{mark.label}: {min(ys):.3f} to {max(ys):.3f} in up"
        items.append(Item(layer, mark.label, tuple(outline), info))
    return items, notes


def _box(x0: float, y0: float, x1: float, y1: float) -> tuple[Point, ...]:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _circle(x: float, y: float, radius: float) -> tuple[Point, ...]:
    steps = 4 * _ARC_STEPS
    return tuple(
        (x + radius * math.cos(2.0 * math.pi * k / steps), y + radius * math.sin(2.0 * math.pi * k / steps))
        for k in range(steps)
    )


def _slot(x: float, y: float, wide: float, tall: float) -> tuple[Point, ...]:
    """A pad: ``wide`` across, ``tall`` up, with full-radius ends top and bottom."""
    radius = wide / 2.0
    straight = max(tall / 2.0 - radius, 0.0)
    top = [(x + radius * math.cos(a), y + straight + radius * math.sin(a))
           for a in (math.pi * k / _ARC_STEPS for k in range(_ARC_STEPS + 1))]
    bottom = [(x + radius * math.cos(a), y - straight + radius * math.sin(a))
              for a in (math.pi + math.pi * k / _ARC_STEPS for k in range(_ARC_STEPS + 1))]
    return tuple(top + bottom)


def _inches(meters: float) -> float:
    return meters / _INCH
