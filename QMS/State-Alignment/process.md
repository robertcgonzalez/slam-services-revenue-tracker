# State Alignment Process (Active)

**Status**: Active under the QMS (moved from proposed status in v2.44.9)

**Owner**: Robert (final decisions); agents (Cursor primary, Grok secondary) are expected to surface findings using this process.

**Goal**: Move from purely retrospective documentation to a lightweight, recurring practice that proactively identifies what should be added, removed, updated, or deprecated in the product, documentation, or processes based on the project's *current* reality.

---

## Why This Matters (QMS Context)

This process is the primary **preventive action and continual improvement** mechanism for the SLAM Services QMS baseline. It directly supports ISO 9001 Clause 10 (Improvement).

It closes the gap between:
- What the code and processes actually do today
- What users are experiencing (via `Data/feedback_log.csv`)
- What the documented vision claims (Blueprint + Section 14 + QMS artifacts)

---

## Cadence

Run this process:
- At the start of every major iteration or sprint
- After any significant spike, stabilization wave, or integration (e.g., G1 hybrid CV work)
- After a material incident or Management Review that surfaces systemic drift
- When Robert or an agent judges that reality has moved meaningfully

Do **not** run it for every tiny bugfix.

---

## Inputs (use only what already exists)

1. Recent entries in `Data/feedback_log.csv` (focus on Open / In Progress / recurring patterns)
2. Sidebar diagnostics + `Scripts/health_check.py --full` output
3. Current "what ships" reality (recent commits, `App/`, `Scripts/`, `QMS/` changes)
4. Documented target state (Blueprint roadmap + Section 14 + active spike handoff plans + this QMS baseline)
5. Current Risk Register (`QMS/Risk-Register.md`)

---

## Review Steps (simple 3-part template)

### 1. Reality vs Documented Vision
- What documented features, capabilities, or processes are not yet real, or are now obsolete?
- What real capabilities or behaviors exist in code/process but are poorly (or not) documented?
- Are any QMS controls (governance, CAPA, risk, Management Review) drifting from the descriptions in Blueprint Section 15?

### 2. Feedback vs Roadmap & QMS
- Which recent feedback items represent gaps in the documented future work or in current QMS controls?
- Are there patterns in user pain (Laura/Stef daily work) that should drive new, reprioritized, or removed items in Section 14 or the QMS operational artifacts?
- Do any open issues indicate weaknesses in the current CAPA escalation rules or Management Review cadence?

### 3. Documentation & Process Drift
- Which sections of the Blueprint, README, `docs/`, `QMS/`, or agent contracts are now misleading or stale relative to current behavior?
- Are the anti-bloat / role-respect rules and git confirmation sequences still being followed in practice?

---

## Outputs (keep extremely lightweight)

Produce **3–8 concise recommendations** maximum.

For each recommendation, answer in one sentence:
> "Add / Remove / Update / Deprecate **X** in **Y location**, because **Z** (tied to specific feedback, health check result, commit, or observed reality)."

**Where to log outputs** (never create new long documents):
- New row(s) in `Data/feedback_log.csv` with `Category = "Process / Documentation"` or `"QMS / State Alignment"`
- Short "State Alignment Review" subsection in the current iteration of Blueprint Section 14
- If a recommendation affects the QMS baseline itself, propose a small update to Blueprint Section 15 and this process.md
- Save the raw review notes (if any) to `QMS/State-Alignment/runs/YYYY-MM-DD-description.md` (keep under ~30 lines)

**Anti-bloat enforcement**:
- If the review finds "nothing material", explicitly state that in the output and move on.
- Recommendations must result in *small, targeted* updates to existing artifacts.
- This process itself must never become a source of bloat.

---

## Agent Expectations

When Cursor or Grok performs significant work:
- The agent is expected to surface candidate State Alignment items using the template above.
- The agent may propose the recommendations, but **final ownership, prioritization, and execution decisions remain with Robert**.
- After the agent session, Robert (or the human lead) is responsible for logging the outcome via the approved channels.

---

## Version & Change History

- **v2.44.9 (May 28, 2026)**: Activated as official QMS continual improvement process. Moved from `docs/proposed-state-alignment-process.md` (now superseded). Added explicit QMS linkage, risk register input, and stronger anti-bloat language. First run scheduled after initial baseline adoption.
- Prior history: See original proposal in Blueprint Change Log v2.44.5 and the superseded file in `docs/`.

---

**Next action**: Execute the first real run of this process (document in `runs/`) and feed any findings into the first formal Management Review.