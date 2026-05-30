# Azure DI Bank Statement Go-Live — Ready-to-Paste Cursor Execution Prompt + Permanent Runbook

**Purpose**: This document provides (1) a complete, high-signal, copy-paste-ready prompt for Cursor (the primary / lead agent) to **thoroughly execute the full 2026 Azure Document Intelligence Bank Statement production go-live**, and (2) the specification for the permanent execution runbook and artifacts Cursor must produce.

This prompt turns the exact command package in `docs/DI-Go-Live-Commands.md` into an autonomous, gated, fully-audited execution run by Cursor, with mandatory owner confirmations at every high-impact step, complete verification at each stage, zero-risk rollback posture, pilot preparation, and handoff-grade documentation closure.

**Owner context (June 2026)**: The DI two-leg pipeline (`prebuilt-bankStatement.us` + geometric cropper v5 + `prebuilt-check.us`) design, setter script, health enhancements, and schema capture (`db/schema.sql`) are complete. The go-live commands exist. Cursor (primary) now owns thorough execution, validation, and production hardening. The rename prompt (`docs/azure-app-service-rename-prompt.md`) is available as a follow-on hardening step if the owner elects it during or after this session.

**When to use**: When the owner is ready for the live production cut-over of the DI path (after any final review of the setter script, health scripts, and DI implementation in `App/`).

---

## The Prompt (copy everything below this line into Cursor)

