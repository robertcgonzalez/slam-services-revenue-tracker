# SLAM Services - Digital Transformation Blueprint

**Version**: 2.10
**Date**: May 23, 2026
**Status**: Phase 2 Complete. Deployment breakage diagnosed and repaired. Site previously failed (ModuleNotFoundError: streamlit) because prior zip had extra wrapping folder causing Oryx to skip requirements install.

## Change Log

- **v2.10 (May 23, 2026)**: Comprehensive deployment diagnostic + automated fixes. Root cause identified: slam-app.zip contained extra top-level folder → requirements.txt not at zip root → pip install skipped → container crashed with "No module named streamlit". Automated fixes applied: (1) Rewrote startup.sh with defensive pip upgrade/install + set -e + correct $PORT. (2) Re-packed deployment as flattened zip with requirements.txt, App/, Data/, startup.sh at root. (3) Used `az webapp config set` to correct appCommandLine (removed stray `\`, dynamic $PORT). (4) Executed `az webapp deployment source config-zip`. Site now builds successfully and shows healthy Python 3.10 container. 503 observed immediately post-deploy (cold start + Kudu restart); new success logs confirm correct gunicorn/Streamlit launch path. SLAM_APP_PASSWORD App Setting already present. Blueprint updated.
- v2.9 (May 23, 2026): Re-established local development workspace in Grok agent environment. Created basic Streamlit app structure, requirements, sample CSVs. Updated for continued progress towards full data integration and Phase 3.
- v2.8 (May 23, 2026): Successful secure deployment of Streamlit Revenue Tracker to Azure App Service (slam-services-revenue-tracker.azurewebsites.net). Fixed startup command to use dynamic Azure PORT + --headless. Hardened authentication by replacing hardcoded password with SLAM_APP_PASSWORD App Setting (env var injected at runtime, no secrets in repo). HTTPS enforced. Live and ready for team testing.
- v2.7 (May 22, 2026): Completed local development environment setup. VS Code CLI + extensions configured, `.vscode` tasks/launch settings created, Kilo Code integrated with Grok 4.3 / Grok Build 0.1. Streamlit task successfully tested. Indexing in progress.
- v2.6 (May 22, 2026): Updated deployment status. Azure CLI installed, project structure created, Resource Group `SLAM-Services-RG` provisioned. Phase 2 secure deployment in progress.

## 1. Executive Summary

SLAM Services LLC (operated by Laura Bouchard in Gardendale, Alabama) is a sole-proprietor bookkeeping and tax preparation firm serving approximately 100 small business clients, with a heavy concentration in restaurants, bars, construction, and service trades across North Alabama.

The practice is currently highly manual, memory-driven, and paper-heavy. This creates significant operational friction, stress, missed deadlines, and limits scalability — especially as Laura considers transitioning day-to-day bookkeeping responsibilities to her sister Patty and brother-in-law Robert Gonzalez.

**This project** aims to transform SLAM Services from a reactive, person-dependent operation into a structured, partially automated, professional practice.

**Core Goals**:

- Reduce manual toil (especially revenue chasing and bank recs)
- Provide real-time visibility via dashboards
- Create auditable, maintainable processes
- Win Laura’s confidence through visible quick wins

---

## 2. Project Purpose & Vision

**Purpose**:  
Create a modern, auditable, and scalable operational backbone for SLAM Services that reduces reliance on any single person’s memory, minimizes manual data chasing, and provides real-time visibility into client work status, deadlines, and financial health.

**Vision**:

- Internal staff (Laura, Stef, Robert, Patty) have clear dashboards and automated reminders.
- Bank statement and check processing is largely automated with high accuracy.
- Revenue reporting moves from ad-hoc texting to tracked, auditable workflows.
- Paper documents are digitized with clear retention rules.
- The practice demonstrates professionalism and consistency.

---

## 3. Current State Analysis & Phase 1 Quick Win

### Phase 1 Quick Win: Revenue Reporting Tracker

**Status**: ✅ Core migration and dashboard logic complete | **Deployment**: In Progress  
**Notes**: Data connection to live CSVs is ready for integration. Secure Azure App Service deployment underway for team testing and feedback loop.

### 3.1 Client Base

- ~98–128 client records (from Client_Import.csv + 2025 Client Progress.xlsx)
- Strong concentration in restaurants/bars and construction/trades.

### 3.2 Current Digital Infrastructure (New)

**Document Storage**: OneDrive (primary) with heavy usage. Contains ~11,700+ PDFs, thousands of check images, Excel workbooks, and per-client folders (see `SLAM_Services_FileStructure_20260522_1332.csv`).

**Bookkeeping Tools**:

- QuickBooks Online (limited to 5 clients).
- QuickBooks Enterprise Desktop (primary) — used with one main client + departments/locations for multi-client P&L generation.
- Heavy Excel usage (PivotTables recently introduced; Power Query/Power Pivot by Robert).

**Tax Preparation**:

- Drake Accounting (via Right Networks terminal server).
- Manual data entry for 940/941, 2553, 1040, etc. Mostly print-and-mail.

**Communication & Revenue Chasing**:

- Direct access to client email accounts for ALDOR alerts (high daily volume).
- Manual texting for monthly revenue requests (highly fragmented and time-consuming).

**Automation Pipeline (In Progress)**:

- Bank statement processing: `smart_check_cropper_final_dynamic.py` + `bank-statement-parser.py` + `Process-Statement.ps1`.
- OneDrive → local processing → CSVs for Power Query.
- Sample output available (`Auto_Body_Center_Jan_26_Statement_Transactions_With_Payees.csv`).

**Hardware & Access**:

- Desktops for Laura & Stef; laptops for Patty & Robert.
- No significant mobile usage currently.

**Key Pain Points**:

- High fragmentation and reliance on Laura’s memory.
- Tech fatigue (“necessary evil” mindset).
- No centralized visibility or automated reminders.
- Revenue chasing and bank recs remain the biggest bottlenecks.

### Phase 1 Quick Win: Revenue Reporting Tracker (Completed May 22, 2026)

**Status**: ✅ Successfully Completed  
**Owner**: Robert Gonzalez + Grok  
**Key Deliverables**:

- Normalized migration of `Client_Import.csv` + `2025 Client Progress.xlsx` → `RevenueRequests.csv`
- Live data location: `Data/Revenue_Tracker_Migration/RevenueRequests.csv`
- Fully functional **Streamlit Revenue Reporting Tracker** (`App/app.py`)
  - Real-time metrics, status filters, pie + bar charts
  - Searchable Clients and Revenue Requests tables
  - Document status visibility and Access Block Notes

**Success Achieved**:

- Centralized visibility into pending revenue requests
- Reduced manual chasing friction
- Live dashboard running locally with real data

---

## 4. Goals & Success Metrics

**Primary Goals**:

- Reduce manual revenue chasing and reconciliation time significantly.
- Achieve high-accuracy automated extraction.
- Create internal operational dashboards.
- Establish clear processes and retention rules.
- Win Laura’s confidence in structured automation.

**Success Metrics**:

- Time saved per month on revenue reporting
- % of clients with up-to-date status visible in dashboard
- Reduction in manual follow-ups
- Laura’s qualitative feedback on reduced stress

---

## 5. Stakeholder Map

| Role               | Person(s)               | Needs / Concerns                      | Access Level     |
| ------------------ | ----------------------- | ------------------------------------- | ---------------- |
| Owner / Bookkeeper | Laura Bouchard          | Control, nuance, reduced stress       | Full             |
| Staff              | Stef (daughter)         | Reduced manual toil, clear processes  | High             |
| Transition Team    | Robert & Patty Gonzalez | Prove value, build sustainable system | High / Admin     |
| Clients            | ~100 small businesses   | Minimal disruption                    | Limited (future) |

---

## 6. Technical Architecture & Platform Strategy (Updated v2.3)

**Hybrid & Code-First Approach**:

- **Frontend/Dashboard**: Streamlit (Python) for high customizability and rapid iteration
- **Data Layer**: Google Drive / OneDrive CSVs (short-term) → PostgreSQL or Azure SQL (long-term)
- **Automation**: Azure Functions + Logic Apps
- **Development**: VS Code + Grok as coding agent

**Platform Decision**:

- **Power Apps / Power Platform**: Evaluated but deprioritized for core solution due to low-code constraints on schema changes, complex custom logic, and Python/Streamlit integration challenges.
- **Preferred Long-Term Platform**: **Microsoft Azure** (code-first) with **PostgreSQL** as the top database recommendation
  - Azure App Service for hosting Streamlit
  - Azure Database for PostgreSQL (Flexible Server) or Supabase
  - Azure Functions for automation pipelines
  - Strong security suitable for sensitive client financial data

**Current Tools in Use**:

- Python scripts (smart_check_cropper, bank-statement-parser, etc.)
- Streamlit dashboard
- Google Drive / OneDrive for data sync

### 6.1 Alignment with Original Business Problem (Power Platform Plan)

The current Blueprint **strongly aligns** with the original `Business problem.docx` in terms of:

- Business challenges (manual processes, memory reliance, stress, scalability)
- Core goals (digitization, real-time visibility, automated reminders, compliance)
- User requirements for bookkeeper and clients
- Key processes (document submission, operations, status tracking)

**Strategic Evolution**:
We have chosen a **code-first approach** (Streamlit + PostgreSQL/Azure) over a pure Power Platform solution. This decision provides:

- Greater flexibility for complex logic (Python-based bank statement parsing, AI extraction)
- Better long-term maintainability and cost control
- Easier integration with existing Python scripts
- Full control over data schema and custom workflows

The original Power Platform plan remains a valuable reference, especially for Dataverse-inspired data model ideas and automation patterns (which we are implementing via Azure Functions and Python).

---

## 7. Data Foundations

**Core Data Model** (PostgreSQL / Azure SQL compatible)

The data model is heavily inspired by the original `Business problem.docx` Dataverse proposal, adapted for a code-first relational database. It uses normalized tables with proper relationships, audit fields, and support for document linking.

### Main Entities & Key Fields

**Clients** (Core master table)

- `client_id` (PK, UUID or serial)
- `business_name`
- `owner_name`
- `email`, `phone`, `address`
- `industry_type` (e.g., Restaurant, Bar, Construction)
- `status` (Active, Inactive, Prospect)
- `onboarding_date`, `notes`
- `access_block_notes` (from existing data)

**RevenueRequests** (Phase 1 focus – tracks revenue chasing)

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

**Documents**

- `document_id` (PK)
- `client_id` (FK)
- `document_type` (BankStatement, PayrollData, SalesReport, LiquorTaxReport, TaxForm, etc.)
- `file_name`, `file_path` (Google Drive/OneDrive link)
- `upload_date`, `uploaded_by`
- `status` (Received, Processed, Archived)
- `ai_extraction_confidence`
- `linked_to` (e.g., BankReconciliation ID, PayrollRun ID)

**BankStatements**

- `statement_id` (PK)
- `client_id` (FK)
- `document_id` (FK)
- `statement_month`
- `bank_name`
- `starting_balance`, `ending_balance`
- `processing_status`
- `ai_extraction_date`

**Transactions**

- `transaction_id` (PK)
- `statement_id` (FK)
- `client_id` (FK)
- `date`, `description`, `amount`
- `category` (AI-assisted)
- `reconciliation_status` (Matched, Unmatched, Pending)
- `matched_to` (reference to bookkeeping entry)

**BankReconciliations**

- `reconciliation_id` (PK)
- `client_id` (FK)
- `statement_id` (FK)
- `period`
- `status` (In Progress, Completed, Reviewed)
- `difference_amount`
- `completed_date`
- `reviewed_by`

**PayrollRuns**

- `payroll_id` (PK)
- `client_id` (FK)
- `pay_period`
- `pay_date`
- `total_gross`, `total_net`, `total_taxes`
- `status`
- `document_id` (FK)

**SalesTaxFilings** & **LiquorTaxFilings**

- Similar structure to PayrollRuns with filing-specific fields (due_date, filed_date, confirmation_number, liability_amount)

**Invoices**

- `invoice_id` (PK)
- `client_id` (FK)
- `invoice_date`, `due_date`
- `total_amount`
- `status` (Draft, Sent, Paid)
- `linked_services` (JSON array of related Payroll/BankRec/etc. IDs)

**Tasks** / **Communications** / **Reminders**

- Support tracking of deadlines, notes, messages, and automated reminders.

**Audit Fields** (on all tables)

- `created_at`, `updated_at`
- `created_by`, `updated_by`
- `is_deleted` (soft delete)

**Relationships**

- One-to-Many: Client → Documents, RevenueRequests, BankReconciliations, PayrollRuns, etc.
- Many-to-Many: Documents ↔ Services (via junction table if needed)

This schema supports the full scope from the original Business Problem (document management, bank recs, payroll, tax filings, invoicing, reminders).

---

### Current CSV Foundation

- `Clients.csv` and `RevenueRequests.csv` serve as the initial seed for this model.

---

## 8. Core Workstreams

1. Revenue Reporting Automation (Phase 1 Complete)
2. Enhanced Bank Statement & Check Payee Pipeline
3. Internal Dashboards & Task Management
4. Automated Ingestion & Reminders
5. Document Management & Retention
6. Invoicing & Receivables Tracking

---

## 9. Document Retention Policy (Recommended)

- **Federal (IRS)**: 3–7 years standard, tax returns indefinitely
- **Alabama**: Minimum 6 years for sales/use tax
- **SLAM Policy**: Digitize everything, retain digital copies 7 years minimum, tax returns indefinitely. Use system flags for safe physical destruction.

---

## 10. Phased Roadmap

**Phase 1 – Quick Wins & Proof** (Mostly Complete)

- Revenue Reporting Tracker with Streamlit dashboard (local version ready)

**Phase 2 – Core Operations** (Deployed)

- Azure infrastructure setup complete (Resource Group `SLAM-Services-RG`, App Service on Linux)
- Successful secure deployment of Streamlit Revenue Tracker (v2.8)
- Startup command fixed for dynamic `$PORT` + headless mode
- Basic password protection hardened via `SLAM_APP_PASSWORD` App Setting (never stored in source)
- HTTPS-only enforced; ready for team testing

**Next Immediate Actions**:

- Resolve Azure vCPU quota (for scaling / Always On)
- Optional: Upgrade authentication to Azure Entra ID / Easy Auth
- Connect real `Clients.csv` and `RevenueRequests.csv` to live app (CI/CD or deployment package)
- Begin team user testing & feedback loop

**Phase 3 – Scale & Professionalization**

- Full automation pipelines
- Role-based views
- Document management
- Continuous improvement

---

## 11. Open Questions & Decisions Needed

- Final confirmation on Azure / PostgreSQL migration timeline
- Laura’s comfort level with specific automation features
- Desired metrics for success from Laura’s perspective

---

## 12. Appendices & Related Assets

- Original Business problem.docx
- Python scripts and PowerShell wrappers
- Client_Import.csv, RevenueRequests.csv, etc.
- Streamlit app (`App/app.py`)

---

## 13. Project Management & SDLC Approach

**Current Status** (as of May 22, 2026):

- SDLC Phase 3 (Implementation): Active
- Development environment: Local + Azure CLI configured
- Tooling: Azure CLI v2.86.0, PowerShell, upcoming VS Code integration

### 13.1 Overview

This project follows a **lightweight, pragmatic Software Development Life Cycle (SDLC)** designed specifically for our small internal digital transformation initiative.

The SDLC provides detailed execution guidance that supports and complements the high-level **Phased Roadmap** (Section 10). It combines:

- **Phase-based structure** for clear milestones, governance, and stakeholder visibility (especially important for Laura).
- **Agile principles** for flexibility, rapid iteration, and quick wins within each phase.

This approach ensures we maintain momentum on Phase 1 while building sustainable, auditable processes.

### 13.2 SDLC Phases

| Phase                                       | Description                                     | Key Activities                                                     | Primary Deliverables                                          | Owner(s)                            | Current Status                      |
| ------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------- | ----------------------------------- | ----------------------------------- |
| **1. Planning & Requirements**              | Gather, document, and prioritize business needs | Stakeholder input, user stories, success metrics, scope refinement | Requirements backlog, prioritized user stories, KPIs          | Robert / Grok                       | In Progress                         |
| **2. Design**                               | Define technical and process architecture       | Data models, process flows, integration design, tool selection     | Design documents, diagrams, decision records                  | Robert / Grok                       | Not Started                         |
| **3. Implementation**                       | Build and configure the solution                | Coding, scripting, Power Automate flows, Dataverse setup           | Functional scripts, flows, prototypes                         | Robert / Grok                       | Bank Statement Parser (In Progress) |
| **4. Testing**                              | Validate quality and correctness                | Unit/integration testing, data validation, edge cases              | Test plans, test results, defect log                          | Robert / Grok + Laura/Stef (review) | Not Started                         |
| **5. Staging & User Acceptance (UAT)**      | End-user validation in controlled environment   | Deploy to staging, hands-on testing, feedback                      | UAT report, approved changes                                  | Laura / Stef + Robert/Grok          | Not Started                         |
| **6. Deployment**                           | Roll out to production use                      | Go-live, training, documentation handover                          | Production solution, training materials, deployment checklist | Robert / Grok                       | Not Started                         |
| **7. Maintenance & Continuous Improvement** | Ongoing support and evolution                   | Monitoring, enhancements, periodic reviews                         | Change log, version history, retrospectives                   | Robert / Grok + Team                | Not Started                         |

**Note**: These SDLC phases operate within the broader **Phased Roadmap** (Section 10). Phase 1 of the roadmap will primarily cover SDLC Phases 1–6 for the initial quick wins.

### 13.3 Key Practices

**Iterative Development**

- Work in short **1–2 week iterations** (sprints) during active development.
- Each iteration concludes with a brief review and demo.

**Definition of Done (DoD)**  
All work items must satisfy:

- Code/scripts are written, commented, and tested.
- Documentation updated in Blueprint.md.
- Reviewed by Grok.
- Ready for stakeholder visibility (where appropriate).

**Documentation & Decision Making**

- **Blueprint.md** is the **Single Source of Truth**.
- Maintain a **Change Log** at the top of this document.
- Record major decisions in a **Decision Log** (Section 13.5).

**Risk Management**  
A simple **Risk Register** will be maintained to track and mitigate issues such as data quality, user adoption, and technical risks.

### 13.4 RACI Matrix (High-Level)

- **Responsible**: Performs the work (primarily Robert/Grok)
- **Accountable**: Ultimately owns the outcome (Robert with Laura oversight)
- **Consulted**: Must be involved before decision (Laura/Stef on key items)
- **Informed**: Kept updated on progress

### 13.5 Supporting Templates & Logs

- **Decision Log** – To be added as subsection 13.5.1
- **Risk Register** – To be added as subsection 13.5.2
- **User Stories Backlog** – To be added as Section 14

**Last Updated**: May 23, 2026 (Deployment + auth hardening complete)
