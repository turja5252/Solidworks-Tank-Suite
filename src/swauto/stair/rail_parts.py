"""The outer handrail as parts (partify, 2026-10-30): the posts on each platform's channels, the toe plates, the top
rail and the midrail along each flight and across each platform, and the closed end at the stair's foot.

Each piece is built in a part of its own by the one-part build's own steps (rail_sw, post_sw), at its real place on
the ground-0 stair, so its placement is only the stair's turn and ground. A bolt hole the one-part build cuts through
two pieces at once is cut in each piece's part from the same numbers: a platform post has its channel's two holes and
its end piece's two, and the channel has the posts' (``frame_holes``, cut in the frame's parts).

As stair_sw._handrail_posts builds it: the platform posts and toe plates with the flight posts, the top rail and
midrail when asked, and the foot's closed end with both; on a stair narrower than its platforms, the side posts and
the corner pieces instead of the end posts and level pieces. The inside handrail's full guardrail is the same pieces
mirrored onto the inner stringer and channel C (``Rails.side`` -1), and its pipe handrail (Elite STWE) only the pipe
on its posts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.errors import SolidWorksError
from swauto.stair import grab_sw as g
from swauto.stair import rail_split_sw as rs
from swauto.stair import rail_sw as r
from swauto.stair import stair_sw as s
from swauto.stair.platform_parts import _holes_through
from swauto.stair.platform_sw import CHANNEL_IN, WEB_IN, _radial, _travel, _upright_angle, _world, platform_lines
from swauto.stair.post_sw import (
    HOLE_DIA_IN,
    HOLE_GAUGE_IN,
    LEG_IN,
    PLATFORM_FOOT_IN,
    PLATFORM_HOLE_SPACE_IN,
    RAIL_TOP_IN,
    THK_IN,
    TOP_GAP_IN,
    _cutback,
    _post_side,
    platform_post_frame,
    side_post_heel,
)
from swauto.stair.stringer import THICKNESS_IN, PlatformSpec

POST_HOLE_DEPTH_IN = THK_IN + WEB_IN + 0.1  # through a post's flat leg and the channel's web, as post_sw cuts them
END_HOLE_DEPTH_IN = 2.0 * THK_IN + 0.1  # through an end piece's leg and the post's, as rail_sw cuts them


@dataclass(frozen=True)
class Rails:
    """The outer handrail's numbers on the ground-0 stair, as stair_sw._handrail_posts hands them on: ``r_b`` the
    outer stringer's walk face, ``pb`` the platforms' outer walk face (a platform is always full width); the top
    rail's height and the flights' midrail's (None: halfway up to it). With ``side`` -1 the inside handrail's, on
    the inner stringer (``r_a``) and channel C; ``railed`` is whether this side's platforms have their rails, where a
    pipe on its flight posts stops at the midrail's miters (the inside's pipe handrail, Elite STWE, has none)."""

    places: tuple
    per_flight: int
    r_a: float
    r_b: float
    pb: float
    platforms: int
    top_platform: bool
    post_in: float
    mid_top: float
    top_rail: bool
    mid_rail: bool
    shapes: tuple = ()
    rail_top: float = RAIL_TOP_IN
    flight_mid: float | None = None
    side: float = 1.0
    railed: bool = True

    @property
    def inner(self) -> bool:
        return self.side < 0

    @property
    def walk(self) -> float:
        """The walk face of the stringer this side's posts are on."""
        return self.r_a if self.inner else self.r_b

    @property
    def face_r(self) -> float:
        """The rails' outside face, over the stringer's back face."""
        return self.walk + self.side * THICKNESS_IN

    @property
    def flights(self) -> list:
        return r._flights(self.places, self.per_flight, self.walk, self.shapes, self.rail_top, self.flight_mid,
                          self.side)

    @property
    def word(self) -> str:
        """The pieces' labels' word for the side: none outside."""
        return "inside " if self.inner else ""

    @property
    def tag(self) -> str:
        """The pieces' names' mark for the side: none outside."""
        return "In" if self.inner else ""

    @property
    def count(self) -> int:
        """Platforms: the mid ones and the top one."""
        return self.platforms + (1 if self.top_platform else 0)

    @property
    def landings(self) -> int:
        return len(self.flights) - 1 + (1 if self.top_platform else 0)

    def shape(self, k: int) -> PlatformSpec | None:
        return self.shapes[k - 1] if k - 1 < len(self.shapes) else None

    def lines(self, k: int):
        """Platform ``k`` (1 the lowest), as the handrail sees it."""
        last = self.places[k * self.per_flight - 1]
        return platform_lines(phi=last.phi, tread_top=last.y1, r_a=self.r_a, r_b=self.pb,
                              stringer_b=None if self.inner else self.r_b, spec=self.shape(k))

    def wraps(self, k: int) -> bool:
        """The rails wrap platform ``k``'s outer corners: outside, on a stair narrower than the platform; the inside
        never does (``rail_sw._wraps``)."""
        return not self.inner and r._narrow(self.lines(k))

    def tread_top(self, k: int) -> float:
        return self.places[k * self.per_flight - 1].y1

    def sides_met(self, k: int) -> tuple[str, ...]:
        """The platform's sides a flight meets: A from below, and B on a mid platform."""
        return ("A", "B") if k <= len(self.flights) - 1 else ("A",)


# ------------------------------------------------------------------------------------------------ the posts


