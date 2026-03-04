from datetime import date

import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

# Forecast API (next ~16 days); use_archive=True uses Historical Weather API (past data).
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def get_weather(latitude, longitude, start_date, end_date, variables, frequency, use_archive=False):
    """
    Fetch weather data from Open-Meteo (forecast or historical archive).

    Args:
        latitude (float)
        longitude (float)
        start_date (str): ISO date yyyy-mm-dd
        end_date (str): ISO date yyyy-mm-dd
        variables (list of str): Hourly or daily variables to fetch (see allowed sets below).
        frequency (str): 'hourly' or 'daily'.
        use_archive (bool): If True, use Historical Weather API (past dates). If False, use Forecast API.

    Returns:
        pd.DataFrame: Hourly or daily weather data.
    """

    variables_allowed_hourly = {
        "temperature_2m",
        "wind_speed_10m",
        "wind_direction_10m",
        "weather_code",
        "direct_radiation",
        "shortwave_radiation",
        "diffuse_radiation",
        "direct_normal_irradiance",
        "relative_humidity_2m",
        "dew_point_2m",
        "apparent_temperature",
        "precipitation",
        "rain",
        "showers",
        "snowfall",
        "hail",
        "wind_gusts_10m",
        "et0_fao_evapotranspiration",
        "vapour_pressure_deficit",
        "visibility",
        "pressure_msl",
        "surface_pressure",
        "cloud_cover",
        "cloud_cover_low",
        "cloud_cover_mid",
        "cloud_cover_high",
        "cloud_cover_2m",
    }

    variables_allowed_daily = {
        "temperature_2m_max",
        "weather_code",
        "apparent_temperature_min",
        "temperature_2m_min",
        "apparent_temperature_max",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "wind_direction_10m_dominant",
        "shortwave_radiation_sum",
        "et0_fao_evapotranspiration",
        "sunshine_duration",
        "daylight_duration",
        "sunset",
        "sunrise",
        "rain_sum",
        "showers_sum",
        "snowfall_sum",
        "precipitation_sum",
        "precipitation_hours",
        "precipitation_probability_max",
    }

    # --- Validate frequency
    if frequency not in ("hourly", "daily"):
        raise ValueError("frequency must be 'hourly' or 'daily'")

    #--- Validate variables
    variables_allowed = variables_allowed_hourly if frequency == "hourly" else variables_allowed_daily
    invalid_vars = [v for v in variables if v not in variables_allowed]
    if invalid_vars:
        raise ValueError(f"Invalid variables requested for {frequency}: {invalid_vars}. "
                         f"Allowed: {sorted(variables_allowed)}")

    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    url = ARCHIVE_URL if use_archive else FORECAST_URL
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "wind_speed_unit": "ms",
        "start_date": start_date,
        "end_date": end_date,
    }
    if not use_archive:
        params["models"] = "ukmo_seamless"
    if frequency == "hourly":
        params["hourly"] = variables
    else:
        params["daily"] = variables
        params["timezone"] = "UTC"

    response_first = openmeteo.weather_api(url, params=params)[0]

    response = response_first.Hourly() if frequency == "hourly" else response_first.Daily()
    data = {
        "date": pd.date_range(
            start=pd.to_datetime(response.Time(), unit="s", utc=True),
            end=pd.to_datetime(response.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=response.Interval()),
            inclusive="left",
        )
    }

    for i, var in enumerate(variables):
        data[var] = response.Variables(i).ValuesAsNumpy()

    dataframe = pd.DataFrame(data=data)
    return dataframe


# Default daily variables for last-year monthly aggregation (radiation sum, wind, temp, precipitation).
DEFAULT_LAST_YEAR_DAILY_VARIABLES = [
    "shortwave_radiation_sum",
    "wind_speed_10m_max",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
]

# Variables that are summed over the month (daily values are summed); all others are averaged.
DAILY_SUM_VARIABLES = {
    "shortwave_radiation_sum",
    "rain_sum",
    "showers_sum",
    "snowfall_sum",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
    "sunshine_duration",
    "daylight_duration",
}


def get_weather_last_year_monthly(latitude, longitude, variables=None):
    """
    Fetch last calendar year's weather at daily resolution from the Historical API,
    then aggregate to one row per month (12 rows).

    Args:
        latitude (float)
        longitude (float)
        variables (list of str, optional): Daily variable names. Defaults to
            shortwave_radiation_sum, wind_speed_10m_max, temperature_2m_max,
            temperature_2m_min, precipitation_sum.

    Returns:
        pd.DataFrame: 12 rows (Jan–Dec), index = month number (1–12), columns = aggregated
        variables. Sum-type variables (e.g. shortwave_radiation_sum) are monthly totals;
        others (e.g. temperature, wind_speed_10m_max) are monthly means.
    """
    last_year = date.today().year - 1
    start_date = f"{last_year}-01-01"
    end_date = f"{last_year}-12-31"
    vars_to_use = variables or DEFAULT_LAST_YEAR_DAILY_VARIABLES
    # Restrict to allowed daily variables
    variables_allowed_daily = {
        "temperature_2m_max", "temperature_2m_min", "weather_code",
        "apparent_temperature_min", "apparent_temperature_max",
        "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant",
        "shortwave_radiation_sum", "et0_fao_evapotranspiration",
        "sunshine_duration", "daylight_duration", "sunset", "sunrise",
        "rain_sum", "showers_sum", "snowfall_sum", "precipitation_sum",
        "precipitation_hours", "precipitation_probability_max",
    }
    vars_to_use = [v for v in vars_to_use if v in variables_allowed_daily]
    if not vars_to_use:
        vars_to_use = list(DEFAULT_LAST_YEAR_DAILY_VARIABLES)

    df = get_weather(
        latitude, longitude,
        start_date, end_date,
        vars_to_use,
        frequency="daily",
        use_archive=True,
    )
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["month"] = df["date"].dt.month

    agg = {}
    for v in vars_to_use:
        if v in DAILY_SUM_VARIABLES:
            agg[v] = "sum"
        else:
            agg[v] = "mean"
    monthly = df.groupby("month", as_index=True).agg(agg)
    monthly.index.name = "month"
    return monthly
