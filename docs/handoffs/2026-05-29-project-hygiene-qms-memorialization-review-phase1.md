# Phase 1 Handoff — Project Hygiene, QMS Revitalization & Memorialization Discipline (Discovery + High-Impact Quick Wins)

**Single Focused Goal for This Dual-Agent Run:**  
Perform a ruthless, evidence-based audit of the current project state (code, docs, git hygiene, QMS usage, memorialization practices). Identify the root causes of the observed "unkempt" condition and lax memorialization. Produce a minimal, high-signal audit report + prioritized amelioration backlog. Immediately execute the 3–5 highest-leverage, lowest-risk, anti-bloat-compliant fixes (especially anything that makes QMS alive and enforces future memorialization discipline). Leave the working tree clean, committed (after full mandatory verification sequence), and with updated living documents in their correct roles per the Documentation Roles Matrix. All work must demonstrably increase Laura’s confidence or reduce long-term operational/hand-off risk.

**MANDATORY PRE-WORK (do this first, log everything):**
1. Read in order (use your tools):
   - `CONSTITUTION.md`
   - `README.md` (full Documentation Roles Matrix + agent workflow)
   - `QMS/README.md`
   - `QMS/State-Alignment/process.md`
   - `QMS/Management-Reviews/2026-05-28-initial-qms-baseline-review.md`
   - `.cursor/rules/slam-services.mdc` and `.grok/AGENT.md`
   - The working-tree version of `SLAM Services - Digital Transformation Blueprint.md` (especially Change Log through v2.44.20 and any Section 14/15 content)
2. Run the **full mandatory git verification sequence** exactly as defined in the agent contracts (even though we are not yet committing):
   ```powershell
   git status
   git diff --cached --stat
   git check-ignore -v . 2>$null | Select-String -Pattern "(Data/|\.csv|\.env|secrets|logs|\.zip)" | Select-Object -First 20
   # Explicit sensitive scan
   git ls-files --others --exclude-standard | Select-String -Pattern "(\.env|Data/.*\.csv|.*\.zip|deploy-logs)" 
   Write-Output "=== VERIFICATION SUMMARY (before any edits) ==="
   ```
   Capture and include the complete output in your final audit report. Note every deviation from the "clean → commit → push" contract.

**Audit Scope (be exhaustive but output only signal):**
- **Git / Memorialization Hygiene**: Why is the tree dirty with uncommitted changes to App/, docs/, Blueprint (v2.44.20 text), dual-agent source, PS scripts, etc.? Was the full verification sequence + commit performed for the dual-agent addition and the Azure outage recovery work? Cross-check recent file mtimes (last 7 days) against the last commit and the Change Log. Identify every material change that exists in tree but is not yet in the official Blueprint Change Log or QMS records.
- **QMS Health (the "shambles" claim)**: 
  - `Data/feedback_log.csv` usage since 2026-05-24 (only 1 ancient row).
  - State Alignment runs: only the 05-28 hub one exists.
  - Management Reviews: only initial.
  - CAPA records: zero real files.
  - Risk Register last review date vs. recent events (dual-agent tool creation, production outage recovery, G1 spike closures).
  - Whether O-002 (QMS visibility in sidebar + health_check) from the initial review was ever done.
  - Whether the active `QMS/State-Alignment/process.md` was actually used after the 05-28 Management Review declared it the "primary continual improvement engine".
- **Documentation Drift & Anti-Bloat Violations**:
  - Orphan / unintegrated content in `Documents/` (all the cursor_g1_*, phase review, recommendation, transcript files).
  - `Scripts/spike/` bloat (thousands of files from G1 phases 0-7) — is there a clear archival/indexing policy? Are the POST_* and PHASE* notes properly cross-referenced from Blueprint?
  - Any duplication between `docs/proposed-state-alignment-process.md` and the now-active `QMS/State-Alignment/`?
  - Stale references anywhere to retired Codespaces/devcontainer paths, old version numbers, or pre-QMS feedback process.
  - Whether recent dual-agent improvements (cli.py, orchestrator, Invoke-DualAgentHandoff.ps1, handoff pattern) are reflected in the correct places (Blueprint for history, `tools/dual-agent/PROJECT_STATUS.md` + README for usage, `docs/deployment.md` for the operational pattern).
- **Code / Structural Unkemptness**:
  - Recent uncommitted edits in `App/app.py`, `App/bank_statements.py`, `App/azure_document_intelligence.py`, `App/data_paths.py`, etc. — what do they actually change? Do they follow style (ruff clean?) and belong in the current architecture?
  - Multiple overlapping bank-statement processing paths (tabular vs full, legacy parser, spike versions) — any obvious consolidation or clearer separation opportunities?
  - Root-level clutter (.bak, zips, logs, CSVs that should stay in Data/).
  - Any obvious dead code, TODOs/FIXMEs, or commented-out blocks that survived previous hygiene passes.
- **Procedure / Contract Adherence**: Evidence that the "read Constitution + Blueprint first" habit, anti-bloat review before doc edits, and "Cursor primary + Grok secondary" model are being followed in recent sessions. Any signs the thin agent contracts are out of date relative to reality (dual-agent now being a core production tool)?