@dataclass(frozen=True)
class PostSpot:
    """A post on platform ``k``: on the outer channel (``side`` False: its frame angle, the channel back's radius
    there, the heel along the travel and the way its flat leg runs) or, on a narrow stair, on side channel A or B.
    ``way`` is the way its outstanding leg stands: off the walk, out from the tank on D (+1), in toward it on C."""

    k: int
    label: str
    side: bool
    phi: float
    heel_r: float
    heel_t: float
    away: float
    ys: tuple[float, float]
    way: float = 1.0


def post_spots(rails: Rails, k: int) -> list[PostSpot]:
    """Platform ``k``'s posts, as post_sw.add_platform_posts places them."""
    lines = rails.lines(k)
    spec = rails.shape(k)
    tread_top = rails.tread_top(k)
    foot = lines.top - CHANNEL_IN + PLATFORM_FOOT_IN
    out = []
    if rails.wraps(k):
        heel_r = side_post_heel(lines)
        ys = (foot, tread_top + rails.rail_top - THK_IN)
        out += [PostSpot(k, label, True, line_phi, heel_r, 0.0, away, ys)
                for label, line_phi, away in (("A", lines.phi_a, -1.0), ("B", lines.phi_b, 1.0))]
        places = []
    else:
        places = [("A", None, 1.0), ("B", None, -1.0)]
    between = [] if spec is None else list(spec.post_positions(rails.inner))
    places += [(f"M{i}", lines.phi_a + along / lines.r_mid, 1.0) for i, along in enumerate(between, start=1)]
    ys = (foot, tread_top + rails.rail_top - TOP_GAP_IN)
    for label, angle, away in places:
        mid, web_r, heel_t = platform_post_frame(lines, label, angle, rails.post_in, rails.inner)
        out.append(PostSpot(k, label, False, mid, web_r, heel_t, away, ys, rails.side))
    return out


def _hole_ys(rails: Rails, k: int) -> tuple[float, float]:
    middle = rails.lines(k).top - CHANNEL_IN / 2.0
    return middle - PLATFORM_HOLE_SPACE_IN / 2.0, middle + PLATFORM_HOLE_SPACE_IN / 2.0


def channel_holes(rails: Rails, spot: PostSpot) -> tuple[list, tuple[float, float, float]]:
    """The two holes a post bolts to its channel with (points, axis): post_sw._platform_holes, or _side_holes for
    a side post."""
    hole_ys = _hole_ys(rails, spot.k)
    if spot.side:
        points = [_world(spot.phi, spot.heel_r + HOLE_GAUGE_IN, spot.away * THK_IN, y) for y in hole_ys]
        return points, _travel(spot.phi)
    t = spot.heel_t + spot.away * HOLE_GAUGE_IN
    return [_world(spot.phi, spot.heel_r + spot.way * THK_IN, t, y) for y in hole_ys], _radial(spot.phi)


def end_holes(rails: Rails, spot: PostSpot) -> tuple[list, tuple[float, float, float]] | None:
    """The two holes the top rail's end piece bolts to this post with (points, axis), if one does: rail_sw._end_piece
    at an end post, _corner_end_piece at a side post, where a flight meets the platform and the top rail is on."""
    if not rails.top_rail or spot.label not in rails.sides_met(spot.k) or spot.k > rails.landings:
        return None
    grating = rails.tread_top(spot.k)
    middle = (grating + rails.mid_top - r.BAR_IN + grating + rails.rail_top) / 2.0
    if spot.side:
        side = r._sides(rails.lines(spot.k))[spot.label]
        t = side.out_t * HOLE_GAUGE_IN
        return ([side.world(spot.heel_r - THK_IN, t, middle + dy)
                 for dy in (r.END_BOLT_SPACE_IN / 2.0, -r.END_BOLT_SPACE_IN / 2.0)], _radial(side.phi))
    post = _rail_post(rails, spot.k, spot.label)
    return ([post.world(post.way * HOLE_GAUGE_IN, post.away * THK_IN, middle + dy)
             for dy in (r.END_BOLT_SPACE_IN / 2.0, -r.END_BOLT_SPACE_IN / 2.0)], _travel(post.mid))


def _rail_post(rails: Rails, k: int, side: str):
    return r._post(rails.flights[k - 1], rails.r_a, rails.pb, rails.post_in, side)


def build_post(model, rails: Rails, spot: PostSpot, profile: str, name: str) -> None:
    """The post (post_sw.add_platform_posts' steps): the L2x2 up from the channel, its outstanding leg cut back 45
    degrees (not a side post's), its two holes to the channel and, where the top rail's end piece bolts to it,
    that piece's two."""
    _upright_angle(model, spot.phi, spot.heel_r, spot.way, spot.away, spot.ys, LEG_IN, profile, name,
                   heel_t=spot.heel_t)
    if not spot.side:
        _cutback(model, spot.phi, spot.heel_r, spot.heel_t, spot.away, spot.ys[0], spot.ys[1], name, inward=spot.way)
    points, axis = channel_holes(rails, spot)
    _holes_through(model, points[0], axis, points, HOLE_DIA_IN, POST_HOLE_DEPTH_IN, f"{name}Channel")
    end = end_holes(rails, spot)
    if end is not None:
        points, axis = end
        _holes_through(model, points[0], axis, points, HOLE_DIA_IN, END_HOLE_DEPTH_IN, f"{name}End")


def frame_holes(rails: Rails, k: int) -> dict[str, list[tuple[list, tuple[float, float, float]]]]:
    """The posts' holes in platform ``k``'s channels, by member: "D" the outer side ("C" the inner, for the inside
    handrail), "A" and "B" the ends (a narrow stair's side posts)."""
    out: dict[str, list] = {}
    for spot in post_spots(rails, k):
        out.setdefault(spot.label if spot.side else "C" if rails.inner else "D", []).append(channel_holes(rails, spot))
    return out


