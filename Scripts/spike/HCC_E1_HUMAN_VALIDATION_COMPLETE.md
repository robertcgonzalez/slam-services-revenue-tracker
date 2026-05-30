# HCC E1 Human Validation — Complete

**Date**: 2026-05-27  
**Status**: **Complete** — Laura graded all **50** HCC E1 crops; spike closed the last **4** gaps with check rules.

---

## One-line result

**46** full wins out of the box, **4** signature-vs-business false positives (now rule-fixed) → **50/50** engine match to human payee truth; **0** Traditions regressions.

---

## Numbers for the integration sprint

| Metric | Value |
|--------|------:|
| Crops human-graded | 50/50 |
| Native full wins (`c`) | 46 |
| Heavy manual (`w`, before rules) | 4 |
| Engine vs human (latest rescore) | **50/50** |
| HCC `no_lines` | 0 |
| Check rules (Regions/HCC) | 6 |
| Traditions regression | 0 |

---

## Go / no-go (HCC/Regions pilot)

| Criterion | Verdict |
|-----------|---------|
| Human validation complete | **Go** |
| Smoke + ground-truth tests | **Go** |
| Traditions-first G1 (B1) | **Go** — approved |
| HCC in same sprint as optional pilot | **Go** — recommend **include** with `full_human` bundle + 6 rules |
| Default-on all clients | **No-go** — B5 QCR tested 2026-05-27; cropper + payee gaps remain |
| Third bank PDF (B5) | **Done** — see `QCR_B5_VALIDATION_REPORT.md` |

---

## Owner decisions still open

1. **Laura** — spot-check 4 QCR `w` crops; G3 UAT on wired App.  
2. **Cropper dedup in App** (B6) + FM-9 imaging-page detection — parallel with G1.  
3. **FM-7 payer header** — spike implemented; validate on QCR before First Metro pilot.

---

## Start here

1. `artifacts/LATEST_HCC_E1.txt`  
2. `G1_HANDOFF_PACKAGE_INDEX.md`  
3. `artifacts/HCC_E1_FULL_HUMAN_GROUND_TRUTH.csv`  
4. `artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7_full_human/`  
5. `python Scripts/spike/test_payee_extractor_smoke.py`
