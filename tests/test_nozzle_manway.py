"""Round roof manways (2026-10-30): the pieces by size, as Elite's AMETank roof manways have them and API 650 Table
5-13 where it lists the size, placed on the roof as the lisp's MANWAY item."""

import math

import pytest

from swauto.nozzle.manway import (
    BOLT_HOLE_IN,
    GASKET_IN,
    HANDLE_RISE_IN,
    HANDLE_ROD_IN,
    PLATE_IN,
    ROOF_SIZES,
    handle_path,
    manway_loops,
    manway_stations,
    normalize_manway_size,
    roof_manway,
)
from swauto.nozzle.roof_gui import check_rows, nozzle_from_row, row_values
from swauto.nozzle.roof_place import place_on_roof
from swauto.nozzle.roof_spec import RoofNozzle
from swauto.tank.roof import RoofSpec

# Measured off the AMETank exports, 2026-10-30: (bolts, bolt circle, plate across, pad across, cover in3, flange in3,
# one handle in3), the plates with their 3/4 bolt holes.
AMETANK = {
    "20": (16, 23.5, 26.0, 42.0, 130.965, 52.425, 3.517),
    "24": (20, 27.5, 30.0, 46.0, 174.506, 61.408, 3.517),
    "30": (24, 33.5, 36.0, 60.0, 251.818, 75.104, 3.517),
    "36": (28, 39.5, 42.0, 72.0, 343.268, 88.799, 3.517),
    "42": (32, 45.5, 48.0, 84.0, 448.855, 102.495, 3.517),
}


def _ring_volume(outer: float, inner: float, thick: float, holes: int) -> float:
    return math.pi / 4.0 * (outer * outer - inner * inner) * thick - holes * math.pi / 4.0 * BOLT_HOLE_IN ** 2 * thick


def test_every_size_has_the_ametank_manways_pieces():
    assert ROOF_SIZES == tuple(AMETANK)
    for size, (bolts, circle, plate, pad, cover, flange, _handle) in AMETANK.items():
        manway = roof_manway(size)
        assert (manway.bolt_count, manway.bolt_circle_in, manway.plate_outer_in, manway.pad_outer_in) == (
            bolts, circle, plate, pad)
        assert manway.neck_outer_in == float(size) and manway.neck_inner_in == float(size) - 0.5
        assert manway.pad_inner_in == float(size) + 0.125
        assert _ring_volume(plate, 0.0, PLATE_IN, bolts) == pytest.approx(cover, abs=0.002)
        assert _ring_volume(plate, manway.neck_outer_in, PLATE_IN, bolts) == pytest.approx(flange, abs=0.002)


def test_the_api_650_sizes_agree():
    # Table 5-13: bolt circle, bolts, cover across and pad across for the 20 and 24 in roof manholes.
    for size, (circle, bolts, cover, pad) in {"20": (23.5, 16, 26.0, 42.0), "24": (27.5, 20, 30.0, 46.0)}.items():
        manway = roof_manway(size)
        assert (manway.bolt_circle_in, manway.bolt_count, manway.plate_outer_in, manway.pad_outer_in) == (
            circle, bolts, cover, pad)


def test_a_size_reads_as_typed_and_only_the_tables_sizes_are_manways():
    assert normalize_manway_size("24 in") == "24" and normalize_manway_size(36.0) == "36"
    with pytest.raises(ValueError, match="20, 24, 30, 36, 42"):
        normalize_manway_size("22")


def test_the_pieces_stack_up_the_axis():
    spot = manway_stations(12.0, 1.5)
    loops = dict(manway_loops(roof_manway("24"), spot))
    assert set(loops) == {"Neck", "Flange", "Gasket", "Cover"}
    assert min(z for z, _r in loops["Neck"]) == -1.5 and max(z for z, _r in loops["Neck"]) == 12.0
    assert {z for z, _r in loops["Flange"]} == {12.0 - PLATE_IN, 12.0}  # flush with the neck's end
    assert {z for z, _r in loops["Gasket"]} == {12.0, 12.0 + GASKET_IN}
    assert {z for z, _r in loops["Cover"]} == {12.0 + GASKET_IN, spot.top_z}
    assert min(r for _z, r in loops["Flange"]) == 12.0  # round the neck's outside


def test_a_handles_bar_runs_unbroken_from_the_cover_up_and_back():
    path = handle_path(10.0)
    ends = []
    for segment in path:
        start, end = (segment[1:3], segment[3:5]) if segment[0] == "line" else (segment[3:5], segment[5:7])
        ends.append((start, end))
    for (_s, end), (start, _e) in zip(ends, ends[1:], strict=False):
        assert end == pytest.approx(start)
    assert ends[0][0][1] == 10.0 and ends[-1][1][1] == 10.0  # both legs stand on the cover
    grip = next(s for s in path if s[0] == "line" and s[2] == s[4])
    assert grip[2] == 10.0 + HANDLE_RISE_IN
    length = sum(math.dist(s[1:3], s[3:5]) if s[0] == "line" else math.pi / 2.0 * math.dist(s[1:3], s[3:5])
                 for s in path)
    assert length * math.pi / 4.0 * HANDLE_ROD_IN ** 2 == pytest.approx(AMETANK["20"][6], abs=0.002)


def test_a_manway_is_placed_as_a_roof_nozzle_with_its_own_pad():
    roof = RoofSpec()
    nozzle = RoofNozzle(mark="M1", nps="30", manway=True, degree=45.0, radial_in=150.0, projection="osp",
                        projection_in=12.0, repad_mode="default")
    placed = place_on_roof(nozzle, roof)
    assert placed.manway == roof_manway("30")
    assert placed.pipe.outside_diameter_in == 30.0 and placed.flange.outside_diameter_in == 36.0
    assert (placed.repad.outer_diameter_in, placed.repad.inner_diameter_in) == (60.0, 30.125)
    assert placed.repad.thickness_in == roof.thickness_in
    assert placed.auto_isp and placed.inside_projection_in > roof.thickness_in  # through the roof, the lisp's AUTO
    with pytest.raises(ValueError, match="flange would go into its pad"):
        place_on_roof(RoofNozzle(mark="M1", nps="30", manway=True, radial_in=150.0, projection="osp",
                                 projection_in=1.0, repad_mode="default"), roof)
    with pytest.raises(ValueError, match="own cover and gasket"):
        RoofNozzle(mark="M1", nps="30", manway=True, radial_in=150.0, projection_in=12.0, blind=True)


def test_the_roof_table_takes_a_manway_row():
    row = {"mark": "M1", "service": "Manway", "item": "Manway", "size": "24", "degree": "90", "radial": "150",
           "offset": "", "mode": "Direct OSP", "value": "12", "isp": "", "inside_flange": "None",
           "repad": "Default", "pad_od": "", "pad_id": "", "pad_thk": "", "style": "Circular", "blind": False,
           "gasket": False, "gasket_material": "", "gasket_thk": "", "schedule": "STD"}
    nozzle = nozzle_from_row(row)
    assert nozzle.manway and nozzle.nps == "24"
    assert nozzle_from_row(row_values(nozzle)) == nozzle
    (check,) = check_rows([row], RoofSpec())
    assert check.ok and "24 in manway" in check.message and "20 x 5/8 bolts on 27.5" in check.message
    with pytest.raises(ValueError, match="untick Blind"):
        nozzle_from_row(dict(row, blind=True))
