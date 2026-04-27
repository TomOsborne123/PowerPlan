"""
Energy balancing: location (lat/lon) + solar/wind capacity + generation-type params
→ daily flux from weather API and daily solar/wind generation (no month scaling).
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Any, Literal

import pandas as pd

__all__ = [
    "get_flux_daily",
    "get_flux_monthly_last_year",
    "get_generation",
    "get_optimised_system",
    "optimize_system_capacity",
    "evaluate_fixed_capacities",
    "demand_after_insulation_and_heat_pump",
    "DEFAULT_PRICING",
]

# Default pricing for sizing and financials (£)
DEFAULT_PRICING = {
    "solar_capex_per_kw": 1500.0,
    "wind_capex_per_kw": 2500.0,
    "battery_capex_per_kwh": 800.0,
    "grid_price_per_kwh": 0.25,
    "export_price_per_kwh": 0.05,
}

# Battery defaults (used when no tier params supplied)
DEFAULT_BATTERY = {
    "round_trip_efficiency": 0.90,
    "depth_of_discharge": 0.90,
    "cycles_per_day": 0.85,
    "battery_capex_per_kwh": DEFAULT_PRICING["battery_capex_per_kwh"],
}

# Intraday mismatch factors (fraction of monthly self-consumption that is, in reality,
# time-shifted across the day and would otherwise become export+later-import without storage).
# Solar peaks midday → high mismatch with evening loads; wind is spread → lower mismatch.
INTRADAY_MISMATCH_SOLAR = 0.45
INTRADAY_MISMATCH_WIND = 0.20

# Insulation: R-value (m²·K/W). Heating demand is reduced by _insulation_reduction(r_value).
# Typical UK: uninsulated wall ~2, well insulated ~5. Scale chosen so e.g. R=5 → ~40% heating reduction.
INSULATION_R_VALUE_SCALE = 12.0  # R-value at which heating reduction reaches cap
INSULATION_MAX_REDUCTION = 0.5   # cap heating demand reduction at 50%


def _default_dates() -> tuple[str, str]:
    """Default to last 7 days (past) so flux data is non-null; forecast API often returns null for future days."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _insulation_reduction(r_value: float) -> float:
    """
    Fraction of space-heating demand saved by insulation (0 = none, up to INSULATION_MAX_REDUCTION).
    r_value: insulation R-value in m²·K/W (0 = no extra insulation).
    """
    if r_value <= 0:
        return 0.0
    return min(INSULATION_MAX_REDUCTION, r_value / INSULATION_R_VALUE_SCALE)


def demand_after_insulation_and_heat_pump(
    annual_consumption_kwh: float,
    heating_fraction: float,
    insulation_r_value: float = 0.0,
    heat_pump_cop: float = 1.0,
) -> dict[str, float]:
    """
    Adjust annual demand for insulation (reduces heating demand) and heat pump (reduces electricity for heating).

    heating_fraction: share of annual_consumption that is space heating (0–1).
    insulation_r_value: m²·K/W; 0 = no extra insulation.
    heat_pump_cop: coefficient of performance; 1.0 = electric heating, 2.5–3.5 typical for ASHP.

    Returns dict with: annual_demand_before_kwh, heating_demand_after_insulation_kwh,
        annual_demand_after_insulation_kwh (before heat pump COP conversion),
        electricity_demand_for_optimisation_kwh (final demand used for sizing solar/wind).
    """
    non_heating = annual_consumption_kwh * (1.0 - heating_fraction)
    heating_raw = annual_consumption_kwh * heating_fraction
    reduction = _insulation_reduction(insulation_r_value)
    heating_after_insulation = heating_raw * (1.0 - reduction)
    cop = max(1.0, float(heat_pump_cop))
    electricity_for_heating = heating_after_insulation / cop
    demand_for_optimisation = non_heating + electricity_for_heating
    return {
        "annual_demand_before_kwh": annual_consumption_kwh,
        "heating_demand_after_insulation_kwh": heating_after_insulation,
        # "Usage adjusted" for display: total after insulation (but before dividing by COP)
        "annual_demand_after_insulation_kwh": non_heating + heating_after_insulation,
        "electricity_demand_for_optimisation_kwh": demand_for_optimisation,
    }


def _wind_power_curve(
    v: float,
    v_cut_in: float,
    v_rated: float,
    v_cut_out: float,
    k: float,
) -> float:
    """Capacity factor per kW: 0 below cut-in, scaled between cut-in and rated, 1.0 at rated, 0 above cut-out."""
    if v < v_cut_in or v >= v_cut_out:
        return 0.0
    if v >= v_rated:
        return 1.0
    return ((v - v_cut_in) / (v_rated - v_cut_in)) ** k


def get_flux_daily(
    lat: float,
    lon: float,
    start_date: str | None = None,
    end_date: str | None = None,
    use_archive: bool = True,
) -> pd.DataFrame:
    """
    Fetch daily solar and wind flux for a location from the weather API.
    Defaults to the last 7 days (past) and uses the Historical API so data is non-null.
    Returns DataFrame with date index and columns: ghi_mj_per_m2, wind_speed_10m_max.
    """
    from src.api.get_weather import get_weather

    start_date = start_date or _default_dates()[0]
    end_date = end_date or _default_dates()[1]
    variables = [
        "shortwave_radiation_sum",
        "wind_speed_10m_max",
    ]
    df = get_weather(
        latitude=lat,
        longitude=lon,
        start_date=start_date,
        end_date=end_date,
        variables=variables,
        frequency="daily",
        use_archive=use_archive,
    )
    # Open-Meteo daily shortwave_radiation_sum is in MJ/m² (megajoules per m²)
    df = df.rename(columns={"shortwave_radiation_sum": "ghi_mj_per_m2"})
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date")
    return df


