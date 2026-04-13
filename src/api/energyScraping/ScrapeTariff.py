"""
Created 02-03-26
Updated to use Camoufox
@author: Tom Osborne
"""

from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup
try:
    from .Tariff import Tariff
except ImportError:
    from Tariff import Tariff
import time
from datetime import datetime
import re
from typing import List
import re
import requests
from difflib import SequenceMatcher
from typing import Dict, Optional
from pathlib import Path
import os
import sys

# Real sleep for _scrape_sleep (all pacing uses _scrape_sleep so SCRAPER_PACE_MULT applies).
_time_sleep = time.sleep


def _configure_live_stdio() -> None:
    """Stdout/stderr attached to pipes default to block-buffering; fix for timely Render logs."""
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(line_buffering=True)
        except Exception:
            pass


# Debug output for scrape (HTML, screenshots) – keeps repo root clean
_DEBUG_DIR = Path(__file__).resolve().parents[3] / "output" / "scrape_debug"


def _debug_path(name: str) -> str:
    """Return path for debug file. Creates output dir if possible; else falls back to cwd so scrape never fails on debug write."""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        return str(_DEBUG_DIR / name)
    except Exception:
        return name


def _scrape_pace_mult() -> float:
    """
    Scale all scraper pacing sleeps. Set SCRAPER_PACE_MULT=0.65 locally to run ~35% faster
    (trade-off: more risk of flaky steps on slow loads or stricter bot timing).
    """
    try:
        m = float((os.environ.get("SCRAPER_PACE_MULT") or "1").strip())
    except ValueError:
        m = 1.0
    return max(0.2, min(1.75, m))


def _scrape_sleep(seconds: float) -> None:
    """Pacing delay between Playwright actions (scaled by SCRAPER_PACE_MULT)."""
    if seconds <= 0:
        return
    _time_sleep(seconds * _scrape_pace_mult())


def _typing_delay_ms() -> int:
    """Milliseconds between keystrokes for .type(); 0 = instant (faster, less human-like)."""
    try:
        ms = int((os.environ.get("SCRAPER_TYPING_DELAY_MS") or "50").strip())
    except ValueError:
        ms = 50
    return max(0, min(120, ms))


def _usage_text_to_annual_kwh(consumption_text: str) -> int | None:
    """
    Parse kWh from comparison-site usage copy (e.g. '2,900 kWh / year' or '242 kWh / month').
    Returns annual kWh, scaling up when the site states a monthly figure.
    """
    if not consumption_text:
        return None
    match = re.search(r"([\d,]+)\s*kwh", consumption_text, re.IGNORECASE)
    if not match:
        return None
    try:
        value = int(match.group(1).replace(",", ""))
    except ValueError:
        return None
    low = consumption_text.lower()
    monthly_markers = ("/month", "/ month", "per month", "a month", "pcm", "p.m.", " monthly")
    yearly_markers = ("/year", "/ year", "per year", "a year", "p.a.", "annum", "annual", "/yr", "/ yr")
    if any(m in low for m in monthly_markers):
        return value * 12
    if any(m in low for m in yearly_markers):
        return value
    # Plain "X kWh" with no period: treat as annual (legacy pages often imply yearly usage).
    return value


def _tariff_card_annual_cost_gbp(cost_sub_value: str) -> float:
    """Parse 'or £1,234 a year' vs '£103 a month' style strings into an annual £ total."""
    if not cost_sub_value:
        return 0.0
    m = re.search(r"£\s*([\d,]+(?:\.\d+)?)", cost_sub_value)
    if not m:
        return 0.0
    try:
        val = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0.0
    low = cost_sub_value.lower()
    if any(x in low for x in ("month", "/mo", " pcm", "p.m.")):
        return val * 12.0
    return val


def _standing_charge_cell_to_pence_per_day(display_text: str) -> float:
    """
    Standing charge may be shown as pence/day or as £/month. Tariff model stores pence per day.
    """
    if not display_text:
        return 0.0
    t = display_text.replace("\u00a0", " ").strip()
    low = t.lower()

    def _gbp_month_to_pence_per_day(gbp_month: float) -> float:
        days_per_month = 365.25 / 12.0
        return round((gbp_month * 100.0) / days_per_month, 4)

    if re.search(r"month|/mo\b|pcm|per\s+month", low):
        m = re.search(r"£\s*([\d,]+(?:\.\d+)?)", t)
        if m:
            try:
                return _gbp_month_to_pence_per_day(float(m.group(1).replace(",", "")))
            except ValueError:
                return 0.0
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*p", low)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return 0.0
    m = re.search(r"£\s*([\d,]+(?:\.\d+)?)", t)
    if m and not re.search(r"[\d,]+(?:\.\d+)?\s*p", low):
        try:
            gbp = float(m.group(1).replace(",", ""))
        except ValueError:
            gbp = 0.0
        if gbp >= 5.0:
            return _gbp_month_to_pence_per_day(gbp)
    m = re.search(r"([\d,]+(?:\.\d+)?)", t)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return 0.0
    return 0.0


# Pacing between Playwright actions (seconds). Multiplied at runtime by SCRAPER_PACE_MULT (default 1).
# Increase base values here (or set SCRAPER_PACE_MULT>1) if the comparison site flakes.
_SCRAPE_AFTER_GOTO = 1.6
_SCRAPE_AFTER_RELOAD = 1.2
_SCRAPE_CLOUDFLARE = 5.0
_SCRAPE_BEFORE_FUEL = 0.55
_SCRAPE_RESULTS_POLL = 1.2
_SCRAPE_AFTER_RESULTS_SELECTOR = 0.65
_SCRAPE_POSTCODE_DOM = 1.8
_SCRAPE_ADDRESS_UI_MAX_WAIT = 18.0  # Address list often loads after postcode API response (wall-clock, not scaled)
_SCRAPE_AFTER_SUBMIT = 1.1
_SCRAPE_AFTER_CLICK = 0.75
_SCRAPE_PRE_CLICK = 0.45
_SCRAPE_MICRO = 0.28
_SCRAPE_SHORT = 0.38


