# HCC E1 Failure Mode Taxonomy (Living)

**Date**: 2026-05-27 (HCC full 50-crop + QCR B5 third-PDF validation)  
**Use**: Future extractor work, Regions / First Metro pilots, cropper tuning

---

## Categories

### FM-1 — Business-line OCR over signature (`first_clean`)

**Symptoms**: Engine returns `* Concrete` variant; human truth is person on signature line.  
**Count (final)**: **3** graded `w` (P05_K12, P05_K15, P06_K06); many more caught as `c` after human_v3 signature ranking.  
**Mitigation**: Signature-zone boost (`regions.yaml`); high-precision check rules per OCR variant.  
**Example patterns**: `Cristone Concrete`, `Customs Concreto`, `Custonie Concrete`, `Custom Conercte`.

### FM-2 — OCR header fragment as payee

**Symptoms**: Single-token garbage (e.g. `OHernandez`, `Olernandez`) wins `first_clean`.  
**Count**: **1** graded `w` (P07_K12).  
**Mitigation**: Singleton denylist / check rule mapping to signature-line person.

### FM-3 — LLC / business block ranked over person (historical)

**Symptoms**: `Hernandez Custom Concrete LLC` or `Custom Concrete` from scan path.  
**Count on full 50**: **0** remaining `w` (fixed in human_v3 on 16-crop sample).  
**Mitigation**: Business-block penalty + signature boost; removed broad Hernandez LLC check rules.

### FM-4 — Wrong Hernandez family member (historical)

**Symptoms**: `Jesus Hernandez` when payee is Gabriel/Misael/etc.  
**Count on full 50**: **0** remaining `w`.  
**Mitigation**: Signature-line ranking; removed broad `Jesus Hernandez` check rules.

### FM-5 — Perez OCR spelling (policy, not failure)

**Symptoms**: `Misaen Perez`, `Jerman Perez` — correct per client policy.  
**Count**: **0** `w` — all graded `c`.  
**Mitigation**: **Do not normalize** (B3 `PEREZ_OCR_POLICY.md`).

### FM-6 — CV read failure / `no_lines` (historical)

**Count on full 50**: **0** (page-7 retry B2).  
**Mitigation**: Targeted CV re-read; rate-limit spacing.

---

## Grade code reference

| Code | HCC E1 final count | Action |
|------|-------------------:|--------|
| `c` | 46 | Ship as-is |
| `w` | 4 → **0** after rules | Check rule or manual |
| `s`/`p` | 0 | Light edit in App (none observed) |
| `e`/`b` | 0 | Full manual (none observed) |

---

## QCR / First Metro B5 observations (2026-05-27)

Third PDF: `Data/QCR 2026-04.pdf` — **16 checks** human-graded on pages **9–10** only (`QCR_B5_VALIDATION_REPORT.md`).

### FM-7 — Payer / company header ranked over payee (`scan`)

**Symptoms**: Engine returns `QUALITY CHOICE ROOFING LLC` when payee is a person or vendor on the pay line (e.g. Jan Fontana, Carlex Garrett, Rocket City Roofing).  
**Count (QCR sample)**: **3** graded `w` (P09_K00, P09_K04, P09_K10).  
**Mitigation**: Client- or bank-specific **payer-header denylist** in profile (substring of account holder name) + signature-zone boost; `regions` profile already fixes some cases vs `generic`.  
**Spike (2026-05-27)**: `payer_header_penalty` in `engine.py` + `regions.yaml` (`generic_suffix_enabled`) + `first_metro.yaml` for QCR substring — see `FM7_FM9_SPIKE_NOTES.md`.  
**Do not** add broad “Roofing LLC” check rules without human-confirmed OCR strings.

### FM-8 — Courtesy amount (words) as payee (`next_line` / `scan`)

**Symptoms**: `two thousand four hundred and fifteen`, `nine thousand three hundred…`, `Aire thousand nine hundred…` instead of person/vendor.  
**Count (QCR)**: **1** graded `w` on regions rescore (P10_K04 → should be ABC Supply); generic had more.  
**Mitigation**: Strengthen amount-in-words filter in engine; prefer `ORDER OF` / line above amount block; regions `scan` helped P09_K09, P10_K03.

### FM-9 — Cropper page-scope miss (statement layout)

**Symptoms**: Zero crops on pages **5–8**; all 26 crops from pages **9–10**; baseline Local OCR **0** cropped checks for full PDF.  
**Mitigation**: Per-PDF imaging page detection or relaxed geometry for First Metro GO-statement layout — **G1 cropper work (B6)**, not payee-engine alone.  
**Spike PoC (2026-05-27)**: `diagnose_check_deposit_cropper.py --detect-imaging-pages` → `imaging_pages.json` + recommended `--pages` range.

### FM-1 / FM-2 — Confirmed on new bank

**QCR examples**: `TAY TO THE` (P09_K03, `w`); `TAY TO THE.` on generic (P09_K02 fixed to `Jan Fatos` with `regions`).  
**Action**: Same as HCC — signature boost + exact check rules only when needed.

### Deposits — First Metro virtual tickets

**Symptoms**: Payee field `SUBSTITUTE IMAGE / VIRTUAL DOCUMENT` — **expected** for 8/10 deposits.  
**Grade**: All **`d`** — classifier correct; not a payee-extraction failure.

---

## When additional bank PDFs arrive

1. Re-run harness; compare failure modes to this list (HCC + QCR columns).  
2. Prefer **signature-zone boost + payer-header penalty** in `regions.yaml` or a dedicated `first_metro.yaml` over broad check rules.  
3. Add check rules only for **exact** OCR strings with human-confirmed mapping (`Data/check_payee_rules.csv`).  
4. Read `artifacts/LATEST_HCC_E1.txt` before wiring; do not copy Hernandez/LLC catch-all rules removed after the 16-crop sample.
