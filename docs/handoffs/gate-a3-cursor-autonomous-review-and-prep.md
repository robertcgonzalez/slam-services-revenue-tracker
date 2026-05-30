# Gate A3 — Cursor Autonomous Review & Preparation Handoff (Post Owner Smoke Execution)

**Date**: 2026-06 (current session)  
**From**: Grok (secondary)  
**To**: Cursor (primary / lead agent)  
**Single Focused Goal**: Perform every autonomous action possible for Gate A3 now that the owner has executed the live re-smoke on the production URL. Establish current production state via CLI and health checks, validate the maximum possible portion of the Pre-Smoke Checklist, prepare the Post-Smoke Scorecard scaffolding and runbook for immediate analysis once the owner pastes evidence, and keep the runbook as the single source of truth.

---

## MANDATORY PRE-WORK (Execute First — Log Everything)

1. Read in strict order:
   - `CONSTITUTION.md`
   - `README.md` (full Documentation Roles Matrix)
   - `docs/go-live-execution-runbook.md` (entire file — this is the SSOT for Gate A3 status)
   - All four files in `docs/gate-a3/`:
     - `Gate-A3-Orchestration-Launch-Directive.md`
     - `Gate-A3-Pre-Smoke-Checklist-and-Evidence-Template.md`
     - `Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`
     - `Gate-A3-Results-Intake-Prompt.md`
   - `QMS/README.md` and the active State Alignment process (`QMS/State-Alignment/process.md`)
   - `.cursor/rules/slam-services.mdc`

2. Run the **full mandatory git verification sequence** (even though we are not committing in this phase):
   ```powershell
   git status
   git diff --cached --stat
   git check-ignore -v . 2>$null | Select-String -Pattern "(Data/|\.csv|\.env|secrets|logs|\.zip|deploy-logs)" | Select-Object -First 30
   git ls-files --others --exclude-standard | Select-String -Pattern "(\.env|Data/.*\.csv|.*\.zip|deploy-logs)" 
   Write-Output "=== VERIFICATION SUMMARY (Gate A3 Cursor handoff) ==="
   ```
   Capture the complete output.

3. Confirm you understand the hard constraint: **You must never perform or simulate the live browser smoke** on the production URL with the real client PDFs. The owner (Robert) has already done the human-only execution.

---

## Current Known State (Authoritative)

- Owner has completed the live re-smoke using both required PDFs:
  - `Data/HCC 2026-04.pdf`
  - `Data/Auto_Body_Center_Jan_26_Statement.pdf`
- Owner has captured screenshots from the Bank Statements page and downloaded the resulting tables.
- Owner will paste key observations, table summaries, and Processing log excerpts when ready.
- The Pre-Smoke Checklist and Evidence Template in `docs/gate-a3/` are the exact instruments to use.
- The runbook `docs/go-live-execution-runbook.md` must remain the single source of truth. All status, verdicts, and Path A/B recommendations go there.

---

## Exact Actions Cursor Must Perform (Autonomous Phase)

### 1. Environment & Production State Validation (Do This Now)
Run these commands and record clean output:

```powershell
# Full health + Azure validation
.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure

# Current App Service configuration (redact secrets in any output you keep)
az webapp config show -g SLAM-Services-RG -n slam-services-revenue-tracker --query "{appCommandLine, alwaysOn, sku}"
az webapp config appsettings list -g SLAM-Services-RG -n slam-services-revenue-tracker | findstr /i "DI|DOCUMENT|POSTGRES|USE_POSTGRES|AZURE_DI"

# Latest deployment history
az webapp deployment list -g SLAM-Services-RG -n slam-services-revenue-tracker --query "[0:3].{id:id, status:status, time:receivedTime}" -o table

# Postgres reachability from the app (via health check or direct if possible)
python Scripts/health_check.py --full
```

### 2. Pre-Smoke Checklist Validation (Autonomous Portion)
Review and mark every item in `docs/gate-a3/Gate-A3-Pre-Smoke-Checklist-and-Evidence-Template.md` that can be validated without the live browser smoke. Explicitly note which items remain owner-only.

### 3. Prepare Analysis Scaffolding
- Load the Post-Smoke Scorecard scaffolding (`docs/gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`).
- Prepare a clean, ready-to-fill version (in your working memory or a scratch note) so that when the owner pastes the filled Evidence Template + logs, you can produce the verdict immediately.
- Identify the exact sections of the main runbook that will need updating after analysis (Gate A3 row, final production state table, new "Gate A3 Verdict" subsection, Handoff section).

### 4. Runbook Hygiene (Do This Phase)
- Add a concise entry to the runbook's Running log and/or Handoff section recording that this autonomous Cursor review phase was initiated after owner smoke execution.
- Do **not** yet fill in smoke results or verdicts.

### 5. Evidence Intake Preparation
Create (or clearly document) the minimal set of information you need from the owner when he pastes results, including:
- Which PDF was processed first / second
- Key numbers from the downloaded tables (register row counts, check/imaging leg crops detected, payee quality examples — redacted where necessary)
- Notable Processing log lines (cropper activation, page range behavior, errors)
- Deploy ID visible at time of smoke
- Whether rollback (`-DisableDI`) was tested during the session
- Any screenshots references (owner will describe; do not ask for actual image files)

---

## Success Criteria for This Cursor Run

- Full git verification executed and logged.
- All autonomous Pre-Smoke Checklist items validated with evidence.
- Current production state (health, DI settings, latest deploy) captured cleanly.
- Post-Smoke Scorecard scaffolding prepared and ready for immediate use.
- Runbook updated with this handoff and the autonomous actions taken.
- Clear, copy-paste-ready request to the owner for the exact evidence format needed to complete the Gate A3 verdict.
- No attempt to access or simulate the live production Bank Statements page with client PDFs.

---

## What You Must NOT Do in This Phase

- Do not ask the owner for full raw screenshots or unredacted tables containing real client financial data.
- Do not modify production (no deploys, no setting changes) unless explicitly authorized in a follow-up handoff.
- Do not update the Blueprint Change Log yet (that happens only after owner review of the final verdict).
- Do not claim any part of the live smoke execution.

---

## Handoff Back to Owner / Grok

When this phase is complete, return:
1. The full output of the git verification + health / Azure commands.
2. Your annotated Pre-Smoke Checklist (autonomous portion).
3. The prepared Post-Smoke analysis scaffolding.
4. Exact proposed updates to `docs/go-live-execution-runbook.md`.
5. A crisp, minimal request to the owner for the smoke evidence (what to paste and in what format).

This keeps the dual-agent loop tight and respects the project’s thin-handoff, anti-bloat, and documentation-roles discipline.

---

**This handoff file is the authoritative directive for the current autonomous Cursor phase of Gate A3.**  
Reference it from the main runbook once executed.