**Output Requirements (strict — put content in exactly the right place per Roles Matrix):**
- Create (or update in place) a dated State Alignment run: `QMS/State-Alignment/runs/2026-05-29-project-hygiene-memorialization-audit.md`
  - Follow the 3-part template in `QMS/State-Alignment/process.md`.
  - Include the full git verification output from step 1.
  - List concrete, prioritized "Amelioration Backlog" items (categorized: Memorialization Enforcement, QMS Activation, Doc Hygiene, Code Cleanup, Procedure Changes). For each: one-sentence impact on Laura’s confidence or handoff risk, estimated scope (tiny/small/medium), correct target document(s), and "execute in this phase?" flag.
- **Only** update the Blueprint Change Log (with a concise v2.44.21 or appropriate bump entry) for material new history (the audit itself + any fixes executed). Do **not** duplicate operational detail — that belongs in the QMS run file or `docs/`.
- Seed real recent events into `Data/feedback_log.csv` (the production outage + dual-agent adoption as a process improvement) using the in-app format or direct append. Set appropriate priority/status.
- Update `QMS/Risk-Register.md` with any new high/medium items surfaced (e.g. "Git + memorialization discipline has lapsed in practice", "QMS activation incomplete — preventive control not yet operational", dual-agent operational dependency risk) and bump the "Last Reviewed" date.
- If warranted by the outage + recovery, create the first post-baseline `QMS/Management-Reviews/2026-05-29-post-incident-review.md` stub (use the template) so the loop is closed.
- **Execute the best ameliorations in this same run** (the ones you flag as "execute now"):
  - Highest priority: anything that makes QMS visible and habitual (e.g. implement the long-planned O-002 QMS status in `App/diagnostics.py` sidebar + `Scripts/health_check.py --qms` or `--full`).
  - Memorialization ritual: add a short, enforceable "Session Close / Memorialization Checklist" section to `docs/` (probably `docs/memorialization-discipline.md` or extend an existing ops doc) + a one-line pointer + mandatory language update in both agent contracts (`.cursor/rules/slam-services.mdc` and `.grok/AGENT.md`). The checklist must require: (a) triage any new runtime observation into feedback_log or CAPA, (b) update the correct living document, (c) full git verification sequence, (d) commit+push when clean.
  - One or two tiny code hygiene wins if they are obvious and zero-risk (e.g. ruff on touched files, removal of one obvious orphan, .gitignore tightening for new clutter patterns).
  - Do **not** do large refactors, new features, or anything that would bloat documents. "Good enough for daily driver + handoff confidence" is the bar.
- At the very end of the run (before any commit):
  - Re-run the full git verification sequence on the **post-edit** tree.
  - If clean and verification passes, commit + push to origin main with a clear message that references this handoff and the new QMS State Alignment run. Surface the complete verification output.
  - If anything is still dirty or verification flags issues, stop, document exactly what remains, and do **not** commit. Explain the blocker.

**Success Criteria (what "done" looks like for this phase):**
- A living, dated QMS State Alignment artifact exists that a future human or agent can read in <5 minutes and know exactly what was broken and what the next 3 concrete actions are.
- At least one concrete, visible QMS activation improvement is shipped (UI or CLI surface).
- A lightweight memorialization ritual is now codified in the agent contracts and a docs/ procedure file.
- Recent real events (outage recovery, dual-agent as production tool) are reflected in feedback_log + Risk Register + (if material) Blueprint.
- Working tree is either cleanly committed/pushed or the exact remaining dirt is explicitly documented with a plan.
- Zero duplication introduced. Every new or updated sentence lives in exactly one place per the Roles Matrix.
- Full verification outputs (pre and post) are captured in the audit artifact.
- Laura’s confidence signal: the project now visibly polices its own discipline instead of relying on any single person’s memory or ad-hoc heroics.

**Constraints (non-negotiable):**
- Follow the exact anti-bloat / role-respect standing order before touching any document.
- Cursor operates with full autonomy for this task (per `.cursor/rules/slam-services.mdc`).
- Grok (via this orchestrator) will review the transcript + artifacts. Only the highest-signal, minimal changes survive.
- Security & Laura-confidence are absolute. Never touch secrets, never weaken verification.
- If you discover anything that feels like scope creep or would create long new docs, push it to the "Amelioration Backlog" as "future State Alignment item" instead of doing it now.

**After You Finish:**
- The final message from Cursor must include:
  1. Link to the new State Alignment run file.
  2. "PHASE 1 COMPLETE — ready for Grok review" (exact phrase so the orchestrator and human can chain cleanly).
  3. One-paragraph "Laura’s Confidence Impact" summary.
  4. The exact command a human should run next (e.g. `dual-agent resume <id>` or the next handoff PS1).

This single run should leave the project noticeably tighter, the QMS observably more alive, and the memorialization muscle memory restored — without adding bureaucratic weight.

**Launch this via:**
```powershell
.\Scripts\PowerShell\Invoke-DualAgentHandoff.ps1 -Directive "docs/handoffs/2026-05-29-project-hygiene-qms-memorialization-review-phase1.md" -MaxTurns 8
```
