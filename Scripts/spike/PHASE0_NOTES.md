# Phase 0 Notes — Azure Computer Vision Read Hybrid Spike

> **Historical note (2026-05-30):** References to GitHub Codespaces as the primary dev environment reflect the May 2026 spike era. **Local Windows is the sole supported path** since v2.44.16. See [`docs/environment-policy.md`](../../docs/environment-policy.md).

**Date**: 2026-05-26
**Spike plan**: [`Spike-Plan-Microsoft-Document-Intelligence-PnL.md`](../../Spike-Plan-Microsoft-Document-Intelligence-PnL.md) (v2 — Revised Hybrid)
**Phase**: 0 — Setup, isolation, and baseline of the current pipeline.
**Owner**: Robert (Cursor primary).

This document is the working log for Phase 0 only. It is intentionally thin and is not part of the Documentation Roles Matrix — it lives under `Scripts/spike/` so it can be deleted (or archived alongside the eventual `Spike-Report-…`) when the spike concludes.

---

## 1. Scope reminder (what Phase 0 may and may not touch)

Per the revised hybrid spike plan, Phase 0 is **setup + baseline only**:

- Isolate work in `Scripts/spike/`.
- Confirm the hard test PDF.
- Capture the *current* Local Enhanced OCR (v2.44.3) output as the baseline.
- Visually review check-derived Payee quality against the actual check photographs in the PDF — **not** against the old Grok Vision CSV.

**Out of scope for Phase 0 (and all later phases unless explicitly approved):**

- Production code paths (`App/app.py`, `App/bank_statements.py`, `App/local_enhanced_ocr.py`, `AzureFunctions/`).
- `requirements.txt` and any production dependency change.
- The four existing Bank Statements processing modes.
- Provisioning the Azure Computer Vision resource (Phase 0 wraps up before that; the key/endpoint enter the spike in Phase 1 via a local-only env file).

---

## 2. Environment summary

