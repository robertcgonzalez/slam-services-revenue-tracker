# State Alignment Run — Full Codebase Drift Audit (Phases 1–3)

**Date**: 2026-05-30  
**Process**: `QMS/State-Alignment/process.md` Step 3 (Documentation & Process Drift)  
**Plan**: `.cursor/plans/codebase_drift_audit_96b59c1a.plan.md` (findings catalog; not duplicated here)

---

## Scan summary

| Severity | Count |
|----------|------:|
| Critical | 6 |
| High | 14 |
| Medium | 18 |
| Low | 12 |

**Top risks addressed in Phases 1–2:** dual GHA deploy race (C5/C6), contradictory `appCommandLine` guidance (C4), README/Blueprint narrative lag vs DI-only production UI (C1/C3).

## Phases executed

- **Phase 1 — Production safety:** Legacy workflow push-to-`main` disabled; `deployment.md` unified on `./startup.sh`; stale handoff superseded banner.
- **Phase 2 — Narrative alignment:** README Production vs Local split; Blueprint v2.44.25 supersedes v2.44.15 tabular story; link repairs; Gate A3 runbook reconciliation; Grok env inviolability; VS Code Kilo retirement.
- **Phase 3 — Dependencies & config:** Removed unused `plotly`; PyYAML local-only note; corrected `.env` loader docs; agent zip/Data rule aligned; `SLAM_RUN_GATE_A3_SMOKE` in deployment App Settings table.

## Residual debt (Phase 4 — deferred)

`hybrid_cv_status()` mislabeling (H11), orphan `bank_statements_tabular.py` (H12), Azure-only docstring alignment (H13), cropper consolidation (M9–M10), shared logging formatter (M8), partial DB indexes vs ORM (M12), spike Codespaces banner pass (M14).

## Verification

Memorialization closed per `docs/memorialization-discipline.md`: `feedback_log.csv` row + Blueprint v2.44.25 Change Log + this run file. Final `Invoke-GitVerification.ps1` result logged in implementer session output.
