"""The stair as an assembly of parts (the user, 2026-10-30: "partify the structural package so it performs faster
with builds").

Each fabricated piece is its own part, built in a small model of its own by the one-part build's builders, so a
feature costs what it costs in an empty part (in the one-part build every feature walks an ever longer feature tree).
Identical pieces share one file, modelled at their first place and put everywhere else by a turn about the tank
axis and a lift (``project.items.Placement``), as the one-part build copies them. A cut the one-part build makes
through two pieces at once is made in each piece's part from the same numbers.

So far: the treads, each flight's two stringers with every tread's and post's bolt holes, the outer flight posts,
and each platform's frame members.
"""

from __future__ import annotations

import contextlib
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from swauto.comutil import com_value
from swauto.errors import SolidWorksError
from swauto.parts import new_part, quiet
from swauto.project.items import Item, Placement
from swauto.stair import stair_sw as s
from swauto.stair.grab_sw import _sketch_through
from swauto.stair.platform_sw import (
    CHANNEL_IN,
    _arc_member,
    _frame,
    _radial,
    _radial_member,
    _signed_area,
    _sketch_on_face,
    _world,
    platform_lines,
    platform_profile,
)
from swauto.stair.post_sw import HOLE_GAUGE_IN, HOLE_UP_IN, THK_IN, Post, _holes, _post_side, _shaped_post
from swauto.stair.post_sw import post_layout as _post_layout
from swauto.stair.post_sw import post_profile
from swauto.stair.stringer import (
    BOLT_DIA_IN,
    BOLT_FROM_FRONT_IN,
    BOLT_SPACE_IN,
    BOLT_UP_IN,
    CLEAR_IN,
    THICKNESS_IN,
    TREAD_DEPTH_IN,
    StringerMock,
)
from swauto.stair.stringer_sw import _create_circle

_INCH = 0.0254
POST_HOLE_DIA_IN = 0.8125


@dataclass(frozen=True)
class PartJob:
    """One part file: how to model it in a new part, and every place it goes in the assembly."""

    file: str
    label: str
    build: Callable[[object], None] = field(compare=False)
    placements: tuple[Placement, ...] = ()


@dataclass(frozen=True)
class StairParts:
    """What the parts build makes, from the same inputs as the one-part build."""

    stair: StringerMock
    shell_od: float
    wall_in: float
    platforms: int = 0
    posts: tuple = ()  # the flight post treads, as for create_stair (one tuple for every flight, or one per flight)
    ground_in: float = 0.0
    turn: float = 0.0  # the whole stair turned about the tank axis, as turn_stair turns the one part
    top_platform: bool = False

    @property
    def where(self):
        return s.stair_places(self.stair, self.shell_od, self.platforms, self.ground_in)

    @property
    def r_b(self) -> float:
        """The outer stringer's walk face, where the posts are laid out."""
        layout = self.where.layout
        return layout.inner_face_in + layout.clear_in

    def flight_posts(self) -> list[Post]:
        where = self.where
        return _post_layout(where.places, where.per_flight, self.posts, self.r_b) if self.posts else []

    def platform_lines(self) -> list[tuple[int, object]]:
        """(k, plan lines) of each platform, 1 the lowest, the top one last: past flight k's top tread, lined up on
        the inner stringer, as stair_sw._platforms puts them."""
        where = self.where
        r_a = where.layout.inner_face_in
        out = []
        for k in range(1, self.platforms + 1 + (1 if self.top_platform else 0)):
            last = where.places[k * where.per_flight - 1]
            out.append((k, platform_lines(phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                                          spec=self.stair.platform(k - 1))))
        return out


