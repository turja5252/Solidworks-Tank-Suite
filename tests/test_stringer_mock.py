import math

from swauto.stair.stringer import StringerMock, hole_point_in, layout_stringer


def test_outside_face_is_longer_and_the_plate_climbs():
    layout = layout_stringer(StringerMock())
    assert layout.outside_true_in == pytest_approx(112.003)
    assert layout.mid_true_in < layout.outside_true_in
    assert layout.pitch_deg == pytest_approx(32.391)
    low = layout.x0_in
    high_y = (layout.x1_in - low) * math.sin(layout.pitch_rad)
    assert high_y > 50
    along, offset = layout.treads[0].hole_along_in[0], layout.treads[0].hole_offset_in
    x_in, _y_in, z_in = hole_point_in(layout, along, offset)
    assert math.hypot(x_in, z_in) == pytest_approx(layout.mid_radius_in, abs_tol=0.05)


def pytest_approx(value: float, abs_tol: float = 0.02):
    class _Approx:
        def __eq__(self, other):
            return math.isclose(other, value, rel_tol=0, abs_tol=abs_tol)

    return _Approx()
