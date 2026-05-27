# Spike Plan: Azure Computer Vision Read for Check Payee Extraction (Hybrid) + Schema + P&L (v2 – Revised)

**Date**: 2026-05-27  
**Owner**: Robert (Cursor primary, Grok advisory)  
**Status**: **SPIKE COMPLETE (Phases 0–7, 2026-05-27)** on the hard test PDF (`Data/Auto_Body_Center_Jan_26_Statement.pdf`). CV Read hybrid validated (56/56, 73.2 % vs 8.9 % EasyOCR, 49+7 classified, ~51 % heavy-manual reduction). Production cropper back-port done (Phase 3). Schema A-then-B recorded. Spike prototype (`phase5_hybrid_pipeline.py`), P&L smoke (`phase6_pl_smoke.py`), and post-spike integration plan delivered. **Live App hybrid wiring not started** — requires explicit owner approval per `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md`. Final report: `Spike-Report-Computer-Vision-Check-Leg-20260527.md`.  
**Timebox**: 3–4 working days (focused spike)  
**Primary Environment**: GitHub Codespace `slam-v2.44-codespaces-migration` (or local Windows with Azure keys)  
**Key Clarification**: Current register/table parsing scripts are now considered strong. The remaining critical failure is reliable payee extraction from the actual photographic images of physical checks. This spike surgically targets that Achilles heel using Azure Computer Vision Read while preserving the existing core logic.

---

## Execution Summary (2026-05-27)

**Phases 0 + 1 are complete on the hard test PDF (`Data/Auto_Body_Center_Jan_26_Statement.pdf`).** A real Azure Computer Vision Read pass (F0 free tier) was executed on the 56 clean crops produced by the diagnostic harness, EasyOCR was run side-by-side on the same images for honest comparison, the side-by-side sheet was visually graded against the actual check photographs, and the cohort split was recorded.

**Headline numbers**:

- **CV Read calls succeeded**: 56 / 56 (100 %).
- **Classifier output**: **49 checks + 7 deposit slips** — exact match to the corrected ground truth (all 7 deposits on page 5).
- **Clean payees (post courtesy-amount filter)**: **41 / 56 = 73.2 %** from CV Read vs **5 / 56 = 8.9 %** from EasyOCR on the same crops — **~7× quality improvement** on the check-photo leg.
- **Visual grading on the actual check photographs (49 checks)**:
  - **11 full wins** — clean, immediately usable payee, zero or near-zero editing.
  - **14 light spelling fixes** — core business name correct, 1–4 character cleanup (e.g. "Hyunden" → "Hyundai", "Cluto Sync" → "Auto Sync", "Sheroin Williams" → "Sherwin Williams"). Largely handled automatically by the existing payee rules engine + data_editor.
  - **24 still need heavy manual work** — CV produced clearly incorrect text, boilerplate, or nothing usable. **Down from 49 (all manual today). ~51 % reduction in heavy manual payee toil on this statement.**
- **Deposit slips**: 7 / 7 correctly classified as `deposit_slip`. Full body text captured in `raw_cv_responses/` — first-class data for credit-side P&L attribution.
- **Cost**: **$0.00** (F0 free tier). Equivalent S1 G2 first-tier price for 56 calls would be **$0.084**. Negligible at SLAM volume (~$0.50–1.00 / month at realistic 300–400 photos/month).
- **Wall time**: ~3 min cropper harness (300 DPI, pages 5–9) + ~10.5 min CV Read at the F0 20-calls/min cap (with EasyOCR side-by-side).
- **Harness validation**: The diagnostic harness (`Scripts/spike/diagnose_check_deposit_cropper.py`) correctly recovered the expected 12 / 12 / 12 / 12 / 8 photos on pages 5–9 = **56 total**, matching the corrected ground truth. The two-stage dedup (contrast-enhanced higher-res perceptual hash + center-distance spatial NMS) is the validated fix for the over-aggressive raw-hash dedup that produced the original 40-vs-53 gap.

