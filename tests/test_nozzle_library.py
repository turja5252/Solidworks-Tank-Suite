"""The nozzle library (2026-10-30): every size B16.5 has a flange for, 1/2 in through 24 in, and every ASME B36.10M /
B36.19M schedule, checked against the published tables."""

import pytest

from swauto.nozzle.flange import flange
from swauto.nozzle.gasket import gasket
from swauto.nozzle.pipe import SCHEDULES, normalize_nps, normalize_schedule, nps_sizes, pipe

SIZES = ("1/2", "3/4", "1", "1-1/4", "1-1/2", "2", "2-1/2", "3", "3-1/2", "4", "5", "6", "8", "10", "12", "14", "16",
         "18", "20", "22", "24")


def test_every_size_has_a_pipe_a_flange_in_both_classes_and_a_ring_that_centres_on_the_bolts():
    assert nps_sizes() == SIZES
    for size in SIZES:
        neck = pipe(size, "STD")
        for rating in (150, 300):
            for kind in ("wn", "so"):
                fitting = flange(size, rating, kind)
                assert fitting.raised_face_diameter_in < fitting.bolt_circle_in - fitting.bolt_hole_diameter_in
                assert fitting.bolt_circle_in + fitting.bolt_hole_diameter_in < fitting.outside_diameter_in
                assert neck.outside_diameter_in < fitting.slip_on_bore_in <= neck.outside_diameter_in + 0.25  # slips on
            ring = gasket(size, rating, "Non-asbestos")
            assert ring.inner_diameter_in == pytest.approx(neck.outside_diameter_in, abs=0.0126)  # 1/16 rounding
            fitting = flange(size, rating)
            assert ring.outer_diameter_in == pytest.approx(fitting.bolt_circle_in - fitting.bolt_diameter_in, abs=0.011)


# (size, schedule, wall) as ASME B36.10M-2018 and B36.19M publish them.
PUBLISHED_WALLS = (
    ("1/2", "5S", 0.065), ("1/2", "10S", 0.083), ("1/2", "30", 0.095), ("1/2", "40", 0.109), ("1/2", "80", 0.147),
    ("1/2", "160", 0.188), ("1/2", "XXS", 0.294),
    ("1-1/4", "STD", 0.140), ("1-1/4", "XS", 0.191), ("1-1/4", "160", 0.250), ("1-1/4", "XXS", 0.382),
    ("3-1/2", "40", 0.226), ("3-1/2", "80", 0.318), ("3-1/2", "XXS", 0.636),
    ("4", "30", 0.188), ("4", "120", 0.438),
    ("5", "40", 0.258), ("5", "80", 0.375), ("5", "120", 0.500), ("5", "160", 0.625), ("5", "XXS", 0.750),
    ("8", "20", 0.250), ("8", "30", 0.277), ("8", "60", 0.406), ("8", "100", 0.594), ("8", "140", 0.812),
    ("8", "160", 0.906), ("8", "XXS", 0.875),
    ("10", "60", 0.500), ("10", "80", 0.594), ("10", "XS", 0.500), ("10", "160", 1.125),
    ("12", "STD", 0.375), ("12", "40", 0.406), ("12", "80", 0.688), ("12", "80S", 0.500), ("12", "160", 1.312),
    ("16", "10S", 0.188), ("16", "10", 0.250), ("16", "40", 0.500), ("16", "160", 1.594),
    ("20", "30", 0.500), ("20", "40", 0.594), ("20", "160", 1.969),
    ("24", "30", 0.562), ("24", "40", 0.688), ("24", "60", 0.969), ("24", "160", 2.344),
)


@pytest.mark.parametrize(("size", "schedule", "wall"), PUBLISHED_WALLS)
def test_walls_are_the_published_ones(size, schedule, wall):
    assert pipe(size, schedule).wall_in == wall


def test_walls_the_standards_do_not_list_are_refused():
    for size, schedule in (("14", "XXS"), ("3-1/2", "160"), ("6", "20"), ("22", "40"), ("16", "40S")):
        with pytest.raises(ValueError, match=f"no {schedule} wall"):
            pipe(size, schedule)
    # Every size has STD and XS, and its walls grow with the schedule number.
    numbered = [s for s in SCHEDULES if s.isdigit()]
    for size in SIZES:
        assert pipe(size, "STD").wall_in < pipe(size, "XS").wall_in
        walls = [pipe(size, s).wall_in for s in numbered if _listed(size, s)]
        assert walls == sorted(walls) and len(set(walls)) == len(walls)


def _listed(size: str, schedule: str) -> bool:
    try:
        pipe(size, schedule)
    except ValueError:
        return False
    return True


def test_new_flanges_are_b16_5s():
    # (size, class, outside, thickness, hub, slip-on length, weld neck length, bore, bolt circle, bolts, hole);
    # lengths and thickness are without the 0.06 in raised face, as the rest of the table is.
    rows = (
        ("1/2", 150, 3.50, 0.38, 1.19, 0.56, 1.82, 0.88, 2.38, 4, 0.63),
        ("1-1/4", 150, 4.62, 0.56, 2.31, 0.75, 2.19, 1.70, 3.50, 4, 0.63),
        ("3-1/2", 150, 8.50, 0.88, 4.81, 1.19, 2.75, 4.07, 7.00, 8, 0.75),
        ("5", 150, 10.00, 0.88, 6.44, 1.38, 3.44, 5.66, 8.50, 8, 0.875),
        ("1/2", 300, 3.75, 0.50, 1.50, 0.82, 2.00, 0.88, 2.62, 4, 0.63),
        ("1-1/4", 300, 5.25, 0.69, 2.50, 1.00, 2.50, 1.70, 3.88, 4, 0.75),
        ("3-1/2", 300, 9.00, 1.12, 5.25, 1.69, 3.13, 4.07, 7.25, 8, 0.875),
        ("5", 300, 11.00, 1.31, 7.00, 1.94, 3.82, 5.66, 9.25, 8, 0.875),
    )
    for size, rating, outside, thick, hub, so_len, wn_len, bore, circle, bolts, hole in rows:
        wn, so = flange(size, rating, "wn"), flange(size, rating, "so")
        assert (wn.outside_diameter_in, wn.thickness_in, wn.hub_diameter_in) == (outside, thick, hub)
        assert (so.length_through_hub_in, wn.length_through_hub_in, so.slip_on_bore_in) == (so_len, wn_len, bore)
        assert (wn.bolt_circle_in, wn.bolt_count, wn.bolt_hole_diameter_in) == (circle, bolts, hole)


def test_sizes_and_schedules_are_read_as_they_are_typed():
    assert [normalize_nps(text) for text in ("1/2", ".5", "0.5", "1 1/4", "1-1/4", "1.25", "3.5", "5", '5"')] == [
        "1/2", "1/2", "1/2", "1-1/4", "1-1/4", "1-1/4", "3-1/2", "5", "5"]
    assert [normalize_schedule(text) for text in ("40", "Sch 40", "S-40", "std", "Standard", "xh", "Extra Strong",
                                                  "XXH", "10s", "sch 80S", "160")] == [
        "40", "40", "40", "STD", "STD", "XS", "XS", "XXS", "10S", "80S", "160"]
    with pytest.raises(ValueError, match="not an ASME"):
        normalize_schedule("Sch 50")
    assert set(SCHEDULES) >= {"5S", "10S", "40S", "80S", "10", "20", "30", "40", "60", "80", "100", "120", "140",
                              "160", "STD", "XS", "XXS"}