```
You are Cursor, the **primary / lead** AI coding agent for the SLAM Services project (per CONSTITUTION.md and .cursor/rules/slam-services.mdc). Grok is secondary.

**Immediate mandatory first actions**:
1. Read `CONSTITUTION.md` (Layer 0 — immutable).
2. Read the full latest `SLAM Services - Digital Transformation Blueprint.md` (especially the v2.44.19 DI go-live Change Log entry and current status section).
3. Read `README.md` (Documentation Roles Matrix and current Post DI Go-Live status).
4. Read `docs/DI-Go-Live-Commands.md` in full (this is the exact command source of truth).
5. Read `docs/deployment.md` (Production Bank Statement DI Go-Live section + health recipes).
6. Read `Scripts/PowerShell/Set-AzureBankStatementDIAppSettings.ps1` completely (understand WhatIf, DisableDI, exact settings, warnings, and next-steps output).
7. Read `Scripts/PowerShell/Check-AppHealth.ps1`, `Scripts/PowerShell/Deploy-ToAzure.ps1`, `Scripts/PowerShell/Build-AzureDeployZip.ps1`, and `Scripts/health_check.py` (focus on -Full -CheckAzure and DI probes).
8. Read `db/schema.sql` and the "Current Implemented" section of `docs/data-model.md`.
9. Confirm the two primary test PDFs exist: `Data/Auto_Body_Center_Jan_26_Statement.pdf` and `Data/Altitude_Base_Coatings_Jan_26_Statement.pdf` (or HCC equivalent).

**Mission**: Thoroughly execute the production go-live of the Azure Document Intelligence two-leg bank statement pipeline on the live F1 App Service (`slam-services-revenue-tracker`). Drive every step to completion with full auditability, owner gates, verification, and zero daily-driver risk. Laura’s confidence and reversible changes are non-negotiable.

**Non-negotiables you must obey at all times**:
- Canonical git verification (`.\Scripts\PowerShell\Invoke-GitVerification.ps1`) **before every add/commit/push**. The script is the single-source implementation (Prime Directive aligned). Surface its full output. Only proceed on exit code 0 (CLEAN).
- Owner explicit confirmation required before: (a) DI SKU upgrade to S0, (b) real (non-WhatIf) run of the setter script, (c) any production deploy, (d) any traffic-affecting change.
- Always keep the rollback command (`Set-... -DisableDI` + optional redeploy) one step away and document it.
- Never delete or overwrite production data. CSV fallback and Postgres remain the ultimate source of truth.
- Respect Documentation Roles Matrix: update Blueprint Change Log + version for the execution record; enhance existing operational docs only by reference (do not duplicate command lists into new files unless creating the designated permanent runbook); the runbook you produce is the authoritative execution transcript.
- Anti-bloat: reuse every existing script and doc. Do not create new wrapper scripts unless the owner explicitly approves during the session.
- If at any point the owner says "pause", "hold", or "rollback", you stop immediately and document the state.

**Execution phases (execute in order; gate on owner at each major step)**:

**Phase 0 — Pre-flight & Current State Capture (read-only)**
- Run `az account show` and confirm correct subscription + RBAC on SLAM-Services-RG.
- Capture current state of `slam-bank-statements` (SKU, endpoint).
- Capture current App Settings on the Web App that relate to AZURE_DI_*, SLAM_IMAGING_*, and OCR fallbacks. Save a redacted summary.
- Run `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` (or python equivalent) and capture baseline.
- Run a quick local schema validation if Postgres env is available.
- Produce a clean "Pre-Go-Live Baseline" table (DI SKU, key App Settings presence/absence, health summary, last deploy).
- Explicitly state: "Pre-flight complete. Ready for owner decision on S0 upgrade."

**Phase 1 — DI Resource Upgrade to S0 (owner gate)**
- Show the exact `az cognitiveservices account update` command from DI-Go-Live-Commands.md.
- Wait for owner "proceed" or "use Portal instead".
- Execute (or confirm Portal result).
- Re-capture SKU and confirm S0.
- Update your running log.

**Phase 2 — Apply Production DI App Settings (dry-run then real, owner gate)**
- First: `.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -WhatIf` (from repo root). Show full intended settings (redact key).
- Confirm with owner.
- Real run: `.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1`
- Immediately capture the post-set App Settings via az (the exact query from DI-Go-Live-Commands.md).
- Show the rollback command that now exists.
- State: "DI settings live on App Service. Code redeploy required next."

**Phase 3 — Code Deploy to Production**
- Use the modern safe path: `Build-AzureDeployZip.ps1` then `Deploy-ToAzure.ps1` (or confirm GitHub Action if owner prefers).
- After deploy, run the full `Check-AppHealth.ps1 -Full -CheckAzure` against the live URL.
- Capture health output (DI status must now report configured + reachable).
- Confirm no regression in sidebar status, login, basic Revenue Requests.

**Phase 4 — Thorough Robert Validation Smoke (on the live URL)**
- Instruct the owner (or document the exact manual steps) to perform the Robert smoke using the known-good scanned PDFs:
  1. Bank Statements page → upload `Data/Auto_Body_Center_Jan_26_Statement.pdf` (and the Altitude/HCC one).
  2. Click Process Statement.
  3. Verify in the live UI:
     - Azure DI banner / status appears (not "not configured").
     - Reasonable transaction count and totals (cross-check against known baselines in prior exports / parser runs).
     - Reconciliation banner is green.
     - Crops appear for imaging pages (pages 5-9 per the setter defaults).
     - "Mark as Received" successfully writes `bank_statement_received=true` (verify in Revenue Requests table or direct DB query).
  - Run any additional local or az log queries you need for confidence (e.g., App Service logs for the DI calls).
- Capture screenshots or exact success output where possible.
- If any failure: immediately offer the one-command rollback and do not proceed.

**Phase 5 — Schema & Data Layer Confidence**
- Run the schema validation snippets from DI-Go-Live-Commands.md (local + against live via health_check or direct).
- Confirm `db/schema.sql` matches the live tables that Bank Statements writes to.
- Confirm the two boolean flags (`bank_statement_received`, `sales_report_received`) are being written by the DI path.

**Phase 6 — Pilot Session Preparation & Gate**
- Produce a concise "Laura + Full Team Pilot Session" one-pager (can be a new small section in the runbook or a short dedicated file if it fits roles):
  - Exact 45-60 min agenda.
  - Side-by-side comparison (old Grok paste path vs new DI path) on one clean PDF and one hard scanned PDF.
  - Specific questions to ask: payee quality improvement, time saved, any friction, "Ready for daily driver use across the whole team?"
- If owner confirms "yes" during this Cursor session: record the decision and leave DI settings in place.
- If owner wants to observe 7-14 days first: document the monitoring plan (cost alerts, daily driver feedback loop via existing Section 14 process).

**Phase 7 — Optional Hardening — App Service Rename (owner decision)**
- Explicitly offer the rename as the natural next production-hardening step (reference the complete ready-to-paste prompt and runbook in `docs/azure-app-service-rename-prompt.md`).
- If owner says "yes, proceed with rename now", immediately load that prompt's content and begin executing it (you already have full authority).
- If owner defers: simply record the decision and the exact pointer.

**Phase 8 — Documentation & Handoff Closure (mandatory)**
- Create / update the permanent artifact: `docs/go-live-execution-runbook.md` (see exact spec below).
- Add a concise new entry to the Blueprint Change Log (bump to next patch, e.g. v2.44.20) titled something like "v2.44.20: Thorough DI Go-Live execution by Cursor — full command sequence driven to completion, health validation passed, pilot prep artifacts delivered, rollback posture confirmed."
- Update the "Current Status (June 2026 — Post DI Go-Live)" section in README.md only with factual post-execution reality (reference the new runbook).
- Make minimal, role-respecting updates to `docs/DI-Go-Live-Commands.md` and `docs/deployment.md` only to cross-reference the new execution runbook and Cursor prompt file.
- Ensure every future engineer (Patty, Robert, etc.) can read the runbook + existing command file and understand exactly what happened and how to repeat/rollback.
- Final git verification + commit/push of all changes (Blueprint, README, new runbook, any tiny doc pointers).

**Rollback posture throughout**:
- Always surface the current one-command rollback.
- Test the rollback path at least once (apply -DisableDI, redeploy if needed, confirm UI reverts cleanly, then re-enable).
- Document the rollback test in the runbook.

**Final success criteria (you must achieve all before declaring done)**:
- DI pipeline is the primary engine on the live App Service.
- Full health + two hard PDF smokes pass on the live URL with DI banner and correct crops + DB write-back.
- Rollback path has been exercised and documented.
- Owner has an explicit gate record for the team pilot ("ready for daily driver").
- `docs/go-live-execution-runbook.md` exists and is the authoritative transcript.
- Blueprint + README reflect reality with no bloat.
- Zero production incidents or Laura friction introduced.

**Output discipline**:
- After every major phase, give a crisp status block: "Phase X complete — findings / artifacts / decision required."
- When truly blocked on owner input, say exactly what signal you need next.
- Never proceed past a gate without the owner's explicit text confirmation in the thread.

Begin with Phase 0 pre-flight. Surface the full baseline. Then wait for the owner's first go / no-go decision.
```

