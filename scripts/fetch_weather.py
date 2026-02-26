# Ensure project root is on path (so "from src..." works when run from project root)
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
if _root not in sys.path:
    sys.path.insert(0, str(_root))

from src.api.get_weather import get_weather

variables = ["temperature_2m", "wind_speed_10m"]

def main():
    df = get_weather(
        latitude=51.4552,
        longitude=-2.5966,
        start_date="2026-01-12",
        end_date="2026-01-19",
        variables=["temperature_2m", "wind_speed_10m"],
        frequency="hourly"
    )
    print(df.head())

if __name__ == "__main__":
    main()
