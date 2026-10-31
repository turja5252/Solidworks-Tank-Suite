"""The stair as 3D faces for the preview, without SolidWorks: shell, stringers, treads, platforms, splice plates,
posts, rails, inner clips and knee braces, from the same placing the build uses (``stair_places``,
``develop_both``, ``splitter.joints``, ``post_sw.post_layout``, ``landings``' pads and the attachment plan).

A face is a flat polygon of (x, y, z) inches in the build's frame (tank axis on Y, 0° toward +Z, the stair
climbing clockwise seen from above), with a colour; ``StairArrangement.world`` turns and mirrors it to where it
stands. Curved parts are cut into facets a few degrees wide. The shell behind is cut at its weld seams, and the
edges on a seam are marked to be drawn as welds. The renderer (``stretchout.view3d_gui``) sorts and shades them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.errors import SolidWorksError
from swauto.stair.attachments import (
    CLIP,
    INNER,
    KNEE,
    OUTER,
    PLATFORM_POST,
    POST,
    RAIL_SPLIT,
    Plan,
    Shell,
    build_angle,
)
from swauto.stair.development import develop_both
from swauto.stair.grab_sw import BRACKET_IN, BRACKET_OVERALL_IN, GRAB_TOP_IN, PIPE_OD_IN
from swauto.stair.landings import StairArrangement, clip_mark, knee_mark, platform_frame
from swauto.stair.platform_sw import CHANNEL_IN, GRATING_IN, _outer_back, platform_knees, platform_lines, shell_pads
from swauto.stair.post_sw import RAIL_TOP_IN, TOP_GAP_IN, _post_side, post_layout
from swauto.stair.rail_sw import BAR_IN, BAR_THK_IN, MID_TOP_IN, PLATFORM_MID_TOP_IN
from swauto.stair.splitter import joints
from swauto.stair.stair_sw import InnerRail, stair_places
from swauto.stair.stringer import CLEAR_IN, THICKNESS_IN, TREAD_DEPTH_IN

Point3 = tuple[float, float, float]
SHELL = "#c9c4b8"
STRINGER = "#7d8794"
TREAD = "#b8a27a"
PLATFORM = "#a39071"
SPLICE = "#0f766e"
POST_COLOR = "#f2c500"
RAIL = "#e0b400"
PIPE = "#a0522d"
CLIP_COLOR = "#2f6fdb"
KNEE_COLOR = "#ef7d00"
SPLIT_COLOR = "#c2185b"
_FACET = math.radians(3.0)
INNER_PIPE_TOP_IN = InnerRail.top


@dataclass(frozen=True)
class Face:
    points: tuple[Point3, ...]
    color: str
    label: str = ""
    welds: tuple[tuple[int, int], ...] = ()  # edges, as pairs of point indexes, on a shell weld seam


@dataclass(frozen=True)
class Rails:
    """The rails the Stairway tab asks for outside: top rail, midrail, grab rail. Inside it is the pipe alone."""

    top: bool = True
    mid: bool = True
    grab: bool = True


def scene(arrangement: StairArrangement, plan: Plan | None = None, shell_height_in: float | None = None,
          shell: Shell | None = None, rails: Rails = Rails()) -> list[Face]:
    """Every face of the stair, its shell band behind it (cut at the weld seams of ``shell``, the tank's) and, with
    ``plan``, its posts, ``rails``, clips, knee braces and rail splits. Placed where the arrangement stands:
    turned, and mirrored when it climbs counterclockwise."""
    stair = arrangement.stair
    where = stair_places(stair, stair.shell_od_in, arrangement.platforms, arrangement.ground_in)
    layout = where.layout
    r_a = layout.inner_face_in
    r_b = r_a + layout.clear_in
    faces: list[Face] = []

    top = shell_height_in or (shell.height_in if shell is not None else None) \
        or max(p.y1 for p in where.places) + RAIL_TOP_IN
    first = min(p.phi for p in where.places) - 0.25
    last = max(p.phi for p in where.places) + 0.35
    faces += _shell(arrangement, stair.shell_od_in, first, last, top, shell)

    inner_dev, outer_dev = develop_both(where.flight)
    for k, (turn, lift) in enumerate(where.offsets):
        for dev, r0, r1, side in ((inner_dev, r_a - THICKNESS_IN, r_a, "Inner"),
                                  (outer_dev, r_b, r_b + THICKNESS_IN, "Outer")):
            label = f"{side} stringer, flight {k + 1}"
            outline = [(turn + x / dev.radius_in, lift + y) for x, y in dev.outline]
            faces += _skin(outline, r1 if side == "Inner" else r0, STRINGER, label)
            if arrangement.splits is not None:
                for joint in joints(dev, stair.rise_in, where.per_flight, arrangement.splits):
                    plate = [(turn + x / dev.radius_in, lift + y) for x, y in joint.plate]
                    faces += _skin(plate, r0 - 0.2 if side == "Inner" else r1 + 0.2, SPLICE,
                                   f"{side} splice, flight {k + 1}, tread {joint.tread}")

    reach = TREAD_DEPTH_IN / 2.0
    for place in where.places:
        a0, a1 = place.phi - reach / r_a, place.phi + reach / r_a
        faces += _block(a0, a1, r_a, r_b, place.y0, place.y1, TREAD, f"Tread {place.index}")

    platforms = arrangement.platforms + (1 if arrangement.top_platform else 0)
    for k in range(1, platforms + 1):
        level = where.places[k * where.per_flight - 1]
        lines = platform_lines(phi=level.phi, tread_top=level.y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                               spec=stair.platform(k - 1))
        faces += _platform(lines, stair.shell_od_in, f"Platform after tread {level.index}")

    if plan is not None:
        faces += _attachments(arrangement, where, plan, r_a, r_b, rails)
    return [_placed(arrangement, face) for face in faces]


def _shell(arrangement: StairArrangement, r: float, a0: float, a1: float, top: float,
           shell: Shell | None) -> list[Face]:
    """The shell band behind the stair, from angle ``a0`` to ``a1`` and the floor to ``top``. With the tank's
    ``shell``, cut at its seams: each course seam, each plate seam in its course, and the floor weld is an edge
    marked as a weld."""
    plumb: list[tuple[float, float, float]] = []  # (angle, bottom, top) of each plate seam in the band
    levels = {0.0, top}
    if shell is not None:
        for seam in shell.seams:
            if not seam.vertical:
                if 0.0 < seam.y0 < top:
                    levels.add(seam.y0)
                continue
            angle = build_angle(arrangement, seam.x0, shell.girth_in, a0)
            for k in range(-1, math.ceil((a1 - a0) / (2.0 * math.pi)) + 2):  # each time the band passes it
                if a0 < angle + 2.0 * math.pi * k < a1:
                    plumb.append((angle + 2.0 * math.pi * k, seam.y0, min(seam.y1, top)))
    seams = {a for a, _y0, _y1 in plumb}
    cuts = sorted({a0, a1} | seams | {a for a in _steps(a0, a1) if all(abs(a - b) > _FACET / 4.0 for b in seams)})
    rows = sorted(levels)
    welded = set(rows[:-1]) if shell is not None else set()  # the floor and each course seam
    faces = []
    for p, q in zip(cuts, cuts[1:], strict=False):
        for y0, y1 in zip(rows, rows[1:], strict=False):
            edges = [(0, 1)] if y0 in welded else []
            if any(a == p and low - 1e-6 <= y0 and y1 <= high + 1e-6 for a, low, high in plumb):
                edges.append((3, 0))
            faces.append(Face((_xyz(r, p, y0), _xyz(r, q, y0), _xyz(r, q, y1), _xyz(r, p, y1)), SHELL, "Shell",
                              tuple(edges)))
    return faces


def _attachments(arrangement, where, plan: Plan, r_a: float, r_b: float, rails: Rails) -> list[Face]:
    faces: list[Face] = []
    per_flight = where.per_flight
    for spot in plan.spots:
        pan = spot.pan(per_flight)
        if spot.kind in (CLIP, KNEE):
            mark = (clip_mark if spot.kind == CLIP else knee_mark)(where, arrangement.platforms, pan)
            if isinstance(mark, str):
                continue
            angle, y = mark.center
            wide, tall = mark.size
            shell = arrangement.stair.shell_od_in
            half = wide / 2.0 / shell
            color = CLIP_COLOR if spot.kind == CLIP else KNEE_COLOR
            faces += _block(angle - half, angle + half, shell, shell + 0.6, y - tall / 2.0, y + tall / 2.0, color,
                            spot.label())
            place = where.places[pan - 1]
            if spot.kind == KNEE:  # the brace from under the tread down to its pad
                faces += _strut((r_b - 3.0, place.phi, place.y0 - 2.0), (shell + 0.6, angle, y), color, spot.label())
            else:
                faces += _strut((r_a - THICKNESS_IN, place.phi, place.y1 + 3.0), (shell + 0.6, angle, y), color,
                                spot.label())
    reach = TREAD_DEPTH_IN / 2.0 / r_a
    for side, r in ((OUTER, r_b + THICKNESS_IN + 1.0), (INNER, r_a - THICKNESS_IN - 1.0)):
        picks = tuple(tuple(sorted(s.tread for s in plan.of_kind(POST, side) if s.flight == k))
                      for k in range(len(where.offsets)))
        if not any(picks):
            continue
        walk = r_b if side == OUTER else r_a  # the stringer face the posts are laid out on
        top = RAIL_TOP_IN if side == OUTER else INNER_PIPE_TOP_IN
        posts = post_layout(where.places, per_flight, picks, walk, rail_top=top)
        for post in posts:
            faces += _block(post.phi, post.phi + 2.0 / r, r - 1.0, r + 1.0, post.foot, post.top(1.0), POST_COLOR,
                            f"{side.capitalize()} post at tread {post.index}")
        way, face_r = _post_side(walk, side == INNER)
        pipe_r = face_r - way * (BRACKET_OVERALL_IN - BRACKET_IN / 2.0)  # on its PC #34s, over the treads
        lines = {}
        for k in range(len(where.offsets)):
            mine = [p for p in posts if (p.index - 1) // per_flight == k]
            if not mine:
                continue

            def line(phi, post=mine[0]):  # the rail line along the flight: the top rail's top, or the pipe's
                return post.top((phi - post.phi) * walk) + TOP_GAP_IN

            lines[k] = line
            fronts = (where.places[k * per_flight].phi - reach, where.places[(k + 1) * per_flight - 1].phi - reach)
            name = f", flight {k + 1}"
            if side == INNER:
                faces += _tube(*fronts, pipe_r, PIPE_OD_IN, PIPE_OD_IN, line, PIPE, "Inside pipe" + name)
                continue
            ends = (mine[0].phi, mine[-1].phi + 2.0 / r)
            if rails.top and len(mine) > 1:
                faces += _tube(*ends, r, 2.0, 2.0, line, RAIL, "Outer top rail" + name)
            if rails.mid and len(mine) > 1:
                faces += _tube(*ends, r + 1.0 - BAR_THK_IN / 2.0, BAR_THK_IN, BAR_IN,
                               lambda phi, line=line: line(phi) - (RAIL_TOP_IN - MID_TOP_IN), RAIL,
                               "Outer midrail" + name)
            if rails.grab:
                faces += _tube(*fronts, pipe_r, PIPE_OD_IN, PIPE_OD_IN,
                               lambda phi, line=line: line(phi) - (RAIL_TOP_IN - GRAB_TOP_IN), PIPE, "Grab rail" + name)
        for spot in plan.of_kind(RAIL_SPLIT, side):
            low = next((p for p in posts if p.index == spot.pan(per_flight)), None)
            high = next((p for p in posts if p.index > spot.pan(per_flight)), None)
            if low is None or high is None or spot.flight not in lines:
                continue
            phi = (low.phi + high.phi) / 2.0
            y = lines[spot.flight](phi)
            at = r if side == OUTER else pipe_r
            faces += _block(phi - 1.0 / at, phi + 1.0 / at, at - 1.5, at + 1.5, y - 3.0, y + 1.0, SPLIT_COLOR,
                            spot.label())
    faces += _platform_handrails(arrangement, where, plan, rails)
    return faces


def _platform_handrails(arrangement, where, plan: Plan, rails: Rails) -> list[Face]:
    """Each platform's posts, on the outer side's back and on the inner side's tank face, and its top rail and
    midrail along the outer side from its first post to its last."""
    faces: list[Face] = []
    for k in range(arrangement.platforms + (1 if arrangement.top_platform else 0)):
        lines, _last = platform_frame(arrangement, where, k)
        floor = lines.top + GRATING_IN
        for side in (OUTER, INNER):
            posts = sorted(s.tread for s in plan.of_kind(PLATFORM_POST, side) if s.flight == k)
            angles = [lines.phi_a + t / lines.r_mid for t in posts]
            for t, angle in zip(posts, angles, strict=True):
                back = _side_back(lines, angle, side)
                r0, r1 = (back, back + 2.0) if side == OUTER else (back - 2.0, back)
                tall = RAIL_TOP_IN - TOP_GAP_IN if side == OUTER else INNER_PIPE_TOP_IN
                faces += _block(angle, angle + 2.0 / back, r0, r1, lines.top - CHANNEL_IN, floor + tall, POST_COLOR,
                                f"Platform {k + 1}: {side} post {t} in along it")
            if side != OUTER or len(angles) < 2:
                continue
            span = (angles[0], angles[-1] + 2.0 / lines.r_out)

            def out(angle, lines=lines):  # just outside the outer side's back, where the posts are
                return _side_back(lines, angle, OUTER) + 1.0

            if rails.top:
                faces += _tube(*span, out, 2.0, 2.0, lambda _a, floor=floor: floor + RAIL_TOP_IN, RAIL,
                               f"Platform {k + 1}: top rail")
            if rails.mid:
                faces += _tube(*span, out, BAR_THK_IN, BAR_IN, lambda _a, floor=floor: floor + PLATFORM_MID_TOP_IN,
                               RAIL, f"Platform {k + 1}: midrail")
    return faces


def _side_back(lines, angle: float, side: str) -> float:
    """A platform side's back on the radial line at ``angle``: the outer side's, or the inner one's (its tank
    face); on the arc when rolled, else on the straight line between the corners."""
    if side == OUTER:
        return _outer_back(lines, angle)
    if lines.rolled:
        return lines.r_in
    half = (lines.phi_b - lines.phi_a) / 2.0
    return lines.r_in * math.cos(half) / math.cos(angle - (lines.phi_a + half))


# ------------------------------------------------------------------------------------------------ shapes


def _xyz(r: float, phi: float, y: float) -> Point3:
    """The build's frame: 0° toward +Z, the stair climbing toward -X (clockwise seen from above)."""
    return (-r * math.sin(phi), y, r * math.cos(phi))


