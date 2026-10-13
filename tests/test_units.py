import pytest

from swauto.units import to_meters


def test_to_meters_inches():
    assert to_meters(10, "in") == pytest.approx(0.254)


def test_to_meters_rejects_non_positive():
    with pytest.raises(ValueError):
        to_meters(0, "in")


def test_to_meters_rejects_unknown_unit():
    with pytest.raises(ValueError):
        to_meters(1, "yd")
