"""App diagnostics and data freshness for Laura/Stef daily-driver confidence."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any


def get_app_user() -> str:
    return os.environ.get("SLAM_APP_USER", "").strip() or "Team"


def get_app_info(*, app_version: str, data_source: str, use_postgres: bool) -> dict[str, Any]:
    """Non-secret environment summary for sidebar diagnostics."""
    return {
        "version": app_version,
        "data_source": data_source,
        "postgres_requested": os.environ.get("USE_POSTGRES", "").strip().lower()
        in ("1", "true", "yes"),
        "postgres_active": use_postgres,
        "custom_password": "SLAM_APP_PASSWORD" in os.environ,
        "data_path_override": bool(os.environ.get("SLAM_DATA_PATH", "").strip()),
        "app_user": get_app_user(),
        "host": os.environ.get("WEBSITE_HOSTNAME", "local"),
    }


def _fmt_mtime(path: Path) -> str | None:
    if not path.is_file():
        return None
    ts = datetime.fromtimestamp(path.stat().st_mtime)
    return ts.strftime("%Y-%m-%d %H:%M")


def get_csv_freshness(data_path: Path | None) -> dict[str, Any]:
    if data_path is None:
        return {"available": False, "message": "CSV folder not resolved"}
    clients = data_path / "Clients.csv"
    requests = data_path / "RevenueRequests.csv"
    if not clients.is_file() or not requests.is_file():
        return {
            "available": False,
            "message": "Clients.csv or RevenueRequests.csv missing",
            "path": str(data_path),
        }
    c_mtime = clients.stat().st_mtime
    r_mtime = requests.stat().st_mtime
    newest = max(c_mtime, r_mtime)
    return {
        "available": True,
        "path": str(data_path),
        "clients_updated": _fmt_mtime(clients),
        "requests_updated": _fmt_mtime(requests),
        "last_updated": datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M"),
        "label": "CSV files",
    }


def get_postgres_freshness() -> dict[str, Any]:
    try:
        from db_utils import get_connection_status

        status = get_connection_status()
        stats = status.get("stats") or {}
        return {
            "available": status["connected"],
            "message": status["message"],
            "clients": stats.get("clients", 0),
            "requests": stats.get("requests", 0),
            "label": "PostgreSQL",
            "last_updated": "Live database" if status["connected"] else None,
        }
    except Exception as exc:
        return {"available": False, "message": str(exc), "label": "PostgreSQL"}


def get_operational_hints(*, data_source: str, db_health: str) -> list[str]:
    """Short actionable hints for sidebar system status (UAT + ops)."""
    hints: list[str] = []
    if db_health == "warn":
        hints.append("Database unreachable — edits save to CSV until Robert fixes Postgres.")
    if data_source == "csv":
        hints.append("CSV mode: use Force reload after another user saves on a different machine.")
    else:
        hints.append("PostgreSQL mode: edits are shared instantly — no reload needed after save.")
    hints.append("Logs: Azure Portal → App Service → Log stream → filter slam_app")
    return hints


def get_data_freshness(
    *,
    data_source: str,
    data_path: Path | None,
) -> dict[str, Any]:
    if data_source == "postgresql":
        return get_postgres_freshness()
    return get_csv_freshness(data_path)
