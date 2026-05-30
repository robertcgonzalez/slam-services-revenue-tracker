# G2 execution guide — second real PDF (spike harness only)

> **Historical note (2026-05-30):** Local Windows is the sole supported dev path (v2.44.16). The `Documents/` folder is gitignored — save G2 grading templates locally under `Scripts/spike/artifacts/` or outside the repo.

**Scope:** Photo leg only (check/deposit slip crops + CV Read). Tabular register extraction stays owned by `App/app.py` and existing parsers — see `Scripts/spike/HYBRID_CV_READ_SCOPE_CLARIFICATION.md`. This guide uses **only** `Scripts/spike/` tools; no `App/` or Azure Function changes.

**Deliverable:** A completed copy of `Documents/g2_second_pdf_grading_summary_template.md` (save under `Documents/` with a distinct filename, or outside the repo — **never** commit client PDFs, crops, raw CV JSON, keys, or filled CSVs).

---

## 1. Choose a suitable second PDF

- Prefer a **different client** and/or **different bank** than the hard test case, still with **embedded check photos** (and deposit slips if you want deposit metrics).
- Stage the file under `Data/` (or another local path) — **gitignored**; do not add to the repo.
- Decide **imaging page range** (`--pages` / `--first-imaging-page` / `--last-imaging-page`). On the first hard PDF, **page 10** produced false crops; excluding the reconciliation sheet (e.g. last page **9**) was important — expect to tune per statement.

---

## 2. Environment

- Run from **repo root** with the project **`.venv` active** (Codespaces usually auto-activate). Paths in this guide assume `python Scripts/spike/...` from root.
- Ensure `.env` at repo root has `AZURE_CV_ENDPOINT` and `AZURE_CV_KEY` (see `Scripts/spike/cv-read.env.sample`). Never commit `.env`.  
  - **Windows:** `copy Scripts\spike\cv-read.env.sample .env` then edit.
- Prefer a **4-core+** machine for 300 DPI work; for Phase 1 with **EasyOCR enabled** (default without `--no-easyocr`), a **16 GB** Codespace SKU avoids PyTorch OOM spikes (see README Codespaces notes). F0 CV Read is slow (~20 calls/min; harness default `--rate-limit-seconds` ≈ 3.2s between calls).

**Ready-to-edit command template (copy once, replace placeholders):**

```bash
export PDF="Data/<your_second_statement>.pdf"
export PAGES="<first>-<last>"          # e.g. 5-9; tune after overlays
export LABEL="<short_tag>"            # e.g. g2_clientA_20260527
export REPO_ROOT="/path/to/SLAM-Services-Project"
cd "$REPO_ROOT"
```

---

## 3. Crop diagnosis (harness folder)

Produce a `crop_diagnosis_*/` tree with `final_kept/` crops aligned with Phase 1 IDs. **Pin the output folder** so you are not hunting for the latest UTC name:

```bash
cd /path/to/SLAM-Services-Project
python Scripts/spike/diagnose_check_deposit_cropper.py \
  --pdf Data/<your_second_statement>.pdf \
  --dpi 300 \
  --pages <first>-<last> \
  --out-dir Scripts/spike/artifacts/crop_diagnosis_${LABEL:-g2_run}
```

- Default in the script for pages is **`5-9`** (hard PDF lesson: page 10 was reconciliation / junk). Override with `--pages` for each bank.
- Optional quick smoke before a long run: `python test_fast_vs_strict.py` (repo root; see `POST_SPIKE_INTEGRATION_PLAN.md` §7).
- Inspect `debug_overlays/` + `manifest.csv`; adjust `--pages` or tune `--min-center-dist` / hash-size only if you understand the tradeoff (see script `--help`).

---

## 4. Phase 1 — CV Read harness (side-by-side vs EasyOCR)

Point at the new harness directory; first run uses Azure when `--real`:

```bash
python Scripts/spike/phase1_cv_read_harness.py \
  --harness-dir Scripts/spike/artifacts/crop_diagnosis_<UTC> \
  --real \
  --out-dir Scripts/spike/artifacts/phase1_real_cv_read_harness_<your_label>
```

**Tips**

- `--limit N` — smoke a few crops before the full pass.
- `--no-easyocr` — faster if you only need CV Read columns (still compare to baseline later if needed).
- **Zero-cost re-run (Phase 1):** after a real run, `raw_cv_responses/*.json` lives under the phase1 output folder. Use **`--rescore <that_folder>`** to re-extract payees with **no Azure calls**. (`--reuse-cv-dir` is a **Phase 5** flag; do not pass it to `phase1_cv_read_harness.py`.)
- Example:  
  `python Scripts/spike/phase1_cv_read_harness.py --rescore Scripts/spike/artifacts/phase1_real_cv_read_harness_<YOUR_RUN> --out-dir Scripts/spike/artifacts/phase1_<YOUR_RUN>__rescored`
- F0: expect **~10+ minutes** for dozens of crops; S1 is faster if available for this validation.

---

## 5. Optional — Phase 5 hybrid + Phase 6 smoke