def bolt_points(place, radius: float) -> list[tuple[float, float, float]]:
    """A tread's two bolt centres on ``radius`` (inches), where stair_sw._bolts puts them. The inner and outer
    ends' bolts are on the same two lines, square to both stringers."""
    half = TREAD_DEPTH_IN / 2.0
    radial = (-math.sin(place.phi), math.cos(place.phi))
    travel = (-math.cos(place.phi), -math.sin(place.phi))
    y = place.y0 + BOLT_UP_IN
    return [(radius * radial[0] + a * travel[0], y, radius * radial[1] + a * travel[1])
            for a in (half - BOLT_FROM_FRONT_IN, half - BOLT_FROM_FRONT_IN - BOLT_SPACE_IN)]


def post_hole_points(post: Post, r_b: float) -> list[tuple[float, float, float]]:
    """A flight post's two bolt centres on its leg's outer face, where post_sw._holes puts them."""
    way, face_r = _post_side(r_b, False)
    return [_world(post.phi, face_r + way * THK_IN, HOLE_GAUGE_IN, post.foot + up) for up in HOLE_UP_IN]


def _circles(points, dia_in: float, name: str):
    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, dia_in / 2.0 * _INCH) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    return draw


def platform_jobs(parts: StairParts, frame_file: str) -> list[PartJob]:
    """Each platform's frame members as parts. Rolled: the sides C and D, the end radials A and B, and one file for
    the radials between, the same piece turned about the tank axis. Straight: each of the mitered A, B, C and D
    (the frame is built whole and the other three bodies deleted, so SolidWorks' own miters stay), and each radial
    between on its own (their reach changes along the chords)."""
    out = []
    for k, lines in parts.platform_lines():
        base = lines.top - CHANNEL_IN
        tag, name = f"Stair Platform {k}", f"ElitePlatform{k}"
        home = (Placement(parts.turn),)
        if lines.rolled:
            out.append(PartJob(f"{tag} C.SLDPRT", f"Platform {k} side C",
                               lambda model, lines=lines, base=base, name=name:
                               _arc_member(model, lines.r_in, lines.phi_a, lines.phi_b, base, 0.0, frame_file,
                                           f"{name}C"), home))
            out.append(PartJob(f"{tag} D.SLDPRT", f"Platform {k} side D",
                               lambda model, lines=lines, base=base, name=name:
                               _arc_member(model, lines.r_out, lines.phi_a, lines.phi_b, base + CHANNEL_IN, math.pi,
                                           frame_file, f"{name}D"), home))
            ends = [lines.supports()[0], lines.supports()[-1]]
        else:
            for side in "ABCD":
                out.append(PartJob(f"{tag} {side}.SLDPRT", f"Platform {k} side {side}",
                                   lambda model, lines=lines, base=base, name=name, side=side:
                                   _straight_side(model, lines, base, frame_file, name, side), home))
            ends = []
        for label, angle, way in ends:
            out.append(PartJob(f"{tag} Radial {label}.SLDPRT", f"Platform {k} radial {label}",
                               lambda model, lines=lines, base=base, angle=angle, way=way, label=label, name=name:
                               _radial_member(model, lines, angle, way, base, frame_file, f"{name}{label}"), home))
        between = lines.supports()[1:-1]
        if between and lines.rolled:
            label, angle, way = between[0]
            out.append(PartJob(f"{tag} Radial.SLDPRT", f"Platform {k} radials between",
                               lambda model, lines=lines, base=base, angle=angle, way=way, name=name:
                               _radial_member(model, lines, angle, way, base, frame_file, f"{name}R"),
                               tuple(Placement(parts.turn + a - angle) for _label, a, _way in between)))
        else:
            for label, angle, way in between:
                out.append(PartJob(f"{tag} Radial {label}.SLDPRT", f"Platform {k} radial {label}",
                                   lambda model, lines=lines, base=base, angle=angle, way=way, label=label, name=name:
                                   _radial_member(model, lines, angle, way, base, frame_file, f"{name}{label}"),
                                   home))
    return out


