#!/usr/bin/env python3
"""Phase 3 — migrate Clients.csv + RevenueRequests.csv into PostgreSQL.

Reads CSVs from the same paths as App/app.py (local or SLAM_DATA_PATH override),
creates Blueprint Section 7 schema (clients + revenue_requests), and idempotently
upserts rows with audit fields and soft-delete restoration.

Usage:
  python Scripts/init_db.py
  python Scripts/migrate_to_postgres.py --dry-run
  python Scripts/migrate_to_postgres.py
  python Scripts/migrate_to_postgres.py --init-schema
  python Scripts/migrate_to_postgres.py --data-path "C:/SLAM-Services-Project/Data/Revenue_Tracker_Migration"

Requires DATABASE_URL or POSTGRES_HOST/USER/PASSWORD in environment (or .env locally).
Never commit credentials or client CSVs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from App.db_utils import (  # noqa: E402
    create_db_engine,
    get_connection_status,
    get_session,
    init_schema,
    parse_bool,
    sync_clients_from_csv,
    upsert_revenue_request_from_row,
)

MIGRATION_ACTOR = "migration"


def resolve_csv_dir(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if (p / "Clients.csv").exists() and (p / "RevenueRequests.csv").exists():
            return p
        raise FileNotFoundError(f"CSV pair not found under {p}")

    from App.data_paths import resolve_data_path

    path, logs = resolve_data_path()
    if path is None:
        print("Could not locate CSV data directory. Checked:")
        for line in logs:
            print(f"  {line}")
        raise FileNotFoundError("Clients.csv / RevenueRequests.csv not found")
    return path


def load_clients_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path / "Clients.csv")
    if "Business Name" not in df.columns:
        df.columns = [c.strip() for c in df.iloc[0]]
        df = df.iloc[1:]
    df = df[df["Business Name"].notna() & (df["Business Name"].astype(str).str.strip() != "")]
    for col in ["EIN", "Entity Type", "City State Zip"]:
        if col not in df.columns:
            df[col] = ""
    return df.reset_index(drop=True)


def load_requests_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path / "RevenueRequests.csv")
    required = [
        "request_id",
        "business_name",
        "request_type",
        "period",
        "status",
        "amount_due",
        "due_date",
        "received_date",
        "notes",
        "bank_statement_received",
        "sales_report_received",
    ]
    for col in required:
        if col not in df.columns:
            df[col] = ""
    df["amount_due"] = pd.to_numeric(df["amount_due"], errors="coerce").fillna(0)
    for col in ["bank_statement_received", "sales_report_received"]:
        df[col] = df[col].apply(parse_bool)
    return df


def migrate(data_dir: Path, *, dry_run: bool = False) -> None:
    clients_df = load_clients_csv(data_dir)
    requests_df = load_requests_csv(data_dir)
    print(
        f"Loaded {len(clients_df)} clients and {len(requests_df)} revenue requests from {data_dir}"
    )

    if dry_run:
        print("Dry run — no database writes.")
        return

    pre = get_connection_status(reset=True)
    if not pre["connected"]:
        raise RuntimeError(pre["message"])

    engine = create_db_engine()
    init_schema(engine)

    created, updated, name_to_id = sync_clients_from_csv(
        clients_df, updated_by=MIGRATION_ACTOR, engine=engine
    )
    print(f"Clients: {created} created, {updated} updated.")

    upserted = 0
    skipped = 0
    skip_reasons: list[str] = []
    with get_session(engine) as session:
        for _, row in requests_df.iterrows():
            ok, reason = upsert_revenue_request_from_row(
                session,
                row,
                name_to_id,
                updated_by=MIGRATION_ACTOR,
            )
            if ok:
                upserted += 1
            else:
                skipped += 1
                if reason and len(skip_reasons) < 10:
                    skip_reasons.append(reason)

    print(f"Migration complete: {upserted} revenue requests upserted, {skipped} skipped.")
    if skip_reasons:
        print("Sample skip reasons:")
        for reason in skip_reasons:
            print(f"  - {reason}")

    post = get_connection_status()
    stats = post.get("stats") or {}
    print(
        f"Database now has {stats.get('clients', 0)} clients and "
        f"{stats.get('requests', 0)} revenue requests."
    )


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Migrate SLAM CSV data to PostgreSQL")
    parser.add_argument("--data-path", help="Override path to Revenue_Tracker_Migration folder")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSV load only")
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Create tables only (same as Scripts/init_db.py)",
    )
    args = parser.parse_args()

    try:
        if args.init_schema:
            engine = create_db_engine()
            init_schema(engine)
            print("Schema initialized (clients + revenue_requests). No CSV data loaded.")
            return 0
        data_dir = resolve_csv_dir(args.data_path)
        migrate(data_dir, dry_run=args.dry_run)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
