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


def _two_course(stack: str) -> tuple[TankSpec, tuple[float, float], tuple[float, float]]:
    spec = TankSpec(
        diameter_in=100,
        diameter_basis="mw",
        stack=stack,
        courses=[Course(48, 1.0), Course(48, 0.5)],
    )
    return spec, course_radii_m(spec, spec.courses[0]), course_radii_m(spec, spec.courses[1])


def test_shell_stack_is_one_choice_for_every_course():
    spec, (c1_outer, c1_inner), (od_outer, od_inner) = _two_course("od")
    assert (c1_outer + c1_inner) / 2 == pytest.approx(50 * 0.0254)
    assert od_outer == pytest.approx(c1_outer)
    assert od_outer - od_inner == pytest.approx(0.5 * 0.0254)

    spec, (c1_outer, c1_inner), (id_outer, id_inner) = _two_course("id")
    assert id_inner == pytest.approx(c1_inner)
    assert course_radii_m(spec, spec.courses[0])[1] == pytest.approx(c1_inner)

    _spec, (c1_outer, c1_inner), (mw_outer, mw_inner) = _two_course("mw")
    assert (mw_outer + mw_inner) / 2 == pytest.approx((c1_outer + c1_inner) / 2)
