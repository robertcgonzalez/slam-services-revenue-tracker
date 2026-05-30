# G1 Handoff Package Index — Spike → Integration Sprint

**Date**: 2026-05-27 (pragmatic G1 prep — post B5 + full HCC human validation)  
**Audience**: App wiring team  
**Boundary**: `Scripts/spike/` + `Data/check_payee_rules.csv` only  
**Read first**: `artifacts/LATEST_HCC_E1.txt` → **`G1_READINESS_SNAPSHOT.md`** (honest state)

---

## Consume today vs needs spike work

| Status | Items |
|--------|--------|
| **Consume today** | `payee_extractor/` · `traditions.yaml` · `regions.yaml` · `Data/check_payee_rules.csv` (6 rules) · `…_p7_full_human/` bundle · `HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv` · `PEREZ_OCR_POLICY.md` · `test_payee_extractor_smoke.py` · `POST_SPIKE_INTEGRATION_PLAN.md` |
| **Spike before QCR pilot only** | FM-9 App imaging env · FM-7 QCR rescore after Laura 4× `w` · `first_metro.yaml` tuning |
| **Not for G1 sprint** | Default-on all clients · additional bank PDFs · FM-8 |

---

## How G1 consumes this spike

| Step | What to wire |
|------|----------------|
| 1 | Port `payee_extractor/` (`engine.py`, `boilerplate.py`, `apply_check_rules.py`, `profiles/`) |
| 2 | **Traditions**: `profiles/traditions.yaml` — feature flag; HCC default-off until pilot flag |
| 3 | **HCC pilot**: `profiles/regions.yaml` + rescore bundle `…_p7_full_human/` |
| 4 | **Rules**: `Data/check_payee_rules.csv` (**6** rows) |
| 5 | **Policy**: `PEREZ_OCR_POLICY.md` (B3) |
| 6 | **Gate**: `python Scripts/spike/test_payee_extractor_smoke.py` (**15** active) |
| 7 | **Ground truth**: `artifacts/HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv` |

Human grades: `…_p7/side_by_side_harness.csv` (`manual_grade`, `notes`). Ground-truth CSV is frozen for tests; regenerate only if grades change.

---

## Key metrics (definitive)

| Metric | full_human (wire this) |
|--------|-------------------------:|
| Human `c` / `w` | 46 / 4 (grades unchanged; 0 heavy manual after rules) |
| Engine vs human | **50/50** |
| HCC automated clean | 50/50 |
| Traditions regression | 0 downgrades |
| Check rules | **6** |
| Smoke (2026-05-27) | **PASS** (15 active) |

---

## Primary artifacts (read in order)

| # | Document | Purpose |
|---|----------|---------|
| 0 | **`G1_READINESS_SNAPSHOT.md`** | **Honest state** — ready / risky / stop-doing |
| 1 | `HCC_E1_HUMAN_VALIDATION_COMPLETE.md` | One-page HCC go |
| 2 | `G1_READINESS_BRIEF.md` | Owner gate table |
| 3 | `G1_IMPLEMENTATION_ROADMAP.md` | Week-by-week sequencing |
| 4 | `POST_B5_OWNER_SUMMARY.md` | Robert / Laura summary |
| 5 | `POST_SPIKE_INTEGRATION_PLAN.md` | G1 sprint 3.1–3.5 |
| 6 | `G1_INTEGRATION_SPRINT_SPIKE_DELIVERABLES.md` | Code inventory |
| 7 | `PRE_G1_INTEGRATION_CHECKLIST.md` | Sign-off checklist |
| 8 | `FM7_FM9_SPIKE_NOTES.md` | PoC design (not G1 blocker) |
| 9 | `QCR_B5_VALIDATION_REPORT.md` | Third PDF (B5) |
| 10 | `HCC_E1_FAILURE_MODE_TAXONOMY.md` | Future PDF risks |

---

## B5 third bank PDF

| Item | Path |
|------|------|
| Report | `QCR_B5_VALIDATION_REPORT.md` |
| Human grades | `artifacts/qcr_b5_human_grades_20260527.csv` |
| Rescore (`regions`) | `artifacts/phase1_qcr_202604_b5__rescored_regions/` |

**Verdict**: B5 process **met**; all-clients default-on **not cleared**. Optional QCR pilot **after** UAT + FM-9 in App.

---

## Rescore bundles (latest)

| Bundle | Path |
|--------|------|
| **HCC — wire this** | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human/` |
| Human grades source | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/side_by_side_harness.csv` |
| Ground truth CSV | `artifacts/HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv` |
| Traditions guard | `artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored_e1_traditions_full_human_guard/` |

---

## Go / no-go

| Item | Decision |
|------|----------|
| Start Traditions-first G1 | **Go** |
| Wire HCC/Regions pilot (flagged) | **Go** |
| Default-on all clients | **No-go** |
| Block G1 on FM-7/FM-9 PoC completion | **No** — parallel only |
| QCR / First Metro pilot | **After** G3 UAT + imaging in App |

---

**Spike state**: Handoff **ready** for integration sprint. Execution phase: App wiring + Laura UAT.
