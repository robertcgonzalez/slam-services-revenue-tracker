# Session Close / Memorialization Checklist

**Purpose**: Enforceable end-of-session ritual for humans and agents (Cursor primary, Grok secondary). Prevents "heroics in chat, nothing in git" drift.

**When**: At the end of every substantive work session — before declaring a task complete.

---

## Checklist (all four required)

### 1. Triage runtime observations
- Any new bug, outage, user pain, or process gap → append to `Data/feedback_log.csv` (via app **Submit Runtime Feedback** or direct append with the standard columns).
- If High/Blocking, recurring, or systemic → open a CAPA in `QMS/CAPA/` per `QMS/CAPA/instructions.md`.

### 2. Update the correct living document (one place only)
- **History / decisions** → Blueprint Change Log (version bump).
- **Operational detail / runbooks** → `docs/` or `QMS/State-Alignment/runs/`.
- **Current status / onboarding** → `README.md`.
- **Tool usage** → relevant `PROJECT_STATUS.md` or tool README.
- Never duplicate content across documents (see Documentation Roles Matrix in `README.md`).

### 3. Full git verification sequence
Execute the canonical implementation (single source of truth):

```powershell
.\Scripts\PowerShell\Invoke-GitVerification.ps1
```

Capture its complete output. It exits 0 only when clean (no sensitive paths staged or in high-risk untracked state). This script is the enforceable form of the verification ritual required by the agent contracts and the dual-agent Prime Directive.

### 4. Commit + push when clean (Prime Directive aligned)
- If `Invoke-GitVerification.ps1` exits 0 (CLEAN) → `git add` (relevant files only), commit with a clear message, and `git push origin main`. The dual-agent Prime Directive requires agents to perform this themselves with no handoff to a human.
- If the script reports issues → **stop immediately**. Document the blocker. Do **not** commit. Re-run the script after remediation until it exits 0.

---

## Quick reference

| Observation type | Target |
| --- | --- |
| Daily user bug / UX gap | `feedback_log.csv` → Section 14 triage |
| Material incident | `QMS/Management-Reviews/` + Blueprint Change Log |
| Process / doc drift | `QMS/State-Alignment/runs/` |
| New or changed risk | `QMS/Risk-Register.md` |
| Agent handoff / phased work | `docs/handoffs/` + dual-agent session |

*Agents: this checklist (and the canonical `Invoke-GitVerification.ps1`) is mandatory language in `.cursor/rules/slam-services.mdc` and `.grok/AGENT.md`. Inside dual-agent runs the orchestrator Prime Directive is the highest law and requires full autonomous execution through verified push.*
