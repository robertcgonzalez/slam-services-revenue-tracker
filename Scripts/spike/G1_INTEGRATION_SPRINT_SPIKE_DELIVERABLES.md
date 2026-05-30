# G1 Integration Sprint — Spike Deliverables

**Date**: 2026-05-27 (pragmatic prep)  
**For**: App wiring team (Traditions-first + optional HCC pilot)  
**State doc**: `G1_READINESS_SNAPSHOT.md`  
**Not included**: Any changes under `App/` — integration sprint owns App wiring

---

## Ready to port today

| Module | Path | Notes |
|--------|------|-------|
| `engine.py` | `payee_extractor/` | Profile-driven scoring; FM-7 penalty in engine |
| `profiles/traditions.yaml` | — | **Production-grade** for G1 |
| `profiles/regions.yaml` | — | **Production-grade** for HCC pilot |
| `apply_check_rules.py` | — | + `Data/check_payee_rules.csv` (6 rows) |
| `boilerplate.py` | — | Denylist + guards |
| `bank_detect.py` | — | `auto` bank selection |

**Smoke gate**: `python Scripts/spike/test_payee_extractor_smoke.py` — **15 active, PASS 2026-05-27**

---

## Pilot-only / PoC (do not block Traditions/HCC)

| Module | Ready? | Notes |
|--------|--------|-------|
| `profiles/first_metro.yaml` | Pilot later | QCR — not G1 wire |
| FM-7 payer penalty | PoC in engine | QCR rescore not re-validated |
| FM-9 `--detect-imaging-pages` | PoC in harness | Not App-wired |

---

## Harness tooling (regression / ops)

| Script | G1 use |
|--------|--------|
| `phase1_cv_read_harness.py` | CV Read + `--rescore` ($0 regression) |
| `generate_rescore_diff_report.py` | Payee diffs |
| `diagnose_check_deposit_cropper.py` | Dedup (B6 merge) + FM-9 PoC |

---

## Validated behavior

| Client / bank | Evidence | G1? |
|---------------|----------|-----|
| Traditions | 0 downgrades; legacy smoke | **Yes — lead** |
| HCC / Regions | 50/50 + 6 rules; `full_human` bundle | **Yes — pilot** |
| Perez spellings | `PEREZ_OCR_POLICY.md` | **Binding** |
| QCR / First Metro | `QCR_B5_VALIDATION_REPORT.md` | **No** (optional later) |

---

## Recommended wiring sequence

1. Port `payee_extractor` (shared module path TBD in integration PR).
2. Hybrid branch + feature flag; prod **OFF**.
3. Traditions profile + hard PDF regression.
4. HCC pilot: `regions.yaml` + 6 rules + `full_human` bundle (`artifacts/LATEST_HCC_E1.txt`).
5. Cropper dedup from spike harness (B6).
6. **Defer**: First Metro, default-on, FM-9 auto-detect until post–G3 UAT.

---

**Index**: `G1_HANDOFF_PACKAGE_INDEX.md` · **Roadmap**: `G1_IMPLEMENTATION_ROADMAP.md`