def _straight_side(model, lines, base: float, frame_file: str, name: str, side: str) -> None:
    """One side of a straight platform's mitered frame: the whole frame, then the other three deleted."""
    outline = [s._plan_xy(r, a) for r, a in ((lines.r_in, lines.phi_a), (lines.r_out, lines.phi_a),
                                              (lines.r_out, lines.phi_b), (lines.r_in, lines.phi_b))]
    if _signed_area(outline) < 0:
        outline.reverse()  # counterclockwise in the sketch puts the flanges inside
    _frame(model, outline, base, frame_file, name)
    bodies = s._bodies(model)

    def where(body):
        x, _y, z = (v / _INCH for v in s._mass_point(body))
        return math.hypot(x, z), math.atan2(-x, z)  # radius, and angle as the stair counts it

    def closeness(body):
        r, a = where(body)
        middle = (lines.phi_a + lines.phi_b) / 2.0
        return {"A": abs(math.remainder(a - lines.phi_a, 2.0 * math.pi)),
                "B": abs(math.remainder(a - lines.phi_b, 2.0 * math.pi)),
                "C": r + abs(math.remainder(a - middle, 2.0 * math.pi)),
                "D": -r + abs(math.remainder(a - middle, 2.0 * math.pi))}[side]

    keep = min(bodies, key=closeness)
    for body in bodies:
        if body is not keep and not s._delete_body(model, body):
            raise SolidWorksError(f"{name}{side}: could not delete the frame's other sides.")


