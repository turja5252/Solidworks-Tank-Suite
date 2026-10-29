"""RNC's break flange: a flange at the inside end, turned to face into the tank, in the nozzle's own class."""

import pytest

from swauto.nozzle.gui import check_rows, row_values
from swauto.nozzle.place import place
from swauto.nozzle.shape import inside_flange_loop, inside_stations, slip_on_loops, stations, weld_neck_loop
from swauto.nozzle.spec import Nozzle, normalize_inside_flange
from swauto.project.items import nozzle_items
from swauto.tank.spec import Course, TankSpec


def _shell() -> TankSpec:
    return TankSpec(diameter_in=200.0, diameter_basis="od", courses=[Course(96.0, 0.5)])


def _nozzle(kind="wn", inside="wn", isp=12.0) -> Nozzle:
    return Nozzle("N1", "6", kind=kind, elevation_in=30.0, outside_projection_in=10.0, inside_projection_in=isp,
                  inside_flange=inside)


@pytest.mark.parametrize(
    ("typed", "kind"),
    [("", "none"), ("None", "none"), ("Weld neck", "wn"), ("Slip-on", "so"), ("CL150 RFSO", "so"),
     ("CL300 RFWN", "wn")],
)
def test_the_inside_flange_reads_the_grid_and_rncs_labels(typed, kind):
    assert normalize_inside_flange(typed) == kind


def test_isp_runs_from_the_shell_inside_to_the_inside_flanges_raised_face():
    placed = place(_nozzle(), _shell())
    inside = inside_stations(placed)
    assert inside.face_z == pytest.approx(-(12.0 + placed.wall_in))
    assert inside.face_z < inside.seat_z < inside.back_z < inside.hub_z < -placed.wall_in  # hub toward the shell
    assert placed.inside_flange.rating == 150 and placed.inside_flange.kind == "wn"


def test_a_weld_neck_inside_flange_takes_the_pipe_at_its_hub():
    placed = place(_nozzle(kind="wn", inside="wn"), _shell())
    spot, inside = stations(placed), inside_stations(placed)
    assert spot.pipe_z == pytest.approx(inside.hub_z)
    assert min(z for z, _r in weld_neck_loop(placed)) == pytest.approx(inside.hub_z)
    loop = inside_flange_loop(placed)
    assert min(z for z, _r in loop) == pytest.approx(inside.face_z)
    assert max(z for z, _r in loop) == pytest.approx(inside.hub_z)


def test_a_slip_on_inside_flange_takes_the_pipe_through_to_under_its_face():
    placed = place(_nozzle(kind="so", inside="so"), _shell())
    pipe, _flange = slip_on_loops(placed)
    inside = inside_stations(placed)
    assert min(z for z, _r in pipe) == pytest.approx(inside.seat_z)
    bore = min(r for _z, r in inside_flange_loop(placed))
    assert bore > placed.pipe.outside_diameter_in / 2.0


def test_an_isp_too_short_for_the_inside_flange_is_refused():
    with pytest.raises(ValueError, match="inside flange"):
        inside_stations(place(_nozzle(isp=1.0), _shell()))


def test_the_inside_flange_is_a_part_of_its_own_in_a_project():
    items = nozzle_items(_shell(), [_nozzle(inside="so")])
    inside = [item for item in items if item.file.startswith("Inside slip-on flange")]
    assert len(inside) == 1
    without = nozzle_items(_shell(), [_nozzle(inside="none")])
    assert not [item for item in without if item.file.startswith("Inside")]


def test_the_grid_round_trips_the_inside_flange():
    values = row_values(_nozzle(inside="so"))
    assert values["inside_flange"] == "Slip-on"
    (check,) = check_rows([values], _shell())
    assert check.ok and check.nozzle.inside_flange == "so"
    assert "inside SO flange" in check.message