class PostcodeLookup:
    """Lookup location data from UK postcodes"""
    
    # DNO (Distribution Network Operator) mapping by postcode area
    DNO_MAPPING = {
        # Scotland
        'AB': ('SPEN', 'SPEN_1'),
        'DD': ('SPEN', 'SPEN_1'),
        'DG': ('SPEN', 'SPEN_1'),
        'EH': ('SPEN', 'SPEN_1'),
        'FK': ('SPEN', 'SPEN_1'),
        'G': ('SPEN', 'SPEN_1'),
        'HS': ('SSEN', 'SSEN_1'),
        'IV': ('SSEN', 'SSEN_1'),
        'KA': ('SPEN', 'SPEN_1'),
        'KW': ('SSEN', 'SSEN_1'),
        'KY': ('SPEN', 'SPEN_1'),
        'ML': ('SPEN', 'SPEN_1'),
        'PA': ('SPEN', 'SPEN_1'),
        'PH': ('SSEN', 'SSEN_1'),
        'ZE': ('SSEN', 'SSEN_1'),
        
        # Northern England
        'BD': ('NPG', 'NPG_1'),
        'CA': ('ENWL', 'ENWL_1'),
        'DH': ('NPG', 'NPG_1'),
        'DL': ('NPG', 'NPG_1'),
        'DN': ('NPG', 'NPG_1'),
        'HG': ('NPG', 'NPG_1'),
        'HU': ('NPG', 'NPG_1'),
        'HX': ('ENWL', 'ENWL_1'),
        'LA': ('ENWL', 'ENWL_1'),
        'LS': ('NPG', 'NPG_1'),
        'NE': ('NPG', 'NPG_1'),
        'SR': ('NPG', 'NPG_1'),
        'TS': ('NPG', 'NPG_1'),
        'YO': ('NPG', 'NPG_1'),
        
        # North West England
        'BB': ('ENWL', 'ENWL_1'),
        'BL': ('ENWL', 'ENWL_1'),
        'CH': ('SPMW', 'SPMW_1'),
        'CW': ('ENWL', 'ENWL_1'),
        'FY': ('ENWL', 'ENWL_1'),
        'L': ('ENWL', 'ENWL_1'),
        'M': ('ENWL', 'ENWL_1'),
        'OL': ('ENWL', 'ENWL_1'),
        'PR': ('ENWL', 'ENWL_1'),
        'SK': ('ENWL', 'ENWL_1'),
        'WA': ('ENWL', 'ENWL_1'),
        'WN': ('ENWL', 'ENWL_1'),
        
        # Midlands
        'B': ('WPD_WM', 'WPD_4'),
        'CV': ('WPD_WM', 'WPD_4'),
        'DE': ('WPD_EM', 'WPD_3'),
        'DY': ('WPD_WM', 'WPD_4'),
        'LE': ('WPD_EM', 'WPD_3'),
        'LN': ('WPD_EM', 'WPD_3'),
        'NG': ('WPD_EM', 'WPD_3'),
        'NN': ('WPD_EM', 'WPD_3'),
        'S': ('NPG', 'NPG_1'),
        'ST': ('WPD_WM', 'WPD_4'),
        'SY': ('SPMW', 'SPMW_1'),
        'TF': ('SPMW', 'SPMW_1'),
        'WS': ('WPD_WM', 'WPD_4'),
        'WV': ('WPD_WM', 'WPD_4'),
        
        # East England
        'CB': ('UKPN_EPN', 'UKPN_2'),
        'CM': ('UKPN_EPN', 'UKPN_2'),
        'CO': ('UKPN_EPN', 'UKPN_2'),
        'IP': ('UKPN_EPN', 'UKPN_2'),
        'LU': ('UKPN_EPN', 'UKPN_2'),
        'NR': ('UKPN_EPN', 'UKPN_2'),
        'PE': ('UKPN_EPN', 'UKPN_2'),
        'SG': ('UKPN_EPN', 'UKPN_2'),
        
        # London
        'E': ('UKPN_LPN', 'UKPN_1'),
        'EC': ('UKPN_LPN', 'UKPN_1'),
        'EN': ('UKPN_LPN', 'UKPN_1'),
        'IG': ('UKPN_LPN', 'UKPN_1'),
        'N': ('UKPN_LPN', 'UKPN_1'),
        'NW': ('UKPN_LPN', 'UKPN_1'),
        'RM': ('UKPN_LPN', 'UKPN_1'),
        'SE': ('UKPN_LPN', 'UKPN_1'),
        'SW': ('UKPN_LPN', 'UKPN_1'),
        'W': ('UKPN_LPN', 'UKPN_1'),
        'WC': ('UKPN_LPN', 'UKPN_1'),
        
        # South East England
        'BN': ('SSEN_SEPD', 'SSEN_2'),
        'BR': ('UKPN_SPN', 'UKPN_3'),
        'CR': ('UKPN_SPN', 'UKPN_3'),
        'CT': ('UKPN_SPN', 'UKPN_3'),
        'DA': ('UKPN_SPN', 'UKPN_3'),
        'GU': ('SSEN_SEPD', 'SSEN_2'),
        'HA': ('UKPN_LPN', 'UKPN_1'),
        'HP': ('SSEN_SEPD', 'SSEN_2'),
        'KT': ('UKPN_SPN', 'UKPN_3'),
        'ME': ('UKPN_SPN', 'UKPN_3'),
        'MK': ('SSEN_SEPD', 'SSEN_2'),
        'OX': ('SSEN_SEPD', 'SSEN_2'),
        'PO': ('SSEN_SEPD', 'SSEN_2'),
        'RG': ('SSEN_SEPD', 'SSEN_2'),
        'RH': ('SSEN_SEPD', 'SSEN_2'),
        'SL': ('SSEN_SEPD', 'SSEN_2'),
        'SM': ('UKPN_SPN', 'UKPN_3'),
        'SO': ('SSEN_SEPD', 'SSEN_2'),
        'TN': ('UKPN_SPN', 'UKPN_3'),
        'TW': ('UKPN_LPN', 'UKPN_1'),
        'UB': ('UKPN_LPN', 'UKPN_1'),
        
        # South West England
        'BA': ('WPD_SW', 'WPD_1'),
        'BH': ('SSEN_SEPD', 'SSEN_2'),
        'BS': ('WPD_SW', 'WPD_1'),
        'DT': ('WPD_SW', 'WPD_1'),
        'EX': ('WPD_SW', 'WPD_1'),
        'GL': ('WPD_SW', 'WPD_1'),
        'PL': ('WPD_SW', 'WPD_1'),
        'SN': ('SSEN_SEPD', 'SSEN_2'),
        'SP': ('SSEN_SEPD', 'SSEN_2'),
        'TA': ('WPD_SW', 'WPD_1'),
        'TQ': ('WPD_SW', 'WPD_1'),
        'TR': ('WPD_SW', 'WPD_1'),
        
        # Wales
        'CF': ('WPD_SW', 'WPD_2'),
        'LD': ('WPD_SW', 'WPD_2'),
        'LL': ('SPMW', 'SPMW_1'),
        'NP': ('WPD_SW', 'WPD_2'),
        'SA': ('WPD_SW', 'WPD_2'),
    }
    
    @staticmethod
    def _get_dno_from_outward_code(outward_code: str):
        """
        Try 2-letter outward code first, then fall back to 1-letter.
        """
        if not outward_code:
            return ('Unknown', 'Unknown')

        outward_code = outward_code.upper()

        # Try first two letters (e.g. "SW", "EC")
        if len(outward_code) >= 2:
            key_2 = outward_code[:2]
            if key_2 in PostcodeLookup.DNO_MAPPING:
                return PostcodeLookup.DNO_MAPPING[key_2]

        # Fall back to first letter (e.g. "S", "L")
        key_1 = outward_code[0]
        return PostcodeLookup.DNO_MAPPING.get(key_1, ('Unknown', 'Unknown'))

    @staticmethod
    def lookup(postcode: str) -> Optional[Dict]:
        """
        Lookup postcode data from postcodes.io API
        
        Returns dict with:
        - postcode
        - outward_code
        - latitude
        - longitude
        - region
        - admin_district
        - country
        - dno_name
        - dno_id
        """
        if not postcode:
            return None
        
        # Clean postcode
        postcode_clean = postcode.strip().upper().replace(" ", "")
        
        try:
            # Call postcodes.io API
            response = requests.get(
                f"https://api.postcodes.io/postcodes/{postcode_clean}",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data['status'] == 200:
                    result = data['result']
                    
                    # Extract outward code (first part of postcode)
                    outward_code = result.get('outcode', '')
                    
                    # Get DNO based on outward code
                    dno_name, dno_id = PostcodeLookup._get_dno_from_outward_code(outward_code)

                    
                    return {
                        'postcode': result.get('postcode', postcode),
                        'outward_code': outward_code,
                        'latitude': result.get('latitude', 0.0),
                        'longitude': result.get('longitude', 0.0),
                        'region': result.get('region', ''),
                        'region_code': result.get('codes', {}).get('admin_district', ''),
                        'admin_district': result.get('admin_district', ''),
                        'country': result.get('country', ''),
                        'dno_name': dno_name,
                        'dno_id': dno_id,
                    }
            
            print(f"⚠ Postcode lookup failed: {response.status_code}")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"⚠ Error looking up postcode: {e}")
            return None

