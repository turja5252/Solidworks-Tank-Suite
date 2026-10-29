"""What a project builds: one part per fabricated piece, identical pieces sharing a file.

An item is one part file: what shapes it (``params``, fingerprinted), every place it
sits in the assembly, and (``source``) what its builder needs that the fingerprint
already covers. A placement turns a part about the vertical and moves it.

Shell plates are modeled at their real height, turned to azimuth 0; a plate a nozzle
cuts through is its own file with the hole in it. Nozzle pieces are modeled about
their own axis, +Z out of the tank: neck and pipe from the shell outside, a flange,
gasket or blind from its own seat, so identical ones share a file whatever the
projection.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import string
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace

from swauto.cleanout.spec import PIECES, Cleanout
from swauto.nozzle.place import place
from swauto.nozzle.shape import (
    blind_loop,
    blind_seat_z,
    gasket_loop,
    inside_flange_loop,
    inside_stations,
    outer_end_z,
    slip_on_loops,
    stations,
    weld_neck_loop,
)
from swauto.nozzle.spec import Nozzle
from swauto.tank.plates import CourseOneGap, PlateSector, layout_plates
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import TankSpec

_INCH = 0.0254
_TURN = 2.0 * math.pi
SHELL_PLATE = "shell plate"
TURNED = "turned piece"
REPAD = "repad"
FTCO_PIECE = "ftco piece"
_HOLE_CLEAR_IN = 0.25  # a plate counts as cut if the hole comes this close to it


@dataclass(frozen=True)
class Placement:
    """One instance in the assembly: turned ``azimuth_rad`` about the vertical, then moved to ``at_in``.

    The turn takes +X to (cos a, 0, sin a): on the shell, 0 is +X and it runs toward +Z.
    """

    azimuth_rad: float
    at_in: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def transform(self) -> list[float]:
        """A SolidWorks MathTransform array: 9 rotation, 3 translation (m), scale, 3 unused.

        SolidWorks applies it as row vector times rotation.
        """
        c, s = math.cos(self.azimuth_rad), math.sin(self.azimuth_rad)
        x, y, z = (value * _INCH for value in self.at_in)
        return [c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c, x, y, z, 1.0, 0.0, 0.0, 0.0]


@dataclass(frozen=True)
class Item:
    """One part file and every place it goes."""

    file: str
    kind: str
    label: str
    params: Mapping[str, object] = field(compare=False)
    placements: tuple[Placement, ...] = ()
    source: object = field(default=None, compare=False)  # builder input the fingerprint already covers

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.kind, self.params)


def fingerprint(kind: str, params: Mapping[str, object]) -> str:
    """What the part is built from, rounded so float noise does not count as a change."""
    text = json.dumps({"kind": kind, "params": _rounded(params)}, sort_keys=True)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _rounded(value):
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    if isinstance(value, Mapping):
        return {str(key): _rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return str(value)


# ------------------------------------------------------------------ shell plates


def shell_items(
    spec: TankSpec,
    gaps: Sequence[CourseOneGap] = (),
    built: Mapping[str, str] | None = None,
    nozzles: Sequence[Nozzle] = (),
) -> list[Item]:
    """The shell plates as parts: one file per distinct plate in a course, placed at each of its seams.

    ``built`` maps file name to the fingerprint it was last built from. A plate keeps the
    file that already holds its exact shape; a changed plate takes over a file of its course
    that no longer fits, so it is rebuilt in place instead of a new file appearing. A plate a
    nozzle cuts is a file of its own, named for its shape, its place in the course and the
    nozzles, like "Shell C1 Plate A P2 N1+N2".
    """
    built = dict(built or {})
    plates = layout_plates(spec, gaps)
    holes = _plate_holes(spec, plates, nozzles)
    courses: dict[int, list[tuple[dict, list]]] = {}
    for index, plate in enumerate(plates):
        params = {
            "course": plate.course_no,
            "inner_r_m": plate.inner_r_m,
            "outer_r_m": plate.outer_r_m,
            "z_bot_m": plate.z_bot_m,
            "height_m": plate.height_m,
            "sweep_rad": plate.sweep_rad,
            "length_in": plate.length_in,
        }
        course = courses.setdefault(plate.course_no, [])
        key = fingerprint(SHELL_PLATE, params)
        group = next((g for g in course if fingerprint(SHELL_PLATE, g[0]) == key), None)
        if group is None:
            group = (params, [])
            course.append(group)
        group[1].append((Placement(azimuth_rad=plate.start_rad), holes.get(index, []), plate.plate_no))

    items: list[Item] = []
    for course_no, groups in sorted(courses.items()):
        prefix = f"Shell C{course_no} Plate"
        mine = _family(prefix, built)
        names = _names(prefix, [fingerprint(SHELL_PLATE, params) for params, _ in groups], mine)
        for (params, instances), name in zip(groups, names, strict=True):
            inner, outer = params["inner_r_m"] / _INCH, params["outer_r_m"] / _INCH
            letter = name[len(prefix) + 1:-len(".SLDPRT")]
            label = (f"Shell C{course_no} plate {letter}: {outer - inner:g} x {params['height_m'] / _INCH:g} "
                     f"x {params['length_in']:.3f} in")
            plain = tuple(placement for placement, cuts, _ in instances if not cuts)
            if plain:
                items.append(Item(file=name, kind=SHELL_PLATE, label=label, params=params, placements=plain))
            for placement, cuts, plate_no in instances:
                if not cuts:
                    continue
                marks = "+".join(mark for _, _, mark in cuts)
                # The plate's number keeps two cut plates of one shape apart (a hole on a seam cuts both).
                items.append(Item(
                    file=f"{prefix} {letter} P{plate_no} {_file_safe(marks)}.SLDPRT",
                    kind=SHELL_PLATE,
                    label=f"{label}, cut for {marks}",
                    params=dict(params, holes=[descriptor for descriptor, _, _ in cuts]),
                    placements=(placement,),
                    source=[(local, mark) for _, local, mark in cuts],
                ))
    return items


def _plate_holes(spec: TankSpec, plates: Sequence[PlateSector], nozzles: Sequence[Nozzle]) -> dict[int, list]:
    """For each plate a nozzle's hole crosses: (what shapes the hole, the nozzle placed on the plate's
    own frame, mark), in mark order. A hole on a seam cuts both plates."""
    found: dict[int, list] = {}
    for nozzle in sorted(nozzles, key=lambda n: n.mark):
        placed = place(nozzle, spec)
        x, y, z = placed.shell_in
        azimuth = math.atan2(z, x) % _TURN
        reach = placed.pipe.outside_diameter_in / 2.0 + _HOLE_CLEAR_IN
        for index, plate in enumerate(plates):
            bottom = plate.z_bot_m / _INCH
            if y + reach <= bottom or y - reach >= bottom + plate.height_m / _INCH:
                continue
            half = math.asin(min(1.0, reach / (plate.outer_r_m / _INCH)))
            along = (azimuth - plate.start_rad) % _TURN
            if not (along < plate.sweep_rad + half or along > _TURN - half):
                continue
            # The plate part runs from azimuth 0, so the nozzle turns back by the plate's start.
            turned = (nozzle.rotation_deg - math.degrees(plate.start_rad) + 180.0) % 360.0 - 180.0
            local = replace(nozzle, rotation_deg=turned)
            descriptor = {"mark": nozzle.mark, "nps": nozzle.nps, "elevation_in": nozzle.elevation_in,
                          "rotation_deg": turned, "offset_in": nozzle.offset_in}
            found.setdefault(index, []).append((descriptor, place(local, spec), nozzle.mark))
    return found


# ------------------------------------------------------------------ nozzles


def nozzle_items(spec: TankSpec, nozzles: Sequence[Nozzle], built: Mapping[str, str] | None = None) -> list[Item]:
    """Each nozzle's pieces as parts: neck (or pipe and slip-on flange), repad, gasket, blind.

    Pieces of the same shape share one file, placed at every nozzle that uses it.
    """
    built = dict(built or {})
    families: dict[str, list] = {}  # file prefix -> [[params, kind, label, placements, source]]
    for nozzle in nozzles:
        placed = place(nozzle, spec)
        for prefix, kind, label, params, shift, source in _pieces(placed):
            at = tuple(placed.shell_in[i] + placed.axis[i] * shift for i in range(3))
            placement = Placement(azimuth_rad=math.radians(nozzle.rotation_deg), at_in=at)
            family = families.setdefault(prefix, [])
            key = fingerprint(kind, params)
            entry = next((e for e in family if fingerprint(e[1], e[0]) == key), None)
            if entry is None:
                family.append([params, kind, label, [placement], source])
            else:
                entry[3].append(placement)
    items: list[Item] = []
    for prefix, family in families.items():
        names = _names(prefix, [fingerprint(kind, params) for params, kind, *_ in family], _family(prefix, built))
        for (params, kind, label, placements, source), name in zip(family, names, strict=True):
            items.append(Item(file=name, kind=kind, label=label, params=params,
                              placements=tuple(placements), source=source))
    return items


def _pieces(placed):
    """(file prefix, kind, label, params, how far out along the axis its origin sits, builder source)."""
    nozzle = placed.nozzle
    spot = stations(placed)
    fitting = placed.flange
    size = f"{_nps_text(nozzle.nps)}in Class {nozzle.rating}"
    named = f"{nozzle.nps} in Class {nozzle.rating}"
    bolts = [fitting.bolt_circle_in, fitting.bolt_count, fitting.bolt_hole_diameter_in]
    if nozzle.kind == "wn":
        yield (f"Nozzle neck {size} {nozzle.schedule}", TURNED, f"{named} weld neck, {nozzle.schedule}",
               {"loop": weld_neck_loop(placed), "bolts": bolts + [spot.back_z, spot.face_z - spot.back_z]}, 0.0, None)
    else:
        pipe_loop, flange_loop = slip_on_loops(placed)
        face = spot.face_z
        yield (f"Nozzle pipe {_nps_text(nozzle.nps)}in {nozzle.schedule}", TURNED,
               f"{nozzle.nps} in {nozzle.schedule} pipe", {"loop": pipe_loop}, 0.0, None)
        yield (f"Slip-on flange {size}", TURNED, f"{named} slip-on flange",
               {"loop": _shifted(flange_loop, face), "bolts": bolts + [spot.back_z - face, face - spot.back_z]},
               face, None)
    ring = gasket_loop(placed)
    if ring is not None:
        gasket = placed.gasket
        yield (f"Gasket {size} {gasket.thickness_in:g}in", TURNED, f"{named} RF ring gasket, {gasket.label}",
               {"loop": _shifted(ring, spot.face_z), "material": gasket.material}, spot.face_z, None)
    blind = blind_loop(placed)
    if blind is not None:
        seat, top = blind_seat_z(placed), outer_end_z(placed)
        yield (f"Blind {size}", TURNED, f"{named} RF blind flange, ASME B16.5",
               {"loop": _shifted(blind, seat), "bolts": bolts + [top - seat, top - seat]}, seat, None)
    inside = inside_flange_loop(placed)
    if inside is not None:
        # Modeled from its raised face, which looks into the tank; its hub runs back toward the shell.
        spots = inside_stations(placed)
        shape = "weld neck" if placed.inside_flange.kind == "wn" else "slip-on"
        yield (f"Inside {shape} flange {size}", TURNED, f"{named} {shape} flange at the inside end",
               {"loop": _shifted(inside, spots.face_z), "bolts": bolts + [0.0, spots.back_z - spots.face_z]},
               spots.face_z, None)
    if placed.repad is not None:
        pad = placed.repad
        params = {
            "r_out": placed.outside_radius_in,
            "pipe_od": placed.pipe.outside_diameter_in,
            # A tombstone pad runs down to the tank bottom.
            "drop": nozzle.elevation_in if pad.style == "tombstone" else 0.0,
            **asdict(pad),
        }
        yield (f"Repad {pad.outer_diameter_in:g}in {pad.thickness_in:g}in", REPAD,
               f"{pad.style} repad {pad.outer_diameter_in:g} OD x {pad.thickness_in:g} for {named}",
               params, 0.0, (placed, nozzle.mark))


def _shifted(loop, z0: float) -> list[tuple[float, float]]:
    return [(z - z0, r) for z, r in loop]


def _nps_text(nps: str) -> str:
    """A pipe size fit for a file name: 1-1/2 is 1.5, 3/4 is 0.75."""
    text = str(nps)
    if "/" not in text:
        return text
    whole, fraction = text.split("-", 1) if "-" in text else ("0", text)
    top, bottom = fraction.split("/")
    return f"{float(whole) + float(top) / float(bottom):g}"


# ------------------------------------------------------------------ flush-type cleanouts

# What shapes each FTCO piece, besides its size and where course 1 is.
_FTCO_SHAPE = {
    "Insert": ("insert_thk_in", "neck_wall_in"),
    "Repad": ("insert_thk_in", "repad_thk_in", "neck_wall_in"),
    "Neck": ("insert_thk_in", "repad_thk_in", "neck_wall_in"),
    "Flange": ("insert_thk_in", "repad_thk_in", "neck_wall_in", "flange_thk_in"),
    "Gasket": ("insert_thk_in", "repad_thk_in", "neck_wall_in", "flange_thk_in", "gasket_thk_in",
               "gasket_material"),
    "Cover": ("insert_thk_in", "repad_thk_in", "flange_thk_in", "gasket_thk_in", "cover_thk_in"),
    "BottomPlate": ("insert_thk_in", "repad_thk_in", "baseplate_thk_in", "annular_width_in", "chime_in",
                    "annular_thk_in"),
}
_FTCO_WORDS = {"Insert": "insert plate", "Repad": "repad", "Neck": "neck", "Flange": "flange",
               "Gasket": "gasket", "Cover": "cover", "BottomPlate": "bottom plate"}


def ftco_items(spec: TankSpec, cleanouts: Sequence[Cleanout], built: Mapping[str, str] | None = None) -> list[Item]:
    """Each FTCO's pieces as parts, modeled facing +Z and turned to the FTCO's orientation.

    Identical FTCOs share every file. The shell plates leave course 1 open for the insert
    plates (``swauto.cleanout.layout.course_one_gaps``).
    """
    if not cleanouts:
        return []
    built = dict(built or {})
    course = spec.active_courses()[0]
    outer_m, inner_m = course_radii_m(spec, course)
    r_mid = (outer_m + inner_m) / 2.0 / _INCH
    shell_outside = outer_m / _INCH
    families: dict[str, list] = {}
    for cleanout in cleanouts:
        upright = replace(cleanout, orientation_deg=0.0, anchor="none")
        size = cleanout.size.replace("'", "").replace('"', "")  # 12'-5" -> 12-5
        placement = Placement(azimuth_rad=math.radians(cleanout.orientation_deg))
        for piece in PIECES:
            params = {"piece": piece, "size": cleanout.size, "r_mid": r_mid, "height": course.height_in,
                      **{name: getattr(cleanout, name) for name in _FTCO_SHAPE[piece]}}
            if piece == "BottomPlate":
                params["shell_outside"] = shell_outside
            label = f"FTCO {cleanout.size} {_FTCO_WORDS[piece]}"
            if piece == "Gasket" and cleanout.gasket_material:
                label += f", {cleanout.gasket_material}, {cleanout.gasket_thk_in:g} in"
            prefix = f"FTCO {size} {_FTCO_WORDS[piece]}"
            family = families.setdefault(prefix, [])
            key = fingerprint(FTCO_PIECE, params)
            entry = next((e for e in family if fingerprint(FTCO_PIECE, e[0]) == key), None)
            if entry is None:
                family.append([params, label, [placement], (upright, piece, r_mid, course.height_in, shell_outside)])
            else:
                entry[2].append(placement)
    items: list[Item] = []
    for prefix, family in families.items():
        names = _names(prefix, [fingerprint(FTCO_PIECE, params) for params, *_ in family], _family(prefix, built))
        for (params, label, placements, source), name in zip(family, names, strict=True):
            items.append(Item(file=name, kind=FTCO_PIECE, label=label, params=params,
                              placements=tuple(placements), source=source))
    return items


# ------------------------------------------------------------------ file names


def _family(prefix: str, built: Mapping[str, str]) -> dict[str, str]:
    """This prefix's lettered files from earlier builds: "<prefix> A.SLDPRT", "<prefix> B.SLDPRT"..."""
    pattern = re.compile(rf"^{re.escape(prefix)} [A-Z]+\.SLDPRT$")
    return {name: fp for name, fp in built.items() if pattern.match(name)}


def _names(prefix: str, wanted: list[str], mine: dict[str, str]) -> list[str]:
    """Lettered file names for the distinct shapes in a family, in order.

    First, a shape a file already holds keeps that file. Then changed shapes take the family's
    other files in letter order, and only then are new letters used.
    """
    names: list[str | None] = [None] * len(wanted)
    free = sorted(mine)
    for index, fp in enumerate(wanted):
        match = next((name for name in free if mine[name] == fp), None)
        if match is not None:
            names[index] = match
            free.remove(match)
    taken = {name for name in names if name}
    letters = (f"{prefix} {letter}.SLDPRT" for letter in _letters())
    for index, name in enumerate(names):
        if name is None:
            if free:
                names[index] = free.pop(0)
            else:
                names[index] = next(name for name in letters if name not in mine and name not in taken)
            taken.add(names[index])
    return [name for name in names if name is not None]


def _letters():
    yield from string.ascii_uppercase
    for first in string.ascii_uppercase:
        for second in string.ascii_uppercase:
            yield first + second


def _file_safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in " -_.+()" else "-" for ch in text)
