# Gate A3 — Final Closure Preparation

**Single Focused Goal:**  
Consolidate everything from prior Gate A3 work (assembly double-counting diagnosis, poppler reliability fix via the just-completed handoff, 2026-05-29 owner re-smoke evidence) into the minimal set of artifacts needed to close Gate A3 after the next deploy. Produce a clean, ready-to-execute "final re-smoke + verdict" package so the overall problem can be driven to completion without further pauses.

**Mode:** reviewer-implementer

**Max turns:** 5

**Non-negotiables:**
- Cursor is primary for producing the artifacts.
- Everything must be minimal, high-signal, and owner-actionable.
- No new questions or asks to the owner in the output.
- Use only facts already in the runbook and prior handoff results.
- The end state is that after one deploy + one owner re-smoke, we can issue a final verdict and Path recommendation.

---

## Context to Use

**What is already solved (do not re-diagnose):**
- Root cause of totals discrepancy in the re-smoke: two-leg assembly double-counting on non-sparse register passes (especially Traditions-style PDFs where DI register rarely populates Check#).
- Protective logic already in source: conditional supplemental check rows only when register is sparse (< 3 rows), with `_normalize_check_number` and provenance.
- Poppler deployment gap: Confirmed blocker in 2026-05-29 re-smoke (HCC log explicitly said cropper skipped because pdftoppm not on PATH). Just addressed via the previous orchestrator handoff (startup.sh now forces timed install even in prod fast-path + IMAGING_LEG structured logging).

**2026-05-29 owner re-smoke evidence (use exactly):**
- HCC 2026-04.pdf: 98 register + 0 supplemental (cropper skipped due to missing poppler). Export CSV exists in deploy-logs-temp.
- Auto_Body_Center_Jan_26_Statement.pdf: 49-row export with lower totals vs gold baseline (92 txns / $41,786.80 deposits / $41,403.63 withdrawals).
- Owner also has screenshots in deploy-logs-temp showing the UI discrepancy (correct numbers in some per-file views vs jacked numbers in the main summary + table).

**What still needs to happen before we can close Gate A3:**
- One deploy of the current source (now includes both assembly hardening + poppler reliability fix).
- Post-deploy verification that `IMAGING_LEG poppler=ok` and pdftoppm is present.
- One clean owner re-smoke on both PDFs with the imaging leg actually enabled.
- Final scorecard + verdict on whether the check/imaging leg is now production-ready.

---

## Deliverables Required (produce these exactly)

1. **Updated runbook subsection** (ready-to-paste text) titled "Gate A3 — Path to Final Verdict (Post-Poppler Fix)":
   - Clear before/after summary of the two issues that were blocking the imaging leg.
   - Exact deploy + verification steps (including the IMAGING_LEG check).
   - What "success" looks like on the next owner re-smoke (HCC should now produce crops + supplemental rows; Auto Body totals should be closer to gold when imaging leg runs).

2. **Pre-filled Evidence Template guidance** (short):
   - A one-page note the owner can use when doing the final re-smoke, mapping what numbers to capture from the UI/screenshots/exports now that the imaging leg should be live.

3. **Gate A3 Closure Checklist** (minimal bullet list):
   - Deploy current source.
   - Verify poppler + IMAGING_LEG poppler=ok.
   - Owner re-smoke both PDFs.
   - Owner pastes the specific numbers/logs from that re-smoke.
   - Final scorecard + Path recommendation issued.

4. **Any tiny script or command helper** (if useful):
   - A one-liner or small addition that makes the post-deploy poppler verification brain-dead simple (e.g., a helper in Deploy-ToAzure.ps1 or a note in the runbook).

**Output format:** 
- The exact text blocks for the runbook.
- The checklist as clean markdown.
- Any command helpers as copy-paste blocks.
- (PRIME DIRECTIVE OVERRIDE) Do NOT end with "READY FOR REVIEW" or any handoff phrase. The orchestrator forces full autonomous iteration to the complete task goal only. Output "TASK COMPLETE" solely when the entire user-requested outcome is delivered and verified. All phase/handoff instructions in this file are overridden.

Do the work. Produce the artifacts. Do not stop or ask for direction. This is the step that lets the overall Gate A3 problem be driven to completion on the next deploy + re-smoke.