#!/usr/bin/env python3
"""Kudu one-shot: verify PostgreSQL from App Service container env."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_env_file = Path("/tmp/slam_pg_env.json")
if _env_file.is_file():
    for key, value in json.loads(_env_file.read_text(encoding="utf-8")).items():
        os.environ[key] = str(value)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "App"))
os.environ.setdefault("USE_POSTGRES", "true")

from sqlalchemy import text  # noqa: E402

from db_utils import get_engine  # noqa: E402


def main() -> int:
    eng = get_engine()
    with eng.connect() as conn:
        clients = conn.execute(text("SELECT COUNT(*) FROM clients")).scalar()
        requests = conn.execute(text("SELECT COUNT(*) FROM revenue_requests")).scalar()
    print(f"POSTGRES_OK clients={clients} requests={requests}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