def _steps(a0: float, a1: float) -> list[float]:
    n = max(1, math.ceil(abs(a1 - a0) / _FACET))
    return [a0 + (a1 - a0) * i / n for i in range(n + 1)]


def _skin(outline: list[tuple[float, float]], r: float, color: str, label: str) -> list[Face]:
    """A flat outline of (angle, y) wrapped on the cylinder of radius ``r``, cut into vertical strips so each
    face is near flat: for each strip, the outline's top and bottom over it."""
    angles = [a for a, _y in outline]
    faces = []
    cuts = _steps(min(angles), max(angles))
    for p, q in zip(cuts, cuts[1:], strict=False):
        spans = [_span_at(outline, a) for a in (p, q)]
        if any(s is None for s in spans):
            continue
        (lo_p, hi_p), (lo_q, hi_q) = spans
        faces.append(Face((_xyz(r, p, lo_p), _xyz(r, q, lo_q), _xyz(r, q, hi_q), _xyz(r, p, hi_p)), color, label))
    return faces


def _span_at(outline, angle: float) -> tuple[float, float] | None:
    ys = []
    for (a0, y0), (a1, y1) in zip(outline, outline[1:] + outline[:1], strict=True):
        if (a0 - angle) * (a1 - angle) <= 0 and a0 != a1:
            ys.append(y0 + (angle - a0) / (a1 - a0) * (y1 - y0))
    return (min(ys), max(ys)) if len(ys) >= 2 else None


