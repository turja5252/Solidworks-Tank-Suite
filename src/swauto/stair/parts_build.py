"""The stair as an assembly of parts (the user, 2026-10-30: "partify the structural package so it performs faster
with builds").

Each fabricated piece is its own part, built in a small model of its own by the one-part build's builders, so a
feature costs what it costs in an empty part (in the one-part build every feature walks an ever longer feature tree).
A cut the one-part build makes through two pieces at once is made in each piece's part from the same numbers.

Every piece is modelled at a seat its own shape fixes, never at "the first one": the stair on ground 0 and not
turned; the tread at pan 1; each stringer where the first flight's stands; a post at the first flight's second tread;
a platform's pieces as if it were the first platform (``platform_parts``); a stringer clip on a radial line at angle
0 with the channel top at 0; the shell pad at angle 0 and height 0. A placement then turns it about the tank axis and
lifts it (``project.items.Placement``), the stair's turn and ground included, so turning the stair, moving its ground
or its posts only moves components. Identical pieces (one family, one fingerprint) share a file, lettered like the
shell plates ("Stair tread A.SLDPRT", "Stair stringer inner B.SLDPRT"), in the stair's own assembly, Stair.SLDASM
(the user's choices, 2026-10-30).

So far: the treads, each stringer with every tread's and post's bolt holes, the outer flight posts, each platform's
frame members and supports, the stringer clips and the shell pads.
"""

from __future__ import annotations

import contextlib
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from swauto.comutil import com_value
from swauto.errors import SolidWorksError
from swauto.parts import new_part, quiet
from swauto.project.items import Item, Placement, _family, _names, fingerprint
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import angle_profile
from swauto.stair.grab_sw import _sketch_through
from swauto.stair.platform_parts import clip_jobs, clip_sides, pad_job, support_jobs, web_holes
from swauto.stair.platform_sw import (
    CHANNEL_IN,
    _arc_member,
    _frame,
    _radial,
    _radial_member,
    _signed_area,
    _sketch_on_face,
    _world,
    clip_profile,
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
    PlatformSpec,
    StringerMock,
)
from swauto.stair.stringer_sw import _create_circle

_INCH = 0.0254
POST_HOLE_DIA_IN = 0.8125
PARTS_VERSION = 1  # what the builders make: raise it when one of them changes, and every stair part is rebuilt
STAIR_PIECE = "stair piece"
ASSEMBLY = "Stair"
# Every C4 of a platform frame, sides and radials alike: a letter is a shape, never the platform's side A-D.
CHANNELS = "Stair platform channel"


@dataclass(frozen=True)
class PartJob:
    """One piece: its family (the lettered file name's stem), what shapes it at its seat, how to model it there in a
    new part, and every place it goes in the assembly."""

    family: str
    label: str
    params: Mapping[str, object] = field(compare=False)
    build: Callable[[object], None] = field(compare=False)
    placements: tuple[Placement, ...] = ()

    @property
    def fingerprint(self) -> str:
        return fingerprint(STAIR_PIECE, dict(self.params, family=self.family))


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
        """The stair on ground 0, not turned: every piece is modelled on it, and ``place`` stands it on its ground."""
        return s.stair_places(self.stair, self.shell_od, self.platforms, 0.0)

    def place(self, dphi: float = 0.0, dy: float = 0.0) -> Placement:
        """A piece modelled on the ground-0 stair, turned ``dphi`` about the tank axis and lifted ``dy``, then turned
        with the whole stair and stood on its ground."""
        return Placement(self.turn + dphi, (0.0, dy + self.ground_in, 0.0))

    def flight_move(self, k: int) -> tuple[float, float]:
        """How far flight ``k`` (0 the lowest) is turned and lifted from the first."""
        offsets = self.where.offsets
        return offsets[k][0] - offsets[0][0], offsets[k][1] - offsets[0][1]

    @property
    def r_b(self) -> float:
        """The outer stringer's walk face, where the posts are laid out."""
        layout = self.where.layout
        return layout.inner_face_in + layout.clear_in

    def flight_posts(self) -> list[Post]:
        where = self.where
        return _post_layout(where.places, where.per_flight, self.posts, self.r_b) if self.posts else []

    def platform_lines(self) -> list[tuple[int, object]]:
        """(k, plan lines) of each platform on the ground-0 stair, 1 the lowest, the top one last: past flight k's
        top tread, lined up on the inner stringer, as stair_sw._platforms puts them."""
        where = self.where
        r_a = where.layout.inner_face_in
        out = []
        for k in range(1, self.platforms + 1 + (1 if self.top_platform else 0)):
            last = where.places[k * where.per_flight - 1]
            out.append((k, platform_lines(phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                                          stringer_b=r_a + where.layout.clear_in, spec=self.stair.platform(k - 1))))
        return out

    def platform_seats(self) -> list[tuple[int, object, float, float]]:
        """(k, seat lines, turn, lift) of each platform: its lines (its own shape) as if it were the first platform,
        past the first flight, and how far the real one is turned and lifted from there."""
        where = self.where
        r_a = where.layout.inner_face_in
        last = where.places[where.per_flight - 1]
        out = []
        for k, _lines in self.platform_lines():
            dphi, dy = self.flight_move(k - 1)
            seat = platform_lines(phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                                  stringer_b=r_a + where.layout.clear_in, spec=self.stair.platform(k - 1))
            out.append((k, seat, dphi, dy))
        return out