**Authoritative artifacts** (the rescored folder is the recommended primary input for grading and downstream re-scoring):

```
Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored/
├── side_by_side_harness.csv          ← honest grading sheet (41 / 56 clean post filter)
├── summary_phase1_harness.json       ← machine-readable headline numbers
├── phase1_harness_report.md          ← per-page breakdown + notable rows
└── raw_cv_responses/<crop_id>.json   ← full Read API response per crop (re-score for free)

Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z/
└── side_by_side_harness.csv          ← un-filtered baseline (50 / 56 = 89.3 %, retained for honesty)

Scripts/spike/artifacts/crop_diagnosis_20260527T001907Z/final_kept/
└── *.png                             ← the 56 raw + enhanced crops fed to CV Read
```

**Detailed log**: `Scripts/spike/PHASE1_NOTES.md` — full TL;DR, cohort breakdown table (11 / 14 / 24 / 7), reproduce commands, architectural confirmation, and follow-up notes. Cropper diagnosis: `Scripts/spike/PHASE1_CROPPER_GAP_DIAGNOSIS.md`.

**Architectural verdict (validated on real data)**: The hybrid path — **fast geometry-only cropper (no EasyOCR at detection time) + Azure CV Read on individual crops + cheap text classifier (check vs deposit_slip)** — is the correct primary architecture. The individual-crop strategy keeps the highest-accuracy payee extraction; the geometry-only detector keeps detection fast enough for daily use; the cheap text classifier makes deposit slips first-class citizens for credit-side attribution. This is Option 1 from the **Operational Latency & Architecture Options** section below — now upgraded from "recommended" to "validated".

**Status of spike work** (2026-05-27 — all spike phases complete):

| # | Item | Status |
|---|------|--------|
| 1 | Production cropper back-port (two-stage dedup) | **Done** — Phase 3 |
| 2 | Schema decision (A-then-B) | **Done** — `Scripts/spike/SCHEMA_DECISION.md` |
| 3 | Hybrid spike prototype | **Done** — `phase5_hybrid_pipeline.py`, `PHASE5_HYBRID_DESIGN.md` |
| 4 | Tiny P&L smoke | **Done** — `phase6_pl_smoke.py`, `PHASE6_NOTES.md` |
| 5 | Final spike report + rollout notes | **Done** — `Spike-Report-Computer-Vision-Check-Leg-20260527.md`, `POST_SPIKE_INTEGRATION_PLAN.md`, `PHASE7_NOTES.md` |

**Post-spike (not started)** — bounded App integration sprint; see `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` §2 gates (owner G1, second PDF, Laura UAT). EasyOCR strict path remains production default.

---

## 1. Problem Statement (Updated)