def _block(a0: float, a1: float, r0: float, r1: float, y0: float, y1: float, color: str, label: str) -> list[Face]:
    """A curved box: from angle ``a0`` to ``a1``, radius ``r0`` to ``r1``, height ``y0`` to ``y1``."""
    faces = []
    angles = _steps(a0, a1)
    for p, q in zip(angles, angles[1:], strict=False):
        for r in (r0, r1):
            faces.append(Face((_xyz(r, p, y0), _xyz(r, q, y0), _xyz(r, q, y1), _xyz(r, p, y1)), color, label))
        for y in (y0, y1):
            faces.append(Face((_xyz(r0, p, y), _xyz(r1, p, y), _xyz(r1, q, y), _xyz(r0, q, y)), color, label))
    for a in (a0, a1):
        faces.append(Face((_xyz(r0, a, y0), _xyz(r1, a, y0), _xyz(r1, a, y1), _xyz(r0, a, y1)), color, label))
    return faces


def _platform(lines, shell_r: float, label: str) -> list[Face]:
    """The deck between the platform's sides, rolled or straight, a dark rib along each radial between its ends,
    and at every support the knee brace under the outer side and the shell clip off the inner one, each to its pad
    on the shell."""
    y0, y1 = lines.top - lines.section.depth_in, lines.top
    if lines.rolled:
        faces = _block(lines.phi_a, lines.phi_b, lines.r_in, lines.r_out, y0, y1, PLATFORM, label)
    else:
        corners = [(lines.r_in, lines.phi_a), (lines.r_out, lines.phi_a), (lines.r_out, lines.phi_b),
                   (lines.r_in, lines.phi_b)]
        faces = _prism([_xyz(r, a, 0.0) for r, a in corners], y0, y1, PLATFORM, label)
    for angle in lines.radials:
        faces += _block(angle, angle + 1.5 / lines.r_mid, lines.r_in, lines.r_out, y1, y1 + 0.2, STRINGER,
                        f"{label}: radial channel")
    try:
        knees = platform_knees(lines, shell_r)
    except SolidWorksError:
        knees = []  # no room between the platform and the shell; the stretchout says so
    for name, frame, knee, _back in knees:
        (r1, k1), (r2, k2) = knee.top, knee.bottom
        faces += _strut((r1, frame.phi, k1), (r2, frame.phi, k2), KNEE_COLOR, f"{label}: knee brace {name}")
        faces += _block(frame.phi - 2.0 / shell_r, frame.phi + 2.0 / shell_r, shell_r, shell_r + 0.6, k2 - 3.0,
                        k2 + 3.0, KNEE_COLOR, f"{label}: knee brace pad {name}")
    half = lines.section.pad_tall_in / 2.0
    for name, angle, y in shell_pads(lines, shell_r):
        faces += _strut((lines.r_in, angle, y), (shell_r + 0.6, angle, y), CLIP_COLOR, f"{label}: shell clip {name}")
        faces += _block(angle - 2.0 / shell_r, angle + 2.0 / shell_r, shell_r, shell_r + 0.6, y - half, y + half,
                        CLIP_COLOR, f"{label}: shell clip pad {name}")
    return faces


