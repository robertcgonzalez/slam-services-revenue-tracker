#!/usr/bin/env python3
"""Production health check for Azure App Service startup and local verification.

Usage:
  python Scripts/health_check.py
  python Scripts/health_check.py --json
  python Scripts/health_check.py --verify-only

Exit codes: 0 = healthy, 1 = failure.
Never commit credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from App.data_paths import resolve_data_path  # noqa: E402
from App.db_utils import get_connection_status, init_schema  # noqa: E402
from App.diagnostics import get_qms_status  # noqa: E402


def check_csv_mode(*, as_json: bool) -> int:
    """Validate CSV data folder for Azure CSV-only or fallback deployments."""
    path, logs = resolve_data_path()
    if path is None:
        payload = {"mode": "csv", "ok": False, "message": "CSV folder not found", "logs": logs}
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print("FAIL: Could not locate Clients.csv + RevenueRequests.csv", file=sys.stderr)
            for line in logs[-8:]:
                print(f"  {line}", file=sys.stderr)
        return 1

    import pandas as pd

    clients_n = len(pd.read_csv(path / "Clients.csv"))
    requests_n = len(pd.read_csv(path / "RevenueRequests.csv"))
    payload = {
        "mode": "csv",
        "ok": True,
        "path": str(path),
        "clients": clients_n,
        "requests": requests_n,
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"OK: CSV data at {path}")
        print(f"  clients={clients_n}  requests={requests_n}")
    if requests_n == 0:
        print("WARN: RevenueRequests.csv has no rows")
    return 0


def check_qms(*, as_json: bool) -> int:
    """Validate QMS operational artifacts and feedback log visibility."""
    data_path, _logs = resolve_data_path()
    status = get_qms_status(data_path=data_path)
    code = 0 if status["operational"] else 1
    if as_json:
        print(json.dumps(status, indent=2))
        return code

    label = "OK" if status["operational"] else "WARN"
    print(f"{label}: QMS baseline — summary={status['summary']}")
    if status["last_state_alignment"]:
        print(f"  last_state_alignment={status['last_state_alignment']}")
    if status["last_management_review"]:
        print(f"  last_management_review={status['last_management_review']}")
    if status["risk_register_last_reviewed"]:
        print(f"  risk_register_last_reviewed={status['risk_register_last_reviewed']}")
    feedback = status["feedback"]
    if feedback["available"]:
        print(f"  feedback_log={feedback['open']} open / {feedback['total']} total")
    if status["issues"]:
        for issue in status["issues"]:
            print(f"  issue: {issue}", file=sys.stderr)
    return code


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="SLAM Revenue Tracker health check")
    parser.add_argument("--json", action="store_true", help="Output JSON for automation")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Test connection only; do not verify schema",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Validate CSV data folder (skip PostgreSQL)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run CSV check, QMS check, then PostgreSQL check when configured",
    )
    parser.add_argument(
        "--qms",
        action="store_true",
        help="Validate QMS operational artifacts and feedback log",
    )
    args = parser.parse_args()

    if args.qms:
        return check_qms(as_json=args.json)

    if args.full:
        csv_code = check_csv_mode(as_json=False)
        qms_code = check_qms(as_json=False)
        status = get_connection_status(reset=True)
        if not status["configured"]:
            print("PostgreSQL: not configured (CSV-only OK)")
            return max(csv_code, qms_code)
        if not status["connected"]:
            print(f"PostgreSQL FAIL: {status['message']}", file=sys.stderr)
            return 1 if csv_code != 0 or qms_code != 0 else 1
        stats = status.get("stats") or {}
        print(
            f"PostgreSQL OK: {stats.get('clients', 0)} clients, {stats.get('requests', 0)} requests"
        )
        return max(csv_code, qms_code)

    if args.csv:
        return check_csv_mode(as_json=args.json)

    status = get_connection_status(reset=True)
    if not status["configured"]:
        payload = {**status, "schema_ok": None}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("SKIP: PostgreSQL not configured (CSV mode).")
        return 0

    if not status["connected"]:
        if args.json:
            print(json.dumps({**status, "schema_ok": False}, indent=2))
        else:
            print(f"FAIL: {status['message']}", file=sys.stderr)
        return 1

    schema_ok = True
    if not args.verify_only:
        try:
            init_schema()
        except Exception as exc:
            schema_ok = False
            status["message"] = f"{status['message']} Schema check failed: {exc}"

    stats = status.get("stats") or {}
    result = {
        **status,
        "schema_ok": schema_ok,
        "clients": stats.get("clients", 0),
        "requests": stats.get("requests", 0),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"OK: {status['message']}")
        print(f"  clients={result['clients']}  requests={result['requests']}")
        if not args.verify_only:
            print(f"  schema_ok={schema_ok}")

    if not schema_ok:
        return 1
    if result["requests"] == 0:
        print("WARN: Database connected but no revenue requests — run migrate_to_postgres.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
