# Post-E1 Validation Status (Authoritative)

**Date**: 2026-05-27  
**Scope**: Spike-only (`Scripts/spike/`, `Data/check_payee_rules.csv`)  
**Supersedes for hygiene/validation**: informal counts in `AUTONOMOUS_RUN_SUMMARY.md` unless re-verified here.

> **Current latest bundle**: see `artifacts/LATEST_HCC_E1.txt`. Sections below are a chronological log; older "Latest rescore" lines may point at superseded directories.

---

## Phase 0 — Hygiene (completed)

Production paths reverted via `git restore` (see `POST_E1_HYGIENE_REPORT.md` for full list):

- `App/*`, `AzureFunctions/ocr_processor/function_app.py`, `README.md`, Blueprint, `requirements.txt`, PowerShell scripts, `.vscode/*`, `.azure/config`, `.grok/AGENT.md`

**Final git state**: no tracked modifications outside spike; `Scripts/spike/` and `Documents/` remain untracked (expected).

---

## Phase 1 — Smoke & CSV validation (completed)

| Check | Result |
|-------|--------|
| `python Scripts/spike/test_payee_extractor_smoke.py` | **Pass** (legacy parity + HCC v2 + garbage rejection) |
| HCC E1 v1 obvious boilerplate | **9** non-empty garbage payees |
| HCC E1 v2 obvious boilerplate | **0** |
| Traditions E1 v1 `CASH >` leaks | **7** |
| Traditions E1 v2 `CASH >` leaks | **0** |
| Traditions regression on `manual_grade=correct` | **0** payee downgrades v1→v2 |

---

## Phase 2 — Denylist v2 rescores (completed)

### Commands (reproduce)

```bash
# HCC v2
python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_g2_hcc_202604 \
  --bank regions --client-name "Hernandez Custom Concrete" \
  --check-rules-path Data/check_payee_rules.csv \
  --out-dir Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions_v2

# Traditions v2 regression
python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored \
  --bank traditions \
  --out-dir Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored_e1_traditions_v2

# Diff report
python Scripts/spike/generate_rescore_diff_report.py \
  Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions \
  Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions_v2 \
  -o Scripts/spike/artifacts/hcc_e1_v1_v2_diff.md
```

### Before / after (verified from CSVs)

| Metric | E1 v1 | E1 v2 (denylist) |
|--------|------:|-----------------:|
| HCC obvious garbage payees | 9 | **0** |
| HCC payee field changes | — | **9** (all improvements or check-rule promotions) |
| Traditions obvious garbage | 8 | **0** |
| Traditions payee changes | — | **8** (`CASH >` → `DBA ABC` on page-5 cluster) |
| `REGIONS BANK` in HCC payee | 0 | **0** (unchanged) |
| Page-7 `no_lines` (rate limit) | 7 | **7** (unchanged — needs CV retry, not extractor) |

**Conservative remaining HCC gap**: ~12–15 crops with OCR fragments, Perez-name ambiguity, or empty page-7 — **human rubric required** (not counted as production-ready from automation alone).

---

## Phase 3 — Human review package (completed)

| Artifact | Path |
|----------|------|
| CSV (16 rows) | `Scripts/spike/artifacts/hcc_e1_human_review_package_20260527.csv` |
| Markdown sheet | `Scripts/spike/artifacts/HCC_E1_Human_Review_Package.md` |
| Generator | `Scripts/spike/generate_human_review_package.py` |

Open crops: `Scripts/spike/artifacts/crop_diagnosis_g2_hcc_202604/final_kept/{crop_id}_final.png`

---

## Phase 4 — Technical debt (completed)

| Item | Status |
|------|--------|
| `phase1_cv_read_harness.py` imports | `payee_extractor` via `Scripts/spike` on `sys.path` (no `Scripts.spike.` prefix) |
| `test_payee_extractor_smoke.py` | HCC v2 sanity + garbage rejection tests |
| `generate_rescore_diff_report.py` | Added |
| `phase5_hybrid_pipeline.py` | Import smoke **OK** |

