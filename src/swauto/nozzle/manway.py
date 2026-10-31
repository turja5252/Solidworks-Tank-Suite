"""Round roof manways, by size: the neck, its bolting flange, the gasket, the cover with its two handles, and the
pad on the roof. Inches.

The user asked for them on 2026-10-30, rebuilt our own way as the FTCO was. The lisp's Roof Nozzle Inserter lists
the item (MANWAY) with its sizes and places it as a roof nozzle: the neck plumb, its outside the size, AUTO ISP. The
pieces are Elite's AMETank roof manways (20, 24, 30, 36 and 42 in, measured 2026-10-30), which match API 650 Table
5-13 where it has the size (20 and 24): flange, gasket and cover 6 in over the size, the bolt circle 3-1/2 in over
it, 5/8 bolts in 3/4 holes straddling the radial line, a 1/4 neck, flange and cover, a 1/16 gasket, and a pad 42 or
46 in across, twice the size from 30 up, its hole 1/8 over the neck. The handles are 5/8 round bar on the cover.

Here they are turned (z, radius) loops in the nozzle's frame (``roof_place``): z up the plumb axis, 0 on the roof's
outside at the centerline. The flange's top, where the neck ends too, is the flange face the OSP measures to.
"""

from __future__ import annotations

from dataclasses import dataclass

ROOF_SIZES = ("20", "24", "30", "36", "42")
NECK_WALL_IN = 0.25
PLATE_IN = 0.25  # the bolting flange and the cover
GASKET_IN = 0.0625
OVER_SIZE_IN = 6.0  # the flange, the gasket and the cover across, over the size
BOLT_CIRCLE_OVER_IN = 3.5
BOLT_IN = 0.625
BOLT_HOLE_IN = 0.75
PAD_HOLE_OVER_IN = 0.125  # the pad's hole across, over the neck's outside
HANDLE_ROD_IN = 0.625  # round bar
HANDLE_SPAN_IN = 6.0  # leg to leg, centre to centre
HANDLE_RISE_IN = 3.0  # the grip's centre over the cover
HANDLE_BEND_IN = 0.625  # each bend's radius, to the bar's centre
HANDLE_OFF_IN = 9.0  # each handle's middle off the axis, the two either side of it along the radial line

# size: bolts, pad across
_ROOF = {"20": (16, 42.0), "24": (20, 46.0), "30": (24, 60.0), "36": (28, 72.0), "42": (32, 84.0)}


def normalize_manway_size(value: object) -> str:
    """A roof manway's size as the table keys it: 20, 24, 30, 36 or 42. Takes "24 in" and 24.0 too."""
    text = str(value if value is not None else "").strip().lower().replace('"', "").replace("in", "").strip()
    try:
        size = f"{float(text):g}"
    except ValueError:
        size = text
    if size not in _ROOF:
        raise ValueError(f"A roof manway is {', '.join(ROOF_SIZES)} in, not {value!s}.")
    return size


@dataclass(frozen=True)
class RoofManway:
    """One size's pieces."""

    size: str
    bolt_count: int
    pad_outer_in: float

    @property
    def neck_outer_in(self) -> float:
        return float(self.size)

    @property
    def neck_inner_in(self) -> float:
        return self.neck_outer_in - 2.0 * NECK_WALL_IN

    @property
    def plate_outer_in(self) -> float:
        """The flange's, the gasket's and the cover's outside."""
        return self.neck_outer_in + OVER_SIZE_IN

    @property
    def bolt_circle_in(self) -> float:
        return self.neck_outer_in + BOLT_CIRCLE_OVER_IN

    @property
    def pad_inner_in(self) -> float:
        return self.neck_outer_in + PAD_HOLE_OVER_IN


def roof_manway(size: object) -> RoofManway:
    key = normalize_manway_size(size)
    bolts, pad = _ROOF[key]
    return RoofManway(key, bolts, pad)


@dataclass(frozen=True)
class ManwayStations:
    """Heights along the axis, z = 0 on the roof's outside at the centerline."""

    end_z: float  # the neck's inside end
    back_z: float  # the bolting flange's underside
    face_z: float  # its top, the neck ending with it: the flange face
    seat_z: float  # the gasket's top, under the cover
    top_z: float  # the cover's top, where the handles stand


def manway_stations(outside_projection_in: float, inside_projection_in: float) -> ManwayStations:
    face = outside_projection_in
    seat = face + GASKET_IN
    return ManwayStations(end_z=-inside_projection_in, back_z=face - PLATE_IN, face_z=face, seat_z=seat,
                          top_z=seat + PLATE_IN)


def manway_loops(manway: RoofManway, spot: ManwayStations) -> list[tuple[str, list[tuple[float, float]]]]:
    """(piece, closed (z, radius) loop) of each turned piece: the neck from its inside end to the flange face; the
    bolting flange, a ring round the neck's top welded to it, flush with its end; the gasket, full face from the
    neck's bore to the plates' edge; the cover on it."""
    bore, neck, plate = manway.neck_inner_in / 2.0, manway.neck_outer_in / 2.0, manway.plate_outer_in / 2.0
    return [
        ("Neck", [(spot.end_z, bore), (spot.end_z, neck), (spot.face_z, neck), (spot.face_z, bore)]),
        ("Flange", [(spot.back_z, neck), (spot.back_z, plate), (spot.face_z, plate), (spot.face_z, neck)]),
        ("Gasket", [(spot.face_z, bore), (spot.face_z, plate), (spot.seat_z, plate), (spot.seat_z, bore)]),
        ("Cover", [(spot.seat_z, 0.0), (spot.seat_z, plate), (spot.top_z, plate), (spot.top_z, 0.0)]),
    ]


def handle_path(top_z: float) -> list[tuple[str, tuple[float, ...]]]:
    """One handle's centreline in its own plane, as (u along the grip from its middle, z up the axis): a leg up
    from the cover, a quarter bend, the grip, a bend, the other leg down. Each segment ("line", u0, z0, u1, z1) or
    ("arc", centre u, centre z, u0, z0, u1, z1)."""
    half, bend = HANDLE_SPAN_IN / 2.0, HANDLE_BEND_IN
    grip = top_z + HANDLE_RISE_IN
    knee = grip - bend
    return [
        ("line", -half, top_z, -half, knee),
        ("arc", -half + bend, knee, -half, knee, -half + bend, grip),
        ("line", -half + bend, grip, half - bend, grip),
        ("arc", half - bend, knee, half - bend, grip, half, knee),
        ("line", half, knee, half, top_z),
    ]
