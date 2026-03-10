"""
Use scraped tariffs with the energy balancing optimisation to recommend a tariff.
Call after ScrapeTariff.scrape() to get a recommendation based on optimal solar/wind
and each tariff's unit rate and standing charge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass  # Tariff from same package

__all__ = ["recommend_after_scrape"]


def recommend_after_scrape(
    tariffs: list[Any],
    annual_consumption_kwh: float | None = None,
    solar_type_params: dict[str, Any] | None = None,
    wind_type_params: dict[str, Any] | None = None,
    *,
    export_price_per_kwh: float = 0.05,
    optimize_over_years: float = 5.0,
    prefer_green: bool = False,
    flux_source: str = "last_year_monthly",
    heating_fraction: float = 0.6,
    insulation_r_value: float = 0.0,
    heat_pump_cop: float = 1.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Recommend a tariff from scraped results using solar/wind optimisation.

    Uses first tariff for location (lat/lon) and, if not provided, annual_electricity_kwh.
    Loads solar/wind type params from energy_tiers if not provided.

    Args:
        tariffs: List of Tariff objects returned by ScrapeTariff.scrape().
        annual_consumption_kwh: Override annual electricity use; if None, uses first tariff's annual_electricity_kwh.
        solar_type_params, wind_type_params: From energy_tiers (SOLAR_TIERS, WIND_TIERS); if None, uses "budget".
        export_price_per_kwh: Export tariff £/kWh (default 5p).
        optimize_over_years: Cost horizon in years (default 5).
        prefer_green: Prefer green tariffs when cost is within 2% of best.
        flux_source, heating_fraction, insulation_r_value, heat_pump_cop: Passed to get_optimised_system.
        **kwargs: Further args for recommend_tariff (e.g. solar_max_kw, min_wind_kw).

    Returns:
        Result dict from recommend_tariff (optimisation_result, recommended_tariff, ranking, ...).
    """
    from src.models.tariff_recommendation import recommend_tariff
    from src.data.energy_tiers import SOLAR_TIERS, WIND_TIERS

    if not tariffs:
        return {
            "optimisation_result": None,
            "recommended_tariff": None,
            "ranking": [],
            "error": "No tariffs provided",
        }

    first = tariffs[0]
    latitude = getattr(first, "latitude", 0.0)
    longitude = getattr(first, "longitude", 0.0)
    if annual_consumption_kwh is None:
        annual_consumption_kwh = float(getattr(first, "annual_electricity_kwh", 3500))

    if solar_type_params is None:
        solar_type_params = SOLAR_TIERS["budget"]
    if wind_type_params is None:
        wind_type_params = WIND_TIERS["budget"]

    return recommend_tariff(
        tariffs,
        latitude,
        longitude,
        annual_consumption_kwh,
        solar_type_params,
        wind_type_params,
        export_price_per_kwh=export_price_per_kwh,
        optimize_over_years=optimize_over_years,
        flux_source=flux_source,
        heating_fraction=heating_fraction,
        insulation_r_value=insulation_r_value,
        heat_pump_cop=heat_pump_cop,
        prefer_green=prefer_green,
        **kwargs,
    )