def cut_frame_holes(model, holes, name: str) -> None:
    for i, (points, axis) in enumerate(holes, start=1):
        _holes_through(model, points[0], axis, points, HOLE_DIA_IN, POST_HOLE_DEPTH_IN, f"{name}Post{i}")


# ------------------------------------------------------------------------------------------- the toe plates


def build_toe(model, rails: Rails, k: int, piece: str, name: str) -> None:
    """Platform ``k``'s toe plate (rail_sw.add_toe_plates): corner to corner, rolled on a rolled platform; on a
    narrow stair the ``piece`` of its wrap, "A" or "B" (a return) or "run"."""
    lines = rails.lines(k)
    y = lines.top + r.TOE_IN
    if rails.inner:
        r._inner_toe(model, lines, y, name)
    elif rails.wraps(k):
        wrap_piece(model, lines, y, r.TOE_SECTION, name, piece, lines.stringer_b + THICKNESS_IN + THK_IN)
    elif lines.rolled:
        r._rolled_band(model, lines.r_out - r.TOE_THK_IN, lines.r_out, lines.phi_a, lines.phi_b, lines.top, r.TOE_IN,
                       name)
    else:
        mid, outer = r._outer_run(lines)
        end = lines.r_out * math.sin((lines.phi_b - lines.phi_a) / 2.0)
        r._flat_bar(model, outer(0.0, -end, y), outer(0.0, end, y), _radial(mid), name, r.TOE_SECTION)


def wrap_piece(model, lines, y: float, section, name: str, piece: str, stop_r: float | None = None) -> None:
    """One piece of rail_sw._wrap: the return along side A or B from the outer corner to ``stop_r`` (the side post
    by default), mitered at the corner, or the run along the outer edge mitered at both corners."""
    heel_r = side_post_heel(lines) if stop_r is None else stop_r
    mid, _outer = r._outer_run(lines)
    sides = r._sides(lines)
    corners = {key: r._corner(lines, side, 0.0, 0.0, y) for key, side in sides.items()}
    if piece in sides:
        side = sides[piece]
        out = tuple(side.out_t * v for v in _travel(side.phi))
        r._flat_bar(model, r._shift(corners[piece], _radial(side.phi), r.OVERHANG_IN), side.world(heel_r, 0.0, y), out,
                    name, section)
        r._trim(model, set(), corners[piece], r._outer_miter(side, lines), f"{name}Outer")
        return
    if lines.rolled:
        thick, tall = -min(p[0] for p in section), -min(p[1] for p in section)
        radius = lines.r_out
        r._rolled_band(model, radius - thick, radius, r._plan_angle(corners["A"]) - r.OVERHANG_IN / radius,
                       r._plan_angle(corners["B"]) + r.OVERHANG_IN / radius, y - tall, tall, name)
    else:
        run = _travel(mid)
        r._flat_bar(model, r._shift(corners["A"], run, -r.OVERHANG_IN), r._shift(corners["B"], run, r.OVERHANG_IN),
                    _radial(mid), name, section)
    for key, side in sides.items():
        r._trim(model, set(), corners[key], tuple(-v for v in r._outer_miter(side, lines)), f"{name}Corner{key}")


# ---------------------------------------------------------------------------------------------- the top rail


def foot_cuts(rails: Rails):
    """The closed end at the foot (rail_sw.add_bottom_end): the top rail's miter (point, normal) and the midrail's
    square cut (point, normal), both as its trims take them."""
    flight = rails.flights[0]
    face_r = rails.face_r
    drop = flight.rail_top - flight.flight_mid
    end = flight.front(flight.first) - flight.step
    back = end + LEG_IN / face_r
    corner = _world(end, face_r, 0.0, flight.top(end))
    along = flight.tangent(end, face_r)
    normal = r._unit((along[0], along[1] + 1.0, along[2]))
    return ((corner, tuple(-v for v in normal)),
            (_world(back, face_r, 0.0, flight.top(back) - drop), tuple(-v for v in _travel(back))))


def build_top_rail(model, rails: Rails, k: int, foot: bool, name: str) -> None:
    """Flight ``k``'s top rail (add_top_rails' loop): the rolled L2x2 mitered at each platform it meets, and on the
    first flight, with the foot's closed end, mitered to it."""
    flights, face_r = rails.flights, rails.face_r
    flight = flights[k]
    start = flight.front(flight.first) - (flight.step if k == 0 else r.OVERHANG_IN / face_r)
    end = flight.front(flight.last) + (r.OVERHANG_IN / face_r if k < rails.landings else 0.0)
    r._helix_rail(model, flight, face_r, start, end, name, r.ANGLE_SECTION)
    if k > 0:
        joint, normal = r._joint(flights[k - 1], flight, face_r, rails.r_a, rails.pb, rails.post_in, "B")
        r._trim(model, set(), joint, tuple(-v for v in normal), f"{name}StartTrim")
    if k < rails.landings:
        joint, normal = r._joint(flight, None, face_r, rails.r_a, rails.pb, rails.post_in, "A")
        r._trim(model, set(), joint, normal, f"{name}EndTrim")
    if foot:
        point, normal = foot_cuts(rails)[0]
        r._trim(model, set(), point, normal, f"{name}FootMiter")


def _below_above(rails: Rails, k: int):
    flights = rails.flights
    return flights[k - 1], (flights[k] if k < len(flights) else None)


