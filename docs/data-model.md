# Data Model & Schema — SLAM Services (Delegated Companion)

**Status**: Populated 2026-05-28 as the first real content delegation in the Blueprint Hub Evolution (see `Documents/Blueprint_Hub_Evolution_Audit_2026-05-28.md` and Blueprint Section 7).

**Role**: Specialized, living technical reference for the project's core data model. This document owns the detailed entity definitions, attribute lists, relationships, and migration notes. The Blueprint retains only high-level strategy and pointers.

**Owner**: Robert (with input from any future DB migration work).

**Relationship to Blueprint**: Per the 2026-05-28 hub methodology decision, detailed schema content no longer lives in the Blueprint. This companion is the single source for that depth.

---

## Current High-Level Model

- **Primary store (production)**: Azure Database for PostgreSQL (Flexible Server) when `USE_POSTGRES=true`.
- **Fallback**: CSV files under `Data/` (fully supported, zero-disruption path).
- **Inspiration**: Original `Business problem.docx` Dataverse proposal, adapted for code-first relational + pragmatic CSV parity.
- **Key characteristics**: Normalized tables, audit fields, soft-delete safety, document linking via JSON or junction tables.

---

## Detailed Entities & Key Fields

### Clients (Core master table)

- `client_id` (PK, UUID or serial)
- `business_name`
- `owner_name`
- `email`, `phone`, `address`
- `industry_type` (e.g., Restaurant, Bar, Construction)
- `status` (Active, Inactive, Prospect)
- `onboarding_date`, `notes`
- `access_block_notes` (from existing data)

### RevenueRequests (Phase 1 focus – tracks revenue chasing)

- `request_id` (PK)
- `client_id` (FK)
- `request_type` (e.g., Monthly Bookkeeping, Sales Tax, Liquor Tax)
- `period` (e.g., "2025-04")
- `amount_due`
- `status` (Pending, Received, Invoiced, Paid)
- `due_date`
- `received_date`
- `document_links` (JSON or separate table)
- `notes`

### Documents

- `document_id` (PK)
- `client_id` (FK)
- `document_type` (BankStatement, PayrollData, SalesReport, LiquorTaxReport, TaxForm, etc.)
- `file_name`, `file_path` (Google Drive/OneDrive link)
- `upload_date`, `uploaded_by`
- `status` (Received, Processed, Archived)
- `ai_extraction_confidence`
- `linked_to` (e.g., BankReconciliation ID, PayrollRun ID)

### BankStatements

- `statement_id` (PK)
- `client_id` (FK)
- `document_id` (FK)
- `statement_month`
- `bank_name`
- `starting_balance`, `ending_balance`
- `processing_status`
- `ai_extraction_date`

### Transactions

- `transaction_id` (PK)
- `statement_id` (FK)
- `client_id` (FK)
- `date`, `description`, `amount`
- `category` (AI-assisted)
- `reconciliation_status` (Matched, Unmatched, Pending)
- `matched_to` (reference to bookkeeping entry)

### BankReconciliations

- `reconciliation_id` (PK)
- `client_id` (FK)
- `statement_id` (FK)
- `period`
- `status` (In Progress, Completed, Reviewed)
- `difference_amount`
- `completed_date`
- `reviewed_by`

### PayrollRuns

- `payroll_id` (PK)
- `client_id` (FK)
- `pay_period`
- `pay_date`
- `total_gross`, `total_net`, `total_taxes`
- `status`
- `document_id` (FK)

### SalesTaxFilings & LiquorTaxFilings

- Similar structure to PayrollRuns with filing-specific fields (due_date, filed_date, confirmation_number, liability_amount)

### Invoices

- `invoice_id` (PK)
- `client_id` (FK)
- `invoice_date`, `due_date`
- `total_amount`
- `status` (Draft, Sent, Paid)
- `linked_services` (JSON array of related Payroll/BankRec/etc. IDs)

### Tasks / Communications / Reminders

- Support tracking of deadlines, notes, messages, and automated reminders.

### Audit Fields (on all tables)

- `created_at`, `updated_at`
- `created_by`, `updated_by`
- `is_deleted` (soft delete)

### Relationships

- One-to-Many: Client → Documents, RevenueRequests, BankReconciliations, PayrollRuns, etc.
- Many-to-Many: Documents ↔ Services (via junction table if needed)

This schema supports the full scope from the original Business Problem (document management, bank recs, payroll, tax filings, invoicing, reminders).

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