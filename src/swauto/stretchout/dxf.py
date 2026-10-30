"""The developed stringer sheet as a DXF for burning: every stringer piece, splice plate and hole, full size in
inches, each kind on its own layer. Holes that are round go out as true circles; the rest as closed polylines.

Plain ASCII DXF (AutoCAD R12), which every burning table's software and AutoCAD read. The splice plates are drawn
where they bolt on, over their stringer pieces, so the shop can see them in place; move them apart to nest them.
The SolidWorks splice plates do not flatten yet on SolidWorks 2013, so this is their burn shape.
"""

from __future__ import annotations

import math

from swauto.stretchout.model import Item, Stretchout
from swauto.stretchout.stringers import HOLES, PIECES, SPLICES

BURN_LAYERS = (PIECES, SPLICES, HOLES)
_LAYER_NAMES = {PIECES: "STRINGER-PIECES", SPLICES: "SPLICE-PLATES", HOLES: "HOLES"}
_COLORS = {PIECES: 7, SPLICES: 4, HOLES: 1}  # white, cyan, red


def to_dxf(sheet: Stretchout, layers: tuple[str, ...] = BURN_LAYERS) -> str:
    """The sheet's items on ``layers`` as DXF text."""
    out: list[str] = []

    def put(code: int, value) -> None:
        out.append(f"{code}\n{value}")

    put(0, "SECTION")
    put(2, "HEADER")
    put(9, "$INSUNITS")
    put(70, 1)  # inches
    put(0, "ENDSEC")
    put(0, "SECTION")
    put(2, "TABLES")
    put(0, "TABLE")
    put(2, "LAYER")
    put(70, len(layers))
    for layer in layers:
        put(0, "LAYER")
        put(2, _LAYER_NAMES.get(layer, layer.upper()))
        put(70, 0)
        put(62, _COLORS.get(layer, 7))
        put(6, "CONTINUOUS")
    put(0, "ENDTAB")
    put(0, "ENDSEC")
    put(0, "SECTION")
    put(2, "ENTITIES")
    for item in sheet.items:
        if item.layer not in layers:
            continue
        name = _LAYER_NAMES.get(item.layer, item.layer.upper())
        circle = round_hole(item)
        if circle is not None:
            (cx, cy), radius = circle
            put(0, "CIRCLE")
            put(8, name)
            put(10, f"{cx:.6f}")
            put(20, f"{cy:.6f}")
            put(30, "0.0")
            put(40, f"{radius:.6f}")
            continue
        put(0, "POLYLINE")
        put(8, name)
        put(66, 1)
        put(70, 1)  # closed
        for x, y in item.outline:
            put(0, "VERTEX")
            put(8, name)
            put(10, f"{x:.6f}")
            put(20, f"{y:.6f}")
            put(30, "0.0")
        put(0, "SEQEND")
        put(8, name)
    put(0, "ENDSEC")
    put(0, "EOF")
    return "\n".join(out) + "\n"


def round_hole(item: Item) -> tuple[tuple[float, float], float] | None:
    """(center, radius) when ``item`` is a hole drawn as a circle: every point the same distance from the middle."""
    if item.layer != HOLES or len(item.outline) < 8:
        return None
    x0, y0, x1, y1 = item.box
    center = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    radii = [math.dist(center, p) for p in item.outline]
    if max(radii) - min(radii) > 1e-3 * max(radii):
        return None
    return center, sum(radii) / len(radii)
