"""
Energy balancing model: lat/lon to solar and wind flux, then to energy options at different price tiers.
Uses pvlib for solar and an in-repo power-curve model for wind.
"""

from __future__ import annotations

import pandas as pd
from datetime import datetime, timedelta
from typing import Any

# Optional pvlib for solar
try:
    import pvlib
    from pvlib import solarposition, irradiance, temperature, pvsystem, inverter
    PVLIB_AVAILABLE = True
except ImportError:
    PVLIB_AVAILABLE = False

from src.api.get_weather import get_weather


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
