# G2 quick-start — command sheet (spike only)

**Scope:** Photo leg only (`Scripts/spike/HYBRID_CV_READ_SCOPE_CLARIFICATION.md`). Tabular register stays with `App/app.py` + parsers. Details: `Scripts/spike/G2_EXECUTION_GUIDE.md`.

**Gotchas (one line each):** Tune **`PAGES` / `LAST_PAGE`** — last sheet is often reconciliation junk (hard PDF: drop page 10). **`--rescore`** = Phase 1 zero-cost reparse; **`--reuse-cv-dir`** = Phase 5 only. **Never** `git add` PDFs, crops, `raw_cv_responses/`, graded CSVs, or `.env`.

---

## 1) Edit once, then paste

```bash
export REPO_ROOT="/path/to/SLAM-Services-Project"   # ← change
export PDF="Data/<your_second_statement>.pdf"       # ← change (gitignored path OK)
export PAGES="5-9"                                  # ← change (e.g. 5-9; inspect overlays first)
export FIRST_PAGE=5                                 # ← must match start of imaging range
export LAST_PAGE=9                                  # ← must match end of imaging range
export LABEL="<short_tag>"                          # ← e.g. g2_clientA_20260527 (used in artifact paths)

cd "$REPO_ROOT"
# .venv active; repo-root .env has AZURE_CV_* (see Scripts/spike/cv-read.env.sample)
```

---

## 2) Optional smoke (seconds)

```bash
python test_fast_vs_strict.py
```

---

## 3) Crop diagnosis → pinned harness dir

```bash
python Scripts/spike/diagnose_check_deposit_cropper.py \
  --pdf "$PDF" \
  --dpi 300 \
  --pages "$PAGES" \
  --out-dir "Scripts/spike/artifacts/crop_diagnosis_${LABEL}"
```

Inspect `Scripts/spike/artifacts/crop_diagnosis_${LABEL}/debug_overlays/` + `manifest.csv`; fix `PAGES` if needed, re-run §3.

---

## 4) Phase 1 — CV Read harness (Azure: `--real`)

```bash
# Smoke: add   --limit 3   before --real
python Scripts/spike/phase1_cv_read_harness.py \
  --harness-dir "Scripts/spike/artifacts/crop_diagnosis_${LABEL}" \
  --real \
  --out-dir "Scripts/spike/artifacts/phase1_${LABEL}"
```

**After JSON exists — re-extract payees, $0 Azure:**  
`python Scripts/spike/phase1_cv_read_harness.py --rescore "Scripts/spike/artifacts/phase1_${LABEL}" --out-dir "Scripts/spike/artifacts/phase1_${LABEL}__rescored"`

(Optional grading: `Scripts/spike/GRADING_GUIDE.md`, `python Scripts/spike/grade_phase1_crops.py`.)

---

## 5) Optional — Phase 5 + 6 (uses `--reuse-cv-dir` only here)

```bash
python Scripts/spike/baseline_current_ocr.py --pdf "$PDF" \
  --out-dir "Scripts/spike/artifacts/baseline_${LABEL}"
# If too few regions vs visible checks: add --relaxed-crop and a new --out-dir (spike-only).

python Scripts/spike/phase5_hybrid_pipeline.py \
  --pdf "$PDF" \
  --baseline-dir "Scripts/spike/artifacts/baseline_${LABEL}" \
  --harness-dir "Scripts/spike/artifacts/crop_diagnosis_${LABEL}" \
  --reuse-cv-dir "Scripts/spike/artifacts/phase1_${LABEL}/raw_cv_responses" \
  --first-imaging-page "$FIRST_PAGE" \
  --last-imaging-page "$LAST_PAGE" \
  --out-dir "Scripts/spike/artifacts/phase5_hybrid_${LABEL}"

python Scripts/spike/phase6_pl_smoke.py --hybrid-dir "Scripts/spike/artifacts/phase5_hybrid_${LABEL}"
```

If you used **`phase1_${LABEL}__rescored`**, point `--reuse-cv-dir` at that folder’s `raw_cv_responses/` instead.

---

## 6) When done — G2 template (one line)

Save a filled copy of `Documents/g2_second_pdf_grading_summary_template.md` as e.g. `Documents/g2_second_pdf_grading_${LABEL}.md` (or outside git); do not commit client artifacts.