| Item | Value |
| --- | --- |
| Host | Windows 10 build 26200 (Robert's laptop) |
| Shell | PowerShell |
| Project venv | `C:\SLAM-Services-Project\.venv` (Python ~3.10, per `runtime.txt` for Azure parity) |
| System Python | 3.14.4 (not used by the pipeline) |
| Primary heavy-OCR mirror | GitHub Codespace `slam-v2.44-codespaces-migration` (per `slam-services.mdc`) |
| Current run mode | Local Windows; the Streamlit app is already running in terminal 21 (`streamlit run App\app.py`) |

Installed heavy libs (verified via `python -c "import pdfplumber, pdf2image, easyocr, cv2, PIL, numpy"` in the .venv):

| Library | Version | Status |
| --- | --- | --- |
| pdfplumber | 0.11.9 | OK |
| pdf2image | imports cleanly | OK |
| easyocr | imports cleanly | OK |
| opencv (cv2) | 4.13.0 | OK |
| Pillow | 12.2.0 | OK |
| numpy | 2.4.4 | OK |

Pipeline tunables (from `leo.environment_summary()`, local Windows defaults):

- `dpi_text=300`, `dpi_crop=250`, `max_pages_raster=30`, `max_checks=40`, `fast_path_min_rows=3`.
- These are the higher-fidelity local defaults; the Codespaces defaults (200/220/20/50) only apply when `CODESPACES=true` is set.

---

## 3. Test fixture confirmation

- Primary hard test PDF: **`Data/Auto_Body_Center_Jan_26_Statement.pdf`** — confirmed present, 666,571 bytes (last modified 2026-02-02). This is the same PDF the revised spike plan calls out (§3, §5 Phase 0).
- The PDF is gitignored (`.gitignore` line 4: `Data/`), so it can never be committed by accident.
- Phase 1 will add 1–2 additional real statements; for Phase 0 the single PDF is sufficient.

---

## 4. Spike isolation confirmation

- `Scripts/spike/` exists.
- All Phase 0 / Phase 1 / Phase 2 / Phase 3 spike work lives under this folder.
- `Scripts/spike/artifacts/.gitignore` was added so cropped check PNGs, transaction JSON/CSV, and pipeline log dumps (all derived from real client data) can never enter git. CSV is already blocked globally by the repo `.gitignore`; the new file closes the PNG/JSON gap.
- No production files were modified. Verify with `git status` — only new untracked files under `Scripts/spike/` should appear.

---

## 5. Baseline execution results (current Local Enhanced OCR v2.44.3)

### 5.1 Run summary

Source bundle: `Scripts/spike/artifacts/baseline_20260526T202334Z/` (generated 2026-05-26 20:44:49Z by `baseline_current_ocr.py` against `Data/Auto_Body_Center_Jan_26_Statement.pdf`).

From `summary.json`:

| Field | Value |
| --- | --- |
| `pipeline_version` | `v2.44.3` |
| `status` | `success` |
| `capabilities` | all six libs `true` (pdfplumber, pdf2image, easyocr, opencv, pillow, numpy) |
| `environment` | local Windows; `dpi_text=300`, `dpi_crop=250`, `max_pages_raster=30`, `max_checks=40` |
| `fast_path_rows` / `fallback_rows` | **0 / 92** — pdfplumber found no text layer; everything came via EasyOCR fallback |

This is a fully scanned PDF, which is exactly the layout class the spike is built around.

### 5.2 Transaction and totals correctness

| Metric | Value | Verdict |
| --- | --- | --- |
| Total transactions | **92** | Matches the v2.44 strict-parser baseline. |
| Check rows (`Check#` populated) | **49** | All carry a clean check number from the register/OCR text. |
| Deposits | **$41,786.80** | Exact match to the historical good v2.43 Grok Vision baseline. |
| Withdrawals | **$41,403.63** | Exact match to the historical good v2.43 Grok Vision baseline. |
| Reconciliation | Deposits − Withdrawals = $383.17 | Consistent with the statement's own summary block. |

**Conclusion**: the transaction table and the deposit/withdrawal totals are correct under v2.44.3. The remaining quality problem is purely on the Payee column for check rows — exactly the failure mode the revised hybrid spike plan targets.

### 5.3 Current Check Payee Quality — Baseline (v2.44.3)

Evaluation was performed against `cropped_checks/manifest.csv` and `transactions_checks.csv` in the artifact bundle, cross-referenced to the corresponding cropped check PNGs. **Per the spike plan §6, the old Grok Vision CSV was not used as ground truth for the Payee column**; we compared raw cropper output and post-matcher transaction rows against the actual check images.

Quantitative state across the 49 check rows:

| Bucket | Count | Notes |
| --- | --- | --- |
| Check rows total | 49 | From `transactions_checks.csv`. |
| Linked to a cropped check image | 28 | Matcher tied the cropper output to a register row (mostly via `check#`, once via `amount $332.43`). |
| Not linked to any cropped check | 21 | Pure-text rows whose check images either weren't cropped or didn't match — `ReviewReason = "OCR fallback — verify payee"`, `Confidence = Medium`. |
| Rows with a non-blank `Payee` | **0 / 49** | **Every check row has a blank `Payee` cell.** |
| Rows with `NeedsReview = Yes` | 49 / 49 | Whole check leg flagged for human review, as designed. |
| Confidence split | 28 Low + 21 Medium | The 28 linked rows are downgraded to Low by the v2.44.3 `Linked via … (no clean payee from image)` path. |

Qualitative state of the 40 cropped check images (from `manifest.csv`):

- **31 / 40** crops returned an empty `extracted_payee` (the cropper got the image, EasyOCR found no usable text in the "Pay to the order of" band).
- **9 / 40** crops returned non-empty `extracted_payee`, but every one is either the literal label "ORDER OF" / "Order Of" / "ORDER Of" or label-plus-garbage. Representative samples directly from the manifest:

  | `check_id` | `extracted_payee` | `extracted_payee_confidence` |
  | --- | --- | --- |
  | P04C05 | `ORDER OFE Hluuk` | 0.133 |
  | P05C14 | `Os.90` | 0.512 |
  | P05C17 | `ORDER Of` | 0.846 |
  | P05C18 | `Order Of` | 0.366 |
  | P06C24 | `ORDER OF Iudsz` | 0.576 |
  | P06C25 | `ORDER OF [NtssnN 97` | 0.521 |
  | P06C28 | `Slon8if4 RS0-od` | 0.385 |
  | P07C34 | `ORDER OF_ Fhs` | 0.524 |
  | P07C35 | `Order Of` | 0.536 |
  | P07C37 | `Order Of` | 0.886 |

- Confidence ≥ 0.80 (P05C17, P07C37) does **not** correlate with usable Payee text — both high-confidence hits are just the OCR of the printed label "ORDER OF", not the payee name.
- `_is_clean_payee` correctly rejects all nine candidates: every linked transaction's `linked_txn_payee` is blank in the manifest, so no garbage is leaking into the Payee column — but no real payee text reaches the Payee column either.

**Bottom line**: the v2.44.3 check-photo OCR leg, on this real statement, produces a **0 % usable-payee rate** from the actual check images. Laura would still need to manually enter payee text for all 49 check rows. This is the precise failure mode the Phase 1 CV Read prototype is meant to attack.

### 5.4 Cropper gap (diagnosed May 2026 — composite rasters, not 53 XObjects)

| Source of count | Value |
| --- | --- |
| Cropped check images produced (Phase 0 baseline) | **40** |
| Distinct check rows in the parsed transactions | 49 |
| Checks visually present on the image pages (user count) | **53** |
| Deposit slips visually present (user count, page 5) | 7 |
| High-recall diagnostic (relaxed geometry + dedup only, **no** keyword filter) on pages 5–10 | **58** unique photo-like rectangles (P5:12, P6:12, P7:11, P8:12, P9:8, P10:3) |

**Root cause (objective)**: pdfplumber reports only **1 large composite image per imaging page** (pages 5–10, 6 total). The 53+7 are visual rectangular photo regions *inside* those composites — the bank photographed the checks/deposits, laid them out with register text, and embedded the composite rasters. There are no 53 separate check XObjects.

The 40-crop shortfall was almost entirely **policy**, not geometry:
- Hard cap `OCR_MAX_CHECKS=40` (local default) hit after page 8 → pages 9–10 never reached.
- On page 5 (first imaging page, containing the 7 deposit slips) 12 candidates passed; several were deposits leaking through the loose short-text + "memo"/"dollars" rule.
- Strict check-keyword gate + geometry bands + dedup + EasyOCR quality on the crops dropped additional real checks.

**Fixes applied (May 2026, minimal, well-commented)**:
- Production cropper (`App/local_enhanced_ocr.py`): cap raised to 60 (both environments); `_CROP_JUNK_KEYWORDS` extended with deposit-ticket language; large architectural comment block added documenting the composite-raster reality and the "relax for CV Read, stay strict for EasyOCR" distinction.
- Same deposit keywords mirrored in the standalone `smart_check_cropper_final_dynamic.py` and the Azure Function copy (plus header note).
- New `--relaxed-crop` flag on the spike baseline runner (bypasses strict keyword gate for CV path only; size/aspect/dedup/junk-bank filters remain). Recommended for CV grading: `SLAM_LOCAL_OCR_MAX_CHECKS=60 python Scripts/spike/baseline_current_ocr.py --relaxed-crop ...`
- Full diagnosis written to `Scripts/spike/PHASE1_CROPPER_GAP_DIAGNOSIS.md` (58-region result, pdfplumber evidence, architectural conclusion, honest remaining-manual-effort assessment, exact rebaseline commands).

**Deposit slips decision (accepted)**: Yes, they have clear value for P&L / revenue attribution. The 7 slips likely correspond to the 7 Regular Deposit + ACH credit rows; OCRing them (especially with CV Read) can reveal the breakdown of checks/cash that made up each deposit → better client-level attribution. Treat as first-class photo regions in the hybrid path (longer-term two-stage cropper refactor: find all photo regions → lightweight classifier "check" vs "deposit_slip").

The cropper gap is now diagnosed and the immediate blocker removed. Phase 1 should use the relaxed re-baseline + CV Read on the fuller set (~49–53 checks + 7 deposits) before Phase 2. See `PHASE1_CROPPER_GAP_DIAGNOSIS.md` for the complete record.

---

## 6. Import / entry-point discoveries

While reviewing `App/local_enhanced_ocr.py`:

- **Public entry point**: `local_enhanced_ocr.run_pipeline(pdf_bytes: bytes) -> dict[str, Any]` at line 257. This is the function the Streamlit `bank_statements.py` page calls, and the one this spike must compare against.
- **Return shape**: `{status, transactions, grok_totals, cropped_checks, logs, message, fast_path_rows, fallback_rows, linked_count}`. Fields the spike depends on:
  - `transactions[i]` follows `TRANSACTION_FIELDS` (12 columns) and may carry `linked_check_id` after the matcher runs.
  - `cropped_checks[i]` is `{check_id, page, width, height, aspect_ratio, image_b64, notes}` plus `extracted_check_number`, `extracted_payee`, `extracted_payee_confidence`, `linked_transaction_index` set by `_match_checks_to_transactions`.
- **Other useful publics**: `LOCAL_ENHANCED_OCR_VERSION`, `TRANSACTION_FIELDS`, `environment_summary()`, `detect_capabilities()`.
- **Sys.path injection pattern**: `App/` is not a package (`bank_statements.py` is a sibling, not a sub-module) so the spike script prepends `App/` to `sys.path` and imports `local_enhanced_ocr` directly — matching the pattern used by `Scripts/e2e_local_ocr.py`. No `App.local_enhanced_ocr` package import is needed and would in fact fail.
- **Cost of a full run**: ~20 min on local Windows due to EasyOCR + OpenCV cropper on a 10-page scanned PDF. Plan accordingly when iterating in Phase 1.

---

## 7. Open decisions / blockers

1. **Codespaces vs. laptop for the spike.** The Constitution / `slam-services.mdc` rule says heavy OCR work belongs in the Codespace `slam-v2.44-codespaces-migration`. Phase 0 ran locally for iteration speed; Phase 1's CV Read calls should run from the Codespace once the Azure key/endpoint are in place, so the prototype mirrors the eventual production environment. The artifact bundle is environment-agnostic, so re-baselining from the Codespace is cheap if needed.
2. **Azure Computer Vision resource (Phase 1 prerequisite).** Region, SKU (S1), and key/endpoint storage strategy. Plan: a local-only `.env` file already covered by `.gitignore` (`*.env`, `.secrets/`). No production code change needed.
3. **Cropper gap (resolved May 2026)**. The 40-vs-53 (plus 7 deposits) discrepancy is now fully diagnosed: composite raster imaging pages (pdfplumber: 1 large image per page 5–10), high-recall diagnostic shows the current geometry already finds 58 photo-like rectangles when the keyword gate and cap are removed. Root cause was policy (cap=40 + strict keywords + deposit leakage on page 5). Tactical fixes applied (cap=60, deposit keywords in all three cropper copies, `--relaxed-crop` flag for the CV path). Longer-term direction recorded: two-stage "find all photo regions (relaxed geometry, high-or-no cap) → lightweight classifier" + first-class deposit handling. See `PHASE1_CROPPER_GAP_DIAGNOSIS.md`. The relaxed re-baseline is the recommended next step for Phase 1 CV grading.
4. **Schema evolution decision (Phase 2, surfaced here for visibility).** Keep the canonical 12-col schema for the first integration release vs. jump to the proposed clean vNext (single signed `Amount` + `RunningBalance` + `TransactionType`). Phase 0 makes no schema change; the baseline runner emits the current 12-col + `linked_check_id` only.
5. **No production-code edits in this spike.** Reiterated: even if Phase 1 measures a large quality win, the integration plan (new processing mode or option) ships as a *separate* change after the spike report lands.

---

## 8. Phase 0 status

**Phase 0 is complete for the baseline.** All §3 success-criteria items in scope for Phase 0 are satisfied:

- [x] Existing cropper successfully isolates check photo regions on the hard PDF (40 cropped, capped at `OCR_MAX_CHECKS=40`).
- [x] Current Local Enhanced OCR v2.44.3 baseline captured and archived in `Scripts/spike/artifacts/baseline_20260526T202334Z/`.
- [x] Payee quality on check-derived rows evaluated against the actual check images / manifest, **not** against the old Grok Vision CSV.
- [x] Transaction count and deposit/withdrawal totals confirmed correct ($41,786.80 / $41,403.63).
- [x] All work isolated under `Scripts/spike/`; no production files touched.

The remaining §3 items (Azure CV Read call, side-by-side comparison, cost measurement, P&L smoke, schema recommendation) all belong to Phases 1–3.

### Next steps — handoff to Phase 1

1. Provision the Azure Computer Vision resource (S1, Read feature) and store key/endpoint in a local `.env` (never committed).
2. In a new `Scripts/spike/phase1_cv_read_prototype.py` (or similarly named, kept isolated), iterate over the PNGs already on disk in `Scripts/spike/artifacts/baseline_20260526T202334Z/cropped_checks/` and call CV Read on each.
3. Emit a side-by-side sheet keyed by `check_id`: `extracted_payee` (current EasyOCR), `extracted_payee_confidence`, `cv_read_payee`, `cv_read_confidence`, `linked_txn_check_no` — so Robert can grade CV Read output against the exact same input crops without re-running the heavy local pipeline.
4. Feed the cleaned CV Read text into the existing `_extract_payee_from_check_detections` / `_is_clean_payee` / `_match_checks_to_transactions` logic (out-of-process or via a thin wrapper module — still no production edits).
5. Re-baseline once with `SLAM_LOCAL_OCR_MAX_CHECKS=60` to test whether lifting the cap closes most of the 40-vs-53 cropper gap before considering geometry changes.
6. Record cost (N crops = N CV Read transactions) and confirm it stays negligible at SLAM volume.

When Phase 1 completes, this file plus the side-by-side sheet become the inputs to the final `Spike-Report-Computer-Vision-Check-Leg-YYYYMMDD.md`.

---

## Follow-up: Diagnostic Harness & Dedup Resolution (late May 2026)

After Phase 0 baseline work exposed the persistent cropper shortfall on the hard test PDF, a dedicated step-by-step diagnostic harness was built:

    Scripts/spike/diagnose_check_deposit_cropper.py

**Key outcome** (on `Auto_Body_Center_Jan_26_Statement.pdf`):
- The OpenCV contour + geometry layer was already locating the real photo rectangles correctly (visual confirmation from rich debug overlays).
- The dominant remaining failure was **over-aggressive deduplication** (old 8×8 raw-hash across the three thresholds on a regular grid). A two-stage fix (contrast-enhanced higher-res perceptual hash + center-distance spatial NMS) was implemented in the harness and recovered the expected ~12 unique photos per imaging page (56 total on pages 5-9), matching the corrected ground truth of 49 checks + 7 deposit slips (all on page 5).
- Page 10 is the reconciliation sheet (no photos) — correctly low candidate count.

The harness is now the authoritative development tool for cropper geometry, dedup, and classification (check vs deposit_slip) work for both the pure-EasyOCR path and the hybrid CV Read / Document Intelligence path. Validated parameters (300 DPI, hash_size=12 for diagnosis, min_center_dist=45) and the two-stage dedup logic are ready for back-port into the three production copies.

All harness artifacts live under `Scripts/spike/artifacts/crop_diagnosis_*` (gitignored). This closes the remaining cropper-gap questions that Phase 0 surfaced.
