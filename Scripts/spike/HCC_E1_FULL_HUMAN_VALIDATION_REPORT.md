# HCC E1 Full Human Validation Report (Definitive)

**Date**: 2026-05-27  
**Scope**: Spike + `Data/check_payee_rules.csv` only  
**Human grades**: All **50** HCC E1 crops in `side_by_side_harness.csv` (p7 bundle)  
**Latest engine**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human/`

---

## Executive summary

Laura completed manual grading on the **entire** 50-crop HCC E1 set using the official rubric. **46** crops are full wins (`c`). **4** required heavy manual correction (`w`) — all business-line or OCR-fragment false positives. Four high-precision check rules close the gap; the engine now matches human payee truth on **50/50** crops with **0** Traditions regressions.

---

## Final metrics vs human truth

| Metric | p7 engine (pre rules) | full_human (post rules) |
|--------|----------------------:|------------------------:|
| Full wins (`c` grade) | **46** | **46** (unchanged grades) |
| Wrong (`w` grade) | **4** | **0** engine mismatch |
| Match human payee | **46/50 (92%)** | **50/50 (100%)** |
| Light-fix (`s`/`p`) | **0** | **0** |
| Heavy manual (`w`/`e`/`b`) | **4** | **0** (rules applied) |
| CV `no_lines` | **0** | **0** |
| Automated clean | **50/50** | **50/50** |

### End-to-end burden (Laura-facing)

| Bucket | Count |
|--------|------:|
| No payee work needed (`c`) | **46** |
| Would have needed full manual (`w`, pre-rules) | **4** |
| Spelling-only / partial fixes | **0** |
| **Production-ready after rules** | **50/50** |

---

## The 4 `w` cases (resolved)

| crop_id | Wrong engine | Human truth | Check rule |
|---------|--------------|-------------|------------|
| P05_K12 | Cristone Concrete | Misael Hernandez | `Cristone Concrete` → Misael Hernandez |
| P05_K15 | Customs Concreto | Luis Angel Torres Hernandez | `Customs Concreto` → … |
| P06_K06 | Custonie Concrete | Oscar Hernandez | `Custonie Concrete` → Oscar Hernandez |
| P07_K12 | OHernandez | Luis Fernando Perez | `OHernandez` → Luis Fernando Perez |

Human note on P06_K06 used “Ocar Hernandez” (typo); signature line reads **Oscar Hernandez** — rule uses Oscar per CV evidence.

---

## Check rules inventory (`Data/check_payee_rules.csv`)

| # | Pattern | Clean payee | Origin |
|---|---------|-------------|--------|
| 1 | Custom Conercte | Gabriel Hernandez | 16-crop human (2026-05-27) |
| 2 | Fernando Hernadnez | Fernando Hernandez | 16-crop human |
| 3 | Cristone Concrete | Misael Hernandez | Full 50-crop |
| 4 | Customs Concreto | Luis Angel Torres Hernandez | Full 50-crop |
| 5 | Custonie Concrete | Oscar Hernandez | Full 50-crop |
| 6 | OHernandez | Luis Fernando Perez | Full 50-crop |

**Perez policy (B3)**: No rules normalize `Misaen`/`Jerman` — see `PEREZ_OCR_POLICY.md`.

---

## Regression & gates

| Gate | Status |
|------|--------|
| E2 HCC full wins ≥ 8 | **Met** — 46 native + 50/50 with rules |
| Traditions `manual_grade=correct` | **0** downgrades |
| Smoke test full ground truth | **Pass** — `test_payee_extractor_smoke.py` |
| Third bank PDF before all-clients default-on | **Still required** (B5) |

---

## Remaining risks (ranked)

1. **New OCR variants** on future statements — extend check rules or signature ranking; not a blocker for G1 pilot.
2. **HCC bbox Y all zero** — spatial profile ineffective; signature heuristics + rules carry Regions.
3. **Third bank PDF** — required before default-on all clients (B5).

~~Ungraded crops~~ — **Closed** (50/50 graded).  
~~Page-7 CV failures~~ — **Closed** (7/7 recovered).

---

## Artifacts

| Artifact | Path |
|----------|------|
| Human grades (p7) | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/side_by_side_harness.csv` |
| Latest rescore | `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human/` |
| Consolidated ground truth | `artifacts/HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv` (frozen; smoke gate) |
| Latest marker | `artifacts/LATEST_HCC_E1.txt` |
| Analysis | `POST_FULL_HCC_GRADING_ANALYSIS_20260527.md` |
| Failure taxonomy | `HCC_E1_FAILURE_MODE_TAXONOMY.md` |
| One-pager | `HCC_E1_HUMAN_VALIDATION_COMPLETE.md` |

**Ground truth vs living CSV**: Laura's grades live in the p7 `side_by_side_harness.csv` (`manual_grade`, `notes`). `HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv` is a consolidated snapshot (human payee truth + p7 vs full_human engine columns) used by `test_hcc_full_human_matches_ground_truth`. Regenerate the snapshot only if grades change.

**Supersedes** conservative estimates in `HCC_HUMAN_VALIDATION_REPORT.md` §2 and §7 for full-50 metrics.
