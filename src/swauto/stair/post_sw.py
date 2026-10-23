"""Handrail posts on the outer stringer, from RailPosts.lsp and SpiralStringerHandrailPostWrap.lsp.

A post stands in front of each picked tread of every flight: an L2x2x1/4 with
its flat leg bolted to the outside face of the outer stringer, heel on the
downhill edge and the other leg straight out from the stringer. Its uphill
edge is 1/2 in downhill of the tread's front edge and its foot is 1/2 in above
the tread below, so the first tread of a flight has no post. The top is cut
along the rail slope 3/4 in, square to the slope, under the top rail's top
edge, which is 42 in above the stringer's top edge (HR_TOPMID in
SpiralStairHandrail.lsp). Two 13/16 holes go through the leg and the stringer,
1-1/8 in from the heel, 1 in and 4 in above the foot.

Each platform has a post at both ends of its outer channel (Stair Platform Top
View.lsp, Stair Platform Streatchout.lsp): the flat leg on the outside of the
web running toward the platform middle, heel a set distance in from the
platform end (the lisp's "move posts inwards"), the other leg straight out. It runs from 1/4 in above the channel bottom to
1/4 in under the platform's 42 in top rail, square, and bolts through the web
with two 13/16 holes 1-3/4 in apart, one above the other on the channel's
mid-depth, 1-1/8 in from the heel.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from swauto.comutil import com_value
from swauto.errors import SolidWorksError
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import BraceResult, _cylinder_radii, _face_at, _progress
from swauto.stair.platform_sw import (
    CHANNEL_IN,
    WEB_IN,
    _cut,
    _hole_in,
    _library,
    _radial,
    _upright_angle,
    _world,
    platform_lines,
)
from swauto.stair.stringer import THICKNESS_IN, TREAD_DEPTH_IN
from swauto.stair.stringer_sw import _create_circle

_INCH = 0.0254
PROFILE = ("ansi inch", "L Angle", "L2x2x0.25.SLDLFP")
LEG_IN = 2.0
THK_IN = 0.25
SETBACK_IN = 0.5  # uphill edge, downhill of the tread's front edge
FOOT_UP_IN = 0.5  # above the tread below
RAIL_TOP_IN = 42.0  # top rail's top edge above the stringer's top edge
TOP_GAP_IN = 0.75  # post top under the rail's top edge, square to the slope
HOLE_GAUGE_IN = 1.125  # from the heel
HOLE_UP_IN = (1.0, 4.0)  # above the foot
HOLE_DIA_IN = 0.8125
PLATFORM_POST_IN = 4.0  # heel in from the platform end, along the outer channel
PLATFORM_FOOT_IN = 0.25  # above the channel bottom
PLATFORM_TOP_GAP_IN = 0.25  # under the top rail's top edge, 42 in above the grating
PLATFORM_HOLE_SPACE_IN = 1.75  # one above the other, centered on the channel's depth


@dataclass(frozen=True)
class Post:
    index: int  # the tread it stands in front of
    phi: float  # heel, on the outer stringer
    foot: float
    cut: float  # top cut height at the heel
    slope: float  # rise per inch along the stringer

    def top(self, t: float) -> float:
        """Top cut height ``t`` in uphill of the heel."""
        return self.cut + t * self.slope


def post_profile(app) -> str:
    """The L2x2x0.25 file in this SolidWorks' weldment library."""
    return _library(app, PROFILE)


def read_post_treads(text: str, per_flight: int) -> tuple[int, ...]:
    """Tread numbers in one flight, as typed: "2, 4". Every flight gets the same ones."""
    picks = set()
    for token in text.replace(",", " ").split():
        try:
            picks.add(int(token))
        except ValueError:
            raise ValueError(f"Post treads are tread numbers in a flight, like 2, 4; not {token!r}.") from None
    bad = sorted(n for n in picks if not 2 <= n <= per_flight)
    if bad:
        raise ValueError(
            f"A post stands on the tread below its own, so post treads are 2 to {per_flight} "
            f"(the treads in one flight); not {', '.join(map(str, bad))}."
        )
    return tuple(sorted(picks))


