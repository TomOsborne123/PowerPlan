"""
Energy balancing model: lat/lon to solar and wind flux, then to energy options at different price tiers.
Builds monthly generation profiles, accepts user consumption, and optimises system capacity to minimise estimated cost.
Uses pvlib for solar and an in-repo power-curve model for wind.
"""

from __future__ import annotations

import pandas as pd
from datetime import datetime, timedelta
from typing import Any

# Typical UK monthly fractions of annual generation (sum = 1). Used when only short-run flux is available.
# Solar: winter low, summer high.
MONTHLY_FRACTION_SOLAR_UK = [
    0.02, 0.03, 0.05, 0.07, 0.09, 0.11, 0.12, 0.11, 0.09, 0.06, 0.03, 0.02,
]  # Jan..Dec
# Wind: often higher in winter.
MONTHLY_FRACTION_WIND_UK = [
    0.11, 0.09, 0.09, 0.07, 0.06, 0.05, 0.05, 0.05, 0.06, 0.08, 0.09, 0.10,
]  # Jan..Dec
MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Default estimated pricing (£) for optimisation.
DEFAULT_PRICING = {
    "solar_capex_per_kw": 1500.0,   # £/kWp installed
    "wind_capex_per_kw": 2500.0,    # £/kW nominal
    "grid_price_per_kwh": 0.25,     # £/kWh imported
    "export_price_per_kwh": 0.05,   # £/kWh exported (optional)
}

# Insulation: use R-value (thermal resistance, m²·K/W). Higher R = less heat loss.
# Heating demand reduction = min(50%, R_value / INSULATION_R_VALUE_SCALE). Typical building R ~ 1–6 m²·K/W.
INSULATION_R_VALUE_SCALE = 10.0   # R-value at which heating reduction caps at 50%
INSULATION_R_VALUE_MAX_REDUCTION = 0.5

# Optional pvlib for solar
try:
    import pvlib
    from pvlib import solarposition, irradiance, temperature, pvsystem, inverter
    PVLIB_AVAILABLE = True
except ImportError:
    PVLIB_AVAILABLE = False

__all__ = [
    "get_flux",
    "get_monthly_profiles",
    "get_energy_options",
    "get_optimised_system",
    "optimize_system_capacity",
    "evaluate_system_capacity",
    "DEFAULT_PRICING",
    "INSULATION_R_VALUE_SCALE",
    "SOLAR_TIERS",
    "WIND_TIERS",
]

# --- Default date range (forecast) ---
def _default_dates():
    start = datetime.utcnow().date()
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


# --- Solar tier config: budget / mid / premium (per kWp) ---
SOLAR_TIERS = {
    "budget": {
        "pdc0_per_kwp": 1000.0,       # W per kWp (100% nameplate)
        "gamma_pdc": -0.004,          # temp coefficient per °C
        "system_losses": 0.18,        # total loss factor (soiling, mismatch, wiring, etc.)
        "inverter_efficiency": 0.94,
        "cost_band": "low",
    },
    "mid": {
        "pdc0_per_kwp": 1050.0,
        "gamma_pdc": -0.0035,
        "system_losses": 0.14,
        "inverter_efficiency": 0.96,
        "cost_band": "medium",
    },
    "premium": {
        "pdc0_per_kwp": 1100.0,
        "gamma_pdc": -0.003,
        "system_losses": 0.10,
        "inverter_efficiency": 0.98,
        "cost_band": "high",
    },
}

