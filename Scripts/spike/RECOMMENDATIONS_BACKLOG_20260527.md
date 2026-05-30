# Post-Human-Grading Recommendations Backlog — 2026-05-27

**Source**: Human grades (16 crops) + `HCC_HUMAN_VALIDATION_REPORT.md` + `G1_READINESS_BRIEF.md` + Grok augmentations  
**Status**: Executed in this run (see `RECOMMENDATIONS_EXECUTION_LOG.md`)

---

## (a) Autonomous — executed

| # | Item | Priority | Status |
|---|------|----------|--------|
| A1 | Profile-driven scoring (Regions penalties + signature boosts → `regions.yaml`) | P0 | **Done** — 0 payee delta vs human_v3 |
| A2 | Signature markers profile-configurable + OCR tolerance (`SIONATURE`, `SIGNALILL`) | P0 | **Done** |
| A3 | Synthetic ranking unit tests (3 tests in smoke suite) | P0 | **Done** |
| A4 | Traditions regression guard rescore | P0 | **Done** — 0 downgrades on `manual_grade=correct` |
| A5 | Spot-check 3× `Jesus Hernandez` from existing CSV/JSON | P1 | **Done** — all match signature line |
| A6 | Random 5-crop spot-check from ungraded set | P1 | **Done** — all payees match line after signature |
| A7 | `PRE_G1_INTEGRATION_CHECKLIST.md` | P1 | **Done** |
| A8 | Page-7 CV retry command + cost justification (prepared, not run) | P1 | **Done** — see `artifacts/PAGE7_CV_RETRY_PREP.md` |
| A9 | Validation refresh + doc cross-references | P1 | **Done** |

---

## (b) Owner decision — materials prepared

| # | Decision | Material | Recommended default |
|---|----------|----------|---------------------|
| B1 | **G1 timing** — Traditions-first integration sprint | `G1_READINESS_BRIEF.md`, `PRE_G1_INTEGRATION_CHECKLIST.md` | **Proceed** Traditions-first |
| B2 | **Page-7 CV retry** — 7× `no_lines` | `artifacts/PAGE7_CV_RETRY_PREP.md` | **Authorize** (~7 calls, ~$0.01–0.05 F0) |
| B3 | **Perez OCR policy** — keep `Misaen`/`Jerman` vs normalize | `HCC_HUMAN_VALIDATION_REPORT.md` §5 | **Keep OCR spellings** (Laura confirmed on 4 crops) |
| B4 | **Spot-check sign-off** — 3× Jesus + random sample | `artifacts/hcc_e1_jesus_hernandez_spot_check_20260527.md`, random sample notes | **Accept** automated analysis; optional Laura confirm |
| B5 | **Third bank PDF** before default-on hybrid | `POST_SPIKE_INTEGRATION_PLAN.md` | **Before** all-clients default-on |
| B6 | **Cropper dedup in App** | `POST_SPIKE_INTEGRATION_PLAN.md` G1 | Parallel with G1 sprint |

---

## (c) Grok-augmented items

| # | Item | Status |
|---|------|--------|
| G1 | Profile-driven scoring | **Done** |
| G2 | Signature detection robustness | **Done** |
| G3 | Unit test coverage for ranking | **Done** (3 tests) |
| G4 | Validation refresh discipline | **Done** — notes appended to validation report |
| G5 | PRE_G1 integration checklist | **Done** |
| G6 | Jesus Hernandez spot-check follow-through | **Done** |

---

## Deferred (not in scope unless owner expands)

- Full page-7 CV retry execution (Phase 3 — owner must authorize)
- Second-bank G2 PDF harness
- Perez name normalization engine change
- Production App wiring (G1)
