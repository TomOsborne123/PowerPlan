"""
Solar and wind generation type definitions (budget, mid, premium).
Heat pump tiers (COP). Store and pass into the energy balancing model.
"""

from __future__ import annotations

from typing import Any

__all__ = ["SOLAR_TIERS", "WIND_TIERS", "HEAT_PUMP_TIERS"]

# Solar: per-kWp parameters for daily GHI-to-energy conversion
# solar_capex_per_kw: illustrative installed cost (£/kWp) for MVP comparisons — not a quote.
# "none" = user opted out of solar; optimisation should use solar_max_kw=0 (params unused).
SOLAR_TIERS: dict[str, dict[str, Any]] = {
    "none": {
        "pdc0_per_kwp": 1000.0,
        "system_losses": 0.18,
        "inverter_efficiency": 0.94,
        "cost_band": "n/a",
        "solar_capex_per_kw": 0.0,
    },
    "budget": {
        "pdc0_per_kwp": 1000.0,
        "system_losses": 0.18,
        "inverter_efficiency": 0.94,
        "cost_band": "low",
        "solar_capex_per_kw": 1250.0,
    },
    "mid": {
        "pdc0_per_kwp": 1050.0,
        "system_losses": 0.14,
        "inverter_efficiency": 0.96,
        "cost_band": "medium",
        "solar_capex_per_kw": 1600.0,
    },
    "premium": {
        "pdc0_per_kwp": 1100.0,
        "system_losses": 0.10,
        "inverter_efficiency": 0.98,
        "cost_band": "high",
        "solar_capex_per_kw": 1950.0,
    },
}

# Wind: power-curve parameters (per kW nominal)
# wind_capex_per_kw: illustrative £/kW for small-scale — not a quote.
# "none" = user opted out of wind; optimisation should use wind_max_kw=0 (params unused).
WIND_TIERS: dict[str, dict[str, Any]] = {
    "none": {
        "v_cut_in": 3.0,
        "v_rated": 12.0,
        "v_cut_out": 25.0,
        "power_exponent": 2.0,
        "cost_band": "n/a",
        "wind_capex_per_kw": 0.0,
    },
    "budget": {
        "v_cut_in": 3.0,
        "v_rated": 12.0,
        "v_cut_out": 25.0,
        "power_exponent": 2.0,
        "cost_band": "low",
        "wind_capex_per_kw": 2300.0,
    },
    "mid": {
        "v_cut_in": 2.5,
        "v_rated": 11.0,
        "v_cut_out": 25.0,
        "power_exponent": 2.2,
        "cost_band": "medium",
        "wind_capex_per_kw": 2750.0,
    },
    "premium": {
        "v_cut_in": 2.0,
        "v_rated": 10.0,
        "v_cut_out": 25.0,
        "power_exponent": 2.5,
        "cost_band": "high",
        "wind_capex_per_kw": 3300.0,
    },
}

# Heat pumps: COP (coefficient of performance). Electricity for heating = heat_demand / COP.
# Tiers align with solar/wind budget | mid | premium. spec_url = independent guidance / specs.
HEAT_PUMP_TIERS: dict[str, dict[str, Any]] = {
    "none": {
        "cop": 1.0,
        "cost_band": "n/a",
        "label": "No heat pump (direct electric heating)",
        "spec_url": "https://www.energysavingtrust.org.uk/advice/electric-heating/",
    },
    "budget": {
        "cop": 2.5,
        "cost_band": "low",
        "label": "Budget / older typical ASHP",
        "spec_url": "https://www.energysavingtrust.org.uk/advice/air-source-heat-pumps/",
    },
    "mid": {
        "cop": 3.0,
        "cost_band": "medium",
        "label": "Mid-range (modern ASHP)",
        "spec_url": "https://www.gov.uk/improve-energy-efficiency",
    },
    "premium": {
        "cop": 3.5,
        "cost_band": "high",
        "label": "Premium / high-performance ASHP",
        "spec_url": "https://mcscertified.com/",
    },
    # Legacy keys kept for older clients
    "standard": {
        "cop": 2.5,
        "cost_band": "medium",
        "label": "Standard ASHP",
        "spec_url": "https://www.energysavingtrust.org.uk/advice/air-source-heat-pumps/",
    },
    "efficient": {
        "cop": 3.5,
        "cost_band": "high",
        "label": "Efficient ASHP",
        "spec_url": "https://mcscertified.com/",
    },
}
