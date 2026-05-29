---
name: ocr-pipeline-robustness
category: ocr
difficulty: hard
recommended_mode: researcher-builder
---

# Task: Improve Local Enhanced OCR Pipeline Robustness

Focus on `App/local_enhanced_ocr.py`, `Scripts/e2e_local_ocr.py`, and related cropper / hybrid logic.

## Goals
- Reduce failure rate on difficult scanned PDFs (especially multi-page statements with mixed check + tabular content).
- Improve check crop quality or detection of failed crops.
- Better handling of edge cases (zero transactions on a page, heavy boilerplate, poor scan quality).
- Maintain or improve speed where possible.

## Approach
1. Run the current pipeline against one or more difficult real statements (use existing test PDFs in `Data/` or `Scripts/_streamlit_bank_uploads/`).
2. Identify the top 3-5 recurring failure modes (bad crops, missed checks, OCR line joining errors, payee extraction collapse, etc.).
3. Propose and implement targeted improvements. Possible areas:
   - Cropper tuning (smart_check_cropper_final_dynamic.py)
   - Better page segmentation / pre-filtering before OCR
   - Improved fallback logic between EasyOCR / Azure DI / local models
   - More defensive parsing in the main pipeline
   - Better diagnostics and structured logging when things go wrong

4. Add or improve regression tests / smoke tests that can be run cheaply.

## Deliverables
- Concrete code changes with clear comments
- Before/after comparison on the test documents (CSV diffs or summary tables)
- Updated documentation in the relevant spike notes or a new "Pipeline Failure Modes" section
- Clear instructions for how to run the improved pipeline locally

## Constraints
- Do not break existing bank statement tabular parsing (that's owned by `App/bank_statements.py` and `App/app.py`).
- The photo-leg payee extraction path can be improved but should remain compatible with the separate payee_extractor evolution work.
