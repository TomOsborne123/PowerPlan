"""
Run the tariff scraper for a postcode as a standalone process.
Used by the web app to avoid "Event loop is closed" when Playwright runs in a thread.

Usage (from project root):
  python -m src.web.run_scrape "BS1 1AA"
Exit code 0 = success, 1 = failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Live logs when stdout is a pipe (e.g. Gunicorn subprocess on Render): flush each line.
os.environ.setdefault("PYTHONUNBUFFERED", "1")
for _stream in (sys.stdout, sys.stderr):
    try:
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(line_buffering=True)
    except Exception:
        pass

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set headless/GPU env before importing browser – can reduce macOS "Python quit unexpectedly"
os.environ.setdefault("MOZ_HEADLESS", "1")
os.environ.setdefault("MOZ_DISABLE_GPU_SANDBOX", "1")


def _scraper_headless():
    """
    Camoufox: True = native headless, 'virtual' = Xvfb (needs `xvfb` package in Docker).
    Env SCRAPER_HEADLESS: 1/true, 0/false, virtual (default: True for speed).
    """
    raw = (os.environ.get("SCRAPER_HEADLESS") or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    if raw == "virtual":
        return "virtual"
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m src.web.run_scrape <postcode> [home|business]", file=sys.stderr)
        return 1
    postcode = sys.argv[1].strip()
    if len(postcode) < 5:
        print("Postcode too short", file=sys.stderr)
        return 1
    home_or_business = (sys.argv[2].strip().lower() if len(sys.argv) > 2 else "home")
    if home_or_business not in ("home", "business"):
        home_or_business = "home"
    print(f"[run_scrape] pid={os.getpid()} postcode={postcode!r} mode={home_or_business!r}", flush=True)
    scraper = None
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
            home_or_business=home_or_business,
            headless=_scraper_headless(),
        )
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(f"Scrape failed: {e}", file=sys.stderr)
        # Avoid Python shutdown/atexit so browser cleanup doesn't crash the process
        os._exit(1)
    finally:
        # Release references so context manager can close browser before process exits
        if scraper is not None:
            scraper.browser = None
            scraper.page = None
        scraper = None


if __name__ == "__main__":
    exit_code = main()
    # Normal success path only; failure path uses os._exit(1)
    sys.exit(exit_code)