def build_end_piece(model, rails: Rails, k: int, side: str, profile: str, name: str) -> None:
    """The L2x2 the top rail's level piece is bolted to the post with at side ``side`` of platform ``k``
    (rail_sw._end_piece, or _corner_end_piece on a narrow stair), with its two bolt holes."""
    lines = rails.lines(k)
    grating = rails.tread_top(k)
    if rails.wraps(k):
        key_side = r._sides(lines)[side]
        heel_r = side_post_heel(lines)
        ys = (grating + rails.mid_top - r.BAR_IN, grating + rails.rail_top - THK_IN)
        _upright_angle(model, key_side.phi, heel_r, -1.0, key_side.out_t, ys, LEG_IN, profile, name)
        spot = PostSpot(k, side, True, key_side.phi, heel_r, 0.0, key_side.out_t, ys)
    else:
        post = _rail_post(rails, k, side)
        ys = (post.grating + rails.mid_top - r.BAR_IN, post.grating + rails.rail_top - TOP_GAP_IN)
        _upright_angle(model, post.mid, post.web_r, post.way, post.away, ys, LEG_IN, profile, name,
                       heel_t=post.heel_t)
        _cutback(model, post.mid, post.web_r, post.heel_t, post.away, ys[0], ys[1], name, inward=post.way)
        spot = PostSpot(k, side, False, post.mid, post.web_r, post.heel_t, post.away, ys, post.way)
    holes = end_holes(rails, spot)
    if holes is None:
        raise SolidWorksError(f"{name}: no post to bolt to.")
    points, axis = holes
    _holes_through(model, points[0], axis, points, HOLE_DIA_IN, END_HOLE_DEPTH_IN, name)


def build_level(model, rails: Rails, k: int, side: str, profile: str, name: str) -> None:
    """The top rail's level piece at side ``side`` of platform ``k``: from its miter with the flight's rail to the
    end piece (rail_sw._level_piece), or on a narrow stair along the flight's line to the platform's side."""
    below, above = _below_above(rails, k)
    lines = rails.lines(k)
    face_r = rails.face_r
    if not rails.wraps(k):
        post = _rail_post(rails, k, side)
        joint, normal = r._joint(below, above, face_r, rails.r_a, rails.pb, rails.post_in, side)
        r._level_piece(model, post, joint, normal, side, profile, name)
        return
    key_side = r._sides(lines)[side]
    top = rails.tread_top(k) + rails.rail_top
    joint, normal = r._joint(below, above, face_r, rails.r_a, rails.pb, r.PLATFORM_POST_IN, side)
    along = r._unit(tuple(key_side.world(face_r, 0.0, top)[i] - joint[i] for i in range(3)))
    out = r._outward(along, key_side.phi)
    start = r._shift(joint, out, -THK_IN)
    stop = r._meet(start, along, key_side.world(face_r, 0.0, top), _radial(key_side.phi))
    ends = (r._shift(start, along, -r.OVERHANG_IN), r._shift(stop, along, r.OVERHANG_IN))
    r._level_angle(model, *(ends if side == "A" else ends[::-1]), out, profile, name)
    r._trim(model, set(), joint, tuple(-v for v in normal) if side == "A" else normal, f"{name}Trim")
    r._trim(model, set(), stop, tuple(-key_side.out_t * v for v in _travel(key_side.phi)), f"{name}End")


def build_platform_rail(model, rails: Rails, k: int, piece: str, profile: str, name: str) -> None:
    """Platform ``k``'s own top rail between its posts (rolled on a rolled platform); on a narrow stair the
    ``piece`` of it, the return along side "A" or "B" from the side post or the "run" round the outer corners."""
    lines = rails.lines(k)
    top = rails.tread_top(k) + rails.rail_top
    if not rails.wraps(k):
        a, b = (_rail_post(rails, k, side) for side in ("A", "B"))
        way = rails.side
        if lines.rolled:
            heel = lines.r_out - THK_IN if way > 0 else lines.r_in + THK_IN
            r._rolled_angle(model, heel, a.mid + THK_IN / heel, b.mid - THK_IN / heel, top, profile, name, way)
        else:
            r._level_angle(model, a.world(-way * THK_IN, THK_IN, top), b.world(-way * THK_IN, -THK_IN, top),
                           tuple(way * v for v in _radial(a.mid)), profile, name)
        return
    heel_r = side_post_heel(lines)
    sides = r._sides(lines)
    met = rails.sides_met(k)
    corners = {key: r._corner(lines, side, -THK_IN, -side.out_t * THK_IN, top) for key, side in sides.items()}
    if piece in sides:
        side = sides[piece]
        # Clear of the end angle by the post's leg between them, where a flight meets.
        far = side.world(heel_r + (THK_IN if piece in met else 0.0), -side.out_t * THK_IN, top)
        out = tuple(side.out_t * v for v in _travel(side.phi))
        r._level_angle(model, r._shift(corners[piece], _radial(side.phi), r.OVERHANG_IN), far, out, profile, name)
        r._trim(model, set(), corners[piece], r._outer_miter(side, lines), f"{name}Outer")
        return
    if lines.rolled:
        heel = lines.r_out - THK_IN
        r._rolled_angle(model, heel, r._plan_angle(corners["A"]) - r.OVERHANG_IN / heel,
                        r._plan_angle(corners["B"]) + r.OVERHANG_IN / heel, top, profile, name)
    else:
        mid, _outer = r._outer_run(lines)
        run = _travel(mid)
        r._level_angle(model, r._shift(corners["A"], run, -r.OVERHANG_IN),
                       r._shift(corners["B"], run, r.OVERHANG_IN), _radial(mid), profile, name)
    for key, side in sides.items():
        r._trim(model, set(), corners[key], tuple(-v for v in r._outer_miter(side, lines)), f"{name}Corner{key}")


