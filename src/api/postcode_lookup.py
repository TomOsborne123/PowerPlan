"""
UK postcode lookup using postcodes.io. Used for weather location and by the web app.
Shared by the scraping workflow (ScrapeTariff uses PostcodeLookup there with DNO mapping).
"""

from __future__ import annotations

from typing import Any

try:
    import requests
except ImportError:
    requests = None


def lookup(postcode: str) -> dict[str, Any] | None:
    """
    Lookup postcode data from postcodes.io API.

    Returns dict with: latitude, longitude, admin_district, region, postcode, outward_code,
    or None if lookup fails.
    """
    if not postcode or not requests:
        return None
    postcode_clean = postcode.strip().upper().replace(" ", "")
    try:
        r = requests.get(
            f"https://api.postcodes.io/postcodes/{postcode_clean}",
            timeout=5,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("status") != 200:
            return None
        result = data["result"]
        outward_code = result.get("outcode", "")
        return {
            "postcode": result.get("postcode", postcode),
            "outward_code": outward_code,
            "latitude": float(result.get("latitude", 0.0)),
            "longitude": float(result.get("longitude", 0.0)),
            "region": result.get("region", ""),
            "admin_district": result.get("admin_district", ""),
            "country": result.get("country", ""),
        }
    except Exception:
        return None
