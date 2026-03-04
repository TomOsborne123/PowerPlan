# PowerPlan

A Home Energy System Planning Tool. PowerPlan uses weather data and tariff information to help plan and compare energy options for a given location.

## Features

- **Weather and flux data** — Fetch hourly or daily weather (temperature, wind, solar irradiance) for any latitude/longitude via the Open-Meteo API.
- **Energy balancing model** — Inputs: latitude, longitude, solar and wind **capacity** (kW), and generation-type params (e.g. budget/mid/premium from `src.data.energy_tiers`). Uses daily weather (GHI sum, wind speed) from the API; returns daily solar and wind generation with no month scaling.
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

After this, `from src...` imports work from any working directory. If you don’t install the package, run scripts and the notebook **from the project root** (the `PowerPlan` directory) so that `src` is found.

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
│   │   ├── energy_tiers.py        # Solar/wind type definitions (budget, mid, premium)
│   │   ├── create_energy_tariff_database.py
│   │   └── create_energy_tariff_database_simple.py   # MySQL schema for tariffs
│   └── models/
│       ├── energy_balancing.py     # get_flux_daily, get_generation (daily, no scaling)
│       ├── energyBalancing.ipynb   # Notebook: location + capacity + types → daily generation
│       └── economicBalancing.ipynb
├── scripts/
│   └── fetch_weather.py           # Example: fetch weather for a location
└── results_page.html              # Scraped comparison page (example output)
```

## Quick start

**Daily generation from location and capacity**

1. Open `src/models/energyBalancing.ipynb`.
2. Set `latitude`, `longitude`, `solar_capacity_kw`, `wind_capacity_kw`, and generation types (e.g. `SOLAR_TIERS["budget"]`, `WIND_TIERS["budget"]` from `src.data.energy_tiers`).
3. Run the cells to get a daily table of solar and wind generation (no month scaling; data comes from the weather API).

From code:

```python
from src.models.energy_balancing import get_generation, get_flux_daily
from src.data.energy_tiers import SOLAR_TIERS, WIND_TIERS

daily = get_generation(
    51.4552, -2.5966,           # latitude, longitude
    4.0, 2.0,                   # solar_capacity_kw, wind_capacity_kw
    SOLAR_TIERS["budget"],      # solar type params (stored in energy_tiers)
    WIND_TIERS["budget"],       # wind type params
)
# daily has columns: ghi_j_per_m2, wind_speed_10m_max, solar_gen_kwh, wind_gen_kwh, total_gen_kwh
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

Or run the example script (from the project root):

```bash
cd PowerPlan
python scripts/fetch_weather.py
```

**If you see `ModuleNotFoundError: No module named 'src'`**

- Run from the **project root** (`PowerPlan/`): e.g. `cd PowerPlan` then `python scripts/fetch_weather.py` or open and run the notebook from that folder, or  
- Install the package so `src` is on the path from anywhere: `pip install -e .` from the project root.  

The script and notebook add the project root to `sys.path` when run from the project root, so `import src` works without installing.

## Configuration

- **Weather API** — Uses [Open-Meteo](https://open-meteo.com/) (no API key required for basic use). Caching is enabled (e.g. `.cache`).
- **Tariff database** — MySQL connection details (host, user, password) are set in the data scripts; use environment variables or a config file in production.

## License

See [LICENSE](LICENSE).

## Author

Tom Osborne (tomosbornee123@gmail.com)
