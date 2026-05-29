# Gate A3 Live Orchestration — Grok CLI Launch Directive

**Purpose**: Single, complete directive that can be submitted via `grok -p` (or any Grok interface) to initiate the final pre-smoke preparation and post-smoke analysis for the SLAM Services production go-live.

**Target**: Cursor (primary agent per CONSTITUTION.md and `.cursor/rules/slam-services.mdc`) must drive execution with maximum autonomy within the constraints below.

---

## Authoritative Current State (as of this launch)

- B2 upgrade: **Complete**
- All P0 imaging dependencies and code changes: **Deployed** (OpenCV, pdf2image, Poppler via apt.txt, page clamping, deploy script fixes, code-only zip strategy)
- Data layer: **Complete** via `Invoke-DataLayerGoLive.ps1`. Production is now running on B2 with PostgreSQL (`slam-services-db` in centralus). 98 clients / 36 requests migrated. `USE_POSTGRES=true` active. App Service healthy.
- `Invoke-DataLayerGoLive.ps1` (end-to-end orchestrator) and fallback ACI path: **Built and executed**
- Runbook (`docs/go-live-execution-runbook.md`): Updated through data layer cut-over.
- **Only remaining hard gate**: Gate A3 — live Robert re-smoke on production URL with the two real PDFs:
  - `Data/HCC 2026-04.pdf` (Hernandez Custom Concrete)
  - `Data/Auto_Body_Center_Jan_26_Statement.pdf` (Auto Body Center — hard Traditions case)

Previous Phase 4 smoke (pre-P0 fixes) showed the check/imaging leg as the primary failure. All identified P0 root causes (missing OpenCV, page-range clamping, deploy hygiene) have since been addressed and deployed.

---

## Hard Constraints (Non-Negotiable)

1. **Single hard limit**: Cursor **must never** perform the actual live browser re-smoke on the production URL with real client PDFs. No browser control, no direct interaction with live production using client data. The human (Robert) will execute the smoke and paste results.
2. Runbook (`docs/go-live-execution-runbook.md`) is the **single source of truth**. All status, checklists, and verdicts live there. No duplication in Blueprint or README until after successful Gate A3.
3. Full git verification (per `.cursor/rules/slam-services.mdc`) before any staging or committing.
4. `apply docs` on Blueprint/README is **deferred** until after Gate A3 PASS + explicit human approval.
5. Client data never touches the App Service or git.
6. Follow CONSTITUTION.md (Laura’s confidence primary, anti-bloat, documentation roles matrix, pragmatic minimalism) and `.cursor/rules/slam-services.mdc` (Cursor as primary/lead, git verification, environment inviolability).

---

## Mandate — Execute Immediately

Upon receipt of this directive (whether via direct Grok CLI submission or human handoff), Cursor shall:

- Treat the "Current State" section above as authoritative (override outdated sections in the existing runbook).
- Immediately begin full autonomous preparation for Gate A3 within the allowed scope.
- Update the runbook in real time as the living artifact.

### Required Deliverables (produce in this or immediate follow-up turns)

1. **Gate A3 Pre-Smoke Checklist** (added to runbook)
   - Focused on validating the *check/imaging leg* as the primary paid-tier benefit.
   - Include pre-flight production state verification, expected Processing log signatures, page clamping behavior, cropper activation, payee quality on checks, register consistency, rollback test procedure, etc.
   - Clear pass/fail criteria per item.

2. **Gate A3 Evidence / Report Template** (ready for human to fill during/after smoke)
   - Structured sections for:
     - Pre-smoke confirmation
     - Per-PDF results (register + imaging)
     - Processing log excerpts (critical lines only)
     - Screenshot references (without embedding client data)
     - Payee quality notes on checks
     - Inconsistencies observed
     - Overall leg verdict
   - Must be copy-paste friendly and minimal.

3. **Post-Smoke Analysis Scaffolding + Scorecard**
   - Clear PASS/FAIL structure for the check/imaging leg.
   - Verdict language on whether the leg is now "production-ready for daily driver / Laura pilot".
   - Decision tree: Path A (proceed to pilot + `apply docs`) vs Path B (register-only + rollback posture) vs "needs more work".
   - Proposed exact commit scope and message (P0 imaging batch + data layer scripts) contingent on PASS.

4. **Runbook Updates**
   - Bring "Current execution state" table, running log, final production state table, and Cursor action sections forward to reflect data layer complete + P0 imaging deployed + Gate A3 as sole remaining gate.
   - Add new "Gate A3 Preparation" section with the checklist, template, and scorecard.
   - Update any stale "data layer blocked" language.

5. **Commit & Documentation Decision Package**
   - Exact proposed git commit scope + message (after Gate A3 PASS).
   - Precise conditions under which `apply docs` on Blueprint v2.44.20+ and README is authorized.
   - Risk assessment of proceeding to Laura pilot vs maintaining rollback posture.

6. **Any Additional Prep**
   - Commands/scripts the human should run before the smoke (health checks, DI probe if added, etc.).
   - Clear handoff instructions for when the human pastes smoke results back.

---

## Success Criteria for This Orchestration Phase

- Runbook is the single accurate source of truth for the current production state (data layer + P0 imaging complete, only Gate A3 pending).
- Human has a crisp, usable checklist + evidence template they can execute against during the live smoke.
- Clear, evidence-based criteria exist to declare the check/imaging leg production-ready (or not).
- Post-smoke analysis can be completed in < 30 minutes once results are pasted.
- All work respects the one hard limit and constitutional rules.

---

## Invocation (Recommended)

From repo root:

```powershell
grok -p "@docs/gate-a3/Gate-A3-Orchestration-Launch-Directive.md" `
     --cwd C:\SLAM-Services-Project `
     --output-format markdown `
     > docs/gate-a3/gate-a3-launch-output.md
```

Then feed the resulting analysis + artifacts (or this directive itself) to Cursor with instructions to begin execution under the constraints.

**Recommended launcher (easiest):**

```powershell
.\Scripts\Launch-GateA3Orchestration.ps1
```

**Autonomous dual-agent tool** (once `dual-agent doctor` passes with a valid `CURSOR_API_KEY`):

```powershell
.\Scripts\Launch-GateA3Orchestration.ps1 -Mode DualAgent -MaxTurns 12
```

Or directly:

```powershell
dual-agent run "@docs/gate-a3/Gate-A3-Orchestration-Launch-Directive.md" --mode reviewer-implementer --max-turns 12
```

---

## Coordination Note (Dual-Agent)

If using the autonomous dual-agent tool or any Grok ↔ Cursor loop:
- Cursor (implementer/builder) owns execution of the deliverables above.
- Grok (reviewer) receives prepared artifacts for rigorous review against the success criteria, scope boundaries, and operational risk before any runbook commit or proposal to the human.
- Human remains the bridge for any live production actions and the actual Gate A3 smoke.

---

**This directive supersedes earlier partial or outdated prompts for Gate A3 preparation.**

---

## Pre-Launch Readiness Checklist (Run This First)

Before launching the orchestration or performing the smoke:

1. Run `dual-agent doctor` (or just validate your `CURSOR_API_KEY` is set if using autonomous mode).
2. Confirm the latest P0 imaging code is deployed (or note the current deploy id).
3. Confirm Postgres is healthy on the App Service (`USE_POSTGRES=true`, client count visible).
4. Have both real PDFs ready locally.
5. Be prepared to capture Processing logs + screenshots during the smoke (human only).

---

Launch and drive. Update the runbook as you go. Hand back only what requires human action or Grok review.