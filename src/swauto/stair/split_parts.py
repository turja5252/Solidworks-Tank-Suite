"""The stringer splices as parts (partify, 2026-10-30): a stringer the splitter cuts is a part for each of its pieces,
and each joint's splice plate is a part of its own.

As stair_sw.split_stringers makes them, at the first flight's seat like the stringers (every flight's joints are
the same): the level 1/4 in cut through the stringer, the inner stringer's 1 in rounds on its pieces, the four 13/16
holes through stringer and plate (each part cuts its own from the same numbers), and the plate rolled as the stringer
is, so it flattens, holed before it is trimmed to the stringer's edges and rounded.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import replace

from swauto.errors import SolidWorksError
from swauto.stair import stair_sw as s
from swauto.stair.development import develop_both
from swauto.stair.splitter import GAP_IN, cut_span, joints, reliefs
from swauto.stair.stringer import THICKNESS_IN

_INCH = 0.0254


def sides(where) -> dict[str, tuple]:
    """Each stringer's (developed stringer, inner radius, outer radius, splice plate's band), by side, as
    split_stringers lays them out."""
    flight = where.flight
    layout = where.layout
    inner_dev, outer_dev = develop_both(flight)
    tank_face = flight.shell_od_in + flight.gap_in
    return {
        "In": (inner_dev, tank_face, tank_face + THICKNESS_IN, (tank_face - s.SPLICE_THK_IN, tank_face)),
        "Out": (outer_dev, layout.outside_radius_in - THICKNESS_IN, layout.outside_radius_in,
                (layout.outside_radius_in, layout.outside_radius_in + s.SPLICE_THK_IN)),
    }


def stringer_joints(where, splits, side: str) -> list:
    """The joints the splitter cuts one flight's stringer at (every flight's are the same)."""
    dev = sides(where)[side][0]
    return joints(dev, where.flight.rise_in, where.flight.treads, splits)


def cut_stringer(model, where, side: str, cuts: list, name: str) -> None:
    """Cut the stringer just built (at the first flight's seat) at each joint, with the inner stringer's rounds on
    its pieces and each joint's four holes, as split_stringers cuts it before the plates go on."""
    dev, r_in, r_out, _band = sides(where)[side]
    at = where.offsets[0]
    turn, lift = at
    radius = dev.radius_in
    for joint in cuts:
        tag = f"{name}T{joint.tread:02d}"
        x0, x1 = cut_span(dev, joint)
        s._sector_cut(model, (r_in - 0.03, r_out + 0.03), turn + (x0 - s._SPLIT_MARGIN_IN) / radius,
                      turn + (x1 + s._SPLIT_MARGIN_IN) / radius, lift + joint.y_cut - GAP_IN / 2.0,
                      lift + joint.y_cut + GAP_IN / 2.0, f"{tag}Cut")
        count = len(s._stringer_pieces(model, f"{tag}Cut", (r_in, r_out)))
        if count != 2:
            raise SolidWorksError(f"{tag}: the cut left {count} stringer pieces, not 2.")
        for index, relief in enumerate((r for r in reliefs(dev, joint) if r.piece != "plate"), start=1):

            def half(cut=f"{tag}Cut", which=relief.piece):
                found = s._stringer_pieces(model, cut, (r_in, r_out))
                return (found[0] if which == "lower" else found[1]) if len(found) == 2 else None

            if not s._relief_cut(model, dev, relief, at, dev.radius_in, True, half, f"{tag}Round{index}"):
                raise SolidWorksError(f"{tag}: a 1 in round was not cut.")
    _holes(model, dev, r_in, r_out, cuts, at, name)


def _holes(model, dev, r_in: float, r_out: float, cuts: list, at, name: str, plate: bool = False) -> None:
    """Each joint's four 13/16 holes, one small jig a hole as split_stringers cuts them; through whichever of the
    stringer and its plate the part holds. In a ``plate``'s part the hole is looked for in the plate:
    stair_sw._end_hole_pair looks in the stringer, which is not there."""
    rounds = replace(dev, slotted=False)
    outward = abs(dev.radius_in - r_out) <= abs(dev.radius_in - r_in)
    for joint in cuts:
        tag = f"{name}T{joint.tread:02d}"
        for index, hole in enumerate(joint.holes, start=1):
            made = s._end_hole_pair(model, rounds, dev.radius_in, outward, [hole], f"{tag}H{index}", at)
            if plate:
                made = _plate_has_hole(model, dev, hole, at)
            if not made:
                raise SolidWorksError(f"{tag}: hole {index} of the splice was not cut.")


def _plate_has_hole(model, dev, hole, at) -> bool:
    """The splice plate (the part's one body) has the 13/16 hole at ``hole``, (x, y) in the stringer's
    development, its axis square to the stringer as stair_sw._end_hole_pair cuts it."""
    turn, lift = at
    radius = dev.radius_in
    phi = hole[0] / radius + turn
    point = [v * _INCH for v in (-radius * math.sin(phi), hole[1] + lift, radius * math.cos(phi))]
    return any(s._has_hole_axis(body, point, s.END_HOLE_RADIUS_IN * _INCH, 0.12 * _INCH) is True
               for body in s._bodies(model))


def keep_stringer_piece(model, i: int, name: str) -> None:
    """Of the pieces the cuts left, keep the ``i``-th from the bottom and delete the rest, one at a time, counting the
    bodies (SolidWorks 2013's Delete Body reports nothing)."""
    def height(body):
        return s._box_in(body)[1]

    bodies = s._bodies(model)
    keep = sorted(height(b) for b in bodies)[i]
    while len(bodies) > 1:
        s._delete_body(model, max(bodies, key=lambda b: abs(height(b) - keep)))
        left = s._bodies(model)
        if len(left) >= len(bodies):
            raise SolidWorksError(f"{name}: could not delete the stringer's other pieces.")
        bodies = left


def build_plate(model, where, side: str, joint, name: str) -> None:
    """A joint's splice plate on the stringer's back face (split_stringers' steps for one plate): rolled as the
    stringer is, its four holes, trimmed to the stringer's top and bottom edges, and on the inner stringer its round."""
    dev, r_in, r_out, band = sides(where)[side]
    at = where.offsets[0]
    turn, lift = at
    radius = dev.radius_in
    xs = [x for x, _y in joint.plate]
    ys = [y for _x, y in joint.plate]
    plate_name = f"{name}T{joint.tread:02d}Plate"
    s._rolled_blank(model, band[0], band[1], turn + (min(xs) - s._SPLIT_MARGIN_IN) / radius,
                    turn + (max(xs) + s._SPLIT_MARGIN_IN) / radius, lift + min(ys), lift + max(ys), plate_name)
    _holes(model, dev, r_in, r_out, [joint], at, name, plate=True)
    g = s._stringer_geometry(where.layout, dev, r_in, r_out)
    far = g["phi_end"]
    helix = ((band[0] + band[1]) / 2.0, g["rise_per_rad"] * far, far / (2.0 * math.pi))
    span = 30.0

    def plates():
        return s._bodies_made_by(model, plate_name)

    for label, y0, y1 in (("Top", lift + g["top_at_zero"], lift + g["top_at_zero"] + span),
                          ("Bottom", lift + g["bottom_at_zero"] - span, lift + g["bottom_at_zero"])):
        before = s._names(model)
        try:
            s._cut_sweep(model, helix, (band[0] - 0.03, band[1] + 0.03), y0, y1, f"{name}Plate{label}", turn,
                         scope=plates)
        except SolidWorksError:
            s._discard_since(model, before)
            s._cut_sweep(model, helix, s._plate_trim_band(band, (r_in, r_out)), y0, y1, f"{name}Plate{label}", turn)
    s._rebuild(model)
    with contextlib.suppress(Exception):
        s._keep_bent_view(model)
    for relief in (r for r in reliefs(dev, joint) if r.piece == "plate"):

        def plate():
            found = s._bodies_made_by(model, plate_name)
            return found[0] if len(found) == 1 else None

        if not s._relief_cut(model, dev, relief, at, band[0], False, plate, f"{name}PlateRound"):
            raise SolidWorksError(f"{name}: the plate's round was not cut.")
    if len(s._bodies(model)) != 1:
        raise SolidWorksError(f"{name}: the splice plate came out as {len(s._bodies(model))} bodies.")
