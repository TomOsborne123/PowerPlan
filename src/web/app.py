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

app = Flask(__name__, static_folder="static", static_url_path="")
# Resolve static_folder so it works when run from project root
app.static_folder = os.path.join(os.path.dirname(__file__), "static")

# In-memory status for background scrape jobs: postcode_norm -> {"status": "running"|"completed"|"failed", "error": str|None}
_scrape_jobs: dict[str, dict] = {}
_scrape_jobs_lock = threading.Lock()

def _get_scrape_results(postcode: str) -> dict | None:
    """Load latest tariff scrape for postcode from DB. Returns None if DB unavailable or no data."""
    postcode_norm = (postcode or "").strip().upper().replace(" ", "")
    if not postcode_norm:
        return None
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="password",
            database="energy_tariff",
        )
        cursor = conn.cursor(dictionary=True)
        # Latest search for this postcode (match normalized)
        cursor.execute(
            """
            SELECT annual_electricity_kwh, latitude, longitude, search_date,
                   new_supplier_name, tariff_name, unit_rate, standing_charge, is_green
            FROM fact_tariff_search_simple
            WHERE REPLACE(postcode, ' ', '') = %s
              AND search_date = (
                SELECT MAX(search_date) FROM fact_tariff_search_simple
                WHERE REPLACE(postcode, ' ', '') = %s
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
            "tariffs": tariffs,
        }
    except Exception:
        return None


def _run_scrape_job(postcode_norm: str, postcode_display: str) -> None:
    """Run scraper in a subprocess (avoids Playwright 'Event loop is closed' in threads)."""
    import subprocess
    with _scrape_jobs_lock:
        _scrape_jobs[postcode_norm] = {"status": "running", "error": None}
    try:
        print(f"[scrape] Starting subprocess for postcode {postcode_display} ...")
        proc = subprocess.run(
            [sys.executable, "-m", "src.web.run_scrape", postcode_display],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
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
    except subprocess.TimeoutExpired:
        with _scrape_jobs_lock:
            _scrape_jobs[postcode_norm] = {"status": "failed", "error": "Scrape timed out after 5 minutes"}
        print(f"[scrape] Timeout for postcode {postcode_display}")
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
    postcode = (data.get("postcode") or "").strip()
    if not postcode or len(postcode) < 5:
        return jsonify({"error": "postcode required (min 5 characters)"}), 400
    postcode_norm = postcode.upper().replace(" ", "")
    with _scrape_jobs_lock:
        existing = _scrape_jobs.get(postcode_norm)
        if existing and existing.get("status") == "running":
            return jsonify({"error": "Scrape already running for this postcode"}), 409
    thread = threading.Thread(
        target=_run_scrape_job,
        args=(postcode_norm, postcode),
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
    threading.Thread(target=open_browser, daemon=True).start()
    print(f"Opening {url} in your browser...")
    app.run(host="0.0.0.0", port=port, debug=True)
