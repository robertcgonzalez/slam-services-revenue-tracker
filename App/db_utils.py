"""PostgreSQL connection utilities for Phase 3 database transition.

Connection string is read from environment variables only — never hard-coded.
Set USE_POSTGRES=true in Azure App Settings when the database is provisioned.
"""

from __future__ import annotations

import os
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

Base = declarative_base()

_engine: Engine | None = None


class Client(Base):
    """Current production schema (see db/schema.sql for the canonical definition).
    Clients master table. Used by Revenue Requests, Bank Statements client selector,
    payee rules, and audit actor display. Soft-delete + full audit fields.
    """

    __tablename__ = "clients"

    client_id = Column(Integer, primary_key=True, autoincrement=True)
    business_name = Column(String(255), nullable=False, unique=True, index=True)
    owner_name = Column(String(255), default="")
    email = Column(String(255), default="")
    phone = Column(String(50), default="")
    address = Column(String(500), default="")
    ein = Column(String(50), default="")
    entity_type = Column(String(100), default="")
    industry_type = Column(String(100), default="Other")
    status = Column(String(50), default="Active")
    access_block_notes = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), default="system")
    updated_by = Column(String(100), default="system")
    is_deleted = Column(Boolean, default=False)


class RevenueRequest(Base):
    """Current production schema (see db/schema.sql for the canonical definition).
    Core revenue-chasing work queue. The two boolean flags
    (bank_statement_received, sales_report_received) are mutated directly from the
    Bank Statements page after successful Azure DI processing or Grok Vision paste.
    Soft-delete + full audit fields (updated_by comes from SLAM_APP_USER).
    """

    __tablename__ = "revenue_requests"

    request_id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.client_id"), nullable=False, index=True)
    request_type = Column(String(100), default="")
    period = Column(String(20), default="")
    amount_due = Column(Numeric(12, 2), default=0)
    status = Column(String(50), default="Pending")
    due_date = Column(Date, nullable=True)
    received_date = Column(Date, nullable=True)
    notes = Column(Text, default="")
    bank_statement_received = Column(Boolean, default=False)
    sales_report_received = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), default="system")
    updated_by = Column(String(100), default="system")
    is_deleted = Column(Boolean, default=False)


def _default_sslmode(host: str) -> str | None:
    """Azure Flexible Server requires SSL; allow override via POSTGRES_SSLMODE."""
    explicit = os.environ.get("POSTGRES_SSLMODE", "").strip()
    if explicit:
        return explicit
    if ".postgres.database.azure.com" in host:
        return "require"
    return None


def get_database_url() -> str | None:
    """Build PostgreSQL URL from DATABASE_URL or discrete POSTGRES_* env vars."""
    direct = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_CONNECTION_STRING")
    if direct:
        return direct.strip()

    host = os.environ.get("POSTGRES_HOST", "").strip()
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "")
    dbname = os.environ.get("POSTGRES_DB", "slam_services").strip()
    port = os.environ.get("POSTGRES_PORT", "5432").strip()
    if host and user and password:
        url = (
            f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{quote_plus(dbname)}"
        )
        sslmode = _default_sslmode(host)
        if sslmode and "sslmode=" not in url:
            url = f"{url}?sslmode={sslmode}"
        return url
    return None


