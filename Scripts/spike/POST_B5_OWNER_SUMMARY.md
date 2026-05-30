# Post-B5 Owner Summary — Pragmatic G1 Phase

**Date**: 2026-05-27  
**For**: Robert and Laura (~2 pages)  
**Technical detail**: `G1_READINESS_SNAPSHOT.md` · **Handoff**: `G1_HANDOFF_PACKAGE_INDEX.md`

---

## Where we actually stand (after B5)

We completed three major validation milestones:

1. **Traditions** (hard test PDF) — no payee regressions on human-graded correct crops. **Ready for G1 wiring.**
2. **Hernandez Custom Concrete / Regions** — Laura graded all **50** check crops; engine matches her payee truth **50/50** after **6** precise check rules. **Ready for a flagged HCC pilot in the same sprint.**
3. **Quality Choice Roofing / First Metro** (third PDF) — pipeline ran end-to-end; deposits **10/10**; checks only from **pages 9–10** (pages 5–8 had zero crops); **4 of 16** graded checks still have the wrong payee. **Validates our process; does not justify turning hybrid on for every client.**

The analysis-and-repair phase did its job. The valuable work now is **getting hybrid check-leg functionality into the real App** so Laura can run meaningful UAT — not perfecting every spike PoC.

---

## Recommended immediate next steps (next 1–2 weeks)

### Integration team (start now)

- Port the spike payee engine and wire **Traditions-first** behind a feature flag (production stays on strict EasyOCR until Laura approves).
- Add the hybrid check-leg branch per the integration plan; keep **default-off** in production.
- Include **HCC/Regions pilot** in the same sprint using the blessed `full_human` bundle and 6 check rules — no further spike tuning required for HCC.

### Spike team (parallel, limited)

- **Do not block G1** on FM-7/FM-9. Those are PoCs for the third-bank gaps (payer header line, imaging page detection).
- After App wiring begins: document how imaging-page detection feeds `SLAM_IMAGING_*` env vars; optional QCR rescore **after** Laura’s spot-check.

### Laura (short + one sprint)

| Action | When | Effort |
|--------|------|--------|
| Spot-check **4** remaining QCR wrong-payee crops | This week | ~15 min — `artifacts/qcr_b5_human_grades_20260527.csv` |
| **G3 UAT** — one full statement in wired App with hybrid mode | G1 week 2 | One real workflow |

### Robert

- Confirm **HCC pilot in same sprint** as Traditions (recommended).
- Decide **Azure CV tier** (F0 vs S1) before any production pilot.

---

## What we are explicitly NOT ready for yet

- **Default-on hybrid for all clients** — QCR proved cropper page-scope and payee-header issues on a new layout.
- **First Metro / QCR as a production pilot** — until imaging pages are wired in App and payee ranking is validated on Laura’s spot-check crops.
- **Removing the strict EasyOCR fallback** — hybrid remains opt-in per statement until G3 UAT passes.

---

## What we should stop spending time on

- Further HCC profile or rescore iterations (validation is complete).
- Gold-plating FM-7/FM-9 PoCs before App integration (helpful for QCR later, not a Traditions/HCC blocker).
- Additional bank PDFs before Laura UAT on wired software.
- Duplicating status metrics across many documents (use `G1_READINESS_SNAPSHOT.md`).

---

## Decisions we still need from you

| Decision | Recommendation |
|----------|----------------|
| HCC pilot same sprint as Traditions? | **Yes** (feature-flagged) |
| When to attempt First Metro pilot? | **After** G3 UAT + cropper page detection in App |
| Azure tier for production volume | Robert — before prod enable |

---

## One sentence

> **Ship G1 for Traditions and HCC now; keep hybrid opt-in; let Laura validate real App workflow; treat the third PDF as a lesson for later banks, not a reason to delay what’s already proven.**

Smoke regression: **passing** (15 tests, 2026-05-27).