def flight_params(where) -> dict:
    """What shapes a flight's pieces: the flight as laid out, less the platforms' shapes."""
    return asdict(replace(where.flight, platform_specs=()))


def shape_params(spec: PlatformSpec) -> dict:
    """What shapes a platform's pieces."""
    return {"length_in": spec.length_in, "width_in": spec.width_in, "rolled": spec.is_rolled,
            "radials": list(spec.radial_positions())}


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
    """Each platform's frame members, modelled on its seat. Rolled: the sides C and D, the end radials A and B, and
    one piece for the radials between, turned about the tank axis to each. Straight: each of the mitred A, B, C and
    D (the frame is built whole and the other three bodies deleted, so SolidWorks' own miters stay), and each radial
    between on its own (their reach changes along the chords). Where a flight meets an end (A, and B on a mid
    platform), its web has the stringer clips' rounds and slots."""
    out = []
    flight = flight_params(parts.where)
    for k, lines, dphi, dy in parts.platform_seats():
        base = lines.top - CHANNEL_IN
        name = f"ElitePlatform{k}"
        common = {"version": PARTS_VERSION, "flight": flight, "shape": shape_params(parts.stair.platform(k - 1))}
        home = (parts.place(dphi, dy),)
        clips = clip_sides(k, parts.platforms)
        if lines.rolled:
            out.append(PartJob(CHANNELS, f"Platform {k} side C", dict(common, piece="C"),
                               lambda model, lines=lines, base=base, name=name:
                               _arc_member(model, lines.r_in, lines.phi_a, lines.phi_b, base, 0.0, frame_file,
                                           f"{name}C"), home))
            out.append(PartJob(CHANNELS, f"Platform {k} side D", dict(common, piece="D"),
                               lambda model, lines=lines, base=base, name=name:
                               _arc_member(model, lines.r_out, lines.phi_a, lines.phi_b, base + CHANNEL_IN, math.pi,
                                           frame_file, f"{name}D"), home))
            ends = [lines.supports()[0], lines.supports()[-1]]
        else:
            for side in "ABCD":
                holes = (side,) if side in clips else ()
                out.append(PartJob(CHANNELS, f"Platform {k} side {side}",
                                   dict(common, piece=side, holes=bool(holes)),
                                   lambda model, lines=lines, base=base, name=name, side=side, holes=holes:
                                   _straight_side(model, lines, base, frame_file, name, side, holes), home))
            ends = []
        for label, angle, way in ends:
            holes = (label,) if label in clips else ()
            out.append(PartJob(CHANNELS, f"Platform {k} radial {label}",
                               dict(common, piece=label, holes=bool(holes)),
                               lambda model, lines=lines, base=base, angle=angle, way=way, label=label, name=name,
                               holes=holes: _end_radial(model, lines, angle, way, base, frame_file, name, label, holes),
                               home))
        between = lines.supports()[1:-1]
        if between and lines.rolled:
            label, angle, way = between[0]
            out.append(PartJob(CHANNELS, f"Platform {k} radials between", dict(common, piece="between"),
                               lambda model, lines=lines, base=base, angle=angle, way=way, name=name:
                               _radial_member(model, lines, angle, way, base, frame_file, f"{name}R"),
                               tuple(parts.place(dphi + a - angle, dy) for _label, a, _way in between)))
        else:
            for label, angle, way in between:
                out.append(PartJob(CHANNELS, f"Platform {k} radial {label}", dict(common, piece=label),
                                   lambda model, lines=lines, base=base, angle=angle, way=way, label=label, name=name:
                                   _radial_member(model, lines, angle, way, base, frame_file, f"{name}{label}"),
                                   home))
    return out


def _end_radial(model, lines, angle: float, way: float, base: float, frame_file: str, name: str, label: str,
                clips: tuple[str, ...]) -> None:
    """A rolled platform's end radial A or B, with the stringer clips' holes in its web if a flight meets it."""
    _radial_member(model, lines, angle, way, base, frame_file, f"{name}{label}")
    if label in clips:
        web_holes(model, lines, label, f"{name}Web{label}")


