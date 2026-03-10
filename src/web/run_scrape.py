"""
Run the tariff scraper for a postcode as a standalone process.
Used by the web app to avoid "Event loop is closed" when Playwright runs in a thread.

Usage (from project root):
  python -m src.web.run_scrape "BS1 1AA"
Exit code 0 = success, 1 = failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m src.web.run_scrape <postcode>", file=sys.stderr)
        return 1
    postcode = sys.argv[1].strip()
    if len(postcode) < 5:
        print("Postcode too short", file=sys.stderr)
        return 1
    try:
        from src.api.energyScraping.ScrapeTariff import ScrapeTariff
        scraper = ScrapeTariff()
        scraper.scrape(
            postcode=postcode,
            address_index=0,
            fuel_type="both",
            current_supplier="Octopus",
            pay_method="monthly_direct_debit",
            has_ev="No but interested",
            headless=True,
        )
        return 0
    except Exception as e:
        print(f"Scrape failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
