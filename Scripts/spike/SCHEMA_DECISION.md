# Schema Decision Record — Bank Statement Transactions (Phase 4)

**Date**: 2026-05-27  
**Status**: **Decided — A-then-B** (owner, 2026-05-27)  
**Scope**: Decision record only — **no schema implementation** in this phase.  
**Context**: Azure CV Read hybrid spike (`Spike-Plan-Microsoft-Document-Intelligence-PnL.md`). Phases 0–1 and cropper back-port (Phase 3) are complete. Hybrid integration (Phase 5) and P&L smoke (Phase 6) should not change column contracts without an explicit owner decision recorded here.

---

## Current canonical shape (Option A baseline)

The live app, Local Enhanced OCR pipeline, Azure OCR Function, lightweight parser, Grok CSV paste path, and Power Query / `Process-Statement.ps1` workflow all converge on the same **12-column** order:

| # | Column | Typical role today |
|---|--------|------------------|
| 1 | `Date` | Transaction date |
| 2 | `Description` | Bank register line (OCR or parser) |
| 3 | `Payee` | Cleaned counterparty (rules + check matcher) |
| 4 | `Amount` | Dollar string as printed on register (often unsigned or layout-dependent) |
| 5 | `Check#` | Check number when present |
| 6 | `Category` | Bookkeeping category |
| 7 | `SubCategory` | Optional sub-category |
| 8 | `SignedAmount` | Numeric signed amount (debits negative); preferred for totals/pivot |
| 9 | `YearMonth` | `YYYY-MM` for period rollups |
| 10 | `Confidence` | `High` / `Medium` / `Low` |
| 11 | `NeedsReview` | `Yes` / `No` |
| 12 | `ReviewReason` | Human-readable review hint |

**Source of truth in code** (must stay in sync if columns change):

- `App/bank_statements.py` — `GROK_CSV_COLUMNS`, `GROK_CSV_FIELDS`
- `App/local_enhanced_ocr.py` — `TRANSACTION_FIELDS`
- `Scripts/bank-statement-parser.py` — `CSV_FIELDNAMES`
- `AzureFunctions/ocr_processor/function_app.py` — inline port of the same 12 fields

**Non-column pipeline fields** (today): cropped checks carry `linked_check_id`, `extracted_payee`, etc. on the check objects / matcher logs — not part of the downloadable 12-column CSV.

---

## Proposed clean vNext shape (Option B)

A smaller, analysis-friendly contract discussed in the spike plan:

| Column | Role |
|--------|------|
| `Date` | Transaction date |
| `Description` | Register line |
| `Payee` | Cleaned counterparty |
| `Amount` | **Single signed numeric amount** (credits positive, debits negative) — replaces the `Amount` + `SignedAmount` pair |
| `Check#` | Check number when present |
| `Category` | Bookkeeping category |
| `SubCategory` | Optional sub-category |
| `RunningBalance` | Running balance after the line when the statement provides it (nullable) |
| `TransactionType` | Normalized type: e.g. `check`, `ach`, `deposit`, `withdrawal`, `fee`, `transfer`, `other` |
| `YearMonth` | Period key for P&L |
| `Confidence` | Review signal |
| `NeedsReview` | Review flag |
| `ReviewReason` | Review hint |

Optional future columns (out of scope for this decision unless owner expands): `linked_check_id`, `deposit_slip_text`, `source_page` for hybrid/debug.

**Column count**: Still ~12–13 logical fields, but **semantics** change (one amount column, explicit type and balance).

---

## Option A — Freeze 12-column for the first hybrid release

**Definition**: Ship Azure CV Read (when integrated) and any P&L smoke **without** changing `GROK_CSV_COLUMNS` / `TRANSACTION_FIELDS`. Hybrid outputs are mapped into the existing 12 columns at the boundary (same as Phase 1 harness feeding `_is_clean_payee`).

### Pros

| Area | Benefit |
|------|---------|
| **Time to value** | Lowest risk path to Laura: Bank Statements UI, reconciliation banner, payee rules, pivot, and CSV download work unchanged. |
| **Hybrid Phase 5** | Matcher (`_match_checks_to_transactions`), payee guard (`_is_clean_payee`), and check# / amount matching already key off `Check#`, `SignedAmount`/`Amount`, `Description`, `Payee`. |
| **Payee rules engine** | Unchanged — rules match on `Description` and write `Payee` / `Category`; no rule-file migration. |
| **data_editor** | `App/app.py` bank statement editor already shows a fixed subset of the 12 columns; no Streamlit column_config rework. |
| **P&L / pivot** | `build_statement_pivot()` already prefers `SignedAmount` with `Amount` fallback — works today. |
| **Downstream** | Power Query, Excel P&L workbooks, `Process-Statement.ps1`, and `Scripts/bank-statement-parser.py` need **zero** column renames. |
| **Azure Function / Local OCR** | Single contract across App and Function; no dual-shape support period. |

