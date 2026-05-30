# Pre-G1 Integration Readiness Checklist

**Date**: 2026-05-27 (pragmatic G1 prep)  
**Audience**: Robert / Laura / integration team  
**Snapshot**: `G1_READINESS_SNAPSHOT.md`  
**Latest marker**: `artifacts/LATEST_HCC_E1.txt`

Legend: 🟢 green · 🟡 yellow (PoC / parallel) · 🔴 red

---

## E1 / E2 gates

| Item | Status | Evidence |
|------|--------|----------|
| E2 HCC full wins ≥ 8 | 🟢 | 46 native + **50/50** with rules |
| Traditions regression | 🟢 | 0 downgrades |
| Laura full 50-crop review | 🟢 | `p7/side_by_side_harness.csv` |
| Smoke + ground truth | 🟢 | **15** active — **PASS** 2026-05-27 |
| G1 integration approval (B1) | 🟢 | Traditions-first **cleared** |
| FM-7 payer header | 🟡 | Engine PoC — **not** QCR-rescore validated; **not** G1 blocker |
| FM-9 imaging pages | 🟡 | Harness PoC — **not** App-wired; **not** G1 blocker |

---

## Technical readiness (G1 approved scope)

| Item | Status | Evidence |
|------|--------|----------|
| Profile-driven scoring | 🟢 | `regions.yaml`, `traditions.yaml` |
| Check rules | 🟢 | 6 rules — `Data/check_payee_rules.csv` |
| Page-7 CV cache | 🟢 | 7/7 recovered |
| HCC blessed bundle | 🟢 | `…_p7_full_human/` |
| App hybrid branch (3.2 pipeline) | 🟢 | Validated locally 2026-05-27 (`App/hybrid_cv_check_leg.py` + smoke); heavy-OCR policy is local Windows only (v2.44.16). See Blueprint v2.44.13 Change Log. |
| QCR / First Metro pilot | 🔴 | B5 validated; pilot deferred |

---

## Metrics (definitive)

| Metric | Value |
|--------|------:|
| Human c / w | 46 / 4 |
| Engine vs human (full_human) | **50/50** |
| Heavy manual remaining | **0** |

---

## Owner sign-off (B1–B6)

- [x] **B1** Traditions-first G1 — Approved  
- [x] **B2** Page-7 CV retry — Done  
- [x] **B3** Perez OCR policy — Locked  
- [x] **B4** Spot-checks — Accepted  
- [x] **B5** Third bank PDF — Validated 2026-05-27; **default-on: not cleared**  
- [x] **B6** Cropper dedup with G1 — Agreed (merge in sprint)

---

## G1 verdict

| Scope | Status |
|-------|--------|
| Traditions-first | 🟢 **Go — wire now** |
| HCC/Regions pilot | 🟢 **Go — same sprint, flagged** |
| Default-on all clients | 🔴 **No-go** |
| Block on FM-7/FM-9 | 🔴 **Do not** — parallel spike only |

**Handoff**: `G1_HANDOFF_PACKAGE_INDEX.md` · **Roadmap**: `G1_IMPLEMENTATION_ROADMAP.md` · **Owners**: `POST_B5_OWNER_SUMMARY.md`
