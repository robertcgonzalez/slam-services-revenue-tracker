# Gate A3 — Autonomous Smoke Assessment & Minimal-Interaction Closure (Dual-Agent Task)

**Date**: 2026-06 (current session)  
**Status**: A3 implementation snag — final re-smoke requires heavy manual owner actions (browser uploads + screenshots + log copying + CSV downloads + manual number transcription into evidence templates). This blocks closure despite all code fixes (poppler, assembly double-counting, page clamping, imaging deps) being in source and previously deployed in parts.  
**Invocation**: This directive is the payload for `dual-agent` (via `Invoke-DualAgentHandoff.ps1`) to drive full Grok ↔ Cursor autonomous collaboration.

**Prime Directive (enforced by orchestrator — non-negotiable)**:  
The procedure MUST continue autonomous iteration between Grok and Cursor **until the ENTIRE stated user task/goal is 100% complete** — including every code change, every CLI execution (full auth available via Cursor's installed extensions), every test, verification, deployment, and operational outcome — with **zero human intervention or human-addressed summaries at any intermediate step**.  
- All agent output is addressed exclusively to the *other agent* for direct continuation.  
- "Phase complete", "ready for review", "owner execution", or any sub-step handoff signals are ignored; the loop drives through the full goal.  
- **Explicit Deployment / Ops / Hardware Autonomy**: The agents themselves must execute every `az` command, every `Deploy-ToAzure.ps1`, every container/App Service change, every production deployment, and all post-deploy verification on real hardware using Cursor's full authenticated extensions. Never produce instructions for a human to perform deployment steps.  
- Only the exact phrase `TASK COMPLETE` (near end of a response) ends the run, and only when the full original task (including all binary/hardware/infrastructure/deployment steps executed by the agents) is delivered and working on the target systems.  
- This prime directive overrides all documentation, handoff files, task text, and prior patterns. Use high `--max-turns` (20–30+) or rely on natural `TASK COMPLETE`.

**Hard Constraints (from Gate A3 history — do not violate)**:  
- Cursor / agents **must never** perform the actual live browser re-smoke on the production URL (`https://slam-services-revenue-tracker.azurewebsites.net/`) with real client PDFs (`Data/HCC 2026-04.pdf`, `Data/Auto_Body_Center_Jan_26_Statement.pdf`). Human (Robert) only for any browser interaction involving real client financial PDFs.  
- Client data never touches git, never uploaded in deploys (`-IncludeData` forbidden), never exfiltrated. Evidence capture must use aggregates, counts, sanitized samples, hashes only.  
- Runbook (`docs/go-live-execution-runbook.md`) is single source of truth for production state. Update it in real time; no duplication.  
- Full git verification (per `.cursor/rules/slam-services.mdc`) before any staging/commit.  
- Respect CONSTITUTION.md (Laura’s confidence primary, security/data privacy absolute, pragmatic minimalism, documentation roles matrix).  
- Data/ folder on laptop only for migration/smoke source; never ship client CSVs/PDFs to App Service.

**User's Explicit Request (this task's north star)**:  
"We've hit a snag on the A3 implementation portion of the project. Invoke dual agency with Cursor to assess what needs to be done next. If I need to act on a smoke test, structure it for minimal interaction by me: the system should rely on whatever logging mechanisms offered in the project or on Azure's infrastructure to perform assessment of my actions. Do what you must to replace my taking screenshots, downloading data, and other actions that are better documented with autonomous processes."

