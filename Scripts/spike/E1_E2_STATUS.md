# Extractor Evolution — E1/E2 Implementation Status

**Date**: 2026-05-27  
**Scope**: Spike-only (`Scripts/spike/payee_extractor/` + harness `--rescore`)  
**Post-E1 validation**: see `POST_E1_VALIDATION_STATUS.md` (denylist v2 + **human_v3** rescores)  
**Human validation**: `HCC_HUMAN_VALIDATION_REPORT.md` · **G1**: `G1_READINESS_BRIEF.md`

---

## What shipped

| Phase | Deliverable | Status |
|-------|-------------|--------|
| **E0** | `payee_extractor/` module + harness thin wrappers | **Complete** — legacy parity verified (`test_payee_extractor_smoke.py`) |
| **E1** | Global denylist, multi-candidate ranking, spike `_is_clean_payee` extensions | **Complete** |
| **E2 (partial)** | `bank_detect.py`, YAML profiles, `--bank` CLI | **Complete** (minimal profiles; not full tuning loop) |
| **E3 (thin)** | `Data/check_payee_rules.csv` + `apply_check_rules.py` | **Complete** — **2** human-precision rules after 2026-05-27 review (6 broad rules removed) |
| **Human gate** | 16-crop Laura review + `human_v3` rescore | **Complete** — **16/16** on review package; see below |

---

## Measured lift (`--rescore`, zero Azure cost)

### HCC (Regions) — `phase1_g2_hcc_202604` → `__rescored_e1_regions`

| Metric | Baseline (2026-05-27 G2) | After E1 + regions profile + check rules |
|--------|--------------------------|----------------------------------------|
| Automated `_is_clean_payee` | 43/43 succeeded (86%) | 43/43 (86%) — count unchanged; **content** improved |
| **`REGIONS BANK` false positives** | 16 crops | **0** |
| **Rubric-assist full wins (`c`)** | 0 | **31** |
| **Rubric-assist light (`s`/`p`)** | 22 | **0** (many promoted to full via rules + ranking) |
| **Rubric-assist heavy (`w`/`e`/`b`)** | 28 | **19** (12 wrong + 7 CV errors) |

**E1 target (heavy ≤20)**: **Met** (19).  
**E2 target (full wins ≥8)**: **Met** under human review — **6** confirmed on v2 payees; **16/16** on same crops after `human_v3` (rubric-assist **31** on full 50 was **overstated** on hard cases: **10/16** false positives on review sample).

### Human-validated 16-crop package (2026-05-27)

| Metric | E1 v2 | human_v3 |
|--------|------:|---------:|
| Match human truth | **6/16** | **16/16** |
| Human **`c`** / **`w`** | 6 / 10 | — |

### Traditions (hard PDF) — `__rescored` → `__rescored_e1_traditions`

| Metric | Baseline | After E1 + traditions profile |
|--------|----------|-------------------------------|
| Automated clean | 41/56 | 41/56 on checks with identical payee; **0 regressions** on human-graded `correct` rows |
| Full wins (checks, vs manual grades) | 11 | **≥15** (empty-anchor rows now extract e.g. Sherwin Williams) |
| Payee identical on checks | — | **33/49** unchanged |

**Traditions regression gate**: **Pass** — no downgrades on previously `correct` manual grades.

---

## Denylist + ranking — what it bought

1. **Boilerplate rejection** eliminated all 16 `REGIONS BANK` / security-line winners on HCC.
2. **Multi-candidate ranking + Y-band (Regions)** surfaced `Custom Concrete` / full names instead of first-line surname fragments when both exist in JSON.
3. **Check rules** (`Hernandez` → `Jesus Hernandez`, `Custom Concrete` → `Hernandez Custom Concrete LLC`) applied on **15** rescored crops (`+check_rule` reason suffix).
4. **Anchor variants** (`asper of`, `to vill`, truncated `pay`) increased anchor hits on Regions stock (7 `next_line` vs 2 baseline).

---

## Spatial bbox heuristic reliability

| PDF | Reliable? | Notes |
|-----|-----------|-------|
| **HCC (Regions)** | **Yes, with tuning** | Bank header Y≈0.10; payee band Y≈0.13–0.38 (`Custom Concrete`); signature names Y≈0.72 penalized. Enabled in `regions.yaml`. |
| **Traditions** | **Left off** | `traditions.yaml` keeps `spatial.enabled: false` to avoid regressions; anchor-window ranking sufficient. |

CV Read bbox Y-ordering was **consistent** on both G2 PDFs at 300 DPI; no blocking anomalies.

