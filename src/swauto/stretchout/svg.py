"""A stretchout sheet as an SVG picture: opens in any browser, prints to PDF, and stays sharp at any zoom."""

from __future__ import annotations

from html import escape

from swauto.stretchout.checks import Clash
from swauto.stretchout.model import (
    ANCHORS,
    CLIPS,
    FTCOS,
    KNEES,
    NOZZLES,
    PLATES,
    PLATFORM_PADS,
    PLATFORMS,
    SPLICES,
    STRINGERS,
    TREADS,
    Stretchout,
)
from swauto.stretchout.stringers import HOLES, PIECES
from swauto.stretchout.stringers import SPLICES as SHEET_SPLICES

# fill, outline per layer; "none" draws the outline only, and the shell plates alternate their fill by course
STYLE = {
    PLATES: ("#f3f0e8", "#9a9282"),
    FTCOS: ("#f6dcc1", "#b5651d"),
    ANCHORS: ("#ddd3c4", "#5b4636"),
    NOZZLES: ("#cfe2f7", "#1f5fa8"),
    STRINGERS: ("none", "#2f6f86"),
    SPLICES: ("#bfe3da", "#0f766e"),
    TREADS: ("#c9e3c0", "#3d7a2f"),
    PLATFORMS: ("#e8d5b5", "#8a5a1e"),
    KNEES: ("#f2b8b5", "#a4262c"),
    CLIPS: ("#e3c5f0", "#6b2c91"),
    PLATFORM_PADS: ("#ffe08a", "#9a6b00"),
    PIECES: ("#eef3f6", "#2f6f86"),
    SHEET_SPLICES: ("#bfe3da", "#0f766e"),
    HOLES: ("#ffffff", "#333333"),
}
THICK = (STRINGERS, PIECES)  # drawn with a heavier line
COURSE_FILLS = ("#f3f0e8", "#e7e1d3")
CLASH = "#d40000"


def to_svg(out: Stretchout, clashes: list[Clash] = (), *, shown=None, title: str = "", step_deg: int = 15) -> str:
    """The whole sheet, its labels and the list of clashes under it. Units are inches; y is flipped to point up."""
    shown = out.layers if shown is None else shown
    margin = 40.0
    low = min([0.0] + [item.box[1] for item in out.items])
    high = max([out.height_in] + [item.box[3] for item in out.items])
    legend_h = 18.0 * (len(clashes) + 4)
    width = out.girth_in + 2 * margin
    height = (high - low) + 2 * margin + legend_h

    def px(x: float, y: float) -> str:
        return f"{x + margin:.3f},{high - y + margin:.3f}"

    bad = {clash.label for clash in clashes}
    girth = out.girth_in
    shifts = (-girth, 0.0, girth) if out.wraps else (0.0,)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
        f'width="{width * 2:.0f}" height="{height * 2:.0f}" font-family="Segoe UI, Arial" font-size="9">',
        f'<rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" fill="#ffffff"/>',
    ]
    if out.wraps:
        # One girth, 360° at the left end and 0° at the right; what runs past an end shows at the other.
        parts.append(f'<defs><clipPath id="girth"><rect x="{margin}" y="0" width="{girth:.3f}" '
                     f'height="{height:.1f}"/></clipPath></defs>')
        parts.append('<g clip-path="url(#girth)">')
    for layer in out.layers:
        if layer not in shown:
            continue
        fill, stroke = STYLE[layer]
        for item in out.items:
            if item.layer != layer:
                continue
            if layer == PLATES:
                fill = COURSE_FILLS[int(item.label.split()[0][1:]) % 2]
            hit = item.label in bad
            for shift in shifts:
                points = " ".join(px(x + shift, y) for x, y in item.outline)
                parts.append(
                    f'<polygon points="{points}" fill="{fill}" stroke="{CLASH if hit else stroke}" '
                    f'stroke-width="{1.6 if hit else (0.8 if layer in THICK else 0.4)}">'
                    f"<title>{escape(item.info or item.label)}</title></polygon>"
                )
        if layer == PLATES:
            for seam in out.seams:
                for shift in shifts:
                    parts.append(f'<polyline points="{px(seam.x0 + shift, seam.y0)} {px(seam.x1 + shift, seam.y1)}" '
                                 'stroke="#5f574a" stroke-width="0.6" fill="none"/>')
    if out.wraps:
        parts.append("</g>")
        for degrees in range(0, 361, step_deg):
            x = girth * (1.0 - degrees / 360.0)
            parts.append(f'<polyline points="{px(x, out.height_in)} {px(x, out.height_in + 6)}" stroke="#333" '
                         'stroke-width="0.5"/>')
            parts.append(f'<text x="{x + margin:.2f}" y="{high - out.height_in - 8 + margin:.2f}" '
                         f'text-anchor="middle">{degrees}°</text>')
    for x, y, text in out.labels:
        parts.append(f'<text x="{x + margin:.2f}" y="{high - y + margin:.2f}" font-size="6">{escape(text)}</text>')
    y_text = high - low + margin * 1.5
    if title:
        parts.append(f'<text x="{margin}" y="{y_text:.1f}" font-size="12">{escape(title)}</text>')
    y_text += 16
    for clash in clashes:
        parts.append(f'<text x="{margin}" y="{y_text:.1f}" fill="{CLASH}">{escape(clash.text)}</text>')
        y_text += 18
    if out.wraps and not clashes:
        parts.append(f'<text x="{margin}" y="{y_text:.1f}">Nothing crosses a seam or sits on anything else.</text>')
    for note in out.notes:
        parts.append(f'<text x="{margin}" y="{y_text:.1f}">{escape(note)}</text>')
        y_text += 18
    parts.append("</svg>")
    return "\n".join(parts)
