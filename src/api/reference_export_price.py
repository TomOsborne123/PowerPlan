"""
Reference export price (£/kWh) from a public tariff API (Octopus Energy).

Used as a live *indicator* — the user's actual export rate depends on their supplier and region.
"""

from __future__ import annotations

import os
from typing import Any

import requests

# Octopus "Outgoing Octopus" flat export product (public API, no key).
DEFAULT_OUTGOING_PRODUCT = "OUTGOING-VAR-24-10-26"
OCTOPUS_PRODUCT_URL = "https://api.octopus.energy/v1/products/{product}/"


def fetch_reference_export_price_gbp_per_kwh(
    *,
    product_code: str | None = None,
    timeout_s: float = 12.0,
) -> dict[str, Any]:
    """
    Return current flat export unit rate from Octopus product metadata (p/kWh → £/kWh).

    Uses the first region entry under single_register_electricity_tariffs (rates are national bands;
    all regions share the same headline rate in the product snapshot).
    """
    code = (product_code or os.environ.get("OCTOPUS_EXPORT_PRODUCT_CODE") or DEFAULT_OUTGOING_PRODUCT).strip()
    url = OCTOPUS_PRODUCT_URL.format(product=code)
    try:
        r = requests.get(url, timeout=timeout_s)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {
            "export_price_per_kwh": None,
            "source": "octopus_product",
            "product_code": code,
            "error": str(e),
            "disclaimer": "Could not reach Octopus API. Enter export price manually.",
        }

    tariffs = data.get("single_register_electricity_tariffs") or {}
    if not isinstance(tariffs, dict) or not tariffs:
        return {
            "export_price_per_kwh": None,
            "source": "octopus_product",
            "product_code": code,
            "error": "No single-rate electricity export tariffs in product",
            "disclaimer": "Enter export price manually.",
        }

    first_key = next(iter(tariffs))
    entry = tariffs[first_key]
    dd = (entry or {}).get("direct_debit_monthly") or {}
    p_per_kwh = dd.get("standard_unit_rate_exc_vat")
    if p_per_kwh is None:
        return {
            "export_price_per_kwh": None,
            "source": "octopus_product",
            "product_code": code,
            "error": "Missing standard_unit_rate in product",
            "disclaimer": "Enter export price manually.",
        }

    gbp_per_kwh = float(p_per_kwh) / 100.0
    display_name = data.get("display_name") or data.get("full_name") or code
    return {
        "export_price_per_kwh": round(gbp_per_kwh, 4),
        "source": "octopus_product",
        "product_code": code,
        "tariff_name": display_name,
        "region_key": first_key.strip("_") or first_key,
        "disclaimer": (
            "Indicative national export rate from Octopus public data — not your personal tariff. "
            "Confirm with your supplier (rates vary by region and product)."
        ),
        "more_info": "https://octopus.energy/outgoing/",
    }
