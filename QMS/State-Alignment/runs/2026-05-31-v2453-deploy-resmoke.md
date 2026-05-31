# State Alignment Run — v2.45.3 Deploy + Gate A3 Re-Smoke

**Date**: 2026-05-31  
**Process**: `QMS/State-Alignment/process.md` (post-deploy evidence)  
**Plan**: `.cursor/plans/v2.45.3_deploy_re-smoke_06d62e26.plan.md` (not duplicated here)

---

## Deploy

| Field | Value |
|-------|-------|
| Deploy GUID | `1dfb6b3f-ad3b-4f9a-938a-242aa8b52e41` |
| Path | `Build-AzureDeployZip.ps1` → OneDeploy (interrupted) → `Deploy-ToAzure.ps1 -SkipDeploy -RunGateA3Smoke` |
| Hotfix | `Seed-WwwRootAppHotfix` confirmed v2.45.2 `App/bank_statements.py` on wwwroot |

## Smoke verdict

| PDF | Rows | Deposits | Withdrawals | Gold withdrawals | Pass ($100 tol) |
|-----|-----:|---------:|------------:|-----------------:|:---------------:|
| HCC | 98 | $163,914.00 | $45,703.76 | $45,703.76 | **PASS** |
| Auto Body | 94 | $41,786.80 | **$41,130.18** | $41,403.63 | **FAIL** (Δ $273.45) |

**Auto Body assembly**: 44 register + 50 supplemental; `register_incomplete=true`; `supplemental_skipped_duplicates=0`; `payee_rules_applied=3`.

**Finding**: v2.45.2 register-prune fix is live but production totals unchanged vs v2.44.32 — residual gap is supplemental/imaging leg amounts, not register row loss (44 register rows retained in both code paths).

## Evidence pointers

- Harvest: `deploy-logs-temp/gate-a3-smoke-log-harvest.txt`
- Bundle: `deploy-logs-temp/gate-a3-intake-bundle.json`
- Guide: `docs/gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md` (auto-updated)

## Verification

- `ruff check` + `Scripts/test_azure_assembly.py`: pass locally
- `Collect-GateA3Evidence.ps1 -Both -UpdateDocs`: pass (evidence collected; Auto Body totals criterion not met)