- The maximized custom OCR pipeline (v2.44.3/4) now handles **inline statement transactions** (registers and tables) reliably on both digital and scanned statements.
- The **persistent blocker** is the check leg: extracting accurate payee names from the embedded **photographic images** of physical checks that banks (e.g., Traditions) include in PDFs. The current OpenCV cropper + EasyOCR + `_is_clean_payee` guard still produces too much garbage or blanks on real data, forcing manual entry.
- **Cropper reality (diagnosed May 2026 on the hard test PDF)**: Imaging pages (starting page 5) are composite rasters — pdfplumber sees only 1 large image per page. The "53 images + 7 deposit slips" are visual rectangles *inside* those composites, not separate XObjects. Local region finding (OpenCV contours on high-DPI raster) remains required even for the Azure CV Read path. Sending full pages does not eliminate the segmentation problem; it merely moves it downstream. The individual-crop strategy (tight crops → CV Read) is retained as the highest-accuracy route for payee extraction. See `Scripts/spike/PHASE1_CROPPER_GAP_DIAGNOSIS.md` for the full 58-region high-recall diagnostic, composite-raster evidence, and the 40-vs-53 root cause (cap + keyword gate + deposit leakage on page 5).
- **Late-May 2026 diagnostic harness breakthrough** (on `Data/Auto_Body_Center_Jan_26_Statement.pdf`): The contour/geometry primitive was already locating the photos correctly (visual confirmation: boxes framed the real check/deposit images). The dominant failure mode was **over-aggressive deduplication** (old 8×8 raw-hash across the three adaptive/global thresholds on a regular grid of similar-sized photos). A new step-by-step diagnostic script (`Scripts/spike/diagnose_check_deposit_cropper.py`) was built collaboratively: high-recall geometry + rich debug overlays (color-coded rectangles) + manifest + two-stage dedup (contrast-enhanced higher-res perceptual hash + center-distance spatial NMS). On the hard test PDF it recovered the expected ~12 unique photos per imaging page (pages 5-9: 12/12/12/12/8 = 56 total), matching the corrected ground truth of 49 checks + 7 deposit slips (all on page 5). Page 10 is the reconciliation sheet (no photos). The script is now the authoritative development harness for tuning/validating the photo region finder (checks + deposits) for both the pure-EasyOCR path and the hybrid CV Read / Document Intelligence path. Validated parameters for this PDF (300 DPI, hash_size=12 for diagnosis, min_center_dist=45 at that DPI) and the two-stage dedup logic are ready for back-port into the three production cropper copies.
- We are **overdue by two weeks** on a bank statement reconciliation product that delivers usable **P&L statements** with modern filtering power (PivotTable-like) for Laura.
- Power Query / external Excel P&L work was Robert’s personal iteration — **not** the official project workflow. The goal is to produce the P&L inside the SLAM app.
- We want a **surgical hybrid**: keep the now-good register parsing in the current scripts; replace only the weak check-photo OCR with a stronger cloud service (Azure Computer Vision Read).

This is the precise next step after maximizing the OCR portion.

---

## 2. Objectives of This Spike

1. **Validate** that Azure Computer Vision Read (on individually cropped check images) delivers materially better payee extraction from real check photographs than the current EasyOCR path.
2. **Demonstrate** a clean integration: existing OpenCV cropper → CV Read → feed into the already-built `_extract_payee...`, `_is_clean_payee`, and `_match_checks_to_transactions` logic.
3. **Produce** working prototype output that improves Payee quality on the hard test PDFs while leaving the main register logic untouched.
4. **Decide** on the 12-column schema evolution (single signed `Amount` + RunningBalance + TransactionType) as a supporting decision for the P&L deliverable.
5. **Show** a minimal P&L smoke that proves the improved data (especially better Payees from checks) makes trustworthy Category/Payee rollups feasible.
6. **Output** an updated spike report + isolated prototype artifacts that let us move immediately to a low-risk integration sprint.

**Non-goals**:
- Replacing the main register/table parsing logic.
- Full production integration or changes to the four existing Bank Statements modes.
- Moving the entire pipeline to `prebuilt-bankStatement.us` (kept as optional parallel evaluation only).
- Complete P&L UI or OneDrive watcher.

---

## 3. Success Criteria

