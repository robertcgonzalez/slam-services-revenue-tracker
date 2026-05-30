# Sprint 3.3 Prompt — Azure CV as Primary Check-Photo Leg (Local Enhanced + Azure Function)

**Date**: 2026-05-28 (evening)  
**Sprint Focus**: Make Azure Computer Vision Read the **primary** mechanism for extracting payee text from cropped check/deposit images in the Local Enhanced OCR path.  
**Execution Context**: Robert testing entirely on his local Windows machine. All heavy OCR and CV work is performed locally. Codespaces is not used for this sprint.  
**Target Outcomes**:
- When `AZURE_CV_ENDPOINT` + `AZURE_CV_KEY` are present → Local Enhanced path uses Azure CV Read on cropped checks (imaging pages) for superior handwriting recognition.
- When CV creds are absent → seamless fallback to the existing EasyOCR-on-crops behavior (no breakage).
- This becomes the **default experience** for the Local Enhanced mode on the site.
- The same pattern must be easily mirrorable into the Azure Function (`AzureFunctions/ocr_processor/function_app.py`).

**You have full authority** to edit `App/`, update the Streamlit UI labels/descriptions, adjust env handling, update docs, run the hard PDF, and produce clean artifacts. The 12-column contract, reconciliation banner, payee rules, and row counts **must remain byte-identical** when CV is not used.

---

## Mandatory Reading Order (read completely before editing any code)

1. `CONSTITUTION.md` (repo root).
2. README.md — Documentation Roles Matrix + current environment policy.
3. `SLAM Services - Digital Transformation Blueprint.md` — top status + latest Change Log (v2.44.11 context from prior work).
4. `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` §3–4 (original integration vision) and §7 (regression commands).
5. `App/hybrid_cv_check_leg.py` (entire file) — this is the reusable heart:
   - `run_hybrid_check_leg(...)` — the main integration entrypoint you should call.
   - `get_cv_client()`, `call_cv_read_on_crop()`, `imaging_page_range()`, `azure_cv_configured()`.
   - `cv_lines_to_easyocr_detections()`, payee extraction + rules re-exports.
   - Cache helpers (`load_cv_cache` / `save_cv_cache`) + `SLAM_CV_CACHE_DIR`.
6. `App/local_enhanced_ocr.py` — current `run_pipeline`, `_crop_checks`, `_match_checks_to_transactions`, and the exact place after cropping where enrichment happens.
7. `App/bank_statements.py` — `run_local_enhanced_ocr_pipeline` (current signature + the call to `run_pipeline` that already passes `check_leg_mode` from prior work) + `hybrid_cv_status()`.
8. `App/app.py` — Bank Statements radio block (around lines 2113–2170), the call site that sets `use_local_enhanced_hybrid`, and the post-run banner logic. Note the state left by the previous 3.3 surface work.
9. `AzureFunctions/ocr_processor/function_app.py` — the parallel pipeline implementation (you will not edit it heavily this sprint, but design changes so the pattern ports cleanly).
10. `Scripts/spike/cv-read.env.sample` (current version) and `Data/Auto_Body_Center_Jan_26_Statement.pdf` (primary test artifact — 92 txns, 49 checks, pages 5–9 are the imaging range).

Skim `Documents/cursor_g1_sprint_3_3_ui_radio_wiring.md` only for "what surface already exists."

---

## Current Reality You Must Internalize

- The previous Cursor run (old conservative 3.3) added:
  - A separate radio option "🖥️ Local Enhanced + CV Read (check photos)".
  - `check_leg_mode` forwarding in `bank_statements.py`.
  - `hybrid_cv_status()` helper.
  - Metadata fields.
- However, `local_enhanced_ocr.run_pipeline` still only accepts `pdf_bytes` (no mode param) and contains **zero** Azure CV logic. Calling it with the kwarg will currently crash.
- `hybrid_cv_check_leg.py` (ported in 3.1) already contains production-grade CV Read + payee scoring + rules + cache + imaging-page scoping. Do **not** re-implement the CV client or Read polling.
- Tabular parsing (pdfplumber), cropping (two-stage dedup), matching, and 12-column output are all solid and must stay untouched.
- Robert is the only person running heavy Local Enhanced work right now and will test on a local Windows machine using a `.env` file.
- The long-term intent (per your direction) is that this CV-enhanced check leg becomes the normal behavior for the Local Enhanced path and will later be mirrored into the Azure Function for Laura's production use.
- Old conservative "feature flag + opt-in radio only for Robert" language is being retired for this sprint. CV should be the **preferred** check-photo path when creds exist.

**Prime Goal (your exact words)**:  
"App.py can read the bank statement's tabular structures, then crop the check images, then call Azure Computer Vision for the check images processing, and compile everything into the site's table."

---