For end-to-end spike parity (register rows from baseline unchanged; photo leg merged):

```bash
# New baseline dir for this PDF (or reuse if you already ran Phase 0 for it)
python Scripts/spike/baseline_current_ocr.py --pdf Data/<your_second_statement>.pdf \
  --out-dir Scripts/spike/artifacts/baseline_<your_label>
# If the baseline manifest shows too few photo regions vs visible checks/deposits,
# re-run baseline with --relaxed-crop (spike-only; does NOT change production strict path).
# python Scripts/spike/baseline_current_ocr.py --pdf Data/<your_second_statement>.pdf \
#   --relaxed-crop --out-dir Scripts/spike/artifacts/baseline_<your_label>_relaxed

python Scripts/spike/phase5_hybrid_pipeline.py \
  --pdf Data/<your_second_statement>.pdf \
  --baseline-dir Scripts/spike/artifacts/baseline_<your_label> \
  --harness-dir Scripts/spike/artifacts/crop_diagnosis_<UTC> \
  --reuse-cv-dir Scripts/spike/artifacts/phase1_real_cv_read_harness_<your_label>/raw_cv_responses \
  --out-dir Scripts/spike/artifacts/phase5_hybrid_<your_label>
```

Then optionally:

```bash
python Scripts/spike/phase6_pl_smoke.py --hybrid-dir Scripts/spike/artifacts/phase5_hybrid_<your_label>
```

Use `--reuse-cv-dir` whenever the JSON cache exists to **avoid duplicate CV billing** during iteration.

---

## 6. Fill the G2 template

- Open `Documents/g2_second_pdf_grading_summary_template.md`, save a **filled** copy (e.g. `Documents/g2_second_pdf_grading_<short_label>.md`) **without** secrets; use initials or “Client A” if needed.
- Record: pages, crop count, EasyOCR vs CV clean-payee stats (or methodology if manual), **full wins / light fixes / still heavy**, deposit slip results, issues, latency/cost, **one-sentence generalization verdict**.
- **Decision-useful grading:** use `side_by_side_harness.csv` from the Phase 1 output (paths in `image_path` must match your `final_kept/` tree). Rubric and workflow: `Scripts/spike/GRADING_GUIDE.md`. Optional: run `python Scripts/spike/grade_phase1_crops.py` (resumable; writes `manual_grade` back to the CSV) then **roll up** codes to the template (`c` → full wins; `s`/`p` → light fixes; `w`/`e`/`b`/`x` → still heavy / needs work; `d`/`d_partial` → deposit slip rows).

---

## 7. Supporting artifacts (all local)

- Keep outputs under `Scripts/spike/artifacts/` (already covered by `Scripts/spike/artifacts/.gitignore` where applicable).
- Do not stage `*.csv`, `raw_cv_responses`, crop PNGs with account numbers, or `.env` for git.

---

## 8. Gotchas from the first hard PDF run

- **Page scope:** Last imaging page often must **exclude** a summary/reconciliation page to avoid junk crops.
- **F0 rate limits:** Use default spacing or `--rate-limit-seconds`; expect long wall times.
- **Hybrid is assist-only:** Many checks may still need heavy manual payee cleanup; the template’s grading breakdown captures that honestly.
- **Tabular row count:** G2 validates the **photo leg**; baseline `transactions_all.csv` row counts for the second PDF are still from existing parsers — note any mismatch in “notable issues” if something looks off, but do not change parser ownership as part of G2.

---

## 9. Dry-run readiness review (guide vs hard PDF artifacts)

Cross-check against the closed spike layout (`PHASE7_NOTES.md`): e.g. harness `crop_diagnosis_20260527T001907Z/`, Phase 1 `phase1_real_cv_read_harness_20260526T195813Z__rescored/`, Phase 5 reuse under `phase5_hybrid_reuse_test/`. Your second PDF should mirror that **folder naming discipline** (`*_g2_*` labels) so paths in the filled template stay auditable.

| Gap addressed | Why it matters |
|---------------|----------------|
| **`--out-dir` on diagnose** | Avoids guessing `crop_diagnosis_<UTC>/` when wiring `--harness-dir` for Phase 1 / 5. |
| **Repo root + venv + RAM** | Wrong cwd breaks imports/paths; low RAM fails EasyOCR in Phase 1. |
| **Clarified `--rescore` vs `--reuse-cv-dir`** | Phase 1 cache re-use is `--rescore`; `--reuse-cv-dir` is Phase 5-only — removes a common copy-paste mistake. |
| **`GRADING_GUIDE.md` + `grade_phase1_crops.py`** | Same rubric as the hard PDF; produces defensible counts for the G2 template verdict. |
| **`--relaxed-crop` on baseline** | If strict baseline under-captures photo regions on a new bank, spike-only relaxation aligns crop inventory with visible checks without touching production defaults. |
| **`test_fast_vs_strict.py`** | Cheap sanity check before 300 DPI + Azure spend. |
| **`.env` Windows one-liner** | Matches `PHASE7_NOTES.md` / runbook; reduces setup friction off-Codespace. |