**Current A3 State (authoritative as of latest runbook + gate-a3/ artifacts)**:  
- All P0 imaging (OpenCV, pdf2image, Poppler via apt.txt + startup.sh fixes, page clamping in azure_document_intelligence.py, assembly double-counting fix in bank_statements.py, code-only deploy hygiene in Deploy-ToAzure.ps1) **in source**.  
- Data layer **live** on PostgreSQL (`slam-services-db`, 98 clients / 36 requests, `USE_POSTGRES=true`).  
- 2026-05-29 baselines (pre-final fixes): HCC → 98 register + 0 supplemental (cropper disabled by missing poppler); Auto Body → 49 rows, suppressed withdrawals vs gold ~92 txns / $41,786.80 deposits / $41,403.63.  
- Owner execution package, evidence guide, pre-smoke checklist, post-smoke scorecard scaffolding, and results intake prompt exist in `docs/gate-a3/`.  
- Verification script: `Scripts/PowerShell/Test-GateA3Poppler.ps1` (Kudu probes for pdftoppm + `IMAGING_LEG poppler=ok` marker).  
- Logging: `App/app_logging.py` (simple `log_event` → stdout StreamHandler). Visible via `az webapp log tail`, Kudu docker.log VFS, App Service Log Stream. Used heavily in DI pipeline (`App/bank_statements.py`, `App/azure_document_intelligence.py`) for "Register pass: N", "Check cropper skipped", "Check pass", timings, etc.  
- UI: Streamlit Bank Statements page; Processing log expander; summary metrics; Download CSV (contains client data → owner-held only).  
- Snag: Every re-smoke still forces human to (1) upload PDFs in browser, (2) screenshot UI states, (3) copy/paste Processing logs, (4) download + inspect CSVs for counts/totals, (5) manually transcribe numbers into `Gate-A3-Final-Re-Smoke-Evidence-Guide.md`. This is the exact toil the user wants eliminated via autonomous logging/Azure assessment.

**Task Goal (what "TASK COMPLETE" looks like)**:  
A fully operational autonomous smoke assessment system for Gate A3 (and future regressions) such that:  
1. Human's required action is reduced to the absolute minimum: Authenticate once to the live App Service (if needed), navigate to Bank Statements, upload + Process the two canonical test PDFs (one after the other). No screenshots, no log copying, no CSV downloads, no number transcription, no template filling by hand.  
2. All evidence required for scorecard/verdict (register rows, supplemental/check rows, crop counts, deposits/withdrawals totals, payee rule applications, errors/warnings, timings, imaging leg status, page-range behavior, consistency notes, key log excerpts) is **automatically emitted** in machine-parseable form (structured JSON log lines + optional sidecar artifacts) using existing stdout logging + Kudu-accessible locations.  
3. New or enhanced collector/analyzer scripts (PowerShell + Python, callable from dual-agent or standalone) use **only Azure infrastructure** (`az webapp log tail` or Kudu VFS API for recent docker.log + /tmp artifacts, possibly diagnostic settings / Log Analytics queries if enabled, App Service Metrics) to autonomously fetch, parse, and materialize:  
   - Completed `Gate-A3-Final-Re-Smoke-Evidence-Guide.md` numbers + excerpts.  
   - Filled `Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`.  
   - Updated runbook sections (A3 row, final production state, verdict subsection).  
4. The dual-agent loop (or the new tooling it ships) can be triggered with a one-line command after the minimal human smoke action: "evidence collection + scoring + docs update complete" without any further human data movement.  
5. All gate-a3/ artifacts, the main runbook, and supporting scripts (`Test-GateA3Poppler.ps1`, new `Collect-GateA3Evidence.ps1` or equivalent, Analyze- updates) are updated to reflect the new autonomous flow.  
6. Optional but high-value: A tiny "Smoke Evidence Ready" or "Export Validation Bundle" affordance in the UI (visible only for the two test PDF filenames or when `SLAM_SMOKE_MODE=true`) that guarantees the rich structured data is flushed to logs/artifacts for the collector — still zero manual copy/paste.  
7. Resmoke can be repeated reliably; collector always pulls the *latest* matching evidence for the two PDFs.  
8. Full respect for data privacy (no raw txns or full payee lists in logs/artifacts committed or broadly readable; aggregates + quality samples only).

