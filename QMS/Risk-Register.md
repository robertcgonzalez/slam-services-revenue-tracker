# Risk & Opportunity Register (Living)

**Last Reviewed**: 2026-05-31 (v2.45.4 — Auto Body dedupe RCA)  
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
| R-006 | Git + memorialization discipline lapsed in practice — substantial v2.44.19–20 work existed uncommitted | Low | High | Robert + agents | Session Close checklist + `Invoke-GitVerification.ps1`; Gate A3 on `origin/main`; **mandatory post-deploy smoke** in `docs/deployment.md` + `Deploy-ToAzure.ps1 -RunGateA3Smoke` (v2.45.1). | 2026-05-31 | Memorialization Enforcement |
| R-007 | QMS activation incomplete — feedback loop, State Alignment runs, and O-002 visibility delayed | Low | Medium | Robert | O-002 shipped; feedback_log seeded; State Alignment runs active; **post-incident Management Review closed** 2026-05-31. | 2026-05-31 | QMS Activation |
| R-008 | Dual-agent orchestrator now a production operational dependency for complex Azure recovery | Low | Medium | Robert | `docs/handoffs/` pattern + `Invoke-DualAgentHandoff.ps1`; document in deployment runbook; do not over-rely without human verification. | 2026-05-29 | Procedure / tooling |
| R-009 | Laura/Stef pilot adoption stalls — insufficient real `feedback_log.csv` volume or recurring P0 blockers | Low | High | Robert / Laura | Gate A3 HCC PASS; Auto Body withdrawal dedupe fix v2.45.4 (production re-smoke pending); payee rules active; post-deploy smoke gate enforced. | 2026-05-31 | Pilot sustainment |

## Closed / Mitigated Risks (recent)

| ID | Description | Closed Date | How Mitigated |
| --- | --- | --- | --- |
| R-GATE-A3-IMG | Gate A3 imaging leg (0 crops / poppler / supplemental inflation) blocked Laura pilot | 2026-05-31 | v2.44.28–32: cropper DPI, stale PNG purge, supplemental dedupe; headless smoke PASS — `QMS/State-Alignment/runs/2026-05-30-gate-a3-hardening.md` |

## Opportunities (positive risks worth pursuing)

| ID | Opportunity | Potential Benefit | Owner | Next Step | Status |
| --- | --- | --- | --- | --- | --- |
| O-001 | Activate State Alignment process as primary preventive engine | Early detection of documentation/process drift before it becomes user pain | Robert + agents | First real run before v2.45 | Completed 2026-05-29 (hygiene audit run) |
| O-002 | Surface QMS status in app sidebar + health check | Increases daily visibility and Laura’s confidence in project professionalism | Robert | Code changes in diagnostics.py + health_check.py | Completed 2026-05-29 |
| O-003 | First formal Management Review + living QMS/ folder | Makes the strong existing culture explicit and auditable for handoff to Patty & Robert | Robert | This review file | Completed 2026-05-28 |

---

**Notes**:
- This register is intentionally small and Markdown-based. It will grow only as real risks surface through State Alignment, CAPAs, or daily use.
- Do not add speculative future risks that have no current evidence.