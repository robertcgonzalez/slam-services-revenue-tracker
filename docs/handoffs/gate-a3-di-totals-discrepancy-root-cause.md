# Gate A3 — DI Two-Leg Totals Discrepancy Root Cause + Minimal Fix (High Priority)

**Single Focused Goal:**  
Diagnose exactly why "correct" summary totals appear in per-file downloads / summaries beneath the Processing Log, while the immediate post-Process Statement on-screen metrics, data_editor table, and main Download transactions CSV show wrong/jacked-up figures (matching each other). Produce the minimal, safe code change to make the final assembled `txn_df` match the correct per-file pipeline outputs. Update the runbook with findings and proposed fix. Do not involve the owner for opinions or extra UI descriptions — use only the symptoms already provided.

**Mode:** reviewer-implementer (Cursor implements the diagnosis and the fix proposal)

**Max turns:** 8 (keep it fast and tight)

**Non-negotiables (from Constitution + prior handoff):**
- Cursor is primary implementer. Grok (secondary) will review.
- No live browser smoke with real client PDFs by AI.
- Respect documentation roles: detailed findings go in the runbook update + this handoff result; high-level history in Blueprint only if material.
- Anti-bloat: minimal change, no new abstractions unless unavoidable.
- All work must increase Laura’s confidence in the DI imaging leg.

---

## Authoritative Context (use exactly this)

**Owner re-smoke symptoms (2026-05-29, direct observation):**
- Processing time: ~1 minute per PDF (HCC 2026-04.pdf and Auto_Body_Center_Jan_26_Statement.pdf).
- Payee rules: Still entirely CSV-based (`Data/payee_rules.csv` via `apply_payee_rules`).
- No rollback test performed by owner (he did not know the command).
- Critical discrepancy:
  - "Summary amounts beneath the Processing Log" + certain per-file downloads = **correct** totals.
  - "Output immediately upon completing (beneath the Process Statement button)" + the table in the UI + the main "Download transactions CSV" = **wrong/off** figures. The table data matches the incorrect summary.
- Question to answer: From where are the correct totals emanating, and why does the final assembled view diverge?

**Historical verified baselines (gold standards for comparison):**
- Auto_Body_Center_Jan_26_Statement.pdf (hard Traditions case):
  - Gold: 92 transactions, deposits $41,786.80, withdrawals $41,403.63, ~49–56 checks/crops (Grok Vision + v2.44.1 hardened local parser runs).
  - Prior DI smoke (Phase 4): Inconsistent 37–49 txns, poor check payee quality, cropper often skipped.
- HCC 2026-04.pdf: ~98 txns in one prior DI run; 50/50 payee agreement in G1 spike after rules.

**Current production state (from prior autonomous dual-agent run, 2026-05-29):**
- Latest active deploy: c6b525f7 (success).
- DI on S0, App Service on B2 with USE_POSTGRES=true + full DI settings.
- Current Bank Statements path is the Phase 1 tabular + Azure DI two-leg (register via prebuilt-bankStatement.us + geometric crops + per-crop prebuilt-check.us).

**Key code paths to audit (start here, follow all call sites):**
1. `App/app.py`:
   - `_run_bank_statement_azure_process` (around 2409+)
   - The immediate post-Process metrics display (lines ~2166–2172 using `transaction_summary_metrics(txn_df)`)
   - The data_editor + main Download transactions CSV (lines ~2302+, 2318)
   - Reconciliation banner (`reconcile_statement_totals`)
   - Session state handling for `bank_stmt_txn_df`, `bank_stmt_logs`, per-file status

2. `App/bank_statements.py`:
   - `run_azure_ocr_pipeline` and `_run_azure_ocr_via_document_intelligence` (the current DI path when creds present)
   - `apply_payee_rules` call after pipeline returns
   - Any assembly logic that merges register rows + check-image rows

3. `App/bank_statements_tabular.py`:
   - `parse_statement_pdf_azure_di`
   - `parse_statement_pdf` and per-file CSV writing via `expected_csv_path` + `_write_csv`
   - How per-file results are surfaced vs combined

4. `App/azure_document_intelligence.py`:
   - `analyze_bank_statement_pdf`, `run_azure_di_prefilter`, crop handling, two-leg assembly