- [x] Existing cropper successfully isolates check photo regions on `Data/Auto_Body_Center_Jan_26_Statement.pdf` (56 unique photos = 49 checks + 7 deposits via the diagnostic harness; pages 5–9 = 12 / 12 / 12 / 12 / 8). [ ] 1–2 other real statements still pending — only the hard test PDF graded so far; recommended to validate on at least one more real statement before the integration sprint.
- [x] Azure Computer Vision Read called on the individual cropped check images (Python SDK). 56 / 56 calls succeeded on F0.
- [x] Quantitative/qualitative improvement in payee quality on check-derived rows vs. current EasyOCR + `_is_clean_payee` output (manual review against the actual check images in the PDF — **not** against old Grok Vision CSVs for the Payee column). **73.2 % vs 8.9 % (~7×) before grading; 11 full wins + 14 light spelling fixes + 24 still heavy manual on 49 checks after visual grading.**
- [~] Results successfully fed into the existing payee extraction + matcher logic with no breakage to the current 12-column (or chosen schema) output. **Partial: `_is_clean_payee` reused via read-only import in the harness. Full feed into `_extract_payee...` + `_match_checks_to_transactions` happens in the integration sprint (Phase 5 / post-spike).**
- [x] Clear measurement of transaction cost (N crops = N transactions) and confirmation it is negligible at expected SLAM volume. **$0.00 on F0 for 56 calls; equivalent S1 G2 = $0.084. Realistic SLAM monthly cost ≈ $0.50–1.00.**
- [x] Tiny P&L smoke (Category or Payee × Period rollup with signed Amount + basic filters) that works on the improved output. **Done — Phase 6 (`Scripts/spike/phase6_pl_smoke.py`, `Scripts/spike/PHASE6_NOTES.md`).**
- [x] Explicit schema recommendation (keep current 12-col for speed or adopt clean vNext with single signed `Amount`). **Decided A-then-B (2026-05-27):** Option A for hybrid + P&L smoke; Option B follow-on with dual-export — `Scripts/spike/SCHEMA_DECISION.md`.
- [x] Updated spike report + isolated prototype code only (no production file changes for the spike). **All work strictly under `Scripts/spike/`. Production cropper back-port is a deliberate, well-commented next step (Phase 3 of the post-Phase-1 plan).**
- [x] Honest assessment of remaining manual payee effort after the hybrid. **See `Scripts/spike/PHASE1_NOTES.md` cohort table: 11 full wins + 14 light spelling fixes (largely automated by payee rules + data_editor) + 24 still heavy manual = ~51 % reduction in heavy manual payee toil on this statement. 7 / 7 deposit slips captured for credit-side P&L attribution.**

---

## 4. Proposed Architecture (Hybrid – This Spike’s Focus)

**Keep (no change in this spike)**:
- Current core scripts for reading registers and tables (the part now considered strong).
- Existing OpenCV-based cropper geometry (or light tuning only).
- All downstream logic: payee rules engine, reconciliation banner, data_editor, “Mark as Received”, download CSV, etc.

**Add / Replace (the surgical change)**:
- On the cropped check images: call **Azure Computer Vision Read** (the Read/OCR capability) instead of (or in addition to) EasyOCR.
- Feed the Read text output into the existing `_extract_payee_from_check_detections` (or a slimmed version) + `_is_clean_payee` guard + `_match_checks_to_transactions`.
- Result: better payee names from the actual check photographs, while everything else stays identical.

**Secondary / Optional**:
- Quick parallel test of `prebuilt-bankStatement.us` on the same PDFs (mainly to compare register quality if desired). This is not the primary path.

**Billing note (from direct investigation)**:
- Azure Computer Vision Read (Group 2): ~$1.50 per 1,000 transactions (first tier).
- A “transaction” = 1 image (for single images) or 1 page (for PDFs).
- Strategy of **individually cropped photo regions** (checks + deposit slips) = N transactions (one per photo). This remains the higher-accuracy approach for the payee goal; full-page sends do not remove the need for local (or post-CV) region finding on composite raster pages (see diagnosis above).
- At realistic SLAM volume (hundreds of checks/month), cost remains negligible ($1–3/month even at aggressive usage). The `--relaxed-crop` spike flag + 60-cap now lets the CV leg see the full set (~49–53 checks + 7 deposits) for grading.

---

## 5. Revised Spike Approach (Narrower, 3–4 Days)

### Phase 0 – Setup (½ day)
- Azure resource for Computer Vision (S1 or equivalent; Read is the feature needed).
- Store key/endpoint locally (never committed).
- Isolate work in `Scripts/spike/` or a clearly named prototype file.
- Confirm the same real test PDFs.
- Baseline: run current Local Enhanced OCR v2.44.3 path and capture current payee quality on check-derived rows (visual review against the actual check photos).

