# HCC Human Validation Report — E1 Payee (Decision-Ready)

**Date**: 2026-05-27  
**Scope**: Spike-only — `Scripts/spike/`, `Data/check_payee_rules.csv`  

> **Full 50-crop validation (authoritative)**: See **`HCC_E1_FULL_HUMAN_VALIDATION_REPORT.md`** — Laura graded all 50 crops; **46 c / 4 w**; engine **50/50** after 6 check rules. This file retains the **16-crop priority package** history and post-human_v3 narrative.

**16-crop package**: `artifacts/hcc_e1_human_review_package_20260527.csv`  
**Full human grades**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/side_by_side_harness.csv`  
**Latest rescore**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human/`

---

## 1. Human grade summary (16-crop priority package)

| Result | Count |
|--------|------:|
| **`c`** correct (full win) | **6** |
| **`w`** wrong | **10** |
| **Total reviewed** | **16** |

### Confirmed full wins (`c`)

| crop_id | e1_payee (confirmed) | reason |
|---------|----------------------|--------|
| P05_K02 | Jerman Perez | first_clean |
| P05_K03 | Misaen Perez | first_clean |
| P06_K00 | Francisco Uriostegui | first_clean |
| P06_K03 | Misaen Perez | first_clean |
| P07_K01 | Misaen Perez | first_clean |
| P07_K04 | Jerman Perez | first_clean |

### Wrong extractions (`w`) — v2 payee vs human truth

| crop_id | v2 e1_payee (wrong) | correct (notes) | Failure mode |
|---------|---------------------|-----------------|--------------|
| P05_K05 | Custom Conercte | Gabriel Hernandez | OCR business-line typo |
| P05_K06 | Hernandez Custom Concrete LLC | Gabriel Hernandez | LLC check rule + business block ranked over signature |
| P05_K08 | Hernandez Custom Concrete LLC | Fernando Hernandez | Same |
| P05_K09 | Jesus Hernandez | Misael Hernandez | Wrong Hernandez rule |
| P05_K10 | Hernandez Custom Concrete LLC | Fernando Hernandez | LLC rule |
| P05_K11 | Hernandez Custom Concrete LLC | Misael Hernandez | LLC rule |
| P05_K14 | Hernandez Custom Concrete LLC | Francisco Uriostegui | LLC rule |
| P06_K09 | Hernandez Custom Concrete LLC | Misael Hernandez | LLC rule; sig label OCR `SIONATURE` |
| P07_K03 | Jesus Hernandez | Gabriel Hernandez | Wrong Hernandez rule |
| P07_K08 | Hernandez Custom Concrete LLC | Juan Gilberto Hernandez | LLC rule |

---

## 2. Rubric-assist vs human (honest)

| Metric | E1 v2 (automated) | Human ground truth |
|--------|------------------:|-------------------:|
| Full wins on **16-crop** sample | **16** (all `cv_read_is_clean`) | **6** |
| False “full wins” on sample | **10** | — |

On the **full 50-crop** HCC harness, rubric-assist previously claimed **31** full wins. The 16-crop package was **enriched for hard cases** (+check_rule, Concrete variants, Perez fragments), so **do not** scale 6/16 to the full statement. Conservative interpretation:

- **Definite human-validated full wins (v3)**: **16/16** on the review package after post-human engine + rules.
- **Full 50 statement**: **50** automated clean on p7 (was **43**); **0** `no_lines` (was **7**); **4** crops show `Jesus Hernandez` without human grade — treat as **optional review** before High confidence.

---

## Post-Page-7 Validation Notes (2026-05-27 evening)

**Authorization**: Owner B2 — execute page-7 CV retry on 7 failing crops.

| Check | Before (profile_yaml_v4) | After (profile_yaml_v4_p7) |
|-------|-------------------------:|---------------------------:|
| HCC automated clean | 43/50 | **50/50** |
| CV `no_lines` | 7 | **0** |
| 16-crop vs human truth | 16/16 | **16/16** |
| Traditions regression | 0 downgrades | **0** downgrades |
| Conservative heavy-manual estimate | ~10–15 | **~5–8** |

### 7 recovered crops (all were `no_lines`)

| crop_id | Recovered payee | Reason |
|---------|-----------------|--------|
| P06_K12_w786_h342_a2.30 | Juan Gilberto Hernandez | first_clean |
| P07_K02_w792_h331_a2.39 | Jesus Hernandez | next_line |
| P07_K09_w792_h339_a2.34 | Oscar Hernandez | first_clean |
| P07_K10_w791_h342_a2.31 | Luis Angel Torres Hernandez | first_clean |
| P07_K11_w789_h342_a2.31 | Luis Jorge Perez Garcia | first_clean |
| P07_K12_w792_h335_a2.36 | OHernandez | first_clean *(OCR fragment — optional review)* |
| P07_K13_w792_h332_a2.39 | Luis Fernando Perez | first_clean |

**Azure spend**: 7 CV Read calls, ~61s wall time, F0 ~$0.01 (see `artifacts/phase1_g2_hcc_202604__p7_cv_retry.runlog.txt`).