### Cons

| Area | Cost |
|------|------|
| **Data model clarity** | `Amount` vs `SignedAmount` redundancy persists; parsers must keep mirroring rules (`SignedAmount` ← `Amount` when blank). |
| **P&L semantics** | Credits/debits rely on sign in `SignedAmount`; register `Amount` column can still confuse exports that sort on the wrong field. |
| **Transaction typing** | No first-class `TransactionType` — type is inferred from `Description` regexes in the parser, not stored consistently for pivot filters. |
| **Running balance** | Not captured in the canonical CSV; reconciliation uses statement summary totals, not per-line balance drift. |
| **Technical debt** | vNext still required later for “real” multi-period P&L and deposit-slip attribution; second migration pass. |

### Impact by subsystem (Option A)

| Subsystem | Impact |
|-----------|--------|
| **Payee rules engine** (`apply_payee_rules`, `Data/payee_rules.csv`) | **None** — columns `pattern`, `clean_payee`, `suggested_category` are independent of amount schema. |
| **Matcher** (`_match_checks_to_transactions`) | **None** — uses `Check#`, `_safe_amount` on `SignedAmount`/`Amount`, `Description`, `Payee`. |
| **data_editor** | **None** — same visible columns. |
| **P&L rollups** (`build_statement_pivot`, Statement Summary in `app.py`) | **None** — continues `SignedAmount` sum/count by Category or Payee × `YearMonth`. |
| **Reconciliation banner** | **None** — `reconcile_statement_totals` / `grok_totals` use deposits, withdrawals, check counts. |
| **Downstream consumers** | **None** — Grok paste, parser CSV, PQ, Process-Statement.ps1 stay aligned. |
| **Phase 5 hybrid** | Map CV Read payee → `Payee`; deposits may stay off check-only rows unless matcher extended — still a **product** gap, not a schema gap. |

---

## Option B — Adopt vNext (signed `Amount` + `RunningBalance` + `TransactionType`)

**Definition**: Introduce the clean shape as the **new** canonical export and in-app DataFrame contract, with a defined migration window (adapter from 12-col → vNext and/or parallel export).

### Pros

| Area | Benefit |
|------|---------|
| **P&L / analytics** | One signed `Amount` column is the standard for sum rollups, credit/debit splits, and future multi-statement stacks without “which amount column?” bugs. |
| **Filtering** | `TransactionType` enables Payee × Period × Type pivots (e.g. deposits vs checks) without re-parsing `Description`. |
| **Reconciliation** | `RunningBalance` supports line-by-line sanity checks when OCR exposes it (common on digital statements). |
| **Deposit / hybrid** | Clear place to attach deposit-slip cohort (`TransactionType=deposit`) when Phase 5+ classifies photo regions. |
| **Long-term maintainability** | Removes duplicate `Amount`/`SignedAmount` mirroring logic scattered in `load_grok_vision_csv`, `_transactions_to_dataframe`, parser emitters. |

### Cons

| Area | Cost |
|------|------|
| **Breaking change** | Every consumer of `GROK_CSV_COLUMNS` must update — high blast radius if done in one shot. |
| **Migration effort** | Touch `bank_statements.py`, `local_enhanced_ocr.py`, `function_app.py`, `bank-statement-parser.py`, `app.py` (editor + pivot + download), Grok prompts, PQ workbooks, Process-Statement.ps1. |
| **Payee rules** | Engine still works on `Description`/`Payee`, but **saved CSVs** and training exports need column rename awareness; optional rule columns unchanged. |
| **Matcher** | Must read signed `Amount` only; `_safe_amount` and amount-match tolerance logic need audit (check amounts are usually positive on image). |
| **data_editor** | Redesign visible columns and Streamlit `column_config`; train Laura on new fields (`TransactionType`, `RunningBalance`). |
| **Pivot / P&L** | `build_statement_pivot` must use `Amount` only; add optional `TransactionType` filter; update UI labels (“Sum of Amount” not “SignedAmount”). |
| **Hybrid timing** | Doing vNext **with** Phase 5 doubles integration scope — conflicts with owner direction to defer hybrid and move in phased order. |

