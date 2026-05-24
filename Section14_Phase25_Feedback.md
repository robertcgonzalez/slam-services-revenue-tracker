## 14. User Stories, Runtime Feedback & Phase 2.5 Stabilization (Added v2.11)

**Status (May 23, 2026 evening)**: First live production user-testing session completed on the deployed Azure App Service using real 2026 client data. Seven specific runtime issues were captured in real time and logged for immediate action. This section is the single source of truth for the current stabilization backlog and the new persistent feedback process.

### 14.1 Phase 2.5 Context & Purpose

- **Objective**: Stabilize the live Revenue Tracker so Laura, Stef, Patty and Robert can use it daily without friction before any further feature work or database migration.
- **Trigger**: Real usage on `https://slam-services-revenue-tracker.azurewebsites.net/` with the actual `Clients.csv` + `RevenueRequests.csv` files.
- **Key Inputs**: `Project Runtime User Stories.txt` (7 raw notes) + direct observation.
- **Output Deliverable**: This Section 14 + the living `Data/feedback_log.csv` file (permanently versioned inside the source tree and deployable).

### 14.2 Phase 2.5 Prioritized Rollout Plan (Immediate 1–2 Week Horizon)

| Wave | Priority | Item (from runtime notes) | Current Root Cause in app.py | Target Fix Description | Owner | Success Metric |
|------|----------|---------------------------|------------------------------|------------------------|-------|----------------|
| P0 – Day 1 | P0 | "request_id" and "business_name" columns show blank / no useful data in Dashboard Overdue table and Recent Activity | Tables are selecting columns that do not exist or have different casing after load_clients()/load_requests() transformations | Change column selections in dashboard_page() to always use the standardized snake_case columns that load_requests() guarantees (`business_name`, `request_id`) | Robert | No blank columns in those two tables on next deploy |
| P0 – Day 1 | P0 | Global Filter "Reset filters" button does nothing useful (cache clear alone not enough) | Current reset only clears cache but does not reset widget state | Change reset logic to also force a full page rerun + clear any session widgets | Robert | Button reliably clears all filters and shows all data |
| P0 – Day 1 | P0 | Revenue Requests page Right-most columns are missing the service Yes/No checkboxes that were added to RevenueRequests.csv | The data_editor is hard-coded to a fixed list of columns; `bank_statement_received` and `sales_report_received` exist in CSV but the UI is not using "Yes/No" checkbox config | Add those two columns explicitly with proper checkbox column config in the data_editor | Robert | Checkboxes visible and editable on the Revenue Requests table |
| P1 – Day 2 | P1 | Request Type filter is missing "Payroll" and "Tax prep" values (only sees what is currently in the live CSV) | The data simply does not contain those request_types yet — they were requested during the 2025 migration but never generated | Add a generation script option or quick data patch (Scripts/generate_revenue_data.py already knows how); document as known gap until full Chart of Accounts mapping exists | Robert + Patty | Payroll and Tax prep appear as filter options when users request them |
| P1 – Day 2 | P1 | "Quick Bulk Status Update" dropdown still shows raw request_id instead of friendly business_name values | The multiselect is bound to `df['request_id']` instead of using the request-specific business_name lookup that already exists in the row | Change the label in the multiselect to "rid – business_name" or switch entirely to business_name + multi-row selection | Robert | Users can select by client name in bulk update |
| P2 | P2 | Edits in the Revenue Requests table have no undo; users worry about accidental data loss | Current save is irreversible write-back to the single CSV with no transaction log | Implement simple in-memory undo stack (last 5 states) + "Undo Last Save" button before writing to disk; later can be upgraded to full audit fields once on PostgreSQL | Robert | One-click recovery within the session after an edit mistake |
| P2 | P2 | "First column" in the Revenue Requests table shows no useful data (index or unnamed column) | pandas index leakage or the data_editor trying to render the implicit index | Explicitly hide the index (`hide_index=True`) + choose only the 11 real columns | Robert | Clean table with only meaningful columns |

**P0 items must be fixed and redeployed before any broader team access (Patty + Stef daily use).**

### 14.3 Structured Persistent Feedback Process (Core Component of Phase 2.5 & Beyond)

**Goal**: Every observation from Laura, Stef, Patty or Robert is captured in a durable, searchable, versioned format instead of Slack texts or memory.

**Mechanism (already implemented live in the app)**:

1. Any authenticated user opens the sidebar “📣 Submit Runtime Feedback” expander.
2. Required fields: Reported by (select), Category (select), Description (free text), Priority.
3. On submit, the row is **immediately appended** to `Data/feedback_log.csv` inside the running container (and therefore survives the session).
4. On next git pull / redeploy the same file is present with full history.
5. Robert (or designate) reviews the log at the start of every 1-week iteration, triages into P0/P1/P2, updates this Section 14, and marks rows “In Progress” / “Done”.

**CSV Schema** (header already present):
```
timestamp,reported_by,category,description,priority,status,version
```
- `status` values: Open / In Progress / Done / Deferred / Duplicate
- `version` = the app/git version string at the time of submission (helps trace regressions).

**Governance**: The log is treated as source-controlled data. It is **never** deleted. Historical rows are kept indefinitely for project memory and audit purposes (ties directly into the 7-year SLAM document retention policy).

**Manual seed (from first live session – May 23 2026)**:
The original 7 issues from `Project Runtime User Stories.txt` were transcribed into the same format and placed at the top of `feedback_log.csv` so the history is continuous.

### 14.4 How This Section Updates the Overall Roadmap

- Phase 2 (Infrastructure & first live deployment) is now considered **substantively complete** once P0 items are shipped.
- Phase 2.5 is the explicit “stabilize + learn” sprint before Phase 3 (full automation + PostgreSQL + Azure Files / Always On).
- All future user stories for bank statement automation, payroll runs, document management, etc. will be **derived from** entries that first appear in this living feedback log.
- This closes the gap between the original Blueprint promise of a “User Stories Backlog (Section 14)” and actual delivered working practice.

**End of Section 14 (v2.11)**.
