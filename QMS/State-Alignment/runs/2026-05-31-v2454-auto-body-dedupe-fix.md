# State Alignment Run — v2.45.4 Auto Body Post-Assembly Dedupe Fix

**Date**: 2026-05-31  
**Process**: `QMS/State-Alignment/process.md` (code fix + pre-deploy evidence)  
**Prior run**: `QMS/State-Alignment/runs/2026-05-31-v2453-deploy-resmoke.md`

---

## Problem (unchanged production baseline)

| PDF | Withdrawals | Gold | Δ |
|-----|------------:|-----:|--:|
| Auto Body | $41,130.18 | $41,403.63 | **$273.45** |

Evidence: 44 register + 50 supplemental; `supplemental_skipped_duplicates=0` — gap not in register prune or pre-filter dedupe.

---

## Root cause

`_dedupe_azure_transactions` dropped amount-only `check_image_crop` rows when `abs(SignedAmount)` matched **any** register row, including **deposits/credits**. A register deposit and an imaging-leg check sharing **$273.45** removed the withdrawal silently (no assembly stat).

Secondary: supplemental duplicate collapse used amount-only keys, collapsing distinct vendors with the same check amount.

---

## Fix (v2.45.4)

| Change | Location |
|--------|----------|
| Cross-source dedupe vs register **debits only** | `App/bank_statements.py` `_dedupe_azure_transactions` |
| Supplemental dup key = amount + payee/description | `_supplemental_row_dedupe_key` |
| Observability | `dedupe_dropped_register_debit_match`, `dedupe_dropped_supplemental_dup` in meta + processing log |

---

## Verification (local)

- `Scripts/test_azure_assembly.py` — all pass (incl. `test_dedupe_preserves_supplemental_when_only_register_deposit_matches`, `test_auto_body_273_gap_regression_assembly`)
- `ruff check` on touched files

**Production re-smoke**: see `2026-05-31-v2454-deploy-resmoke.md` — withdrawals unchanged ($41,130.18); owner accepts Δ $273.45 with human review.

---

## Before / after (production re-smoke)

| Metric | Before (v2.45.3 smoke) | After (v2.45.4 deploy) |
|--------|------------------------|------------------------|
| Auto Body withdrawals | $41,130.18 | $41,130.18 (Δ $273.45 — human review) |
| Dedupe false drops (deposit collision) | Possible in code path | Fix live; gap persists from other imaging-leg causes |
| Human review path | Reconciliation banner only | Banner + guidance + optional review note + skip logging |