# ---------------------------------------------------------------------------------------------- the midrail


def build_midrail(model, rails: Rails, k: int, foot: bool, name: str) -> None:
    """Flight ``k``'s 2 x 1/4 midrail (add_mid_rails' loop), turned level where it climbs to the platform's
    midrail; on the first flight, with the foot's closed end, cut square against it."""
    flights, face_r = rails.flights, rails.face_r
    flight = flights[k]
    tops = (rails.mid_top, flight.flight_mid)
    climb = (rails.mid_top - flight.flight_mid) / flight.rise_per_rad
    start = flight.front(flight.first) - flight.step if k == 0 else (
        flight.front(flight.first) + climb - r.OVERHANG_IN / face_r
    )
    end = flight.front(flight.last) + (climb + r.OVERHANG_IN / face_r if k < rails.landings else 0.0)
    r._helix_rail(model, flight, face_r, start, end, name, r.BAR_SECTION, flight.rail_top - flight.flight_mid)
    if k > 0:
        joint, normal = r._joint(flights[k - 1], flight, face_r, rails.r_a, rails.pb, rails.post_in, "B", *tops)
        r._trim(model, set(), joint, tuple(-v for v in normal), f"{name}StartTrim")
    if k < rails.landings:
        joint, normal = r._joint(flight, None, face_r, rails.r_a, rails.pb, rails.post_in, "A", *tops)
        r._trim(model, set(), joint, normal, f"{name}EndTrim")
    if foot:
        point, normal = foot_cuts(rails)[1]
        r._trim(model, set(), point, normal, f"{name}FootTrim")


def build_mid_level(model, rails: Rails, k: int, side: str, name: str) -> None:
    """The midrail's level bar at side ``side`` of platform ``k`` (rail_sw._mid_level, _corner_mid_level)."""
    below, above = _below_above(rails, k)
    if rails.wraps(k):
        r._corner_mid_level(model, below, above, side, rails.face_r, rails.r_a, rails.pb, rails.mid_top, name)
    else:
        r._mid_level(model, below, above, side, rails.face_r, rails.r_a, rails.pb, rails.post_in, rails.mid_top, name)


def build_platform_mid(model, rails: Rails, k: int, piece: str, name: str) -> None:
    """Platform ``k``'s own midrail between its posts (rolled on a rolled platform); on a narrow stair the
    ``piece`` of its wrap, "A", "B" or "run"."""
    lines = rails.lines(k)
    top = rails.tread_top(k) + rails.mid_top
    if rails.wraps(k):
        wrap_piece(model, lines, top, r.BAR_SECTION, name, piece)
        return
    a, b = (_rail_post(rails, k, side) for side in ("A", "B"))
    way = rails.side
    if lines.rolled:
        radius = lines.r_out if way > 0 else lines.r_in
        r0, r1 = (radius - r.BAR_THK_IN, radius) if way > 0 else (radius, radius + r.BAR_THK_IN)
        r._rolled_band(model, r0, r1, a.mid + THK_IN / radius, b.mid - THK_IN / radius, top - r.BAR_IN, r.BAR_IN,
                       name)
    else:
        r._flat_bar(model, a.world(0.0, THK_IN, top), b.world(0.0, -THK_IN, top),
                    tuple(way * v for v in _radial(a.mid)), name)


# ------------------------------------------------------------------------------------------------- the foot


def build_foot(model, rails: Rails, profile: str, name: str) -> None:
    """The closed end at the foot (rail_sw.add_bottom_end): an L2x2 down from the top rail's low end to the
    midrail's bottom, mitered to the top rail."""
    flight = rails.flights[0]
    face_r = rails.face_r
    stretch = 1.0 / math.cos(math.atan(flight.rise_per_rad / face_r))
    drop = flight.rail_top - flight.flight_mid
    end = flight.front(flight.first) - flight.step
    back = end + LEG_IN / face_r
    (corner, normal), _mid = foot_cuts(rails)
    ys = (flight.top(back) - drop - r.BAR_IN * stretch, flight.top(end) + 0.5)
    _upright_angle(model, end, face_r - rails.side * THK_IN, rails.side, 1.0, ys, LEG_IN, profile, name)
    r._trim(model, set(), corner, tuple(-v for v in normal), f"{name}Miter")


# -------------------------------------------------------------------------------------------------- the jobs