### Phase 1 – Crop + Computer Vision Read Prototype (1 day)
- Use (or lightly tune) the existing cropper, or the new `--relaxed-crop` path in the spike baseline runner, to produce individual photo-region PNGs (checks + deposit slips on the first imaging page).
- For the CV Read leg: bypass the strict check-keyword gate (size/aspect/dedup/junk-bank filters remain) so every plausible region reaches the stronger model; let CV Read + cheap text heuristics label check vs deposit.
- Send each cropped image to Azure Computer Vision Read (Python SDK – `azure-cognitiveservices-vision-computervision` or unified vision package).
- Capture Read results (text lines + confidence/bounding boxes).
- Compare quality on the “Pay to the order of” area vs. current EasyOCR output.
- **Deposit slips**: Diagnosed as having clear value for P&L / revenue attribution (the 7 slips on page 5 likely correspond to the 7 Regular Deposit + ACH credit rows; OCRing them can reveal the breakdown of checks/cash that made up each deposit). Treat as first-class photo regions in the hybrid path (parallel or typed output). Longer-term: two-stage cropper (find all photo regions with relaxed geometry / high-or-no cap → lightweight classifier) in the production Local Enhanced OCR path.

### Phase 2 – Integration into Existing Payee Flow + Schema Prototypes (1 day)
- Feed Read output into the current payee extraction + cleaning + matching logic.
- Produce output in the current 12-col shape (for zero immediate breakage).
- In parallel, produce a second output using the proposed clean vNext shape (single signed `Amount`, + `RunningBalance`, + `TransactionType`).
- Re-apply payee rules post-extraction.
- Verify reconciliation banner still works.
- Measure transaction count and estimated cost.

### Phase 3 – P&L Smoke + Decision (½–1 day)
- Run the same minimal P&L rollup smoke as before on the improved data.
- Document schema recommendation (freeze current 12-col for first integration, or adopt clean vNext).
- Honest remaining manual effort assessment.
- Updated spike report.

---

## 6. Evaluation Method (Important)

- **Primary comparison**: Visual/manual review of the actual check photographs in the PDF vs. the extracted payee text (both current EasyOCR and new CV Read paths).
- Do **not** use the old Grok Vision CSVs as ground truth for the Payee column (they did not contain the check-image payees).
- Secondary: overall transaction quality, totals reconciliation, and how much manual cleanup Laura would still need.

---

## 7. Risks & Mitigations (Updated)

- CV Read quality still insufficient on very poor scans → mitigation: still have the human-in-the-loop editor + payee rules engine as safety net.
- Integration friction with existing extraction code → low risk (we are feeding better text into code that already exists).
- Cost modeling wrong → explicit measurement during spike + volume math already done.
- Desire to also improve registers later → we can still run a quick DI test in parallel if needed.

---

## 8. Output Artifacts

- Updated this plan + concise `Spike-Report-Computer-Vision-Check-Leg-YYYYMMDD.md`.
- Isolated prototype code (crop → CV Read → existing payee flow).
- Side-by-side comparison (current vs. new) on the real test statements, focused on check-derived payees.
- P&L smoke export.
- Clear schema recommendation.
- All work isolated so main app and production paths remain untouched.

---

## 9. Post-Spike Path (Validated Recommendation, 2026-05-27)

Phase 1 results (see **Execution Summary (2026-05-27)** above) confirm the check-leg quality win on real data. The post-spike path below is now the **validated** recommendation, not a hypothesis.

**Primary recommendation: fast geometry + CV Read on crops.**

