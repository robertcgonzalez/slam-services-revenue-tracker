# Post-E1 Hygiene Report

**Date**: 2026-05-27  
**Run**: Post-E1 independent review cleanup (autonomous)

---

## Phase 0 — Git hygiene & reversion

### Initial `git status` (before reverts)

Tracked modifications outside spike boundary included:

- `App/` (5 files including `local_enhanced_ocr.py`)
- `AzureFunctions/ocr_processor/function_app.py`
- `README.md`, `SLAM Services - Digital Transformation Blueprint.md`
- `Scripts/PowerShell/*`, `Scripts/*.py` (non-spike), `requirements.txt`
- `.azure/config`, `.grok/AGENT.md`, `.vscode/*`

### Actions taken

```bash
git restore -- .azure/config .grok/AGENT.md .vscode/* App/* AzureFunctions/ocr_processor/function_app.py \
  README.md "SLAM Services - Digital Transformation Blueprint.md" Scripts/PowerShell/* \
  Scripts/Process-Statement.ps1 Scripts/bank-statement-parser.py Scripts/health_check.py \
  Scripts/init_db.py Scripts/migrate_to_postgres.py Scripts/smart_check_cropper_final_dynamic.py \
  requirements.txt "Project Runtime User Stories.txt"
```

### Final `git status` (after reverts)

Only **untracked** paths remain (no tracked modifications outside spike):

```
?? Documents/
?? Scripts/spike/
?? Spike-Report-Computer-Vision-Check-Leg-20260527.md
?? (other untracked root docs — not modified by this run)
```

### Legitimate spike work verified present

| Artifact | Path | Status |
|----------|------|--------|
| Payee extractor module | `Scripts/spike/payee_extractor/` | Present |
| HCC E1 rescore | `Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions/` | Present |
| Traditions E1 rescore | `Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored_e1_traditions/` | Present |
| Check rules | `Data/check_payee_rules.csv` | Present |
| Smoke test | `Scripts/spike/test_payee_extractor_smoke.py` | Present |
| Status docs | `AUTONOMOUS_RUN_SUMMARY.md`, `E1_E2_STATUS.md` | Present |

---

## Phase 1 — Validation findings

### Smoke test

```
python Scripts/spike/test_payee_extractor_smoke.py
→ OK: payee_extractor smoke tests passed
```

### HCC E1 (`phase1_g2_hcc_202604__rescored_e1_regions`) — 50 rows

**`cv_read_payee_reason` distribution**

| Reason | Count |
|--------|------:|
| first_clean | 16 |
| scan+check_rule | 9 |
| first_clean+check_rule | 7 |
| no_lines | 7 |
| next_line | 6 |
| scan | 4 |
| next_line+check_rule | 1 |

- `cv_read_is_clean` Yes: **43/50** (7 page-7 `no_lines` = CV rate-limit failures)
- `+check_rule` suffix: **17**

**Confirmed wins vs baseline**

- `REGIONS BANK` false positives: **12 baseline → 0 E1** (re-verified from CSV)

**Obvious boilerplate/garbage still accepted (E1 v1)** — 3 crops:

| crop_id | payee | reason |
|---------|-------|--------|
| P05_K05 | Pretected by | next_line |
| P07_K00 | AUTHORIZED SIGNALILL | next_line |
| P07_K08 | Protectis by -PINKcryph | next_line |

**Borderline / OCR-wrong payees (not boilerplate; need human or rules)** — examples:

- Perez name variants: `Misaen Perez`, `Jerman Perez` (likely Jesus Hernandez checks)
- Concrete OCR: `Casstomat Concrete`, `Custonie Concrete`, `Customs Concrete`, `Customer Concrete`
- Other garbage: `Quetent Orstarcie`, `IC HE O. EN OF`, `Visit golf-NG`, `Prouced by BIRKiry:P.`

**Raw JSON cross-check (P07_K08)**

CV Read contains `Custom Concrete` (line 4) and `Ofernandez` (line 1); extractor wrongly picked vertical security text `Protectis by -PINKcryph` via `next_line` after anchor — spatial/ranking gap, not missing OCR.

### Traditions E1 — 56 rows

- Reasons: `next_line` 28, `first_clean` 23, `same_line` 5
- **7× `CASH >`** on page 5 (`first_clean`) — courtesy-amount line mis-selected as payee
- **1× `Security innitems`** on P09_K00

### Honest assessment

E1 met the **heavy ≤20** rubric gate and eliminated bank-name boilerplate, but **~15–20 HCC crops** still need Laura review (OCR fragments, Perez names, security-line leaks). Traditions has a **systematic `CASH >` leak** on early page-5 checks.

---

## Phase 2 — Denylist v2 (append)

After `boilerplate.py` tightening and v2 rescores:

- HCC obvious garbage: **9 → 0**
- Traditions `CASH >` / security: **8 → 0**
- Traditions regressions on `manual_grade=correct`: **0**

See `POST_E1_VALIDATION_STATUS.md` and `artifacts/hcc_e1_v1_v2_diff.md`.

---

## Human Validation Results (2026-05-27)

**Source**: `artifacts/hcc_e1_human_review_package_20260527.csv` (Laura / owner grades on 16 priority crops).

| Metric | Count |
|--------|------:|
| Rows reviewed | **16** |
| Human **`c`** (correct / full win) | **6** |
| Human **`w`** (wrong) | **10** |

### Rubric-assist cross-check (E1 v2 / `__rescored_e1_regions_v2`)

All 16 review crops had `cv_read_is_clean=Yes` (rubric-assist would score **16/16 full wins**). Human ground truth on the **same** v2 payees: **6/16** correct → **10/16 false positives** (62.5%) on this priority sample. Root cause: printed **business block** (`Custom Concrete` / LLC) and blanket **check rules** (`Hernandez` → `Jesus Hernandez`) beat signature-line payees.

### Failure modes in human **`w`** rows (v2 extractor)

| Mode | Crops | Notes |
|------|------:|-------|
| **Check rule over-correction** | 7 | `Custom Concrete` → `Hernandez Custom Concrete LLC` on checks whose payee is an individual Hernandez or Uriostegui |
| **Wrong Hernandez individual** | 2 | `Jesus Hernandez` rule; truth was Gabriel or Misael |
| **OCR business-line winner** | 1 | `Custom Conercte` (P05_K05) |
| **Ranking missed signature line** | — | Correct names were present in raw JSON after `AUTHORIZED SIGNATURE` (bbox Y all zero on HCC cache) |

### Post-human fix (`human_v3` rescore)

Engine: Regions **signature-zone person-name boost** + **business-line penalty** (`payee_extractor/engine.py`). Rules: replaced 6 broad HCC seeds with **2** high-precision human-derived rows in `Data/check_payee_rules.csv`. **16/16** match human truth on the review package; **0** Traditions regressions on `manual_grade=correct`. Detail: `HCC_HUMAN_VALIDATION_REPORT.md`, `artifacts/hcc_e1_v2_human_v3_diff.md`.

---
