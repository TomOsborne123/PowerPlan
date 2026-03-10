# PowerPlan

A Home Energy System Planning Tool. PowerPlan uses weather data and tariff information to help plan and compare energy options for a given location.

## Features

- **Weather and flux data** — Fetch hourly or daily weather (temperature, wind, solar irradiance) for any latitude/longitude via the Open-Meteo API.
- **Energy balancing model** — Inputs: latitude, longitude, solar and wind **capacity** (kW), and generation-type params (e.g. budget/mid/premium from `src.data.energy_tiers`). Uses daily weather (GHI sum, wind speed) from the API; returns daily solar and wind generation with no month scaling.
- **Tariff scraping** — Scrape energy tariff and comparison data (e.g. supplier, unit rate, standing charge, green/renewable flags) with location (postcode, lat/lon) and store in a MySQL-backed tariff database.
- **Web app** — Enter location (UK postcode or lat/lon), annual usage, demand options (heating fraction, insulation, heat pump), and tariffs; get recommended solar/wind sizing and best tariff.

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
├── .gitignore
├── src/
│   ├── api/
│   │   ├── get_weather.py           # Open-Meteo hourly/daily weather (solar, wind, temp)
│   │   ├── postcode_lookup.py       # UK postcode → lat/lon (postcodes.io)
│   │   └── energyScraping/
│   │       ├── ScrapeTariff.py     # Tariff scraping (Camoufox/Playwright)
│   │       ├── ScrapeSequence.py   # CLI scrape flow
│   │       ├── Tariff.py           # Tariff dataclass and DB save
│   │       ├── recommend_from_scrape.py
│   │       └── testScrape.py       # Selenium scrape test
│   ├── data/
│   │   ├── energy_tiers.py
│   │   ├── create_energy_tariff_database.py
│   │   └── create_energy_tariff_database_simple.py
│   ├── models/
│   │   ├── energy_balancing.py
│   │   ├── tariff_recommendation.py
│   │   ├── energyBalancing.ipynb
│   │   └── economicBalancing.ipynb
│   └── web/
│       ├── app.py                  # Flask app: API + serves React build
│       ├── run_scrape.py           # CLI for scrape (used by app in subprocess)
│       └── static/                 # React build output (npm run build)
├── frontend/                       # React (Vite) source
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── ResultView.jsx
│       ├── api.js
│       └── index.css
├── scripts/
│   └── fetch_weather.py
└── output/                         # Ignored; scrape debug (HTML, screenshots) → output/scrape_debug/
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

**Web app (recommended technologies + tariff)**

The web UI is a **React** app (Vite). You can either run the React dev server (with API proxy to Flask) or build once and let Flask serve the built files.

**Option A — Development (React dev server + Flask API)**

Terminal 1 (Flask API):

```bash
cd PowerPlan
pip install -e .
python -m src.web.app
```

Terminal 2 (React dev server; proxies /api to Flask on port 5001):

```bash
cd PowerPlan/frontend
npm install
npm run dev
```

Then open http://127.0.0.1:5173 (Vite). API calls go to the Flask backend.

**Option B — Production-style (Flask serves built React app)**

Build the frontend once, then run Flask:

```bash
cd PowerPlan/frontend
npm install
npm run build
cd ..
python -m src.web.app
```

Then open http://127.0.0.1:5001. The build output is written to `src/web/static/`.

On the page: enter a UK postcode (or latitude/longitude), annual electricity use, optional demand adjustments (heating fraction, insulation, heat pump COP), and tariff options (supplier, unit rate p/kWh, standing charge p/day). Click **Get recommendation** to see optimal solar/wind capacity and the best tariff.

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
