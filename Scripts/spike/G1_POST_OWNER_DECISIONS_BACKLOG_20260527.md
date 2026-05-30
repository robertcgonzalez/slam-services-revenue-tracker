# G1 Post-Owner-Decisions Backlog — 2026-05-27 (evening)

**Prompt**: `CURSOR_PROMPT_G1_INTEGRATION_PREP_PAGE7.md`  
**Executor**: Cursor agent (spike-only)

---

## Owner decisions (verbatim — 2026-05-27 evening)

| ID | Decision |
|----|----------|
| **B1** | Approved — Traditions-first G1 integration sprint is authorized. |
| **B2** | Authorized — Execute the page-7 CV retry on the 7 failing crops. |
| **B3** | Perez OCR policy — "Misaen" (for Misaen Perez) and "Jerman" (for Jerman Perez) are the **correct** spellings for this client. Do **not** normalize away from the correct OCR spellings that matched human grades. |
| **B4** | Accepted — Spot-check analysis (3× Jesus Hernandez + 5 random) is accepted. |
| **B5** | Agreed — Third bank PDF required before any default-on hybrid for all clients. |
| **B6** | Agreed — Cropper dedup merge timing aligned with G1 sprint. |

---

## Prioritized execution queue

| Priority | Item | Source | Status |
|----------|------|--------|--------|
| P0 | Page-7 CV retry (7 crops, 4s rate limit) | B2 | **Done** — 7/7 |
| P0 | Merge retry JSON → `phase1_g2_hcc_202604` cache + `--rescore` → `profile_yaml_v4_p7` | Grok #1 | **Done** |
| P0 | Full 50-crop metric refresh + diff vs v4 | Grok #2 | **Done** |
| P0 | Traditions regression guard (0 downgrades) | Standing order | **Done** |
| P1 | Perez OCR policy artifact (`PEREZ_OCR_POLICY.md`) + rules audit | B3 | **Done** |
| P1 | Update PRE-G1 checklist (B1–B6 → 🟢 R/L) | Grok #4 | **Done** |
| P1 | G1 Handoff Package Index + sprint deliverables doc | Grok #5 | **Done** |
| P1 | Refresh status docs with post-page-7 numbers | Grok #2 | **Done** |
| P2 | Smoke test Perez protection + page-7 assertions | Grok #6 | **Done** |
| P2 | Post-Page-7 + Owner Decisions Summary (owner forward) | Phase 6 | **Done** |

---

## Deferred (unchanged)

- Full second-bank G2 PDF harness
- Production `App/` wiring (G1 sprint team)
- Perez name normalization to Misael/German (explicitly rejected per B3)
- Default-on hybrid for all clients before third bank PDF (B5)

---

## Baseline metrics (pre page-7, profile_yaml_v4)

| Metric | Value |
|--------|------:|
| HCC automated clean | **43/50** |
| HCC `no_lines` | **7** |
| 16-crop human package | **16/16** |
| Conservative heavy-manual estimate | **~10–15** |
| Traditions regression | **0** downgrades |

## Post page-7 metrics (profile_yaml_v4_p7) — **ACHIEVED**

| Metric | Value |
|--------|------:|
| HCC automated clean | **50/50** |
| HCC `no_lines` | **0** |
| 16-crop human package | **16/16** |
| Conservative heavy-manual estimate | **~5–8** |
| Traditions regression | **0** downgrades |

---

**Execution log**: `RECOMMENDATIONS_EXECUTION_LOG.md` (append Phase 0–6 sections)
