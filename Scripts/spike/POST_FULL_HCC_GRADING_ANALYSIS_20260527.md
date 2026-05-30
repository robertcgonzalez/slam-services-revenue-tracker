# Post Full HCC Human Grading Analysis

**Date**: 2026-05-27  
**Source of truth**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7/side_by_side_harness.csv` (`manual_grade` + `notes` on all 50 rows)  
**Latest engine bundle**: `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human/`

---

## Grade counts (full 50-crop set)

| Code | Count | Meaning |
|------|------:|---------|
| **`c`** | **46** | Full win — engine payee matches human truth |
| **`w`** | **4** | Wrong — human `notes` = correct payee |
| **`s`** | **0** | Spelling cleanup only |
| **`p`** | **0** | Partial / light edit |
| **`e`** | **0** | Empty / illegible |
| **`b`** | **0** | Boilerplate false positive |

**Human-validated full wins (pre rules)**: **46/50 (92%)**  
**After 4 post-full-human check rules**: **50/50 (100%)** vs human payee truth

---

## Comparison to prior estimates

| Metric | Prior (16-crop + estimates) | Full human truth |
|--------|----------------------------|------------------|
| Human-reviewed crops | 16 | **50** |
| Full wins (`c`) | 6 on v2 sample → 16/16 post human_v3 | **46/50** on p7 engine |
| False automated wins | 10/16 on v2 hard sample | **4/50** on p7 (8% false positive rate) |
| Conservative heavy-manual | ~5–8 | **4** (all `w`; fixed by rules → **0** remaining) |
| Ungraded crops | 34 | **0** |

Page-7 CV recovery held: **50/50** automated clean, **0** `no_lines`.

---

## The 4 remaining `w` cases (engine vs human)

| crop_id | Page | Engine (p7) | Human truth (`notes`) | Failure mode |
|---------|-----:|---------------|----------------------|--------------|
| P05_K12 | 5 | Cristone Concrete | Misael Hernandez | Business-line OCR typo ranked over signature (`first_clean`) |
| P05_K15 | 5 | Customs Concreto | Luis Angel Torres Hernandez | Same; `AUTHORIELD SIGNATURE` OCR |
| P06_K06 | 6 | Custonie Concrete | Oscar Hernandez | Same; `AUTHORIZED SIONATURI` OCR |
| P07_K12 | 7 | OHernandez | Luis Fernando Perez | Header OCR fragment ranked over signature (`AUTHASITED SIGNATURE`) |

No `s`/`p`/`e`/`b` cases — remaining burden was exclusively **business-line / fragment over signature**, same family as the original 16-crop `w` set.

---

## Post-analysis actions (Phase 1)

| Action | Result |
|--------|--------|
| 4 high-precision check rules in `Data/check_payee_rules.csv` | All 4 `w` crops → human truth on rescore |
| `regions.yaml` business-block expansion | **Reverted** — caused ranking regression to signature-label lines |
| Traditions regression guard | **0** payee changes on `manual_grade=correct` |

---

## By page

| Page | `c` | `w` |
|------|----:|----:|
| 5 | 16 | 2 |
| 6 | 17 | 1 |
| 7 | 13 | 1 |

---

## Recurring failure modes (observed)

1. **Concrete business-line OCR variants** — `Cristone`, `Customs Concreto`, `Custonie` (not caught by earlier `Custom Conercte` rule).
2. **Signature-zone ranking loss** — `first_clean` picks printed business block before person name on signature line.
3. **OCR header fragments** — `OHernandez` treated as payee candidate.
4. **No new Perez/Hernandez person-confusion** in the final 34 crops beyond patterns already fixed in human_v3.

See `HCC_E1_FAILURE_MODE_TAXONOMY.md` for the living taxonomy.