def _straight_side(model, lines, base: float, frame_file: str, name: str, side: str,
                   clips: tuple[str, ...] = ()) -> None:
    """One side of a straight platform's mitered frame: the whole frame, then the other three deleted; the ends A
    and B with the stringer clips' holes in the web where a flight meets them."""
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

    while len(bodies) > 1:
        # One at a time, the furthest first, from a fresh list: a delete leaves the other bodies' handles stale.
        # SolidWorks 2013 deletes the body but returns nothing, so the bodies are counted instead.
        s._delete_body(model, max(bodies, key=closeness))
        left = s._bodies(model)
        if len(left) >= len(bodies):
            raise SolidWorksError(f"{name}{side}: could not delete the frame's other sides.")
        bodies = left
    keep = bodies[0]
    with contextlib.suppress(Exception):
        keep.Name = f"{name}{side}"  # the web holes look for the frame's bodies by name
    if side in clips:
        web_holes(model, lines, side, f"{name}Web{side}")


def jobs(parts: StairParts, post_file: str = "", frame_file: str = "", knee_file: str = "",
         clip_file: str = "") -> list[PartJob]:
    """Every piece, in build order: the tread, each flight's two stringers, the flight post, the platforms' frames
    and supports, the stringer clips, and the shell pad."""
    where = parts.where
    first = where.places[0]
    flight = flight_params(where)
    out = [PartJob(
        "Stair tread", "Tread", {"version": PARTS_VERSION, "flight": flight, "wall_in": parts.wall_in},
        lambda model: _tread(model, parts),
        tuple(parts.place(p.phi - first.phi, p.y0 - first.y0) for p in where.places),
    )]
    posts = parts.flight_posts()
    for k in range(len(where.offsets)):
        dphi, dy = parts.flight_move(k)
        # This flight's posts where they would stand on the first flight, where its stringers are modelled.
        mine = tuple(replace(p, phi=p.phi - dphi, foot=p.foot - dy, cut=p.cut - dy) for p in posts
                     if (p.index - 1) // where.per_flight == k)
        for side, word in (("In", "inner"), ("Out", "outer")):
            holes = mine if side == "Out" else ()
            params = {"version": PARTS_VERSION, "flight": flight, "side": side, "foot_holes": k > 0,
                      "posts": [[p.phi, p.foot] for p in holes]}
            out.append(PartJob(
                f"Stair stringer {word}", f"Flight {k + 1} {word} stringer", params,
                lambda model, side=side, foot=k > 0, holes=holes: _stringer(model, parts, side, foot, holes),
                (parts.place(dphi, dy),),
            ))
    if posts:
        seat = _post_layout(where.places, where.per_flight, (2,), parts.r_b)[0]
        out.append(PartJob(
            "Stair post", "Flight post", {"version": PARTS_VERSION, "flight": flight, "r_b": parts.r_b},
            lambda model: _post(model, parts, seat, post_file),
            tuple(parts.place(p.phi - seat.phi, p.foot - seat.foot) for p in posts),
        ))
    if parts.platforms or parts.top_platform:
        platforms = parts.platform_lines()
        out.extend(platform_jobs(parts, frame_file))
        for k, seat_lines, dphi, dy in parts.platform_seats():
            common = {"version": PARTS_VERSION, "flight": flight,
                      "shape": shape_params(parts.stair.platform(k - 1))}
            out.extend(support_jobs(PartJob, k, seat_lines, parts.shell_od, knee_file, common,
                                    lambda turn, dphi=dphi, dy=dy: parts.place(dphi + turn, dy)))
        out.extend(clip_jobs(PartJob, platforms, parts.platforms, clip_file,
                             {"version": PARTS_VERSION, "flight": flight}, parts.place))
        out.append(pad_job(PartJob, platforms, parts.shell_od, {"version": PARTS_VERSION}, parts.place))
    return out


def stair_items(todo: Sequence[PartJob], built: Mapping[str, str] | None = None) -> list[Item]:
    """The pieces as project items: identical pieces (one family, one fingerprint) merged into one file placed at
    all their places, and each family's distinct pieces lettered as the shell plates are, a shape keeping the file
    that already holds it (``built``: file name to the fingerprint it was last built from)."""
    built = dict(built or {})
    families: dict[str, list[list]] = {}
    for job in todo:
        group = families.setdefault(job.family, [])
        same = next((entry for entry in group if entry[0].fingerprint == job.fingerprint), None)
        if same is None:
            group.append([job, list(job.placements), 1])
        else:
            same[1].extend(job.placements)
            same[2] += 1
    items = []
    for family, group in families.items():
        names = _names(family, [entry[0].fingerprint for entry in group], _family(family, built))
        for (job, placements, count), name in zip(group, names, strict=True):
            label = job.label if count == 1 else f"{job.label} and {count - 1} more alike"
            items.append(Item(name, STAIR_PIECE, label, dict(job.params, family=family), tuple(placements),
                              job.build))
    return items


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


def _stringer(model, parts: StairParts, side: str, foot_holes: bool, posts: Sequence[Post]) -> None:
    """One stringer (``side`` In or Out) where the first flight's stands, as every flight's is modelled: rolled and
    formed as the one-part build makes it, every tread's two bolt holes through it (a sketch square to it on the
    bolt lines), and each of ``posts``' two holes (on the outer one, the posts moved onto the first flight)."""
    where = parts.where
    layout = where.layout
    s.build_flight_stringers(model, where.flight, parts.shell_od, at=where.offsets[0], foot_holes=foot_holes,
                             sides=(side,))
    middle = (layout.inner_face_in + layout.outside_radius_in) / 2.0
    reach = (layout.outside_radius_in - layout.inner_face_in) / 2.0 + 1.0
    for place in where.places[:where.per_flight]:
        points = bolt_points(place, middle)
        name = f"EliteBolt{place.index:02d}"
        sketch = _sketch_through(model, points[0], _radial(place.phi), name, _circles(points, BOLT_DIA_IN, name))
        if s._cut_both_ways(model, sketch, reach) is None:
            raise SolidWorksError(f"{name}: the bolt holes were not cut through the stringer.")
    for post in posts:
        points = post_hole_points(post, parts.r_b)
        name = f"ElitePost{post.index:02d}Holes"
        sketch = _sketch_through(model, points[0], _radial(post.phi), name,
                                 _circles(points, POST_HOLE_DIA_IN, name))
        if s._cut_both_ways(model, sketch, THK_IN + THICKNESS_IN + 0.1) is None:
            raise SolidWorksError(f"{name}: the post holes were not cut through the stringer.")


def _post(model, parts: StairParts, post: Post, profile: str) -> None:
    """The post at its seat, shaped as post_sw shapes it, its two holes through its leg."""
    way, face_r = _post_side(parts.r_b, False)
    name = f"ElitePost{post.index:02d}"
    if _shaped_post(model, post, face_r, profile, name, way) is None:
        raise SolidWorksError(f"{name}: the post was not made.")
    _holes(model, post, face_r, parts.r_b, name, way)  # no stringer here, so its check of the stringer fails


def build(app, parts: StairParts, folder: Path, name: str = ASSEMBLY, progress=None,
          built: Mapping[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Model every piece in a new part, save it in ``folder`` and close it, then place them all in
    ``folder``/``name``.SLDASM. Each part is closed before the assembly opens (an assembly must not hold a part being
    edited). ``built`` is what the last build returned, so each shape keeps its file. Returns a note with the time
    each part took, and each file's fingerprint."""
    from swauto.project.build_sw import _properties, _save, check_name_clashes, sync_assembly
    from swauto.project.project import Project
    from swauto.tank.spec import TankSpec

    folder.mkdir(parents=True, exist_ok=True)
    timings = []
    frame_file = platform_profile(app) if parts.platforms or parts.top_platform else ""
    knee_file = angle_profile(app) if frame_file else ""
    clip_file = clip_profile(app) if frame_file else ""
    todo = stair_items(jobs(parts, post_profile(app) if parts.posts else "", frame_file, knee_file, clip_file),
                       built)
    project = Project(folder=folder, name=name, spec=TankSpec())
    # SolidWorks keeps one document per file name: a same-named part open from another folder would be overwritten.
    check_name_clashes(app, project, todo)
    for item in todo:
        start = time.time()
        model = new_part(app)
        if model is None:
            raise SolidWorksError("Could not start a new part.")
        steps = []
        try:
            with quiet(app, model):  # graphics and feature tree off while it builds: several times faster
                item.source(model)
            steps.append(f"model {time.time() - start:.0f}")
            mark = time.time()
            with contextlib.suppress(Exception):
                s._hide_construction(model)
            _properties(model, item)
            _save(model, folder / item.file)
            steps.append(f"save {time.time() - mark:.0f}")
        finally:
            mark = time.time()
            app.CloseDoc(str(com_value(model.GetTitle)))
            steps.append(f"close {time.time() - mark:.0f}")
        timings.append(f"{item.label} {time.time() - start:.0f} s ({', '.join(steps)})")
        if progress is not None:
            progress(f"{item.file} built ({item.label}): {timings[-1]}")
    start = time.time()
    placed, _removed = sync_assembly(app, project, todo)
    timings.append(f"assembly {time.time() - start:.0f} s")
    copies = sum(len(item.placements) for item in todo)
    note = (f"{len(todo)} part files, {copies} pieces placed ({placed} new) in {name}.SLDASM. "
            f"Times: {', '.join(timings)}.")
    return note, {item.file: item.fingerprint for item in todo}
