from __future__ import annotations

import os


def mysql_config() -> dict:
    """
    Central DB config (used by both the web app and scraper).
    Defaults match local dev; override via env vars in production/Docker.
    """
    return {
        "host": os.environ.get("DB_HOST", "powerplan-1.cxu0s4i46e5n.eu-north-1.rds.amazonaws.com"),
        "user": os.environ.get("DB_USER", "admin"),
        "password": os.environ.get("DB_PASSWORD", "2yxID9807s."),
        "database": os.environ.get("DB_NAME", "energy_tariff"),
        "port": int(os.environ.get("DB_PORT", "3306")),
    }

