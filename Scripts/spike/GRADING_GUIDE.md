# Phase 1 Visual Grading Guide — CV Read vs PNGs

**Goal**: Produce an honest, human-verified count of how many payees are actually usable after Azure CV Read on the 56 clean crops. This number (plus the breakdown of remaining manual effort) feeds the final spike report and the Phase 2 decision.

**Primary artifacts** (use these):
- CSV: `Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored/side_by_side_harness.csv`
- Images: `Scripts/spike/artifacts/crop_diagnosis_20260527T001907Z/final_kept/` (the `_final.png` files referenced by the CSV `image_path` column)

All 56 images exist on disk and the CSV `image_path` values point to them.

---

## Grading Rubric (use these values in the `manual_grade` column)

| Code | Stored value example                          | Meaning / When to use |
|------|-----------------------------------------------|-----------------------|
| `c`  | `correct`                                     | CV extracted the correct payee cleanly (or near-perfect). This is a full win. |
| `s`  | `spelling: Hallmark Hyundai (was Hyunden)`    | Core business name is right but needs 1–4 character spelling cleanup. Still a huge win — the payee rules engine + data_editor can usually fix these. |
| `p`  | `partial: Auto Body Center (extra junk)`      | Got the main name but truncated, has OCR noise, or extra tokens. Usable with light editing. |
| `w`  | `wrong: should be Sherwin Williams`           | CV produced something clearly incorrect. Type the actual text visible in the photo after the "Pay to the order of" line. |
| `e`  | `empty - handwritten payee illegible`         | No usable payee text recovered (handwritten, very light print, CV missed the line entirely). These require full manual entry. |
| `b`  | `boilerplate: Security features`              | CV anchored on a printed check security line instead of the payee. False positive. Treat as manual. |
| `d`  | `deposit_ok - text captured for P&L`          | Deposit slip. Classification is correct. The raw JSON contains the deposit breakdown lines (useful for credit-side attribution). |
| `d_partial` | `deposit_partial - some lines weak`      | Deposit slip but CV missed or garbled some of the deposit items. Still classifiable, but P&L value is reduced. |
| `x`  | (leave blank or `x - revisit`)                | Unsure / need second opinion / consult Laura. Come back later. |

**Free-text is allowed** after the code if you want to capture extra context. The interactive grader script below accepts short codes and expands them into the structured values shown above.

---

## Recommended Workflow

1. **Start with the 7 deposits (page 5 only)**  
   They are the easiest and most consistent. All 7 should be classifiable as `d` or `d_partial`. Their `cv_read_payee_candidate` is usually "DEPOSIT TICKET" — this is expected and correct for classification.

2. **Then go page-by-page (P05 checks → P06 → P07 → P08 → P09)**  
   Keeps context fresh (same statement, similar check stock, same bank).

3. **For each row**:
   - Look at `cv_read_payee_candidate` + `cv_read_payee_reason` (`next_line` is the most common good path after "Pay to the order of").
   - Open the PNG (the grader script does this for you with one keypress).
   - Find the physical "Pay to the order of" area in the photo.
   - Compare what CV Read pulled vs what is actually written.
   - Ignore the EasyOCR column for the final verdict — it is the garbage baseline we already know loses badly.

4. **Focus especially on**:
   - The ~15 rows that came back empty (`anchor_no_clean_candidate` or `no_clean_candidate`).
   - Any row where `cv_read_is_clean = Yes` but the candidate looks like a courtesy amount or boilerplate.
   - Spelling variants on real business names ("Hallmark Hyunden", "Cluto Sync", "Sheroin Williams", etc.).

5. **Record the final honest count** in `PHASE1_NOTES.md` (there is already a placeholder section for it).

---

## How to interpret key CSV columns

- `cv_read_payee_reason`:
  - `next_line` — strongest signal (anchored on "Pay to the order of" then took the following clean line).
  - `same_line` — payee was on the same line as the anchor (less common).
  - `first_clean` — fell back to the first clean-looking line in the crop.
  - `anchor_no_clean_candidate` / `no_clean_candidate` — CV saw the anchor but nothing usable after it (these are the hard cases).

- `predicted_class` + `classifier_keywords` — the cheap text heuristic that separated checks from the 7 deposit slips on page 5. It matched ground truth perfectly in this run.

- `easyocr_extracted_payee` / `easyocr_text` — the current production baseline on the exact same enhanced PNG. Usually garbage or blank. Use it only to feel the pain of the status quo.

---

## Launching the interactive grader

```powershell
# From repo root, in the project venv
python Scripts/spike/grade_phase1_crops.py
```

The script:
- Defaults to the recommended rescored CSV.
- Opens each image in your default Windows viewer (Photos, IrfanView, etc.) with one keypress.
- Is fully resumable — it always starts at the first blank `manual_grade` row.
- Accepts the short codes above (or full words).
- For `w` (wrong) it prompts for the actual payee text you see in the photo.
- Writes the CSV back after every grade (safe incremental progress).
- Shows live stats: graded this session, remaining, per-page progress.

Optional filters (examples):
```powershell
python Scripts/spike/grade_phase1_crops.py --page 5
python Scripts/spike/grade_phase1_crops.py --class check
python Scripts/spike/grade_phase1_crops.py --only-ungraded
```

See the script header for all flags.

---

## After you finish grading

1. Re-run the breakdown diagnostic on the updated CSV:
   ```powershell
   python Scripts/spike/phase1_breakdown.py `
       Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored
   ```
   (It will now reflect your human grades.)

2. Update the "Remaining manual payee effort for Laura on this statement" table in `PHASE1_NOTES.md` with the real numbers.

3. (Optional but recommended) Add 5–10 example rows to the notes with your `manual_grade` verdict + a one-sentence note.

4. The final "manual entries/corrections" number becomes the key success metric for the spike report.

---

## Security / hygiene

- The CSV and PNGs are already gitignored (under `Scripts/spike/artifacts/`).
- Do **not** commit the graded CSV if it contains any sensitive customer names from real statements (the Auto Body Center test PDF is internal test data, but treat it as production-grade for privacy).
- The `.env` with the F0 key should have been rotated after the original run (per the original spike instructions).

---

**Questions while grading?**  
Open the raw JSON for any crop:
`Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored/raw_cv_responses/<crop_id>.json`

It contains the full `raw_text` + every line with confidence + bounding box. Very useful when the CSV candidate looks odd.

Good luck — this 15–25 minute pass is the single most important piece of evidence the spike will produce.