import pytest

from swauto.tank.profile import course_radii_m, shell_profile_meters
from swauto.tank.spec import Course, TankSpec


def test_outside_basis_radii():
    spec = TankSpec(diameter_in=100, diameter_basis="outside", courses=[Course(48, 1)])
    outer, inner = course_radii_m(spec, spec.courses[0])
    assert outer == pytest.approx(1.27)  # 50 in
    assert inner == pytest.approx(1.27 - 0.0254)


def test_profile_is_closed_and_positive():
    spec = TankSpec(
        diameter_in=120,
        diameter_basis="outside",
        courses=[Course(48, 0.5), Course(48, 0.375), Course(0, 0)],
    )
    pts = shell_profile_meters(spec)
    assert pts[0] == pts[-1]
    assert all(x > 0 for x, _y in pts)
    assert max(y for _x, y in pts) == pytest.approx(96 * 0.0254)


def test_centerline_basis():
    spec = TankSpec(diameter_in=100, diameter_basis="centerline", courses=[Course(12, 2)])
    outer, inner = course_radii_m(spec, spec.courses[0])
    assert (outer + inner) / 2 == pytest.approx(50 * 0.0254)
