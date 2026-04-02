"""
Quick Railway-side diagnostics for RDS connectivity.

What it checks:
1) TCP reachability to DB_HOST:DB_PORT (fast; confirms SG/NACL/firewall issues)
2) MySQL handshake/auth (slower; confirms credentials/DB permissions)

Usage (inside the deployed environment, e.g. Railway Shell):
  python3 -m src.tools.check_db_connectivity
"""

from __future__ import annotations

import os
import socket
import sys
from typing import Tuple


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


def tcp_connect(host: str, port: int, timeout_s: float = 5.0) -> None:
    addr: Tuple[str, int] = (host, port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout_s)
    try:
        s.connect(addr)
    finally:
        try:
            s.close()
        except Exception:
            pass


def main() -> int:
    host = _env("DB_HOST") or "localhost"
    port = int(_env("DB_PORT") or "3306")
    user = _env("DB_USER") or "root"
    db_name = _env("DB_NAME") or "energy_tariff"

    print(f"[db-check] DB_HOST={host}")
    print(f"[db-check] DB_PORT={port}")
    print(f"[db-check] DB_USER={user}")
    print(f"[db-check] DB_NAME={db_name}")

    print("[db-check] Checking TCP reachability...")
    try:
        tcp_connect(host, port, timeout_s=5.0)
        print("[db-check] TCP connect OK")
    except Exception as e:
        print(f"[db-check] TCP connect FAILED: {type(e).__name__}: {e}")
        print(
            "[db-check] This usually means RDS security group / NACL / public accessibility "
            "is blocking Railway egress IPs."
        )
        return 2

    print("[db-check] Checking MySQL auth/connect...")
    password = _env("DB_PASSWORD") or ""
    try:
        import mysql.connector  # type: ignore

        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            connection_timeout=5,
        )
        conn.close()
        print("[db-check] MySQL connect OK")
        return 0
    except ModuleNotFoundError as e:
        # Common when running `railway run ...` locally without mysql-connector installed.
        print(f"[db-check] MySQL client not installed locally: {e}")
        print("[db-check] TCP reachability is OK. To test MySQL auth locally, install:")
        print("           python3 -m pip install mysql-connector-python")
        return 0
    except Exception as e:
        print(f"[db-check] MySQL connect FAILED: {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

