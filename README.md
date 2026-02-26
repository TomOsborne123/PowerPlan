# PowerPlan

A Home Energy System Planning Tool. PowerPlan uses weather data and tariff information to help plan and compare energy options for a given location.

## Features

- **Weather and flux data** — Fetch hourly or daily weather (temperature, wind, solar irradiance) for any latitude/longitude via the Open-Meteo API.
- **Energy balancing model** — From coordinates, derive solar (GHI/DNI/DHI) and wind flux, then run them through solar (pvlib) and wind (power-curve) models for several technology tiers (budget, mid, premium). Returns options for energy generation at different price points (annual kWh, capacity factor, cost band).
- **Tariff scraping** — Scrape energy tariff and comparison data (e.g. supplier, unit rate, standing charge, green/renewable flags) with location (postcode, lat/lon) and store in a MySQL-backed tariff database.

## Requirements

- Python ≥ 3.10
- MySQL (for tariff database; optional if you only use weather and energy balancing)

## Installation

```bash
git clone <repo-url>
cd PowerPlan
pip install -e .
```

For the energy balancing model (solar PV output), install the solar library:

```bash
pip install pvlib
```

## Project structure

```
PowerPlan/
├── pyproject.toml
├── README.md
├── src/
│   ├── api/
│   │   ├── get_weather.py          # Open-Meteo hourly/daily weather (solar, wind, temp)
│   │   └── energyScraping/
│   │       ├── ScrapeTariff.py     # Tariff scraping workflow
│   │       ├── ScrapeSequence.py   # Scrape sequencing
│   │       ├── Tariff.py           # Tariff dataclass and DB access
│   │       └── testScrape.py       # Scrape tests
│   ├── data/
│   │   ├── create_energy_tariff_database.py
│   │   └── create_energy_tariff_database_simple.py   # MySQL schema for tariffs
│   └── models/
│       ├── energy_balancing.py     # get_flux, get_energy_options, solar/wind tiers
│       ├── energyBalancing.ipynb   # Notebook: lat/lon → energy options
│       └── economicBalancing.ipynb
├── scripts/
│   └── fetch_weather.py           # Example: fetch weather for a location
└── results_page.html              # Scraped comparison page (example output)
```

## Quick start

**Energy options from latitude and longitude**

1. Open `src/models/energyBalancing.ipynb`.
2. Set `latitude` and `longitude` (e.g. Bristol: 51.4552, -2.5966).
3. Run the cells. The first cell calls `get_energy_options(latitude, longitude)` and shows a table of solar and wind options (by tier) with annual energy (kWh), cost band, and capacity factor.

From code:

```python
from src.models.energy_balancing import get_energy_options, get_flux

options = get_energy_options(latitude=51.4552, longitude=-2.5966)
# Optional: pass start_date, end_date (default: next 7 days forecast)
# options = get_energy_options(51.4552, -2.5966, "2026-02-20", "2026-02-26")
```

**Weather only**

```python
from src.api.get_weather import get_weather

df = get_weather(
    latitude=51.4552,
    longitude=-2.5966,
    start_date="2026-02-20",
    end_date="2026-02-26",
    variables=["temperature_2m", "wind_speed_10m", "shortwave_radiation"],
    frequency="hourly",
)
```

Or run the example script:

```bash
python scripts/fetch_weather.py
```

## Configuration

- **Weather API** — Uses [Open-Meteo](https://open-meteo.com/) (no API key required for basic use). Caching is enabled (e.g. `.cache`).
- **Tariff database** — MySQL connection details (host, user, password) are set in the data scripts; use environment variables or a config file in production.

## License

See [LICENSE](LICENSE).

## Author

Tom Osborne (tomosbornee123@gmail.com)
