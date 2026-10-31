"""A shell nozzle's repad lies on the shell, radial or offset (2026-10-30: an offset nozzle's band was turned about
the line behind its own centreline instead of the tank axis, so its pad stood off the shell on one side)."""

import math

import pytest

from swauto.nozzle.nozzle_sw import _band_angle, _rise, _sag, _shell_axis, _shell_z
from swauto.nozzle.place import place
from swauto.nozzle.spec import Nozzle
from swauto.tank.spec import Course, TankSpec

SPEC = TankSpec(diameter_in=240.0, diameter_basis="mw", stack="mw", courses=[Course(96.0, 0.5)])


def _placed(**more):
    return place(Nozzle("N1", "6", elevation_in=30.0, outside_projection_in=8.0, repad_mode="default", **more), SPEC)


def test_a_radial_nozzles_repad_is_turned_about_the_tank_axis_right_behind_it():
    placed = _placed()
    radius, outer = placed.outside_radius_in, placed.repad.outer_diameter_in / 2.0
    assert _shell_axis(placed) == pytest.approx((0.0, -radius))
    assert _sag(placed) == pytest.approx(radius - math.sqrt(radius ** 2 - outer ** 2))
    assert _rise(placed) == 0.0
    assert _band_angle(placed) == pytest.approx(math.asin((outer + 0.5) / radius))


def test_an_offset_nozzles_repad_lies_on_the_shell_off_to_its_side():
    placed = _placed(offset_in=40.0, rotation_deg=90.0)
    radius, outer = placed.outside_radius_in, placed.repad.outer_diameter_in / 2.0
    ax, az = _shell_axis(placed)
    assert (ax, az) == pytest.approx((40.0, -math.sqrt(radius ** 2 - 40.0 ** 2)))
    # The nozzle's shell point is on the shell, and so is the shell under every part of the pad.
    assert _shell_z(placed, 0.0) == pytest.approx(0.0, abs=1e-9)
    for x in (-outer, -1.0, 2.0, outer):
        assert math.hypot(x - ax, _shell_z(placed, x) - az) == pytest.approx(radius)
    # The shell comes out toward the flange on the offset's side and falls back on the other.
    assert _rise(placed) == pytest.approx(_shell_z(placed, outer)) and _rise(placed) > 0.0
    assert _sag(placed) == pytest.approx(-_shell_z(placed, -outer)) and _sag(placed) > 0.0
    # The band reaches past the pad on both sides, turned about the tank axis from the shell point.
    start = math.atan2(-ax, -az)
    for x in (-(outer + 0.5), outer + 0.5):
        turn = math.atan2(x - ax, _shell_z(placed, x) - az) - start
        assert abs(turn) <= _band_angle(placed) + 1e-12
