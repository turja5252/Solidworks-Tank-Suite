import math

from swauto.tank.floor import CENTER_SEAM, FloorSpec, layout_floor


def _point_in_polygon(x: float, z: float, polygon) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, (xi, zi) in enumerate(polygon):
        xj, zj = polygon[j]
        if (zi > z) != (zj > z):
            cross = (xj - xi) * (z - zi) / (zj - zi) + xi
            if x < cross:
                inside = not inside
        j = i
    return inside


def test_center_plate_is_the_plate_width_on_the_centerline():
    spec = FloorSpec(diameter_in=400, plate_width_in=60, max_length_in=80, lap_in=2)
    plates = layout_floor(spec)
    middle = [plate for plate in plates if plate.row_k == 0]
    assert len(middle) == 1
    assert middle[0].x0_in == pytest_approx(-30)
    assert middle[0].x1_in == pytest_approx(30)
    assert middle[0].z0_in == pytest_approx(-40)
    assert middle[0].z1_in == pytest_approx(40)
    right = sorted((plate for plate in plates if plate.x0_in > 0), key=lambda plate: plate.x0_in)
    assert right[0].x0_in == pytest_approx(28)
    assert all(len(plate.polygon_in) == 4 for plate in plates)


def test_center_seam_laps_across_the_centerline():
    spec = FloorSpec(diameter_in=400, plate_width_in=60, max_length_in=80, lap_in=2, center=CENTER_SEAM)
    covering = [plate for plate in layout_floor(spec) if plate.x0_in <= 0.0 <= plate.x1_in]
    assert len(covering) == 2
    assert all(plate.row_k != 0 for plate in covering)
    seam = max(plate.x1_in for plate in covering if plate.x1_in < 40)
    lap = min(plate.x0_in for plate in covering if plate.x0_in > -40)
    assert seam - lap == pytest_approx(2.0)
    assert (seam + lap) / 2.0 == pytest_approx(0.0)


def test_full_plates_stop_before_they_leave_the_circle():
    spec = FloorSpec(diameter_in=400, plate_width_in=60, max_length_in=80, lap_in=2)
    plates = layout_floor(spec)
    limit = math.sqrt(200.0**2 - 40.0**2)
    assert len(plates) == 5
    for plate in plates:
        assert max(abs(plate.x0_in), abs(plate.x1_in)) <= limit + 1e-6
    assert max(plate.x1_in for plate in plates) == pytest_approx(146)


def test_rotation_turns_the_row_counterclockwise():
    spec = FloorSpec(diameter_in=160, plate_width_in=60, max_length_in=80, lap_in=2, rotation_deg=90)
    plates = layout_floor(spec)
    assert len(plates) == 1
    corners = {(round(x, 4), round(z, 4)) for x, z in plates[0].polygon_in}
    assert corners == {(40.0, 30.0), (-40.0, 30.0), (-40.0, -30.0), (40.0, -30.0)}


def test_lap_zone_is_in_two_plates():
    spec = FloorSpec(diameter_in=400, plate_width_in=96, max_length_in=120, lap_in=2)
    plates = layout_floor(spec)
    hits = [plate for plate in plates if _point_in_polygon(47.0, 0.0, plate.polygon_in)]
    assert len(hits) >= 2


def pytest_approx(value: float):
    class _Approx:
        def __eq__(self, other):
            return math.isclose(other, value, rel_tol=0, abs_tol=1e-6)

        def __repr__(self):
            return f"approx {value}"

    return _Approx()
