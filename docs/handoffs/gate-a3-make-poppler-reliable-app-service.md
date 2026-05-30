# Gate A3 — Make Poppler Reliable on App Service (Enable Imaging Leg)

**Single Focused Goal:**  
Ensure `pdftoppm` (poppler-utils) is reliably present in the production App Service container on every deploy so the geometric cropper v5 + per-crop `prebuilt-check.us` imaging leg can actually run. This was the hard blocker observed in the 2026-05-29 owner re-smoke (HCC log: "Check cropper skipped: poppler (pdftoppm) not on PATH").

**Mode:** reviewer-implementer

**Max turns:** 6

**Non-negotiables:**
- Cursor is the primary implementer for any code or deployment changes.
- Changes must be minimal and safe.
- Do not ask the owner for opinions or extra input.
- Respect the production fast-path constraints in `startup.sh` (cold-start time, Oryx behavior).
- The goal is to make the imaging leg testable on the next owner re-smoke.

---

## Current Situation (use this exactly)

From the 2026-05-29 owner re-smoke on production:
- HCC 2026-04.pdf log: Cropper completely skipped because poppler was missing.
- Result: 98 register + 0 supplemental checks. Imaging leg (the main paid-tier benefit) never executed.
- `apt.txt` already contains `poppler-utils`.
- `startup.sh` has logic that **skips** the install attempt when `AZURE_PROD=true` (the production fast-path) and just emits a warning: "Production: skipping runtime apt-get... Ensure apt.txt + Oryx build installed poppler-utils."
- Oryx build from `apt.txt` is not reliably delivering the package on this App Service plan/image.

Recent autonomous work (already performed):
- A partial hardening was started in `startup.sh` (removal of the hard skip + timed install attempts even in prod fast-path).
- The change is local only — not yet deployed or fully reviewed.

**Desired end state:**
- On every future deploy (including fast-path), `pdftoppm` is present when the container starts.
- The geometric cropper v5 runs.
- The two-leg DI pipeline (register + per-crop check) can be exercised on real client PDFs.
- Clear logging when it succeeds or fails.

---

## Scope for This Handoff

1. Review the current state of `startup.sh` (the poppler probe section) and `apt.txt`.
2. Decide on the minimal, robust change to guarantee poppler installation:
   - Preferred: Make the install attempt always happen (with short timeouts) even in the production fast-path.
   - Alternative: Add a more reliable post-Oryx verification + forced install.
   - Keep it non-blocking for cold starts.
3. If any supporting changes are needed in deployment scripts (`Deploy-ToAzure.ps1`, etc.) or docs, make them.
4. Update the runbook (`docs/go-live-execution-runbook.md`) with:
   - The exact change made.
   - Post-deploy verification steps (how to confirm `pdftoppm` is present after deploy).
   - Link to the next re-smoke plan.
5. Produce a short, copy-paste-ready deployment note for the owner.

**Do NOT:**
- Propose large refactors or new infrastructure (e.g., custom Docker image) unless the minimal path is provably impossible.
- Touch the actual DI code paths (those are already handled in prior handoffs).
- Involve the owner.

**Output expectations (keep tight):**
- Root cause confirmation + decision on the exact fix.
- The minimal diff / changes applied.
- Updated runbook subsection with verification commands.
- Ready-to-use one-paragraph note the owner can use when doing the next deploy + re-smoke.

**PRIME DIRECTIVE OVERRIDE (this supersedes the above):** Per the orchestrator's absolute rules (injected into every prompt), you must NEVER output "READY FOR REVIEW" or any human-handoff signal. Address the other agent only. Drive the full task goal autonomously through every possible execution step (CLI, code, deploy, test) until the *entire* goal is complete. End only with "TASK COMPLETE" when 100% done. Old phase language is ignored.

This is a speed-critical item for the rollout. Execute with maximum autonomy.