---

## Page-7 diagnostic (HCC)

Six of seven page-7 failures were **`Too Many Requests`** (F0 rate limit at tail of batch), not scan geometry. **Resolved 2026-05-27 evening**: 7-crop retry with `--rate-limit-seconds 4` + `--crop-ids` → **7/7 succeeded**, **50/50** automated clean on `profile_yaml_v4_p7`.

---

## Remaining gap to production-ready HCC

| Item | Count / action |
|------|----------------|
| CV Read errors (page 7 rate limit) | ~~7~~ **0** — retry complete (B2) |
| Wrong-line extractions after E1 | ~12 — handwritten / OCR garbage lines; Laura editor |
| E2 full profile tuning | Per-client vendor seeds, optional signature-zone disambiguation |
| G1 integration | Block on E2 gate doc + owner approval (see `POST_SPIKE_INTEGRATION_PLAN.md`) |

---

## v2 Denylist tightening results (2026-05-27, re-verified)

| Metric | E1 v1 (`__rescored_e1_regions`) | v2 (`__rescored_e1_regions_v2`) |
|--------|--------------------------------:|--------------------------------:|
| Obvious garbage payees (non-empty) | 9 | **0** |
| Payee field changes vs v1 | — | 9 (all garbage→better or check-rule) |
| Page-7 `no_lines` | 7 | 7 |

Traditions v2: **8** `CASH >` / security leaks fixed; **0** regressions on human `correct` grades.

Artifacts: `phase1_g2_hcc_202604__rescored_e1_regions_v2/`, `phase1_real_cv_read_harness_*__rescored_e1_traditions_v2/`, diff `artifacts/hcc_e1_v1_v2_diff.md`.

---

## Commands (reproduce)

```bash
# E0 smoke (legacy parity + HCC v2 + denylist rejection)
python Scripts/spike/test_payee_extractor_smoke.py

# HCC E1 rescore (latest denylist)
python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_g2_hcc_202604 \
  --bank regions --client-name "Hernandez Custom Concrete" \
  --check-rules-path Data/check_payee_rules.csv \
  --out-dir Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_regions_v2

# Traditions regression rescore
python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored \
  --bank traditions \
  --out-dir Scripts/spike/artifacts/phase1_real_cv_read_harness_20260526T195813Z__rescored_e1_traditions_v2
```

---

## Human decisions still required

1. ~~**G1 timing**~~ — **Approved B1** — Traditions-first sprint cleared (`G1_HANDOFF_PACKAGE_INDEX.md`).
2. ~~**Page-7 CV retry**~~ — **Done B2** — 7/7 recovered.
3. **Spot-check sign-off** — **Accepted B4**; optional Laura confirm on 4× ungraded `Jesus Hernandez`.
4. **Perez OCR policy** — **Locked B3** — `PEREZ_OCR_POLICY.md`.
5. **Third bank PDF** before default-on hybrid for all clients (B5).

## Profile-yaml refactor (2026-05-27)

Regions signature-zone scoring moved from hardcoded `engine.py` to `profiles/regions.yaml`. Verified **0** payee delta vs human_v3 on 50 HCC crops; **0** Traditions downgrades.

```bash
python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_g2_hcc_202604 \
  --bank regions --client-name "Hernandez Custom Concrete" \
  --check-rules-path Data/check_payee_rules.csv \
  --out-dir Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_profile_yaml_v4_p7
```

## Commands (page-7 CV retry — executed B2)

```bash
python Scripts/spike/phase1_cv_read_harness.py --real \
  --rate-limit-seconds 4 --no-easyocr \
  --harness-dir Scripts/spike/artifacts/crop_diagnosis_g2_hcc_202604 \
  --crop-ids "P06_K12_w786_h342_a2.30,P07_K02_w792_h331_a2.39,..." \
  --bank regions --client-name "Hernandez Custom Concrete" \
  --check-rules-path Data/check_payee_rules.csv \
  --out-dir Scripts/spike/artifacts/phase1_g2_hcc_202604__p7_cv_retry
# Then merge raw_cv_responses → phase1_g2_hcc_202604 and --rescore to v4_p7
```

## Commands (human_v3 baseline)

```bash
python Scripts/spike/phase1_cv_read_harness.py --rescore \
  Scripts/spike/artifacts/phase1_g2_hcc_202604 \
  --bank regions --client-name "Hernandez Custom Concrete" \
  --check-rules-path Data/check_payee_rules.csv \
  --out-dir Scripts/spike/artifacts/phase1_g2_hcc_202604__rescored_e1_human_v3
```
