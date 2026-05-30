# QMS Operations Quick Reference

**Purpose**: This folder is the **living operational home** of the SLAM Services ISO 9001 baseline (v2.44.8+). It contains everything needed to execute governance, issue registration, corrective action (CAPA), risk management, and continual improvement in daily project and practice work.

**Guiding Rule**: Everything here must increase Laura’s confidence or reduce operational risk/toil. If it adds friction without clear value, remove it.

---

## Daily / Weekly Operating Rhythm

### 1. Issue / Nonconformity Registration (most common action)
- Any user (Laura, Stef, Robert, Patty) submits via the **📣 Submit Runtime Feedback** expander in the live Streamlit app.
- This appends directly to `Data/feedback_log.csv`.
- Robert (or designated agent) reviews new entries at the start of each work session or iteration.
- Triage immediately in `Section 14` of the Blueprint (update status, add root cause notes, assign owner).

**Escalation to formal CAPA** (see `CAPA/instructions.md`):
- High/Blocking priority, or
- Recurring pattern, or
- Systemic (affects multiple clients, data integrity, security, or Laura’s confidence), or
- Cross-version impact.

### 2. Corrective Action (CAPA)
- Use `CAPA/template.md` when escalation criteria are met.
- Every CAPA **must** produce a linked entry in the Blueprint Change Log (the fix + verification).
- Close the loop by updating the original `feedback_log.csv` row and the CAPA file with verification evidence.

### 3. Management Review (periodic evaluation)
- Run using `Management-Reviews/template.md`.
- Cadence: At major version bumps (v2.45+), after any material incident, or quarterly.
- Output is a dated file in `Management-Reviews/`.
- Record decisions as new rows in `feedback_log.csv` (Category = "QMS / Management Review") or direct Blueprint updates.

### 4. State Alignment (preventive / proactive improvement)
- This is the primary **continual improvement engine**.
- Run the process in `State-Alignment/process.md` after significant spikes, stabilizations, or at the start of a new iteration.
- Output goes into `State-Alignment/runs/` (one small Markdown per run).
- Recommendations are actioned via existing mechanisms (Blueprint Change Log, Section 14, code changes). Never create long new documents.

### 5. Risk Management
- Maintain the living `Risk-Register.md`.
- Review high items during every Management Review and State Alignment run.
- Add new risks as they are identified (especially during spikes and real-user testing).

---

## Artifact Ownership & Locations

| Artifact | Owner | Location | Update Trigger |
| --- | --- | --- | --- |
| `feedback_log.csv` | All users (via app) + Robert triage | `Data/` | Every runtime observation |
| CAPA records | Robert (or agent) | `QMS/CAPA/` | Escalated issues only |
| Management Reviews | Robert | `QMS/Management-Reviews/` | Per defined cadence |
| Risk Register | Robert | `QMS/Risk-Register.md` | New risk identified or status change |
| State Alignment runs | Robert + agents | `QMS/State-Alignment/runs/` | After major work or per iteration |
| Blueprint (Change Log hub + QMS pointer) | Robert + agents | Root | After any material QMS action |
| Section 14 (triage & plan) | Robert | Blueprint | Weekly / per iteration |

---

## Agent & Tooling Rules (Cursor / Grok)

- When starting any session that touches process, governance, or improvement: read this `QMS/README.md` + the active `State-Alignment/process.md`.
- All QMS work follows the same anti-bloat + git-confirmation standing orders as the rest of the project.
- After completing a CAPA, Management Review, or State Alignment run, add a concise entry to the Blueprint Change Log (v2.44.9+).
- Never duplicate content between this folder and the Blueprint. The Blueprint owns the "why" and history (as the authoritative hub + cross-reference index per the 2026-05-28 hub evolution). `QMS/` owns the live operational templates, current records, and execution detail. See `docs/data-model.md` as the first example of delegated specialized content.

---

## Current Baseline Status (as of v2.44.24)

- **Baseline hub**: Blueprint status line + Change Log (v2.44.10 hub evolution); operational detail in this `QMS/` folder — not a recreated Blueprint Section 15 body
- **Operational home**: This `QMS/` folder (activated v2.44.9)
- **Last Management Review**: See most recent file in `Management-Reviews/`
- **Open feedback items**: Check `Data/feedback_log.csv`
- **Risk Register**: `Risk-Register.md` (review before every Management Review)

**Questions or drift?** Run a State Alignment pass or open a Management Review.

---

*This document is intentionally short and actionable. Its job is to let anyone (human or agent) execute the QMS correctly on the first try.*