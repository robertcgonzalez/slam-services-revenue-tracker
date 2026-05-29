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
Run and log the complete output:

```powershell
git status
git diff --cached --stat
git check-ignore -v . 2>$null | Select-String -Pattern "(Data/|\.csv|\.env|secrets|logs|\.zip)" | Select-Object -First 20
git ls-files --others --exclude-standard | Select-String -Pattern "(\.env|Data/.*\.csv|.*\.zip|deploy-logs)"
Write-Output "=== VERIFICATION SUMMARY ==="
```

Confirm: no client CSVs, secrets, `.env`, logs, or deploy artifacts staged.

### 4. Commit + push when clean
- If verification passes → `git add` (relevant files only), commit with a clear message, push to `origin main`.
- If verification flags issues or sensitive paths → **stop**. Document the blocker in the session artifact; do **not** commit.

---

## Quick reference

| Observation type | Target |
| --- | --- |
| Daily user bug / UX gap | `feedback_log.csv` → Section 14 triage |
| Material incident | `QMS/Management-Reviews/` + Blueprint Change Log |
| Process / doc drift | `QMS/State-Alignment/runs/` |
| New or changed risk | `QMS/Risk-Register.md` |
| Agent handoff / phased work | `docs/handoffs/` + dual-agent session |

*Agents: this checklist is mandatory language in `.cursor/rules/slam-services.mdc` and `.grok/AGENT.md`.*
