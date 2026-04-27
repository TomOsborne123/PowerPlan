"""
Tariff recommendation: combine energy balancing optimisation with scraped tariff data.
Runs optimisation once for the user's location and demand, then scores each tariff by
total cost (capex + import cost − export revenue + standing charge) over the chosen horizon.
"""

from __future__ import annotations

from typing import Any, Literal

from src.models.energy_balancing import get_optimised_system, DEFAULT_PRICING

__all__ = [
    "recommend_tariff",
    "tariff_to_pricing_dict",
    "coerce_unit_rate_pence_per_kwh",
    "coerce_standing_charge_pence_per_day",
]


def coerce_unit_rate_pence_per_kwh(raw: float) -> float:
    """
    Model expects pence per kWh (e.g. 24.5). Some sources store £/kWh (e.g. 0.245) without scaling.
    """
    v = float(raw or 0)
    if v <= 0:
        return 0.0
    if v < 2.0:
        return v * 100.0
    return v


def coerce_standing_charge_pence_per_day(raw: float) -> float:
    """
    Model expects pence per day (e.g. 51). A bare £/day value (e.g. 0.52) is sometimes stored as 0.52.
    """
    v = float(raw or 0)
    if v <= 0:
        return 0.0
    if v < 5.0:
        return v * 100.0
    return v


def tariff_to_pricing_dict(tariff: Any) -> dict[str, Any]:
    """
    Convert a Tariff object (from scraping) or dict to a normalized dict for costing.
    Handles both src.api.energyScraping.Tariff dataclass and plain dicts.
    """
    if hasattr(tariff, "unit_rate"):
        return {
            "unit_rate_p_per_kwh": coerce_unit_rate_pence_per_kwh(float(tariff.unit_rate)),
            "standing_charge_p_per_day": coerce_standing_charge_pence_per_day(float(tariff.standing_charge_day)),
            "supplier_name": getattr(tariff, "new_supplier_name", "") or getattr(tariff, "supplier_name", ""),
            "tariff_name": getattr(tariff, "tariff_name", "") or "",
            "is_green": bool(getattr(tariff, "is_green", False)),
            "annual_cost_new": float(getattr(tariff, "annual_cost_new", 0)),
        }
    if isinstance(tariff, dict):
        ur = float(tariff.get("unit_rate", tariff.get("unit_rate_p_per_kwh", 0)))
        sc = float(tariff.get("standing_charge_day", tariff.get("standing_charge_p_per_day", 0)))
        return {
            "unit_rate_p_per_kwh": coerce_unit_rate_pence_per_kwh(ur),
            "standing_charge_p_per_day": coerce_standing_charge_pence_per_day(sc),
            "supplier_name": str(tariff.get("new_supplier_name", tariff.get("supplier_name", ""))),
            "tariff_name": str(tariff.get("tariff_name", "")),
            "is_green": bool(tariff.get("is_green", False)),
            "annual_cost_new": float(tariff.get("annual_cost_new", 0)),
        }
    raise TypeError("tariff must be a Tariff-like object or dict with unit_rate and standing_charge_day")