---

## Permanent Go-Live Execution Runbook (what Cursor must produce)

After successful completion of the prompt above, the following file must exist and become the authoritative execution record:

**`docs/go-live-execution-runbook.md`**

It must contain (at minimum):

- Execution date(s) and Cursor session context (Grok secondary review reference if any).
- Pre-flight baseline table (exact DI SKU, App Settings snapshot redacted, health output summary, last known good deploy).
- Exact commands executed in each phase, with key outputs (keys redacted to length only, full success/failure text for non-secrets).
- Owner confirmation log (who said what at each gate).
- Post-deploy health output (full or redacted critical sections).
- Validation smoke results: for each test PDF, transaction counts/totals, DI banner presence, crop count, Mark-as-Received DB write confirmation, any anomalies noted.
- Rollback test record (when -DisableDI was used, what the UI showed, re-enable results).
- Pilot session one-pager (agenda, comparison PDFs used, decision recorded).
- If rename was executed: link to the rename runbook + summary of timing relative to DI enablement.
- Final production state summary (URL, DI models active, schema baseline, monitoring hooks in place).
- Exact rollback commands that remain valid forever.
- Handoff note: "This runbook + DI-Go-Live-Commands.md + deployment.md + db/schema.sql together allow Patty or Robert to understand the 2026 go-live and operate/rollback the DI path."
- Link to the Blueprint Change Log entry that records the Cursor-driven execution.

This runbook, together with the setter script, health scripts, `db/schema.sql`, and the rename runbook (if used), represents the complete "production hardened" state after the 2026 DI Bank Statement go-live.

---

**End of prompt + runbook package**

**Usage note for the owner**: Paste the entire block inside the long ``` above directly into a fresh Cursor chat (Composer or Agent). Cursor will drive the work with the exact autonomy + gates defined in the Constitution and this project's standing orders. You retain final say at every material step.

After Cursor finishes, perform an independent review (Grok or human) against the produced `docs/go-live-execution-runbook.md` and the live application before declaring the go-live "complete for daily driver use."

This file lives in `docs/` alongside `DI-Go-Live-Commands.md` and `deployment.md` per the Documentation Roles Matrix.
