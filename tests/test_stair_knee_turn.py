"""How a knee brace's turn is read off its end face (brace_sw._knee_angle)."""

import math

import pytest

from swauto.stair import brace_sw as b


def _end_face(twist: float) -> list[tuple[float, float]]:
    """An L3x3x3/8's end outline as (across, out) from the heel, its flat leg down -across and its other leg out,
    turned ``twist`` counterclockwise."""
    c, s = math.cos(twist), math.sin(twist)
    outline = [(0.0, 0.0), (-3.0, 0.0), (-3.0, 0.375), (-0.375, 0.375), (-0.375, 3.0), (0.0, 3.0)]
    return [(a * c - o * s, a * s + o * c) for a, o in outline]


def test_a_twist_too_small_for_the_fit_is_still_read():
    # 89 deg round a 50 ft tank SolidWorks set a platform knee brace a little off square: inside the 0.01 in fit at
    # its 3 in legs, so it was kept, but its clip's 7 in outline, sketched on the flat leg, came 0.011 in off it and
    # the platform's knees stopped there (2026-10-31). The turn read off the end face still sees the twist, so a
    # brace that only fits is turned square too.
    square = _end_face(0.0)
    assert b._knee_fits(square, 0.01)
    assert b._turn_off(square) == pytest.approx(0.0, abs=1e-12)
    twist = math.radians(0.15)
    twisted = _end_face(twist)
    assert b._knee_fits(twisted, 0.01)  # the fit alone lets it through
    assert b._turn_off(twisted) == pytest.approx(-twist, rel=1e-9)  # the turn that squares it
    assert 7.0 * math.sin(twist) > 0.01  # what that leaves at the clip's far edge
