"""The developed stringers laid out flat: each flight's inner and outer stringer as its burn pieces, with
the splice plates and every hole, marked the way the lisp's splitter marks its parts. The treads' end walls
and every bolt's washer show too, so a joint can be seen clear of the treads.

Inner stringers run along the bottom row, flight by flight from the left, and outer ones above them.
Each is drawn in its own development (x along the climb, y up, inches), shifted into its slot.
"""

from __future__ import annotations

import math

from swauto.stair.development import END_HOLE_RADIUS_IN, SLOT_LENGTH_IN, connecting_holes, develop_both, tread_rect
from swauto.stair.landings import StairArrangement
from swauto.stair.splitter import (
    HOLE_DIA_IN,
    SEGMENTS,
    SPLICE_WASHER_OD_IN,
    TREAD_WASHER_OD_IN,
    choose_cuts,
    clashes,
    flight_span_in,
    holes_in,
    joints,
    pieces_wanted,
    pieces,
)
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import BOLT_DIA_IN
from swauto.stretchout.checks import Clash
from swauto.stretchout.model import Item, Stretchout

PIECES = "Stringer pieces"
TREAD_MARKS = "Tread end walls"
SPLICES = "Splice plates"
WASHERS = "Washers"
HOLES = "Holes"
SHEET_LAYERS = (PIECES, TREAD_MARKS, SPLICES, WASHERS, HOLES)
GAP_IN = 30.0  # between stringers on the sheet
_STEPS = 24


def build_stringer_sheet(arrangement: StairArrangement) -> Stretchout:
    stair = arrangement.stair
    where = stair_places(stair, stair.shell_od_in, arrangement.platforms, arrangement.ground_in)
    flights = len(where.offsets)
    inner, outer = develop_both(where.flight)
    items: list[Item] = []
    labels: list[tuple[float, float, str]] = []
    notes: list[str] = []
    row_y = 0.0
    width = 0.0
    for dev, side in ((inner, "INNER"), (outer, "OUTER")):
        cuts = joints(dev, stair.rise_in, where.per_flight, arrangement.splits) if arrangement.splits else []
        if arrangement.splits and not cuts and where.per_flight > 1:
            notes.append(f"{side.title()} stringer: {_no_cuts(stair.rise_in, where.per_flight, arrangement.splits)}")
        parts = pieces(dev, cuts)
        x_min = min(x for x, _y in dev.outline)
        y_min = min(y for _x, y in dev.outline)
        span = max(x for x, _y in dev.outline) - x_min
        tall = max(y for _x, y in dev.outline) - y_min
        x = 0.0
        for flight in range(1, flights + 1):
            def move(point, dx=x - x_min, dy=row_y - y_min):
                return (point[0] + dx, point[1] + dy)

            for number, part in enumerate(parts, start=1):
                small = holes_in(part, dev.tread_bolts, BOLT_DIA_IN / 2.0)
                ends = holes_in(part, connecting_holes(dev, flight - 1), END_HOLE_RADIUS_IN)
                splice = holes_in(part, [hole for joint in cuts for hole in joint.holes], HOLE_DIA_IN / 2.0)
                slots = len(ends) if dev.slotted else 0
                big = len(splice) + (0 if dev.slotted else len(ends))
                name = f"{side} Flight {flight} Part {number}"
                info = (f"{name}: 7/16 in holes {len(small)}, 13/16 in holes {big}, slotted holes {slots}; "
                        f"{dev.pitch_deg:.3f}° slope, developed at its walk face, {dev.radius_in:.3f} in radius")
                items.append(Item(PIECES, name, tuple(move(p) for p in part), info))
                for hole in small:
                    items.append(Item(HOLES, f"{name} tread bolt", _circle(move(hole), BOLT_DIA_IN / 2.0)))
                for hole in ends:
                    shape = _slot(move(hole)) if dev.slotted else _circle(move(hole), END_HOLE_RADIUS_IN)
                    items.append(Item(HOLES, f"{name} end {'slot' if dev.slotted else 'hole'}", shape))
                for hole in splice:
                    items.append(Item(HOLES, f"{name} splice bolt", _circle(move(hole), HOLE_DIA_IN / 2.0)))
                top = max(y for _x, y in part)
                left = min(x for x, _y in part)
                labels.append((move((left, top))[0], move((left, top))[1] + 3.0, name))
            for number, center in enumerate(dev.tread_centers, start=1):
                items.append(Item(TREAD_MARKS, f"{side} Flight {flight} tread {number} end wall",
                                  tuple(move(p) for p in tread_rect(center))))
            for bolt in dev.tread_bolts:
                items.append(Item(WASHERS, f"{side} Flight {flight} tread bolt washer",
                                  _circle(move(bolt), TREAD_WASHER_OD_IN / 2.0)))
            for joint in cuts:
                items.append(Item(SPLICES, splice_label(side, flight, joint.tread),
                                  tuple(move(p) for p in joint.plate),
                                  f"Splice plate, {side.lower()} stringer, flight {flight}: four 13/16 in holes, "
                                  f"cut {joint.y_cut:.3f} in up the flight's development"))
                for hole in joint.holes:
                    items.append(Item(WASHERS, f"{side} Flight {flight} splice bolt washer",
                                      _circle(move(hole), SPLICE_WASHER_OD_IN / 2.0)))
            x += span + GAP_IN
        width = max(width, x - GAP_IN)
        row_y += tall + GAP_IN
    return Stretchout(width, row_y - GAP_IN, tuple(items), (), tuple(notes), layers=SHEET_LAYERS, wraps=False,
                      labels=tuple(labels))


