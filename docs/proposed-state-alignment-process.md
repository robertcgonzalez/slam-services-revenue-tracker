# Proposed: Lightweight State Alignment Process (Future)

**Status**: Proposed / Not Implemented (logged in Blueprint Change Log under v2.44.5 Future item).

**Goal**: Move from purely retrospective documentation (Change Log updates after the fact) to a lightweight, recurring practice that proactively identifies what should be added, removed, updated, or deprecated in the product or its documentation based on the project's *current* reality.

## Why This Matters
The current system works well for recording what happened. It is weaker at surfacing drift between:
- What the code actually does today
- What users are actually experiencing / complaining about (`feedback_log.csv`)
- What the documented vision and roadmap claim (this Blueprint + Section 14)

## Lightweight Process (Minimal Viable Version)

**Cadence**: At the start of every major iteration / after any significant spike or stabilization wave (not every tiny bugfix).

**Inputs** (use what already exists):
- Recent entries in `Data/feedback_log.csv` (especially Open / In Progress)
- Sidebar diagnostics + `Scripts/health_check.py --full` output
- Current "what ships" reality (review recent commits + App/ + Scripts/ changes)
- Documented target state (Blueprint roadmap + Section 14 + any active spike handoff plans)

**Simple Review Template** (can be done by Robert or an agent):

1. **Reality vs Documented Vision**  
   - What documented features/capabilities are not yet real, or are now obsolete?
   - What real capabilities exist in code but are poorly (or not) documented?

2. **Feedback vs Roadmap**  
   - Which recent feedback items represent gaps in the documented future work?
   - Are there patterns in user pain that should drive new (or deprioritized) items in Section 14 or the main roadmap?

3. **Documentation Drift**  
   - Which sections of the Blueprint, README, or `docs/` are now misleading or stale relative to current behavior?

**Output** (keep it lightweight):
- 3–8 concise recommendations.
- Each recommendation should answer: "Add / Remove / Update / Deprecate **what**, in **which document or code area**, and **why** (tied to feedback or observed reality)".
- Log the recommendations in one of two places:
  - New row(s) in `feedback_log.csv` (Category = "Process / Documentation")
  - Or a short "State Alignment Review" subsection under the current iteration in Section 14 of the Blueprint.

**Agent Role** (when used by Cursor or Grok):
- The agent is expected to surface candidate items during or after significant work, using the template above.
- Final ownership and triaging remains with Robert (consistent with current RACI).

## Anti-Bloat Guardrails
- This process must **not** create new long documents.
- Recommendations should usually result in small, targeted updates to existing artifacts (Blueprint Change Log, Section 14, `docs/`, etc.).
- If the review finds "nothing material", explicitly note that and move on.

---

This proposal is intentionally minimal. It reuses existing mechanisms (`feedback_log.csv`, Section 14, the Change Log, and the agent contracts) rather than inventing new heavyweight processes.

**Next step when ready**: Turn the "Future implementation" note in the Blueprint Change Log into a small pilot (one review cycle) and refine from real usage.