def post_layout(places, per_flight: int, picks: tuple[int, ...], r_b: float) -> list[Post]:
    """One post per picked tread per flight. ``places`` are every pan, lowest first; ``r_b`` is
    the outer stringer's walk face, where the lisp develops it."""
    posts = []
    for first in range(0, len(places), per_flight):
        for pick in picks:
            tread, below = places[first + pick - 1], places[first + pick - 2]
            slope = (tread.y1 - below.y1) / ((tread.phi - below.phi) * r_b)
            heel = -(SETBACK_IN + LEG_IN)  # along the stringer from the tread's front edge
            front = tread.phi - TREAD_DEPTH_IN / 2.0 / r_b
            datum = tread.y1 + heel * slope  # the stringer's top edge runs through the tread's top front corner
            posts.append(
                Post(
                    index=tread.index,
                    phi=front + heel / r_b,
                    foot=below.y1 + FOOT_UP_IN,
                    cut=datum + RAIL_TOP_IN - TOP_GAP_IN * math.hypot(1.0, slope),
                    slope=slope,
                )
            )
    return posts


def add_handrail_posts(model, posts: list[Post], *, r_b: float, profile: str, progress=None) -> BraceResult:
    """Each post, its top cut along the rail, and its two bolt holes through the stringer.

    ``profile`` is from ``post_profile``.
    """
    face_r = r_b + THICKNESS_IN
    missed = []
    for post in posts:
        name = f"ElitePost{post.index:02d}"
        _upright_angle(model, post.phi, face_r, 1.0, 1.0, (post.foot, post.top(LEG_IN) + 0.1), LEG_IN, profile, name)
        _top_cut(model, post, face_r, name)
        _progress(progress, f"{name} placed")
        holes = _holes(model, post, face_r, r_b, name)
        if not holes:
            missed.append(str(post.index))
        _progress(progress, f"{name} holes {'cut' if holes else 'missed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    treads = ", ".join(str(p.index) for p in posts)
    note = (
        f"L2x2x1/4 handrail posts in front of tread{'s' if len(posts) > 1 else ''} {treads} on the outer "
        f"stringer, tops cut along the rail {TOP_GAP_IN:g} in under the 42 in top rail, two 13/16 holes each "
        "through the stringer."
        + (f" Holes missed at tread(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def add_platform_posts(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, profile: str,
    post_in: float = PLATFORM_POST_IN, progress=None,
) -> BraceResult:
    """Posts at both ends of the outer channel of the platform after tread ``tread_index``,
    each with its heel ``post_in`` in from the platform end."""
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b)
    half = (lines.phi_b - lines.phi_a) / 2.0
    web_r = lines.r_out * math.cos(half)  # the outer channel's back, on the bisector
    end_t = lines.r_out * math.sin(half) - post_in
    if end_t < LEG_IN + 1.0:
        raise SolidWorksError(f"Platform posts {post_in:g} in from the ends would meet in the middle.")
    ys = (lines.top - CHANNEL_IN + PLATFORM_FOOT_IN, tread_top + RAIL_TOP_IN - PLATFORM_TOP_GAP_IN)
    name = f"ElitePlatform{tread_index:02d}Post"
    mid = lines.phi_a + half
    middle = lines.top - CHANNEL_IN / 2.0
    hole_ys = (middle - PLATFORM_HOLE_SPACE_IN / 2.0, middle + PLATFORM_HOLE_SPACE_IN / 2.0)
    missed = []
    for label, heel_t, away in (("A", -end_t, 1.0), ("B", end_t, -1.0)):
        tag = f"{name}{label}"
        _upright_angle(model, mid, web_r, 1.0, away, ys, LEG_IN, profile, tag, heel_t=heel_t)
        _progress(progress, f"{tag} placed")
        holes = _platform_holes(model, mid, web_r, heel_t + away * HOLE_GAUGE_IN, hole_ys, tag)
        if not holes:
            missed.append(label)
        _progress(progress, f"{tag} holes {'cut' if holes else 'missed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: L2x2x1/4 posts {ys[1] - ys[0]:.2f} in long, {post_in:g} in in from "
        "both ends of the outer channel, bolted through its web with two 13/16 holes 1-3/4 in apart."
        + (f" Holes missed at end(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _platform_holes(model, mid: float, web_r: float, t: float, hole_ys: tuple[float, float], name: str) -> bool:
    """13/16 rounds through the post's flat leg and the outer channel's web."""
    points = [_world(mid, web_r + THK_IN, t, y) for y in hole_ys]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    face = _face_at(s._bodies(model), points[0], _radial(mid))
    if not _cut(model, face, f"{name}Holes", draw, THK_IN + WEB_IN + 0.1):
        return False
    in_web = [_world(mid, web_r - WEB_IN / 2.0, t, y) for y in hole_ys]
    return all(_hole_in(model, p) for p in points) and all(_channel_hole(model, p) for p in in_web)


def _channel_hole(model, point_in) -> bool:
    """The post's hole carried on into the channel web: the post shares its axis, so look at the channel alone."""
    point = [v * _INCH for v in point_in]
    for body in s._bodies(model):
        try:
            box = s._box_in(body)
        except Exception:
            continue
        if abs(box[4] - box[1] - CHANNEL_IN) > 0.05 or not all(
            box[i] - 0.1 <= point_in[i] <= box[i + 3] + 0.1 for i in range(3)
        ):
            continue
        if s._has_hole_axis(body, point, HOLE_DIA_IN / 2.0 * _INCH, 0.1 * _INCH) is True:
            return True
    return False


def _leg_face(model, post: Post, face_r: float, y: float):
    """Outside face of the flat leg, square to the radial line through the heel."""
    return _face_at(s._bodies(model), _world(post.phi, face_r + THK_IN, HOLE_GAUGE_IN, y), _radial(post.phi))


def _top_cut(model, post: Post, face_r: float, name: str) -> None:
    """Cut the top along the rail slope, through both legs."""
    face = _leg_face(model, post, face_r, post.foot + 2.5)
    lo, hi = -0.5, LEG_IN + 0.5
    over = post.top(hi) + 1.0

    def draw(manager, to_sketch):
        corners = ((lo, post.top(lo)), (hi, post.top(hi)), (hi, over), (lo, over))
        pts = [to_sketch(_world(post.phi, face_r + THK_IN, t, y)) for t, y in corners]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: top cut edge failed.")

    if not _cut(model, face, f"{name}Top", draw, LEG_IN + 0.5):
        raise SolidWorksError(f"{name}: the top was not cut along the rail.")


def _holes(model, post: Post, face_r: float, r_b: float, name: str) -> bool:
    """13/16 rounds through the flat leg and the stringer."""
    points = [_world(post.phi, face_r + THK_IN, HOLE_GAUGE_IN, post.foot + up) for up in HOLE_UP_IN]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    if not _cut(model, _leg_face(model, post, face_r, post.foot + 2.5), f"{name}Holes", draw, THK_IN + THICKNESS_IN + 0.1):
        return False
    in_stringer = [_world(post.phi, r_b + THICKNESS_IN / 2.0, HOLE_GAUGE_IN, post.foot + up) for up in HOLE_UP_IN]
    return all(_hole_in(model, p) for p in points) and all(_stringer_hole(model, p, r_b) for p in in_stringer)


def _stringer_hole(model, point_in, r_b: float) -> bool:
    """The post's hole carried on into the outer stringer: the post shares its axis, so look at the stringer alone."""
    point = [v * _INCH for v in point_in]
    for body in s._bodies(model):
        try:
            box = s._box_in(body)
        except Exception:
            continue
        if box[4] - box[1] < 12.0 or not all(box[i] - 1.0 <= point_in[i] <= box[i + 3] + 1.0 for i in range(3)):
            continue
        if any(abs(r - r_b) < 0.01 for r in _cylinder_radii(body)):
            if s._has_hole_axis(body, point, HOLE_DIA_IN / 2.0 * _INCH, 0.1 * _INCH) is True:
                return True
    return False
