"""Nozzles in a project: pieces as parts, and the holes cut into the shell plates they cross."""

import math

import pytest

from swauto.nozzle.place import place
from swauto.nozzle.spec import Nozzle
from swauto.project.items import REPAD, TURNED, Placement, nozzle_items, shell_items
from swauto.tank.spec import Course, TankSpec


def _tank() -> TankSpec:
    # 750 in mid-wall: course 1 is five plates of 72 degrees, from +X toward +Z.
    return TankSpec(diameter_in=750.0, courses=[Course(96.0, 1.0), Course(96.0, 0.75)])


def _wn(mark: str, rotation: float, **more) -> Nozzle:
    base = {"elevation_in": 12.0, "outside_projection_in": 12.0, "inside_projection_in": 12.0}
    base.update(more)
    return Nozzle(mark, "6", rotation_deg=rotation, **base)


def _apply(placement: Placement, point):
    """Where SolidWorks puts a part's point: row vector times the rotation, then the move."""
    t = placement.transform()
    x, y, z = point
    return (
        x * t[0] + y * t[3] + z * t[6] + t[9] / 0.0254,
        x * t[1] + y * t[4] + z * t[7] + t[10] / 0.0254,
        x * t[2] + y * t[5] + z * t[8] + t[11] / 0.0254,
    )


def test_nozzles_on_one_plate_make_one_cut_variant_and_leave_the_rest_shared():
    nozzles = [_wn("N1", 30.0), _wn("N2", 45.0)]  # azimuths 120 and 135: the same 72-144 plate
    items = shell_items(_tank(), nozzles=nozzles)
    c1 = {item.file: item for item in items if item.file.startswith("Shell C1")}
    assert set(c1) == {"Shell C1 Plate A.SLDPRT", "Shell C1 Plate A P2 N1+N2.SLDPRT"}
    assert len(c1["Shell C1 Plate A.SLDPRT"].placements) == 4
    variant = c1["Shell C1 Plate A P2 N1+N2.SLDPRT"]
    assert [math.degrees(p.azimuth_rad) for p in variant.placements] == pytest.approx([72.0])
    assert [mark for _, mark in variant.source] == ["N1", "N2"]
    # On the plate's own frame the nozzles turn back by the plate's 72 degrees.
    assert [hole["rotation_deg"] for hole in variant.params["holes"]] == pytest.approx([-42.0, -27.0])


def test_a_hole_on_a_seam_cuts_both_plates():
    seam = _wn("N9", 54.0)  # azimuth 144: the seam between plates 2 and 3
    cut = {item.file: item for item in shell_items(_tank(), nozzles=[seam]) if "N9" in item.file}
    assert set(cut) == {"Shell C1 Plate A P2 N9.SLDPRT", "Shell C1 Plate A P3 N9.SLDPRT"}
    assert sorted(round(math.degrees(item.placements[0].azimuth_rad)) for item in cut.values()) == [72, 144]


def test_identical_pieces_share_a_file_whatever_the_projection():
    nozzles = [
        _wn("N1", 30.0, blind=True, gasket=True, gasket_material="CNAF"),
        _wn("N2", 200.0, outside_projection_in=20.0, blind=True, gasket=True, gasket_material="CNAF"),
    ]
    items = {item.file: item for item in nozzle_items(_tank(), nozzles)}
    necks = [name for name in items if name.startswith("Nozzle neck")]
    assert len(necks) == 2  # a longer neck is a different part
    assert len(items["Blind 6in Class 150 A.SLDPRT"].placements) == 2
    assert len(items["Gasket 6in Class 150 0.125in A.SLDPRT"].placements) == 2
    assert {item.kind for item in items.values()} == {TURNED}


def test_a_nozzle_piece_lands_on_its_nozzle_axis():
    nozzle = _wn("N1", 30.0, blind=True)
    placed = place(nozzle, _tank())
    blind = next(item for item in nozzle_items(_tank(), [nozzle]) if item.file.startswith("Blind"))
    placement = blind.placements[0]
    # The blind's part origin is its seat on the flange face; +Z runs out along the nozzle.
    seat = _apply(placement, (0.0, 0.0, 0.0))
    out = _apply(placement, (0.0, 0.0, 1.0))
    face = tuple(placed.shell_in[i] + placed.axis[i] * 12.0 for i in range(3))
    assert seat == pytest.approx(face)
    assert tuple(out[i] - seat[i] for i in range(3)) == pytest.approx(placed.axis)
    assert blind.params["loop"][0][0] == pytest.approx(0.0)


def test_slip_ons_and_repads_become_parts():
    slip_on = Nozzle("N3", "1-1/2", kind="so", elevation_in=40.0, outside_projection_in=8.0,
                     inside_projection_in=2.0)
    padded = _wn("N4", 270.0, repad_mode="default")
    files = {item.file: item.kind for item in nozzle_items(_tank(), [slip_on, padded])}
    assert files["Nozzle pipe 1.5in XS A.SLDPRT"] == TURNED
    assert files["Slip-on flange 1.5in Class 150 A.SLDPRT"] == TURNED
    assert [kind for name, kind in files.items() if name.startswith("Repad")] == [REPAD]
