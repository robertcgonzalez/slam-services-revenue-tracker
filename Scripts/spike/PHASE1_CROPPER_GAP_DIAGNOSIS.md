# Phase 1 Cropper Gap Diagnosis (2026-05-27)

**Context**: Before continuing the hybrid Azure CV Read spike (Spike-Plan-Microsoft-Document-Intelligence-PnL.md) past Phase 1, the 40-vs-53 cropper discrepancy on the hard test PDF had to be diagnosed and the local region-finding logic corrected or consciously scoped.

**Test PDF**: `Data/Auto_Body_Center_Jan_26_Statement.pdf` (10 pages, Traditions Bank style).

## Key Finding — Composite Raster Imaging Pages (Not 53 XObjects)

- pdfplumber image extraction on the PDF reports **only 1 large image per imaging page** (pages 5–10).
- Total large images on pages 5+: **6**.
- The "53 images + 7 deposit slips" the user counted (and the ~49 checks declared in the bank's statement summary) are **visually distinct rectangular photographic regions inside composite page rasters**.
- The bank photographed the physical checks and deposit slips, assembled them (with register text) into "statement imaging pages", and embedded those composite images into the PDF.
- There are **no 53 separate check image XObjects** that can be extracted via pdfplumber, PyMuPDF, or pdf2image at the object level.

**Implication**: The only reliable way to isolate the individual check (and deposit) photographs is exactly what the existing OpenCV-based cropper does — rasterize at high DPI (250/220), run multi-threshold contour finding + size/aspect/dedup, then (optionally) keyword-validate with EasyOCR.

## Why Phase 0 Baseline Only Produced 40 Crops

From `Scripts/spike/artifacts/baseline_20260526T202334Z/pipeline_logs.txt` and `summary.json` (v2.44.3, local Windows defaults):

```
[INFO] Check cropper scanning 10 page(s) at 250 DPI.
[INFO] Check cropper page 5: 12 candidate(s).
[INFO] Check cropper page 6: 12 candidate(s).
[INFO] Check cropper page 7: 10 candidate(s).
[INFO] Check cropper page 8: 6 candidate(s).
[WARN] Hit OCR_MAX_CHECKS=40; stopping cropper.
[INFO] Check cropper extracted 40 unique check(s).
```

- Hard cap `OCR_MAX_CHECKS=40` (local default; Codespaces was 50) was hit after page 8.
- Pages 9–10 were never scanned for crops.
- On page 5 (the first imaging page, which contains the 7 deposit slips), 12 candidates passed the filters. Several were deposit slips or partials that leaked through the loose short-text + "memo"/"dollars" rule.
- Geometry (aspect 2.0–3.2, height 320–900 at 250 DPI) + keyword gate ("pay to", "order of", "memo", "dollars") + perceptual dedup + EasyOCR quality on the crops themselves dropped additional real checks.
- Result: 40 crops (P04C00–P07C39), 49 check rows in the parsed transactions, only 28 linked cleanly.

The v2.44.3 bump (30→50 in Codespaces, 40 local) was a partial fix; the deposit leakage on page 5 and the remaining misses on later pages were the next increment.

## Architectural Conclusion for the Azure CV Read Spike

**We cannot hand off the cropping/region-finding problem entirely to Azure Computer Vision Read.**

- Because the imaging pages are composite rasters, there is no "just extract the embedded check images from the PDF" shortcut.
- Sending full pages to CV Read (cheaper — 1 txn per page instead of 1 per check) does **not** eliminate the need for local (or post-CV) photo-region detection. You still have to attribute the excellent Read lines back to the correct visual check rectangle on the page (via contours, pdfplumber bboxes, or spatial clustering of Read bounding boxes). The segmentation problem simply moves downstream.
- The spike's chosen strategy — **individual tight crops (with contrast enhancement) → CV Read on each crop** — remains the highest-accuracy path for the "Pay to the order of" payee goal. It requires a reliable local photo-region detector.
- The current OpenCV contour + keyword cropper is the correct architectural layer. It just needed:
  - The cap raised (now 60 for both environments).
  - Stronger deposit-slip rejection on the first imaging page.
  - A conscious "strict for EasyOCR path, relaxed for CV Read path" distinction.

## Fixes Applied (2026-05-27)

1. `App/local_enhanced_ocr.py`:
   - `_DEFAULT_MAX_CHECKS` harmonized at 60 (both Codespaces and local).
   - `_CROP_JUNK_KEYWORDS` extended with deposit-ticket language ("deposit ticket", "deposit slip", "depobit ticket", "cash in", "checks in", "subtotal", "for deposit").
   - Large explanatory comment block added immediately above the `_CROP_*` constants documenting the composite-raster reality and the CV Read implications.

2. `Scripts/smart_check_cropper_final_dynamic.py` (historical standalone):
   - Same deposit junk keywords added for consistency.

3. `AzureFunctions/ocr_processor/function_app.py` (the Y1 Function copy):
   - Same deposit junk keywords added.
   - Header comment references the diagnosis.
   - **Note**: the hard-coded default `OCR_MAX_CHECKS = int(os.environ.get("OCR_MAX_CHECKS", "40"))` should also be bumped to 60 (or made an App Setting) before any production hybrid lands.

4. Spike scripts (`Scripts/spike/baseline_current_ocr.py` and `phase1_cv_read_prototype.py`):
   - New `--relaxed-crop` flag on the baseline runner.
   - When set, the strict check-keyword gate is bypassed for that run only (size/aspect/dedup/junk-bank filters remain). All plausible photo regions on pages 5+ are emitted as crops for CV Read consumption.
   - Phase 1 rebaseline documentation updated to mention the flag.
   - Recommended usage for CV grading: `SLAM_LOCAL_OCR_MAX_CHECKS=60 python Scripts/spike/baseline_current_ocr.py --relaxed-crop ...`

## Recommended Commands to Produce a Fuller Artifact Set for Phase 1 Re-Grading

```powershell
# From repo root, with the project venv active
$env:SLAM_LOCAL_OCR_MAX_CHECKS = "60"

# Strict (current EasyOCR path behaviour, now with deposit rejection + higher cap)
python Scripts/spike/baseline_current_ocr.py `
    --pdf Data/Auto_Body_Center_Jan_26_Statement.pdf `
    --out-dir Scripts/spike/artifacts/baseline_v2_44_3_relaxed_strict

# Relaxed (recommended for CV Read side-by-side grading — captures deposits + weak-text checks)
python Scripts/spike/baseline_current_ocr.py `
    --pdf Data/Auto_Body_Center_Jan_26_Statement.pdf `
    --relaxed-crop `
    --out-dir Scripts/spike/artifacts/baseline_v2_44_3_relaxed_cv

# Then feed the relaxed manifest/PNGs into Phase 1
python Scripts/spike/phase1_cv_read_prototype.py `
    --baseline-dir Scripts/spike/artifacts/baseline_v2_44_3_relaxed_cv `
    --out-dir Scripts/spike/artifacts/phase1_cv_read_relaxed_$(Get-Date -UFormat %Y%m%dT%H%M%SZ)
```

Open the new `side_by_side_checks.csv` + the PNGs in `cropped_checks/` and grade visually against the actual check photographs in the PDF (never against old Grok Vision CSVs for the Payee column).

## Remaining Manual Effort After CV Read (Honest Assessment)

Even with a fuller set of ~49–53 crops + CV Read:
- Some checks will still be too low-contrast, handwritten, or damaged for perfect payee extraction.
- Deposit slips (7 on page 5) will now be captured; the CV Read + cheap text heuristic layer must label them correctly so they do not pollute the check-payee flow.
- The existing `_is_clean_payee` guard + payee rules engine + human-in-the-loop editor remain the safety net (as documented in the spike plan).

## Post-Spike Path (Updated Recommendation)

1. Keep the individual-crop strategy for the hybrid CV Read mode (it is still the accuracy winner).
2. Expose the mode behind the existing Local Enhanced OCR radio (or a new "Local Enhanced + CV Read for checks" option).
3. Use the relaxed crop path only for the CV leg; keep the strict keyword path for pure-EasyOCR fallback.
4. When the hybrid lands in the Azure Function, bump the Function's default cap and include the deposit keywords.
5. Proceed with schema cleanup + minimal P&L smoke on the improved data (Phase 2/3).

All work above was isolated under `Scripts/spike/` + minimal, well-commented changes to the three cropper copies. No production behaviour changed for the current EasyOCR path except the higher cap and better deposit rejection (both strict improvements).

**Ready for Phase 2 once a fuller crop set has been graded with CV Read.**

---

## Validation with the Diagnostic Harness (late May 2026)

After the initial diagnosis and tactical fixes (cap=60, deposit junk keywords, `--relaxed-crop` flag), a dedicated step-by-step development harness was built:

    Scripts/spike/diagnose_check_deposit_cropper.py

**Key findings from the harness on the same hard test PDF**:

- The OpenCV contour + geometry primitive was already locating the real photo rectangles correctly. Visual inspection of the debug overlays confirmed that both green ("kept") and blue ("dedup") boxes accurately framed the actual check and deposit slip images.
- The dominant remaining failure mode on this regular-grid layout was **over-aggressive deduplication**: the original 8×8 raw perceptual hash (applied across the three adaptive/global thresholds) caused the vast majority of real distinct photos to be marked as duplicates (blue), leaving only 1–3 green survivors per page even when ~12 visual photo rectangles existed per composite imaging page.
- Page 10 produced very few candidates because it is the statement reconciliation sheet (no check or deposit photographs) — not a cropper bug.
- A two-stage dedup was implemented in the harness: (1) contrast-enhanced higher-resolution perceptual hash (12×12 for diagnosis), (2) center-distance spatial non-max suppression (min ~45 px at 300 DPI, exploiting the regular 2-column grid). This recovered the expected counts:
  - Pages 5–8: 12 unique photos each
  - Page 9: 8 unique photos
  - **Total: 56** — matching the corrected ground truth of 49 checks + 7 deposit slips (all on page 5).

The new script produces:
- Rich per-page debug overlays (color-coded rectangles for size/aspect/dedup + thick bright-green "final kept" markers with "K" labels after the improved dedup).
- A full candidate manifest (every contour with exact rejection reason, brightness/variance stats, etc.).
- Final clean crops of the unique survivors (`final_kept/` folder).
- A machine-readable summary.json.

**Conclusion for the spike and production cropper work**:
The "cropper gap" was real, but the root cause was narrower than initially feared: geometry was sufficient; dedup on grid layouts with the old coarse hash was the primary killer. The diagnostic harness (`diagnose_check_deposit_cropper.py`) is now the authoritative tool for any future geometry, dedup, or classification tuning (check vs deposit_slip) on this or similar PDFs. The validated parameters (300 DPI, hash_size=12 for diagnosis, min_center_dist=45 at that DPI) and the two-stage dedup logic are ready for back-port into the three production copies and the app's bank_statements integration. The script also provides the clean foundation for the "two-stage cropper" (relaxed geometry → lightweight classifier) recommended in the main spike plan for the hybrid CV Read / Document Intelligence path.

All artifacts from the harness runs live under `Scripts/spike/artifacts/crop_diagnosis_*` (gitignored). No production files were modified during this validation pass.