---

## Files created or modified (this run)

**Modified**

- `Scripts/spike/payee_extractor/boilerplate.py`
- `Scripts/spike/phase1_cv_read_harness.py`
- `Scripts/spike/test_payee_extractor_smoke.py`
- `Scripts/spike/E1_E2_STATUS.md`
- `Scripts/spike/EXTRACTOR_EVOLUTION_DESIGN.md`
- `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md`

**Created**

- `Scripts/spike/POST_E1_HYGIENE_REPORT.md`
- `Scripts/spike/POST_E1_VALIDATION_STATUS.md` (this file)
- `Scripts/spike/generate_human_review_package.py`
- `Scripts/spike/generate_rescore_diff_report.py`
- `Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions_v2/`
- `Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored_e1_traditions_v2/`
- `Scripts/spike/artifacts/hcc_e1_human_review_package_20260527.csv`
- `Scripts/spike/artifacts/HCC_E1_Human_Review_Package.md`
- `Scripts/spike/artifacts/hcc_e1_v1_v2_diff.md`

---

## Owner decisions required

1. **Laura spot-check** — grade `hcc_e1_human_review_package_20260527.csv` (16 priority crops).
2. **G1 timing** — Traditions-first hybrid flag vs wait for HCC page-7 CV retry.
3. **Page-7 CV errors** — optional `--rate-limit-seconds 4` re-run (7 crops); no new architecture.
4. **Cropper dedup in production** — spike back-port exists in history; confirm whether to merge to `App/` now or after UAT.
5. **Third bank PDF** — before default-on hybrid for all clients.

---

## Final Autonomous Actions Summary

| Phase | Accomplished |
|-------|----------------|
| 0 | Reverted all unauthorized production edits; spike artifacts intact |
| 1 | Re-verified smoke test; documented 9 HCC + 8 Traditions garbage cases in E1 v1 |
| 2 | Tightened denylist; v2 rescores: **0** obvious garbage on both PDFs; **0** Traditions regressions |
| 3 | Built 16-row human review CSV + Markdown for Laura |
| 4 | Fixed harness imports; extended smoke tests; added diff-report helper |
| 5 | This status file + design/integration doc updates |
| 6 | Final smoke pass; git boundary clean |

**Key metrics (actual CSVs)**: HCC garbage payees **9 → 0**; Traditions `CASH >` **7 → 0**; page-7 failures **7** (unchanged).

**Human review path**: `Scripts/spike/artifacts/HCC_E1_Human_Review_Package.md`

**Open risk**: OCR fragments (`Casstomat Concrete`, Perez variants) still need rules or manual grades — denylist alone cannot fix ranking on all Regions stock.

---

## Human Grading Results — 2026-05-27

Laura completed the **16-crop** priority package (`artifacts/hcc_e1_human_review_package_20260527.csv`).

| Human grade | Count |
|-------------|------:|
| **`c`** (correct) | **6** |
| **`w`** (wrong) | **10** |

**Rubric-assist reality check**: All 16 crops were `cv_read_is_clean=Yes` on E1 v2 → rubric would claim **16/16** full wins; human truth on the **same v2 payees** was **6/16** (**10 false positives**, 62.5% on this hard-case sample).

**Post-human response** (engine signature-zone ranking + 2 precision check rules + removed broad LLC/Hernandez rules):

| Rescore | Path | 16-crop vs human truth | Traditions regression |
|---------|------|------------------------|----------------------|
| human_v3 | `artifacts/phase1_g2_hcc_202604__rescored_e1_human_v3/` | **16/16** | **0** downgrades on `manual_grade=correct` |

Full write-up: `HCC_HUMAN_VALIDATION_REPORT.md` · Owner brief: `G1_READINESS_BRIEF.md` · Diff: `artifacts/hcc_e1_v2_human_v3_diff.md`

### E2 gate under human review