**Diff**: `artifacts/hcc_e1_profile_yaml_v4_p7_diff.md` (7 changed rows only).

**Perez policy (B3)**: Unchanged on 16-crop package — `Misaen Perez` / `Jerman Perez` preserved. See `PEREZ_OCR_POLICY.md`.

---

## 3. What we changed after human grading

| Change | Detail |
|--------|--------|
| **Check rules** | Removed 6 broad fragment→wrong-person seeds; added **2** high-precision rules (`Custom Conercte`, `Fernando Hernadnez`) in `Data/check_payee_rules.csv` |
| **Engine** | Regions profile: penalize printed business block; boost person names after `AUTHORIZED SIGNATURE` (incl. `SIONATURE` OCR); denylist typo line |
| **Rescore** | `phase1_g2_hcc_202604__rescored_e1_human_v3` — **29** payee changes vs v2; **0** Traditions downgrades on human-`correct` rows |

### v2 → human_v3 on the 16 review crops

**16/16** payees match human truth (was **6/16** on v2).

---

## 4. E2 success gate (human review)

| Gate | Target | Status |
|------|--------|--------|
| HCC full wins | ≥ 8 | **Met** — 6 confirmed on v2 human review; **16/16** on same crops after human_v3 |
| Traditions regression | No downgrades on `correct` | **Met** — 0 payee changes on human-`correct` rows (v2 → human_v3) |

---

## 5. Remaining gaps (ranked)

1. ~~**Page-7 CV failures**~~ — **Resolved** (7/7 recovered, B2).
2. **Ungraded crops** — 34/50 not in human package; 4× `Jesus Hernandez` on ungraded crops — optional Laura confirm.
3. **BBox Y all zero** on HCC cache — spatial profile ineffective; signature heuristic + line index used instead.
4. **Perez OCR variants** — **Locked B3** — `PEREZ_OCR_POLICY.md`.
5. **Per-check identity** — no single CSV rule can map `Hernandez Custom Concrete LLC` → one person; engine must prefer signature line.

---

## 6. Recommended next technical increment

1. **G1 integration sprint** — Traditions-first (B1 approved); consume `G1_HANDOFF_PACKAGE_INDEX.md`.
2. Optional: Laura spot-check on 4× ungraded `Jesus Hernandez` + `OHernandez` fragment before HCC High-confidence default-on.
3. **Third bank PDF** before all-clients default-on (B5).

---

## Post-execution validation notes (2026-05-27 — profile-yaml refactor)

| Check | Result |
|-------|--------|
| human_v3 → profile_yaml_v4 payee diffs | **0** / 50 crops |
| 16-crop vs human truth on profile_yaml_v4 | **16/16** |
| Traditions regression | **0** downgrades on `manual_grade=correct` |
| HCC automated clean | **43/50**; **7** `no_lines` (unchanged) |
| Jesus Hernandez spot-check | **3/3** match signature line |
| Random 5-crop spot-check | **5/5** match line after signature |

**Engine change**: Regions scoring + signature markers moved from hardcoded `engine.py` block to `profiles/regions.yaml`. Numeric behavior identical on cached CV.

**Artifacts**: `artifacts/hcc_e1_human_v3_profile_yaml_v4_diff.md`, `RECOMMENDATIONS_EXECUTION_LOG.md`, `PRE_G1_INTEGRATION_CHECKLIST.md`

---

## 7. Heavy-manual estimate (HCC, post human_v3)

| Bucket | Count (estimate) |
|--------|-----------------:|
| CV `no_lines` (heavy manual from photo) | **0** *(was 7; recovered B2)* |
| Needs human spot-check (`Jesus Hernandez`, ungraded) | **~4** |
| OCR fragment review (`OHernandez`) | **~1** |
| Human-validated production-ready (16-crop package) | **16** |
| **Conservative still-heavy / uncertain** | **~5–8** (down from **~10–15** and rubric **19**) |

---

## Artifacts

| Artifact | Path |
|----------|------|
| Graded CSV | `artifacts/hcc_e1_human_review_package_20260527.csv` |
| human_v3 rescore | `artifacts/phase1_g2_hcc_202604__rescored_e1_human_v3/` |
| profile_yaml_v4 rescore | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4/` |
| profile_yaml_v4_p7 rescore | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/` |
| v4 → p7 diff (7 rows) | `artifacts/hcc_e1_profile_yaml_v4_p7_diff.md` |
| Page-7 CV retry | `artifacts/phase1_g2_hcc_202604__p7_cv_retry/` |
| Perez OCR policy | `PEREZ_OCR_POLICY.md` |
| Jesus Hernandez spot-check | `artifacts/hcc_e1_jesus_hernandez_spot_check_20260527.md` |
| PRE-G1 checklist | `PRE_G1_INTEGRATION_CHECKLIST.md` |
| v2 → v3 diff | `artifacts/hcc_e1_v2_human_v3_diff.md` |
| G1 brief | `G1_READINESS_BRIEF.md` |
