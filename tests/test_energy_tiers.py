"""Sanity checks for tier configuration used by the optimiser."""

from __future__ import annotations

import pytest

from src.data.energy_tiers import HEAT_PUMP_TIERS, SOLAR_TIERS, WIND_TIERS


@pytest.mark.parametrize("name", ["none", "budget", "mid", "premium"])
def test_solar_wind_tiers_have_core_keys(name: str) -> None:
    s = SOLAR_TIERS[name]
    w = WIND_TIERS[name]
    assert "pdc0_per_kwp" in s
    assert "solar_capex_per_kw" in s
    assert s["solar_capex_per_kw"] >= 0
    assert "v_rated" in w
    assert "wind_capex_per_kw" in w
    assert w["wind_capex_per_kw"] >= 0


@pytest.mark.parametrize("name", ["none", "budget", "mid", "premium"])
def test_heat_pump_tier_cop(name: str) -> None:
    row = HEAT_PUMP_TIERS[name]
    assert "cop" in row
    assert row["cop"] > 0


def test_none_tiers_zero_or_unit_capex() -> None:
    assert SOLAR_TIERS["none"]["solar_capex_per_kw"] == 0.0
    assert WIND_TIERS["none"]["wind_capex_per_kw"] == 0.0
    assert HEAT_PUMP_TIERS["none"]["cop"] == 1.0