def rail_jobs(job, rails: Rails, profile: str, common: dict, place, pairs=()) -> list:
    """The PartJobs (``job`` the PartJob class) of the outer handrail beyond the flight posts, each at its real place
    on the ground-0 stair and put there by ``place()``; ``common`` is what shapes them all. A flight's top rail and
    midrail spliced at ``pairs`` ((low post, high post) each) are a part for each piece."""
    home = (place(),)
    narrow = {k: rails.wraps(k) for k in range(1, rails.count + 1)}
    w, t = rails.word, rails.tag  # "inside " and "In" on the inside, nothing outside
    out = []

    def add(family, label, piece, build, **more):
        # The side is in the piece's name, so an inside piece never shares a file with an outside one.
        out.append(job(family, label, dict(common, piece=f"{w}{piece}", **more), build, home))

    for k in range(1, rails.count + 1):
        for spot in post_spots(rails, k):
            where = f"{'side post' if spot.side else 'post'} {spot.label}"
            add("Stair platform post", f"Platform {k} {w}{where}", f"post {k} {spot.label} {spot.side}",
                lambda model, spot=spot, k=k: build_post(model, rails, spot, profile,
                                                         f"ElitePlatform{k}Post{t}{spot.label}"),
                at=[spot.phi, spot.heel_r, spot.heel_t])
        for piece in ("A", "B", "run") if narrow[k] else ("run",):
            label = f"Platform {k} {w}toe plate" + (f" {piece}" if narrow[k] else "")
            add("Stair toe plate", label, f"toe {k} {piece}",
                lambda model, k=k, piece=piece: build_toe(model, rails, k, piece, f"ElitePlatform{k}Toe{t}{piece}"))
    flights = rails.flights
    foot = rails.top_rail and rails.mid_rail
    if rails.top_rail:
        for k in range(len(flights)):
            cuts = flight_cuts(rails, pairs, k)
            for i, suffix in _pieces(cuts):
                add("Stair top rail", f"Flight {k + 1} {w}top rail{suffix}", f"top rail {k + 1} {i}",
                    lambda model, k=k, cuts=cuts, i=i: build_spliced(
                        model, lambda m: build_top_rail(m, rails, k, foot and k == 0, f"EliteRail{t}F{k + 1}"),
                        lambda m, phi, nm: rail_gap(m, rails, k, phi, nm), cuts, i, f"EliteRail{t}F{k + 1}"))
        for k in range(1, rails.landings + 1):
            for side in rails.sides_met(k):
                add("Stair rail end", f"Platform {k} {w}rail end {side}", f"end {k} {side}",
                    lambda model, k=k, side=side: build_end_piece(model, rails, k, side, profile,
                                                                  f"ElitePlatform{k}Rail{t}End{side}"))
                add("Stair top rail", f"Platform {k} {w}top rail level {side}", f"level {k} {side}",
                    lambda model, k=k, side=side: build_level(model, rails, k, side, profile,
                                                              f"ElitePlatform{k}Rail{t}Level{side}"))
            for piece in ("A", "B", "run") if narrow[k] else ("run",):
                label = f"Platform {k} {w}top rail" + (f" {piece}" if narrow[k] else "")
                add("Stair top rail", label, f"platform rail {k} {piece}",
                    lambda model, k=k, piece=piece: build_platform_rail(model, rails, k, piece, profile,
                                                                        f"ElitePlatform{k}Rail{t}{piece}"))
    if rails.mid_rail:
        for k in range(len(flights)):
            cuts = flight_cuts(rails, pairs, k)
            for i, suffix in _pieces(cuts):
                add("Stair midrail", f"Flight {k + 1} {w}midrail{suffix}", f"midrail {k + 1} {i}",
                    lambda model, k=k, cuts=cuts, i=i: build_spliced(
                        model, lambda m: build_midrail(m, rails, k, foot and k == 0, f"EliteMid{t}F{k + 1}"),
                        lambda m, phi, nm: rail_gap(m, rails, k, phi, nm), cuts, i, f"EliteMid{t}F{k + 1}"))
        for k in range(1, rails.landings + 1):
            for side in rails.sides_met(k):
                add("Stair midrail", f"Platform {k} {w}midrail level {side}", f"mid level {k} {side}",
                    lambda model, k=k, side=side: build_mid_level(model, rails, k, side,
                                                                  f"ElitePlatform{k}Mid{t}Level{side}"))
            for piece in ("A", "B", "run") if narrow[k] else ("run",):
                label = f"Platform {k} {w}midrail" + (f" {piece}" if narrow[k] else "")
                add("Stair midrail", label, f"platform mid {k} {piece}",
                    lambda model, k=k, piece=piece: build_platform_mid(model, rails, k, piece,
                                                                       f"ElitePlatform{k}Mid{t}{piece}"))
    if foot:
        add("Stair rail end", f"{'Inside foot' if rails.inner else 'Foot'} end", "foot",
            lambda model: build_foot(model, rails, profile, f"EliteRail{t}BottomEnd"))
    return out


# ----------------------------------------------------------------------------------------------- the grab rail


