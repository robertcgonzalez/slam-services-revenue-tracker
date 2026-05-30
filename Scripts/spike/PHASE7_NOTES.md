# Phase 7 — Operational & Rollout Notes (Spike Closure)

**Date**: 2026-05-27  
**Status**: COMPLETE  
**Entry point**: [`README.md`](README.md) in this folder (canonical index since v2.44.27).

## Purpose

Close the Azure CV Read hybrid spike with:

1. **Post-Spike Integration Plan** — gates, sprint steps, runbook, rollout.
2. **Final spike report** — repo root for stakeholders.
3. **Spike file catalog** — what each script does and what to archive after integration.

**No App code changes in Phase 7.**

---

## Primary documents (read in this order)

| Order | Document |
|-------|----------|
| 1 | `Spike-Report-Computer-Vision-Check-Leg-20260527.md` — executive summary |
| 2 | `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` — how to integrate safely |
| 3 | `Spike-Plan-Microsoft-Document-Intelligence-PnL.md` — original plan + success criteria (all checked) |

---

## Spike script catalog

| Script | Phase | Role | After integration |
|--------|-------|------|-------------------|
| `baseline_current_ocr.py` | 0 | Strict Local Enhanced baseline + artifacts | Keep for regression |
| `diagnose_check_deposit_cropper.py` | 1 | **SSOT** harness for geometry/dedup/overlays | Keep — cropper tuning |
| `phase1_cv_read_harness.py` | 1 | CV Read + classify + payee extract on crops | Keep; thin-wraps `payee_extractor/` |
| `payee_extractor/` | E0–E3 | Bank-aware payee engine, profiles, check rules | Extract to App with hybrid module |
| `phase1_cv_read_prototype.py` | 1 | Early prototype (superseded by harness) | Archive candidate |
| `phase1_breakdown.py` | 1 | Cohort stats helper | Optional keep |
| `grade_phase1_crops.py` | 1 | Grading helper | Optional keep |
| `fast_cv_photo_processor.py` | 1 | Fast path experiments | Archive candidate |
| `_diag_photo_regions.py` | 1 | Diagnostics | Archive candidate |
| `phase5_hybrid_pipeline.py` | 5 | End-to-end hybrid orchestrator | Refactor into `App/`; keep CLI wrapper |
| `phase6_pl_smoke.py` | 6 | P&L pivot smoke | Keep for CI/regression |
| `Provision-AzureComputerVisionRead.ps1` | 0 | One-time Azure provision | Keep in `Scripts/spike/` |
| `test_fast_vs_strict.py` (repo root) | 3 | Fast vs strict cropper smoke | Keep at root or move to `Scripts/` |

---

## Spike markdown catalog

| File | Content |
|------|---------|
| `PHASE0_NOTES.md` | Baseline run log |
| `PHASE1_NOTES.md` | CV Read + visual grading TL;DR |
| `PHASE1_CROPPER_GAP_DIAGNOSIS.md` | 40 vs 56 root cause |
| `GRADING_GUIDE.md` | How to grade side-by-side sheet |
| `SCHEMA_DECISION.md` | Option A-then-B record |
| `PHASE5_HYBRID_DESIGN.md` | Architecture + future App checklist |
| `PHASE6_NOTES.md` | P&L smoke results |
| `PHASE7_NOTES.md` | This file |
| `POST_SPIKE_INTEGRATION_PLAN.md` | Integration gates + runbook |

---

## Artifacts directory (`Scripts/spike/artifacts/`)

- **Gitignored** via `artifacts/.gitignore` — never commit client crops, CSVs, or `raw_cv_responses/`.
- **Authoritative Phase 1 folder** (for re-score without Azure cost):
  `phase1_real_cv_read_harness_20260526T195813Z__rescored/`
- **Safe to delete locally** after backup: timestamped `phase5_hybrid_*`, `phase6_pl_smoke_*` except those referenced in docs.
- **Retain** for integration PR evidence: one harness dir, one phase5 bundle, one phase6 smoke report.

---

## Environment reminder

```powershell
# Copy sample → repo root .env (gitignored)
copy Scripts\spike\cv-read.env.sample .env
# Fill AZURE_CV_ENDPOINT and AZURE_CV_KEY
```

Provision: `Scripts/spike/Provision-AzureComputerVisionRead.ps1`

---

## Production state as of spike close

| Component | State |
|-----------|-------|
| `App/local_enhanced_ocr.py` | Phase 3 two-stage dedup; **strict default** |
| Bank Statements UI | **No hybrid radio** |
| Azure Function cropper | Dedup back-ported; no CV Read call yet |
| Default check leg | EasyOCR strict |

---

## Phase 7 complete — no further spike phases planned

Next work is **outside** the spike folder: integration sprint per `POST_SPIKE_INTEGRATION_PLAN.md` after owner G1 approval.
