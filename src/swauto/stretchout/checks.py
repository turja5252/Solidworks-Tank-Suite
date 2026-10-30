"""What lands where: every landing on the stretchout against the seams, the shell's ends, and each other.

A landing is anything that sits on the shell (a pad, a repad, an FTCO insert). It crosses a
seam when its outline meets the seam's line inside the seam's length; two landings clash when
their outlines overlap. The girth wraps, so each test is also made a girth to either side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.stretchout.model import Item, Seam, Stretchout


@dataclass(frozen=True)
class Clash:
    label: str
    problem: str
    x: float
    y: float
    joiner: str = " "  # ": " when the problem is a whole sentence

    @property
    def text(self) -> str:
        return f"{self.label}{self.joiner}{self.problem}"


def find_clashes(out: Stretchout) -> list[Clash]:
    """Landings past the bottom or top of the shell, across a seam, or on another landing."""
    landings = [item for item in out.items if item.lands]
    clashes: list[Clash] = []
    for item in landings:
        x0, y0, x1, y1 = item.box
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if y0 < -1e-6:
            clashes.append(Clash(item.label, f"reaches {-y0:.2f} in below the floor, past the shell's bottom", cx, cy))
        if y1 > out.height_in + 1e-6:
            clashes.append(Clash(item.label, f"reaches {y1 - out.height_in:.2f} in above the top of the shell", cx, cy))
        for seam in out.seams if item.on_seams else ():
            if crosses(item, seam, out.girth_in):
                clashes.append(Clash(item.label, f"crosses {seam.label}", cx, cy))
    for i, a in enumerate(landings):
        box_a = a.box
        for b in landings[i + 1:]:
            if _overlap(a, b, box_a, out.girth_in):
                x0, y0, x1, y1 = box_a
                clashes.append(Clash(a.label, f"overlaps {b.label}", (x0 + x1) / 2.0, (y0 + y1) / 2.0))
    return clashes


def crosses(item: Item, seam: Seam, girth: float) -> bool:
    """The item's outline meets the seam inside the seam's length."""
    for shift in (0.0, girth, -girth):
        if seam.vertical:
            span = _cut(item.outline, seam.x0 + shift, 0)
            if span and span[0] < seam.y1 - 1e-6 and span[1] > seam.y0 + 1e-6:
                return True
        else:
            span = _cut(item.outline, seam.y0, 1)
            if span and span[0] < seam.x1 + shift - 1e-6 and span[1] > seam.x0 + shift + 1e-6:
                return True
    return False


def clearance(item: Item, out: Stretchout) -> tuple[float, str] | None:
    """The nearest seam to the item's outline: distance in inches and which seam (0 if it crosses)."""
    best: tuple[float, str] | None = None
    for seam in out.seams:
        if crosses(item, seam, out.girth_in):
            return 0.0, seam.label
        for shift in (0.0, out.girth_in, -out.girth_in):
            gap = min(_to_segment(x, y, seam, shift) for x, y in item.outline)
            if best is None or gap < best[0]:
                best = (gap, seam.label)
    return best


def _cut(outline, at: float, axis: int) -> tuple[float, float] | None:
    """Where the closed outline crosses the line x = at (axis 0) or y = at (axis 1): the span along it."""
    other = 1 - axis
    hits = []
    for p, q in zip(outline, outline[1:] + outline[:1], strict=True):
        a, b = p[axis], q[axis]
        if (a - at) * (b - at) > 0.0 or a == b:
            continue
        t = (at - a) / (b - a)
        hits.append(p[other] + t * (q[other] - p[other]))
    return (min(hits), max(hits)) if hits else None


def _overlap(a: Item, b: Item, box_a, girth: float) -> bool:
    for shift in (0.0, girth, -girth):
        bx0, by0, bx1, by1 = b.box
        bx0, bx1 = bx0 + shift, bx1 + shift
        if box_a[2] <= bx0 or bx1 <= box_a[0] or box_a[3] <= by0 or by1 <= box_a[1]:
            continue
        moved = tuple((x + shift, y) for x, y in b.outline)
        if _outlines_meet(a.outline, moved):
            return True
    return False


def _outlines_meet(p, q) -> bool:
    """Two closed outlines overlap: an edge of one crosses an edge of the other, or one holds the other."""
    edges_p = list(zip(p, p[1:] + p[:1], strict=True))
    edges_q = list(zip(q, q[1:] + q[:1], strict=True))
    for e in edges_p:
        for f in edges_q:
            if _segments_cross(e, f):
                return True
    return _inside(p[0], q) or _inside(q[0], p)


def _segments_cross(e, f) -> bool:
    (ax, ay), (bx, by) = e
    (cx, cy), (dx, dy) = f

    def turn(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)

    d1, d2 = turn(cx, cy, dx, dy, ax, ay), turn(cx, cy, dx, dy, bx, by)
    d3, d4 = turn(ax, ay, bx, by, cx, cy), turn(ax, ay, bx, by, dx, dy)
    return (d1 * d2 < 0.0) and (d3 * d4 < 0.0)


def _inside(point, outline) -> bool:
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(outline, outline[1:] + outline[:1], strict=True):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def _to_segment(x: float, y: float, seam: Seam, shift: float) -> float:
    ax, ay, bx, by = seam.x0 + shift, seam.y0, seam.x1 + shift, seam.y1
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0.0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))
