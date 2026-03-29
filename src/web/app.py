"""
PowerPlan web app: frontend for energy optimisation and tariff recommendation.
Run from project root: python -m src.web.app
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from src.db import mysql_config

app = Flask(__name__, static_folder="static", static_url_path="")
# Resolve static_folder so it works when run from project root
app.static_folder = os.path.join(os.path.dirname(__file__), "static")

# Browser site on Netlify calls this API on another origin — set CORS_ORIGINS=https://your-site.netlify.app
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    CORS(app, resources={r"/api/*": {"origins": _cors_origins}})

# In-memory status for background scrape jobs: postcode_norm -> {"status": "running"|"completed"|"failed", "error": str|None}
_scrape_jobs: dict[str, dict] = {}
_scrape_jobs_lock = threading.Lock()

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
    except Exception:
        return None


def _run_scrape_job(postcode_norm: str, postcode_display: str, home_or_business: str = "home") -> None:
    """Run scraper in a subprocess (avoids Playwright 'Event loop is closed' in threads)."""
    import subprocess
    with _scrape_jobs_lock:
        _scrape_jobs[postcode_norm] = {"status": "running", "error": None}
    try:
        print(f"[scrape] Starting subprocess for postcode {postcode_display} ({home_or_business}) ...")
        # start_new_session=True isolates the subprocess so a browser crash doesn't take down Flask
        # No timeout — wait until the scrape subprocess exits (success or failure).
        proc = subprocess.run(
            [sys.executable, "-m", "src.web.run_scrape", postcode_display, home_or_business],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            start_new_session=True,
        )
        if proc.returncode == 0:
            with _scrape_jobs_lock:
                _scrape_jobs[postcode_norm] = {"status": "completed", "error": None}
            print(f"[scrape] Completed for postcode {postcode_display}")
        else:
            err_short = (proc.stderr or proc.stdout or "Scrape failed").strip().split("\n")[-1][:200]
            with _scrape_jobs_lock:
                _scrape_jobs[postcode_norm] = {"status": "failed", "error": err_short}
            print(f"[scrape] Failed for postcode {postcode_display}: {err_short}")
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
    with _scrape_jobs_lock:
        existing = _scrape_jobs.get(postcode_norm)
        if existing and existing.get("status") == "running":
            return jsonify({"error": "Scrape already running for this postcode"}), 409
    thread = threading.Thread(
        target=_run_scrape_job,
        args=(postcode_norm, postcode_norm, home_or_business),
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
