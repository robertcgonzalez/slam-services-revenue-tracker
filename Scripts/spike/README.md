# Scripts/spike — G1 Azure CV hybrid check leg

**Status**: Phases 0–7 **complete** (2026-05-27). Production Streamlit Bank Statements is **Azure DI-only** (`App/app.py`); spike code is for **local validation**, regression, and G1 integration prep — not deployed to App Service by default.

**Environment**: **Local Windows only** (Python 3.10 + `.venv`, poppler on PATH). GitHub Codespaces / Docker dev paths were retired v2.44.16 — any Codespace mentions in older spike notes are historical; see [`docs/environment-policy.md`](../../docs/environment-policy.md).

**Stakeholder report**: [`Spike-Report-Computer-Vision-Check-Leg-20260527.md`](../../Spike-Report-Computer-Vision-Check-Leg-20260527.md) (repo root).

---

## Read first (integration team)

| Order | Document | Purpose |
|------:|----------|---------|
| 1 | [`G1_HANDOFF_PACKAGE_INDEX.md`](G1_HANDOFF_PACKAGE_INDEX.md) | What to wire vs spike-only |
| 2 | [`G1_READINESS_SNAPSHOT.md`](G1_READINESS_SNAPSHOT.md) | Honest go/no-go (Traditions/HCC vs QCR) |
| 3 | [`POST_SPIKE_INTEGRATION_PLAN.md`](POST_SPIKE_INTEGRATION_PLAN.md) | Gates G1–G5, sprint steps 3.1–3.5 |
| 4 | [`PRE_G1_INTEGRATION_CHECKLIST.md`](PRE_G1_INTEGRATION_CHECKLIST.md) | Sign-off checklist |
| 5 | [`PHASE7_NOTES.md`](PHASE7_NOTES.md) | Full script + markdown catalog |

---

## Python scripts (quick reference)

All scripts assume **repo root** as cwd unless noted. Heavy OCR requires `Setup-LocalVenv.ps1 -InstallHeavyOcr`.

| Script | Phase | Role |
|--------|-------|------|
| [`baseline_current_ocr.py`](baseline_current_ocr.py) | 0 | Local Enhanced baseline + artifact bundle |
| [`diagnose_check_deposit_cropper.py`](diagnose_check_deposit_cropper.py) | 1 | **SSOT** geometry/dedup cropper harness + overlays |
| [`phase1_cv_read_harness.py`](phase1_cv_read_harness.py) | 1 | CV Read + classify + payee extract on crops |
| [`phase1_cv_read_prototype.py`](phase1_cv_read_prototype.py) | 1 | Early prototype (superseded by harness) |
| [`phase1_breakdown.py`](phase1_breakdown.py) | 1 | Cohort stats helper |
| [`grade_phase1_crops.py`](grade_phase1_crops.py) | 1 | Interactive visual grader |
| [`fast_cv_photo_processor.py`](fast_cv_photo_processor.py) | 1 | Fast geometry-only photo leg experiments |
| [`_diag_photo_regions.py`](_diag_photo_regions.py) | 1 | Upper-bound region count diagnostic |
| [`phase5_hybrid_pipeline.py`](phase5_hybrid_pipeline.py) | 5 | End-to-end hybrid orchestrator (spike-only) |
| [`phase6_pl_smoke.py`](phase6_pl_smoke.py) | 6 | P&L pivot smoke on hybrid CSV |
| [`test_payee_extractor_smoke.py`](test_payee_extractor_smoke.py) | E1/E2 | **15-test regression gate** (uses `App/payee_extractor`) |
| [`test_hybrid_check_leg.py`](test_hybrid_check_leg.py) | G1 3.2 | Unit smoke for `App/hybrid_cv_check_leg.py` |
| [`test_azure_di_prefilter.py`](test_azure_di_prefilter.py) | — | Offline DI page pre-filter smoke |
| [`test_content_understanding_checks.py`](test_content_understanding_checks.py) | — | CU prebuilt-check.us smoke |
| [`generate_human_review_package.py`](generate_human_review_package.py) | E1 | Laura spot-check CSV from rescore |
| [`generate_rescore_diff_report.py`](generate_rescore_diff_report.py) | E1 | Before/after harness diff |
| [`regenerate_hcc_ground_truth.py`](regenerate_hcc_ground_truth.py) | E1 | Rebuild ground-truth CSV from grades |

**Payee engine**: Production code lives in [`App/payee_extractor/`](../../App/payee_extractor/). [`payee_extractor/__init__.py`](payee_extractor/__init__.py) is a thin re-export shim for spike scripts.

**PowerShell**: [`Provision-AzureComputerVisionRead.ps1`](Provision-AzureComputerVisionRead.ps1) — one-time F0/S1 CV resource (spike-only, not CI).

### Common commands

```powershell
# Env (repo root .env — gitignored)
copy Scripts\spike\cv-read.env.sample .env

# Regression gate (must pass before G1 merge)
python Scripts/spike/test_payee_extractor_smoke.py

# Phase 0 baseline
python Scripts/spike/baseline_current_ocr.py

# Phase 1 harness (reuse cache — zero Azure cost)
python Scripts/spike/phase1_cv_read_harness.py --reuse-cv-dir Scripts/spike/artifacts/<folder>
```

---

## Tier-1 markdown index (committed)

| Category | Files |
|----------|-------|
| **Integration** | `G1_*`, `POST_SPIKE_INTEGRATION_PLAN.md`, `PRE_G1_INTEGRATION_CHECKLIST.md`, `G2_*` |
| **Validation / metrics** | `E1_E2_STATUS.md`, `HCC_*`, `QCR_B5_VALIDATION_REPORT.md`, `RECOMMENDATIONS_*` |
| **Design** | `EXTRACTOR_EVOLUTION_DESIGN.md`, `PHASE5_HYBRID_DESIGN.md`, `SCHEMA_DECISION.md`, `HYBRID_CV_READ_SCOPE_CLARIFICATION.md` |
| **Phase logs** | `PHASE0_NOTES.md` … `PHASE7_NOTES.md`, `PHASE1_CROPPER_GAP_DIAGNOSIS.md` |
| **Policy** | `PEREZ_OCR_POLICY.md`, `GRADING_GUIDE.md` |

Full catalog: [`PHASE7_NOTES.md`](PHASE7_NOTES.md) § Spike script/markdown catalog.

---

## Git policy

| Path | Policy |
|------|--------|
| `Scripts/spike/artifacts/` | **Gitignored** — client crops, JSON, PNG (~184 MB) |
| `CURSOR_PROMPT_*.md`, `Sprint_*_Prompt.md` | **Gitignored** — ephemeral session prompts |
| `Scripts/temp_*.py` | **Gitignored** — one-off diagnostics |
| Tier-1 sources + docs above | **Committed** — indexed 2026-05-30 (Blueprint v2.44.27) |
| Azure deploy zip | **Excludes** `Scripts/spike/` per `Build-AzureDeployZip.ps1` |

---

## Production vs spike (do not confuse)

| Layer | Production (App Service) | Spike / local |
|-------|--------------------------|---------------|
| Bank Statements UI | Azure DI-only | Local Enhanced + optional hybrid CV |
| Check payee source | DI `prebuilt-check.us` | CV Read + `App/payee_extractor` profiles |
| Default check leg | Document Intelligence | `strict` or `hybrid_cv` when CV creds set |

Next operational work after hygiene: **Gate A3 smoke evidence** (production) then **G1 App wiring** per `POST_SPIKE_INTEGRATION_PLAN.md`.
