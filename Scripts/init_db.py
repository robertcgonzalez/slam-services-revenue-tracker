#!/usr/bin/env python3
"""Initialize PostgreSQL schema for SLAM Services (idempotent, safe to re-run).

Creates clients + revenue_requests tables if they do not exist, then verifies
connectivity. Run before the first CSV migration or after provisioning Azure
PostgreSQL Flexible Server.

Usage:
  python Scripts/init_db.py
  python Scripts/init_db.py --verify-only

Requires DATABASE_URL or POSTGRES_HOST/USER/PASSWORD in environment (or .env locally).
Never commit credentials.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from App.db_utils import get_connection_status, init_schema  # noqa: E402


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Initialize SLAM PostgreSQL schema")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Test connection only; do not create tables",
    )
    args = parser.parse_args()

    status = get_connection_status(reset=True)
    if not status["connected"]:
        print(f"ERROR: {status['message']}", file=sys.stderr)
        return 1
    print(status["message"])

    if args.verify_only:
        stats = status.get("stats") or {}
        print(
            f"Verify-only — schema not modified. "
            f"({stats.get('clients', 0)} clients, {stats.get('requests', 0)} requests)"
        )
        return 0

    try:
        init_schema()
        stats = get_connection_status()["stats"] or {}
        print("Schema ready: clients, revenue_requests (create_all idempotent).")
        print(
            f"Current rows: {stats.get('clients', 0)} clients, {stats.get('requests', 0)} requests."
        )
        return 0
    except Exception as exc:
        print(f"ERROR: Schema init failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