def _prism(base: list[Point3], y0: float, y1: float, color: str, label: str) -> list[Face]:
    """A straight-sided slab on the plan outline ``base`` (points at any height), from ``y0`` up to ``y1``."""
    low = [(x, y0, z) for x, _y, z in base]
    high = [(x, y1, z) for x, _y, z in base]
    faces = [Face(tuple(low), color, label), Face(tuple(high), color, label)]
    for i in range(len(base)):
        j = (i + 1) % len(base)
        faces.append(Face((low[i], low[j], high[j], high[i]), color, label))
    return faces


def _strut(a: tuple[float, float, float], b: tuple[float, float, float], color: str, label: str) -> list[Face]:
    """A thin bar between two (r, angle, y) points."""
    p, q = _xyz(*a), _xyz(*b)
    up = (0.0, 0.75, 0.0)
    return [Face((p, q, tuple(q[i] + up[i] for i in range(3)), tuple(p[i] + up[i] for i in range(3))), color, label)]


def _tube(a0: float, a1: float, r, wide: float, tall: float, top_at, color: str, label: str) -> list[Face]:
    """A rail ``wide`` across the radius and ``tall``, centred on radius ``r`` (a number, or a function of the
    angle) from angle ``a0`` to ``a1``, its top at ``top_at(angle)`` inches up."""
    faces = []
    radius = r if callable(r) else (lambda _angle: r)
    angles = _steps(a0, a1)
    for p, q in zip(angles, angles[1:], strict=False):
        hp, hq = top_at(p), top_at(q)
        (p0, p1), (q0, q1) = ((radius(a) - wide / 2.0, radius(a) + wide / 2.0) for a in (p, q))
        for side_p, side_q in ((p0, q0), (p1, q1)):
            faces.append(Face((_xyz(side_p, p, hp - tall), _xyz(side_q, q, hq - tall), _xyz(side_q, q, hq),
                               _xyz(side_p, p, hp)), color, label))
        for drop in (0.0, tall):
            faces.append(Face((_xyz(p0, p, hp - drop), _xyz(p1, p, hp - drop), _xyz(q1, q, hq - drop),
                               _xyz(q0, q, hq - drop)), color, label))
    return faces


def _placed(arrangement: StairArrangement, face: Face) -> Face:
    """Turned to the stair's orientation, mirrored through the Right plane (x to -x) when counterclockwise."""
    turn = arrangement.turn
    c, s = math.cos(turn), math.sin(turn)
    points = []
    for x, y, z in face.points:
        if arrangement.ccw:
            x = -x
        # a plan angle grows clockwise from +Z, toward -X: turning by ``turn`` is the same rotation.
        points.append((x * c - z * s, y, x * s + z * c))
    return Face(tuple(points), face.color, face.label, face.welds)
