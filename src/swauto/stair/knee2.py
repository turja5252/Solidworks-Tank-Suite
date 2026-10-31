"""Type 2 platform knee brace (Elite 2026-050-1 PL1A to PL2B, with the user's answers of 2026-10-30).

The brace bolts to its hanger and to its shell clip with two 3/4 A325 bolts at each end: one in a round hole, the
other 3 in down (or up) the brace in a 13/16 x 1-5/8 slot curved on a 3 in radius about the round one, so the brace
can swing about 7-3/4 deg either way to meet the shell. A platform's knees are all this type when its shape asks for
it (PlatformSpec.knee 2). The knee's line is type 1's, its round holes where type 1's two bolts are; the pieces are:

* PC12 hanger: 3/8 plate under the outer channel, 1/4 in in from the channel's outside and from the platform end as
  type 1's: 6 in along the channel bottom, its outer edge 3-7/8 deep and its inner 5-11/16, the bottom a V whose point
  is 2-1/8 from the inner edge and 7-3/4 below the top (the drawing's label; its edges' arithmetic gives 7-13/16).
* PC13 brace: type 1's L3x3x3/8 at 45 deg, as long, but its bolts 1-11/16 from the heel (type 1 keeps 1-1/2), with
  four 13/16 holes 1-1/2 and 4-1/2 from each end.
* PC11 shell clip: 3/8 plate, 6 in up the pad, 8-7/8 out along its top, 6-3/16 along its bottom and 3-5/16 up its outer
  edge, the lower outer corner cut 45 deg 2-11/16 each way. Its round hole is type 1's bolt, 5.766 in out from the
  shell OD, 1.98 above the clip's bottom as PC11 is drawn.
* PC10B pad: 1/4 x 4 x 8 with full round ends, centred on the clip.

Points are (r, y) on the knee's radial frame (brace_sw._Frame), as brace_sw._Knee has them.
"""

from __future__ import annotations

import contextlib
import math

from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import LEG_THK_IN, PAD_THK_IN, _extrude_to, _knee_angle
from swauto.stair.grab_sw import _sketch_through
from swauto.stair.platform_sw import HANGER_IN_FROM_OUTSIDE_IN, HOLE_DIA_IN, _cut_both_ways_in
from swauto.stair.stringer_sw import _create_circle

_INCH = 0.0254
_ROOT2 = math.sqrt(2.0)
GAUGE_IN = 1.6875  # the bolts from the brace's heel
BOLT_SPACE_IN = 3.0  # round hole to slot along the brace, and the slot's radius about the round hole
SLOT_LONG_IN = 1.625  # overall; it is HOLE_DIA_IN wide
HANGER_THK_IN = 0.375
HANGER_WIDE_IN = 6.0
HANGER_OUTER_IN = 3.875
HANGER_INNER_IN = 5.6875
HANGER_POINT_IN = 2.125  # the V's point in from the inner edge
HANGER_DEEP_IN = 7.75  # and below the top
CLIP_THK_IN = 0.375
CLIP_TALL_IN = 6.0
CLIP_TOP_IN = 8.875
CLIP_BOTTOM_IN = 6.1875
CLIP_HOLE_UP_IN = 1.98  # the round hole above the clip's bottom
PAD_TALL_IN = 8.0
DOWN = (-1.0 / _ROOT2, -1.0 / _ROOT2)  # down the brace toward the shell, in (r, y)


def hanger_outline(back: float, bottom: float) -> list[tuple[float, float]]:
    """PC12's corners: the outer channel's back at ``back`` on the knee's line, its bottom at ``bottom``."""
    r_out = back - HANGER_IN_FROM_OUTSIDE_IN
    r_in = r_out - HANGER_WIDE_IN
    return [(r_in, bottom), (r_out, bottom), (r_out, bottom - HANGER_OUTER_IN),
            (r_in + HANGER_POINT_IN, bottom - HANGER_DEEP_IN), (r_in, bottom - HANGER_INNER_IN)]


