"""Blind flanges and ring gaskets on the nozzle face."""

import pytest

from swauto.nozzle.gasket import DEFAULT_THICKNESS_IN, gasket
from swauto.nozzle.gui import blank_row, check_rows
from swauto.nozzle.place import place
from swauto.nozzle.shape import blind_loop, blind_seat_z, gasket_loop, outer_end_z, stations
from swauto.nozzle.spec import Nozzle
from swauto.tank.spec import Course, TankSpec


def _shell() -> TankSpec:
    return TankSpec(diameter_in=200.0, diameter_basis="od", courses=[Course(96.0, 0.5)])


def _nozzle(**more) -> Nozzle:
    return Nozzle("N1", 6, elevation_in=48.0, outside_projection_in=8.0, inside_projection_in=4.0, **more)


def test_ring_gasket_sizes_follow_b16_21():
    ring = gasket("6", 150, "CNAF")
    assert (ring.inner_diameter_in, ring.outer_diameter_in) == (6.62, 8.75)
    assert ring.thickness_in == DEFAULT_THICKNESS_IN == 0.125
    assert gasket("6", 300, "CNAF").outer_diameter_in == 9.88
    assert gasket("6", 150, "  spiral   wound 304 / graphite ").material == "spiral wound 304 / graphite"
    assert gasket("6", 150, "CNAF", 0.0625).thickness_in == 0.0625
    with pytest.raises(ValueError, match="material"):
        gasket("6", 150, "  ")


def test_a_gasket_needs_its_material_typed():
    with pytest.raises(ValueError, match="gasket material"):
        _nozzle(gasket=True)


def test_gasket_and_blind_stack_on_the_raised_face():
    placed = place(_nozzle(blind=True, gasket=True, gasket_material="CNAF"), _shell())
    face = stations(placed).face_z
    assert face == 8.0
    ring = gasket_loop(placed)
    assert ring == [(8.0, 3.31), (8.0, 4.375), (8.125, 4.375), (8.125, 3.31)]
    assert blind_seat_z(placed) == pytest.approx(8.125)
    blind = blind_loop(placed)
    # Raised face down on the gasket, then the full 11 in plate, 0.94 in thick like the flange.
    assert blind[0] == (8.125, 0.0)
    assert blind[1] == (8.125, 4.25)
    assert blind[3] == pytest.approx((8.185, 5.5))
    assert outer_end_z(placed) == pytest.approx(8.125 + 0.06 + 0.94)


def test_blind_alone_sits_on_the_flange_face():
    placed = place(_nozzle(blind=True), _shell())
    assert placed.gasket is None
    assert gasket_loop(placed) is None
    assert blind_seat_z(placed) == 8.0
    assert outer_end_z(placed) == pytest.approx(8.0 + 0.06 + 0.94)


def test_without_either_the_face_is_the_end():
    placed = place(_nozzle(), _shell())
    assert blind_loop(placed) is None
    assert outer_end_z(placed) == 8.0


def test_grid_rows_carry_blind_and_typed_gasket_material():
    base = dict(blank_row(), mark="N1", size="6", elevation="48", osp="8", isp="4")
    good = dict(base, blind=True, gasket=True, gasket_material="Garlock 3000", gasket_thk="0.0625")
    missing = dict(base, mark="N2", gasket=True)
    unticked = dict(base, mark="N3", gasket_material="ignored without the tick")
    checks = check_rows([good, missing, unticked], _shell())
    assert checks[0].ok
    assert checks[0].nozzle.blind and checks[0].nozzle.gasket
    assert checks[0].nozzle.gasket_material == "Garlock 3000"
    assert checks[0].nozzle.gasket_thickness_in == 0.0625
    assert "blind" in checks[0].message and "Garlock 3000 gasket" in checks[0].message
    assert not checks[1].ok and "gasket material" in checks[1].message
    assert checks[2].ok and not checks[2].nozzle.gasket