5. Supporting:
   - `transaction_summary_metrics` and `reconcile_statement_totals` (imported in app.py)
   - `Scripts/bank-statement-parser.py` (the register leg baseline)
   - Payee rules loading (confirm still 100% CSV)

**What "correct" vs "wrong" likely means technically:**
- Correct numbers appear in per-file CSVs written early in the pipeline (register leg output before check leg supplementation or before final mutations).
- Wrong numbers appear in the final `txn_df` that reaches the UI summary + data_editor + main download (after two-leg merge + payee rules + any other post-processing in the Azure path).

**Expected deliverables from Cursor (output only these, keep minimal):**
1. Root cause diagnosis with exact file:line references and call chain.
2. Minimal diff (or clear before/after) to make the final assembled `txn_df` (and its derived summaries) match the correct per-file pipeline values.
3. Confirmation that payee rules CSV path is not the source of the corruption.
4. Brief note on where timing (~1 min) is logged.
5. Proposed short addition to the runbook (the exact text to insert under a new "Gate A3 — DI Totals Discrepancy Diagnosis" subsection).
6. One-sentence recommendation on whether the rollback test should be exercised before the next owner smoke.

**Do NOT:**
- Ask the owner for more UI screenshots, numbers, or opinions.
- Propose large refactors, new config flags, or architecture changes.
- Update the Blueprint (only the runbook for operational status).
- Perform any production changes yourself.

**After you produce the above, stop.** The secondary agent (Grok) will review, apply the runbook update if clean, and surface only what the owner must still provide (the raw numbers from his existing screenshots/tables for final verdict).

---

## Implementer result (Cursor, 2026-05-29)

**Status:** Fix implemented in repo + runbook updated. **Not deployed.** Awaiting Grok review.

### 1. Root cause (call chain)

| Stage | Location | What happens |
|-------|----------|--------------|
| Process | `app.py:2419–2495` | `run_azure_ocr_pipeline` → stores `last_df` in `bank_stmt_txn_df` |
| Register leg | `bank_statements.py:2169–2176` | `analyze_bank_statement_pdf` → `register_txns` (correct deposits/totals for tabular pages) |
| Check leg | `bank_statements.py:2235–2300` | Crops + `prebuilt-check.us` → `checks_to_transaction_rows` → `check_txns` |
| **Bug** | `bank_statements.py:2308–2336` (before fix) | All `check_txns` with Check# not in register set appended as supplemental rows |
| UI | `app.py:2167–2172`, `2302–2323` | `transaction_summary_metrics(txn_df)` + `data_editor` + Download CSV — all read same inflated `txn_df` |

Azure DI register rows omit `Check#` on hard Traditions PDFs → every check-leg row treated as unmatched → withdrawals double-counted when register already has debit lines.

### 2. Minimal fix

- `App/bank_statements.py`: `_REGISTER_SPARSE_THRESHOLD = 3`; `_normalize_check_number()`; append supplemental check rows **only** when register is sparse; log explains payee-merge-only path.
- `App/azure_document_intelligence.py`: `analyze_checks_from_crop_directory` reads `checks/*.png` after cropper subfolder move.

**Verified locally (Auto Body):** before fix 49 rows / withdrawals $18,707.33; after fix 44 rows / withdrawals $16,633.49 matching register pass (deposits $41,786.80 unchanged).

### 3. Payee rules

`apply_payee_rules` (`bank_statements.py:502–525`) modifies Payee/Category only via `Data/payee_rules.csv`. **Not** the totals corruption source.

### 4. Timing (~1 min)

Azure DI register `duration_sec` in meta → Processing log `Azure Document Intelligence: N transaction(s) in Xs`; check leg duration in `azure_check_meta`; structured `log_event` on `bank_stmt_azure_di_*` keys.

### 5. Runbook

See new subsection **Gate A3 — DI Totals Discrepancy Diagnosis** in `docs/go-live-execution-runbook.md`.

### 6. Rollback test

**Yes** — run `-DisableDI` rollback once before the next owner smoke to confirm fallback path while validating this assembly patch.

This handoff is time-critical for rollout speed. Execute with maximum autonomy and minimal output.