def reset_db_engine() -> None:
    """Dispose cached engine (after connection failures or config changes)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def get_db_engine() -> Engine:
    """Return a shared SQLAlchemy engine with Azure-friendly pool settings."""
    global _engine
    if _engine is not None:
        return _engine

    url = get_database_url()
    if not url:
        raise RuntimeError(
            "PostgreSQL not configured. Set DATABASE_URL or POSTGRES_HOST/USER/PASSWORD "
            "(and optional POSTGRES_DB, POSTGRES_PORT, POSTGRES_SSLMODE)."
        )

    host = os.environ.get("POSTGRES_HOST", "")
    connect_args: dict[str, Any] = {}
    sslmode = _default_sslmode(host)
    if sslmode and "sslmode=" not in url:
        connect_args["sslmode"] = sslmode

    _engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=int(os.environ.get("POSTGRES_POOL_SIZE", "5")),
        max_overflow=int(os.environ.get("POSTGRES_MAX_OVERFLOW", "10")),
        pool_recycle=int(os.environ.get("POSTGRES_POOL_RECYCLE", "1800")),
        connect_args=connect_args,
    )
    return _engine


def create_db_engine() -> Engine:
    """Backward-compatible alias for scripts and migrations."""
    return get_db_engine()


def init_schema(engine: Engine | None = None) -> None:
    """Create clients + revenue_requests tables if they do not exist.

    The authoritative definition lives in db/schema.sql (heavily commented).
    SQLAlchemy ``create_all`` creates tables and simple column indexes only;
    partial indexes from schema.sql are applied immediately afterward.
    """
    eng = engine or get_db_engine()
    Base.metadata.create_all(eng)
    partial_indexes = (
        "CREATE INDEX IF NOT EXISTS idx_clients_status_active "
        "ON clients (status) WHERE is_deleted = FALSE",
        "CREATE INDEX IF NOT EXISTS idx_revenue_requests_status "
        "ON revenue_requests (status) WHERE is_deleted = FALSE",
        "CREATE INDEX IF NOT EXISTS idx_revenue_requests_due_date "
        "ON revenue_requests (due_date) WHERE is_deleted = FALSE",
        "CREATE INDEX IF NOT EXISTS idx_revenue_requests_bank_stmt_received "
        "ON revenue_requests (bank_statement_received) WHERE is_deleted = FALSE",
        "CREATE INDEX IF NOT EXISTS idx_revenue_requests_sales_rpt_received "
        "ON revenue_requests (sales_report_received) WHERE is_deleted = FALSE",
    )
    with eng.begin() as conn:
        for stmt in partial_indexes:
            conn.execute(text(stmt))


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    eng = engine or get_db_engine()
    session_factory = sessionmaker(bind=eng)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_connection(*, reset: bool = False) -> tuple[bool, str]:
    """Return (ok, message) for health checks."""
    if reset:
        reset_db_engine()
    url = get_database_url()
    if not url:
        return False, "No DATABASE_URL or POSTGRES_* environment variables set."
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "PostgreSQL connection OK."
    except Exception as exc:
        reset_db_engine()
        return False, friendly_db_error(exc)


def get_db_stats(engine: Engine | None = None) -> dict[str, int]:
    """Row counts for production health / sidebar display."""
    with get_session(engine) as session:
        clients = session.query(Client).filter(Client.is_deleted.is_(False)).count()
        requests = (
            session.query(RevenueRequest).filter(RevenueRequest.is_deleted.is_(False)).count()
        )
    return {"clients": clients, "requests": requests}


def get_connection_status(*, reset: bool = False) -> dict[str, Any]:
    """Structured status for UI, health_check.py, and startup diagnostics."""
    configured = get_database_url() is not None
    ok, msg = test_connection(reset=reset)
    status: dict[str, Any] = {
        "configured": configured,
        "connected": ok,
        "message": msg,
        "stats": None,
    }
    if ok:
        try:
            status["stats"] = get_db_stats()
        except Exception as exc:
            status["message"] = f"{msg} Row counts unavailable: {friendly_db_error(exc)}"
    return status


def friendly_db_error(exc: Exception) -> str:
    """Laura-friendly database error text for UI and logs."""
    raw = str(exc).strip()
    lower = raw.lower()
    if "connection refused" in lower or "could not connect" in lower:
        return (
            "The database server is not reachable. "
            "Check that PostgreSQL is running and firewall rules allow this app."
        )
    if "password authentication failed" in lower or "authentication failed" in lower:
        return "Database login failed — verify POSTGRES_USER and POSTGRES_PASSWORD App Settings."
    if "timeout" in lower or "timed out" in lower:
        return (
            "Database connection timed out — the server may be starting up "
            "or blocked by a firewall."
        )
    if "does not exist" in lower and "database" in lower:
        return "The configured database name was not found — run init_db.py or create the database first."
    if "ssl" in lower and ("required" in lower or "negotiation" in lower):
        return (
            "Secure connection (SSL) required — set POSTGRES_SSLMODE=require for Azure PostgreSQL."
        )
    if "no pg_hba.conf entry" in lower:
        return (
            "Database firewall blocked this app — add an Azure firewall rule "
            "or allow Azure services."
        )
    if raw:
        return f"Database error: {raw}"
    return "An unknown database error occurred."


def industry_category(name: str) -> str:
    """Match app.py client industry bucketing for CSV sync."""
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


def sync_clients_from_csv(
    clients_df,
    *,
    updated_by: str | None = None,
    engine: Engine | None = None,
) -> tuple[int, int, dict[str, int]]:
    """Upsert clients from a Clients.csv-style dataframe.

    Returns (created_count, updated_count, business_name -> client_id map).
    Restores soft-deleted clients when they reappear in CSV.
    """
    actor = updated_by or get_actor()
    created = 0
    updated = 0
    name_to_id: dict[str, int] = {}

    with get_session(engine) as session:
        for _, row in clients_df.iterrows():
            business_name = str(row.get("Business Name", "")).strip()
            if not business_name:
                continue
            industry = industry_category(business_name)
            existing = session.query(Client).filter(Client.business_name == business_name).first()
            fields = {
                "ein": str(row.get("EIN", "") or ""),
                "entity_type": str(row.get("Entity Type", "") or ""),
                "address": str(row.get("City State Zip", "") or ""),
                "industry_type": industry,
                "status": "Active",
                "is_deleted": False,
                "updated_by": actor,
            }
            if existing:
                for key, val in fields.items():
                    setattr(existing, key, val)
                name_to_id[business_name] = existing.client_id
                updated += 1
            else:
                client = Client(
                    business_name=business_name,
                    created_by=actor,
                    **fields,
                )
                session.add(client)
                session.flush()
                name_to_id[business_name] = client.client_id
                created += 1
    return created, updated, name_to_id


def upsert_revenue_request_from_row(
    session: Session,
    row,
    name_to_id: dict[str, int],
    *,
    updated_by: str | None = None,
) -> tuple[bool, str | None]:
    """Idempotent revenue request upsert from a CSV/editor row. Returns (ok, skip_reason)."""
    actor = updated_by or get_actor()
    business_name = str(row.get("business_name", "")).strip()
    client_id = name_to_id.get(business_name)
    if client_id is None:
        return False, f"unknown client '{business_name}'"

    pk = normalize_request_id(row.get("request_id"))
    if pk is None:
        return False, f"invalid request_id {row.get('request_id')!r}"

    payload = _row_to_payload(row)
    payload["client_id"] = client_id
    payload["request_type"] = str(row.get("request_type", "") or "")
    payload["period"] = str(row.get("period", "") or "")

    existing = session.query(RevenueRequest).filter(RevenueRequest.request_id == pk).first()
    if existing:
        for key, val in payload.items():
            setattr(existing, key, val)
        existing.is_deleted = False
        existing.updated_by = actor
    else:
        session.add(
            RevenueRequest(
                request_id=pk,
                created_by=actor,
                updated_by=actor,
                is_deleted=False,
                **payload,
            )
        )
    return True, None


def get_actor() -> str:
    """Audit actor for write-back (override via SLAM_APP_USER App Setting)."""
    return os.environ.get("SLAM_APP_USER", "streamlit").strip() or "streamlit"


def normalize_request_id(rid) -> int | None:
    """Coerce display/CSV request_id values to integer PK."""
    if rid is None:
        return None
    s = str(rid).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def parse_date(value) -> date | None:
    """Parse due/received dates from CSV, editor, or DB values."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")[:10]).date()
    except ValueError:
        return None


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("yes", "y", "true", "1", "✔", "✓")