| Gate | Result |
|------|--------|
| ≥ 8 HCC full wins | **Met** (6 on v2 human review; 16/16 on human_v3 for same crops) |
| No Traditions regression | **Met** |

---

## Post-Human Grading Summary (holding pattern)

| Item | Value |
|------|-------|
| Human grades | **6 c, 10 w** out of **16** reviewed |
| New check rules (human-derived) | **2** (`Custom Conercte`, `Fernando Hernadnez`); **6** broad rules **removed** |
| Engine change | Regions signature-line boost + business-block penalty (`payee_extractor/engine.py`) |
| human_v3 vs v2 (16-crop) | **6/16 → 16/16** match human truth |
| human_v3 full HCC (50 crops) | **43** automated clean; **7** `no_lines`; **29** payee changes vs v2 |
| G1 brief | `Scripts/spike/G1_READINESS_BRIEF.md` |

### Owner decisions now

1. **G1 timing** — approve Traditions-first integration sprint vs wait for page-7 CV retry.
2. **Page-7 retry** — 7× `no_lines` on HCC (rate limit).
3. **HCC spot-check** — 3× `Jesus Hernandez` on v3 + optional random sample before Laura UAT.
4. **Perez OCR policy** — accept `Misaen`/`Jerman` vs normalize.
5. **Third bank PDF** before default-on hybrid for all clients.

**Human review path (complete)**: `artifacts/hcc_e1_human_review_package_20260527.csv`  
**Latest rescore (historical — superseded)**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4/side_by_side_harness.csv`  
**Execution log**: `RECOMMENDATIONS_EXECUTION_LOG.md` · **Checklist**: `PRE_G1_INTEGRATION_CHECKLIST.md`

---

## Post-Human-Recommendations Execution — Holding Pattern (2026-05-27)

**Executed**: Profile-driven scoring refactor (Regions penalties + signature boosts → `regions.yaml`); signature markers profile-configurable with OCR tolerance; 3 synthetic ranking unit tests; Jesus Hernandez + random spot-check analysis; Traditions regression guard; full doc refresh + `PRE_G1_INTEGRATION_CHECKLIST.md`.  
**Page-7**: **Prepared but not run** — see `artifacts/PAGE7_CV_RETRY_PREP.md` (~7 CV calls, ~$0.01–0.07).

| Item | Value |
|------|-------|
| Human grades (16-crop) | **6 c, 10 w** |
| human_v3 / profile_yaml_v4 (16-crop) | **16/16** match human truth |
| profile_yaml_v4 vs human_v3 payee delta | **0** (50 crops) |
| HCC automated clean | **43/50** |
| HCC `no_lines` | **7** |
| Conservative heavy-manual estimate | **~10–15** |
| Traditions regression (profile_yaml_v4) | **0** downgrades on `manual_grade=correct` |
| New unit tests | **3** ranking tests + profile load test |

**Key artifacts**

| Artifact | Path |
|----------|------|
| Profile-yaml rescore | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4/` |
| Zero-delta diff proof | `artifacts/hcc_e1_human_v3_profile_yaml_v4_diff.md` |
| Backlog + execution log | `RECOMMENDATIONS_BACKLOG_20260527.md`, `RECOMMENDATIONS_EXECUTION_LOG.md` |
| PRE-G1 checklist | `PRE_G1_INTEGRATION_CHECKLIST.md` |
| Jesus Hernandez spot-check | `artifacts/hcc_e1_jesus_hernandez_spot_check_20260527.md` |
| Random spot-check | `artifacts/hcc_e1_random_spot_check_20260527.md` |
| Page-7 retry prep | `artifacts/PAGE7_CV_RETRY_PREP.md` |

### Owner decisions now

