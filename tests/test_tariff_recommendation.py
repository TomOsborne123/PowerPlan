"""Unit tests for tariff pricing normalisation (no Flask / DB)."""

from __future__ import annotations

import pytest

from src.models.tariff_recommendation import (
    coerce_standing_charge_pence_per_day,
    coerce_unit_rate_pence_per_kwh,
    tariff_to_pricing_dict,
)


@pytest.mark.parametrize(
    ("raw", "expected_p_per_kwh"),
    [
        (0, 0.0),
        (-1, 0.0),
        (24.5, 24.5),
        (0.245, 24.5),
        (1.99, 199.0),
        (2.0, 2.0),
        (30.0, 30.0),
    ],
)
def test_coerce_unit_rate_pence_per_kwh(raw: float, expected_p_per_kwh: float) -> None:
    assert coerce_unit_rate_pence_per_kwh(raw) == pytest.approx(expected_p_per_kwh)


@pytest.mark.parametrize(
    ("raw", "expected_p_per_day"),
    [
        (0, 0.0),
        (-5, 0.0),
        (51.0, 51.0),
        (0.52, 52.0),
        (4.99, 499.0),
        (5.0, 5.0),
        (60.0, 60.0),
    ],
)
def test_coerce_standing_charge_pence_per_day(raw: float, expected_p_per_day: float) -> None:
    assert coerce_standing_charge_pence_per_day(raw) == pytest.approx(expected_p_per_day)


def test_tariff_to_pricing_dict_from_plain_dict() -> None:
    d = tariff_to_pricing_dict(
        {
            "unit_rate": 0.28,
            "standing_charge_day": 0.55,
            "supplier_name": "Test Co",
            "tariff_name": "Flex",
            "is_green": True,
            "annual_cost_new": 900.0,
        }
    )
    assert d["unit_rate_p_per_kwh"] == pytest.approx(28.0)
    assert d["standing_charge_p_per_day"] == pytest.approx(55.0)
    assert d["supplier_name"] == "Test Co"
    assert d["tariff_name"] == "Flex"
    assert d["is_green"] is True
    assert d["annual_cost_new"] == pytest.approx(900.0)


def test_tariff_to_pricing_dict_alternate_keys() -> None:
    d = tariff_to_pricing_dict(
        {
            "unit_rate_p_per_kwh": 26.0,
            "standing_charge_p_per_day": 48.0,
            "new_supplier_name": "Alt",
            "tariff_name": "Std",
        }
    )
    assert d["unit_rate_p_per_kwh"] == pytest.approx(26.0)
    assert d["standing_charge_p_per_day"] == pytest.approx(48.0)
    assert d["supplier_name"] == "Alt"


def test_tariff_to_pricing_dict_rejects_invalid_type() -> None:
    with pytest.raises(TypeError, match="Tariff-like object or dict"):
        tariff_to_pricing_dict("not-a-tariff")


class _FakeTariff:
    unit_rate = 24.0
    standing_charge_day = 50.0
    new_supplier_name = "Octopus"
    supplier_name = ""
    tariff_name = "Go"
    is_green = False
    annual_cost_new = 800.0


def test_tariff_to_pricing_dict_from_object() -> None:
    d = tariff_to_pricing_dict(_FakeTariff())
    assert d["unit_rate_p_per_kwh"] == pytest.approx(24.0)
    assert d["standing_charge_p_per_day"] == pytest.approx(50.0)
    assert d["supplier_name"] == "Octopus"
    assert d["tariff_name"] == "Go"
