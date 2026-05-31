# State Alignment Run — v2.45.4 Deploy + Gate A3 Re-Smoke

**Date**: 2026-05-31  
**Process**: `QMS/State-Alignment/process.md` (post-deploy evidence)  
**Prior run**: `QMS/State-Alignment/runs/2026-05-31-v2454-auto-body-dedupe-fix.md`

---

## Deploy

| Field | Value |
|-------|-------|
| Deploy GUID | `b013ddfa-748e-4790-b0a5-e5a56ad6a8c2` |
| Path | `Build-AzureDeployZip.ps1` → `Deploy-ToAzure.ps1 -RunGateA3Smoke` |
| Hotfix | `Seed-WwwRootAppHotfix` confirmed v2.45.4 `App/bank_statements.py` on wwwroot |

## Smoke verdict

| PDF | Rows | Deposits | Withdrawals | Gold withdrawals | Automated pass ($100 tol) | Owner disposition |
|-----|-----:|---------:|------------:|-----------------:|:-------------------------:|:-----------------|
| HCC | 98 | $163,914.00 | $45,703.76 | $45,703.76 | **PASS** | — |
| Auto Body | 94 | $41,786.80 | **$41,130.18** | $41,403.63 | **FAIL** (Δ $273.45) | **Accepted** — human review in reconciliation UI |

**Auto Body assembly**: 44 register + 50 supplemental; `register_incomplete=true`; `supplemental_skipped_duplicates=0`; `supplemental_by_amount=14`; `payee_rules_applied=3`; 56 crops.

**Finding**: v2.45.4 dedupe fix (register-debit-only cross-source match) is live; production withdrawal total unchanged vs v2.45.3. Owner edict (Robert): residual Δ $273.45 is acceptable for daily driver — Laura/Stef finalize via reconciliation banner + optional review note; pipeline supports iterative human inputs over chasing perfect automation on this edge case.

**Human-review UI (v2.45.4)**: reconciliation mismatch expander shows `human_review_guidance`; optional review note field; processing log includes assembly skip summary and dedupe dropped-row detail.

## Evidence pointers

- Harvest: `deploy-logs-temp/gate-a3-smoke-log-harvest.txt`
- Deploy log: `deploy-logs-temp/v2454-deploy-smoke.log`
- Guide: `docs/gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md`

## Verification

- `ruff check` + `Scripts/test_azure_assembly.py`: pass locally
- `Collect-GateA3Evidence.ps1 -Both`: pass (evidence collected; Auto Body automated totals criterion not met — owner-accepted)