def along(point: tuple[float, float], way: float) -> tuple[float, float]:
    """The point BOLT_SPACE_IN from ``point`` down the brace (``way`` 1) or up it (-1)."""
    return point[0] + way * BOLT_SPACE_IN * DOWN[0], point[1] + way * BOLT_SPACE_IN * DOWN[1]


def brace_bolts(knee) -> list[tuple[float, float]]:
    """The four bolts: the hanger's round hole and its slot, then the clip's slot and its round hole."""
    return [knee.top, along(knee.top, 1.0), along(knee.bottom, -1.0), knee.bottom]


def clip_outline(knee) -> list[tuple[float, float]]:
    """PC11's corners: on the pad's face, its round hole on the knee's bottom bolt."""
    root = knee.shell_r + PAD_THK_IN
    v0 = knee.bottom[1] - CLIP_HOLE_UP_IN
    cut = CLIP_TOP_IN - CLIP_BOTTOM_IN
    return [(root, v0), (root + CLIP_BOTTOM_IN, v0), (root + CLIP_TOP_IN, v0 + cut),
            (root + CLIP_TOP_IN, v0 + CLIP_TALL_IN), (root, v0 + CLIP_TALL_IN)]


def pad_middle(knee) -> tuple[float, float]:
    """PC10B's middle: t along the knee's frame (the clip's thickness), and y (the clip's height)."""
    return knee.t_face - knee.side * CLIP_THK_IN / 2.0, knee.bottom[1] - CLIP_HOLE_UP_IN + CLIP_TALL_IN / 2.0


def slot_arcs(hole: tuple[float, float], way: float) -> list[tuple[tuple, tuple, tuple]]:
    """The slot about the round ``hole`` whose middle is the bolt ``way`` down the brace (1) or up it (-1), as a closed
    run of four arcs (start, middle, end): its outer side, one end, its inner side, the other end."""
    middle = math.atan2(way * DOWN[1], way * DOWN[0])
    half = (SLOT_LONG_IN - HOLE_DIA_IN) / 2.0 / BOLT_SPACE_IN  # of the slot's centreline, either way
    w = HOLE_DIA_IN / 2.0

    def on(radius: float, angle: float) -> tuple[float, float]:
        return hole[0] + radius * math.cos(angle), hole[1] + radius * math.sin(angle)

    def end(angle: float, out: float) -> tuple[float, float]:  # the end round's far point, along the arc
        centre = on(BOLT_SPACE_IN, angle)
        return centre[0] - out * w * math.sin(angle), centre[1] + out * w * math.cos(angle)

    a0, a1 = middle - half, middle + half
    outer, inner = BOLT_SPACE_IN + w, BOLT_SPACE_IN - w
    return [
        (on(outer, a0), on(outer, middle), on(outer, a1)),
        (on(outer, a1), end(a1, 1.0), on(inner, a1)),
        (on(inner, a1), on(inner, middle), on(inner, a0)),
        (on(inner, a0), end(a0, -1.0), on(outer, a0)),
    ]


# ----------------------------------------------------------------------------------------------- SolidWorks


def _outline(points, name: str):
    def draw(manager, to_sketch):
        pts = [to_sketch(p) for p in points]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1], strict=True):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: edge failed.")

    return draw


def _holes(frame, t: float, rounds, slots, name: str):
    """Round 13/16 holes at ``rounds`` and curved slots (``slot_arcs`` runs), on the plane at ``t``."""
    def draw(manager, to_sketch):
        for r, y in rounds:
            sx, sy = to_sketch(frame.world(r, t, y))
            if _create_circle(manager, sx, sy, HOLE_DIA_IN / 2.0 * _INCH) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")
        for arcs in slots:
            for start, middle, finish in arcs:
                (ax, ay), (mx, my), (bx, by) = (to_sketch(frame.world(r, t, y)) for r, y in (start, middle, finish))
                if manager.Create3PointArc(ax, ay, 0.0, bx, by, 0.0, mx, my, 0.0) is None:
                    raise SolidWorksError(f"{name}: slot edge failed.")

    return draw


