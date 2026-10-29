"""Outer grab rail: a 1-1/2 in pipe rolled to a helix on the walk side of the flight posts.

From HR_TOPMID's grab rail (SpiralStairHandrail.lsp) and SpiralStairHandrailWrap.lsp. The pipe's top
is 34 in over the stringer's top edge, as the top rail's is 42. On the bottom flight it starts over
the front edge of tread 1; at a platform, each flight's pipe stops on the vertical through the
midrail's miter with the platform midrail, and so does the top flight's at a top platform (with
none, at the top tread's front edge). The pipe's top line meets those verticals and its ends are
cut square, each lengthened or shortened by the same signed amount on every flight, and each
takes a 1-5/8 in round cut from 1/4 in flat bar, welded on.

Each flight post carries the pipe on a PC #34 hanging under it: 3/4 x 3/4 bar cut from 3/4 plate
to a quarter turn, 1-1/2 in inside and 2-1/4 in outside radius, 3-3/16 in overall each way. Its leg
at the bottom runs level to the post, its end welded to the walk side of the post's flat leg; its
leg up from the bend carries the pipe centered on it, the top cut along the pipe's slope.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from swauto.comutil import com_value
from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import BraceResult, _progress
from swauto.stair.platform_sw import _travel, _world
from swauto.stair.post_sw import PLATFORM_POST_IN, RAIL_TOP_IN, Post
from swauto.stair.rail_sw import (
    MID_TOP_IN,
    PLATFORM_MID_TOP_IN,
    _draw_section,
    _Flight,
    _flights,
    _joint,
    _plane_through,
    _trim,
)
from swauto.stair.stringer import THICKNESS_IN
from swauto.stair.stringer_sw import _names, _rename_new, _select_feature
from swauto.tank.shell import _clear_selection, _close_sketch, _open_sketch

_INCH = 0.0254
GRAB_TOP_IN = 34.0  # pipe top over the stringer's top edge
PIPE_OD_IN = 1.9  # 1-1/2 in Sch 40
PIPE_WALL_IN = 0.145
CAP_DIA_IN = 1.625
CAP_THK_IN = 0.25
BRACKET_IN = 0.75  # PC #34, 3/4 plate cut 3/4 wide
BRACKET_INSIDE_R_IN = 1.5
BRACKET_OUTSIDE_R_IN = 2.25
BRACKET_OVERALL_IN = 3.1875
BRACKET_AT_IN = 1.0  # its middle along the post's flat leg, uphill of the heel


@dataclass(frozen=True)
class GrabRail:
    """The pipe's top over the stringer's top edge, and the signed lengths every flight's pipe is
    lengthened by at its low and its high end (negative shortens)."""

    top: float = GRAB_TOP_IN
    low: float = 0.0
    high: float = 0.0


@dataclass(frozen=True)
class _Pipe:
    flight: _Flight
    radius: float  # of its centerline
    top: float

    @property
    def alpha(self) -> float:
        return math.atan(self.flight.rise_per_rad / self.radius)

    def center_y(self, phi: float) -> float:
        """Centerline height: the top of a radial slice, 1/cos of the slope over it, is ``top`` over the stringer's top edge."""
        return self.flight.top(phi) - RAIL_TOP_IN + self.top - PIPE_OD_IN / 2.0 / math.cos(self.alpha)

    def center(self, phi: float) -> tuple[float, float, float]:
        return _world(phi, self.radius, 0.0, self.center_y(phi))

    def tangent(self, phi: float) -> tuple[float, float, float]:
        return self.flight.tangent(phi, self.radius)

    def end(self, cut: float, more: float, way: float) -> float:
        """Centerline angle of a square end whose top is on the vertical at ``cut``, ``more`` inches
        further out along the pipe, ``way`` -1 at the low end and +1 at the high."""
        top_back = PIPE_OD_IN / 2.0 * math.sin(self.alpha) / self.radius
        return cut + top_back + way * more * math.cos(self.alpha) / self.radius