class ScrapeTariff:

    def __init__(self):
        self.soup = None
        self.tariff = None
        self.browser = None
        self.page = None
        self.location_data = None

    def fetch_address_options(self, postcode: str, headless: bool | str = False) -> List[str]:
        """
        Open the comparison flow and return address dropdown options for a postcode.
        This lets the UI present a real address picker before running the full scrape.
        """
        _configure_live_stdio()
        url = "https://www.moneysupermarket.com/gas-and-electricity/"
        options_out: List[str] = []
        try:
            print(f"-- Fetching address options for {postcode} --", flush=True)
            with Camoufox(
                headless=headless,
                humanize=False,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
            ) as browser:
                self.browser = browser
                self.page = browser.new_page()
                self.page.set_extra_http_headers({
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Encoding': 'identity',
                    'Accept-Language': 'en-GB,en;q=0.9',
                })
                nav_timeout_ms = int(float(os.environ.get("SCRAPER_NAV_TIMEOUT_MS", "90000")))
                self.page.set_default_navigation_timeout(nav_timeout_ms)
                self.page.set_default_timeout(nav_timeout_ms)
                self.page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
                _scrape_sleep(_SCRAPE_AFTER_GOTO)

                self._step0_cookies_and_start()
                self._step1_enter_email()

                postcode_input = None
                for selector in [
                    "#postcode",
                    "input[name='postcode']",
                    "input[name*='postcode']",
                    "input[id*='postcode']",
                    "input[placeholder*='postcode' i]",
                    "input[type='text']",
                ]:
                    try:
                        candidate = self.page.locator(selector).first
                        if candidate.is_visible(timeout=3000):
                            postcode_input = candidate
                            break
                    except Exception:
                        continue
                if postcode_input is None:
                    raise Exception("Could not find postcode input field")
                postcode_input.clear()
                postcode_input.type(postcode, delay=_typing_delay_ms())
                try:
                    postcode_input.press("Enter")
                except Exception:
                    pass
                _scrape_sleep(_SCRAPE_POSTCODE_DOM)

                for open_sel in [
                    '[role="combobox"]',
                    'input[aria-autocomplete="list"]',
                    'input[aria-haspopup="listbox"]',
                    '[data-testid*="address" i] input',
                    'input[placeholder*="address" i]',
                ]:
                    try:
                        loc = self.page.locator(open_sel).first
                        if loc.is_visible(timeout=1000):
                            loc.click(timeout=1500)
                            break
                    except Exception:
                        continue

                deadline = time.monotonic() + _SCRAPE_ADDRESS_UI_MAX_WAIT
                collected: List[str] = []
                while time.monotonic() < deadline and not collected:
                    # Native <select>
                    for selector in ["#address", "select[name*='address' i]", "select[id*='address' i]", "select[class*='address' i]"]:
                        try:
                            dd = self.page.locator(selector).first
                            if not dd.is_visible(timeout=700):
                                continue
                            opts = dd.locator("option").all()
                            for o in opts:
                                txt = (o.text_content() or "").strip()
                                if txt:
                                    collected.append(txt)
                            if collected:
                                break
                        except Exception:
                            continue
                    if collected:
                        break
                    # Custom list options
                    for list_selector in [
                        '[role="listbox"] [role="option"]',
                        '[role="listbox"] li',
                        "div[role='option']",
                        '[data-testid*="address" i]',
                        '[data-testid*="suggestion" i]',
                        ".address-list li",
                        '[class*="Address"] [class*="option" i]',
                    ]:
                        try:
                            opts = self.page.locator(list_selector)
                            cnt = opts.count()
                            for j in range(min(cnt, 40)):
                                t = (opts.nth(j).text_content() or "").strip()
                                if t:
                                    collected.append(t)
                            if collected:
                                break
                        except Exception:
                            continue
                    if not collected:
                        _scrape_sleep(0.45)

                # Clean and de-duplicate, drop placeholders.
                seen = set()
                for raw in collected:
                    txt = " ".join(raw.split())
                    low = txt.lower()
                    if not txt:
                        continue
                    if any(p in low for p in ["please select", "choose", "select address", "see more", "search"]):
                        continue
                    if txt not in seen:
                        seen.add(txt)
                        options_out.append(txt)
                return options_out
        finally:
            self.page = None
            self.browser = None

    def scrape(self,
               postcode: str,
               address_index: int = 0,
               address_name: str = '',
               fuel_type: str = 'both',
               current_supplier: str = '',
               pay_method: str = 'monthly_direct_debit',
               has_ev: str = 'No',
               home_or_business: str = 'home',
               headless: bool | str = False,
               _retry_on_target_closed: bool = True) -> List[Tariff]:

        _configure_live_stdio()

        url = "https://www.moneysupermarket.com/gas-and-electricity/"

        print(f"-- Starting scrape for {postcode} --", flush=True)

        self.location_data = PostcodeLookup.lookup(postcode)
        if self.location_data:
            print(f"✓ Location: {self.location_data.get('admin_district')}, {self.location_data.get('region')}")
            print(f"✓ DNO: {self.location_data.get('dno_name')} ({self.location_data.get('dno_id')})")
            print(f"✓ Coordinates: {self.location_data.get('latitude')}, {self.location_data.get('longitude')}")
        else:
            print("⚠ Could not lookup postcode data - will use defaults")
            postcode_norm = (postcode or '').strip().upper().replace(" ", "")
            outward_match = re.match(r"^([A-Z]{1,2}\d{1,2}[A-Z]?)", postcode_norm)
            outward_code = outward_match.group(1) if outward_match else ""
            dno_name, dno_id = PostcodeLookup._get_dno_from_outward_code(outward_code)
            self.location_data = {
                'postcode': postcode_norm,
                'outward_code': outward_code,
                'latitude': 0.0,
                'longitude': 0.0,
                'region': '',
                'region_code': '',
                'admin_district': '',
                'country': '',
                'dno_name': dno_name,
                'dno_id': dno_id,
            }

        try:
            # Use Camoufox with humanized settings
            print("Launching Camoufox browser...")
            with Camoufox(
                    headless=headless,
                    humanize=False,  # Try disabling humanize
                    # Extra arguments to improve stability in linux containers.
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
            ) as browser:
                self.browser = browser
                self.page = browser.new_page()

                # Set headers to request uncompressed content
                self.page.set_extra_http_headers({
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Encoding': 'identity',  # Request uncompressed
                    'Accept-Language': 'en-GB,en;q=0.9',
                })

                print("Loading page...")
                nav_timeout_ms = int(float(os.environ.get("SCRAPER_NAV_TIMEOUT_MS", "90000")))
                self.page.set_default_navigation_timeout(nav_timeout_ms)
                self.page.set_default_timeout(nav_timeout_ms)

                # Render/network can be slow and occasionally flaky; retry with progressively
                # looser wait conditions instead of failing the whole scrape on first timeout.
                nav_attempts = [
                    ("load", nav_timeout_ms),
                    ("domcontentloaded", nav_timeout_ms),
                    ("commit", max(30000, nav_timeout_ms // 2)),
                ]
                last_nav_error = None
                for idx, (wait_until, timeout_ms) in enumerate(nav_attempts, start=1):
                    try:
                        print(
                            f"↻ goto attempt {idx}/{len(nav_attempts)} "
                            f"(wait_until={wait_until}, timeout={timeout_ms}ms)"
                        )
                        self.page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                        last_nav_error = None
                        break
                    except Exception as e:
                        last_nav_error = e
                        print(f"⚠ goto attempt {idx} failed: {e}")
                        # Lightweight recovery before retrying.
                        try:
                            self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except Exception:
                            pass
                        _scrape_sleep(1.0)
                if last_nav_error is not None:
                    raise last_nav_error

                _scrape_sleep(_SCRAPE_AFTER_GOTO)

                print(f"Page title: {self.page.title()}")

                # Check JavaScript is working
                try:
                    js_test = self.page.evaluate("() => true")
                    print(f"JavaScript enabled: {js_test}")
                except Exception as e:
                    print(f"⚠️  JavaScript error: {e}")

                # Check for Cloudflare or encoding issues
                page_content = self.page.content()

                # Check if we got garbled content
                if page_content[:100].count('�') > 5 or page_content[:100].count('\\x') > 5:
                    print("⚠️  Garbled content detected - trying reload...")
                    self.page.reload(wait_until="domcontentloaded")
                    _scrape_sleep(_SCRAPE_AFTER_RELOAD)
                    page_content = self.page.content()

                if "cloudflare" in page_content.lower() or "verify you are human" in page_content.lower():
                    print("⚠️  Cloudflare detected - waiting for auto-resolution...")
                    _scrape_sleep(_SCRAPE_CLOUDFLARE)

                # STEP 0: Handle cookies and start quote button
                self._step0_cookies_and_start()

                # STEP 1: Enter email
                self._step1_enter_email()

                # STEP 2: Postcode and address
                self._step2_postcode_and_address(postcode, address_index, address_name)

                # STEP 3: Home or Business – user choice: "No, it's a home" or "Yes, it's a business"
                self._step3_home_or_business(home_or_business)
                _scrape_sleep(_SCRAPE_BEFORE_FUEL)  # Let fuel type options appear

                # STEP 4: Select fuel type
                self._step4_select_fuel_type(fuel_type)

                # STEP 4b: Supplier details (new required section on comparison form)
                self._step4b_supplier_details(current_supplier)

                # STEP 5: Select EV option
                self._step5_select_ev(has_ev)

                # STEP 6: See results
                self._step6_see_results()

                # Wait for results to load (page may render cards via JS)
                print("Waiting for results...")
                _scrape_sleep(_SCRAPE_RESULTS_POLL)
                result_selectors = [
                    ".results-new-item",
                    "[data-testid*='result']",
                    "[data-testid*='tariff']",
                    ".tariff-card",
                    ".deal-card",
                    ".result-card",
                    "article",
                ]
                # Wait for at least one result card or common container to appear
                for selector in result_selectors:
                    try:
                        self.page.wait_for_selector(selector, timeout=12000)
                        _scrape_sleep(_SCRAPE_AFTER_RESULTS_SELECTOR)
                        break
                    except Exception:
                        continue
                # If still on enquiry form, click "See results" again and wait a bit longer.
                try:
                    if self.page.locator(".enquiry-view-new__form").first.is_visible(timeout=1000):
                        retry_btn = self.page.locator(
                            "button[data-qa='enquiry-submit-button'], button:has-text('See results')"
                        ).first
                        if retry_btn.is_visible(timeout=1000):
                            retry_btn.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            retry_btn.click()
                            print("↻ Clicked 'See results' again (still on enquiry form)")
                            try:
                                self.page.wait_for_load_state("domcontentloaded", timeout=12000)
                            except Exception:
                                try:
                                    self.page.wait_for_load_state("networkidle", timeout=8000)
                                except Exception:
                                    pass
                            for selector in result_selectors:
                                try:
                                    self.page.wait_for_selector(selector, timeout=12000)
                                    break
                                except Exception:
                                    continue
                except Exception:
                    pass
                _scrape_sleep(_SCRAPE_AFTER_RESULTS_SELECTOR)

                # Get results HTML
                html = self.page.content()
                self.soup = BeautifulSoup(html, 'lxml')

                # Save for debugging (non-fatal: if this fails, we still extract from self.soup)
                try:
                    with open(_debug_path('results_page.html'), 'w', encoding='utf-8') as f:
                        f.write(self.soup.prettify())
                    print("💾 Saved results to 'output/scrape_debug/results_page.html'")
                except Exception as save_err:
                    print(f"⚠ Could not save debug HTML: {save_err}")

                # Extract tariff data for all result cards
                self.tariff = self._extract_tariff_data()

                # Persist each tariff to the database
                for t in self.tariff:
                    try:
                        t.save(current_supplier, pay_method, has_ev)
                    except Exception as db_err:
                        print(f"⚠ Failed to save tariff '{t.new_supplier_name} - {t.tariff_name}': {db_err}")

                return self.tariff

        except Exception as e:
            print(f"❌ Error: {e}")
            err_low = str(e).lower()
            is_target_closed = (
                "targetclosederror" in err_low
                or "target page, context or browser has been closed" in err_low
                or "page has been closed" in err_low
            )
            if is_target_closed and _retry_on_target_closed:
                print("↻ TargetClosed detected; restarting browser and retrying scrape once...")
                # Drop stale handles before retrying a clean browser session.
                self.page = None
                self.browser = None
                return self.scrape(
                    postcode=postcode,
                    address_index=address_index,
                    address_name=address_name,
                    fuel_type=fuel_type,
                    current_supplier=current_supplier,
                    pay_method=pay_method,
                    has_ev=has_ev,
                    home_or_business=home_or_business,
                    headless=headless,
                    _retry_on_target_closed=False,
                )
            if self.page:
                try:
                    self.page.screenshot(path=_debug_path('error_screenshot.png'))
                    with open(_debug_path('error_page.html'), 'w', encoding='utf-8') as f:
                        f.write(self.page.content())
                    print("📸 Saved error screenshot and HTML")
                except Exception:
                    pass
            # Release refs before context manager closes to reduce risk of double-close crash
            self.page = None
            self.browser = None
            raise

        finally:
            print("Browser closed")

    def _step0_cookies_and_start(self):
        """STEP 0: Handle cookie banner and click 'Start a quote' button"""

        print("\n--- STEP 0: Cookies & Start Quote ---")

        try:
            # 1. HANDLE COOKIES
            cookie_button_selectors = [
                "#onetrust-accept-btn-handler",
                "button:has-text('Accept')",
                "button:has-text('accept')",
                "button[class*='accept']",
                "#onetrust-reject-all-handler",
                "button:has-text('Reject')",
                "button:has-text('reject')",
                "button[class*='reject']",
                "button:has-text('Close')",
                "button:has-text('Dismiss')"
            ]

            cookie_handled = False
            for selector in cookie_button_selectors:
                try:
                    cookie_btn = self.page.locator(selector).first
                    if cookie_btn.is_visible(timeout=2000):
                        cookie_btn.click()
                        print(f"✓ Clicked cookie button using: {selector}")
                        cookie_handled = True
                        _scrape_sleep(_SCRAPE_AFTER_CLICK)
                        break
                except:
                    continue

            if not cookie_handled:
                print("⚠ No cookie banner found (or already dismissed)")

            # DEBUG: Let's see what's actually on the page
            print("\n--- DEBUG: Checking page state ---")
            print(f"Current URL: {self.page.url}")

            # Wait a bit for page to fully load
            _scrape_sleep(_SCRAPE_AFTER_CLICK)

            # Check for various CTA buttons
            all_cta_buttons = self.page.locator("a[class*='cta']").count()
            print(f"Found {all_cta_buttons} elements with 'cta' in class")

            all_links_with_quote = self.page.locator("a:has-text('quote')").count()
            print(f"Found {all_links_with_quote} links containing 'quote'")

            # Try to get the actual HTML of CTA buttons
            try:
                cta_elements = self.page.locator("a[class*='cta']").all()
                for i, elem in enumerate(cta_elements[:3]):  # Just first 3
                    try:
                        html = elem.evaluate("el => el.outerHTML")
                        print(f"\nCTA Element {i + 1}:")
                        print(html[:200])  # First 200 chars
                    except:
                        pass
            except:
                pass

            # 2. CLICK "START A QUOTE" BUTTON
            start_quote_selectors = [
                "a.cta-button.cta-button--primary-mega",
                "a[class*='cta-button--primary-mega']",
                "a[class*='cta-button'][class*='primary']",
                "a:has-text('Start a quote')",
                "a:has-text('Start quote')",
                "button:has-text('Start a quote')",
                "button:has-text('Start quote')",
                "a[class*='cta']",
            ]

            quote_started = False
            for selector in start_quote_selectors:
                try:
                    print(f"Trying selector: {selector}")
                    start_btn = self.page.locator(selector).first
                    if start_btn.is_visible(timeout=3000):
                        start_btn.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_PRE_CLICK)

                        try:
                            start_btn.click(timeout=5000)
                        except:
                            print(f"  Regular click failed, trying force click...")
                            start_btn.click(force=True)

                        print(f"✓ Clicked 'Start a quote' using: {selector}")
                        quote_started = True
                        _scrape_sleep(_SCRAPE_AFTER_SUBMIT)
                        break
                except Exception as e:
                    print(f"  Failed: {type(e).__name__}")
                    continue

            if not quote_started:
                print("\n✗ Failed to find 'Start a quote' button")
                print("Taking screenshot for debugging...")
                self.page.screenshot(path=_debug_path("debug_no_start_button.png"))

                # Also save the full HTML
                html_content = self.page.content()
                with open(_debug_path("debug_page_content.html"), "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("✓ Saved debug_no_start_button.png and debug_page_content.html")

                # Don't raise error - maybe we're already on the form
                print("⚠ Could not find 'Start a quote' button - may already be on form")

        except Exception as e:
            print(f"✗ Error in step 0: {str(e)}")
            raise

    def _step1_enter_email(self):
        """STEP 1: Enter randomly generated email address"""

        print("\n--- STEP 1: Enter Email ---")

        try:
            # Generate random email
            import random
            import string

            random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            random_email = f"user{random_string}@example.com"

            print(f"Generated email: {random_email}")

            # Give the page a moment to render the email step/field.
            # Then attempt to locate the email input robustly.
            _scrape_sleep(_SCRAPE_AFTER_CLICK)

            # Try different selectors for email input
            email_selectors = [
                # Common explicit email inputs
                "input[type='email']",
                "input[name*='email']",
                "input[id*='email']",
                "input[name='email']",
                "input#email",

                # Often uses type="text" but label/attributes indicate email
                "input[type='text'][name*='email']",
                "input[type='text'][id*='email']",
                "input[autocomplete*='email']",
                "input[aria-label*='email']",
                "input[placeholder*='email']",
                "input[placeholder*='Email']",
                "input[placeholder*='e-mail']",
                "input[placeholder*='E-mail']",
                "input[name*='Email']",
                "input[id*='Email']",
                "input[data-testid*='email']",
                "input[data-testid*='Email']",
            ]

            email_entered = False
            email_input = None
            for selector in email_selectors:
                try:
                    candidate = self.page.locator(selector).first
                    # Wait until attached and visible.
                    candidate.wait_for(state="visible", timeout=5000)

                    candidate.scroll_into_view_if_needed()
                    _scrape_sleep(_SCRAPE_MICRO)

                    # Clear any existing text and enter email
                    candidate.click()
                    candidate.fill(random_email)

                    email_input = candidate
                    print(f"✓ Entered email using: {selector}")
                    email_entered = True
                    _scrape_sleep(_SCRAPE_PRE_CLICK)
                    break
                except Exception as e:
                    continue

            if not email_entered:
                print("✗ Failed to find email input field")
                self.page.screenshot(path=_debug_path("debug_no_email_field.png"))
                raise Exception("Could not locate email input field")

            # Now click submit/continue button
            submit_selectors = [
                "button[type='submit']",
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button:has-text('Get quotes')",
                "button:has-text('Submit')",
                "input[type='submit']",
                "button[class*='submit']",
                "button[class*='continue']",
                "a:has-text('Continue')",
            ]

            submitted = False
            for selector in submit_selectors:
                try:
                    submit_btn = self.page.locator(selector).first
                    if submit_btn.is_visible(timeout=2000):
                        submit_btn.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_SHORT)
                        submit_btn.click()
                        print(f"✓ Clicked submit using: {selector}")
                        submitted = True
                        _scrape_sleep(_SCRAPE_AFTER_SUBMIT)
                        break
                except:
                    continue

            if not submitted:
                print("⚠ Could not find submit button - may need to press Enter")
                # Try pressing Enter on the email field
                try:
                    if email_input is not None:
                        email_input.press("Enter")
                    print("✓ Pressed Enter on email field")
                    _scrape_sleep(_SCRAPE_AFTER_SUBMIT)
                except:
                    print("✗ Failed to submit form")
                    self.page.screenshot(path=_debug_path("debug_no_submit.png"))

            print(f"✓ Step 1 complete - email entered: {random_email}")

        except Exception as e:
            print(f"✗ Error in step 1: {str(e)}")
            raise

    def _step2_postcode_and_address(self, postcode: str, address_index: int, address_name: str = ''):
        """STEP 2: Enter postcode and select address"""

        print("\n--- STEP 2: Postcode & Address ---")

        try:
            def _is_target_closed_error(err: Exception) -> bool:
                msg = str(err or "").lower()
                return (
                    "targetclosederror" in msg
                    or "target page, context or browser has been closed" in msg
                    or "page has been closed" in msg
                )

            wanted = " ".join((address_name or "").strip().lower().split())
            if wanted:
                print(f"Address hint provided: {wanted!r}")

            def _normalize_text(s: str) -> str:
                return " ".join((s or "").strip().lower().split())

            def _matches_wanted(s: str) -> bool:
                if not wanted:
                    return False
                txt = _normalize_text(s)
                if not txt:
                    return False
                # Exact contains first.
                if wanted in txt:
                    return True
                # Token overlap handles punctuation/order differences.
                wanted_tokens = set([t for t in re.split(r"[^a-z0-9]+", wanted) if t])
                txt_tokens = set([t for t in re.split(r"[^a-z0-9]+", txt) if t])
                if wanted_tokens and txt_tokens:
                    overlap = len(wanted_tokens & txt_tokens) / max(1, len(wanted_tokens))
                    if overlap >= 0.6:
                        return True
                # Fuzzy similarity tolerates minor typos/spelling mistakes.
                if SequenceMatcher(None, wanted, txt).ratio() >= 0.72:
                    return True
                return False
            # Find and fill postcode input
            postcode_input = None
            selectors = [
                "#postcode",
                "input[name='postcode']",
                "input[name*='postcode']",
                "input[id*='postcode']",
                "input[placeholder*='postcode' i]",
                "input[type='text']"
            ]

            for selector in selectors:
                try:
                    postcode_input = self.page.locator(selector).first
                    if postcode_input.is_visible(timeout=5000):
                        print(f"✓ Found postcode input using: {selector}")
                        break
                except:
                    continue

            if not postcode_input:
                raise Exception("Could not find postcode input field")

            # Type slowly like a human
            postcode_input.clear()
            postcode_input.type(postcode, delay=_typing_delay_ms())

            print(f"✓ Entered postcode: {postcode}")

            # Submit postcode
            _scrape_sleep(_SCRAPE_PRE_CLICK)
            try:
                postcode_input.press("Enter")
                print("✓ Submitted postcode (Enter key)")
            except Exception:
                try:
                    submit_btn = self.page.locator(
                        "button[type='submit'], button:has-text('Continue'), button:has-text('Next'), button:has-text('Find')"
                    ).first
                    submit_btn.click()
                    print("✓ Submitted postcode (button click)")
                except Exception:
                    print("⚠ Could not submit - trying to continue anyway")

            _scrape_sleep(_SCRAPE_POSTCODE_DOM)

            # Open combobox-style address fields (click triggers fetch of address list)
            for open_sel in [
                '[role="combobox"]',
                'input[aria-autocomplete="list"]',
                'input[aria-haspopup="listbox"]',
                '[data-testid*="address" i] input',
                'input[placeholder*="address" i]',
            ]:
                try:
                    loc = self.page.locator(open_sel).first
                    if loc.is_visible(timeout=1500):
                        loc.click(timeout=2000)
                        _scrape_sleep(_SCRAPE_SHORT)
                        print(f"✓ Opened possible address control: {open_sel}")
                        break
                except Exception:
                    continue

            address_selected = False

            # Poll until address UI has choices (async postcode lookup)
            deadline = time.monotonic() + _SCRAPE_ADDRESS_UI_MAX_WAIT
            while time.monotonic() < deadline and not address_selected:
                # --- Native <select> (prefer specific selectors; avoid first random <select> on page) ---
                dropdown_selectors = [
                    "#address",
                    "select[name*='address' i]",
                    "select[id*='address' i]",
                    "select[class*='address' i]",
                ]
                for selector in dropdown_selectors:
                    try:
                        address_dropdown = self.page.locator(selector).first
                        if not address_dropdown.is_visible(timeout=800):
                            continue
                        n_opts = address_dropdown.locator("option").count()
                        if n_opts < 2:
                            continue
                        print(f"✓ Found address <select> using: {selector} ({n_opts} options)")

                        address_dropdown.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_SHORT)

                        options = address_dropdown.locator("option").all()
                        for i, option in enumerate(options[:5]):
                            text = (option.text_content() or "").strip()
                            print(f"  {i}: {text[:60]}")

                        if wanted:
                            matched_idx = None
                            for i, option in enumerate(options):
                                txt = (option.text_content() or "").strip()
                                if _matches_wanted(txt):
                                    matched_idx = i
                                    break
                            if matched_idx is not None:
                                address_dropdown.select_option(index=matched_idx)
                                print(
                                    f"✓ Selected address by name match: "
                                    f"{(options[matched_idx].text_content() or '')[:80]}"
                                )
                                address_selected = True
                                break

                        first_option_text = (options[0].text_content() or "").lower()
                        is_placeholder = any(
                            word in first_option_text for word in ("select", "choose", "please", "--", "pick")
                        )

                        if is_placeholder:
                            actual_index = address_index + 1
                            if len(options) > actual_index:
                                address_dropdown.select_option(index=actual_index)
                                print(
                                    f"✓ Selected address (skipped placeholder): "
                                    f"{(options[actual_index].text_content() or '')[:60]}"
                                )
                                address_selected = True
                        elif len(options) > address_index:
                            address_dropdown.select_option(index=address_index)
                            print(f"✓ Selected address {address_index}: {(options[address_index].text_content() or '')[:60]}")
                            address_selected = True

                        if address_selected:
                            break
                    except Exception as e:
                        if _is_target_closed_error(e):
                            raise Exception(
                                "Browser/page closed during address selection (TargetClosedError). "
                                "Likely browser crash or container memory pressure."
                            ) from e
                        print(f"  <select> {selector}: {type(e).__name__}")
                        continue

                if address_selected:
                    break

                # Any visible <select> with multiple real-looking options (last resort)
                if not address_selected:
                    try:
                        for i in range(self.page.locator("select").count()):
                            sel = self.page.locator("select").nth(i)
                            if not sel.is_visible(timeout=500):
                                continue
                            n = sel.locator("option").count()
                            if n < 2:
                                continue
                            opts = sel.locator("option").all()
                            texts = [(o.text_content() or "").strip().lower() for o in opts[:3]]
                            if any("postcode" in t for t in texts if t):
                                continue
                            print(f"✓ Using visible <select> #{i} with {n} options")
                            sel.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            if wanted:
                                matched_idx = None
                                for opt_idx, opt in enumerate(opts):
                                    txt = (opt.text_content() or "").strip()
                                    if _matches_wanted(txt):
                                        matched_idx = opt_idx
                                        break
                                if matched_idx is not None:
                                    sel.select_option(index=matched_idx)
                                    address_selected = True
                                    print(f"✓ Selected visible <select> option by address name at index {matched_idx}")
                                    break
                            first = (opts[0].text_content() or "").lower()
                            skip = any(w in first for w in ("select", "choose", "please", "--", "pick"))
                            idx = address_index + (1 if skip else 0)
                            if len(opts) > idx:
                                sel.select_option(index=idx)
                                address_selected = True
                                print(f"✓ Selected option index {idx}")
                                break
                    except Exception as e:
                        if _is_target_closed_error(e):
                            raise Exception(
                                "Browser/page closed during address selection (TargetClosedError). "
                                "Likely browser crash or container memory pressure."
                            ) from e
                        print(f"  Generic select scan: {type(e).__name__}")

                if address_selected:
                    break

                # --- Custom lists: role=option, MUI/React menus ---
                for list_selector in [
                    '[role="listbox"] [role="option"]',
                    '[role="listbox"] li',
                    "div[role='option']",
                    '[data-testid*="address" i]',
                    '[data-testid*="suggestion" i]',
                    ".address-list li",
                    '[class*="Address"] [class*="option" i]',
                    'ul[class*="menu" i] li',
                    'div[class*="menu" i] [role="option"]',
                ]:
                    try:
                        opts = self.page.locator(list_selector)
                        cnt = opts.count()
                        if cnt <= address_index:
                            continue
                        # Skip empty or heading rows
                        visible_idx = 0
                        for j in range(min(cnt, 30)):
                            o = opts.nth(j)
                            if not o.is_visible(timeout=300):
                                continue
                            txt = (o.text_content() or "").strip().lower()
                            if not txt or any(x in txt for x in ("select", "choose address", "search")):
                                continue
                            if wanted and _matches_wanted(txt):
                                o.scroll_into_view_if_needed()
                                _scrape_sleep(_SCRAPE_MICRO)
                                o.click()
                                print(f"✓ Clicked address list item by name via: {list_selector} → {txt[:80]}")
                                address_selected = True
                                break
                            if visible_idx == address_index:
                                o.scroll_into_view_if_needed()
                                _scrape_sleep(_SCRAPE_MICRO)
                                o.click()
                                print(f"✓ Clicked address list item via: {list_selector} → {txt[:50]}")
                                address_selected = True
                                break
                            visible_idx += 1
                        if address_selected:
                            break
                    except Exception as e:
                        if _is_target_closed_error(e):
                            raise Exception(
                                "Browser/page closed during address selection (TargetClosedError). "
                                "Likely browser crash or container memory pressure."
                            ) from e
                        print(f"  List {list_selector}: {type(e).__name__}")
                        continue

                if address_selected:
                    break

                _scrape_sleep(0.45)

            if address_selected:
                _scrape_sleep(_SCRAPE_PRE_CLICK)

            if not address_selected:
                if wanted:
                    print(f"⚠ Address name match not found for {wanted!r}; no fallback selection succeeded.")
                print("✗ Failed to select address")
                try:
                    if self.page is not None and not self.page.is_closed():
                        self.page.screenshot(path=_debug_path('step2_address_error.png'))
                        with open(_debug_path("step2_address_page.html"), "w", encoding="utf-8") as f:
                            f.write(self.page.content())
                        print("Saved debug files: step2_address_error.png and step2_address_page.html")
                except Exception:
                    pass
                raise Exception("Could not select address from dropdown")

            # Submit address selection
            _scrape_sleep(_SCRAPE_PRE_CLICK)
            continue_clicked = False
            continue_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button[type='submit']",
                "button:has-text('Proceed')",
                "input[type='submit']",
            ]

            for selector in continue_selectors:
                try:
                    continue_btn = self.page.locator(selector).first
                    if continue_btn.is_visible(timeout=2000):
                        continue_btn.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_SHORT)
                        continue_btn.click()
                        print(f"✓ Clicked continue button using: {selector}")
                        continue_clicked = True
                        break
                except:
                    continue

            if not continue_clicked:
                print("⚠ No continue button found after address - may auto-submit")

            _scrape_sleep(_SCRAPE_AFTER_SUBMIT)
            print("✓ Step 2 complete")

        except Exception as e:
            print(f"✗ Error in Step 2: {e}")
            try:
                if self.page is not None and not self.page.is_closed():
                    self.page.screenshot(path=_debug_path('step2_error.png'))
            except Exception:
                pass
            raise

    def _step3_home_or_business(self, home_or_business: str = 'home'):
        """STEP 3: Select 'No, it's a home' or 'Yes, it's a business' so fuel type options appear."""

        is_business = (home_or_business or '').strip().lower() in ('business', 'yes', 'true', '1')
        choice = "business" if is_business else "home"
        print(f"\n--- STEP 3: Home or Business ({choice}) ---")

        try:
            _scrape_sleep(_SCRAPE_AFTER_CLICK)

            if is_business:
                # "Yes, it's a business"
                button_texts = [
                    "Yes, it's a business",
                    "Yes it's a business",
                    "It's a business",
                    "Business",
                ]
                selectors = [
                    "button:has-text(\"Yes, it's a business\")",
                    "a:has-text(\"Yes, it's a business\")",
                    "label:has-text(\"Yes, it's a business\")",
                    "[role='button']:has-text(\"Yes, it's a business\")",
                    "button:has-text('Business')",
                    "a:has-text('Business')",
                ]
            else:
                # "No, it's a home"
                button_texts = [
                    "No, it's a home",
                    "No it's a home",
                    "It's a home",
                    "No, just home",
                    "Just home",
                    "Home",
                ]
                selectors = [
                    "button:has-text(\"No, it's a home\")",
                    "a:has-text(\"No, it's a home\")",
                    "label:has-text(\"No, it's a home\")",
                    "[role='button']:has-text(\"No, it's a home\")",
                    "button:has-text('No, just home')",
                    "a:has-text('No, just home')",
                    "button:has-text('Just home')",
                    "a:has-text('Just home')",
                    "button:has-text('Home')",
                    "a:has-text('Home')",
                    "label:has-text('Home')",
                ]

            found = False
            for selector in selectors:
                try:
                    btn = self.page.locator(selector).first
                    if btn.is_visible(timeout=2000):
                        btn.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_SHORT)
                        btn.click()
                        print(f"✓ Selected '{choice}' using: {selector}")
                        found = True
                        _scrape_sleep(_SCRAPE_AFTER_CLICK)
                        break
                except Exception:
                    continue

            if not found:
                for text in button_texts:
                    try:
                        loc = self.page.get_by_text(text, exact=False).first
                        if loc.is_visible(timeout=1500):
                            loc.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            loc.click()
                            print(f"✓ Selected '{choice}' (get_by_text: {text!r})")
                            found = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                            break
                    except Exception:
                        continue

            if not found:
                print(f"⚠ No '{choice}' button found - skipping (fuel type step may fail)")

        except Exception as e:
            print(f"⚠ Error in step 3 (non-critical): {str(e)}")

    def _step4_select_fuel_type(self, fuel_type: str):
        """STEP 4: Select fuel type (Gas, Gas & Electricity, or Electricity)"""

        print("\n--- STEP 4: Select Fuel Type ---")

        try:
            # Wait for fuel type options to appear
            _scrape_sleep(_SCRAPE_AFTER_CLICK)

            # Save page state for debugging if step fails (so we can inspect structure)
            def _save_step4_debug():
                try:
                    self.page.screenshot(path=_debug_path('step4_fuel_type_error.png'))
                    with open(_debug_path("step4_fuel_page.html"), "w", encoding="utf-8") as f:
                        f.write(self.page.content())
                    print("Saved debug files: step4_fuel_type_error.png and step4_fuel_page.html")
                except Exception:
                    pass

            # Map fuel_type parameter to button/link text (site may use various wordings)
            # Note: MoneySupermarket uses "Gas  & Electicity" (two spaces, typo) - include exact match
            fuel_type_map = {
                'gas': ['Gas', 'gas', 'Gas only', 'Gas only tariffs', 'I only use gas'],
                'both': [
                    'Gas  & Electicity',  # exact as on site (two spaces, typo)
                    'Gas & Electricity', 'Gas and Electricity', 'Both', 'Dual fuel', 'Gas & Electric',
                    'Gas and Electric', 'Gas & electricity', 'Gas and electricity', 'Compare both',
                    'Dual', 'I have both', 'Gas and electricity', 'Dual fuel tariffs',
                    'I use both gas and electricity', 'Gas & Electricity tariffs',
                ],
                'electricity': [
                    'Electricity', 'electricity', 'Electric', 'Electricity only', 'Electric only',
                    'Electricity only tariffs', 'I only use electricity', 'Electric only tariffs',
                ],
            }

            # Normalise: accept gas_and_electricity / gas_and_electric as 'both'
            fuel_key = fuel_type.lower().strip()
            if fuel_key in ('gas_and_electricity', 'gas_and_electric', 'dual'):
                fuel_key = 'both'
            if fuel_key not in fuel_type_map:
                print(f"⚠ Invalid fuel_type: {fuel_type}. Using 'both' as default.")
                fuel_key = 'both'

            possible_texts = fuel_type_map[fuel_key]
            print(f"Looking for fuel type: {fuel_key} (possible texts: {possible_texts})")

            # Try to find and click the appropriate button
            fuel_selected = False

            # For 'both': try Playwright text= regex (matches any element with that text)
            if not fuel_selected and fuel_key == 'both':
                try:
                    loc = self.page.locator("text=/Gas\\s*&\\s*Electic/i").first
                    if loc.is_visible(timeout=2000):
                        loc.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_SHORT)
                        loc.click()
                        print("✓ Selected fuel type (text= regex)")
                        fuel_selected = True
                        _scrape_sleep(_SCRAPE_AFTER_CLICK)
                except Exception:
                    pass

            # For 'both': get_by_text with exact site string and with substring
            if not fuel_selected and fuel_key == 'both':
                for search_text in ["Gas  & Electicity", "Electicity", "Gas & Electic"]:
                    try:
                        loc = self.page.get_by_text(search_text, exact=False).first
                        if loc.is_visible(timeout=1500):
                            loc.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            loc.click()
                            print(f"✓ Selected fuel type (get_by_text: {search_text!r})")
                            fuel_selected = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                            break
                    except Exception:
                        continue

            # For 'both': JavaScript fallback – text may be split across child nodes
            if not fuel_selected and fuel_key == 'both':
                try:
                    clicked = self.page.evaluate("""
() => {
  var walk = function(el) {
    var text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    if (/Gas\\s*&\\s*Electic/i.test(text)) {
      var target = el.closest('button, a, [role=\"button\"], [onclick]') || el;
      try {
        target.click();
        return true;
      } catch (e) { return false; }
    }
    for (var i = 0; i < el.children.length; i++) {
      if (walk(el.children[i])) return true;
    }
    return false;
  };
  return walk(document.body);
}
                    """)
                    if clicked:
                        print("✓ Selected fuel type (JS: element containing Gas & Electic)")
                        fuel_selected = True
                        _scrape_sleep(_SCRAPE_AFTER_CLICK)
                except Exception as e:
                    print("  JS fallback:", str(e))

            # For 'both': try regex on button/link
            if not fuel_selected and fuel_key == 'both':
                for role_or_tag in ["button", "a"]:
                    try:
                        loc = self.page.locator(role_or_tag).filter(
                            has_text=re.compile(r"Gas\s*&\s*Electic", re.IGNORECASE)
                        ).first
                        if loc.is_visible(timeout=2000):
                            loc.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            loc.click()
                            print("✓ Selected fuel type (regex: Gas & Electic...)")
                            fuel_selected = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                            break
                    except Exception:
                        continue

            for text in possible_texts:
                if fuel_selected:
                    break

                # Try different element types
                selectors = [
                    f"button:has-text('{text}')",
                    f"a:has-text('{text}')",
                    f"label:has-text('{text}')",
                    f"div[role='button']:has-text('{text}')",
                    f"input[value='{text}']",
                    f"[data-testid]:has-text('{text}')",
                    f"[data-value]:has-text('{text}')",
                ]

                for selector in selectors:
                    try:
                        fuel_btn = self.page.locator(selector).first
                        if fuel_btn.is_visible(timeout=2000):
                            fuel_btn.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)

                            # Click the button/label
                            fuel_btn.click()
                            print(f"✓ Selected fuel type '{text}' using: {selector}")
                            fuel_selected = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                            break
                    except Exception:
                        continue

            # Fallback for 'both': any clickable containing both "gas" and "electric" (case-insensitive)
            if not fuel_selected and fuel_key == 'both':
                for fallback_selector in [
                    "button:has-text('Gas'):has-text('Electric')",
                    "a:has-text('Gas'):has-text('Electric')",
                    "button:has-text('Dual')",
                    "a:has-text('Dual')",
                ]:
                    try:
                        el = self.page.locator(fallback_selector).first
                        if el.is_visible(timeout=2000):
                            el.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            el.click()
                            print(f"✓ Selected fuel type (fallback selector: {fallback_selector})")
                            fuel_selected = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                            break
                    except Exception:
                        continue
                if not fuel_selected:
                    try:
                        combined = self.page.get_by_role("button").filter(has_text=re.compile(r"gas.*electric|electric.*gas", re.I)).first
                        if combined.is_visible(timeout=3000):
                            combined.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            combined.click()
                            print("✓ Selected fuel type (fallback: button containing 'gas' and 'electric')")
                            fuel_selected = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                    except Exception:
                        pass
                if not fuel_selected:
                    try:
                        combined = self.page.locator("a").filter(has_text=re.compile(r"gas.*electric|electric.*gas", re.I)).first
                        if combined.is_visible(timeout=3000):
                            combined.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)
                            combined.click()
                            print("✓ Selected fuel type (fallback: link containing 'gas' and 'electric')")
                            fuel_selected = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                    except Exception:
                        pass

            if not fuel_selected:
                print("✗ Failed to find fuel type selection")
                _save_step4_debug()
                raise Exception(f"Could not find fuel type option for: {fuel_type}")

            # Look for continue button
            _scrape_sleep(_SCRAPE_PRE_CLICK)
            continue_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button[type='submit']",
                "input[type='submit']",
            ]

            for selector in continue_selectors:
                try:
                    continue_btn = self.page.locator(selector).first
                    if continue_btn.is_visible(timeout=2000):
                        continue_btn.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_SHORT)
                        continue_btn.click()
                        print(f"✓ Clicked continue button")
                        break
                except:
                    continue

            _scrape_sleep(_SCRAPE_AFTER_SUBMIT)
            print("✓ Step 4 complete")

        except Exception as e:
            print(f"✗ Error in Step 4: {str(e)}")
            self.page.screenshot(path=_debug_path('step4_error.png'))
            raise

    def _step4b_supplier_details(self, current_supplier: str = ""):
        """
        STEP 4b: Fill supplier details required by newer flows.
        """
        print("\n--- STEP 4b: Supplier details ---")
        supplier_hint = (current_supplier or "").strip()
        try:
            _scrape_sleep(_SCRAPE_AFTER_CLICK)

            same_selected = False
            for sel in [
                "label:has-text('Do you have the same supplier for both your gas and electricity?')",
                ".enquiry-view-new__form__row:has-text('Do you have the same supplier for both your gas and electricity?')",
            ]:
                try:
                    sec = self.page.locator(sel).first
                    if not sec.is_visible(timeout=800):
                        continue
                    for yes_sel in ["label:has-text('Yes')", "button:has-text('Yes')", "[role='radio']:has-text('Yes')"]:
                        try:
                            yes = sec.locator(yes_sel).first
                            if yes.is_visible(timeout=800):
                                yes.click()
                                print("✓ Selected same-supplier: Yes")
                                same_selected = True
                                break
                        except Exception:
                            continue
                    break
                except Exception:
                    continue
            if not same_selected:
                print("⚠ Same-supplier section not found or not selectable")

            _scrape_sleep(_SCRAPE_SHORT)

            supplier_selected = False
            supplier_sections = [
                ".enquiry-current-supplier-selector",
                ".enquiry-view-new__form__row:has-text('Who is your current supplier?')",
            ]
            for sec_sel in supplier_sections:
                try:
                    sec = self.page.locator(sec_sel).first
                    if not sec.is_visible(timeout=1000):
                        continue
                    if supplier_hint:
                        try:
                            hit = sec.locator(f"label:has-text('{supplier_hint}')").first
                            if hit.is_visible(timeout=900):
                                hit.click()
                                print(f"✓ Selected current supplier: {supplier_hint}")
                                supplier_selected = True
                                break
                        except Exception:
                            pass
                    labels = sec.locator("label")
                    if labels.count() > 0:
                        first = labels.first
                        if first.is_visible(timeout=900):
                            txt = (first.text_content() or "").strip()
                            first.click()
                            print(f"✓ Selected first supplier option: {txt[:60]}")
                            supplier_selected = True
                            break
                except Exception:
                    continue
            if not supplier_selected:
                print("⚠ Current supplier section not found or not selectable")

            # 3) Payment type (if required): prefer Monthly Direct Debit.
            payment_selected = False
            for pay_sel in [
                "label:has-text('Monthly Direct Debit')",
                "input[name='dual-payments'][value='1']",
            ]:
                try:
                    el = self.page.locator(pay_sel).first
                    if el.is_visible(timeout=800):
                        el.click()
                        payment_selected = True
                        print("✓ Selected payment type: Monthly Direct Debit")
                        break
                except Exception:
                    continue
            if not payment_selected:
                print("⚠ Payment type section not found or not selectable")

            # 4) Current tariff dropdown (if required): choose first non-placeholder option.
            tariff_selected = False
            for tariff_sel in [
                "select[name='dual-tariffs']",
                "select[id*='tariff' i]",
                ".enquiry-tariff-selector select",
            ]:
                try:
                    dd = self.page.locator(tariff_sel).first
                    if not dd.is_visible(timeout=800):
                        continue
                    # Select by index skips placeholder in this flow.
                    dd.select_option(index=1)
                    tariff_selected = True
                    print(f"✓ Selected current tariff via: {tariff_sel}")
                    break
                except Exception:
                    continue
            if not tariff_selected:
                print("⚠ Current tariff selector not found or not selectable")

            print("✓ Step 4b complete")
        except Exception as e:
            print(f"⚠ Error in Step 4b (non-critical): {e}")
            print("Continuing to next step...")

    def _step5_select_ev(self, has_ev: str):
        """STEP 5: Select EV (electric vehicle) option"""

        print("\n--- STEP 5: Select EV Option ---")

        try:
            # Wait for EV options to appear
            _scrape_sleep(_SCRAPE_AFTER_CLICK)

            # Determine which option to select based on has_ev parameter
            # Normalize the input to handle variations
            ev_question_lower = has_ev.lower().strip()
            
            # Determine which option to select based on EV_question parameter
            if ev_question_lower in ['yes', 'y']:
                ev_options = ['Yes', 'yes', 'I have an EV', 'I have an electric vehicle']
                print("Selecting: Yes (has EV)")
            elif ev_question_lower in ['no but interested', 'no but considering', 'interested', 'considering']:
                ev_options = ['No, but considering', 'No but considering', 'Considering', 'Maybe',
                              'Planning to get one', 'No but interested']
                print("Selecting: No, but interested")
            else:  # Default to "No"
                ev_options = ['No', 'no', 'I don\'t have an EV', 'I do not have an EV']
                print("Selecting: No")

            # Try to find and click the appropriate option
            ev_selected = False

            # Prefer direct radio selection by known field name.
            try:
                ev_val = "NO"
                if ev_question_lower in ['yes', 'y']:
                    ev_val = "YES"
                elif ev_question_lower in ['no but interested', 'no but considering', 'interested', 'considering']:
                    ev_val = "CONSIDERING"
                radio = self.page.locator(f"input[name='electric-vehicle-ownership-selector'][value='{ev_val}']").first
                if radio.is_visible(timeout=1500):
                    radio.check(force=True)
                    ev_selected = True
                    print(f"✓ Selected EV option via input value: {ev_val}")
                    _scrape_sleep(_SCRAPE_AFTER_CLICK)
            except Exception:
                pass

            for text in ev_options:
                if ev_selected:
                    break

                # Try different element types
                selectors = [
                    f"button:has-text('{text}')",
                    f"a:has-text('{text}')",
                    f"label:has-text('{text}')",
                    f"div[role='button']:has-text('{text}')",
                    f"input[value*='{text}' i]",
                    f"label:text-is('{text}')",
                ]

                for selector in selectors:
                    try:
                        ev_btn = self.page.locator(selector).first
                        if ev_btn.is_visible(timeout=2000):
                            ev_btn.scroll_into_view_if_needed()
                            _scrape_sleep(_SCRAPE_SHORT)

                            # Click the button/label
                            ev_btn.click()
                            print(f"✓ Selected EV option '{text}' using: {selector}")
                            ev_selected = True
                            _scrape_sleep(_SCRAPE_AFTER_CLICK)
                            break
                    except:
                        continue

            # If still not selected, try a simpler "No" option as last resort
            if not ev_selected and not has_ev:
                no_options = ['No', 'no', 'I don\'t have an EV']
                print("Trying simple 'No' option as fallback...")

                for text in no_options:
                    selectors = [
                        f"button:has-text('{text}')",
                        f"label:has-text('{text}')",
                    ]

                    for selector in selectors:
                        try:
                            no_btn = self.page.locator(selector).first
                            if no_btn.is_visible(timeout=2000):
                                no_btn.scroll_into_view_if_needed()
                                _scrape_sleep(_SCRAPE_SHORT)
                                no_btn.click()
                                print(f"✓ Selected '{text}' as fallback")
                                ev_selected = True
                                _scrape_sleep(_SCRAPE_AFTER_CLICK)
                                break
                        except:
                            continue
                    if ev_selected:
                        break

            if not ev_selected:
                print("⚠ Failed to find EV selection - may be optional")
                self.page.screenshot(path=_debug_path('step5_ev_error.png'))
                # Don't raise error - EV question might be optional
                print("⚠ Continuing without EV selection")
                return

            # Guard: if validation still says EV status missing, fail this step explicitly.
            ev_still_invalid = False
            try:
                ev_error = self.page.locator("text=Must select an electric vehicle ownership status").first
                if ev_error.is_visible(timeout=600):
                    ev_still_invalid = True
            except Exception:
                ev_still_invalid = False
            if ev_still_invalid:
                raise Exception("EV validation still failing after selection")

            # Look for continue button
            _scrape_sleep(_SCRAPE_PRE_CLICK)
            continue_selectors = [
                "button:has-text('Continue')",
                "button:has-text('Next')",
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Get quotes')",
                "button:has-text('Show results')",
            ]

            continue_clicked = False
            for selector in continue_selectors:
                try:
                    continue_btn = self.page.locator(selector).first
                    if continue_btn.is_visible(timeout=2000):
                        continue_btn.scroll_into_view_if_needed()
                        _scrape_sleep(_SCRAPE_SHORT)
                        continue_btn.click()
                        print(f"✓ Clicked continue button")
                        continue_clicked = True
                        break
                except:
                    continue

            if not continue_clicked:
                print("⚠ No continue button found - may auto-proceed")

            _scrape_sleep(_SCRAPE_AFTER_SUBMIT)
            print("✓ Step 5 complete")

        except Exception as e:
            print(f"⚠ Error in Step 5 (non-critical): {str(e)}")
            # Don't raise - this might be optional
            print("Continuing to next step...")

    def _step6_see_results(self):
        """STEP 6: See quote results by selecting button"""

        print("\n--- STEP 6: See results ---")

        try:
            # 1. HANDLE COOKIES
            results_button_selectors = [
                "#onetrust-results-btn-handler",
                "button:has-text('See results')",
                "button:has-text('results')",
                "button[class*='reslts']"
            ]

            results_handled = False
            for selector in results_button_selectors:
                try:
                    results_btn = self.page.locator(selector).first
                    if results_btn.is_visible(timeout=2000):
                        results_btn.click()
                        print(f"✓ Clicked results button using: {selector}")
                        results_handled = True
                        _scrape_sleep(_SCRAPE_AFTER_CLICK)
                        break
                except:
                    continue

            if not results_handled:
                print("⚠ No cookie banner found (or already dismissed)")

        except Exception as e:
            print(f"✗ Error in step 6: {str(e)}")
            raise


    def _extract_tariff_data(self) -> List[Tariff]:
        """Extract tariff data for all tariff result cards on the page."""

        # Try multiple selectors – site may have changed class names
        CARD_SELECTORS = [
            ".results-new-item",
            "[data-testid*='tariff']",
            "[data-testid*='result']",
            ".tariff-card",
            ".deal-card",
            ".result-card",
            ".energy-deal",
            ".product-card",
            ".comparison-result",
            "article[class*='result']",
            "article[class*='tariff']",
            "li[class*='result']",
            "li[class*='tariff']",
            "[class*='results-new-item']",
            "[class*='tariff-card']",
        ]
        cards = []
        for sel in CARD_SELECTORS:
            cards = self.soup.select(sel)
            if len(cards) >= 1:
                print(f"  Found {len(cards)} cards using selector: {sel}")
                break
        if not cards:
            # Log sample of class names in the page to help debug
            all_classes = set()
            for tag in self.soup.find_all(class_=True):
                c = tag.get("class") or []
                for cl in c:
                    if isinstance(cl, str):
                        all_classes.add(cl)
            sample = sorted(all_classes)[:40]
            print("  No tariff cards found. Sample class names on page:", sample)
            raise Exception(
                "Could not find any tariff result cards in results_page.html. "
                "The comparison site may have changed its HTML. Check output/scrape_debug/results_page.html "
                "and look for the class used for each tariff/result card, then add it to CARD_SELECTORS in _extract_tariff_data."
            )

        def build_tariff_from_card(card) -> Tariff:
            # Annual cost from page-level usage callout (may be absent if layout changed)
            annual_cost_ = 0
            cost_span = self.soup.find(
                "span",
                class_="current-usage-card__callout__value",
                string=re.compile("/yr")
            )
            if cost_span:
                text = cost_span.get_text(strip=True)
                m = re.search(r"£([\d,]+)/yr", text, re.IGNORECASE)
                if m:
                    try:
                        annual_cost_ = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass
                else:
                    m = re.search(r"£([\d,]+)/mo", text, re.IGNORECASE)
                    if m:
                        try:
                            annual_cost_ = int(m.group(1).replace(",", "")) * 12
                        except ValueError:
                            pass

            annual_electricity_kwh = None
            annual_gas_kwh = None
            
            usage_overview = self.soup.select_one(".current-usage-overview")

            if usage_overview:
                fuel_sections = usage_overview.select(".current-usage-overview__fuel")
                for fuel_section in fuel_sections:
                    # Find the fuel type and consumption spans that are siblings
                    fuel_type_span = fuel_section.select_one(".current-usage-overview__consumption__type")
                    
                    if fuel_type_span:
                        fuel_type_text = fuel_type_span.get_text(strip=True).lower()
                        
                        # The consumption value is the next sibling span
                        consumption_span = fuel_type_span.find_next_sibling("span")
                        
                        if consumption_span:
                            consumption_text = consumption_span.get_text(strip=True)
                            print(f"  Found {fuel_type_text}: {consumption_text}")
                            value = _usage_text_to_annual_kwh(consumption_text)
                            if value is not None:
                                if "gas" in fuel_type_text:
                                    annual_gas_kwh = value
                                elif "electric" in fuel_type_text:
                                    annual_electricity_kwh = value

            # Fallbacks for newer/variant markup where usage appears outside .current-usage-overview.
            if annual_electricity_kwh is None or annual_gas_kwh is None:
                usage_blocks = self.soup.select(
                    ".enquiry-usage-prepop__container__item, .enquiry-usage, [class*='usage-prepop']"
                )
                for block in usage_blocks:
                    text = block.get_text(" ", strip=True)
                    low = text.lower()
                    value = _usage_text_to_annual_kwh(text)
                    if value is None:
                        continue
                    if annual_electricity_kwh is None and "electric" in low:
                        annual_electricity_kwh = value
                    if annual_gas_kwh is None and "gas" in low:
                        annual_gas_kwh = value

            # Last-resort parse from full page text.
            if annual_electricity_kwh is None or annual_gas_kwh is None:
                page_text = self.soup.get_text(" ", strip=True)
                if annual_gas_kwh is None:
                    m = re.search(r"gas[^\\d]{0,40}([\\d,]+)\\s*kwh(?:\\s*/\\s*(year|yr|month|mo))?", page_text, re.IGNORECASE)
                    if m:
                        annual_gas_kwh = _usage_text_to_annual_kwh(f"{m.group(1)} kWh / {m.group(2) or 'year'}")
                if annual_electricity_kwh is None:
                    m = re.search(r"electric(?:ity)?[^\\d]{0,40}([\\d,]+)\\s*kwh(?:\\s*/\\s*(year|yr|month|mo))?", page_text, re.IGNORECASE)
                    if m:
                        annual_electricity_kwh = _usage_text_to_annual_kwh(f"{m.group(1)} kWh / {m.group(2) or 'year'}")

            if annual_electricity_kwh is not None or annual_gas_kwh is not None:
                print(
                    f"  Parsed usage: electricity={annual_electricity_kwh} kWh/yr, "
                    f"gas={annual_gas_kwh} kWh/yr"
                )
            # Helper: get text within this card; try multiple selectors
            def get_card_text(selectors, default: str = "") -> str:
                if isinstance(selectors, str):
                    selectors = [selectors]
                for sel in selectors:
                    el = card.select_one(sel)
                    if el:
                        return el.get_text(strip=True)
                return default

            # --- Supplier & tariff names (try multiple possible class names) ---
            new_supplier_name = get_card_text([
                ".results-new-item-brand__provider-name",
                "[class*='provider-name']",
                "[class*='supplier']",
                ".supplier-name",
                "h3",
            ], "Unknown Supplier")
            tariff_name = get_card_text([
                ".results-new-item-brand__tariff-name",
                "[class*='tariff-name']",
                "[class*='tariff-name']",
                ".tariff-name",
            ], "Unknown Tariff")

            # --- Tariff type & fixed length ---
            fixed_price_length_months = 0
            tariff_type = "Unknown"

            rate_label_el = card.select_one(".results-new-item-rate-type__label")
            rate_value_el = card.select_one(".results-new-item-rate-type__value")

            rate_label_text = (
                rate_label_el.get_text(strip=True).lower() if rate_label_el else ""
            )
            rate_value_text = (
                rate_value_el.get_text(" ", strip=True).lower() if rate_value_el else ""
            )

            if "fixed" in rate_label_text or "fixed" in rate_value_text:
                tariff_type = "Fixed"
            elif "variable" in rate_label_text or "variable" in rate_value_text:
                tariff_type = "Variable"

            if rate_value_text:
                m = re.search(r"(\d+)", rate_value_text)
                if m:
                    try:
                        fixed_price_length_months = int(m.group(1))
                    except ValueError:
                        fixed_price_length_months = 0

            # --- Exit fee & yearly saving / annual cost ---
            exit_fee = 0.0
            annual_cost_new = 0.0

            # Exit fee lives in the callouts section
            callout_cells = card.select(".results-new-item-callouts__cells__cell")
            for cell in callout_cells:
                label_el = cell.select_one(
                    ".results-new-item-callouts__cells__cell__label"
                )
                if not label_el:
                    continue
                label = label_el.get_text(strip=True).lower()
                if "early exit fee" in label:
                    value_el = cell.select_one(
                        ".results-new-item-callouts__cells__cell__value"
                    )
                    if value_el:
                        text = value_el.get_text(" ", strip=True)
                        cleaned = text.replace("£", "").replace(",", "").strip()
                        try:
                            exit_fee = float(cleaned)
                        except ValueError:
                            exit_fee = 0.0
                    break

            # Annual cost is in the "or £1,234 a year" / "£103 a month" style text
            cost_sub_value = get_card_text(".results-new-item-cost__sub_value", "")
            if cost_sub_value:
                annual_cost_new = _tariff_card_annual_cost_gbp(cost_sub_value)

            # --- Unit rate & standing charge (take Electricity column if present) ---
            unit_rate = 0.0
            standing_charge_day = 0.0
            fuel_type = "Unknown"

            table = card.select_one(".results-new-item-charges-breakdown__table")
            if table:
                # Determine fuel type from table headers
                header_cells = table.select("thead tr th")
                header_texts = [h.get_text(strip=True).lower() for h in header_cells]

                has_gas = any("gas" in t for t in header_texts)
                has_elec = any("electric" in t for t in header_texts)

                if has_gas and has_elec:
                    fuel_type = "gas_and_electricity"
                elif has_elec:
                    fuel_type = "electricity"
                elif has_gas:
                    fuel_type = "gas"

                # When both present, the last column is Electricity
                # We read standing charge and unit rate from that column
                rows = table.select("tbody tr")
                for row in rows:
                    header_el = row.select_one("th")
                    if not header_el:
                        continue
                    label = header_el.get_text(strip=True).lower()
                    cells = row.select("td")
                    if not cells:
                        continue

                    # Prefer electricity column = last cell
                    value_el = cells[-1]
                    text = value_el.get_text(" ", strip=True)

                    if "standing charge" in label:
                        standing_charge_day = _standing_charge_cell_to_pence_per_day(text)
                    elif "unit rate" in label:
                        text_lower = text.lower()
                        m_gbp = re.search(r"£\s*([\d.]+)", text)
                        if m_gbp:
                            try:
                                unit_rate = float(m_gbp.group(1)) * 100.0
                            except ValueError:
                                unit_rate = 0.0
                        else:
                            m_p = re.search(r"([\d.]+)\s*p\b", text_lower)
                            if m_p:
                                try:
                                    unit_rate = float(m_p.group(1))
                                except ValueError:
                                    unit_rate = 0.0
                            else:
                                m = re.search(r"([\d.]+)", text)
                                if m:
                                    try:
                                        unit_rate = float(m.group(1))
                                    except ValueError:
                                        unit_rate = 0.0
                        # --- Check if tariff is green/renewable ---
            is_green = False
            # Check for green-electricity-decal within tariff-decals
            decals_section = card.select_one(".tariff-decals")
            if decals_section:
                green_decal = decals_section.select_one(".green-electricity-decal")
                if green_decal:
                    # Check if it contains "Green electricity" text
                    decal_text = green_decal.get_text(strip=True).lower()
                    if "green" in decal_text or "renewable" in decal_text:
                        is_green = True


            # --- Build Tariff object ---
            now = datetime.now()

            tariff = Tariff(
                # Tariff details
                new_supplier_name=new_supplier_name,
                tariff_name=tariff_name,
                tariff_type=tariff_type,
                fixed_price_length_months=fixed_price_length_months,
                is_green=is_green,

                # Location details - USE LOOKUP DATA
                region_code=self.location_data.get('region_code', ''),
                region_name=self.location_data.get('region', ''),
                dno_name=self.location_data.get('dno_name', ''),
                dno_id=self.location_data.get('dno_id', ''),
                postcode=self.location_data.get('postcode', ''),
                outward_code=self.location_data.get('outward_code', ''),
                latitude=self.location_data.get('latitude', 0.0),
                longitude=self.location_data.get('longitude', 0.0),

                fuel_type=fuel_type,

                # Search details
                search_date=now,
                month=now.month,
                year=now.year,

                # Cost details
                annual_electricity_kwh=annual_electricity_kwh,
                annual_gas_kwh=annual_gas_kwh,
                unit_rate=unit_rate,
                standing_charge_day=standing_charge_day,
                exit_fee=exit_fee,
                annual_cost_current=annual_cost_,
                annual_cost_new=annual_cost_new,
                valid_from=self._get_datetime(".valid-from"),
                valid_to=self._get_datetime(".valid-to"),
                created_at=now,
                last_updated=now,
            )

            return tariff

        tariffs: List[Tariff] = []
        for idx, card in enumerate(cards):
            try:
                tariffs.append(build_tariff_from_card(card))
            except Exception as e:
                print(f"⚠ Skipping result card {idx} due to error: {e}")

        return tariffs

    # Helper methods for extracting data
    def _get_text(self, selector: str, default: str = '') -> str:
        """Get text content from CSS selector"""
        element = self.soup.select_one(selector)
        return element.get_text(strip=True) if element else default


    def _get_bool(self, selector: str, default: bool = False) -> bool:
        """Get boolean value from CSS selector"""
        element = self.soup.select_one(selector)
        if not element:
            return default

        text = element.get_text(strip=True).lower()
        return text in ['true', 'yes', '1', 'green', 'renewable']

    def _get_datetime(self, selector: str) -> datetime:
        """Get datetime value from CSS selector"""
        text = self._get_text(selector)
        try:
            return datetime.strptime(text, '%Y-%m-%d')
        except (ValueError, AttributeError):
            return datetime.now() 