def splice_label(side: str, flight: int, tread: int) -> str:
    return f"{side} Flight {flight} splice over tread {tread}"


def _no_cuts(rise_in: float, per_flight: int, splits) -> str:
    """Why a flight's stringer is one piece: no cut needed, or more pieces wanted than it has treads for."""
    if choose_cuts(rise_in, per_flight, splits) is not None:
        return "one piece a flight, no splitters required."
    wanted = pieces_wanted(flight_span_in(rise_in, per_flight), splits)
    if splits.mode == SEGMENTS:
        return f"a flight of {per_flight} treads cannot make {wanted} pieces; it stays one piece."
    return (f"a {splits.max_span_ft:g} ft max span needs {wanted} pieces a flight, more than its {per_flight} "
            "treads; it stays one piece.")


def sheet_clashes(arrangement: StairArrangement, sheet: Stretchout) -> list[Clash]:
    """What each splice on the sheet still runs into (``splitter.clashes``), on the plate's own label so the
    sheet marks it."""
    if arrangement.splits is None:
        return []
    where = stair_places(arrangement.stair, arrangement.stair.shell_od_in, arrangement.platforms,
                         arrangement.ground_in)
    plates = {item.label: item for item in sheet.items if item.layer == SPLICES}
    found = []
    for dev, side in zip(develop_both(where.flight), ("INNER", "OUTER"), strict=True):
        for joint in joints(dev, arrangement.stair.rise_in, where.per_flight, arrangement.splits):
            problems = [text.split(": ", 1)[1] for text in clashes(dev, [joint], arrangement.splits.avoid)]
            for flight in range(1, len(where.offsets) + 1):
                item = plates.get(splice_label(side, flight, joint.tread))
                if item is None:
                    continue
                x0, y0, x1, y1 = item.box
                found.extend(Clash(item.label, problem, (x0 + x1) / 2.0, (y0 + y1) / 2.0, ": ")
                             for problem in problems)
    return found


def _circle(center, radius: float):
    cx, cy = center
    steps = [2.0 * math.pi * k / _STEPS for k in range(_STEPS)]
    return tuple((cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in steps)


def _slot(center):
    """The outer stringer's end slots: 1-5/8 in long, level, full-radius ends."""
    cx, cy = center
    radius, half = END_HOLE_RADIUS_IN, (SLOT_LENGTH_IN - 2.0 * END_HOLE_RADIUS_IN) / 2.0
    right = [(cx + half + radius * math.cos(a), cy + radius * math.sin(a))
             for a in (-math.pi / 2.0 + math.pi * k / 12 for k in range(13))]
    left = [(cx - half + radius * math.cos(a), cy + radius * math.sin(a))
            for a in (math.pi / 2.0 + math.pi * k / 12 for k in range(13))]
    return tuple(right + left)
