"""
PowerPlan web app: frontend for energy optimisation and tariff recommendation.
Run from project root: python -m src.web.app
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import requests

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from src.db import mysql_config
from src.models.tariff_recommendation import (
    coerce_standing_charge_pence_per_day,
    coerce_unit_rate_pence_per_kwh,
)

app = Flask(__name__, static_folder="static", static_url_path="")
# Resolve static_folder so it works when run from project root
app.static_folder = os.path.join(os.path.dirname(__file__), "static")

# If the browser UI is on another origin than this app, set CORS_ORIGINS (comma-separated origins).
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    CORS(app, resources={r"/api/*": {"origins": _cors_origins}})

# In-memory status for background scrape jobs: postcode_norm -> {"status": "running"|"completed"|"failed", "error": str|None}
_scrape_jobs: dict[str, dict] = {}
_scrape_jobs_lock = threading.Lock()


def _lookup_addresses_getaddress(postcode_norm: str) -> list[str]:
    """
    Fast UK address lookup via getAddress.io.
    Returns [] when API key missing or lookup fails.
    """
    api_key = (os.environ.get("GETADDRESS_API_KEY") or "").strip()
    if not api_key:
        return []
    # Keep timeout short: this endpoint is used interactively in the UI.
    timeout_s = float(os.environ.get("ADDRESS_LOOKUP_TIMEOUT_S", "10"))
    base = "https://api.getaddress.io/find"
    url = f"{base}/{postcode_norm}"
    try:
        r = requests.get(
            url,
            params={"api-key": api_key, "expand": "true"},
            timeout=timeout_s,
        )
        if r.status_code != 200:
            print(f"[address-lookup] getAddress status={r.status_code} postcode={postcode_norm}", flush=True)
            return []
        data = r.json() or {}
        raw_items = data.get("addresses") or []
        out: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            # expand=true returns dicts; without expand, strings.
            if isinstance(item, dict):
                parts = item.get("formatted_address") or []
                text = ", ".join([str(p).strip() for p in parts if str(p).strip()])
            else:
                text = str(item or "").strip()
            if not text:
                continue
            if text not in seen:
                seen.add(text)
                out.append(text)
        return out
    except Exception as e:
        print(f"[address-lookup] getAddress error postcode={postcode_norm}: {e}", flush=True)
        return []

def _get_scrape_results(postcode: str) -> dict | None:
    """Load latest tariff scrape for postcode from DB. Returns None if DB unavailable or no data."""
    import re
    postcode_norm = (postcode or "").strip().upper().replace(" ", "")
    if not postcode_norm:
        return None
    try:
        import mysql.connector
        conn = mysql.connector.connect(**mysql_config())
        cursor = conn.cursor(dictionary=True)
        rows = []
        is_outward_only = bool(re.match(r"^[A-Z]{1,2}\d{1,2}[A-Z]?$", postcode_norm))

        if is_outward_only:
            # Outward-only postcode area search (e.g. BS39)
            cursor.execute(
                """
                SELECT annual_electricity_kwh, latitude, longitude, search_date,
                       new_supplier_name, tariff_name, unit_rate, standing_charge, is_green
                FROM fact_tariff_search_simple
                WHERE UPPER(outward_code) = %s
                  AND search_date = (
                    SELECT MAX(search_date) FROM fact_tariff_search_simple
                    WHERE UPPER(outward_code) = %s
                  )
                ORDER BY new_supplier_name
                """,
                (postcode_norm, postcode_norm),
            )
            rows = cursor.fetchall()
        else:
            # Latest search for this full postcode (normalized, spaces optional)
            cursor.execute(
                """
                SELECT annual_electricity_kwh, latitude, longitude, search_date,
                       new_supplier_name, tariff_name, unit_rate, standing_charge, is_green
                FROM fact_tariff_search_simple
                WHERE REPLACE(UPPER(postcode), ' ', '') = %s
                  AND search_date = (
                    SELECT MAX(search_date) FROM fact_tariff_search_simple
                    WHERE REPLACE(UPPER(postcode), ' ', '') = %s
                  )
                ORDER BY new_supplier_name
                """,
                (postcode_norm, postcode_norm),
            )
            rows = cursor.fetchall()

        cursor.close()
        conn.close()
        if not rows:
            return None
        first = rows[0]
        # True annual kWh; scraper maps “per month” site copy into this column (re-scrape if data predates that fix).
        usage = first.get("annual_electricity_kwh")
        if usage is None:
            usage = 3500  # fallback
        lat = float(first.get("latitude") or 0.0)
        lon = float(first.get("longitude") or 0.0)
        search_date_val = first.get("search_date")
        search_date_iso = search_date_val.isoformat() if hasattr(search_date_val, "isoformat") else (str(search_date_val) if search_date_val else None)
        tariffs = [
            {
                "supplier_name": r["new_supplier_name"],
                "tariff_name": r["tariff_name"] or "",
                "unit_rate": float(r["unit_rate"] or 0),
                "standing_charge_day": float(r["standing_charge"] or 0),
                "is_green": bool(r.get("is_green", False)),
            }
            for r in rows
        ]
        return {
            "annual_electricity_kwh": int(usage),
            "latitude": lat,
            "longitude": lon,
            "search_date": search_date_iso,
            "tariffs": tariffs,
        }
    except Exception as e:
        import traceback
        print(f"[scrape-results] DB error for postcode={postcode!r}: {e}", flush=True)
        traceback.print_exc()
        return None


def _run_scrape_subprocess(argv: list[str], cwd: Path) -> tuple[int, str]:
    """
    Run the scraper child process. Stream combined stdout/stderr into the server log in real time.
    capture_output=True would buffer everything until exit — unusable for long scrapes on Render.
    """
    collected: list[str] = []
    lock = threading.Lock()
    max_lines = 400

    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    def _reader() -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            with lock:
                collected.append(line)
                if len(collected) > max_lines:
                    collected.pop(0)
            print(line, end="", flush=True)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    code = proc.wait()
    t.join(timeout=60)
    with lock:
        tail = "".join(collected)
    if len(tail) > 4500:
        tail = tail[-4500:]
    return code, tail


def _run_scrape_job(
    postcode_norm: str,
    postcode_display: str,
    home_or_business: str = "home",
    has_ev_slug: str = "interested",
    address_name: str = "",
    address_index: int = 0,
) -> None:
    """Run scraper in a subprocess (avoids Playwright 'Event loop is closed' in threads)."""
    with _scrape_jobs_lock:
        _scrape_jobs[postcode_norm] = {"status": "running", "error": None}
    try:
        print(
            f"[scrape] Starting subprocess for postcode {postcode_display} "
            f"({home_or_business}, has_ev={has_ev_slug}, address_name={address_name!r}, address_index={address_index}) ...",
            flush=True,
        )
        # -u: unbuffered Python so prints appear while the scrape runs (pipes are not TTYs).
        argv = [
            sys.executable,
            "-u",
            "-m",
            "src.web.run_scrape",
            postcode_display,
            home_or_business,
            has_ev_slug,
            address_name,
            str(max(0, int(address_index))),
        ]
        code, tail = _run_scrape_subprocess(argv, PROJECT_ROOT)
        if code == 0:
            with _scrape_jobs_lock:
                _scrape_jobs[postcode_norm] = {"status": "completed", "error": None}
            # Quick sanity check: if the scrape said it succeeded but the DB has no rows,
            # we likely have an RDS/permissions/config mismatch.
            try:
                seen = _get_scrape_results(postcode_norm)
                has_rows = bool(seen and seen.get("tariffs"))
                print(
                    f"[scrape] Post-complete DB check for {postcode_display}: has_rows={has_rows}",
                    flush=True,
                )
            except Exception as _e:
                print(f"[scrape] Post-complete DB check failed: {_e}", flush=True)
            print(f"[scrape] Completed for postcode {postcode_display}", flush=True)
        else:
            excerpt = (tail.strip() or f"Scraper exited with code {code} (no output captured).")
            with _scrape_jobs_lock:
                _scrape_jobs[postcode_norm] = {"status": "failed", "error": excerpt}
            print(
                f"[scrape] Failed for postcode {postcode_display} (exit {code})\n{excerpt}",
                flush=True,
            )
    except Exception as e:
        err_short = str(e) or type(e).__name__
        with _scrape_jobs_lock:
            _scrape_jobs[postcode_norm] = {"status": "failed", "error": err_short}
        print(f"[scrape] Error for postcode {postcode_display}: {err_short}")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/assets/<path:path>")
def static_assets(path):
    return send_from_directory(app.static_folder, os.path.join("assets", path))


@app.route("/api/postcode", methods=["POST"])
def api_postcode():
    """Resolve UK postcode to latitude, longitude using api postcode lookup."""
    from src.api.postcode_lookup import lookup as postcode_lookup
    data = request.get_json() or {}
    postcode = (data.get("postcode") or "").strip()
    if not postcode:
        return jsonify({"error": "postcode required"}), 400
    result = postcode_lookup(postcode)
    if result is None:
        return jsonify({"error": "Could not resolve postcode"}), 422
    return jsonify(result)


@app.route("/api/scrape-results")
def api_scrape_results():
    """Get latest tariff scrape results for a postcode (usage + tariffs + lat/lon). Returns 200 with no_saved_scrape when none found so the app can run the scraper."""
    postcode = (request.args.get("postcode") or "").strip()
    if not postcode:
        return jsonify({"error": "postcode required"}), 400
    result = _get_scrape_results(postcode)
    if result is None:
        return jsonify({
            "no_saved_scrape": True,
            "tariffs": [],
            "annual_electricity_kwh": None,
            "latitude": None,
            "longitude": None,
        }), 200
    return jsonify(result)


@app.route("/api/scrape-address-options", methods=["POST"])
def api_scrape_address_options():
    """Fetch selectable address options for a full postcode."""
    data = request.get_json() or {}
    postcode = (data.get("postcode") or "").strip()
    postcode_norm = postcode.upper().replace(" ", "")
    import re
    full_re = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2}$")
    if not postcode_norm or not full_re.match(postcode_norm):
        return jsonify({"error": "full postcode required (e.g. BS1 1AA)"}), 400
    try:
        # Prefer fast API lookup when key is configured.
        options = _lookup_addresses_getaddress(postcode_norm)
        if options:
            return jsonify({
                "postcode": postcode_norm,
                "address_options": options,
                "source": "getaddress",
            })

        # Slow browser fallback is optional: disable by default so UI stays fast.
        allow_slow_fallback = (os.environ.get("ADDRESS_LOOKUP_ALLOW_SCRAPE_FALLBACK") or "").strip().lower() in (
            "1", "true", "yes", "on"
        )
        if not allow_slow_fallback:
            return jsonify({
                "postcode": postcode_norm,
                "address_options": [],
                "source": "none",
                "error": "Fast address lookup unavailable. Configure GETADDRESS_API_KEY (recommended).",
            }), 503

        # Fallback to scraper-driven options when explicitly enabled.
        from src.api.energyScraping.ScrapeTariff import ScrapeTariff

        raw = (os.environ.get("SCRAPER_HEADLESS") or "").strip().lower()
        if raw in ("1", "true", "yes"):
            headless_mode = True
        elif raw in ("0", "false", "no"):
            headless_mode = False
        elif raw == "virtual":
            headless_mode = "virtual"
        else:
            headless_mode = True

        scraper = ScrapeTariff()
        options = scraper.fetch_address_options(postcode_norm, headless=headless_mode)
        return jsonify({
            "postcode": postcode_norm,
            "address_options": options,
            "source": "scrape_fallback",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/run-scrape", methods=["POST"])
def api_run_scrape():
    """Start a background tariff scrape for the given postcode. Returns 202 when started."""
    data = request.get_json() or {}
    import re
    postcode = (data.get("postcode") or "").strip()
    postcode_norm = postcode.upper().replace(" ", "")
    # Accept outward-only (e.g. BS39) or full postcodes (e.g. BS1 1AA / BS394DB)
    outward_re = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]?$")
    full_re = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2}$")
    if not postcode_norm or not (outward_re.match(postcode_norm) or full_re.match(postcode_norm)):
        return jsonify({"error": "postcode required (e.g. BS39 or BS1 1AA; spaces optional)"}), 400
    home_or_business = (data.get("home_or_business") or "home").strip().lower()
    if home_or_business not in ("home", "business"):
        home_or_business = "home"
    has_ev_slug = (data.get("has_ev") or "interested").strip().lower()
    if has_ev_slug not in ("yes", "no", "interested"):
        has_ev_slug = "interested"
    address_name = str(data.get("address_name") or "").strip()
    try:
        address_index = int(data.get("address_index", 0))
    except (TypeError, ValueError):
        address_index = 0
    with _scrape_jobs_lock:
        existing = _scrape_jobs.get(postcode_norm)
        if existing and existing.get("status") == "running":
            return jsonify({"error": "Scrape already running for this postcode"}), 409
    postcode_for_cli = (postcode or "").strip() or postcode_norm
    thread = threading.Thread(
        target=_run_scrape_job,
        args=(postcode_norm, postcode_for_cli, home_or_business, has_ev_slug, address_name, max(0, address_index)),
        daemon=True,
    )
    thread.start()
    return jsonify({"status": "started", "postcode": postcode}), 202


@app.route("/api/scrape-status")
def api_scrape_status():
    """Return status of scrape job for postcode: idle, running, completed, or failed."""
    postcode = (request.args.get("postcode") or "").strip()
    if not postcode:
        return jsonify({"error": "postcode required"}), 400
    postcode_norm = postcode.upper().replace(" ", "")
    with _scrape_jobs_lock:
        job = _scrape_jobs.get(postcode_norm)
    if not job:
        return jsonify({"status": "idle"})
    return jsonify({
        "status": job.get("status", "idle"),
        "error": job.get("error"),
    })


@app.route("/api/export-price")
def api_export_price():
    """Indicative UK export rate (£/kWh) from public Octopus product data."""
    from src.api.reference_export_price import fetch_reference_export_price_gbp_per_kwh

    out = fetch_reference_export_price_gbp_per_kwh()
    status = 200 if out.get("export_price_per_kwh") is not None else 503
    return jsonify(out), status


@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    """
    Run optimisation and tariff recommendation.
    Body: {
      postcode? (if no lat/lon or to load usage/tariffs from scrape when usage empty),
      latitude, longitude,
      annual_consumption_kwh? (optional; if missing and postcode set, use scrape data),
      tariffs?: [ ... ] (optional; if missing and postcode set, use scrape tariffs),
      ...
    }
    """
    try:
        data = request.get_json() or {}
        postcode = (data.get("postcode") or "").strip()
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        annual_consumption_kwh = data.get("annual_consumption_kwh")
        tariffs_data = data.get("tariffs") or []

        # If annual usage not provided and postcode given, try scrape results
        from src.api.postcode_lookup import lookup as postcode_lookup
        if (annual_consumption_kwh is None or annual_consumption_kwh == "" or float(annual_consumption_kwh or 0) <= 0) and postcode:
            scrape = _get_scrape_results(postcode)
            if scrape:
                annual_consumption_kwh = scrape["annual_electricity_kwh"]
                if not tariffs_data:
                    tariffs_data = scrape["tariffs"]
                if latitude is None and longitude is None:
                    latitude = scrape["latitude"]
                    longitude = scrape["longitude"]

        latitude = float(latitude if latitude is not None else 0)
        longitude = float(longitude if longitude is not None else 0)
        annual_consumption_kwh = float(annual_consumption_kwh if annual_consumption_kwh not in (None, "") else 3500)
        heating_fraction = float(data.get("heating_fraction", 0.6))
        insulation_r_value = float(data.get("insulation_r_value", 0))
        heat_pump_cop = float(data.get("heat_pump_cop", 1.0))
        solar_tier = (data.get("solar_tier") or "budget").lower()
        wind_tier = (data.get("wind_tier") or "budget").lower()
        export_price_per_kwh = float(data.get("export_price_per_kwh", 0.05))
        optimize_over_years = float(data.get("optimize_over_years", 5))
        prefer_green = bool(data.get("prefer_green", False))
        solar_max_kw = float(data.get("solar_max_kw", 20.0))
        wind_max_kw = float(data.get("wind_max_kw", 10.0))
        min_solar_kw = float(data.get("min_solar_kw", 0.0))
        min_wind_kw = float(data.get("min_wind_kw", 0.5))
        if solar_tier == "none":
            solar_max_kw, min_solar_kw = 0.0, 0.0
        if wind_tier == "none":
            wind_max_kw, min_wind_kw = 0.0, 0.0
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid input: {e}"}), 400

    if not tariffs_data:
        # No scrape data and no tariffs provided
        if postcode:
            return jsonify({"error": "No tariffs for this postcode. Enter tariffs below or run the tariff scraper first and try again."}), 400
        # Default example tariffs so the page works without user adding any
        tariffs_data = [
            {"supplier_name": "Octopus", "tariff_name": "Flexible", "unit_rate": 24.5, "standing_charge_day": 55.0, "is_green": True},
            {"supplier_name": "British Gas", "tariff_name": "Standard", "unit_rate": 28.2, "standing_charge_day": 60.0, "is_green": False},
            {"supplier_name": "EDF", "tariff_name": "Standard", "unit_rate": 26.8, "standing_charge_day": 52.0, "is_green": True},
            {"supplier_name": "Ovo", "tariff_name": "Better", "unit_rate": 25.0, "standing_charge_day": 58.0, "is_green": True},
        ]

    # Normalise tariff keys for recommend_tariff (it accepts unit_rate p/kWh, standing_charge_day p/day)
    tariffs = []
    for t in tariffs_data:
        tariffs.append({
            "new_supplier_name": t.get("supplier_name", t.get("new_supplier_name", "")),
            "tariff_name": t.get("tariff_name", ""),
            "unit_rate": float(t.get("unit_rate", t.get("unit_rate_p", 0))),
            "standing_charge_day": float(t.get("standing_charge_day", t.get("standing_charge_p_per_day", 0))),
            "is_green": bool(t.get("is_green", False)),
        })

    from src.models.tariff_recommendation import recommend_tariff
    from src.data.energy_tiers import SOLAR_TIERS, WIND_TIERS

    solar_type = SOLAR_TIERS.get(solar_tier, SOLAR_TIERS["budget"])
    wind_type = WIND_TIERS.get(wind_tier, WIND_TIERS["budget"])

    try:
        rec = recommend_tariff(
            tariffs,
            latitude,
            longitude,
            annual_consumption_kwh,
            solar_type,
            wind_type,
            export_price_per_kwh=export_price_per_kwh,
            optimize_over_years=optimize_over_years,
            heating_fraction=heating_fraction,
            insulation_r_value=insulation_r_value,
            heat_pump_cop=heat_pump_cop,
            prefer_green=prefer_green,
            solar_max_kw=max(0.0, solar_max_kw),
            wind_max_kw=max(0.0, wind_max_kw),
            min_solar_kw=max(0.0, min_solar_kw),
            min_wind_kw=max(0.0, min_wind_kw),
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if rec.get("error"):
        return jsonify({"error": rec["error"]}), 422

    # Serialise for JSON (e.g. numpy floats)
    opt = rec["optimisation_result"]
    out = {
        "recommended_tariff": rec["recommended_tariff"],
        "ranking": rec["ranking"],
        "optimization": {
            "optimal_solar_kw": float(opt["optimal_solar_kw"]),
            "optimal_wind_kw": float(opt["optimal_wind_kw"]),
            "total_capacity_kw": float(opt["total_capacity_kw"]),
            "annual_demand_kwh": float(opt["annual_demand_kwh"]),
            "annual_demand_before_adjustments_kwh": float(opt.get("annual_demand_before_adjustments_kwh", opt["annual_demand_kwh"])),
            "heating_demand_after_insulation_kwh": float(opt.get("heating_demand_after_insulation_kwh", 0.0)),
            "annual_demand_after_insulation_kwh": float(opt.get("annual_demand_after_insulation_kwh", 0.0)),
            "heating_fraction": float(opt.get("heating_fraction", heating_fraction)),
            "insulation_r_value": float(opt.get("insulation_r_value", insulation_r_value)),
            "heat_pump_cop": float(opt.get("heat_pump_cop", heat_pump_cop)),
            "annual_solar_generation_kwh": float(opt.get("annual_solar_generation_kwh", 0.0)),
            "annual_wind_generation_kwh": float(opt.get("annual_wind_generation_kwh", 0.0)),
            "annual_generation_kwh": float(opt["annual_generation_kwh"]),
            "annual_import_kwh": float(opt["annual_import_kwh"]),
            "annual_export_kwh": float(opt["annual_export_kwh"]),
            "demand_met_from_generation_pct": float(opt["demand_met_from_generation_pct"]),
            "capex": float(opt["capex"]),
            "solar_capex": float(opt["solar_capex"]),
            "wind_capex": float(opt["wind_capex"]),
            "payback_solar_years": opt.get("payback_solar_years"),
            "payback_wind_years": opt.get("payback_wind_years"),
        },
        "optimize_over_years": rec["optimize_over_years"],
        "total_cost_best_gbp": rec["ranking"][0]["total_cost_gbp"] if rec["ranking"] else None,
    }
    if opt.get("monthly_balance") is not None:
        df = opt["monthly_balance"]
        out["monthly_balance"] = df.to_dict(orient="records") if hasattr(df, "to_dict") else []

    return jsonify(out)


@app.route("/api/cost-projection", methods=["POST"])
def api_cost_projection():
    """
    Cumulative cost vs years for incremental upgrade steps using one tariff’s unit rate and
    standing charge. Each scenario adds on top of the previous: baseline → +solar → +wind → +insulation.
    """
    try:
        data = request.get_json() or {}
        latitude = float(data.get("latitude", 0))
        longitude = float(data.get("longitude", 0))
        annual_consumption_kwh = float(data.get("annual_consumption_kwh", 3500))
        heating_fraction = float(data.get("heating_fraction", 0.6))
        heat_pump_cop = float(data.get("heat_pump_cop", 3.0))
        export_price_per_kwh = float(data.get("export_price_per_kwh", 0.05))
        unit_rate_p = coerce_unit_rate_pence_per_kwh(float(data.get("unit_rate_p_per_kwh", 0)))
        standing_p_day = coerce_standing_charge_pence_per_day(float(data.get("standing_charge_p_per_day", 0)))
        max_years = int(float(data.get("max_years", 20)))
        max_years = max(1, min(20, max_years))
        baseline_insulation = float(data.get("baseline_insulation_r_value", 2.5))
        upgraded_insulation = float(data.get("upgraded_insulation_r_value", 6.0))
        scenario_solar_kw = float(data.get("scenario_solar_kw", 4.0))
        scenario_wind_kw = float(data.get("scenario_wind_kw", 2.0))
        solar_tier = (data.get("solar_tier") or "mid").lower()
        wind_tier = (data.get("wind_tier") or "mid").lower()
        if solar_tier == "none":
            solar_tier = "mid"
        if wind_tier == "none":
            wind_tier = "mid"
        tariff_label = str(data.get("tariff_label") or "Selected tariff")
        scenario_ids = data.get("scenario_ids")
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid input: {e}"}), 400

    if unit_rate_p <= 0:
        return jsonify({"error": "unit_rate_p_per_kwh required (p/kWh from your best or chosen tariff)"}), 400

    from src.models.energy_balancing import evaluate_fixed_capacities
    from src.data.energy_tiers import SOLAR_TIERS, WIND_TIERS

    solar_params = SOLAR_TIERS.get(solar_tier, SOLAR_TIERS["mid"])
    wind_params = WIND_TIERS.get(wind_tier, WIND_TIERS["mid"])
    grid_gbp_per_kwh = unit_rate_p / 100.0
    standing_gbp_per_year = 365.0 * (standing_p_day / 100.0)

    # All 2^3 = 8 combinations of the three upgrade technologies: Solar, Wind, Insulation.
    # Each scenario's `techs` list is a stable, sorted set of tech keys so the frontend can render
    # consistent badges and group by "individual / pairs / full" without hard-coding each id.
    def _combo_label(techs: list[str]) -> str:
        if not techs:
            return f"Baseline — grid only (R {baseline_insulation:g})"
        pretty = {"solar": "Solar", "wind": "Wind", "insulation": "Insulation"}
        return " + ".join(pretty[t] for t in techs)

    combos = [
        [],
        ["solar"],
        ["wind"],
        ["insulation"],
        ["solar", "wind"],
        ["solar", "insulation"],
        ["wind", "insulation"],
        ["solar", "wind", "insulation"],
    ]
    scenario_defs = []
    for techs in combos:
        sid = "combo_baseline" if not techs else "combo_" + "_".join(techs)
        scenario_defs.append({
            "id": sid,
            "label": _combo_label(techs),
            "techs": list(techs),
            "insulation_r_value": upgraded_insulation if "insulation" in techs else baseline_insulation,
            "solar_kw": scenario_solar_kw if "solar" in techs else 0.0,
            "wind_kw": scenario_wind_kw if "wind" in techs else 0.0,
        })
    if isinstance(scenario_ids, list) and scenario_ids:
        want = {str(x) for x in scenario_ids}
        scenario_defs = [s for s in scenario_defs if s["id"] in want]

    try:
        series_out: list[dict] = []
        for sc in scenario_defs:
            ev = evaluate_fixed_capacities(
                latitude,
                longitude,
                annual_consumption_kwh,
                heating_fraction,
                sc["insulation_r_value"],
                heat_pump_cop,
                sc["solar_kw"],
                sc["wind_kw"],
                solar_params,
                wind_params,
            )
            imp = float(ev["annual_import_kwh"])
            exp = float(ev["annual_export_kwh"])
            annual_energy_cash = imp * grid_gbp_per_kwh - exp * export_price_per_kwh
            annual_running_gbp = annual_energy_cash + standing_gbp_per_year
            capex = float(ev["capex_gbp"])
            cumulative = [round(capex + annual_running_gbp * y, 2) for y in range(1, max_years + 1)]
            series_out.append({
                "id": sc["id"],
                "label": sc["label"],
                "techs": sc.get("techs", []),
                "solar_kw": sc["solar_kw"],
                "wind_kw": sc["wind_kw"],
                "insulation_r_value": sc["insulation_r_value"],
                "cumulative_gbp": cumulative,
                "annual_running_gbp": round(annual_running_gbp, 2),
                "capex_gbp": round(capex, 2),
                "annual_import_kwh": ev["annual_import_kwh"],
                "annual_export_kwh": ev["annual_export_kwh"],
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "years": list(range(1, max_years + 1)),
        "max_years": max_years,
        "tariff_label": tariff_label,
        "export_price_per_kwh": export_price_per_kwh,
        "unit_rate_p_per_kwh": unit_rate_p,
        "standing_charge_p_per_day": standing_p_day,
        "series": series_out,
    })


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    url = f"http://127.0.0.1:{port}"
    def open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open(url)
    # When Flask runs with debug=True, Werkzeug's reloader can start the process twice.
    # Guard the auto-open so Chrome only gets opened once.
    if os.environ.get("WERKZEUG_RUN_MAIN") in (None, "true", "True", "1"):
        threading.Thread(target=open_browser, daemon=True).start()
    print(f"Opening {url} in your browser...")
    # Disable the reloader so we don't spawn a second server process.
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