# --- Wind tier config: power curve params (per kW nominal) ---
WIND_TIERS = {
    "budget": {
        "v_cut_in": 3.0,    # m/s
        "v_rated": 12.0,    # m/s
        "v_cut_out": 25.0,
        "power_exponent": 2.0,  # P ~ (v - v_cut_in)^k between cut-in and rated
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


def get_flux(
    lat: float,
    lon: float,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Fetch hourly solar and wind flux for a location.
    Returns a DataFrame with datetime index and columns: ghi, dhi, dni, wind_speed_10m, temperature_2m.
    """
    from src.api.get_weather import get_weather

    start_date, end_date = start_date or _default_dates()[0], end_date or _default_dates()[1]
    variables = [
        "shortwave_radiation",
        "diffuse_radiation",
        "direct_normal_irradiance",
        "wind_speed_10m",
        "temperature_2m",
    ]
    df = get_weather(
        latitude=lat,
        longitude=lon,
        start_date=start_date,
        end_date=end_date,
        variables=variables,
        frequency="hourly",
    )
    df = df.rename(columns={
        "shortwave_radiation": "ghi",
        "diffuse_radiation": "dhi",
        "direct_normal_irradiance": "dni",
    })
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date")
    return df


def _wind_power_curve(v: float, v_cut_in: float, v_rated: float, v_cut_out: float, k: float) -> float:
    """Power output per kW nominal: 0 below cut-in, scaled between cut-in and rated, 1.0 at rated, 0 above cut-out."""
    if v < v_cut_in or v >= v_cut_out:
        return 0.0
    if v >= v_rated:
        return 1.0
    # P = ((v - v_cut_in) / (v_rated - v_cut_in)) ** k
    return ((v - v_cut_in) / (v_rated - v_cut_in)) ** k


def _annual_solar_kwh_per_kw(
    flux_df: pd.DataFrame,
    lat: float,
    lon: float,
    tier_cfg: dict[str, Any],
) -> float:
    """Compute annual AC kWh per kWp for one solar tier (uses period in flux_df, scaled to 365 days)."""
    if not PVLIB_AVAILABLE:
        return 0.0
    times = flux_df.index
    ghi = flux_df["ghi"].fillna(0)
    dhi = flux_df["dhi"].fillna(0)
    dni = flux_df["dni"].fillna(0)
    temp_air = flux_df["temperature_2m"].reindex(times).fillna(15.0)
    location = pvlib.location.Location(lat, lon, tz=times.tz or "UTC")
    solar_pos = solarposition.get_solarposition(times, location.latitude, location.longitude)
    surface_tilt = min(45.0, max(10.0, lat))
    surface_azimuth = 180.0
    poa = irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        solar_zenith=solar_pos["zenith"],
        solar_azimuth=solar_pos["azimuth"],
        ghi=ghi,
        dhi=dhi,
        dni=dni,
    )
    poa_global = poa["poa_global"].fillna(0).clip(lower=0)
    temp_cell = temp_air + (poa_global / 1000.0) * 25.0
    pdc0 = tier_cfg["pdc0_per_kwp"]
    gamma_pdc = tier_cfg["gamma_pdc"]
    system_losses = tier_cfg["system_losses"]
    eta_inv = tier_cfg["inverter_efficiency"]
    dc_per_kwp = pvsystem.pvwatts_dc(poa_global, temp_cell, pdc0=pdc0, gamma_pdc=gamma_pdc)
    dc_per_kwp = dc_per_kwp * (1.0 - system_losses)
    ac_per_kwp = inverter.pvwatts(dc_per_kwp, pdc0=pdc0, eta_inv_nom=eta_inv)
    period_hours = len(flux_df)
    period_days = period_hours / 24.0
    scale_to_annual = 365.0 / period_days if period_days > 0 else 1.0
    energy_kwh_period = ac_per_kwp.sum() / 1000.0
    return float(energy_kwh_period * scale_to_annual)


def _annual_wind_kwh_per_kw(flux_df: pd.DataFrame, tier_cfg: dict[str, Any]) -> float:
    """Compute annual kWh per kW for one wind tier (uses period in flux_df, scaled to 365 days)."""
    wind_speed = flux_df["wind_speed_10m"].fillna(0)
    period_hours = len(flux_df)
    period_days = period_hours / 24.0
    scale_to_annual = 365.0 / period_days if period_days > 0 else 1.0
    v_ci, v_r, v_co, k = tier_cfg["v_cut_in"], tier_cfg["v_rated"], tier_cfg["v_cut_out"], tier_cfg["power_exponent"]
    cf_series = wind_speed.apply(lambda v: _wind_power_curve(float(v), v_ci, v_r, v_co, k))
    energy_kwh_period = cf_series.mean() * period_hours
    return float(energy_kwh_period * scale_to_annual)


def get_monthly_profiles(
    flux_df: pd.DataFrame,
    lat: float,
    lon: float,
    solar_tier: str = "mid",
    wind_tier: str = "mid",
    solar_tiers_config: dict[str, Any] | None = None,
    wind_tiers_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build monthly generation profiles (kWh per kW) for solar and wind from flux data.
    Uses typical UK monthly fractions to distribute annual generation when flux is a short sample.
    Returns dict with keys: monthly_profile (DataFrame), solar_kwh_per_kw (list of 12), wind_kwh_per_kw (list of 12),
    annual_solar_per_kw, annual_wind_per_kw.
    """
    solar_tiers = solar_tiers_config or SOLAR_TIERS
    wind_tiers = wind_tiers_config or WIND_TIERS
    annual_solar = _annual_solar_kwh_per_kw(flux_df, lat, lon, solar_tiers[solar_tier])
    annual_wind = _annual_wind_kwh_per_kw(flux_df, wind_tiers[wind_tier])
    solar_kwh_per_kw = [annual_solar * f for f in MONTHLY_FRACTION_SOLAR_UK]
    wind_kwh_per_kw = [annual_wind * f for f in MONTHLY_FRACTION_WIND_UK]
    monthly_profile = pd.DataFrame({
        "month": MONTH_LABELS,
        "solar_kwh_per_kw": solar_kwh_per_kw,
        "wind_kwh_per_kw": wind_kwh_per_kw,
    })
    return {
        "monthly_profile": monthly_profile,
        "solar_kwh_per_kw": solar_kwh_per_kw,
        "wind_kwh_per_kw": wind_kwh_per_kw,
        "annual_solar_per_kw": annual_solar,
        "annual_wind_per_kw": annual_wind,
    }


def run_solar_options(
    flux_df: pd.DataFrame,
    lat: float,
    lon: float,
    tiers_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Run solar PV model for each tier. Returns list of option dicts (technology, tier, capacity_kw, annual_energy_kwh, cost_band, etc.).
    Energy is computed for the period in flux_df and scaled to annual (period_days -> 365).
    """
    if not PVLIB_AVAILABLE:
        return []
    tiers = tiers_config or SOLAR_TIERS
    times = flux_df.index
    ghi = flux_df["ghi"].fillna(0)
    dhi = flux_df["dhi"].fillna(0)
    dni = flux_df["dni"].fillna(0)
    temp_air = flux_df["temperature_2m"].reindex(times).fillna(15.0)

    location = pvlib.location.Location(lat, lon, tz=times.tz or "UTC")
    solar_pos = solarposition.get_solarposition(times, location.latitude, location.longitude)
    # Fixed tilt/azimuth: tilt ~ latitude, azimuth 180 = south (northern hemisphere)
    surface_tilt = min(45.0, max(10.0, lat))
    surface_azimuth = 180.0

    poa = irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        solar_zenith=solar_pos["zenith"],
        solar_azimuth=solar_pos["azimuth"],
        ghi=ghi,
        dhi=dhi,
        dni=dni,
    )
    poa_global = poa["poa_global"].fillna(0).clip(lower=0)

    # Simple cell temperature: temp_air + (poa/1000)*25
    temp_cell = temp_air + (poa_global / 1000.0) * 25.0

    options = []
    period_hours = len(flux_df)
    period_days = period_hours / 24.0
    scale_to_annual = 365.0 / period_days if period_days > 0 else 1.0

    for tier_name, cfg in tiers.items():
        pdc0 = cfg["pdc0_per_kwp"]
        gamma_pdc = cfg["gamma_pdc"]
        system_losses = cfg["system_losses"]
        eta_inv = cfg["inverter_efficiency"]

        dc_per_kwp = pvsystem.pvwatts_dc(
            poa_global,
            temp_cell,
            pdc0=pdc0,
            gamma_pdc=gamma_pdc,
        )
        dc_per_kwp = dc_per_kwp * (1.0 - system_losses)
        ac_per_kwp = inverter.pvwatts(dc_per_kwp, pdc0=pdc0, eta_inv_nom=eta_inv)

        energy_wh = ac_per_kwp.sum()
        energy_kwh_period = energy_wh / 1000.0
        annual_energy_kwh = energy_kwh_period * scale_to_annual

        options.append({
            "technology": "solar",
            "tier": tier_name,
            "capacity_kw": 1.0,
            "annual_energy_kwh": round(annual_energy_kwh, 1),
            "cost_band": cfg["cost_band"],
            "period_days": round(period_days, 1),
            "capacity_factor": round(annual_energy_kwh / (1.0 * 8760) * 100, 2) if annual_energy_kwh else 0.0,
        })
    return options


def run_wind_options(
    flux_df: pd.DataFrame,
    tiers_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Run wind power-curve model for each tier. Returns list of option dicts.
    Output is per kW nominal capacity; energy is scaled to annual.
    """
    tiers = tiers_config or WIND_TIERS
    wind_speed = flux_df["wind_speed_10m"].fillna(0)
    period_hours = len(flux_df)
    period_days = period_hours / 24.0
    scale_to_annual = 365.0 / period_days if period_days > 0 else 1.0

    options = []
    for tier_name, cfg in tiers.items():
        v_ci = cfg["v_cut_in"]
        v_r = cfg["v_rated"]
        v_co = cfg["v_cut_out"]
        k = cfg["power_exponent"]

        cf_series = wind_speed.apply(
            lambda v: _wind_power_curve(float(v), v_ci, v_r, v_co, k)
        )
        capacity_factor_period = cf_series.mean()
        # Energy per kW in period: CF * 1 kW * hours
        energy_kwh_period = capacity_factor_period * period_hours
        annual_energy_kwh = energy_kwh_period * scale_to_annual
        capacity_factor_annual = cf_series.mean()  # same as period for CF

        options.append({
            "technology": "wind",
            "tier": tier_name,
            "capacity_kw": 1.0,
            "annual_energy_kwh": round(annual_energy_kwh, 1),
            "cost_band": cfg["cost_band"],
            "period_days": round(period_days, 1),
            "capacity_factor": round(capacity_factor_annual * 100, 2),
        })
    return options


def get_energy_options(
    latitude: float,
    longitude: float,
    start_date: str | None = None,
    end_date: str | None = None,
    solar_tiers: dict[str, Any] | None = None,
    wind_tiers: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Get combined solar and wind energy options at different price points for a location.
    Returns a list of option dicts with technology, tier, capacity_kw, annual_energy_kwh, cost_band, etc.
    """
    flux_df = get_flux(latitude, longitude, start_date, end_date)
    options = []
    options.extend(run_solar_options(flux_df, latitude, longitude, solar_tiers))
    options.extend(run_wind_options(flux_df, wind_tiers))
    return options


def _monthly_consumption_from_input(
    monthly_consumption_kwh: list[float] | None = None,
    annual_consumption_kwh: float | None = None,
    monthly_fraction: list[float] | None = None,
) -> list[float]:
    """
    Return a list of 12 monthly consumption values (kWh).
    Either pass monthly_consumption_kwh (length 12) or annual_consumption_kwh.
    If annual, monthly_fraction (length 12, sum 1) spreads it; default is flat 1/12.
    """
    if monthly_consumption_kwh is not None:
        if len(monthly_consumption_kwh) != 12:
            raise ValueError("monthly_consumption_kwh must have 12 elements")
        return list(monthly_consumption_kwh)
    if annual_consumption_kwh is None:
        raise ValueError("Provide either monthly_consumption_kwh or annual_consumption_kwh")
    frac = monthly_fraction or [1.0 / 12] * 12
    if len(frac) != 12:
        raise ValueError("monthly_fraction must have 12 elements")
    return [annual_consumption_kwh * f for f in frac]


def _insulation_reduction_from_r_value(r_value: float) -> float:
    """
    Fraction of heating demand reduced from R-value (m²·K/W).
    Linear in R up to INSULATION_R_VALUE_SCALE, then capped at INSULATION_R_VALUE_MAX_REDUCTION.
    """
    if r_value <= 0:
        return 0.0
    return min(
        INSULATION_R_VALUE_MAX_REDUCTION,
        (r_value / INSULATION_R_VALUE_SCALE) * INSULATION_R_VALUE_MAX_REDUCTION,
    )


def _apply_insulation(
    monthly_consumption_kwh: list[float],
    insulation_r_value: float = 0.0,
    heating_fraction: float = 0.6,
) -> list[float]:
    """
    Reduce monthly demand to reflect insulation (applies to heating share of demand).
    insulation_r_value: R-value in m²·K/W (thermal resistance; 0 = none, typical 1–6, high 8+).
    heating_fraction: share of total demand that is space heating (default 0.6 for UK).
    Returns new monthly consumption (kWh) after insulation savings.
    """
    reduction = _insulation_reduction_from_r_value(insulation_r_value)
    if reduction <= 0 or heating_fraction <= 0:
        return list(monthly_consumption_kwh)
    scale = 1.0 - heating_fraction * reduction
    return [c * scale for c in monthly_consumption_kwh]


def optimize_system_capacity(
    monthly_consumption_kwh: list[float],
    monthly_solar_kwh_per_kw: list[float],
    monthly_wind_kwh_per_kw: list[float],
    solar_capex_per_kw: float = DEFAULT_PRICING["solar_capex_per_kw"],
    wind_capex_per_kw: float = DEFAULT_PRICING["wind_capex_per_kw"],
    grid_price_per_kwh: float = DEFAULT_PRICING["grid_price_per_kwh"],
    export_price_per_kwh: float | None = DEFAULT_PRICING["export_price_per_kwh"],
    solar_max_kw: float = 20.0,
    wind_max_kw: float = 10.0,
    step_kw: float = 0.5,
    min_demand_met_from_gen_pct: float = 0.0,
    years: float = 25.0,
) -> dict[str, Any]:
    """
    Find solar and wind capacity (kW) that minimises total cost over `years` to meet demand:
    capex + (annual grid import cost - annual export revenue) * years.
    Payback: years for capex to be recovered by annual savings vs grid-only.
    min_demand_met_from_gen_pct (0–100): require at least this share from own generation.
    Returns dict with optimal_solar_kw, optimal_wind_kw, total_capacity_kw, capex, payback_years,
    cost_over_years, annual_opex_*, demand_met_from_generation_pct, monthly_balance (DataFrame).
    """
    best_cost = float("inf")
    best_solar = 0.0
    best_wind = 0.0
    best_monthly_import = None
    best_monthly_export = None
    export_price = export_price_per_kwh if export_price_per_kwh is not None else 0.0
    annual_demand = sum(monthly_consumption_kwh)

    solar_kw = 0.0
    while solar_kw <= solar_max_kw:
        wind_kw = 0.0
        while wind_kw <= wind_max_kw:
            annual_import_cost = 0.0
            annual_export_revenue = 0.0
            annual_gen = 0.0
            monthly_import = []
            monthly_export = []
            for m in range(12):
                gen = solar_kw * monthly_solar_kwh_per_kw[m] + wind_kw * monthly_wind_kwh_per_kw[m]
                annual_gen += gen
                demand = monthly_consumption_kwh[m]
                imp = max(0.0, demand - gen)
                exp = max(0.0, gen - demand)
                monthly_import.append(imp)
                monthly_export.append(exp)
                annual_import_cost += imp * grid_price_per_kwh
                annual_export_revenue += exp * export_price
            demand_met_pct = (annual_gen / annual_demand * 100.0) if annual_demand > 0 else 0.0
            if demand_met_pct < min_demand_met_from_gen_pct:
                wind_kw += step_kw
                if wind_kw > wind_max_kw:
                    break
                continue
            capex = solar_kw * solar_capex_per_kw + wind_kw * wind_capex_per_kw
            annual_net_opex = annual_import_cost - annual_export_revenue
            total_cost = capex + annual_net_opex * years
            if total_cost < best_cost:
                best_cost = total_cost
                best_solar = solar_kw
                best_wind = wind_kw
                best_monthly_import = monthly_import
                best_monthly_export = monthly_export
            wind_kw += step_kw
            if wind_kw > wind_max_kw:
                break
        solar_kw += step_kw
        if solar_kw > solar_max_kw:
            break

    capex = best_solar * solar_capex_per_kw + best_wind * wind_capex_per_kw
    opex_import = sum(imp * grid_price_per_kwh for imp in (best_monthly_import or [0] * 12))
    opex_export = sum(exp * export_price for exp in (best_monthly_export or [0] * 12))
    monthly_balance_df = pd.DataFrame({
        "month": MONTH_LABELS,
        "consumption_kwh": monthly_consumption_kwh,
        "solar_gen_kwh": [best_solar * monthly_solar_kwh_per_kw[m] for m in range(12)],
        "wind_gen_kwh": [best_wind * monthly_wind_kwh_per_kw[m] for m in range(12)],
        "grid_import_kwh": best_monthly_import or [0] * 12,
        "export_kwh": best_monthly_export or [0] * 12,
    })
    monthly_balance_df["total_gen_kwh"] = monthly_balance_df["solar_gen_kwh"] + monthly_balance_df["wind_gen_kwh"]

    annual_demand_kwh = sum(monthly_consumption_kwh)
    annual_gen_kwh = monthly_balance_df["total_gen_kwh"].sum()
    demand_met_from_gen_pct = (annual_gen_kwh / annual_demand_kwh * 100.0) if annual_demand_kwh > 0 else 0.0
    total_capacity_kw = best_solar + best_wind
    annual_net_opex = opex_import - opex_export
    cost_over_years = capex + annual_net_opex * years
    # Payback: years for capex to be recovered by savings vs grid-only (annual_demand * grid_price - annual_net_opex)
    grid_only_annual_cost = annual_demand_kwh * grid_price_per_kwh
    annual_savings = grid_only_annual_cost - annual_net_opex
    if annual_savings > 0 and capex > 0:
        payback_years = capex / annual_savings
    else:
        payback_years = None

    return {
        "optimal_solar_kw": round(best_solar, 2),
        "optimal_wind_kw": round(best_wind, 2),
        "total_capacity_kw": round(total_capacity_kw, 2),
        "capex": round(capex, 2),
        "annual_opex_import_cost": round(opex_import, 2),
        "annual_export_revenue": round(opex_export, 2),
        "annual_net_opex": round(annual_net_opex, 2),
        "years_considered": years,
        "total_annual_cost_estimate": round(capex + annual_net_opex, 2),
        "cost_over_years": round(cost_over_years, 2),
        "payback_years": round(payback_years, 1) if payback_years is not None else None,
        "annual_demand_kwh": round(annual_demand_kwh, 1),
        "annual_generation_kwh": round(annual_gen_kwh, 1),
        "demand_met_from_generation_pct": round(demand_met_from_gen_pct, 1),
        "monthly_balance": monthly_balance_df,
        "monthly_profile_solar_kwh_per_kw": monthly_solar_kwh_per_kw,
        "monthly_profile_wind_kwh_per_kw": monthly_wind_kwh_per_kw,
    }


def evaluate_system_capacity(
    solar_kw: float,
    wind_kw: float,
    monthly_consumption_kwh: list[float],
    monthly_solar_kwh_per_kw: list[float],
    monthly_wind_kwh_per_kw: list[float],
    solar_capex_per_kw: float = DEFAULT_PRICING["solar_capex_per_kw"],
    wind_capex_per_kw: float = DEFAULT_PRICING["wind_capex_per_kw"],
    grid_price_per_kwh: float = DEFAULT_PRICING["grid_price_per_kwh"],
    export_price_per_kwh: float | None = DEFAULT_PRICING["export_price_per_kwh"],
    years: float = 25.0,
) -> dict[str, Any]:
    """
    Evaluate a fixed system size (solar_kw, wind_kw): costs, payback, monthly balance.
    Same return shape as optimize_system_capacity but for one capacity pair.
    """
    export_price = export_price_per_kwh if export_price_per_kwh is not None else 0.0
    capex = solar_kw * solar_capex_per_kw + wind_kw * wind_capex_per_kw
    monthly_import = []
    monthly_export = []
    for m in range(12):
        gen = solar_kw * monthly_solar_kwh_per_kw[m] + wind_kw * monthly_wind_kwh_per_kw[m]
        demand = monthly_consumption_kwh[m]
        monthly_import.append(max(0.0, demand - gen))
        monthly_export.append(max(0.0, gen - demand))
    opex_import = sum(imp * grid_price_per_kwh for imp in monthly_import)
    opex_export = sum(exp * export_price for exp in monthly_export)
    annual_net_opex = opex_import - opex_export
    annual_demand_kwh = sum(monthly_consumption_kwh)
    annual_gen_kwh = sum(solar_kw * monthly_solar_kwh_per_kw[m] + wind_kw * monthly_wind_kwh_per_kw[m] for m in range(12))
    demand_met_pct = (annual_gen_kwh / annual_demand_kwh * 100.0) if annual_demand_kwh > 0 else 0.0
    cost_over_years = capex + annual_net_opex * years
    grid_only_annual_cost = annual_demand_kwh * grid_price_per_kwh
    annual_savings = grid_only_annual_cost - annual_net_opex
    payback_years = (capex / annual_savings) if (annual_savings > 0 and capex > 0) else None
    monthly_balance_df = pd.DataFrame({
        "month": MONTH_LABELS,
        "consumption_kwh": monthly_consumption_kwh,
        "solar_gen_kwh": [solar_kw * monthly_solar_kwh_per_kw[m] for m in range(12)],
        "wind_gen_kwh": [wind_kw * monthly_wind_kwh_per_kw[m] for m in range(12)],
        "grid_import_kwh": monthly_import,
        "export_kwh": monthly_export,
    })
    monthly_balance_df["total_gen_kwh"] = monthly_balance_df["solar_gen_kwh"] + monthly_balance_df["wind_gen_kwh"]
    return {
        "optimal_solar_kw": round(solar_kw, 2),
        "optimal_wind_kw": round(wind_kw, 2),
        "total_capacity_kw": round(solar_kw + wind_kw, 2),
        "capex": round(capex, 2),
        "annual_opex_import_cost": round(opex_import, 2),
        "annual_export_revenue": round(opex_export, 2),
        "annual_net_opex": round(annual_net_opex, 2),
        "years_considered": years,
        "total_annual_cost_estimate": round(capex + annual_net_opex, 2),
        "cost_over_years": round(cost_over_years, 2),
        "payback_years": round(payback_years, 1) if payback_years is not None else None,
        "annual_demand_kwh": round(annual_demand_kwh, 1),
        "annual_generation_kwh": round(annual_gen_kwh, 1),
        "demand_met_from_generation_pct": round(demand_met_pct, 1),
        "monthly_balance": monthly_balance_df,
        "monthly_profile_solar_kwh_per_kw": monthly_solar_kwh_per_kw,
        "monthly_profile_wind_kwh_per_kw": monthly_wind_kwh_per_kw,
    }


def get_optimised_system(
    latitude: float,
    longitude: float,
    monthly_consumption_kwh: list[float] | None = None,
    annual_consumption_kwh: float | None = None,
    monthly_fraction: list[float] | None = None,
    pricing: dict[str, float] | None = None,
    solar_tier: str = "mid",
    wind_tier: str = "mid",
    solar_max_kw: float = 20.0,
    wind_max_kw: float = 10.0,
    step_kw: float = 0.5,
    min_demand_met_from_gen_pct: float = 0.0,
    years: float = 25.0,
    fixed_solar_kw: float | None = None,
    fixed_wind_kw: float | None = None,
    insulation_r_value: float = 0.0,
    heating_fraction: float = 0.6,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Optimise system capacity and cost to meet user energy demand over `years`, or evaluate a fixed size.
    Capacity: optimiser search (solar_max_kw, wind_max_kw, step_kw) or fixed_solar_kw/fixed_wind_kw.
    insulation_r_value: R-value in m²·K/W (0 = none; typical 1–6; reduces heating share of demand).
    heating_fraction: share of demand that is space heating (default 0.6); insulation applies to this share.
    """
    flux_df = get_flux(latitude, longitude, start_date, end_date)
    profiles = get_monthly_profiles(flux_df, latitude, longitude, solar_tier=solar_tier, wind_tier=wind_tier)
    consumption_raw = _monthly_consumption_from_input(
        monthly_consumption_kwh=monthly_consumption_kwh,
        annual_consumption_kwh=annual_consumption_kwh,
        monthly_fraction=monthly_fraction,
    )
    consumption = _apply_insulation(consumption_raw, insulation_r_value=insulation_r_value, heating_fraction=heating_fraction)
    pr = {**DEFAULT_PRICING, **(pricing or {})}
    if fixed_solar_kw is not None and fixed_wind_kw is not None:
        result = evaluate_system_capacity(
            fixed_solar_kw,
            fixed_wind_kw,
            consumption,
            profiles["solar_kwh_per_kw"],
            profiles["wind_kwh_per_kw"],
            solar_capex_per_kw=pr["solar_capex_per_kw"],
            wind_capex_per_kw=pr["wind_capex_per_kw"],
            grid_price_per_kwh=pr["grid_price_per_kwh"],
            export_price_per_kwh=pr.get("export_price_per_kwh"),
            years=years,
        )
    else:
        result = optimize_system_capacity(
            monthly_consumption_kwh=consumption,
            monthly_solar_kwh_per_kw=profiles["solar_kwh_per_kw"],
            monthly_wind_kwh_per_kw=profiles["wind_kwh_per_kw"],
            solar_capex_per_kw=pr["solar_capex_per_kw"],
            wind_capex_per_kw=pr["wind_capex_per_kw"],
            grid_price_per_kwh=pr["grid_price_per_kwh"],
            export_price_per_kwh=pr.get("export_price_per_kwh"),
            solar_max_kw=solar_max_kw,
            wind_max_kw=wind_max_kw,
            step_kw=step_kw,
            min_demand_met_from_gen_pct=min_demand_met_from_gen_pct,
            years=years,
        )
    annual_demand_before_insulation = sum(consumption_raw)
    annual_demand_after_insulation = sum(consumption)
    return {
        "monthly_profiles": profiles["monthly_profile"],
        "annual_solar_per_kw": profiles["annual_solar_per_kw"],
        "annual_wind_per_kw": profiles["annual_wind_per_kw"],
        "optimisation": result,
        "consumption_monthly_kwh": consumption,
        "consumption_before_insulation_monthly_kwh": consumption_raw,
        "annual_demand_before_insulation_kwh": round(annual_demand_before_insulation, 1),
        "annual_demand_after_insulation_kwh": round(annual_demand_after_insulation, 1),
        "insulation_r_value": insulation_r_value,
        "heating_fraction": heating_fraction,
    }