## Required Changes (in priority order)

### 1. Core Integration in `App/local_enhanced_ocr.py` (the heart of the sprint)
- Update `run_pipeline(pdf_bytes, *, check_leg_mode: str | None = None)` (or use a simple internal flag/env check — prefer the cleanest approach that works with the existing `bank_statements` forwarding).
- After the existing `_crop_checks(...)` call (and before `_match_checks_to_transactions`), add logic:
  - If CV creds are present (`azure_cv_configured()` from the hybrid module), **call `run_hybrid_check_leg(cropped_checks, detections_by_id, ...)`** (pass imaging page range, optional cache dir, client_name, etc.).
  - This replaces the detections for imaging-page checks with CV-derived ones and enriches `extracted_payee` where the rules + profile scoring succeed.
  - Non-imaging pages and deposit slips keep the original EasyOCR path (per the hybrid module's design).
- When CV creds are **absent**, do **nothing** — fall straight through to the existing EasyOCR-based enrichment in the matcher. Zero behavior change.
- Return additional useful meta from the hybrid run (e.g. `cv_crops_enriched`, `hybrid_cv_used`) so the UI can surface it.
- Add clear structured logging via `log_event` and the pipeline log list ("Hybrid CV check leg active", "X crops enriched via CV", "Falling back to EasyOCR on crops (no CV creds)").
- Keep the entire strict/EasyOCR path byte-identical when no CV creds.

### 2. Call-Site & Orchestration Cleanup (`App/bank_statements.py`)
- The prior work already extended the function to accept `check_leg_mode` and call through. Evolve or simplify as needed so the default Local Enhanced path automatically prefers the CV leg when possible.
- Ensure `hybrid_cv_status()` (or a new lightweight `cv_check_leg_available()`) is accurate.
- Preserve all existing meta fields and add any new ones the UI needs.
- Graceful degradation must be perfect: missing SDK, bad creds, rate limits, or cache misses must never break the run.

### 3. Streamlit UI Evolution (`App/app.py`)
- Evolve the radio / labels so that **Local Enhanced OCR** (the main Robert dev toggle) now reflects the new primary behavior:
  - Update the main "🖥️ Local Enhanced OCR" label and help text to say it uses Azure CV Read on check photos **when credentials are configured**, otherwise falls back to EasyOCR.
  - Remove or de-emphasize the separate "Local Enhanced + CV Read" radio that the prior 3.3 run created (or repurpose it cleanly). The goal is that CV becomes the normal/default experience for this mode when creds exist.
- Show a clear, non-alarming info banner when the CV leg is active (mention imaging pages, that register totals are unchanged, and that this is higher-quality payee extraction for checks).
- Show a helpful note when CV creds are missing (so the user knows why it's using EasyOCR).
- Update the sidebar "System status" / Local Enhanced caption to reflect CV capability.
- Keep Lightweight Parser and Azure OCR (Function) paths completely unchanged for now.

### 4. Environment & Configuration
- Ensure `Scripts/spike/cv-read.env.sample` is excellent for local Windows testing (clear comments, cache example, imaging page defaults for Traditions).
- The four key vars remain:
  - `AZURE_CV_ENDPOINT`
  - `AZURE_CV_KEY`
  - `SLAM_IMAGING_FIRST_PAGE` (default 5)
  - `SLAM_IMAGING_LAST_PAGE` (optional)
  - `SLAM_CV_CACHE_DIR` (strongly recommended for dev — zero cost, zero rate limits)
  - `SLAM_CLIENT_NAME` (helps bank profile selection)
- No change to production App Service settings yet.

### 5. Documentation & Artifacts (do not skip)
- Update the help text in the radio and any banners to be accurate and confident.
- Lightly update `README.md` and `docs/local-development.md` (one short paragraph + env var table entry is enough).
- Produce a strong completion note: `Documents/cursor_g1_sprint_3_3_cv_primary_check_leg.md` (include before/after behavior on the hard PDF, commands run, metrics on payee quality improvement if measurable, and explicit note that this is now the default direction for Local Enhanced and is designed to port to the Function).
- Add a concise, honest Blueprint Change Log entry (v2.44.12 or next).
- Update the previous thin `cursor_g1_sprint_3_3_ui_radio_wiring.md` note or supersede it.

### 6. Azure Function Mirroring Path (design for it)
- Do not do a full port in this sprint, but:
  - Keep all new logic inside or directly callable from `hybrid_cv_check_leg.py`.
  - After cropping in the Function, the same `run_hybrid_check_leg(...)` call pattern should work (the Function will need the `azure-cognitiveservices-vision-computervision` package + the two env vars).
  - Note any small differences (e.g. how the Function receives client_name or page text) in the completion note so the mirror sprint is trivial.

---

## Verification (execute in this order)

**Pre-flight**
- Clean git state or explicit note of changes.
- Read all 10 mandatory documents.
- Have a `.env` with CV creds (or a populated `SLAM_CV_CACHE_DIR`) ready for the hard PDF.

**Core regressions (must stay perfect)**
- `python Scripts/test_local_ocr_regression.py` → 92 transactions, exact deposit/withdrawal totals, 49 checks on `Auto_Body_Center_Jan_26_Statement.pdf`.
- `python test_fast_vs_strict.py` (note: this test currently fails for pre-existing `_find_photo_regions` reasons — do not let it block; document the gap).
- Streamlit Bank Statements → Local Enhanced on the hard PDF with **no CV creds** in env → behavior and output identical to before this sprint.

**CV primary path (the new win)**
- With CV creds or a good cache dir + `SLAM_IMAGING_FIRST_PAGE=5` (and last=9 for the test PDF):
  - Run Local Enhanced on the hard PDF.
  - Confirm: same row count (92), same totals, reconciliation banner green.
  - Confirm: higher `linked_count` and visibly better `Payee` values on check rows (spot-check at least 8–10).
  - Logs clearly show CV was used and how many crops were enriched.
  - `cv_crops_enriched` (or equivalent) surfaces in the UI banner.
- Cache-only run (no live Azure calls) must succeed and produce the enriched payees.
- Missing creds → clean fallback log + normal EasyOCR behavior, no crash.

**UI / UX**
- Only one primary "Local Enhanced OCR" choice (or the CV version is the clear default when available).
- Banners are accurate and non-scary.
- The mode is the default selection when the user has the right env vars.

**Hygiene & safety**
- `ruff check App/app.py App/bank_statements.py App/local_enhanced_ocr.py --fix && ruff format App/`
- No new rows, no changed totals, no pollution of non-check transactions.
- Cost controls respected (imaging pages only; cache support exercised).

**Artifacts**
- Strong completion note with commands, results, and "ready to mirror to Function" guidance.
- Blueprint entry.
- Updated env sample + minimal docs.

---

## Explicit Boundaries & Anti-Goals

- Do **not** change the Lightweight Parser or the Azure OCR Function call path this sprint.
- Do **not** touch deposit-slip sidecar UI or P&L (that remains 3.4).
- Do **not** alter the canonical 12-column shape or any downstream contracts (Power Query, Process-Statement.ps1, etc.).
- Do **not** make CV mandatory — the fallback must be seamless and production-safe for when the Function is updated later.
- Do **not** spend time fixing pre-existing test gaps (`_find_photo_regions`) unless they are trivial 1-line blockers for your verification.
- Keep diffs focused. The heavy algorithmic work (CV client, scoring, rules, cache, cropper) is already done.

---

## Execution Notes

- Work primarily against the hard Traditions PDF (`Auto_Body_Center_Jan_26_Statement.pdf`).
- Prefer cache-backed runs during development (`SLAM_CV_CACHE_DIR` pointing at prior Phase-1 artifacts).
- When in doubt about the integration point, call `run_hybrid_check_leg` right after `_crop_checks` returns — that is exactly what it was designed for.
- Update the Local Enhanced description text to proudly state the new capability.
- Robert tests on local Windows — make `.env` loading and clear error messages for the missing CV SDK excellent.
- After the core engine works, spend the last portion of the session on the completion note and Blueprint entry.

---

## Definition of Done

- [ ] Local Enhanced path on the hard PDF with CV creds/cache produces measurably better payees on check rows while keeping 92 txns + exact totals + green reconciliation.
- [ ] Same path with no CV creds is 100% unchanged from pre-sprint behavior.
- [ ] UI presents CV-enhanced Local Enhanced as the normal/default experience (not a hidden pilot radio).
- [ ] `run_hybrid_check_leg` is the integration point (no duplicated CV logic).
- [ ] Ruff clean, good logging, graceful fallbacks everywhere.
- [ ] Completion note + Blueprint entry written, with clear guidance for the Azure Function mirror.
- [ ] Robert can run the flow end-to-end on his local Windows machine and see the win.

---

## Summary — The Single Mission

**Make Azure CV Read the primary check-photo leg inside the Local Enhanced OCR pipeline** (tabular → crop → CV on imaging-page checks → enriched table in the site).

When credentials are present it just works and is the default. When they are absent it silently does the old EasyOCR thing. The pattern is deliberately easy to mirror into the Azure Function.

This is the direct realization of the G1 value (7× clean payee improvement on difficult statements) inside the actual tool Robert uses every day.

Load the mandatory documents, start with the integration point in `local_enhanced_ocr.py`, make the UI reflect the new reality, verify on the hard PDF (cache first), and deliver a clean, confident completion package.

**You are cleared to proceed.** Make it excellent.