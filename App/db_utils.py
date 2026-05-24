"""PostgreSQL connection utilities for Phase 3 database transition.

Connection string is read from environment variables only — never hard-coded.
Set USE_POSTGRES=true in Azure App Settings when the database is provisioned.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

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


class Client(Base):
    """Blueprint Section 7 — Clients (Phase 3 initial schema)."""

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
    """Blueprint Section 7 — RevenueRequests (Phase 3 initial schema)."""

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


def get_database_url() -> str | None:
    """Build PostgreSQL URL from DATABASE_URL or discrete POSTGRES_* env vars."""
    direct = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_CONNECTION_STRING")
    if direct:
        return direct

    host = os.environ.get("POSTGRES_HOST")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    dbname = os.environ.get("POSTGRES_DB", "slam_services")
    port = os.environ.get("POSTGRES_PORT", "5432")
    if host and user and password:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return None


def create_db_engine() -> Engine:
    url = get_database_url()
    if not url:
        raise RuntimeError(
            "PostgreSQL not configured. Set DATABASE_URL or POSTGRES_HOST/USER/PASSWORD "
            "(and optional POSTGRES_DB, POSTGRES_PORT)."
        )
    return create_engine(url, pool_pre_ping=True)


def init_schema(engine: Engine | None = None) -> None:
    """Create clients + revenue_requests tables if they do not exist."""
    engine = engine or create_db_engine()
    Base.metadata.create_all(engine)


@contextmanager
def get_session(engine: Engine | None = None) -> Generator[Session, None, None]:
    engine = engine or create_db_engine()
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_connection() -> tuple[bool, str]:
    """Return (ok, message) for health checks."""
    url = get_database_url()
    if not url:
        return False, "No DATABASE_URL or POSTGRES_* environment variables set."
    try:
        engine = create_db_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "PostgreSQL connection OK."
    except Exception as exc:
        return False, f"PostgreSQL connection failed: {exc}"
