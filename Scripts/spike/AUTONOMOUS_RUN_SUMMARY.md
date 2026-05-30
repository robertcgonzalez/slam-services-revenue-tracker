# Extractor Evolution — Autonomous Run Summary

**Date**: 2026-05-27  
**Agent**: Cursor (full autonomous implementation per `CURSOR_PROMPT_EXTRACTOR_EVOLUTION_IMPLEMENTATION.md`)

---

## Accomplished

1. **E0** — Created `Scripts/spike/payee_extractor/` (engine, boilerplate, bank_detect, profiles, apply_check_rules). Legacy parity verified on Traditions cache.
2. **E1** — Global denylist, multi-candidate ranking, Y-band heuristic (Regions), spike-local clean gate extensions.
3. **Partial E2** — `bank_detect.py`, YAML profiles, `--bank` / `--client-name` / `--check-rules-path` on Phase 1 + Phase 5 harnesses.
4. **Check rules** — `Data/check_payee_rules.csv` (6 HCC seeds, gitignored).
5. **Zero-cost validation** — `--rescore` on HCC + Traditions artifacts with measured rubric-assist lift.
6. **Documentation** — Updated design doc, G2 summary, integration plan, spike report, PHASE7 catalog, this file + `E1_E2_STATUS.md`.

---

## Metrics (before → after E1)

| Corpus | Full wins | Heavy manual | Notes |
|--------|-----------|--------------|-------|
| **HCC (Regions)** | 0 → **31** | 28 → **19** | `REGIONS BANK` boilerplate 16 → **0** |
| **Traditions** | 11 → **≥15** | No regression on `correct` grades | 33/49 check payees unchanged |

---

## Commands executed

```bash
python Scripts/spike/test_payee_extractor_smoke.py

python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_g2_hcc_202604 \
  --bank regions --client-name "Hernandez Custom Concrete" \
  --check-rules-path Data/check_payee_rules.csv \
  --out-dir Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions

python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored \
  --bank traditions \
  --out-dir Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored_e1_traditions

ruff check --fix Scripts/spike/payee_extractor Scripts/spike/test_payee_extractor_smoke.py
ruff format Scripts/spike/payee_extractor Scripts/spike/test_payee_extractor_smoke.py
```

---

## Files created

| Path | Role |
|------|------|
| `Scripts/spike/payee_extractor/` | Shared extraction engine |
| `Scripts/spike/test_payee_extractor_smoke.py` | Legacy parity smoke |
| `Data/check_payee_rules.csv` | HCC fragment rules (gitignored) |
| `Scripts/spike/E1_E2_STATUS.md` | Measured lift + open questions |
| `Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions/` | HCC E1 rescore output |
| `Scripts/spike/artifacts/phase1_real_cv_read_harness_*__rescored_e1_traditions/` | Traditions regression rescore |

## Files modified

| Path | Change |
|------|--------|
| `Scripts/spike/phase1_cv_read_harness.py` | Thin wrapper + CLI flags |
| `Scripts/spike/phase5_hybrid_pipeline.py` | Bank/check-rules wiring |
| `Scripts/spike/EXTRACTOR_EVOLUTION_DESIGN.md` | Status + phased table |
| `Documents/g2_hcc_202604.md` | Page-7 diagnostic + E1 results |
| `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` | E2 gate + extractor cross-refs |
| `Spike-Report-Computer-Vision-Check-Leg-20260527.md` | Post-G2 addendum |
| `Scripts/spike/PHASE7_NOTES.md` | Script catalog |

**No changes** to `App/`, `AzureFunctions/`, or register parsing logic.

---

## Open questions (better understood)

| Question | Finding |
|----------|---------|
| Page-7 CV failures | **Rate limit**, not geometry — retry with slower throttle |
| BBox reliability | **Usable** at 300 DPI for Regions Y-band |
| Denylist effectiveness | **Primary lift** on HCC (eliminated all `REGIONS BANK` wins) |
| Client rules | **High ROI** for repeat fragments (`Hernandez`, `Custom Concrete`) |

---

## Human decisions required

1. Laura spot-check ~10 HCC E1 payees before UAT sign-off.
2. Re-run HCC CV for 7 rate-limited crops (optional before G1).
3. G1: Traditions-first hybrid flag vs wait for full E2 tuning.
4. Optional E5 LLM A/B on ~12 remaining wrong-line crops.

---

**Holding pattern**: Extractor evolution E0–E3 is implemented and measured. Highest-value next step is **Laura HCC spot-check** + **owner G1 timing**; technical work can continue via `--rescore` at zero Azure cost.