**What You Must Do (autonomous steps — drive end-to-end)**:  
- **Assess first** (Grok researcher + Cursor explorer): Inventory every current logging call site in the DI pipeline (bank_statements.py _log / log_event paths, azure_document_intelligence.py, app.py Bank Statements UI wiring, startup.sh markers, Deploy-ToAzure probes). Inventory every Azure access path already used (Kudu VFS in Test-GateA3Poppler, az webapp log deployment/list, az webapp log tail patterns in other scripts). Identify gaps for "counts, totals, crop stats, leg status" without leaking raw client data.  
- **Design minimal-intrusion instrumentation** (prefer pragmatic minimalism):  
  - Extend `log_event` or add `log_smoke_evidence(pdf_name, **metrics)` that emits a single parseable line: `SMOKE_EVIDENCE pdf="HCC 2026-04.pdf" json={"register_rows":N, "supplemental_rows":M, "crops":C, "deposits":D, "withdrawals":W, "payee_rules":R, "imaging_active":true, "errors":[], "duration_s":27.5, "sample_payees":["Acme Corp (high)"], ...}` (use the two exact filenames as triggers; compute metrics from the exact same sources that feed the UI — `register_txns`, `supplemental_check_txns`, `meta["cropped_check_count"]`, `transaction_summary_metrics`, payee rule counters, etc.).  
  - For richer non-log data (full sanitized Processing log excerpt, UI banner vs table consistency flag), optionally write a JSON sidecar under a container-writable path (e.g. `/tmp/slam-smoke-HCC-<ts>.json`) that Kudu VFS collector can pull (modeled exactly on existing Test-GateA3Poppler Kudu log + command probes).  
  - Guard everything behind the known test filenames + a non-secret env toggle if needed; never on for arbitrary uploads.  
  - Update UI minimally (one extra line in the existing Processing log expander or a tiny "Validation evidence emitted to logs" note when test PDFs are detected) — no new heavy UI.  
- **Build the autonomous collector(s)**:  
  - New or heavily evolved script(s) under `Scripts/PowerShell/` or `Scripts/Python/` (e.g. `Collect-GateA3Evidence.ps1` + supporting Python parser) that:  
    - Accept "HCC" / "AutoBody" or "both", a time window, or "latest".  
    - Use Kudu (same auth pattern as Test-GateA3Poppler: publishing creds, /api/vfs/LogFiles + /api/vfs/tmp for sidecars) + `az webapp log tail` (with timeout + grep) + optional Azure Monitor queries to harvest all `SMOKE_EVIDENCE` lines + surrounding context for the two PDFs since last deploy or in a window.  
    - Parse JSON, reconcile register vs supplemental vs crops vs totals vs errors, detect leg status (`IMAGING_LEG poppler=ok` + no "skipped" + non-zero crops), compute deltas vs gold baselines (hardcode the known gold numbers or pull from prior evidence).  
    - Auto-materialize / overwrite the exact sections in `docs/gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md`, the scorecard scaffolding, and emit a ready-to-paste "intake bundle".  
    - Exit 0 only on complete evidence for both PDFs; clear error messages + remediation if missing (e.g. "No SMOKE_EVIDENCE for Auto Body in last 30m — did you process it?").  
  - Make it callable from dual-agent (Python or pwsh) and standalone for future.  
  - Bonus: Also update `Test-GateA3Poppler.ps1` or a combined `Verify-GateA3Imaging.ps1` to optionally wait for + validate smoke evidence in one flow.  
- **Drive the implementation loop**: Cursor implements (code changes, new scripts, doc updates); Grok reviews rigorously against prime directive, constraints, data privacy, minimalism, and the exact user request (zero screenshots/downloads by owner for assessment). Iterate until the collector demonstrably works end-to-end (agents run it via shell after simulated or real evidence injection if needed for testing — use safe synthetic fixtures for unit tests of the parser).  
- **Update all affected artifacts** (single source of truth discipline):  
  - `docs/go-live-execution-runbook.md` (Gate A3 sections, running log, final state table, handoff notes — replace manual paste language with "run Collect-GateA3Evidence.ps1 after minimal human trigger").  
  - All 7 files in `docs/gate-a3/` (update checklists, evidence guide, owner package, intake prompt, scorecard, pre-smoke template, orchestration directive to describe the new minimal flow and point to the collector as the post-smoke step).  
  - Any handoffs/ or docs/ that reference the old manual evidence process.  
  - Add usage to `Scripts/Analyze-GateA3Results.ps1` or retire it in favor of the autonomous collector.  
