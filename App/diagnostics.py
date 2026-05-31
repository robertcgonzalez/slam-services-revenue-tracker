"""App diagnostics and data freshness for Laura/Stef daily-driver confidence."""

from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_QMS_DIR = _REPO_ROOT / "QMS"


def get_app_user() -> str:
    """Display name: session login choice first, then SLAM_APP_USER env, else Team."""
    try:
        import streamlit as st

        session_user = (st.session_state.get("current_user") or "").strip()
        if session_user:
            return session_user
    except (ImportError, RuntimeError, AttributeError):
        pass
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


def _latest_dated_file(directory: Path, pattern: str = "*.md") -> Path | None:
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _parse_last_reviewed(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
        match = re.search(r"\*\*Last Reviewed\*\*:\s*(.+)", line)
        if match:
            return match.group(1).strip()
    return None


def _feedback_log_summary(data_path: Path | None) -> dict[str, Any]:
    candidates: list[Path] = []
    if data_path is not None:
        candidates.append(data_path / "feedback_log.csv")
    candidates.append(_REPO_ROOT / "Data" / "feedback_log.csv")
    log_path = next((p for p in candidates if p.is_file()), None)
    if log_path is None:
        return {"available": False, "open": 0, "total": 0, "path": None}
    rows: list[dict[str, str]] = []
    with log_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    open_rows = [
        row
        for row in rows
        if row.get("status", "").strip().lower() not in ("closed", "resolved", "done")
    ]
    return {
        "available": True,
        "open": len(open_rows),
        "total": len(rows),
        "path": str(log_path),
    }


def get_qms_status(*, data_path: Path | None = None) -> dict[str, Any]:
    """Lightweight QMS health summary for sidebar + health_check."""
    qms_ok = _QMS_DIR.is_dir()
    state_run = _latest_dated_file(_QMS_DIR / "State-Alignment" / "runs")
    mgmt_review = _latest_dated_file(_QMS_DIR / "Management-Reviews")
    risk_register = _QMS_DIR / "Risk-Register.md"
    capa_dir = _QMS_DIR / "CAPA"
    feedback = _feedback_log_summary(data_path)

    issues: list[str] = []
    if not qms_ok:
        issues.append("QMS folder missing")
    if state_run is None:
        issues.append("No State Alignment runs logged")
    if mgmt_review is None or mgmt_review.name == "template.md":
        issues.append("No Management Review on file")
    if feedback["available"] and feedback["open"] > 0:
        issues.append(f"{feedback['open']} open feedback item(s)")

    return {
        "operational": qms_ok and not issues,
        "qms_folder": qms_ok,
        "last_state_alignment": state_run.name if state_run else None,
        "last_management_review": (
            mgmt_review.name if mgmt_review and mgmt_review.name != "template.md" else None
        ),
        "risk_register_last_reviewed": _parse_last_reviewed(risk_register),
        "capa_records": len([p for p in capa_dir.glob("*.md") if p.name != "template.md"])
        if capa_dir.is_dir()
        else 0,
        "feedback": feedback,
        "issues": issues,
        "summary": "healthy" if qms_ok and not issues else "watch",
    }