def add_grab_rails(
    model, places, per_flight: int, posts: list[Post], *, r_a: float, r_b: float, platforms: int,
    top_platform: bool, post_in: float = PLATFORM_POST_IN, mid_top: float = PLATFORM_MID_TOP_IN,
    grab: GrabRail = GrabRail(), platform_b: float | None = None, progress=None,
) -> BraceResult:
    """The pipe along every flight with its two caps, and a PC #34 to it from each flight post.

    ``places`` are every pan, lowest first; ``posts`` are the flight posts (``post_sw.post_layout``);
    ``post_in`` and ``mid_top`` place the platform midrail miters the pipe stops at. ``r_b`` is the
    outer stringer's walk face, ``platform_b`` the platform's when the treads are narrower.
    """
    face_r = r_b + THICKNESS_IN  # the flight posts' walk side
    radius = face_r - BRACKET_OVERALL_IN + BRACKET_IN / 2.0  # over the middle of the PC #34's upright
    pb = r_b if platform_b is None else platform_b
    flights = _flights(places, per_flight, r_b)
    landings = len(flights) - 1 + (1 if top_platform else 0)
    pipes: list[tuple[_Pipe, float, float]] = []
    for k, flight in enumerate(flights):
        name = f"EliteGrabF{k + 1}"
        if k == 0:
            low = flight.front(flight.first)
        else:
            low = _miter_phi(flights[k - 1], flight, face_r, r_a, pb, post_in, mid_top, "B")
        if k < landings:
            high = _miter_phi(flight, None, face_r, r_a, pb, post_in, mid_top, "A")
        else:
            high = flight.front(flight.last)
        pipe = _Pipe(flight, radius, grab.top)
        lo, hi = pipe.end(low, grab.low, -1.0), pipe.end(high, grab.high, 1.0)
        if hi - lo < flight.step / 2.0:
            raise SolidWorksError(f"{name}: the grab rail end adjustments leave too little pipe.")
        _pipe(model, pipe, lo, hi, name)
        _cap(model, pipe, lo, -1.0, f"{name}CapLow")
        _cap(model, pipe, hi, 1.0, f"{name}CapHigh")
        pipes.append((pipe, lo, hi))
        _progress(progress, f"{name} placed")
    skipped = []
    master_post = None
    master_body = None
    for post in posts:
        name = f"EliteGrabBracket{post.index:02d}"
        pipe, lo, hi = pipes[min(len(pipes) - 1, (post.index - 1) // per_flight)]
        phi = post.phi + math.atan2(BRACKET_AT_IN, radius)
        reach = (BRACKET_IN / 2.0 + PIPE_OD_IN) / radius
        if not lo + reach <= phi <= hi - reach:
            skipped.append(str(post.index))
            _progress(progress, f"{name} skipped")
            continue
        # The connector, including the cut under the pipe, is the same piece turned and raised
        # with its post. The pipe itself is not copied.
        copied = False
        if master_body is not None and master_post is not None:
            copied = s._copy_turned(
                model, master_body, post.phi - master_post.phi, post.foot - master_post.foot, name,
            )
        if not copied:
            before = s._body_names(model)
            _bracket(model, post, pipe, phi, face_r, name)
            made = [body for body in s._bodies(model) if str(body.Name) not in before]
            if len(made) == 1:
                with contextlib.suppress(Exception):
                    made[0].Name = name
                if master_body is None:
                    master_post, master_body = post, made[0]
        _progress(progress, f"{name} {'copied' if copied else 'placed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Grab rail: 1-1/2 in Sch 40 pipe {grab.top:g} in over the stringer's top edge on the walk side of the "
        f"outer posts, rolled to a helix on each flight, from tread 1 and the midrail miters at the platforms, "
        f"1-5/8 in round caps on both ends, and a PC #34 3/4 x 3/4 bracket under it from each flight post."
        + (f" No bracket at post(s) {', '.join(skipped)}: the pipe does not reach them." if skipped else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _miter_phi(below, above, face_r, r_a, r_b, post_in, mid_top, side: str) -> float:
    """Angle of the vertical through the midrail's miter with the platform midrail, where the lisp stops the pipe.
    Read off the joint point, it is taken to the turn nearest the flight's own angles: atan2 wraps at 180°."""
    joint, _normal = _joint(below, above, face_r, r_a, r_b, post_in, side, mid_top, MID_TOP_IN)
    near = below.last.phi
    return near + math.remainder(math.atan2(-joint[0], joint[2]) - near, 2.0 * math.pi)


def _pipe(model, pipe: _Pipe, lo: float, hi: float, name: str) -> None:
    """The pipe from its square end at ``lo`` to the one at ``hi``.

    As the rails are: the ring's slice in the radial plane where the helix starts, stretched up by
    1/cos of the slope, swept a little past both ends and cut square there. The helix starts on the
    Top plane, and SolidWorks only sweeps quickly from a path that starts on the profile's plane.
    """
    flight = pipe.flight
    past = PIPE_OD_IN / pipe.radius
    start, end = lo - past, hi + past
    stretch = 1.0 / math.cos(pipe.alpha)
    helix = s._helix(model, pipe.radius, flight.rise_per_rad * (end - start), (end - start) / (2.0 * math.pi), name, start)
    y = pipe.center_y(start)
    plane = _plane_through(model, _world(start, pipe.radius, 0.0, y), _travel(start), f"{name}Prof")
    before = _names(model)
    _open_sketch(model, plane)
    try:
        sketch = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]

        def at(out: float, up: float):
            return s._to_sketch(data, [v * _INCH for v in _world(start, pipe.radius + out, 0.0, y + up)])[:2]

        c = at(0.0, 0.0)
        for ring in (PIPE_OD_IN / 2.0, PIPE_OD_IN / 2.0 - PIPE_WALL_IN):
            major, minor = at(0.0, ring * stretch), at(ring, 0.0)
            if model.SketchManager.CreateEllipse(c[0], c[1], 0.0, major[0], major[1], 0.0, minor[0], minor[1], 0.0) is None:
                raise SolidWorksError(f"{name}: pipe ellipse failed.")
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    profile = _rename_new(model, before, f"{name}Prof", "pipe profile")
    _clear_selection(model)
    if not (
        _select_feature(model, profile, "SKETCH", mark=1, append=False)
        and _select_feature(model, helix, "REFERENCECURVES", mark=4, append=True)
    ):
        raise SolidWorksError(f"{name}: could not select the pipe profile and its helix.")
    bodies0 = s._body_names(model)
    feature = model.FeatureManager.InsertProtrusionSwept3(
        False, False, 0, False, False, 0, 0, False, 0.0, 0.0, 0, 0, False, True, True, 0.0, True
    )
    if feature is None:
        raise SolidWorksError(f"{name}: the pipe sweep was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
    _trim(model, bodies0, pipe.center(lo), tuple(-v for v in pipe.tangent(lo)), f"{name}LowEnd")
    _trim(model, bodies0, pipe.center(hi), pipe.tangent(hi), f"{name}HighEnd")


def _cap(model, pipe: _Pipe, phi: float, way: float, name: str) -> None:
    """The 1-5/8 in round on the pipe's end at ``phi``, ``way`` -1 at the low end and +1 at the high."""
    normal = tuple(way * v for v in pipe.tangent(phi))
    middle = tuple(pipe.center(phi)[i] + normal[i] * CAP_THK_IN / 2.0 for i in range(3))

    def draw(manager, to_sketch):
        cx, cy = to_sketch(middle)
        if manager.CreateCircleByRadius(cx, cy, 0.0, CAP_DIA_IN / 2.0 * _INCH) is None:
            raise SolidWorksError(f"{name}: cap circle failed.")

    _extrude_mid(model, _sketch_through(model, middle, normal, name, draw), CAP_THK_IN, name)


def _bracket(model, post: Post, pipe: _Pipe, phi: float, face_r: float, name: str) -> None:
    """PC #34 hanging under the pipe at ``post``: its foot's end on the walk side of the post's flat leg,
    its upright under the pipe at ``phi``, cut back along the pipe's slope to sit tight under it."""
    under = pipe.center_y(phi) - PIPE_OD_IN / 2.0 / math.cos(pipe.alpha)  # the pipe's underside over the upright
    bend = under - (BRACKET_OVERALL_IN - BRACKET_OUTSIDE_R_IN)  # the bend's center; the upright runs straight above it
    top = under + BRACKET_IN  # past the underside on the uphill face, to be cut back
    upright = BRACKET_OVERALL_IN - BRACKET_IN
    # (in from the post, height, round) around the outline, from the foot's end on the post.
    outline = (
        (0.0, bend - BRACKET_OUTSIDE_R_IN, 0.0),
        (BRACKET_OVERALL_IN, bend - BRACKET_OUTSIDE_R_IN, BRACKET_OUTSIDE_R_IN),
        (BRACKET_OVERALL_IN, top, 0.0),
        (upright, top, 0.0),
        (upright, bend - BRACKET_INSIDE_R_IN, BRACKET_INSIDE_R_IN),
        (0.0, bend - BRACKET_INSIDE_R_IN, 0.0),
    )

    def draw(manager, to_sketch):
        _draw_section(manager, outline, name, lambda u, v: to_sketch(_world(post.phi, face_r - u, BRACKET_AT_IN, v)))

    bodies0 = s._body_names(model)
    sketch = _sketch_through(model, _world(post.phi, face_r, BRACKET_AT_IN, bend), _travel(post.phi), name, draw)
    _extrude_mid(model, sketch, BRACKET_IN, name)
    # Square to the pipe through its bottom line over the upright: the pipe center that line hangs from is downhill.
    at = phi - PIPE_OD_IN / 2.0 * math.sin(pipe.alpha) / pipe.radius
    level = _travel(at)
    up = (-math.sin(pipe.alpha) * level[0], math.cos(pipe.alpha), -math.sin(pipe.alpha) * level[2])
    bottom = tuple(pipe.center(at)[i] - PIPE_OD_IN / 2.0 * up[i] for i in range(3))
    _trim(model, bodies0, bottom, up, f"{name}Top")


def _sketch_through(model, point, normal, name: str, draw):
    """Sketch on a plane through ``point`` square to ``normal``; ``draw(manager, to_sketch)`` with points in inches."""
    plane = _plane_through(model, point, normal, name)
    before = _names(model)
    _open_sketch(model, plane)
    try:
        sketch = com_value(model.GetActiveSketch2)
        data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]
        draw(model.SketchManager, lambda p: tuple(s._to_sketch(data, [v * _INCH for v in p])[:2]))
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    return _rename_new(model, before, f"{name}Sk", "sketch")


def _extrude_mid(model, sketch, depth_in: float, name: str) -> None:
    """Its own body, ``depth_in`` thick, half each side of the sketch."""
    _clear_selection(model)
    if not _select_feature(model, sketch, "SKETCH", mark=0, append=False):
        raise SolidWorksError(f"{name}: could not select its sketch.")
    depth = depth_in * _INCH
    # End condition 6 is mid plane, D1 the whole depth; not merged, so it stays a piece of its own.
    legacy = (
        True, False, False, 6, 0, depth, 0.0, False, False, False, False, 0.0, 0.0,
        False, False, False, False, False, True, True,
    )
    feature = None
    for args in (legacy, legacy + (0, 0.0, False)):
        try:
            feature = model.FeatureManager.FeatureExtrusion2(*args)
        except Exception:
            continue
        if feature is not None:
            break
    if feature is None:
        raise SolidWorksError(f"{name}: the extrude was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