def get_flux_monthly_last_year(lat: float, lon: float) -> pd.DataFrame:
    """
    Fetch last calendar year's weather from the Historical API, aggregated by month (12 rows).
    Returns DataFrame with index month (1–12) and columns: ghi_mj_per_m2 (monthly sum, MJ/m²),
    wind_speed_10m_max (monthly mean, m/s), days_in_month.
    Used by optimisation when flux_source='last_year_monthly'.
    """
    from src.api.get_weather import get_weather_last_year_monthly

    monthly = get_weather_last_year_monthly(
        lat, lon,
        variables=["shortwave_radiation_sum", "wind_speed_10m_max"],
    )
    last_year = datetime.utcnow().year - 1
    monthly = monthly.rename(columns={"shortwave_radiation_sum": "ghi_mj_per_m2"})
    monthly["days_in_month"] = [calendar.monthrange(last_year, m)[1] for m in monthly.index]
    return monthly


def _daily_solar_kwh(
    ghi_mj_per_m2: float,
    capacity_kw: float,
    solar_type_params: dict[str, Any],
) -> float:
    """Daily solar energy (kWh) from daily GHI sum (MJ/m², Open-Meteo convention), capacity (kW), and type params."""
    if capacity_kw <= 0 or ghi_mj_per_m2 != ghi_mj_per_m2 or ghi_mj_per_m2 <= 0:
        return 0.0  # NaN check: x != x is True for NaN
    # GHI MJ/m² → kWh/m² (1 MJ = 1/3.6 kWh)
    ghi_kwh_m2 = ghi_mj_per_m2 / 3.6
    losses = solar_type_params.get("system_losses", 0.14)
    inv_eff = solar_type_params.get("inverter_efficiency", 0.96)
    pdc0 = solar_type_params.get("pdc0_per_kwp", 1000.0)
    # kWh = capacity_kw * (kWh/m²) * (W/kWp at STC) / 1000 * (1 - losses) * inv_eff
    # At 1000 W/m², 1 kWp gives 1 kW; at ghi_kwh_m2 we get ghi_kwh_m2 * 1 * (1-losses)*inv
    return capacity_kw * ghi_kwh_m2 * (pdc0 / 1000.0) * (1.0 - losses) * inv_eff


def _daily_wind_kwh(
    wind_speed_mps: float,
    capacity_kw: float,
    wind_type_params: dict[str, Any],
) -> float:
    """Daily wind energy (kWh) from daily wind speed (m/s), capacity (kW), and type params."""
    if capacity_kw <= 0 or wind_speed_mps != wind_speed_mps:
        return 0.0  # NaN check
    v_ci = wind_type_params["v_cut_in"]
    v_r = wind_type_params["v_rated"]
    v_co = wind_type_params["v_cut_out"]
    k = wind_type_params["power_exponent"]
    cf = _wind_power_curve(float(wind_speed_mps), v_ci, v_r, v_co, k)
    return capacity_kw * cf * 24.0


