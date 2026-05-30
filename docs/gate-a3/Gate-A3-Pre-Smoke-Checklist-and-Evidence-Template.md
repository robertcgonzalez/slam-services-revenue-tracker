# Gate A3 — Pre-Smoke Checklist + Evidence / Report Template

**Live URL**: https://slam-services-revenue-tracker.azurewebsites.net/
**PDFs**:
- `Data/HCC 2026-04.pdf` (Hernandez Custom Concrete)
- `Data/Auto_Body_Center_Jan_26_Statement.pdf` (Auto Body Center — hard Traditions case)

**Executor**: Human (Robert) only for browser upload/process. Evidence collection is autonomous via `Collect-GateA3Evidence.ps1`.

---

## Pre-Smoke Checklist (Run Before Starting the Smoke)

### Environment & App State
- [ ] App Service healthy (`Check-AppHealth.ps1 -Full -CheckAzure` or portal)
- [ ] Sidebar shows **Data Source Status → PostgreSQL connected** with client count ≥ 98
- [ ] Bank Statements page loads without "Critical: CSV files — not found" or similar
- [ ] DI pipeline visibly configured (no persistent "Azure OCR is not configured" blocker)
- [ ] Latest deploy id visible and matches expected P0 imaging code-only zip
- [ ] Rollback command confirmed working: `.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI`

### DI Configuration Spot-Check (optional but recommended)
- [ ] `AZURE_DI_ENDPOINT`, `AZURE_DI_MODEL`, `AZURE_DI_CHECK_MODEL`, `SLAM_IMAGING_FIRST_PAGE`/`LAST_PAGE` visible in App Settings
- [ ] Imaging page range clamp logic is in the deployed code (not the old blind 5-9 range)

### Local Prep
- [ ] Both PDFs present locally under `Data/`
- [ ] `Invoke-DataLayerGoLive.ps1 -WhatIf` or health check passes locally against Postgres
- [ ] Git status clean; no accidental client data staged
- [ ] `Collect-GateA3Evidence.ps1` available; no manual screenshot/log/CSV capture needed

**Mark all items green before proceeding to smoke.**

---

## Evidence / Report Template (Fill During or Immediately After Smoke)

**Date/Time (UTC)**: ______________________________
**Executor**: Robert
**App Service deploy id at time of smoke**: ______________________________
**DI settings active?** (yes / no — note if `-DisableDI` was used): ______________________________

### PDF 1 — HCC 2026-04.pdf (Hernandez Custom Concrete)

| Item | Result / Observation |
|------|----------------------|
| Register / tabular rows extracted | |
| Check/imaging leg — checks detected & cropped? | Yes / Partial / No |
| Check/imaging leg — payee quality on detected checks | (list example payees or "N/A") |
| Processing log — cropper activated? (`opencv` / `check_cropper`) | |
| Processing log — page range error from `prebuilt-check.us`? | Yes (quote) / No |
| Processing log — other critical errors/warnings | |
| Uncategorized volume or large buckets | |
| Payee rules applied (how many rows helped) | |
| Overall time / retries observed | |
| Screenshots taken (reference only, do not paste images here) | |

**Narrative notes for this PDF**:

_______________________________________________________________________________

### PDF 2 — Auto_Body_Center_Jan_26_Statement.pdf (Hard Traditions case)

| Item | Result / Observation |
|------|----------------------|
| Register / tabular rows extracted (best run) | |
| Register consistency across 2–3 runs on same PDF | |
| Check/imaging leg — checks detected & cropped? | Yes / Partial / No |
| Check/imaging leg — payee quality on detected checks | (list examples or "N/A") |
| Processing log — cropper activated? | |
| Processing log — page range clamp working? | |
| Payee rules applied (how many rows helped) | |
| Comparison to historical spike baseline (~92 txns, ~56 crops) | |
| Screenshots taken | |

**Narrative notes for this PDF**:

_______________________________________________________________________________

### Cross-Cutting Observations

- Sidebar / Bank Statements page behavior before processing
- Any "Azure OCR is not configured" or DI reachability messages?
- App responsiveness / cold start during smoke
- Rollback test performed? (`-DisableDI` + re-smoke of one PDF)
- Any other anomalies (inconsistent results, UI state issues, etc.)

---

## Immediate Post-Smoke Actions (Human)

1. Paste the completed template above back into the chat / runbook discussion.
2. Include key Processing log excerpts (focus on cropper, check analyzer, page range, errors).
3. Note the exact deploy id and whether rollback was tested.
4. Do **not** commit any client data or screenshots containing real numbers/payees.

---

## Cursor Post-Smoke Analysis (After Human Pastes Results)

Cursor will receive the filled template + logs and must produce:

1. Completed **Gate A3 Scorecard** (see separate scaffolding).
2. Clear verdict: "Check/imaging leg production-ready" / "Needs specific fixes" / "Register-only viable for now".
3. Updated runbook sections (A3 row, final state table, Path A/B decision).
4. Proposed commit message + scope (only if PASS or conditional PASS).
5. Recommendation on Laura pilot timing + any required hardening.

---

**This template + checklist lives in `docs/gate-a3/` and is referenced from the main runbook.**

Update the runbook with a pointer once the checklist is integrated.