def jobs(parts: StairParts, post_file: str, frame_file: str = "") -> list[PartJob]:
    """Every part to build, in order: the tread, each flight's stringers, the flight post, the platforms' frames."""
    where = parts.where
    first = where.places[0]
    turned = parts.turn
    out = [PartJob(
        "Stair Tread.SLDPRT", "Tread", lambda model: _tread(model, parts),
        tuple(Placement(turned + p.phi - first.phi, (0.0, p.y0 - first.y0, 0.0)) for p in where.places),
    )]
    posts = parts.flight_posts()
    for k, at in enumerate(where.offsets):
        mine = [p for p in posts if (p.index - 1) // where.per_flight == k]
        treads = where.places[k * where.per_flight:(k + 1) * where.per_flight]
        out.append(PartJob(
            f"Stair Flight {k + 1} Stringers.SLDPRT", f"Flight {k + 1} stringers",
            lambda model, k=k, at=at, treads=treads, mine=mine: _stringers(model, parts, k, at, treads, mine),
            (Placement(turned),),
        ))
    if posts:
        head = posts[0]
        out.append(PartJob(
            "Stair Post.SLDPRT", "Flight post", lambda model: _post(model, parts, head, post_file),
            tuple(Placement(turned + p.phi - head.phi, (0.0, p.foot - head.foot, 0.0)) for p in posts),
        ))
    if frame_file or parts.platforms or parts.top_platform:
        out.extend(platform_jobs(parts, frame_file))
    return out


def _tread(model, parts: StairParts) -> None:
    """The pan at the first tread, its four bolt holes from one sketch on its inner end wall through both walls."""
    where = parts.where
    first = where.places[0]
    s._tread(model, where.layout, first, parts.wall_in)
    inner_edge = where.layout.inner_face_in + s.TREAD_CLEAR_IN
    face = s._end_wall_face(model, first, inner_edge)
    if face is None:
        raise SolidWorksError("Tread: its inner end wall was not found.")
    sketch = _sketch_on_face(model, face, "EliteTreadBolts", _circles(bolt_points(first, inner_edge), BOLT_DIA_IN,
                                                                       "Tread"))
    feature = s._cut_both_ways(model, sketch, where.layout.tread_in + 1.0)
    if feature is None:
        raise SolidWorksError("Tread: the bolt holes were not cut.")


def _stringers(model, parts: StairParts, k: int, at, treads, posts: Sequence[Post]) -> None:
    """Flight ``k``'s two stringers where the one-part build puts them, every tread's bolt holes through both (one
    sketch square to them on the bolt lines), and every post's two holes through the outer one."""
    where = parts.where
    layout = where.layout
    s.build_flight_stringers(model, where.flight, parts.shell_od, at=at, suffix=s.flight_suffix(k),
                             foot_holes=k > 0)
    middle = (layout.inner_face_in + layout.outside_radius_in) / 2.0
    reach = (layout.outside_radius_in - layout.inner_face_in) / 2.0 + 1.0
    for place in treads:
        points = bolt_points(place, middle)
        name = f"EliteBolt{place.index:02d}"
        sketch = _sketch_through(model, points[0], _radial(place.phi), name, _circles(points, BOLT_DIA_IN, name))
        if s._cut_both_ways(model, sketch, reach) is None:
            raise SolidWorksError(f"{name}: the bolt holes were not cut through the stringers.")
    for post in posts:
        points = post_hole_points(post, parts.r_b)
        name = f"ElitePost{post.index:02d}Holes"
        sketch = _sketch_through(model, points[0], _radial(post.phi), name,
                                 _circles(points, POST_HOLE_DIA_IN, name))
        if s._cut_both_ways(model, sketch, THK_IN + THICKNESS_IN + 0.1) is None:
            raise SolidWorksError(f"{name}: the post holes were not cut through the stringer.")


def _post(model, parts: StairParts, post: Post, profile: str) -> None:
    """The first flight post, shaped as post_sw shapes it, its two holes through its leg."""
    way, face_r = _post_side(parts.r_b, False)
    name = f"ElitePost{post.index:02d}"
    if _shaped_post(model, post, face_r, profile, name, way) is None:
        raise SolidWorksError(f"{name}: the post was not made.")
    _holes(model, post, face_r, parts.r_b, name, way)  # no stringer here, so its check of the stringer fails


def build(app, parts: StairParts, folder: Path, name: str, progress=None) -> str:
    """Model every part in a new part, save it in ``folder`` and close it, then place them all in
    ``folder``/``name``.SLDASM. Each part is closed before the assembly opens (an assembly must not hold a part being
    edited). Returns a note with the time each part took."""
    from swauto.project.build_sw import _save, check_name_clashes, sync_assembly
    from swauto.project.project import Project
    from swauto.tank.spec import TankSpec

    folder.mkdir(parents=True, exist_ok=True)
    timings = []
    frame_file = platform_profile(app) if parts.platforms or parts.top_platform else ""
    todo = jobs(parts, post_profile(app) if parts.posts else "", frame_file)
    project = Project(folder=folder, name=name, spec=TankSpec())
    items = [Item(job.file, "stair", job.label, {}, job.placements) for job in todo]
    # SolidWorks keeps one document per file name: a same-named part open from another folder would be overwritten.
    check_name_clashes(app, project, items)
    for job in todo:
        start = time.time()
        model = new_part(app)
        if model is None:
            raise SolidWorksError("Could not start a new part.")
        steps = []
        try:
            with quiet(app, model):  # graphics and feature tree off while it builds: several times faster
                job.build(model)
            steps.append(f"model {time.time() - start:.0f}")
            mark = time.time()
            with contextlib.suppress(Exception):
                s._hide_construction(model)
            _save(model, folder / job.file)
            steps.append(f"save {time.time() - mark:.0f}")
        finally:
            mark = time.time()
            app.CloseDoc(str(com_value(model.GetTitle)))
            steps.append(f"close {time.time() - mark:.0f}")
        timings.append(f"{job.label} {time.time() - start:.0f} s ({', '.join(steps)})")
        if progress is not None:
            progress(f"{job.label} built: {timings[-1]}")
    start = time.time()
    placed, _removed = sync_assembly(app, project, items)
    timings.append(f"assembly {time.time() - start:.0f} s")
    copies = sum(len(job.placements) for job in todo)
    return (f"{len(todo)} part files, {copies} pieces placed ({placed} new) in {name}.SLDASM. "
            f"Times: {', '.join(timings)}.")