def grab_pipes(rails: Rails, grab, posts) -> list:
    """Each flight's grab rail pipe as grab_sw.add_grab_rails runs it: (flight, pipe, low end, high end), or None
    for a flight with no post to hold it. Where the side's platforms have no rails (``Rails.railed``: STWE's inside
    pipe handrail) each runs from its first tread's front edge to its top tread's."""
    way, face_r = _post_side(rails.walk, rails.inner)
    radius = face_r - way * (g.BRACKET_OVERALL_IN - g.BRACKET_IN / 2.0)
    flights = rails.flights
    landings = rails.landings if rails.railed else 0
    out = []
    for k, flight in enumerate(flights):
        if not any((post.index - 1) // rails.per_flight == k for post in posts):
            out.append(None)
            continue
        low = flight.front(flight.first) if k == 0 or not rails.railed else g._miter_phi(
            flights[k - 1], flight, face_r, rails.r_a, rails.pb, rails.post_in, rails.mid_top, "B")
        high = g._miter_phi(flight, None, face_r, rails.r_a, rails.pb, rails.post_in, rails.mid_top, "A") if (
            k < landings) else flight.front(flight.last)
        pipe = g._Pipe(flight, radius, grab.top)
        lo, hi = pipe.end(low, grab.low, -1.0), pipe.end(high, grab.high, 1.0)
        if hi - lo < flight.step / 2.0:
            raise SolidWorksError(f"Flight {k + 1}: the grab rail end adjustments leave too little pipe.")
        out.append((k, pipe, lo, hi))
    return out


def bracket_posts(rails: Rails, grab, posts) -> list:
    """The flight posts the grab rail's PC #34 hangs from: those the pipe reaches past."""
    pipes = grab_pipes(rails, grab, posts)
    out = []
    for post in posts:
        held = pipes[min(len(pipes) - 1, (post.index - 1) // rails.per_flight)]
        if held is None:
            continue
        _k, pipe, lo, hi = held
        phi = post.phi + math.atan2(g.BRACKET_AT_IN, pipe.radius)
        reach = (g.BRACKET_IN / 2.0 + g.PIPE_OD_IN) / pipe.radius
        if lo + reach <= phi <= hi - reach:
            out.append(post)
    return out


def build_bracket(model, rails: Rails, grab, post, name: str) -> None:
    """The PC #34 under the pipe at ``post`` (grab_sw._bracket), on the pipe as every flight's runs: one piece, turned
    and raised with its post."""
    way, face_r = _post_side(rails.walk, rails.inner)
    radius = face_r - way * (g.BRACKET_OVERALL_IN - g.BRACKET_IN / 2.0)
    flight = rails.flights[(post.index - 1) // rails.per_flight]
    pipe = g._Pipe(flight, radius, grab.top)
    g._bracket(model, post, pipe, post.phi + math.atan2(g.BRACKET_AT_IN, radius), face_r, name, way)


def grab_jobs(job, rails: Rails, grab, posts, seat, common: dict, place, pairs=()) -> list:
    """The grab rail as PartJobs: each flight's pipe (a part for each piece where it is spliced at ``pairs``) and
    its two caps where they are, and the one PC #34 modelled at the flight posts' seat and put under every post the
    pipe reaches."""
    out = []
    w, t = rails.word, rails.tag
    params = dict(common, grab=[grab.top, grab.low, grab.high])
    for held in grab_pipes(rails, grab, posts):
        if held is None:
            continue
        k, pipe, lo, hi = held
        cuts = flight_cuts(rails, pairs, k)
        for i, suffix in _pieces(cuts):
            out.append(job("Stair grab rail", f"Flight {k + 1} {w}grab rail{suffix}",
                           dict(params, piece=f"{w}pipe {k + 1} {i}"),
                           lambda model, pipe=pipe, lo=lo, hi=hi, k=k, cuts=cuts, i=i: build_spliced(
                               model, lambda m: g._pipe(m, pipe, lo, hi, f"EliteGrab{t}F{k + 1}"),
                               lambda m, phi, nm: pipe_gap(m, rails, grab, k, phi, nm), cuts, i,
                               f"EliteGrab{t}F{k + 1}"),
                           (place(),)))
        for end, phi, way in (("low", lo, -1.0), ("high", hi, 1.0)):
            out.append(job("Stair grab rail cap", f"Flight {k + 1} {w}grab rail cap {end}",
                           dict(params, piece=f"{w}cap {k + 1} {end}"),
                           lambda model, pipe=pipe, phi=phi, way=way, k=k, end=end:
                           g._cap(model, pipe, phi, way, f"EliteGrab{t}F{k + 1}Cap{end.title()}"), (place(),)))
    held = bracket_posts(rails, grab, posts)
    if held:
        out.append(job("Stair grab rail bracket", f"{'Inside grab' if rails.inner else 'Grab'} rail bracket",
                       dict(params, piece=f"{w}bracket"),
                       lambda model: build_bracket(model, rails, grab, seat, f"EliteGrab{t}Bracket"),
                       tuple(place(p.phi - seat.phi, p.foot - seat.foot) for p in held)))
    return out


# --------------------------------------------------------------------------------------------------- the splices


def split_pairs(rails: Rails, posts, wanted) -> list:
    """The side's handrail splices as stair_sw._rail_splits pairs them: (low post, high post) for each wanted
    (side, pan of the post below the bay), "outer" or "inner" as ``rails`` is, whose bay has a post either side, in
    its flight."""
    mine = sorted(posts, key=lambda p: p.index)
    out = []
    for side, pan in wanted:
        if side != ("inner" if rails.inner else "outer"):
            continue
        low = next((p for p in mine if p.index == pan), None)
        high = next((p for p in mine if p.index > pan
                     and (p.index - 1) // rails.per_flight == (pan - 1) // rails.per_flight), None)
        if low is not None and high is not None:
            out.append((low, high))
    return out


def flight_cuts(rails: Rails, pairs, k: int) -> list[float]:
    """The splice angles along flight ``k`` (0 the lowest), lowest first: each in the middle of its bay."""
    return sorted(rs.split_angle(low, high) for low, high in pairs if (low.index - 1) // rails.per_flight == k)


def rail_gap(model, rails: Rails, k: int, phi: float, name: str) -> None:
    """The splice's 1/8 in gap through the top rail and midrail (rail_split_sw._connectors' sector cut)."""
    flight = rails.flights[k]
    _top, foot, _up = rs.connector_ends(flight, phi, rails.face_r)
    half = rs.GAP_IN / 2.0 / rails.face_r
    s._sector_cut(model, rs.gap_radii(rails.face_r, rails.side), phi - half, phi + half, foot - r.BAR_IN,
                  flight.top(phi) + 1.0, name)
    s._rebuild(model)


def _grab_pipe(rails: Rails, grab, k: int):
    way, face_r = _post_side(rails.walk, rails.inner)
    return g._Pipe(rails.flights[k], face_r - way * (g.BRACKET_OVERALL_IN - g.BRACKET_IN / 2.0), grab.top)


def pipe_gap(model, rails: Rails, grab, k: int, phi: float, name: str) -> None:
    """The splice's 1/4 in gap through the grab rail's pipe, square to it (rail_split_sw._pipe_joint)."""
    pipe = _grab_pipe(rails, grab, k)
    center, tangent = pipe.center(phi), pipe.tangent(phi)

    def draw(manager, to_sketch):
        cx, cy = to_sketch(center)
        if manager.CreateCircleByRadius(cx, cy, 0.0, (g.PIPE_OD_IN / 2.0 + 0.25) * 0.0254) is None:
            raise SolidWorksError(f"{name}: gap circle failed.")

    if s._cut_both_ways(model, g._sketch_through(model, center, tangent, name, draw), rs.PIPE_GAP_IN / 2.0) is None:
        raise SolidWorksError(f"{name}: the pipe gap was not cut.")
    s._rebuild(model)


def keep_piece(model, cuts: list[float], i: int, name: str) -> None:
    """Of the pieces the splice gaps cut a rail into, keep the ``i``-th up the stair and delete the rest, one at a
    time and counting the bodies (SolidWorks 2013's Delete Body reports nothing)."""
    def angle(body):
        x, _y, z = s._mass_point(body)
        return math.remainder(math.atan2(-x, z) - cuts[0], 2.0 * math.pi)

    bodies = s._bodies(model)
    if len(bodies) != len(cuts) + 1:
        raise SolidWorksError(f"{name}: the splices left {len(bodies)} pieces, not {len(cuts) + 1}.")
    keep = angle(sorted(bodies, key=angle)[i])
    while len(bodies) > 1:
        s._delete_body(model, max(bodies, key=lambda b: abs(angle(b) - keep)))
        left = s._bodies(model)
        if len(left) >= len(bodies):
            raise SolidWorksError(f"{name}: could not delete the rail's other pieces.")
        bodies = left


def _pieces(cuts: list[float]) -> list[tuple[int, str]]:
    """(index, label suffix) of the pieces a rail is spliced into: one, unnamed, with no splice."""
    if not cuts:
        return [(0, "")]
    return [(i, f" piece {i + 1} of {len(cuts) + 1}") for i in range(len(cuts) + 1)]


def build_spliced(model, build, gap, cuts: list[float], i: int, name: str) -> None:
    """``build`` the whole rail, cut each splice's gap (``gap(model, phi, name)``), keep piece ``i``."""
    build(model)
    for j, phi in enumerate(cuts, start=1):
        gap(model, phi, f"{name}Splice{j}")
    if cuts:
        keep_piece(model, cuts, i, name)


def build_connector(model, rails: Rails, k: int, phi: float, away: float, profile: str, name: str) -> None:
    """One of a splice's two L2x2 connectors (rail_split_sw._connectors): its flat leg on the rails' outside, its
    standing leg at the cut, both ends parallel to the rails, cut back 45 degrees, with the two bolt holes it shares
    with the other one."""
    face_r = rails.face_r
    flight = rails.flights[k]
    top, foot, up = rs.connector_ends(flight, phi, face_r)
    climb = LEG_IN * flight.rise_per_rad / face_r + 0.5
    ys = (foot - climb, top + climb)
    heel = rs.connector_heel(face_r, rails.side)
    _upright_angle(model, phi, heel, rails.side, away, ys, LEG_IN, profile, name)
    r._trim(model, set(), _world(phi, heel, 0.0, top), up, f"{name}Top")
    r._trim(model, set(), _world(phi, heel, 0.0, foot), tuple(-v for v in up), f"{name}Foot")
    rs.standing_cutback(model, s._bodies(model)[0], phi, heel, away, top, foot, name, rails.side)
    middle = (foot + top) / 2.0
    points = [_world(phi, heel + rails.side * HOLE_GAUGE_IN, -THK_IN, middle + d)
              for d in (-rs.BOLT_SPACE_IN / 2.0, rs.BOLT_SPACE_IN / 2.0)]
    _holes_through(model, points[0], tuple(-v for v in _travel(phi)), points, rs.BOLT_HOLE_IN, END_HOLE_DEPTH_IN,
                   f"{name}Holes")


def build_round_bar(model, rails: Rails, grab, k: int, phi: float, name: str) -> None:
    """The splice's 1-1/2 in round bar inside both pipe ends (rail_split_sw._round_bar)."""
    pipe = _grab_pipe(rails, grab, k)
    rs._round_bar(model, pipe.center(phi), pipe.tangent(phi), _radial(phi), name)


def splice_jobs(job, rails: Rails, pairs, profile: str, grab, common: dict, place) -> list:
    """Each of the side's splices' two connectors (with the top rail or midrail) and its round bar (with a pipe)."""
    out = []
    w, t = rails.word, rails.tag
    for low, high in pairs:
        k = (low.index - 1) // rails.per_flight
        phi = rs.split_angle(low, high)
        tag = f"{'Inside splice' if rails.inner else 'Splice'} at post {low.index}"
        if rails.top_rail or rails.mid_rail:
            for label, away in (("low", -1.0), ("high", 1.0)):
                out.append(job("Stair splice connector", f"{tag}, {label} connector",
                               dict(common, piece=f"{w}connector {low.index} {label}"),
                               lambda model, k=k, phi=phi, away=away, low=low, label=label:
                               build_connector(model, rails, k, phi, away, profile,
                                               f"EliteRailSplit{t}{low.index:02d}{label.title()}"), (place(),)))
        if grab is not None:
            out.append(job("Stair splice round bar", f"{tag}, round bar", dict(common, piece=f"{w}bar {low.index}"),
                           lambda model, k=k, phi=phi, low=low:
                           build_round_bar(model, rails, grab, k, phi, f"EliteRailSplit{t}{low.index:02d}PipeBar"),
                           (place(),)))
    return out