def _cut_in(model, frame, t: float, at, rounds, slots, depth_in: float, body_name: str, name: str) -> None:
    """The holes cut both ways from the plane at ``t`` through ``at`` (r, y), on the body ``body_name`` alone (in a
    one-part stair the brace's flat leg lies against the hanger and the clip, and their holes differ)."""
    sketch = _sketch_through(model, frame.world(at[0], t, at[1]), frame.travel, f"{name}Holes",
                             _holes(frame, t, rounds, slots, name))
    body = next((b for b in s._bodies(model) if str(b.Name) == body_name), None)
    if body is None:
        raise SolidWorksError(f"{name}: its body {body_name} is not in the part.")
    feature = _cut_both_ways_in(model, sketch, depth_in, body)
    if feature is None:
        raise SolidWorksError(f"{name}: its bolt holes were not cut.")
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Holes")


def _new_body_name(model, before: set[str], name: str) -> str:
    made = [str(b.Name) for b in s._bodies(model) if str(b.Name) not in before]
    if len(made) != 1:
        raise SolidWorksError(f"{name}: expected one new body, found {len(made)}.")
    return made[0]


def build_hanger(model, frame, knee, back: float, bottom: float, name: str) -> None:
    """PC12 on the platform-end side of the knee's contact plane, with its round hole and slot."""
    outline = hanger_outline(back, bottom)
    r_mid = (outline[0][0] + outline[1][0]) / 2.0
    y_mid = bottom - HANGER_DEEP_IN / 2.0  # the middle of its box, which _extrude_to looks for
    before = s._body_names(model)
    sketch = _sketch_through(model, frame.world(r_mid, knee.t_face, y_mid), frame.travel, name,
                             _outline([frame.world(r, knee.t_face, y) for r, y in outline], name))
    _extrude_to(model, sketch, HANGER_THK_IN, frame.world(r_mid, knee.t_face - knee.side * HANGER_THK_IN / 2.0, y_mid),
                HANGER_DEEP_IN + 0.1, name)
    body = _new_body_name(model, before, name)
    _cut_in(model, frame, knee.t_face, knee.top, [knee.top], [slot_arcs(knee.top, 1.0)], HANGER_THK_IN + 0.05, body,
            name)


def build_brace(model, frame, knee, profile: str, name: str) -> None:
    """PC13: type 1's L3x3x3/8 on the knee's line with its bolts 1-11/16 from the heel, and its four holes."""
    before = s._body_names(model)
    _knee_angle(model, frame, knee, profile, name, gauge=GAUGE_IN)
    body = _new_body_name(model, before, name)
    t_leg = knee.t_face + knee.side * LEG_THK_IN / 2.0
    _cut_in(model, frame, t_leg, knee.top, brace_bolts(knee), [], LEG_THK_IN / 2.0 + 0.05, body, name)


def build_clip(model, frame, knee, name: str) -> None:
    """PC11 in line with the brace's flat leg, on the platform-end side of the contact plane, with its round hole
    and slot."""
    outline = clip_outline(knee)
    t_mid, y_mid = pad_middle(knee)
    r_mid = (outline[0][0] + outline[3][0]) / 2.0
    before = s._body_names(model)
    sketch = _sketch_through(model, frame.world(r_mid, knee.t_face, y_mid), frame.travel, name,
                             _outline([frame.world(r, knee.t_face, y) for r, y in outline], name))
    _extrude_to(model, sketch, CLIP_THK_IN, frame.world(r_mid, t_mid, y_mid), CLIP_TALL_IN + 0.1, name)
    body = _new_body_name(model, before, name)
    _cut_in(model, frame, knee.t_face, knee.bottom, [knee.bottom], [slot_arcs(knee.bottom, -1.0)],
            CLIP_THK_IN + 0.05, body, name)


def pad_spot(frame, knee) -> tuple[float, float]:
    """Where PC10B's middle is on the shell: the stair's plan angle, and height."""
    t_mid, y_mid = pad_middle(knee)
    x, _y, z = frame.world(knee.shell_r, t_mid, y_mid)
    return math.atan2(-x, z), y_mid
