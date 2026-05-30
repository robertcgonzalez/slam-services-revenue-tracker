# Data Model & Schema — SLAM Services (Delegated Companion)

**Status**: Populated 2026-05-28 as the first real content delegation in the Blueprint Hub Evolution (see [`QMS/State-Alignment/runs/2026-05-28-blueprint-hub-evolution.md`](../QMS/State-Alignment/runs/2026-05-28-blueprint-hub-evolution.md) and Blueprint Section 7).

**Role**: Specialized, living technical reference for the project's core data model. This document owns the detailed entity definitions, attribute lists, relationships, and migration notes. The Blueprint retains only high-level strategy and pointers.

**Owner**: Robert (with input from any future DB migration work).

**Relationship to Blueprint**: Per the 2026-05-28 hub methodology decision, detailed schema content no longer lives in the Blueprint. This companion is the single source for that depth.

---

## Current High-Level Model (Production Baseline)

- **Primary store (production)**: Azure Database for PostgreSQL (Flexible Server) when `USE_POSTGRES=true`.
- **Fallback**: CSV files under `Data/` (fully supported, zero-disruption path — never remove this).
- **Canonical definition**: `db/schema.sql` (the single source of truth for what actually exists in the live database).
- **Key characteristics**: Minimal, accurate, audit-heavy (created/updated + actor + soft-delete on every row), pragmatic CSV parity.

**Important (2026 DI go-live rule)**: Only tables listed in `db/schema.sql` are guaranteed to exist in production. Everything else below is aspirational until promoted.

---

## Current Implemented Schema (Production — 2026 DI Go-Live Baseline)

This section is **authoritative** and must match `db/schema.sql` + the SQLAlchemy models in `App/db_utils.py` at all times.

### clients
- `client_id` (SERIAL PK)
- `business_name` (unique, not null) — primary lookup key
- `owner_name`, `email`, `phone`, `address`, `ein`, `entity_type`
- `industry_type` (default 'Other')
- `status` (default 'Active')
- `access_block_notes`, `notes`
- `created_at`, `updated_at`, `created_by`, `updated_by`, `is_deleted` (soft delete)

**Usage**: Master list for Dashboard, Revenue Requests, Bank Statements client selector, payee rule scoping.

### revenue_requests
- `request_id` (INTEGER PK — stable business key from CSV source)
- `client_id` (FK → clients)
- `request_type`, `period`, `amount_due` (NUMERIC(12,2))
- `status` (default 'Pending')
- `due_date`, `received_date`
- `notes`
- `bank_statement_received` (BOOLEAN) — written by Bank Statements "Mark as Received" after DI or Grok Vision success
- `sales_report_received` (BOOLEAN) — companion flag, same mutation path
- `created_at`, `updated_at`, `created_by`, `updated_by`, `is_deleted`

**Usage**: Core daily-driver work queue. The 2026 Azure Document Intelligence bank statement pipeline directly improves the quality and speed of the data that feeds the `*_received` updates.

**Audit & soft-delete pattern** (identical on both tables):
- Never hard-delete rows.
- `updated_by` is populated from the `SLAM_APP_USER` App Setting (Laura, Stef, Robert, etc.).
- `is_deleted` filters are applied in all production queries (`get_db_stats`, UI lists, etc.).

See `db/schema.sql` for the exact `CREATE TABLE` statements, indexes, and comments. See `App/db_utils.py` for the SQLAlchemy `Client` and `RevenueRequest` models that generate the same structure via `init_schema()`.

---

## Future / Aspirational Entities (Not Yet Implemented)

The content below is retained for long-term vision and roadmap context. **None of these tables exist in the live production database** until they are implemented, added to `db/schema.sql`, and the "Current Implemented" section above is updated on the same commit.

### Documents (future)
- `document_id`, `client_id`, `document_type` (BankStatement, SalesReport, ...), `file_name`/`file_path`, `upload_date`, `uploaded_by`, `status`, `ai_extraction_confidence`, `linked_to`

### BankStatements, Transactions, BankReconciliations (future)
- (Detailed fields as previously drafted — see git history of this file for the 2026-05-28 version.)

### PayrollRuns, SalesTaxFilings, LiquorTaxFilings, Invoices, Tasks/Communications/Reminders (future)
- Similar normalized structures with status machines and document linking.

### Audit Fields (future pattern)
- Will continue the `created_at/updated_at/created_by/updated_by/is_deleted` pattern established in the current tables.

### Relationships (future)
- Will be added only when the concrete tables are promoted.

This aspirational section supports the original Business Problem scope but is **not** a commitment or current reality.

---

## Evolution & Maintenance

- **2026 DI Go-Live + Schema Robustness Workstream**: `db/schema.sql` was created as the canonical on-disk definition. `docs/data-model.md` was restructured so that "Current Implemented" is 100% accurate to production while the broader vision remains visible but clearly labeled as future work. This directly supports handoff confidence for Patty & Robert and reduces single-person memory risk (Constitution priority).
- Any future table, column, or constraint change must update **all three** locations on the same commit:
  1. `db/schema.sql`
  2. The corresponding SQLAlchemy model(s) in `App/db_utils.py`
  3. The "Current Implemented" section of this document (plus a note in the Evolution section)
- The DI bank statement pipeline (and any later persistence of crops, extracted payees, or provenance) will drive the next evolution of this schema.

**References**:
- `db/schema.sql` (production truth)
- `App/db_utils.py` (init_schema, CRUD, connection handling)
- `Scripts/init_db.py`, `Scripts/migrate_to_postgres.py`
- `docs/deployment.md` (Postgres Schema Reference subsection)
- Blueprint Section 7 (high-level strategy only)

---

## Current CSV Foundation

- `Clients.csv` and `RevenueRequests.csv` serve as the initial seed for this model.

---

## Conventions & Patterns

- UUID or serial primary keys
- Consistent `*_at` / `*_by` audit columns
- Status enums with clear state machines (document in this file when defined)
- JSON columns used sparingly for document_links and flexible metadata

---

## References

- Blueprint Section 7 (hub pointer + high-level strategy)
- `QMS/Risk-Register.md` (data classification / retention risks)
- `Scripts/migrate_to_postgres.py` and `init_db.py` (implementation)
- `Business problem.docx` (original Dataverse proposal)

*This document is the living single source for detailed data model work. Updates here do not require changes to the Blueprint except for high-level pointer refreshes.*