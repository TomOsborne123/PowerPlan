import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

def get_weather(latitude, longitude, start_date, end_date, variables, frequency):
    """
    Fetch hourly weather data from Open-Meteo.

    Args:
        latitude (float)
        longitude (float)
        start_date (str)
        end_date (str)
        variables (list of str): List of hourly variables to fetch.
        frequency (str): Daily or hourly.

    Returns:
        pd.DataFrame: Hourly or Daily weather data.
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

    # Set up the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "models": "ukmo_seamless",
        "wind_speed_unit": "ms",
        "start_date": start_date,
        "end_date": end_date,
    }
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

    dataframe = pd.DataFrame(data = data)

    return dataframe
