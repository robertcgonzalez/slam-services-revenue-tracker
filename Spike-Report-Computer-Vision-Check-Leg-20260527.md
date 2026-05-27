# Spike Report: Azure Computer Vision Read — Check Payee Hybrid Leg

**Date**: 2026-05-27  
**Owner**: Robert  
**Status**: **SPIKE COMPLETE** (Phases 0–7)  
**Plan**: `Spike-Plan-Microsoft-Document-Intelligence-PnL.md`  
**Integration**: Deferred — see `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md`

---

## Executive summary

The spike validated a **surgical hybrid** for bank statements: keep the strong register/table parser; replace only the **check-photo OCR leg** with **fast geometry cropping + Azure Computer Vision Read** on individual crops.

On the hard test PDF (`Data/Auto_Body_Center_Jan_26_Statement.pdf`):

- **56/56** CV Read calls succeeded; **49 checks + 7 deposit slips** classified correctly.
- **73.2%** clean payee candidates from CV Read vs **8.9%** from EasyOCR on the same crops (~**7×** improvement on the photo leg).
- After visual grading of 49 checks: **11** full wins, **14** light spelling fixes, **24** still need heavy manual work — **~51% reduction** in heavy manual payee toil vs today.
- **Cost**: $0 on F0; ~**$0.084** equivalent on S1 for 56 crops; negligible at SLAM monthly volume.
- **Schema**: Option **A-then-B** — 12-column freeze for first integration; vNext later.
- **Production cropper** two-stage dedup back-ported (Phase 3); **hybrid pipeline and P&L smoke** remain under `Scripts/spike/` only.

**Recommendation**: Proceed to a **bounded integration sprint** only after explicit owner approval, **E2 extractor gate sign-off** (Regions profile + Laura HCC spot-check), and Traditions Laura UAT. Do **not** change the live app default until UAT. Payee extractor evolution (post-G2) is tracked in **`Scripts/spike/EXTRACTOR_EVOLUTION_DESIGN.md`** — E1 `--rescore` lifted HCC rubric-assist full wins **0→31**, heavy manual **28→19**.

---

## Extractor evolution (post-G2 addendum)

Second PDF (HCC / Regions) proved the cropper + CV Read stack generalizes but **payee line selection** did not. Spike follow-up **`payee_extractor/`** (E0–E3):

| PDF | Full wins (rubric-assist) | Heavy manual |
|-----|---------------------------|--------------|
| HCC baseline | 0 | 28 |
| HCC after E1 `--rescore` | **31** | **19** |
| Traditions (maintain) | **≥15** | no regression on graded `correct` rows |

Detail: `Scripts/spike/E1_E2_STATUS.md`, `Documents/g2_hcc_202604.md` §E1 Hardening Results.

---

## Problem (recap)

Register parsing is now reliable on scanned Traditions-style statements. The remaining failure mode is **payee extraction from embedded check photographs** — EasyOCR on cropped regions produces garbage or blanks, forcing manual entry and blocking trustworthy Category/Payee P&L rollups.

Composite raster pages (one image per page) require local region finding; full-page CV Read does not remove segmentation.

---

## Approach tested

1. **Diagnostic harness** (`diagnose_check_deposit_cropper.py`) — two-stage dedup (enhanced perceptual hash + spatial NMS) recovers **56** photos on pages 5–9.
2. **Azure CV Read** per crop (`phase1_cv_read_harness.py`).
3. **Cheap classifier** — check vs `deposit_slip` from Read text.
4. **Existing matcher** — `_match_checks_to_transactions` + `_is_clean_payee` (read-only imports in spike).
5. **Phase 5 orchestrator** — baseline register + hybrid photo leg → `transactions_hybrid.csv` + `deposit_slips.json`.
6. **Phase 6** — `build_statement_pivot()` smoke on hybrid output.

---

## Key metrics

| Metric | Baseline (EasyOCR on crops) | CV Read hybrid |
|--------|----------------------------|----------------|
| Clean payees (automated heuristic) | 5/56 (8.9%) | 41/56 (73.2%) post filter |
| Visual grading (49 checks) | 49 heavy manual | 11 + 14 + 24 |
| Deposit slips | Often missed / junk | 7/7 classified, full body text |
| Register transactions | 92 rows | 92 rows (unchanged) |
| Matcher-linked payee improvements | — | 14/49 vs baseline CSV |

---

## Deliverables (artifact index)

| Artifact | Path |
|----------|------|
| Phase 1 harness (rescored) | `Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored/` |
| Harness crops | `Scripts/spike/artifacts/crop_diagnosis_20260527T001907Z/final_kept/` |
| Hybrid sample run | `Scripts/spike/artifacts/phase5_hybrid_reuse_test/` |
| P&L smoke sample | `Scripts/spike/artifacts/phase6_pl_smoke_latest/` |
| Schema decision | `Scripts/spike/SCHEMA_DECISION.md` |
| Integration plan | `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` |
| Extractor evolution design | `Scripts/spike/EXTRACTOR_EVOLUTION_DESIGN.md` |
| E1/E2 status (measured) | `Scripts/spike/E1_E2_STATUS.md` |
| Spike file catalog | `Scripts/spike/PHASE7_NOTES.md` |

---

## Risks (honest)

| Risk | Status |
|------|--------|
| ~24/49 checks still wrong after CV | Accepted — editor + payee rules remain mandatory |
| Single PDF graded | Mitigate with G2 second statement before prod |
| F0 rate limits | Use S1 for production batches |
| Payee not written to all register rows | Integration sprint must widen write-back policy |
| Deposit attribution without new columns | Sidecar JSON + UI expander (Option A) |

---

## Non-goals (respected)

- No Bank Statements UI changes during spike.
- No `run_pipeline` hybrid branch in production.
- No Option B schema in spike.
- No commit of client PDFs, crops, keys, or CSVs.

---

## Next steps (post-spike)

1. Owner **G1** — approve integration sprint.
2. Validate **second real statement** (G2).
3. Execute `POST_SPIKE_INTEGRATION_PLAN.md` §3 (2–4 days).
4. Laura **UAT** (G3); feature flag pilot.
5. Later: Option B schema + PostgreSQL P&L track (Blueprint §8.1).

---

## Sign-off

| Role | Action |
|------|--------|
| Visual grading | Owner **YES** (prior checkpoint) |
| Schema A-then-B | Owner **YES** (Phase 4) |
| Spike technical complete | **2026-05-27** — Phases 0–7 |
| Live integration | **Pending explicit owner approval** |