### Impact by subsystem (Option B)

| Subsystem | Impact |
|-----------|--------|
| **Payee rules engine** | **Low** — matching still on `Description`; may add optional `suggested_transaction_type` later (not required for vNext). Existing `payee_rules.csv` rows unchanged. |
| **Matcher** | **Medium** — `_safe_amount`, amount-based matching, and emitted transaction dicts must use single signed `Amount`; confirm sign convention vs check OCR amounts. |
| **data_editor** | **Medium** — column list in `bank_statements_page()` (~10 visible cols today); add `TransactionType` / `RunningBalance` or hide in expander. |
| **P&L rollups** | **Medium** — `build_statement_pivot` amount_col logic simplifies to `Amount` only; new filters (e.g. credits only, `TransactionType=deposit`) become feasible. |
| **Reconciliation banner** | **Low–medium** — totals logic unchanged if `grok_totals` still deposits/withdrawals; optional running-balance check is new feature work. |
| **Downstream consumers** | **High** — Power Query, Excel, Process-Statement.ps1, external Grok prompts must adopt new header row; versioned export filename recommended (`*_vNext.csv`). |
| **Phase 5 hybrid** | **Medium** — cleaner mapping for deposit slips and credits, but integration must not start until adapters exist. |

---

## Side-by-side summary

| Criterion | Option A (freeze 12-col) | Option B (vNext) |
|-----------|--------------------------|------------------|
| Hybrid Phase 5 readiness | **Ready** — map into existing fields | **Blocked** until migration plan approved |
| Laura / UI disruption | Minimal | Moderate (new columns, relabel pivot) |
| Engineering effort before hybrid | Low | High (multi-file contract change) |
| P&L smoke (Phase 6) | Use `SignedAmount` as today | Cleaner sums on one `Amount` |
| Power Query / Excel | No change | Breaking unless dual-export |
| Deposit-slip attribution | Awkward (type not in schema) | Natural via `TransactionType` |
| Long-term debt | Keeps Amount/SignedAmount dualism | Pays down debt early |

---

## Recommendation for owner decision (not implemented)

**For the phased spike sequence as the owner defined it** (schema decision → later hybrid → P&L smoke):

1. **Choose Option A** if the next milestone is **Phase 5 hybrid + Phase 6 P&L smoke on real improved payees** with minimal Laura disruption and no Power Query breakage.
2. **Choose Option B** if the next milestone is a deliberate **schema migration sprint** before any hybrid lands, with budget to update PQ/Excel and accept a short dual-export period (`12-col legacy` + `vNext`).

**Suggested compromise (record only — not a third official option unless owner wants it)**:

- **Option A** for Phase 5–6 deliverables.
- **Option B** as a follow-on release with an adapter: `transactions_vnext.csv` generated alongside the existing download until PQ is retired.

---

## Decision checklist (owner)

Reply with one of:

- **A** — Freeze 12-column for first hybrid release and P&L smoke.
- **B** — Adopt vNext before hybrid integration.
- **A then B** — Freeze now; schedule vNext migration after hybrid proof on hard PDF.
- **Other** — Specify constraints (e.g. vNext export only, in-app stays 12-col).

**Recorded decision**: **A-then-B**

- **Now (Phase 5–6)**: **Option A** — freeze the current 12-column shape for the first hybrid spike prototype, P&L smoke, and any later App integration. Deliver improved payee quality and deposit-slip capture with minimal Laura / Power Query disruption.
- **Follow-on (post-stable hybrid)**: **Option B** — migrate to single signed `Amount` + `RunningBalance` + `TransactionType`. Plan an **adapter / dual-export** period (`*_transactions.csv` legacy 12-col + `*_transactions_vnext.csv`) for Power Query and Excel until workbooks are updated.

**Decided by / date**: Owner (Robert) / 2026-05-27

---

## References

- Spike plan: `Spike-Plan-Microsoft-Document-Intelligence-PnL.md` (§3 success criteria, §9 post-spike path)
- Phase 1 artifacts: `Scripts/spike/PHASE1_NOTES.md`
- Payee rules: `App/bank_statements.py` (`PAYEE_RULES_COLUMNS`)
- Pivot: `App/bank_statements.py` (`build_statement_pivot`)
- Matcher: `App/local_enhanced_ocr.py` (`_match_checks_to_transactions`)

*This file lives under `Scripts/spike/` only. No production code changes are implied until a later phase explicitly implements the chosen option.*