def get_generation(
    latitude: float,
    longitude: float,
    solar_capacity_kw: float,
    wind_capacity_kw: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Get daily solar and wind generation for a location and capacity.

    Inputs:
        latitude, longitude: location
        solar_capacity_kw, wind_capacity_kw: system capacities (kW)
        solar_type_params, wind_type_params: generation-type dicts (e.g. from src.data.energy_tiers.SOLAR_TIERS["budget"])
        start_date, end_date: optional date range (default: next 7 days)

    Returns:
        DataFrame with date index and columns: ghi_mj_per_m2, wind_speed_10m_max,
        solar_gen_kwh, wind_gen_kwh, total_gen_kwh. (ghi_mj_per_m2 = daily GHI in MJ/m².)
    """
    flux = get_flux_daily(latitude, longitude, start_date, end_date)
    flux = flux.copy()
    flux["solar_gen_kwh"] = flux["ghi_mj_per_m2"].fillna(0).map(
        lambda g: _daily_solar_kwh(g, solar_capacity_kw, solar_type_params)
    )
    flux["wind_gen_kwh"] = flux["wind_speed_10m_max"].fillna(0).map(
        lambda v: _daily_wind_kwh(v, wind_capacity_kw, wind_type_params)
    )
    flux["total_gen_kwh"] = flux["solar_gen_kwh"] + flux["wind_gen_kwh"]
    return flux


def _annual_generation_from_flux(
    flux: pd.DataFrame,
    solar_capacity_kw: float,
    wind_capacity_kw: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
) -> tuple[float, float]:
    """
    From daily flux, compute annualised solar and wind generation (kWh).
    Annualises using 365 / period_days (period = length of flux).
    Returns (annual_solar_kwh, annual_wind_kwh).
    """
    period_days = len(flux)
    if period_days <= 0:
        return 0.0, 0.0
    flux = flux.copy()
    flux["solar_gen_kwh"] = flux["ghi_mj_per_m2"].fillna(0).map(
        lambda g: _daily_solar_kwh(g, solar_capacity_kw, solar_type_params)
    )
    flux["wind_gen_kwh"] = flux["wind_speed_10m_max"].fillna(0).map(
        lambda v: _daily_wind_kwh(v, wind_capacity_kw, wind_type_params)
    )
    period_solar = flux["solar_gen_kwh"].sum()
    period_wind = flux["wind_gen_kwh"].sum()
    scale = 365.0 / period_days
    return period_solar * scale, period_wind * scale


def _annual_generation_from_flux_monthly(
    flux_monthly: pd.DataFrame,
    solar_capacity_kw: float,
    wind_capacity_kw: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
) -> tuple[float, float]:
    """
    From monthly flux (12 rows: index month 1–12, columns ghi_mj_per_m2, wind_speed_10m_max, days_in_month),
    compute annual solar and wind generation (kWh). No scaling; full year of data.
    Returns (annual_solar_kwh, annual_wind_kwh).
    """
    if len(flux_monthly) != 12 or "days_in_month" not in flux_monthly.columns:
        return 0.0, 0.0
    annual_solar = 0.0
    annual_wind = 0.0
    for month in flux_monthly.index:
        ghi_mj = float(flux_monthly.loc[month, "ghi_mj_per_m2"])
        wind_mps = float(flux_monthly.loc[month, "wind_speed_10m_max"])
        days = int(flux_monthly.loc[month, "days_in_month"])
        if ghi_mj != ghi_mj or ghi_mj < 0:
            ghi_mj = 0.0  # NaN or invalid
        if wind_mps != wind_mps or wind_mps < 0:
            wind_mps = 0.0
        # Archive API may return monthly sum in J/m²; convert to MJ if value is very large
        if ghi_mj > 1e6:
            ghi_mj = ghi_mj / 1e6
        # Monthly GHI sum in MJ → monthly solar kWh (same formula as daily)
        annual_solar += _daily_solar_kwh(ghi_mj, solar_capacity_kw, solar_type_params)
        # Monthly mean wind speed → daily equivalent × days
        annual_wind += _daily_wind_kwh(wind_mps, wind_capacity_kw, wind_type_params) * days
    return annual_solar, annual_wind


# Month labels for monthly breakdown (Jan–Dec)
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _monthly_generation_breakdown(
    flux_monthly: pd.DataFrame,
    solar_capacity_kw: float,
    wind_capacity_kw: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
) -> tuple[list[float], list[float]]:
    """
    From monthly flux (12 rows), return (monthly_solar_kwh, monthly_wind_kwh) as lists of 12.
    """
    if len(flux_monthly) != 12 or "days_in_month" not in flux_monthly.columns:
        return [0.0] * 12, [0.0] * 12
    solar_list: list[float] = []
    wind_list: list[float] = []
    for month in flux_monthly.index:
        ghi_mj = float(flux_monthly.loc[month, "ghi_mj_per_m2"])
        wind_mps = float(flux_monthly.loc[month, "wind_speed_10m_max"])
        days = int(flux_monthly.loc[month, "days_in_month"])
        if ghi_mj != ghi_mj or ghi_mj < 0:
            ghi_mj = 0.0
        if wind_mps != wind_mps or wind_mps < 0:
            wind_mps = 0.0
        if ghi_mj > 1e6:
            ghi_mj = ghi_mj / 1e6
        solar_list.append(_daily_solar_kwh(ghi_mj, solar_capacity_kw, solar_type_params))
        wind_list.append(_daily_wind_kwh(wind_mps, wind_capacity_kw, wind_type_params) * days)
    return solar_list, wind_list


def _battery_adjusted_monthly_balance(
    monthly_solar_kwh: list[float],
    monthly_wind_kwh: list[float],
    monthly_demand_kwh: list[float],
    days_in_month: list[int],
    battery_kwh: float,
    battery_params: dict[str, Any] | None,
) -> tuple[list[float], list[float], float, float]:
    """
    Apply intraday mismatch + battery time-shifting to a 12-month gen/demand schedule.

    Returns (monthly_import_kwh, monthly_export_kwh, annual_import, annual_export).

    Model:
      - The monthly "perfect match" assumption hides intraday mismatch, so we add back
        a realistic export+import pair scaled by INTRADAY_MISMATCH_SOLAR/WIND on the
        self-consumed portion (solar generates by day, typical demand peaks evening).
      - A battery (size B kWh) shifts up to (B × DoD × cycles/day × days_in_month) kWh
        per month from would-be export back to would-be import, with round-trip eff η.
    """
    bp = battery_params or {}
    eta = float(bp.get("round_trip_efficiency", 0.0)) if battery_kwh > 0 else 0.0
    dod = float(bp.get("depth_of_discharge", 0.0)) if battery_kwh > 0 else 0.0
    cycles_per_day = float(bp.get("cycles_per_day", 0.0)) if battery_kwh > 0 else 0.0
    has_battery = battery_kwh > 0 and eta > 0 and dod > 0 and cycles_per_day > 0

    monthly_import: list[float] = []
    monthly_export: list[float] = []
    for i in range(12):
        gen = max(0.0, monthly_solar_kwh[i] + monthly_wind_kwh[i])
        demand = max(0.0, monthly_demand_kwh[i])
        solar = max(0.0, monthly_solar_kwh[i])
        wind = max(0.0, monthly_wind_kwh[i])

        # Net monthly imbalance under the perfect-match assumption
        net_export = max(0.0, gen - demand)
        net_import = max(0.0, demand - gen)

        # Intraday mismatch: a slice of the would-be-self-consumed energy is exported by
        # day and replaced by import at night, even when the month is net-balanced.
        matched = min(gen, demand)
        if gen > 0:
            intraday_factor = (
                INTRADAY_MISMATCH_SOLAR * (solar / gen)
                + INTRADAY_MISMATCH_WIND * (wind / gen)
            )
        else:
            intraday_factor = 0.0
        intraday_pair = matched * intraday_factor

        realistic_export = net_export + intraday_pair
        realistic_import = net_import + intraday_pair

        if has_battery:
            # Throughput at the load side (energy delivered from battery to home, kWh)
            throughput_to_load = battery_kwh * dod * cycles_per_day * float(days_in_month[i])
            # We can shift at most (export × η) kWh from gen-to-load; capped by import + throughput
            charge_available = realistic_export * eta
            shift_to_load = min(realistic_import, charge_available, throughput_to_load)
            new_import = realistic_import - shift_to_load
            new_export = realistic_export - (shift_to_load / eta if eta > 0 else 0.0)
            new_export = max(0.0, new_export)
            new_import = max(0.0, new_import)
        else:
            new_import = realistic_import
            new_export = realistic_export

        monthly_import.append(new_import)
        monthly_export.append(new_export)

    return monthly_import, monthly_export, sum(monthly_import), sum(monthly_export)


def _battery_adjusted_annual_balance(
    annual_solar_kwh: float,
    annual_wind_kwh: float,
    annual_demand_kwh: float,
    battery_kwh: float,
    battery_params: dict[str, Any] | None,
) -> tuple[float, float]:
    """
    Daily-flux fallback: collapse the year into a single bucket scaled to 365 days
    and apply the same intraday-mismatch + battery-shift model. Returns (import, export).
    """
    monthly_solar = [annual_solar_kwh / 12.0] * 12
    monthly_wind = [annual_wind_kwh / 12.0] * 12
    monthly_demand = [annual_demand_kwh / 12.0] * 12
    days = [30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 35]  # ~365
    _, _, ann_imp, ann_exp = _battery_adjusted_monthly_balance(
        monthly_solar, monthly_wind, monthly_demand, days, battery_kwh, battery_params
    )
    return ann_imp, ann_exp


def optimize_system_capacity(
    flux: pd.DataFrame,
    annual_consumption_kwh: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
    solar_capex_per_kw: float = DEFAULT_PRICING["solar_capex_per_kw"],
    wind_capex_per_kw: float = DEFAULT_PRICING["wind_capex_per_kw"],
    grid_price_per_kwh: float = DEFAULT_PRICING["grid_price_per_kwh"],
    export_price_per_kwh: float = DEFAULT_PRICING["export_price_per_kwh"],
    solar_max_kw: float = 20.0,
    wind_max_kw: float = 10.0,
    step_kw: float = 0.5,
    optimize_over_years: float = 5.0,
    flux_frequency: Literal["daily", "monthly"] | None = None,
    min_demand_met_from_gen_pct: float = 50.0,
    min_solar_kw: float = 0.0,
    min_wind_kw: float = 0.5,
    monthly_demand_kwh: list[float] | None = None,
    battery_type_params: dict[str, Any] | None = None,
    battery_capex_per_kwh: float = DEFAULT_PRICING["battery_capex_per_kwh"],
    battery_max_kwh: float = 0.0,
    battery_min_kwh: float = 0.0,
    battery_step_kwh: float = 1.0,
) -> dict[str, Any]:
    """
    Find solar/wind/battery sizing that minimises total cost over `optimize_over_years`.
    Flux can be daily (short period, then annualised) or monthly (12 rows from last year, no scaling).
    Demand is annual_consumption_kwh.
    min_demand_met_from_gen_pct: require at least this % of demand from own generation (0–100);
        avoids choosing 0 kW when grid-only is cheapest.
    min_solar_kw, min_wind_kw: only consider solutions with at least this much solar/wind (default 0.5 kW wind).
    battery_type_params: tier params dict (round_trip_efficiency, depth_of_discharge,
        cycles_per_day) — when None or battery_max_kwh<=0, battery sweep is skipped.
    battery_max_kwh, battery_min_kwh, battery_step_kwh: usable battery size search bounds.

    Returns dict with optimal_solar_kw, optimal_wind_kw, optimal_battery_kwh,
    annual_demand_kwh, annual_generation_kwh, demand_met_from_generation_pct, capex
    (and component capex), annual_import_kwh, annual_export_kwh, annual_net_opex,
    financials_0/5/10_year, and monthly_balance (DataFrame of solar/wind/demand/
    import/export by month when flux is monthly; None otherwise).
    """
    if flux_frequency is None:
        flux_frequency = (
            "monthly"
            if len(flux) == 12 and "days_in_month" in flux.columns
            else "daily"
        )
    if flux_frequency == "monthly":
        if len(flux) != 12 or "days_in_month" not in flux.columns:
            raise ValueError("monthly flux must have 12 rows and column 'days_in_month'")
        period_days = 365
    else:
        period_days = len(flux)
    if period_days <= 0:
        raise ValueError("flux must contain at least one day or 12 months")
    export_price = export_price_per_kwh

    # Pre-compute the demand schedule once (used for the monthly balance + battery model).
    if monthly_demand_kwh and len(monthly_demand_kwh) == 12 and sum(monthly_demand_kwh) > 0:
        scale = annual_consumption_kwh / float(sum(monthly_demand_kwh))
        demand_schedule = [float(x) * scale for x in monthly_demand_kwh]
    else:
        demand_schedule = [annual_consumption_kwh / 12.0] * 12
    if flux_frequency == "monthly" and len(flux) == 12 and "days_in_month" in flux.columns:
        days_schedule = [int(flux.loc[m, "days_in_month"]) for m in flux.index]
    else:
        days_schedule = [30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 35]

    def annual_gen(solar_kw: float, wind_kw: float) -> tuple[float, float]:
        if flux_frequency == "monthly":
            return _annual_generation_from_flux_monthly(
                flux, solar_kw, wind_kw, solar_type_params, wind_type_params
            )
        return _annual_generation_from_flux(
            flux, solar_kw, wind_kw, solar_type_params, wind_type_params
        )

    def annual_balance_with_battery(
        solar_kw: float, wind_kw: float, battery_kwh: float
    ) -> tuple[float, float, float, float, float]:
        """Returns (annual_solar, annual_wind, total_gen, annual_import, annual_export)."""
        if flux_frequency == "monthly":
            monthly_solar, monthly_wind = _monthly_generation_breakdown(
                flux, solar_kw, wind_kw, solar_type_params, wind_type_params
            )
            ann_solar = sum(monthly_solar)
            ann_wind = sum(monthly_wind)
            _, _, ann_imp, ann_exp = _battery_adjusted_monthly_balance(
                monthly_solar, monthly_wind, demand_schedule, days_schedule,
                battery_kwh, battery_type_params,
            )
        else:
            ann_solar, ann_wind = _annual_generation_from_flux(
                flux, solar_kw, wind_kw, solar_type_params, wind_type_params
            )
            ann_imp, ann_exp = _battery_adjusted_annual_balance(
                ann_solar, ann_wind, annual_consumption_kwh, battery_kwh, battery_type_params,
            )
        return ann_solar, ann_wind, ann_solar + ann_wind, ann_imp, ann_exp

    # Battery sweep range — clamped to non-negative and at least one point at 0.
    bat_max = max(0.0, float(battery_max_kwh))
    bat_min = max(0.0, float(battery_min_kwh))
    bat_step = max(0.1, float(battery_step_kwh))
    if bat_max < bat_min:
        bat_max = bat_min

    best_total_cost: float = float("inf")
    best_solar = 0.0
    best_wind = 0.0
    best_battery = 0.0
    best_annual_import = 0.0
    best_annual_export = 0.0
    best_annual_gen = 0.0
    best_annual_solar = 0.0
    best_annual_wind = 0.0

    solar_kw = min_solar_kw
    while solar_kw <= solar_max_kw:
        wind_kw = min_wind_kw
        while wind_kw <= wind_max_kw:
            total_annual_gen_only = sum(annual_gen(solar_kw, wind_kw))
            demand_met_pct = (total_annual_gen_only / annual_consumption_kwh * 100.0) if annual_consumption_kwh > 0 else 0.0
            if min_demand_met_from_gen_pct > 0 and demand_met_pct < min_demand_met_from_gen_pct:
                wind_kw += step_kw
                if wind_kw > wind_max_kw:
                    break
                continue
            battery_kwh = bat_min
            while battery_kwh <= bat_max:
                annual_solar, annual_wind, total_annual_gen, annual_import, annual_export = (
                    annual_balance_with_battery(solar_kw, wind_kw, battery_kwh)
                )
                capex = (
                    solar_kw * solar_capex_per_kw
                    + wind_kw * wind_capex_per_kw
                    + battery_kwh * battery_capex_per_kwh
                )
                annual_opex_import = annual_import * grid_price_per_kwh
                annual_opex_export_revenue = annual_export * export_price
                annual_net_opex = annual_opex_import - annual_opex_export_revenue
                total_cost = capex + annual_net_opex * optimize_over_years
                if total_cost < best_total_cost:
                    best_total_cost = total_cost
                    best_solar = solar_kw
                    best_wind = wind_kw
                    best_battery = battery_kwh
                    best_annual_import = annual_import
                    best_annual_export = annual_export
                    best_annual_gen = total_annual_gen
                    best_annual_solar = annual_solar
                    best_annual_wind = annual_wind
                if bat_max <= 0:
                    break
                battery_kwh += bat_step
                if battery_kwh > bat_max:
                    break
            wind_kw += step_kw
            if wind_kw > wind_max_kw:
                break
        solar_kw += step_kw
        if solar_kw > solar_max_kw:
            break

    solar_capex = best_solar * solar_capex_per_kw
    wind_capex = best_wind * wind_capex_per_kw
    battery_capex = best_battery * battery_capex_per_kwh
    capex = solar_capex + wind_capex + battery_capex
    opex_import = best_annual_import * grid_price_per_kwh
    opex_export_revenue = best_annual_export * export_price
    annual_net_opex = opex_import - opex_export_revenue
    demand_met_pct = (best_annual_gen / annual_consumption_kwh * 100.0) if annual_consumption_kwh > 0 else 0.0

    # Payback: per-technology capex recovered by its annual savings (import offset + export revenue)
    total_export = best_annual_export
    if best_annual_gen > 0:
        solar_share = best_annual_solar / best_annual_gen
        wind_share = best_annual_wind / best_annual_gen
    else:
        solar_share = wind_share = 0.0
    used_on_site = min(best_annual_gen, annual_consumption_kwh)
    solar_used = used_on_site * solar_share
    solar_exported = total_export * solar_share
    wind_used = used_on_site * wind_share
    wind_exported = total_export * wind_share
    annual_solar_savings = solar_used * grid_price_per_kwh + solar_exported * export_price
    annual_wind_savings = wind_used * grid_price_per_kwh + wind_exported * export_price
    payback_solar_years = round(solar_capex / annual_solar_savings, 1) if (solar_capex > 0 and annual_solar_savings > 0) else None
    payback_wind_years = round(wind_capex / annual_wind_savings, 1) if (wind_capex > 0 and annual_wind_savings > 0) else None

    # Battery payback: compare annual opex with vs without battery at fixed solar/wind
    payback_battery_years: float | None = None
    if battery_capex > 0 and best_battery > 0:
        if flux_frequency == "monthly":
            ms, mw = _monthly_generation_breakdown(
                flux, best_solar, best_wind, solar_type_params, wind_type_params
            )
            _, _, imp_no_bat, exp_no_bat = _battery_adjusted_monthly_balance(
                ms, mw, demand_schedule, days_schedule, 0.0, battery_type_params,
            )
        else:
            imp_no_bat, exp_no_bat = _battery_adjusted_annual_balance(
                best_annual_solar, best_annual_wind, annual_consumption_kwh,
                0.0, battery_type_params,
            )
        opex_no_bat = imp_no_bat * grid_price_per_kwh - exp_no_bat * export_price
        annual_battery_savings = opex_no_bat - annual_net_opex
        if annual_battery_savings > 0:
            payback_battery_years = round(battery_capex / annual_battery_savings, 1)

    # Monthly breakdown over the year (when we have monthly flux) for exploring solar vs wind by month
    monthly_balance: pd.DataFrame | None = None
    if flux_frequency == "monthly" and len(flux) == 12:
        monthly_solar, monthly_wind = _monthly_generation_breakdown(
            flux, best_solar, best_wind, solar_type_params, wind_type_params
        )
        monthly_demand = demand_schedule
        monthly_import_b, monthly_export_b, _, _ = _battery_adjusted_monthly_balance(
            monthly_solar, monthly_wind, monthly_demand, days_schedule,
            best_battery, battery_type_params,
        )
        monthly_balance = pd.DataFrame({
            "month": MONTH_LABELS,
            "solar_kwh": [round(x, 1) for x in monthly_solar],
            "wind_kwh": [round(x, 1) for x in monthly_wind],
            "total_gen_kwh": [round(monthly_solar[i] + monthly_wind[i], 1) for i in range(12)],
            "demand_kwh": [round(monthly_demand[i], 1) for i in range(12)],
            "import_kwh": [round(monthly_import_b[i], 1) for i in range(12)],
            "export_kwh": [round(monthly_export_b[i], 1) for i in range(12)],
        })

    def _financials(n_years: float) -> dict[str, float]:
        opex_total = annual_net_opex * n_years
        return {
            "capex": round(capex, 2),
            "opex_total": round(opex_total, 2),
            "total": round(capex + opex_total, 2),
        }

    return {
        "optimal_solar_kw": round(best_solar, 2),
        "optimal_wind_kw": round(best_wind, 2),
        "optimal_battery_kwh": round(best_battery, 2),
        "total_capacity_kw": round(best_solar + best_wind, 2),
        "annual_demand_kwh": round(annual_consumption_kwh, 1),
        "annual_generation_kwh": round(best_annual_gen, 1),
        "annual_solar_generation_kwh": round(best_annual_solar, 1),
        "annual_wind_generation_kwh": round(best_annual_wind, 1),
        "annual_import_kwh": round(best_annual_import, 1),
        "annual_export_kwh": round(best_annual_export, 1),
        "demand_met_from_generation_pct": round(demand_met_pct, 1),
        "capex": round(capex, 2),
        "solar_capex": round(solar_capex, 2),
        "wind_capex": round(wind_capex, 2),
        "battery_capex": round(battery_capex, 2),
        "annual_net_opex": round(annual_net_opex, 2),
        "payback_solar_years": payback_solar_years,
        "payback_wind_years": payback_wind_years,
        "payback_battery_years": payback_battery_years,
        "financials_0_year": _financials(0),
        "financials_5_year": _financials(5),
        "financials_10_year": _financials(10),
        "period_days": period_days,
        "monthly_balance": monthly_balance,
    }


def evaluate_fixed_capacities(
    latitude: float,
    longitude: float,
    annual_consumption_kwh: float,
    heating_fraction: float,
    insulation_r_value: float,
    heat_pump_cop: float,
    solar_kw: float,
    wind_kw: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
    *,
    flux_source: Literal["forecast", "last_year_monthly"] = "last_year_monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    battery_kwh: float = 0.0,
    battery_type_params: dict[str, Any] | None = None,
    battery_capex_per_kwh: float = DEFAULT_PRICING["battery_capex_per_kwh"],
) -> dict[str, float]:
    """
    Annual import/export and capex for fixed solar/wind/battery sizes (no optimisation).
    Uses the same demand model as get_optimised_system and weather flux for generation.
    """
    demand_adj = demand_after_insulation_and_heat_pump(
        annual_consumption_kwh,
        heating_fraction,
        insulation_r_value,
        heat_pump_cop,
    )
    demand_for_optimisation = float(demand_adj["electricity_demand_for_optimisation_kwh"])

    if flux_source == "last_year_monthly":
        flux = get_flux_monthly_last_year(latitude, longitude)
        flux_frequency: Literal["daily", "monthly"] = "monthly"
    else:
        if start_date is None or end_date is None:
            start_date = datetime.utcnow().date().isoformat()
            end_date = (datetime.utcnow().date() + timedelta(days=6)).isoformat()
        flux = get_flux_daily(latitude, longitude, start_date, end_date, use_archive=False)
        flux_frequency = "daily"

    sk = max(0.0, float(solar_kw))
    wk = max(0.0, float(wind_kw))
    bk = max(0.0, float(battery_kwh))
    if flux_frequency == "monthly":
        ms, mw = _monthly_generation_breakdown(
            flux, sk, wk, solar_type_params, wind_type_params
        )
        annual_solar = sum(ms)
        annual_wind = sum(mw)
        days_schedule = [int(flux.loc[m, "days_in_month"]) for m in flux.index]
        demand_schedule = [demand_for_optimisation / 12.0] * 12
        _, _, annual_import, annual_export = _battery_adjusted_monthly_balance(
            ms, mw, demand_schedule, days_schedule, bk, battery_type_params,
        )
    else:
        annual_solar, annual_wind = _annual_generation_from_flux(
            flux, sk, wk, solar_type_params, wind_type_params
        )
        annual_import, annual_export = _battery_adjusted_annual_balance(
            annual_solar, annual_wind, demand_for_optimisation, bk, battery_type_params,
        )
    total_gen = annual_solar + annual_wind
    solar_capex_per_kw = float(solar_type_params.get("solar_capex_per_kw", DEFAULT_PRICING["solar_capex_per_kw"]))
    wind_capex_per_kw = float(wind_type_params.get("wind_capex_per_kw", DEFAULT_PRICING["wind_capex_per_kw"]))
    bat_capex_per_kwh = float((battery_type_params or {}).get("battery_capex_per_kwh", battery_capex_per_kwh))
    capex = sk * solar_capex_per_kw + wk * wind_capex_per_kw + bk * bat_capex_per_kwh
    return {
        "annual_demand_kwh": round(demand_for_optimisation, 1),
        "annual_import_kwh": round(annual_import, 1),
        "annual_export_kwh": round(annual_export, 1),
        "annual_generation_kwh": round(total_gen, 1),
        "solar_kw": round(sk, 2),
        "wind_kw": round(wk, 2),
        "battery_kwh": round(bk, 2),
        "capex_gbp": round(capex, 2),
        "insulation_r_value": float(insulation_r_value),
    }


def get_optimised_system(
    latitude: float,
    longitude: float,
    annual_consumption_kwh: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
    pricing: dict[str, float] | None = None,
    solar_max_kw: float = 20.0,
    wind_max_kw: float = 10.0,
    step_kw: float = 0.5,
    optimize_over_years: float = 5.0,
    start_date: str | None = None,
    end_date: str | None = None,
    flux_source: Literal["forecast", "last_year_monthly"] = "last_year_monthly",
    min_demand_met_from_gen_pct: float = 50.0,
    min_solar_kw: float = 0.0,
    min_wind_kw: float = 0.5,
    heating_fraction: float = 0.6,
    insulation_r_value: float = 0.0,
    heat_pump_cop: float = 1.0,
    battery_type_params: dict[str, Any] | None = None,
    battery_max_kwh: float = 0.0,
    battery_min_kwh: float = 0.0,
    battery_step_kwh: float = 1.0,
) -> dict[str, Any]:
    """
    Size and price a solar/wind/battery system for a location and annual demand.
    Flux can be from a short forecast (daily, then annualised) or from last year's
    monthly historical data (12 months, no scaling).
    Demand can be reduced by insulation (lower heating demand) and heat pump (less electricity per unit heat).

    Inputs:
        latitude, longitude: location
        annual_consumption_kwh: annual energy demand (kWh) before insulation/heat-pump adjustment
        solar_type_params, wind_type_params: from src.data.energy_tiers (e.g. SOLAR_TIERS["budget"])
        pricing: optional override for solar_capex_per_kw, wind_capex_per_kw, grid_price_per_kwh, export_price_per_kwh
        solar_max_kw, wind_max_kw, step_kw: search range for optimisation
        optimize_over_years: minimise total cost over this many years (e.g. 5)
        start_date, end_date: used only when flux_source='forecast' (default: next 7 days)
        flux_source: 'last_year_monthly' = use Historical API last year aggregated by month (default);
                     'forecast' = use short daily forecast and annualise
        min_demand_met_from_gen_pct: require at least this % of demand from solar/wind (default 50);
             set to 0 to allow 0 kW (grid-only) if cheapest.
        min_solar_kw, min_wind_kw: only consider solutions with at least this much solar/wind (default min_wind_kw=0.5).
        heating_fraction: share of annual_consumption that is space heating (0–1, default 0.6).
        insulation_r_value: insulation R-value in m²·K/W; 0 = no extra insulation (default).
        heat_pump_cop: heat pump COP; 1.0 = electric heating (default), 2.5–3.5 for ASHP (e.g. from HEAT_PUMP_TIERS).

    Returns:
        Dict with optimal_solar_kw, optimal_wind_kw, annual_demand_kwh (demand used for sizing),
        annual_demand_before_adjustments_kwh, heating_demand_after_insulation_kwh, heating_fraction, insulation_r_value, heat_pump_cop,
        financials_0_year, financials_5_year, financials_10_year, flux_source, flux_period_days, etc.
    """
    demand_adj = demand_after_insulation_and_heat_pump(
        annual_consumption_kwh,
        heating_fraction,
        insulation_r_value,
        heat_pump_cop,
    )
    demand_for_optimisation = demand_adj["electricity_demand_for_optimisation_kwh"]

    def _typical_monthly_profile_weights() -> tuple[list[float], list[float]]:
        """
        Return (non_heating_weights, heating_weights) for 12 months.

        - non_heating: fairly flat with mild winter uplift
        - heating: winter-peaked (captures typical UK space-heating seasonality)

        Both arrays are normalized so each sums to 1.0.
        """
        import math

        # winter_factor peaks in January (month 0) and bottoms in July (month 6)
        winter_factor = [0.5 + 0.5 * math.cos(2.0 * math.pi * (m / 12.0)) for m in range(12)]

        # Sharper winter peak for the heating component.
        heating_raw = [0.05 + 0.95 * (wf**1.5) for wf in winter_factor]
        non_heating_raw = [0.08 + 0.12 * wf for wf in winter_factor]

        heating_sum = sum(heating_raw) or 1.0
        non_heating_sum = sum(non_heating_raw) or 1.0

        heating_w = [x / heating_sum for x in heating_raw]
        non_heating_w = [x / non_heating_sum for x in non_heating_raw]
        return non_heating_w, heating_w

    non_heating_weights, heating_weights = _typical_monthly_profile_weights()

    # Split the *optimiser* electricity demand into non-heating and heating components.
    non_heating_electricity_kwh = annual_consumption_kwh * (1.0 - heating_fraction)
    heating_after_insulation_kwh = demand_adj["heating_demand_after_insulation_kwh"]
    cop = max(1.0, float(heat_pump_cop))
    heating_electricity_kwh = heating_after_insulation_kwh / cop

    # Build a seasonal monthly electricity demand profile for monthly import/export display.
    monthly_demand_kwh = [
        (non_heating_electricity_kwh * non_heating_weights[i]) + (heating_electricity_kwh * heating_weights[i])
        for i in range(12)
    ]
    if flux_source == "last_year_monthly":
        flux = get_flux_monthly_last_year(latitude, longitude)
        flux_frequency = "monthly"
    else:
        # Forecast path: use future dates and forecast API (use_archive=False)
        if start_date is None or end_date is None:
            start_date = datetime.utcnow().date().isoformat()
            end_date = (datetime.utcnow().date() + timedelta(days=6)).isoformat()
        flux = get_flux_daily(latitude, longitude, start_date, end_date, use_archive=False)
        flux_frequency = "daily"
    pr = {**DEFAULT_PRICING, **(pricing or {})}
    # If neither solar nor wind is allowed, the only feasible point is 0 kW / 0 kW; relax the
    # default min-% self-gen constraint so grid-only scoring still runs.
    _min_met_pct = float(min_demand_met_from_gen_pct)
    if max(0.0, float(solar_max_kw)) <= 0.0 and max(0.0, float(wind_max_kw)) <= 0.0:
        _min_met_pct = 0.0
    result = optimize_system_capacity(
        flux,
        demand_for_optimisation,
        solar_type_params,
        wind_type_params,
        solar_capex_per_kw=pr["solar_capex_per_kw"],
        wind_capex_per_kw=pr["wind_capex_per_kw"],
        grid_price_per_kwh=pr["grid_price_per_kwh"],
        export_price_per_kwh=pr["export_price_per_kwh"],
        solar_max_kw=solar_max_kw,
        wind_max_kw=wind_max_kw,
        step_kw=step_kw,
        optimize_over_years=optimize_over_years,
        flux_frequency=flux_frequency,
        min_demand_met_from_gen_pct=_min_met_pct,
        min_solar_kw=min_solar_kw,
        min_wind_kw=min_wind_kw,
        monthly_demand_kwh=monthly_demand_kwh if flux_frequency == "monthly" else None,
        battery_type_params=battery_type_params,
        battery_capex_per_kwh=float(
            (battery_type_params or {}).get(
                "battery_capex_per_kwh", pr.get("battery_capex_per_kwh", DEFAULT_PRICING["battery_capex_per_kwh"])
            )
        ),
        battery_max_kwh=battery_max_kwh,
        battery_min_kwh=battery_min_kwh,
        battery_step_kwh=battery_step_kwh,
    )
    result["flux_source"] = flux_source
    result["flux_period_days"] = result.pop("period_days")
    result["annual_demand_before_adjustments_kwh"] = round(demand_adj["annual_demand_before_kwh"], 1)
    result["heating_demand_after_insulation_kwh"] = round(demand_adj["heating_demand_after_insulation_kwh"], 1)
    result["annual_demand_after_insulation_kwh"] = round(demand_adj["annual_demand_after_insulation_kwh"], 1)
    result["heating_fraction"] = heating_fraction
    result["insulation_r_value"] = insulation_r_value
    result["heat_pump_cop"] = heat_pump_cop
    return result