def recommend_tariff(
    tariffs: list[Any],
    latitude: float,
    longitude: float,
    annual_consumption_kwh: float,
    solar_type_params: dict[str, Any],
    wind_type_params: dict[str, Any],
    *,
    export_price_per_kwh: float = 0.05,
    optimize_over_years: float = 5.0,
    flux_source: Literal["forecast", "last_year_monthly"] = "last_year_monthly",
    heating_fraction: float = 0.6,
    insulation_r_value: float = 0.0,
    heat_pump_cop: float = 1.0,
    solar_max_kw: float = 20.0,
    wind_max_kw: float = 10.0,
    min_solar_kw: float = 0.0,
    min_wind_kw: float = 0.5,
    battery_type_params: dict[str, Any] | None = None,
    battery_max_kwh: float = 0.0,
    battery_min_kwh: float = 0.0,
    battery_step_kwh: float = 1.0,
    prefer_green: bool = False,
) -> dict[str, Any]:
    """
    Recommend a tariff based on scraped options and optimal solar/wind sizing.

    Runs optimisation once (using first tariff's unit rate as reference grid price)
    to get optimal capacities and annual import/export. Then scores each tariff by
    total cost over `optimize_over_years`: capex + (import cost + standing charge − export revenue) × years.
    Returns the best tariff and a full ranking.

    Args:
        tariffs: List of Tariff objects (from scraping) or dicts with unit_rate (p/kWh),
                standing_charge_day (p/day), and optionally new_supplier_name, tariff_name, is_green.
        latitude, longitude: location (e.g. from postcode lookup or first tariff).
        annual_consumption_kwh: annual electricity demand (e.g. from user or first tariff's annual_electricity_kwh).
        solar_type_params, wind_type_params: from src.data.energy_tiers (SOLAR_TIERS, WIND_TIERS).
        export_price_per_kwh: export tariff in £/kWh (scraped data often omits this; default 5p).
        optimize_over_years: cost horizon in years (default 5).
        flux_source: 'last_year_monthly' or 'forecast' for weather data.
        heating_fraction, insulation_r_value, heat_pump_cop: demand adjustment for optimisation.
        solar_max_kw, wind_max_kw, min_solar_kw, min_wind_kw: optimisation search bounds.
        prefer_green: if True, among similar-cost tariffs prefer is_green (within 2% of best).

    Returns:
        Dict with:
          optimisation_result: full result from get_optimised_system.
          recommended_tariff: best tariff (normalized dict with supplier_name, tariff_name, unit_rate, etc.).
          ranking: list of dicts { tariff, total_cost_gbp, opex_per_year_gbp, rank } sorted by total cost.
          annual_import_kwh, annual_export_kwh, capex: from optimisation.
    """
    if not tariffs:
        return {
            "optimisation_result": None,
            "recommended_tariff": None,
            "ranking": [],
            "annual_import_kwh": 0.0,
            "annual_export_kwh": 0.0,
            "capex": 0.0,
            "error": "No tariffs provided",
        }

    # Normalize all tariffs to pricing dicts
    pricing_dicts = []
    for t in tariffs:
        try:
            pricing_dicts.append(tariff_to_pricing_dict(t))
        except (TypeError, KeyError):
            continue
    if not pricing_dicts:
        return {
            "optimisation_result": None,
            "recommended_tariff": None,
            "ranking": [],
            "annual_import_kwh": 0.0,
            "annual_export_kwh": 0.0,
            "capex": 0.0,
            "error": "No valid tariff data could be extracted",
        }

    # Use a tariff unit rate as reference grid price for the single optimisation run.
    # If scraped data is missing and unit_rate is 0 for the first tariff, the optimiser can pick solar=0.
    unit_rate_candidates_p = [p.get("unit_rate_p_per_kwh", 0) for p in pricing_dicts if float(p.get("unit_rate_p_per_kwh", 0) or 0) > 0]
    unit_rate_ref_p = unit_rate_candidates_p[0] if unit_rate_candidates_p else pricing_dicts[0].get("unit_rate_p_per_kwh", 0) or 0
    grid_price_ref = float(unit_rate_ref_p) / 100.0  # p -> £
    if grid_price_ref <= 0:
        grid_price_ref = float(DEFAULT_PRICING.get("grid_price_per_kwh", 0.25))

    solar_capex = float(
        solar_type_params.get("solar_capex_per_kw", DEFAULT_PRICING["solar_capex_per_kw"])
    )
    wind_capex = float(
        wind_type_params.get("wind_capex_per_kw", DEFAULT_PRICING["wind_capex_per_kw"])
    )
    battery_capex = float(
        (battery_type_params or {}).get(
            "battery_capex_per_kwh", DEFAULT_PRICING["battery_capex_per_kwh"]
        )
    )

    optimisation_result = get_optimised_system(
        latitude,
        longitude,
        annual_consumption_kwh,
        solar_type_params,
        wind_type_params,
        pricing={
            "grid_price_per_kwh": grid_price_ref,
            "export_price_per_kwh": export_price_per_kwh,
            "solar_capex_per_kw": solar_capex,
            "wind_capex_per_kw": wind_capex,
            "battery_capex_per_kwh": battery_capex,
        },
        solar_max_kw=solar_max_kw,
        wind_max_kw=wind_max_kw,
        optimize_over_years=optimize_over_years,
        flux_source=flux_source,
        min_solar_kw=min_solar_kw,
        min_wind_kw=min_wind_kw,
        heating_fraction=heating_fraction,
        insulation_r_value=insulation_r_value,
        heat_pump_cop=heat_pump_cop,
        battery_type_params=battery_type_params,
        battery_max_kwh=battery_max_kwh,
        battery_min_kwh=battery_min_kwh,
        battery_step_kwh=battery_step_kwh,
    )

    capex = optimisation_result["capex"]
    annual_import_kwh = optimisation_result["annual_import_kwh"]
    annual_export_kwh = optimisation_result["annual_export_kwh"]

    # Score each tariff: total cost over optimize_over_years
    def total_cost_gbp(p: dict) -> float:
        unit_rate_gbp = p["unit_rate_p_per_kwh"] / 100.0
        standing_charge_gbp_per_year = 365 * (p["standing_charge_p_per_day"] / 100.0)
        opex_per_year = (
            annual_import_kwh * unit_rate_gbp
            + standing_charge_gbp_per_year
            - annual_export_kwh * export_price_per_kwh
        )
        return capex + opex_per_year * optimize_over_years

    def opex_per_year_gbp(p: dict) -> float:
        unit_rate_gbp = p["unit_rate_p_per_kwh"] / 100.0
        standing_charge_gbp_per_year = 365 * (p["standing_charge_p_per_day"] / 100.0)
        return (
            annual_import_kwh * unit_rate_gbp
            + standing_charge_gbp_per_year
            - annual_export_kwh * export_price_per_kwh
        )

    scored = []
    for p in pricing_dicts:
        total = total_cost_gbp(p)
        opex = opex_per_year_gbp(p)
        scored.append({
            "tariff": p,
            "total_cost_gbp": round(total, 2),
            "opex_per_year_gbp": round(opex, 2),
        })
    scored.sort(key=lambda x: x["total_cost_gbp"])

    best_total = scored[0]["total_cost_gbp"] if scored else 0.0
    threshold_similar = best_total * 0.02  # 2% tolerance for "similar cost"

    if prefer_green and scored:
        # Among tariffs within 2% of best cost, prefer green
        similar = [s for s in scored if s["total_cost_gbp"] <= best_total + threshold_similar]
        green_options = [s for s in similar if s["tariff"].get("is_green")]
        if green_options:
            scored = green_options + [s for s in scored if s not in green_options and s not in similar]
            scored = sorted(scored, key=lambda x: (x["total_cost_gbp"], not x["tariff"].get("is_green")))

    for i, s in enumerate(scored, start=1):
        s["rank"] = i

    recommended = scored[0]["tariff"] if scored else None

    return {
        "optimisation_result": optimisation_result,
        "recommended_tariff": recommended,
        "ranking": scored,
        "annual_import_kwh": annual_import_kwh,
        "annual_export_kwh": annual_export_kwh,
        "capex": capex,
        "optimize_over_years": optimize_over_years,
        "export_price_per_kwh": export_price_per_kwh,
    }
