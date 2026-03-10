"""
Solar and wind generation type definitions (budget, mid, premium).
Heat pump tiers (COP). Store and pass into the energy balancing model.
"""

from __future__ import annotations

from typing import Any

__all__ = ["SOLAR_TIERS", "WIND_TIERS", "HEAT_PUMP_TIERS"]

# Solar: per-kWp parameters for daily GHI-to-energy conversion
SOLAR_TIERS: dict[str, dict[str, Any]] = {
    "budget": {
        "pdc0_per_kwp": 1000.0,
        "system_losses": 0.18,
        "inverter_efficiency": 0.94,
        "cost_band": "low",
    },
    "mid": {
        "pdc0_per_kwp": 1050.0,
        "system_losses": 0.14,
        "inverter_efficiency": 0.96,
        "cost_band": "medium",
    },
    "premium": {
        "pdc0_per_kwp": 1100.0,
        "system_losses": 0.10,
        "inverter_efficiency": 0.98,
        "cost_band": "high",
    },
}

# Wind: power-curve parameters (per kW nominal)
WIND_TIERS: dict[str, dict[str, Any]] = {
    "budget": {
        "v_cut_in": 3.0,
        "v_rated": 12.0,
        "v_cut_out": 25.0,
        "power_exponent": 2.0,
        "cost_band": "low",
    },
    "mid": {
        "v_cut_in": 2.5,
        "v_rated": 11.0,
        "v_cut_out": 25.0,
        "power_exponent": 2.2,
        "cost_band": "medium",
    },
    "premium": {
        "v_cut_in": 2.0,
        "v_rated": 10.0,
        "v_cut_out": 25.0,
        "power_exponent": 2.5,
        "cost_band": "high",
    },
}

# Heat pumps: COP (coefficient of performance). Electricity for heating = heat_demand / COP.
# "none" = electric heating (COP 1). Pass as heat_pump_params to energy balancing.
HEAT_PUMP_TIERS: dict[str, dict[str, Any]] = {
    "none": {
        "cop": 1.0,
        "cost_band": "n/a",
    },
    "standard": {
        "cop": 2.5,
        "cost_band": "medium",
    },
    "efficient": {
        "cop": 3.5,
        "cost_band": "high",
    },
}
