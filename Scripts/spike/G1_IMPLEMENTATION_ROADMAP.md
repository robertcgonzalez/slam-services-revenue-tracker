# G1 Implementation Roadmap (Pragmatic — Post-B5)

**Date**: 2026-05-27  
**Status**: Execute — integration-first, spike parallel non-blocking  
**Audience**: Integration sprint, Robert, Laura  
**Current state**: `G1_READINESS_SNAPSHOT.md`

---

## Executive direction

| Track | Decision |
|-------|----------|
| **G1 integration** | **Start now** — Traditions-first + HCC/Regions pilot (same sprint, flagged) |
| **Spike parallel** | FM-9 design + optional QCR rescore **after** Laura spot-check — **do not block G1** |
| **FM-7 / FM-9** | PoC in spike; honest: **not validated** for QCR in App |
| **Default-on all clients** | **No** until G3 UAT + App imaging scope + QCR payee re-check |
| **Laura** | 4× QCR `w` spot-check (this week) · G3 UAT (week 2) |

---

## Consume today vs spike still owed

| Consume today (integration) | Spike still owed (non-blocking for Traditions/HCC) |
|-----------------------------|-----------------------------------------------------|
| `payee_extractor/` + profiles | FM-9 → `SLAM_IMAGING_*` App wiring |
| `full_human` HCC bundle + 6 rules | FM-7 QCR `--rescore` after Laura |
| `test_payee_extractor_smoke.py` | QCR re-crop with detected page range |
| `POST_SPIKE_INTEGRATION_PLAN.md` §3 | `first_metro.yaml` pilot only |

---

## Week 1 — Integration-led

| Day | Integration team (priority) | Spike (if bandwidth) |
|-----|----------------------------|----------------------|
| 1–2 | Port `payee_extractor/`; feature flag; Traditions profile | — |
| 3 | Hybrid `check_leg_mode`; CV cache path for CI | Document FM-9 → env var mapping |
| 4 | HCC pilot: `regions.yaml` + 6 rules + `full_human` | — |
| 5 | Regression: hard PDF, smoke, harness reuse | — |

**Gate**: Smoke **15/15** green before merge.

---

## Week 2 — UAT-led

| Owner | Work |
|-------|------|
| **Laura** | G3 UAT one Traditions (or agreed) statement; hybrid opt-in |
| **Integration** | Cropper dedup merge (B6); prod flag **OFF** |
| **Spike** | Optional QCR rescore with FM-7 after Laura 4× `w` sign-off |
| **Spike** | Re-run FM-9 on QCR; compare crop count to bank summary |

---

## Week 3+ — Deferred (not G1 blockers)

- First Metro / QCR production pilot
- FM-8 amount-in-words
- Default-on all clients
- S1 tier / Function offload (G4)
- Option B schema sprint

---

## Spike vs G1 ownership

| Item | Integration (now) | Spike (parallel / later) |
|------|-------------------|--------------------------|
| Payee engine + Traditions/HCC profiles | **Port & wire** | — |
| HCC 50/50 + 6 rules | **Wire** | — |
| Hybrid pipeline + UI flag | **G1 sprint** | — |
| FM-7 payer penalty | Port `engine.py` + profiles | QCR rescore validation |
| FM-9 imaging pages | Set static pages for Traditions/HCC | Auto-detect → App env |
| QCR / third bank | — | Pilot after UAT |
| App UI | **G1 only** | **No** spike App changes |

---

## Production-grade today vs risky

| Ready today | Risky / defer |
|-------------|---------------|
| Traditions payee (0 downgrades) | QCR payee (4/16 material `w`) |
| HCC 50/50 + 6 rules | Cropper pages 5–8 on First Metro layout |
| Deposit classifier QCR 10/10 | FM-7/FM-9 without App validation |
| Engine + smoke + handoff bundles | Default-on all clients |

---

## References

| Doc | Role |
|-----|------|
| `G1_READINESS_SNAPSHOT.md` | Honest state + stop-doing + open questions |
| `POST_SPIKE_INTEGRATION_PLAN.md` | Sprint 3.1–3.5 checklist |
| `G1_HANDOFF_PACKAGE_INDEX.md` | Paths |
| `POST_B5_OWNER_SUMMARY.md` | Robert / Laura summary |
| `FM7_FM9_SPIKE_NOTES.md` | FM-7 / FM-9 design (PoC) |
