-- db/schema.sql
-- Canonical, production-grade definition of the current live PostgreSQL schema
-- for SLAM Services Revenue Tracker (as of the 2026 Azure DI Bank Statement go-live).
--
-- This file is the SINGLE SOURCE OF TRUTH for the tables that actually exist
-- in the Azure Database for PostgreSQL (Flexible Server) when USE_POSTGRES=true.
--
-- It is intentionally minimal and accurate to the current implementation.
-- Future entities (Documents, Transactions, BankReconciliations, Payroll, etc.)
-- live only in the "Future / Aspirational" section of docs/data-model.md until
-- they are implemented and promoted here.
--
-- How to use:
--   • Local development:  psql $DATABASE_URL -f db/schema.sql
--   • Or rely on App/db_utils.py:init_schema() which does the SQLAlchemy equivalent
--     of the CREATE TABLE statements below.
--   • Verification: Compare output of \d+ against this file after any change.
--
-- Maintenance rule (per 2026 go-live decision):
--   Any change to the live tables MUST be reflected here + in App/db_utils.py
--   models + in the "Current Implemented" section of docs/data-model.md on the
--   same commit. The DI pipeline writes (bank_statement_received etc.) make this
--   schema part of the daily operational backbone.
--
-- ============================================================================

-- Enable required extensions (Azure Flexible Server usually has them; safe to run)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- not currently used

-- ============================================================================
-- Table: clients
-- ============================================================================
-- Primary master table for SLAM Services clients.
-- Populated initially from Data/Revenue_Tracker_Migration/Clients.csv via
-- migrate_to_postgres.py and kept in sync with CSV fallback mode.
--
-- Used by: Dashboard, Revenue Requests, Bank Statements (client selector),
--          payee rules scoping, audit actor display.
--
-- Soft-delete + audit pattern is consistent across all tables.

CREATE TABLE IF NOT EXISTS clients (
    client_id       SERIAL PRIMARY KEY,
    business_name   VARCHAR(255) NOT NULL UNIQUE,
    owner_name      VARCHAR(255)        DEFAULT '',
    email           VARCHAR(255)        DEFAULT '',
    phone           VARCHAR(50)         DEFAULT '',
    address         VARCHAR(500)        DEFAULT '',
    ein             VARCHAR(50)         DEFAULT '',
    entity_type     VARCHAR(100)        DEFAULT '',
    industry_type   VARCHAR(100)        DEFAULT 'Other',
    status          VARCHAR(50)         DEFAULT 'Active',
    access_block_notes TEXT             DEFAULT '',
    notes           TEXT                DEFAULT '',
    created_at      TIMESTAMPTZ         DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         DEFAULT NOW(),
    created_by      VARCHAR(100)        DEFAULT 'system',
    updated_by      VARCHAR(100)        DEFAULT 'system',
    is_deleted      BOOLEAN             DEFAULT FALSE
);

-- Helpful indexes for the daily driver queries (client lookup + filter)
CREATE INDEX IF NOT EXISTS idx_clients_business_name ON clients (business_name);
CREATE INDEX IF NOT EXISTS idx_clients_status_active ON clients (status) WHERE is_deleted = FALSE;

COMMENT ON TABLE  clients IS 'Master list of SLAM Services clients. Single source for business_name across Revenue Requests and Bank Statements.';
COMMENT ON COLUMN clients.business_name IS 'Primary display name / lookup key. Must be unique and stable.';
COMMENT ON COLUMN clients.industry_type IS 'Used for high-level bucketing in UI and reporting (Restaurant/Bar, Construction, etc.).';
COMMENT ON COLUMN clients.is_deleted IS 'Soft-delete flag. Never hard-delete client rows for audit integrity.';

-- ============================================================================
-- Table: revenue_requests
-- ============================================================================
-- Core operational table for the revenue-chasing workflow.
-- This is the "daily driver" table for Laura & Stef.
--
-- The two boolean columns (bank_statement_received, sales_report_received)
-- are mutated directly from the Bank Statements page when a statement is
-- successfully processed and "Mark as Received" is clicked.
--
-- The new Azure Document Intelligence pipeline (2026 go-live) feeds richer
-- data into the Bank Statements workflow that ultimately updates these flags
-- and the notes / status fields.
--
-- Populated from Data/Revenue_Tracker_Migration/RevenueRequests.csv and kept
-- in sync with CSV mode.

CREATE TABLE IF NOT EXISTS revenue_requests (
    request_id                INTEGER PRIMARY KEY,
    client_id                 INTEGER NOT NULL REFERENCES clients(client_id),
    request_type              VARCHAR(100)        DEFAULT '',
    period                    VARCHAR(20)         DEFAULT '',
    amount_due                NUMERIC(12,2)       DEFAULT 0,
    status                    VARCHAR(50)         DEFAULT 'Pending',
    due_date                  DATE,
    received_date             DATE,
    notes                     TEXT                DEFAULT '',
    bank_statement_received   BOOLEAN             DEFAULT FALSE,
    sales_report_received     BOOLEAN             DEFAULT FALSE,
    created_at                TIMESTAMPTZ         DEFAULT NOW(),
    updated_at                TIMESTAMPTZ         DEFAULT NOW(),
    created_by                VARCHAR(100)        DEFAULT 'system',
    updated_by                VARCHAR(100)        DEFAULT 'system',
    is_deleted                BOOLEAN             DEFAULT FALSE
);

-- Critical indexes for the "Today's priority", overdue, and missing-docs views
CREATE INDEX IF NOT EXISTS idx_revenue_requests_client_id ON revenue_requests (client_id);
CREATE INDEX IF NOT EXISTS idx_revenue_requests_status ON revenue_requests (status) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_revenue_requests_due_date ON revenue_requests (due_date) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_revenue_requests_bank_stmt_received ON revenue_requests (bank_statement_received) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_revenue_requests_sales_rpt_received ON revenue_requests (sales_report_received) WHERE is_deleted = FALSE;

COMMENT ON TABLE  revenue_requests IS 'Primary revenue-chasing work queue. Bank Statements page writes directly to the *_received flags and notes.';
COMMENT ON COLUMN revenue_requests.request_id IS 'Stable business key (matches the CSV source). Not a surrogate UUID.';
COMMENT ON COLUMN revenue_requests.bank_statement_received IS 'Set true by Bank Statements "Mark as Received" action after successful DI or Grok Vision parse. Drives Missing Docs views.';
COMMENT ON COLUMN revenue_requests.sales_report_received IS 'Companion flag for sales reports. Same mutation path as bank_statement_received.';
COMMENT ON COLUMN revenue_requests.updated_by IS 'Audit actor (SLAM_APP_USER from App Settings: Laura, Stef, Robert, etc.).';

-- ============================================================================
-- Future-proofing notes (do not add tables here until implemented)
-- ============================================================================
-- When the imaging leg / DI pipeline begins persisting extracted checks,
-- crop metadata, or per-statement provenance, those columns or a new
-- bank_statement_extractions table will be added here with a dated comment
-- and a matching model update in App/db_utils.py.
--
-- Any such addition must also update:
--   • docs/data-model.md (move from Future to Current Implemented)
--   • The Cursor rename / schema prompt artifacts if relevant
--   • This file + init_schema() behavior

-- End of canonical schema (2026 DI go-live baseline)
