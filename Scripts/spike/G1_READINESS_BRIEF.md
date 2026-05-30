# G1 Readiness Brief — Hybrid Check Leg (Owner)

**Date**: 2026-05-27 (pragmatic G1 prep)  
**Audience**: Robert / Laura  
**Full snapshot**: `G1_READINESS_SNAPSHOT.md` · **Owner narrative**: `POST_B5_OWNER_SUMMARY.md`

---

## Verdict (one line)

**Traditions-first G1: go. HCC/Regions pilot: go (flagged). Default-on all clients: no. QCR/First Metro: later.**

---

## Design gates

| Gate | Target | Status |
|------|--------|--------|
| E1 heavy manual (HCC) | ≤ 20 | **Met** — 0 after 6 rules |
| E2 HCC full wins | ≥ 8 | **Met** — 46 native `c` + 50/50 |
| Traditions regression | None on `correct` | **Met** |
| Full HCC human validation | 50 crops | **Done** 2026-05-27 |
| G1 App wiring | B1 approved | **Integration starts now** |
| Third bank PDF (B5) | Process before default-on | **Done** — default-on **not** cleared |
| Laura G3 UAT | Wired App | **Pending** (week 2) |

---

## HCC metrics (definitive)

| Metric | Value |
|--------|------:|
| Human grades | 46 c / 4 w |
| Engine vs human (`full_human`) | **50/50** |
| CV `no_lines` | **0** |
| Check rules | **6** |
| Smoke | **PASS** (15 active) |

---

## Risks (honest)

| Risk | G1 blocker? |
|------|-------------|
| New Regions OCR variants | No — extend rules post-pilot |
| QCR cropper page scope (FM-9) | No for Traditions/HCC; **yes** for QCR pilot |
| QCR payer header (FM-7) | No for Traditions/HCC; **yes** for QCR pilot |
| FM-7/FM-9 PoCs incomplete in App | No for approved G1 scope |

---

## Recommended path

| Option | Recommendation |
|--------|----------------|
| Traditions-first | **Proceed now** |
| HCC same sprint | **Yes** — flagged pilot |
| Third bank / default-on | **Defer** |
| Laura | 4× QCR spot-check + G3 UAT week 2 |

**Detail**: `G1_READINESS_SNAPSHOT.md` · **Checklist**: `PRE_G1_INTEGRATION_CHECKLIST.md`