1. **Back-port the harness's two-stage dedup into all three production cropper locations** (`App/local_enhanced_ocr.py`, `Scripts/smart_check_cropper_final_dynamic.py`, `AzureFunctions/ocr_processor/function_app.py`). This is a pure quality improvement for the existing EasyOCR path *and* the prerequisite for a clean hybrid integration. Keep the existing strict EasyOCR-keyword behavior available; expose the new logic via a `fast=True` (or equivalent) flag where appropriate. Reference: `Scripts/spike/diagnose_check_deposit_cropper.py` (validated parameters: 300 DPI, hash_size=12, min_center_dist=45). See `Scripts/spike/PHASE1_CROPPER_GAP_DIAGNOSIS.md` for the full diagnosis.
2. **Add a new optional Local-Enhanced-OCR mode** (or a "Local Enhanced + CV Read for checks" radio entry) that uses the fast geometry-only photo region detector on imaging pages, sends tight contrast-enhanced crops to Azure CV Read, post-classifies check vs deposit_slip from the Read text using cheap heuristics (keywords + text features), and feeds the result through the existing `_extract_payee...`, `_is_clean_payee`, and `_match_checks_to_transactions` logic with zero (or minimal) changes to those functions. Keep the current EasyOCR path 100 % untouched as fallback.
3. **Schema cleanup** — make the explicit decision (freeze current 12-col vs. adopt clean vNext: single signed `Amount` + `RunningBalance` + `TransactionType`) before or alongside the hybrid release. See the dedicated decision record (`Scripts/spike/SCHEMA_DECISION.md`).
4. **Deliver first useful P&L surface** (Category / Payee × Period with signed Amount + basic filters) on top of the improved hybrid output. Deposit-slip detail directly improves credit-side attribution (the 7 deposit slips on page 5 of the test statement classify cleanly and capture full body text).
5. **Continue PostgreSQL production path** in parallel (foundation for historical P&L).
6. **Safety net stays mandatory**: the human-in-the-loop data_editor + payee rules engine remain the floor for the 24 / 49 checks that CV Read still cannot read cleanly.

This is the lowest-risk, highest-leverage move that directly addresses the stated remaining failure mode and the overdue P&L deliverable while preserving the accuracy advantage of individual crops. The cropper gap (40 vs ~49–53 checks + 7 deposits) is now fully diagnosed *and validated as fixed* — the harness produces the expected 56-photo set on the hard test PDF, and CV Read converts that into a 7× clean-payee improvement vs EasyOCR.

---

## Operational Latency & Architecture Options (May 2026, post cropper-gap diagnosis)

The 27+ minute baseline runs exposed that the current "find photo regions" step (EasyOCR on every candidate + strict keyword gate) is not viable for real operations, even after the tactical fixes (cap=60, deposit keywords, `--relaxed-crop` flag).

**Recommended path for the hybrid CV Read mode (and production):**

1. **Fast geometry-only detector + CV Read on crops (primary recommendation)**  
   - `_find_photo_regions(..., fast=True)` does contours + size/aspect + dedup + cheap image heuristics (no EasyOCR at detection time).  
   - Send the tight contrast-enhanced crops to CV Read.  
   - Post-classify the Read results (keywords or cheap text) as "check" vs "deposit_slip".  
   - Deposits are now first-class (clear value for credit-side P&L / revenue attribution).  
   - This keeps the individual-crop accuracy advantage while making detection fast enough for daily use.

2. **Full imaging pages to CV Read + bbox attribution (cheapest at volume)**  
   - Send the composite page rasters (pages 5+) to CV Read (1 txn/page).  
   - Use the same fast contour finder (or pdfplumber layout) + Read line bboxes to group text back to visual photo rectangles.  
   - Still requires local region finding (the composite-raster reality does not go away), but eliminates the per-crop loop.

3. **Keep the current heavy local path only for the pure-EasyOCR fallback** (or make it async/background with progress in the UI). The app already has a strong human-in-the-loop editor + payee rules engine as the safety net.

The spike work (including the long runs) proved the quality direction and the architectural truth. Real operations must use one of the fast paths above. The `_find_photo_regions` helper + the minimal refactor of `_crop_checks(..., fast=...)` is the concrete first step in that direction.

