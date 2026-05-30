# Phase 6 — P&L Smoke Notes

**Date**: 2026-05-27  
**Script**: `Scripts/spike/phase6_pl_smoke.py`  
**Status**: COMPLETE (spike-only)

## Purpose

Prove that Phase 5 hybrid output (`transactions_hybrid.csv` + `deposit_slips.json`) can drive the same **Category/Payee × YearMonth** rollups Laura needs for P&L direction, using production `build_statement_pivot()` logic (read-only import from `App/bank_statements.py`). No App/UI changes. Option A schema unchanged.

## Run (reuse Phase 5 artifacts — zero Azure cost)

```powershell
python Scripts/spike/phase6_pl_smoke.py `
  --hybrid-dir Scripts/spike/artifacts/phase5_hybrid_reuse_test `
  --baseline-transactions Scripts/spike/artifacts/baseline_20260526T202334Z/transactions_all.csv
```

## Sample output (Auto Body Center Jan 26)

| Metric | Value |
|--------|-------|
| Register rows | 92 |
| Deposits (signed credits) | $41,786.80 |
| Withdrawals (signed debits) | $41,403.63 |
| Check rows | 49 |
| Payee filled on register (matcher-linked) | 14 / 49 (28.6%) |
| CV clean payees on crops (manifest) | 34 / 49 checks (~69%) |
| vs baseline: payee improved | 14 rows |
| Deposit slips (sidecar) | 7 |
| Pivot payee rows | 33 |

**Artifact folder** (example): `Scripts/spike/artifacts/phase6_pl_smoke_20260527T033415Z/`

| File | Role |
|------|------|
| `pivot_category_by_yearmonth.csv` | Category × month, SignedAmount sum |
| `pivot_payee_by_yearmonth.csv` | Payee × month, SignedAmount sum |
| `pivot_payee_by_yearmonth_count.csv` | Payee × month, counts |
| `top_payees_by_total.csv` | Quick Laura review sort |
| `credit_register_rows.csv` | Credit-side rows for deposit attribution |
| `deposit_attribution.md` | 7 slip excerpts + credit register sample |
| `phase6_pl_smoke_report.md` | Human summary |
| `phase6_pl_summary.json` | Machine-readable |

## Interpretation

1. **Pivots work** on hybrid CSV with `SignedAmount` — same code path as Bank Statements P&L tab.
2. **Payee column on register** only reflects matcher-linked CV updates (14/49 today); manifest shows **34 clean CV payees** on crops — integration sprint must widen write-back or Laura edits remain.
3. **Deposit slips** stay in JSON sidecar; credit attribution is narrative until Option B or a dedicated UI field.
4. **Single-period statement** — one YearMonth dominates; multi-month P&L needs more statements.

## Limitations (explicit)

- Spike-only; no `run_pipeline` / hybrid radio in App.
- Heuristic “cleanish payee” on register rows is conservative; use manifest for photo-leg quality.
- Power Query / Excel unchanged.
- ~24/49 checks still need heavy manual payee work per Phase 1 visual grading.

## Next

Phase 7 complete — see `Scripts/spike/POST_SPIKE_INTEGRATION_PLAN.md` and `Spike-Report-Computer-Vision-Check-Leg-20260527.md`.
