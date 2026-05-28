# Risk & Opportunity Register (Living)

**Last Reviewed**: 2026-05-28 (during Initial Management Review)  
**Review Cadence**: Every Management Review + after any major spike or incident

**Instructions**: Add new rows as risks are identified. Update status / mitigation as actions are taken. High and Medium items must be discussed in every Management Review and State Alignment run.

---

## Active Risks

| ID | Description | Likelihood | Impact | Owner | Mitigation / Current Status | Last Reviewed | QMS Link |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-001 | Heavy reliance on Robert for complex OCR pipeline changes and validation (G1 hybrid CV, cropper, etc.) | Medium | High | Robert | G1 handoff package + spike isolation + detailed POST_* docs + agent contracts. State Alignment process now active to surface drift earlier. | 2026-05-28 | CAPA escalation rule + Section 15 governance |
| R-002 | Feedback_log.csv remains very small because most work is internal/agent-driven; real daily-user volume not yet proven | Low | Medium | Robert / Laura | In-app submission form is live. Section 14 process is documented. Initial Management Review noted this as watch item. | 2026-05-28 | State Alignment input |
| R-003 | ~~Codespaces onboarding/auth friction~~ | — | — | Robert | **Closed (v2.44.16)** — Codespaces/devcontainer path removed; local Windows + `Setup-LocalVenv.ps1` / `Install-LocalHeavyOcr.ps1` only. | 2026-05-28 | Retired with env policy |
| R-004 | Future OneDrive / document management automation could introduce new data classification or retention risks | Low | High | Robert (future) | Document Retention Policy already in Blueprint Section 9. Will be re-evaluated when that workstream activates. | 2026-05-28 | Future CAPA / risk when scoped |
| R-005 | Agent-generated code or documentation could silently violate anti-bloat or roles matrix over many small sessions | Low | Medium | All agents + Robert | Strong standing orders in agent contracts + Documentation Roles Matrix + mandatory Blueprint Change Log discipline. State Alignment process now watches for this specifically. | 2026-05-28 | Core QMS control (Section 15.1) |

## Closed / Mitigated Risks (recent)

| ID | Description | Closed Date | How Mitigated |
| --- | --- | --- | --- |
| (none at baseline activation) | | | |

## Opportunities (positive risks worth pursuing)

| ID | Opportunity | Potential Benefit | Owner | Next Step | Status |
| --- | --- | --- | --- | --- | --- |
| O-001 | Activate State Alignment process as primary preventive engine | Early detection of documentation/process drift before it becomes user pain | Robert + agents | First real run before v2.45 | In progress (this review) |
| O-002 | Surface QMS status in app sidebar + health check | Increases daily visibility and Laura’s confidence in project professionalism | Robert | Code changes in diagnostics.py + health_check.py (v2.44.9) | Planned |
| O-003 | First formal Management Review + living QMS/ folder | Makes the strong existing culture explicit and auditable for handoff to Patty & Robert | Robert | This review file | Completed 2026-05-28 |

---

**Notes**:
- This register is intentionally small and Markdown-based. It will grow only as real risks surface through State Alignment, CAPAs, or daily use.
- Do not add speculative future risks that have no current evidence.