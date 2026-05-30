# QCR B5 Validation Report — Third Bank PDF

**Date:** 2026-05-27  
**PDF:** `Data/QCR 2026-04.pdf` (Quality Choice Roofing LLC, April 2026, First Metro Bank)  
**Artifacts:** `artifacts/crop_diagnosis_qcr_202604_b5/`, `artifacts/phase1_qcr_202604_b5/`, `artifacts/phase1_qcr_202604_b5__rescored_regions/`

---

## Executive summary

The mature spike pipeline was run on the third real client PDF. **26 photo-leg crops** (16 checks, 10 deposits) were extracted from **pages 9–10 only**; pages 5–8 yielded zero crops at default geometry. CV Read succeeded on all 26 images. With the **`regions` profile** (zero-cost rescore), human-equivalent grading on checks shows **5 full wins, 7 light fixes, 4 material wrong payees** — far below HCC’s **50/50** after rules. Deposit classification is **10/10**. Traditions smoke tests remain green. **B5 “third bank tested” is satisfied; B5 “ready for all-clients default-on” is not.**

---

## Comparison to HCC baseline

| Metric | HCC E1 (Regions, 50 crops) | QCR B5 (First Metro, 16 checks graded) |
|--------|---------------------------|----------------------------------------|
| Human `c` / `w` | 46 / 4 → 0 `w` after rules | 5 / 4 (`w` remaining) |
| Engine vs human | 50/50 (`full_human`) | 12/16 usable (c+s+p); 5/16 strict `c` |
| Cropper coverage | Pages 5–9 tuned | **Pages 9–10 only** (gap on 5–8) |
| Profile | `regions.yaml` + 6 check rules | `regions.yaml`, **0** QCR-specific rules |
| Deposits | 7/7 classified | 10/10 classified |

---

## B5 recommendation (numbered)

1. **Third PDF requirement (process):** **Met** — real third client PDF processed with documented evidence and grading summary.
2. **All-clients default-on hybrid:** **Not cleared** — cropper coverage + payee accuracy gap vs HCC.
3. **G1 sprint:** **Proceed** Traditions-first + HCC/Regions pilot per existing handoff; **do not** enable default-on hybrid for all clients.
4. **Optional follow-up:** First Metro / QCR pilot **after** (a) cropper finds imaging pages 5–8 or auto-detects imaging range, (b) payer-header penalty in profile (see FM-7), (c) Laura spot-check on 4 `w` crops in `qcr_b5_human_grades_20260527.csv`.
5. **No new check rules added** in this spike (validation-only per prompt).

---

## Artifact paths

| Artifact | Path |
|----------|------|
| Grading summary (template-filled) | `Documents/g3_third_pdf_grading_qcr_202604_b5.md` |
| Human grades CSV | `Scripts/spike/artifacts/qcr_b5_human_grades_20260527.csv` |
| Phase 1 (generic, Azure) | `Scripts/spike/artifacts/phase1_qcr_202604_b5/` |
| Phase 1 rescore (`regions`) | `Scripts/spike/artifacts/phase1_qcr_202604_b5__rescored_regions/` |
| Crop harness | `Scripts/spike/artifacts/crop_diagnosis_qcr_202604_b5/` |
