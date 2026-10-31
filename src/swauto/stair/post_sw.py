"""Handrail posts on the outer stringer (and the inner one's, for the inside handrail), from RailPosts.lsp and
SpiralStringerHandrailPostWrap.lsp.

A post stands in front of each picked tread of every flight: an L2x2x1/4 with
its flat leg bolted to the outside face of the outer stringer, heel on the
downhill edge and the other leg straight out from the stringer. Its uphill
edge is 1/2 in downhill of the tread's front edge and its foot is 1/2 in above
the tread below, so the first tread of a flight has no post. The top is cut
along the rail slope 3/4 in, square to the slope, under the top rail's top
edge, which is 42 in above the stringer's top edge (HR_TOPMID in
SpiralStairHandrail.lsp), and the outstanding leg is cut back 45 degrees from
its root down to its toe so fingers sliding along under the rail clear it. Two
13/16 holes go through the leg and the stringer, 1-1/8 in from the heel, 1 in
and 4 in above the foot.

Each platform has a post at both ends of its outer channel (Stair Platform Top
View.lsp, Stair Platform Streatchout.lsp): the flat leg on the outside of the
web running toward the platform middle, heel a set distance in from the
platform end (the lisp's "move posts inwards"), the other leg straight out. It runs from 1/4 in above the channel bottom to
3/4 in under the platform's 42 in top rail, square, the same weld gap as on the
flights, with the outstanding leg cut back 45 degrees the same way, and bolts
through the web with two 13/16 holes 1-3/4 in apart, one above the other on the
channel's mid-depth, 1-1/8 in from the heel.

The inside handrail's platform posts are the same on channel C, the inner side (the user, 2026-10-30: "same rule
as outer"): on its tank side, the outstanding leg toward the shell.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass

from swauto.comutil import com_value
from swauto.errors import SolidWorksError
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import BraceResult, _cylinder_radii, _face_at, _progress
from swauto.stair.heights import RAIL_TOP_IN  # the top rail's top edge above the stringer's top edge
from swauto.stair.platform_sw import (
    CHANNEL_IN,
    SECTIONS,
    SHELL_CLIP_THK_IN,
    TAB_FROM_END_IN,
    TAB_THK_IN,
    WEB_IN,
    _cut,
    _hole_in,
    _library,
    _radial,
    _travel,
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
TOP_GAP_IN = 0.75  # post top under the rail's top edge, square to the slope
HOLE_GAUGE_IN = 1.125  # from the heel
HOLE_UP_IN = (1.0, 4.0)  # above the foot
HOLE_DIA_IN = 0.8125
PLATFORM_POST_IN = 4.0  # heel in from the platform end, along the outer channel
PLATFORM_FOOT_IN = 0.25  # above the channel bottom
PLATFORM_HOLE_SPACE_IN = 1.75  # one above the other, centered on the channel's depth
# Channel C's ends carry a shell tab and its shell clip on the tank side, where the inside handrail's end posts stand.
INNER_POST_IN_MIN = TAB_FROM_END_IN + TAB_THK_IN + SHELL_CLIP_THK_IN + 0.25


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


def flight_picks(picks, flight: int) -> tuple[int, ...]:
    """The post treads of one flight (0 the lowest): ``picks`` are the same treads for every flight, or one tuple
    of treads per flight (as the attachment rules place them)."""
    if picks and isinstance(picks[0], tuple):
        return tuple(picks[flight]) if flight < len(picks) else ()
    return tuple(picks)


def post_layout(places, per_flight: int, picks, r_b: float, rail_top: float = RAIL_TOP_IN) -> list[Post]:
    """One post per picked tread per flight (``flight_picks``). ``places`` are every pan, lowest first; ``r_b`` is
    the stringer's walk face, where the lisp develops it (the outer one's, or the inner one's for the inside
    handrail), and ``rail_top`` how far over the stringer's top edge the rail the post carries is."""
    posts = []
    for first in range(0, len(places), per_flight):
        for pick in flight_picks(picks, first // per_flight):
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
                    cut=datum + rail_top - TOP_GAP_IN * math.hypot(1.0, slope),
                    slope=slope,
                )
            )
    return posts