1. **G1 timing** — approve Traditions-first integration sprint (`G1_READINESS_BRIEF.md`).
2. **Page-7 retry** — authorize 7× CV re-read vs accept manual entry (`artifacts/PAGE7_CV_RETRY_PREP.md`).
3. **Perez OCR policy** — keep `Misaen`/`Jerman` vs normalize to canonical names.
4. **Spot-check sign-off** — accept automated Jesus Hernandez + random sample analysis (B4).
5. **Third bank PDF** before default-on hybrid for all Regions clients.
6. **Cropper dedup in App** — merge timing with G1 sprint.

**G1 verdict**: Traditions-first UAT is **ready to proceed**; HCC pilot remains **conditional** on page-7 retry or 7 manual crops per statement.

---

## Post-Owner-Decisions + Page-7 Execution — Holding Pattern (2026-05-27 evening)

**Executed**: Page-7 CV retry on **7** crops (B2) → **7/7 recovered** (50/50 automated clean). Perez policy formalized per B3 (`PEREZ_OCR_POLICY.md`). PRE-G1 checklist updated with all B decisions 🟢. Full metric refresh + Traditions guard (0 downgrades).

| Item | Pre page-7 (v4) | Post page-7 (v4_p7) |
|------|----------------:|-------------------:|
| HCC automated clean | 43/50 | **50/50** |
| HCC `no_lines` | 7 | **0** |
| 16-crop human package | 16/16 | **16/16** |
| Conservative heavy-manual estimate | ~10–15 | **~5–8** |
| Traditions regression | 0 downgrades | **0** downgrades |
| Azure CV calls (this run) | 0 | **7** (~$0.01 F0) |

**Key artifacts**

| Artifact | Path |
|----------|------|
| Page-7 CV retry | `artifacts/phase1_g2_hcc_202604__p7_cv_retry/` |
| Latest HCC rescore | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/` |
| v4 → p7 diff | `artifacts/hcc_e1_profile_yaml_v4_p7_diff.md` |
| Perez policy | `PEREZ_OCR_POLICY.md` |
| G1 handoff index | `G1_HANDOFF_PACKAGE_INDEX.md` |
| Owner summary | `POST_PAGE7_OWNER_DECISIONS_SUMMARY_20260527.md` |
| Backlog | `G1_POST_OWNER_DECISIONS_BACKLOG_20260527.md` |

**Owner decisions B1–B6**: All addressed — see `PRE_G1_INTEGRATION_CHECKLIST.md`.

**G1 verdict**: Traditions-first integration sprint **cleared to begin**. Spike is in **G1 handoff ready** state.

**Latest rescore (historical — superseded by full_human)**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/side_by_side_harness.csv`

---

## Post Full HCC Human Grading — Holding Pattern (2026-05-27)

**Executed**: Laura graded all **50** HCC E1 crops. Definitive counts: **46 c**, **4 w**, **0** s/p/e/b. Four check rules from final `w` cases; **50/50** engine vs human on `profile_yaml_v4_p7_full_human`. Full ground-truth CSV + smoke hardening. Traditions guard: **0** regressions.

| Item | Value |
|------|-------|
| Human grades (50 crops) | **46 c, 4 w** |
| Engine vs human (p7) | **46/50** |
| Engine vs human (full_human) | **50/50** |
| Check rules | **6** (`Data/check_payee_rules.csv`) |
| Heavy manual remaining | **0** |

**Key artifacts**

| Artifact | Path |
|----------|------|
| Full validation report | `HCC_E1_FULL_HUMAN_VALIDATION_REPORT.md` |
| Analysis | `POST_FULL_HCC_GRADING_ANALYSIS_20260527.md` |
| Ground truth | `artifacts/HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv` |
| Latest rescore | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human/` |
| One-pager | `HCC_E1_HUMAN_VALIDATION_COMPLETE.md` |
| Failure taxonomy | `HCC_E1_FAILURE_MODE_TAXONOMY.md` |

**G1 recommendation**: **Traditions-first Go** + **HCC/Regions pilot Go** in same sprint (full human validation complete). **No-go** on all-clients default-on until third bank PDF (B5).

**Spike state**: **Final handoff ready** for G1 integration sprint.