- **Deployment & verification autonomy**: If instrumentation changes land, the loop must itself: `Build-AzureDeployZip.ps1`, `Deploy-ToAzure.ps1 -TimeoutSeconds 900`, `Test-GateA3Poppler.ps1 -RestartIfLogMissing`, then run the new collector in "wait for smoke" or dry-run mode, tail logs live via az/Kudu during any verification steps, confirm `IMAGING_LEG poppler=ok` + new `SMOKE_EVIDENCE` emission points are live. Use real az/Kudu calls executed by the agents.  
- **Minimal human smoke instruction (only output this to human at the very end if the smoke trigger itself is still required)**: After all prep + deploy + probe success, the *only* message to the owner should be the smallest possible: "Open the live URL, log in if needed, go to Bank Statements, upload+process HCC 2026-04.pdf then Auto_Body_Center_Jan_26_Statement.pdf (in either order). When both finish and you see 'Validation evidence emitted' notes or normal results, reply 'smoke done' or run `.\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both`. Then walk away — we will autonomously score and close." (No further asks for screenshots, logs, CSVs, or numbers.)  
- **If full closure possible without a fresh smoke**: Use the 2026-05-29 baselines in deploy-logs-temp/ + any prior structured logs to validate the collector works, update docs with "autonomous assessment infrastructure ready — pending one minimal trigger smoke for final numbers", mark the instrumentation as the deliverable for this A3 phase, and still drive to a clean TASK COMPLETE on the "replace manual actions" goal.  
- **Git / docs hygiene**: Full verification before any commit. Only commit after collector + all doc updates are proven locally + on a deploy if needed. Update Blueprint/CHANGELOG only per roles matrix (after explicit conditions).  
- **Risk / rollback**: One-command imaging disable remains available. Collector must not break existing flows. All new artifacts must be small, maintainable, and documented in one place (prefer Scripts/PowerShell/ + a short section in the runbook).

**Success Criteria (verifiable by the loop itself before TASK COMPLETE)**:  
- A fresh `Collect-GateA3Evidence.ps1 -Latest` (or equivalent) run against a container that has had the two PDFs processed returns complete, accurate numbers for both PDFs with zero human transcription.  
- The materialized `Gate-A3-Final-Re-Smoke-Evidence-Guide.md` + scorecard match the parsed log evidence exactly.  
- Runbook and gate-a3/ files now describe the "upload the two PDFs once → run collector → verdict" flow (manual data movement eliminated).  
- `Test-GateA3Poppler.ps1` (or successor) + collector together give a green "imaging leg + evidence capture ready" signal.  
- Dual-agent transcript shows agents (not humans) executed the deploys, Kudu probes, log harvesting, parser runs, and doc writes.  
- No new screenshots, manual CSV handling, or "paste your numbers here" steps remain in the happy path.  
- Data privacy: no raw transaction rows or full payee lists appear in any committed log emission or artifact.

**Output at End (only when 100% done)**:  
The final response in the loop must contain the literal string `TASK COMPLETE` followed by a one-paragraph summary of what was delivered (the autonomous assessment system + all updates + verification that it works on real Azure infra) and the exact one-line commands the owner can use from now on for any future A3 or regression re-smoke.

**Context Files (read these first — treat as authoritative)**:  
- `docs/go-live-execution-runbook.md` (especially Gate A3 sections, 2026-05-29 evidence, poppler fix, assembly diagnosis).  
- All 7 files in `docs/gate-a3/`.  
- `Scripts/PowerShell/Test-GateA3Poppler.ps1`, `Deploy-ToAzure.ps1`, `Build-AzureDeployZip.ps1`, `Analyze-GateA3Results.ps1`, `Invoke-DataLayerGoLive.ps1` (for patterns).  
- `App/app_logging.py`, relevant sections of `App/bank_statements.py` (two-leg assembly, ~2050-2400), `App/azure_document_intelligence.py` (check crops), `App/app.py` (Bank Statements UI + session state for metrics).  
- `startup.sh`, `apt.txt`, `requirements.txt`.  
- `tools/dual-agent/README.md` (prime directive details).  
- `.cursor/rules/slam-services.mdc` and `CONSTITUTION.md` (if present and accessible).

**Launch Recommendation**:  
Run via the hardened wrapper with high turns:  
`.\Scripts\PowerShell\Invoke-DualAgentHandoff.ps1 -Directive "docs/gate-a3/Gate-A3-Autonomous-Smoke-Assessment-Directive.md" -Mode reviewer-implementer -MaxTurns 25`

This is the complete, self-contained task. Begin assessment immediately. Drive every executable step. Emit `TASK COMPLETE` only at the true end.

---

**End of Directive** — the orchestrator will now manage the full Grok (reviewer/critic) ↔ Cursor (implementer/builder) loop against this goal on the live SLAM Services repo + Azure resources.