**Late-May 2026 diagnostic harness (Scripts/spike/diagnose_check_deposit_cropper.py)**: A dedicated step-by-step development tool was built on the hard test PDF (`Auto_Body_Center_Jan_26_Statement.pdf`). It uses the same 3-threshold contour primitive, produces rich per-page debug overlays (color-coded rectangles + thick-green "final kept" markers), a full candidate manifest, and final clean crops. The key insight: the contour/geometry layer was already locating photos correctly (visual confirmation). The dominant failure on regular grid layouts was **over-aggressive deduplication** (old 8×8 raw-hash across thresholds). The harness implemented a two-stage fix (contrast-enhanced higher-res perceptual hash + center-distance spatial NMS) and recovered the expected ~12 unique photos per imaging page (56 total on pages 5-9), matching the corrected ground truth of 49 checks + 7 deposit slips (all on page 5). Validated parameters for this PDF (300 DPI, hash_size=12 for diagnosis, min_center_dist=45) plus the two-stage dedup logic are ready for back-port into the three production cropper copies. The script is now the authoritative harness for any future geometry/dedup/classification work on photo regions (checks + deposits) for both the EasyOCR path and the hybrid CV Read / Document Intelligence path.

## Phase 1 real-CV-Read result (2026-05-27, F0 free tier)

A full real Azure Computer Vision Read pass against the harness-fed 56 clean crops was executed on the F0 (free) tier, followed by a visual grading pass against the actual check photographs in the PDF. Headline numbers (see `Scripts/spike/PHASE1_NOTES.md` §TL;DR for the full record and the **Execution Summary (2026-05-27)** at the top of this document for the full headline block):

- 56 / 56 Read calls succeeded.
- Classifier produced exactly **49 checks + 7 deposit slips** — perfect match to ground truth (all 7 deposits on page 5).
- **41 / 56 (73.2 %) clean payee candidates** with the post-spike courtesy-amount filter (un-filtered baseline: 50 / 56 / 89.3 %; the filter removes 11 false positives where the extractor anchored on "Pay to the order of" but Read had not recognised the payee line, so the next line was the courtesy amount).
- **5 / 56 (8.9 %) clean payees from EasyOCR on the same crops** — the expected garbage baseline. CV Read is **~7× better** on the check-photo leg.
- **Visual grading on the actual check photographs (49 checks)**: **11 full wins + 14 light spelling fixes (largely automated by the existing payee rules + data_editor) + 24 still need heavy manual work**. Heavy manual entry burden for Laura on this statement is **down from 49 → 24 = ~51 % reduction** in heavy manual payee toil. The 14 light-spelling-fix rows are low-effort and largely cleaned up by the existing rules engine.
- 7 / 7 deposit slips correctly classified; full body text captured in `raw_cv_responses/` for credit-side P&L attribution.
- Cost: **$0.00 (F0)**. Equivalent S1 G2 price for 56 calls: $0.084. Confirmed negligible at SLAM volume.
- Wall time: 10.5 min for 56 crops (F0 20-calls/min cap + EasyOCR side-by-side).

This validates the hybrid path (fast geometry-only cropper + CV Read on individual crops + cheap text classifier) called out as Option 1 in the **Operational Latency & Architecture Options** section.

**Spike closed 2026-05-27.** Next move is the **integration sprint** only after gates in `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` — not automatic.

---

## 10. Phase 7 — Operational closure (2026-05-27)

| Deliverable | Location |
|-------------|----------|
| Final spike report | `Spike-Report-Computer-Vision-Check-Leg-20260527.md` |
| Post-spike integration plan + runbook | `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` |
| Spike file catalog & archival notes | `Scripts/spike/PHASE7_NOTES.md` |

**Explicit**: No `App/` hybrid wiring during the spike. Phase 3 cropper dedup is in production code; CV Read remains opt-in future work.

(End of Revised Hybrid Spike Plan v2)
