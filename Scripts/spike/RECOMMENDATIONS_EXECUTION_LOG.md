# Recommendations Execution Log — 2026-05-27

**Prompt**: `CURSOR_PROMPT_POST_HUMAN_RECOMMENDATIONS.md`  
**Executor**: Cursor agent (spike-only)

---

## Phase 0 — Synthesis

- Read all required artifacts in order.
- Produced `RECOMMENDATIONS_BACKLOG_20260527.md` (consolidated backlog).

---

## Phase 1 — Profile-driven scoring + signature robustness

**Changes**

| File | Change |
|------|--------|
| `payee_extractor/profiles/regions.yaml` | Added `signature_markers`, `scoring` blocks |
| `payee_extractor/engine.py` | `ScoringConfig`, `SignatureMarkers` dataclasses; YAML-driven `_score_candidate`; profile-based `_find_authorized_signature_index` |
| `test_payee_extractor_smoke.py` | +3 synthetic ranking tests + profile load test |

**Proof**

| Check | Result |
|-------|--------|
| human_v3 → profile_yaml_v4 payee diffs (50 crops) | **0** |
| 16-crop vs human truth on v4 | **16/16** |
| Traditions downgrades on `manual_grade=correct` | **0** |
| Smoke test (incl. human_v3 gate) | **Pass** |

**Artifact**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4/`  
**Diff**: `artifacts/hcc_e1_human_v3_profile_yaml_v4_diff.md` (0 changed rows)

---

## Phase 2 — Preparatory actions

- **Jesus Hernandez spot-check**: `artifacts/hcc_e1_jesus_hernandez_spot_check_20260527.md` — 3/3 match signature line in raw CV.
- **Random sample**: `artifacts/hcc_e1_random_spot_check_20260527.md` — 5/5 payees match line after signature marker.
- **Page-7 prep**: `artifacts/PAGE7_CV_RETRY_PREP.md` — command + cost estimate; **not executed**.
- **Checklist**: `PRE_G1_INTEGRATION_CHECKLIST.md` created.

---

## Phase 3 — Page-7 CV retry

**Status**: **Prepared, not run** (owner decision B2 required; zero Azure spend policy for autonomous execution).

---

## Phase 4 — Validation refresh

| Metric | Value (profile_yaml_v4) |
|--------|-------------------------|
| HCC total crops | 50 |
| Automated clean (`cv_read_is_clean=Yes`) | **43** |
| `no_lines` (page-7 rate limit) | **7** |
| 16-crop human-validated | **16/16** |
| Conservative heavy-manual estimate | **~10–15** |

---

## Phase 5 — Documentation

Updated: `POST_E1_VALIDATION_STATUS.md`, `G1_READINESS_BRIEF.md`, `HCC_HUMAN_VALIDATION_REPORT.md`, `E1_E2_STATUS.md`, `EXTRACTOR_EVOLUTION_DESIGN.md`, `POST_SPIKE_INTEGRATION_PLAN.md`, `PRE_G1_INTEGRATION_CHECKLIST.md`.

---

## Phase 6 — Verification

```bash
python Scripts/spike/test_payee_extractor_smoke.py  # Pass
git status --short  # Scripts/spike/ + Data/ only
```

---

## Post-Owner-Decisions + Page-7 Execution (2026-05-27 evening)

**Prompt**: `CURSOR_PROMPT_G1_INTEGRATION_PREP_PAGE7.md`

### Owner decisions (B1–B6)

| ID | Status |
|----|--------|
| B1 Traditions-first G1 | **Approved** |
| B2 Page-7 CV retry | **Executed** — 7/7 recovered |
| B3 Perez OCR policy | **Locked** — `PEREZ_OCR_POLICY.md` |
| B4 Spot-check | **Accepted** |
| B5 Third bank PDF | **Agreed** |
| B6 Cropper dedup | **Agreed** |

### Phase 1 — Page-7 CV retry

| Item | Result |
|------|--------|
| Azure CV calls | **7** (~61s, F0 ~$0.01) |
| Crops recovered | **7/7** (all `no_lines` → payee extracted) |
| Artifact | `artifacts/phase1_g2_hcc_202604__p7_cv_retry/` |
| Harness change | Added `--crop-ids` filter to `phase1_cv_read_harness.py` |

### Phase 2 — Rescore + validation

| Metric | Before (v4) | After (v4_p7) |
|--------|------------:|--------------:|
| HCC automated clean | 43/50 | **50/50** |
| `no_lines` | 7 | **0** |
| 16-crop human package | 16/16 | **16/16** |
| Heavy-manual estimate | ~10–15 | **~5–8** |
| Traditions regression | 0 | **0** |

**Artifacts**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/`, `artifacts/hcc_e1_profile_yaml_v4_p7_diff.md`

### Phase 3–6 — Documentation + tests

- Created: `PEREZ_OCR_POLICY.md`, `G1_HANDOFF_PACKAGE_INDEX.md`, `G1_INTEGRATION_SPRINT_SPIKE_DELIVERABLES.md`, `POST_PAGE7_OWNER_DECISIONS_SUMMARY_20260527.md`, `G1_POST_OWNER_DECISIONS_BACKLOG_20260527.md`
- Updated: `PRE_G1_INTEGRATION_CHECKLIST.md`, `G1_READINESS_BRIEF.md`, `HCC_HUMAN_VALIDATION_REPORT.md`, `POST_E1_VALIDATION_STATUS.md`, `E1_E2_STATUS.md`, `POST_SPIKE_INTEGRATION_PLAN.md`, `EXTRACTOR_EVOLUTION_DESIGN.md`
- Smoke tests: +2 (`test_hcc_p7_matches_review_package`, `test_perez_ocr_spellings_not_in_check_rules`) — **pass**

**G1 state**: **Handoff ready**

