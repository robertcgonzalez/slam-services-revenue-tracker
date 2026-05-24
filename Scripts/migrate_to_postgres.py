#!/usr/bin/env python3
"""Phase 3 — migrate Clients.csv + RevenueRequests.csv into PostgreSQL.

Reads CSVs from the same paths as App/app.py (local or SLAM_DATA_PATH override),
creates Blueprint Section 7 schema (clients + revenue_requests), and upserts rows.

Usage:
  python Scripts/migrate_to_postgres.py
  python Scripts/migrate_to_postgres.py --dry-run
  python Scripts/migrate_to_postgres.py --data-path "C:/SLAM-Services-Project/Data/Revenue_Tracker_Migration"

Requires DATABASE_URL or POSTGRES_HOST/USER/PASSWORD in environment (or .env locally).
Never commit credentials or client CSVs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Allow imports from App/ when run from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from App.db_utils import (  # noqa: E402
    Client,
    RevenueRequest,
    create_db_engine,
    get_session,
    init_schema,
)


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
        df[col] = (
            df[col].astype(str).str.strip().str.lower().isin(["yes", "y", "true", "1", "✔", "✓"])
        )
    return df


def _parse_date(value) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    parsed = pd.to_datetime(s, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _industry_category(name: str) -> str:
    n = str(name).upper()
    if any(
        x in n
        for x in ["GRILL", "CANTINA", "RESTAURANT", "TACOS", "MEX", "BAR", "TAQUERIA", "FIESTA"]
    ):
        return "Restaurant/Bar"
    if any(
        x in n
        for x in [
            "CONCRETE",
            "ROOF",
            "BUILDER",
            "MASON",
            "PAINT",
            "REMODEL",
            "PLUMB",
            "CONTRACT",
            "DRY",
        ]
    ):
        return "Construction/Trades"
    return "Other"


def migrate(data_dir: Path, dry_run: bool = False) -> None:
    clients_df = load_clients_csv(data_dir)
    requests_df = load_requests_csv(data_dir)
    print(
        f"Loaded {len(clients_df)} clients and {len(requests_df)} revenue requests from {data_dir}"
    )

    if dry_run:
        print("Dry run — no database writes.")
        return

    engine = create_db_engine()
    init_schema(engine)

    with get_session(engine) as session:
        name_to_id: dict[str, int] = {}
        for _, row in clients_df.iterrows():
            business_name = str(row["Business Name"]).strip()
            existing = session.query(Client).filter(Client.business_name == business_name).first()
            industry = _industry_category(business_name)
            if existing:
                existing.ein = str(row.get("EIN", "") or "")
                existing.entity_type = str(row.get("Entity Type", "") or "")
                existing.address = str(row.get("City State Zip", "") or "")
                existing.industry_type = industry
                name_to_id[business_name] = existing.client_id
            else:
                client = Client(
                    business_name=business_name,
                    ein=str(row.get("EIN", "") or ""),
                    entity_type=str(row.get("Entity Type", "") or ""),
                    address=str(row.get("City State Zip", "") or ""),
                    industry_type=industry,
                    status="Active",
                )
                session.add(client)
                session.flush()
                name_to_id[business_name] = client.client_id

        session.flush()
        upserted = 0
        skipped = 0
        for _, row in requests_df.iterrows():
            business_name = str(row["business_name"]).strip()
            client_id = name_to_id.get(business_name)
            if client_id is None:
                skipped += 1
                continue
            rid = int(float(row["request_id"]))
            existing = (
                session.query(RevenueRequest).filter(RevenueRequest.request_id == rid).first()
            )
            payload = dict(
                client_id=client_id,
                request_type=str(row.get("request_type", "") or ""),
                period=str(row.get("period", "") or ""),
                amount_due=float(row.get("amount_due", 0) or 0),
                status=str(row.get("status", "Pending") or "Pending"),
                due_date=_parse_date(row.get("due_date")),
                received_date=_parse_date(row.get("received_date")),
                notes=str(row.get("notes", "") or ""),
                bank_statement_received=bool(row.get("bank_statement_received", False)),
                sales_report_received=bool(row.get("sales_report_received", False)),
            )
            if existing:
                for key, val in payload.items():
                    setattr(existing, key, val)
            else:
                session.add(RevenueRequest(request_id=rid, **payload))
            upserted += 1

    print(
        f"Migration complete: {upserted} revenue requests upserted, {skipped} skipped (unknown client)."
    )


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Migrate SLAM CSV data to PostgreSQL")
    parser.add_argument("--data-path", help="Override path to Revenue_Tracker_Migration folder")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSV load only")
    args = parser.parse_args()

    try:
        data_dir = resolve_csv_dir(args.data_path)
        migrate(data_dir, dry_run=args.dry_run)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