def add_handrail_posts(
    model, posts: list[Post], *, r_b: float, profile: str, progress=None, inner: bool = False,
) -> BraceResult:
    """Each post, its top cut along the rail and cut back 45 degrees, and its two bolt holes through the stringer.

    The posts on the flights are the same piece turned about the tank axis and raised, so the first
    is modeled and the rest are copied. The bolt holes are cut afterwards: each one also goes
    through the stringer. ``profile`` is from ``post_profile``. ``r_b`` is the stringer's walk face; ``inner``
    posts go on the inner stringer's tank face (``r_b`` its walk face), the outstanding leg toward the shell.
    """
    way, face_r = _post_side(r_b, inner)
    prefix = "ElitePostIn" if inner else "ElitePost"
    missed = []
    master_post = None
    master_body = None
    for post in posts:
        name = f"{prefix}{post.index:02d}"
        copied = False
        if master_body is not None and master_post is not None:
            copied = s._copy_turned(
                model, master_body, post.phi - master_post.phi, post.foot - master_post.foot, name,
            )
        if not copied:
            body = _shaped_post(model, post, face_r, profile, name, way)
            if master_body is None and body is not None:
                master_post, master_body = post, body
        _progress(progress, f"{name} {'copied' if copied else 'placed'}")
    for post in posts:
        name = f"{prefix}{post.index:02d}"
        holes = _holes(model, post, face_r, r_b, name, way)
        if not holes:
            missed.append(str(post.index))
        _progress(progress, f"{name} holes {'cut' if holes else 'missed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    treads = ", ".join(str(p.index) for p in posts)
    note = (
        f"L2x2x1/4 handrail posts in front of tread{'s' if len(posts) > 1 else ''} {treads} on the "
        f"{'inner stringer, on its tank face' if inner else 'outer stringer'}, tops cut along the rail "
        f"{TOP_GAP_IN:g} in under the rail they carry and the outstanding leg "
        "cut back 45 degrees, two 13/16 holes each through the stringer."
        + (f" Holes missed at tread(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _post_side(r_b: float, inner: bool) -> tuple[float, float]:
    """(way, face_r): the side of the stringer a flight post's flat leg is on, +1 out from the tank or -1 in
    toward it, and the radius of the leg's face against the stringer. On the inner stringer's tank face the
    face is concave, so the flat leg stands off it by its sag: it touches only at the heel's end."""
    if not inner:
        return 1.0, r_b + THICKNESS_IN
    tank_face = r_b - THICKNESS_IN
    return -1.0, tank_face - LEG_IN * LEG_IN / (2.0 * tank_face) - 0.001


def _shaped_post(model, post: Post, face_r: float, profile: str, name: str, way: float = 1.0):
    """The flight post with its sloped top and 45 degree cutback, before the bolt holes."""
    before = s._body_names(model)
    _upright_angle(model, post.phi, face_r, way, 1.0, (post.foot, post.top(LEG_IN) + 0.1), LEG_IN, profile, name)
    _top_cut(model, post, face_r, name, way)
    _cutback(model, post.phi, face_r, 0.0, 1.0, post.foot, post.top(THK_IN), name, inward=way)
    made = [body for body in s._bodies(model) if str(body.Name) not in before]
    if len(made) != 1:
        return None
    with contextlib.suppress(Exception):
        made[0].Name = name
    return made[0]


def side_post_heel(lines) -> float:
    """Radius of a side post's heel, back to back with the flight's end angle: the flight's top rail reaches
    a leg less its thickness out past the stringer's outside face, and the end angle's leg lies along it."""
    return lines.stringer_b + THICKNESS_IN + LEG_IN


def add_platform_posts(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, profile: str,
    post_in: float = PLATFORM_POST_IN, stringer_b: float | None = None, progress=None, spec=None,
    rail_top: float = RAIL_TOP_IN, inner: bool = False,
) -> BraceResult:
    """Posts at both ends of the outer channel of the platform after tread ``tread_index``,
    each with its heel ``post_in`` in from the platform end, and between them where ``spec`` (the
    platform's shape) puts them, along a straight outer channel or a rolled one. When the outer
    stringer's walk face ``stringer_b`` is in from the platform's ``r_b``, the end ones stand on the
    side channels instead. With ``inner`` they go on channel C for the inside handrail, at the same places along
    it; the inner stringer always meets C at its corner, so there are never side posts."""
    try:
        check_inner_post_in(post_in, inner)
    except ValueError as exc:
        raise SolidWorksError(str(exc)) from None
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b, stringer_b=None if inner else stringer_b,
                           spec=spec)
    between = [] if spec is None else list(spec.post_positions(inner))
    ys = (lines.top - CHANNEL_IN + PLATFORM_FOOT_IN, tread_top + rail_top - TOP_GAP_IN)
    name = f"ElitePlatform{tread_index:02d}Post{'In' if inner else ''}"
    way = -1.0 if inner else 1.0
    middle = lines.top - CHANNEL_IN / 2.0
    hole_ys = (middle - PLATFORM_HOLE_SPACE_IN / 2.0, middle + PLATFORM_HOLE_SPACE_IN / 2.0)
    places = []  # (label, angle or None for an end post, away)
    side_note = ""
    if lines.stringer_b < lines.r_b - 0.01:
        side_note = _side_posts(model, tread_index, lines, tread_top, profile, progress, rail_top).note
    else:
        places += [("A", None, 1.0), ("B", None, -1.0)]
    places += [(f"M{i}", lines.phi_a + along / lines.r_mid, 1.0) for i, along in enumerate(between, start=1)]
    missed = []
    for label, angle, away in places:
        tag = f"{name}{label}"
        mid, web_r, heel_t = platform_post_frame(lines, label, angle, post_in, inner)
        _upright_angle(model, mid, web_r, way, away, ys, LEG_IN, profile, tag, heel_t=heel_t)
        _cutback(model, mid, web_r, heel_t, away, ys[0], ys[1], tag, inward=way)
        _progress(progress, f"{tag} placed")
        back = lines.r_in if inner and lines.rolled else web_r  # a rolled C's post stands off its back by its sag
        holes = _platform_holes(model, mid, web_r, heel_t + away * HOLE_GAUGE_IN, hole_ys, tag, way, back)
        if not holes:
            missed.append(label)
        _progress(progress, f"{tag} holes {'cut' if holes else 'missed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    channel = "channel C, on its tank side" if inner else "the outer channel"
    ends = "" if side_note else f"{post_in:g} in in from both ends" + ("" if inner else " of the outer channel")
    more = f"{len(between)} between, by the radials" if between else ""
    note = (
        (side_note + " " if side_note else "")
        + (f"Platform after tread {tread_index}: L2x2x1/4 {'inside ' if inner else ''}posts {ys[1] - ys[0]:.2f} in "
           f"long, {', and '.join(part for part in (ends, more) if part)} on {channel}, outstanding legs cut "
           "back 45 degrees, bolted through its web with two 13/16 holes 1-3/4 in apart." if places else "")
        + (f" Holes missed at {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note.strip())


def check_inner_post_in(post_in: float, inner: bool = True) -> float:
    """The inside platform posts' distance in from the ends, if it keeps them clear of the shell tabs and clips at C's
    ends (the outer ones have none)."""
    if inner and post_in < INNER_POST_IN_MIN - 1e-9:
        raise ValueError(f"The inside platform posts must stand at least {INNER_POST_IN_MIN:g} in in from the ends, "
                         "clear of the shell clips' tabs on channel C.")
    return post_in


def platform_post_frame(lines, label: str, angle: float | None, post_in: float,
                        inner: bool = False) -> tuple[float, float, float]:
    """Where a post on a platform's outer channel (with ``inner``, on channel C) stands, as (frame angle, its heel's
    radius on it, the heel along the travel from it): an end post (``angle`` None) ``post_in`` in from its end, A or
    B by ``label``, any other at ``angle``. A straight channel is framed on the platform's bisector, a rolled one
    on the post's own radial line, where the arc runs square to it. The heel is on the channel's back, but on a
    rolled C, whose back is concave where the post stands, the flat leg stands off it by its sag and touches it at
    its end, as the inside posts do on the inner stringer (``_post_side``)."""
    back = lines.r_in if inner else lines.r_out
    half = (lines.phi_b - lines.phi_a) / 2.0
    if lines.rolled:
        if angle is None:
            angle = lines.phi_a + post_in / back if label == "A" else lines.phi_b - post_in / back
        return angle, back - (LEG_IN * LEG_IN / (2.0 * back) + 0.001 if inner else 0.0), 0.0
    mid = lines.phi_a + half
    web_r = back * math.cos(half)  # the channel's back, on the bisector
    if angle is None:
        end_t = back * math.sin(half) - post_in
        if end_t < LEG_IN + 1.0:
            raise SolidWorksError(f"Platform posts {post_in:g} in from the ends would meet in the middle.")
        return mid, web_r, -end_t if label == "A" else end_t
    return mid, web_r, web_r * math.tan(angle - mid)


def _side_posts(model, tread_index: int, lines, tread_top: float, profile: str, progress,
                rail_top: float = RAIL_TOP_IN) -> BraceResult:
    """On a stair narrower than its platforms: a post on each side channel just outside the flight's top
    rail, its flat leg out along the channel's back and bolted through the web, its other leg turned
    toward the flight, back to back with the flight's end angle and bolted to it. It runs up to the
    underside of the platform rail's top leg."""
    heel_r = side_post_heel(lines)
    ys = (lines.top - CHANNEL_IN + PLATFORM_FOOT_IN, tread_top + rail_top - THK_IN)
    name = f"ElitePlatform{tread_index:02d}Post"
    middle = lines.top - CHANNEL_IN / 2.0
    hole_ys = (middle - PLATFORM_HOLE_SPACE_IN / 2.0, middle + PLATFORM_HOLE_SPACE_IN / 2.0)
    missed = []
    for label, line_phi, away in (("A", lines.phi_a, -1.0), ("B", lines.phi_b, 1.0)):
        tag = f"{name}{label}"
        _upright_angle(model, line_phi, heel_r, 1.0, away, ys, LEG_IN, profile, tag)
        _progress(progress, f"{tag} placed")
        holes = _side_holes(model, line_phi, heel_r + HOLE_GAUGE_IN, away, hole_ys, tag)
        if not holes:
            missed.append(label)
        _progress(progress, f"{tag} holes {'cut' if holes else 'missed'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: L2x2x1/4 posts {ys[1] - ys[0]:.2f} in long on both side channels "
        "just outside the flights' top rails, up to the underside of the platform rail's top leg, bolted through "
        "the web with two 13/16 holes 1-3/4 in apart."
        + (f" Holes missed at end(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _side_holes(model, line_phi: float, r: float, away: float, hole_ys: tuple[float, float], name: str) -> bool:
    """13/16 rounds through a side post's flat leg and the side channel's web behind it."""
    points = [_world(line_phi, r, away * THK_IN, y) for y in hole_ys]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    face = _face_at(s._bodies(model), points[0], _travel(line_phi))
    if not _cut(model, face, f"{name}Holes", draw, THK_IN + WEB_IN + 0.1):
        return False
    in_web = [_world(line_phi, r, -away * WEB_IN / 2.0, y) for y in hole_ys]
    return all(_hole_in(model, p) for p in points) and all(_channel_hole(model, p) for p in in_web)


def _platform_holes(model, mid: float, web_r: float, t: float, hole_ys: tuple[float, float], name: str,
                    way: float = 1.0, back: float | None = None) -> bool:
    """13/16 rounds through the post's flat leg and the channel's web: the outer channel's, its back at the heel
    ``web_r``, or with ``way`` -1 channel C's, its back at ``back``."""
    points = [_world(mid, web_r + way * THK_IN, t, y) for y in hole_ys]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    face = _face_at(s._bodies(model), points[0], _radial(mid))
    if not _cut(model, face, f"{name}Holes", draw, THK_IN + WEB_IN + 0.1):
        return False
    back = web_r if back is None else back
    in_web = [_world(mid, back - way * WEB_IN / 2.0, t, y) for y in hole_ys]
    return all(_hole_in(model, p) for p in points) and all(_channel_hole(model, p) for p in in_web)


def _channel_hole(model, point_in) -> bool:
    """The post's hole carried on into the channel web: the post shares its axis, so look at the channel alone."""
    point = [v * _INCH for v in point_in]
    for body in s._bodies(model):
        try:
            box = s._box_in(body)
        except Exception:
            continue
        if all(abs(box[4] - box[1] - section.depth_in) > 0.05 for section in SECTIONS.values()) or not all(
            box[i] - 0.1 <= point_in[i] <= box[i + 3] + 0.1 for i in range(3)
        ):
            continue
        if s._has_hole_axis(body, point, HOLE_DIA_IN / 2.0 * _INCH, 0.1 * _INCH) is True:
            return True
    return False


def _leg_face(model, post: Post, face_r: float, y: float, way: float = 1.0):
    """The flat leg's face away from the stringer, square to the radial line through the heel."""
    normal = tuple(way * v for v in _radial(post.phi))
    return _face_at(s._bodies(model), _world(post.phi, face_r + way * THK_IN, HOLE_GAUGE_IN, y), normal)


def _top_cut(model, post: Post, face_r: float, name: str, way: float = 1.0) -> None:
    """Cut the top along the rail slope, through both legs."""
    face = _leg_face(model, post, face_r, post.foot + 2.5, way)
    lo, hi = -0.5, LEG_IN + 0.5
    over = post.top(hi) + 1.0

    def draw(manager, to_sketch):
        corners = ((lo, post.top(lo)), (hi, post.top(hi)), (hi, over), (lo, over))
        pts = [to_sketch(_world(post.phi, face_r + way * THK_IN, t, y)) for t, y in corners]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: top cut edge failed.")

    if not _cut(model, face, f"{name}Top", draw, LEG_IN + 0.5):
        raise SolidWorksError(f"{name}: the top was not cut along the rail.")


def _cutback(
    model, line_phi: float, heel_r: float, heel_t: float, away: float, foot: float, top: float, name: str,
    inward: float = 1.0,
) -> None:
    """Cut the outstanding leg of an upright angle back 45 degrees from ``top`` at its root down to its toe.

    The heel is at ``heel_r`` on the radial line at ``line_phi``, ``heel_t`` along the travel, the
    other leg running ``away`` along it and the outstanding leg ``inward`` along the radial. Sketched on the
    leg's inside face, outside the other leg and no more than 0.1 in over the top, so cut before the rails go on
    it takes nothing else.
    """
    face_t = heel_t + away * THK_IN
    normal = tuple(away * v for v in _travel(line_phi))
    face = _face_at(s._bodies(model), _world(line_phi, heel_r + inward * (THK_IN + LEG_IN / 2.0), face_t, foot + 2.5),
                    normal)
    root, past = heel_r + inward * THK_IN, heel_r + inward * (LEG_IN + 0.5)
    corners = ((root, top + 0.1), (root, top), (past, top - abs(past - root)), (past, top + 0.1))

    def draw(manager, to_sketch):
        pts = [to_sketch(_world(line_phi, r, face_t, y)) for r, y in corners]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: cutback edge failed.")

    if not _cut(model, face, f"{name}Cutback", draw, THK_IN + 0.1):
        raise SolidWorksError(f"{name}: the outstanding leg was not cut back 45 degrees.")


def _holes(model, post: Post, face_r: float, r_b: float, name: str, way: float = 1.0) -> bool:
    """13/16 rounds through the flat leg and the stringer."""
    points = [_world(post.phi, face_r + way * THK_IN, HOLE_GAUGE_IN, post.foot + up) for up in HOLE_UP_IN]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    face = _leg_face(model, post, face_r, post.foot + 2.5, way)
    if not _cut(model, face, f"{name}Holes", draw, THK_IN + THICKNESS_IN + 0.1):
        return False
    in_stringer = [_world(post.phi, r_b + way * THICKNESS_IN / 2.0, HOLE_GAUGE_IN, post.foot + up)
                   for up in HOLE_UP_IN]
    return all(_hole_in(model, p) for p in points) and all(_stringer_hole(model, p, r_b) for p in in_stringer)


def _stringer_hole(model, point_in, r_b: float) -> bool:
    """The post's hole carried on into the stringer whose walk face is ``r_b``: the post shares its axis, so look
    at the stringer alone."""
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