def _row_to_payload(row) -> dict:
    amount = row.get("amount_due")
    try:
        amount_dec = Decimal(str(float(amount or 0)))
    except (ValueError, TypeError):
        amount_dec = Decimal("0")
    return {
        "status": str(row.get("status", "Pending") or "Pending"),
        "amount_due": amount_dec,
        "due_date": parse_date(row.get("due_date")),
        "received_date": parse_date(row.get("received_date")),
        "notes": str(row.get("notes", "") or ""),
        "bank_statement_received": parse_bool(row.get("bank_statement_received")),
        "sales_report_received": parse_bool(row.get("sales_report_received")),
    }


def update_revenue_request(
    session: Session,
    request_id: int,
    *,
    updated_by: str | None = None,
    **fields,
) -> RevenueRequest | None:
    """Update a single revenue request row (status, amounts, dates, flags, notes)."""
    req = (
        session.query(RevenueRequest)
        .filter(RevenueRequest.request_id == request_id, RevenueRequest.is_deleted.is_(False))
        .first()
    )
    if req is None:
        return None

    actor = updated_by or get_actor()
    if "status" in fields and fields["status"] is not None:
        req.status = str(fields["status"])
    if "amount_due" in fields and fields["amount_due"] is not None:
        req.amount_due = Decimal(str(fields["amount_due"]))
    if "due_date" in fields:
        req.due_date = parse_date(fields["due_date"])
    if "received_date" in fields:
        req.received_date = parse_date(fields["received_date"])
    if "notes" in fields:
        req.notes = str(fields["notes"] or "")
    if "bank_statement_received" in fields:
        req.bank_statement_received = parse_bool(fields["bank_statement_received"])
    if "sales_report_received" in fields:
        req.sales_report_received = parse_bool(fields["sales_report_received"])
    req.updated_by = actor
    return req


def bulk_update_status(
    request_ids: Iterable,
    status: str,
    *,
    updated_by: str | None = None,
    engine: Engine | None = None,
) -> tuple[int, list[str]]:
    """Set status on multiple revenue requests in one transaction."""
    actor = updated_by or get_actor()
    warnings: list[str] = []
    normalized: list[int] = []
    for rid in request_ids:
        pk = normalize_request_id(rid)
        if pk is None:
            warnings.append(f"Invalid request_id: {rid!r}")
        else:
            normalized.append(pk)

    updated = 0
    with get_session(engine) as session:
        for pk in normalized:
            req = update_revenue_request(session, pk, status=status, updated_by=actor)
            if req is None:
                warnings.append(f"Request {pk} not found in database (skipped).")
            else:
                updated += 1
    return updated, warnings


def save_revenue_requests_from_df(
    df,
    *,
    updated_by: str | None = None,
    engine: Engine | None = None,
) -> tuple[int, list[str]]:
    """Persist edited revenue request rows from the Streamlit editor dataframe."""
    actor = updated_by or get_actor()
    warnings: list[str] = []
    updated = 0

    with get_session(engine) as session:
        for _, row in df.iterrows():
            pk = normalize_request_id(row.get("request_id"))
            if pk is None:
                warnings.append(f"Skipped row with invalid request_id: {row.get('request_id')!r}")
                continue
            payload = _row_to_payload(row)
            req = update_revenue_request(session, pk, updated_by=actor, **payload)
            if req is None:
                warnings.append(f"Request {pk} not found in database (skipped).")
            else:
                updated += 1
    return updated, warnings
