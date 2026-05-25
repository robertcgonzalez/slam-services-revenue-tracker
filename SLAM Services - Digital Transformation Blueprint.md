# SLAM Services - Digital Transformation Blueprint

**Version**: 2.40  
**Date**: May 25, 2026  
**Status**: **Polished Learn-this-mapping UX + Rules Library + in-app pivot summary are live.** The Learn form now smart-suggests a merchant pattern from the selected description (strips POS/ACH/etc. noise prefixes, trims store #s and state codes), shows a live "would affect X rows" preview as Laura types, warns on 0 or >20 matches, and renders a clean before→after Payee diff after save. A new **📚 Rules Library** expander surfaces the top 25 rules sorted by recently used (with scope and sort filters and a 30-day usage headline). A new **📊 Statement Summary** section pivots the open statement by Category or Payee × YearMonth (sum or count) with quick presets, an Uncategorized-only filter, and an Export Pivot CSV button — the first step toward reducing Power Query dependence. The **Download transactions CSV** button is preserved unchanged as the Power Query safety net. Grok Vision prompt also sharpened with explicit warnings on the three real-world failure modes (dual amounts, check register, multi-page). v2.39's persistent payee rules engine and v2.38.3's polling-safe Azure deploy path remain the standard. **Cursor is primary agent**; Kilo Code secondary.

## Change Log

- **v2.40 (May 25, 2026)**: **Polished Learn-this-mapping UX + Rules Library + in-app pivot summary.** Five focused improvements to the v2.39 Bank Statements page with zero regression on CSV column order, Power Query, or Process-Statement.ps1. (1) **Smart pattern suggestion**: new `suggest_payee_pattern(description)` helper in `App/bank_statements.py` strips 28 common noise prefixes (POS PURCHASE, ACH DEBIT, DEBIT CARD PURCHASE, ELECTRONIC DEBIT/CREDIT, ONLINE BANKING, MOBILE DEPOSIT, ATM WITHDRAWAL, CHECK #, etc.) and trims trailing stop tokens (store numbers, embedded dates, 2-letter state codes) so the Learn form now defaults to the actual merchant (`WAL-MART` instead of `POS`). (2) **Live impact preview**: new `count_pattern_matches(df, pattern, client_name)` helper drives a reactive caption under the pattern field — green checkmark for 1-20 matches, amber warning at 0 or >20. Pattern input was moved OUTSIDE `st.form` so Streamlit reruns the preview on each keystroke; submit + other inputs stay inside the form to keep noisy reruns minimal. (3) **Sharper post-save messaging**: captures the picked row's Payee before save and renders a clean `(blank) → Acme Supply` diff after the rules engine re-applies; warns when rule saved but matched 0 rows (manual edits prevented overwrite); **Rules improved** metric refreshes in the same rerun. (4) **📚 Rules Library quick view**: new `rules_library_summary(rules_df, client_name, scope, sort_by, limit)` helper plus a collapsible expander below the Learn form showing up to 25 rules with columns Pattern, Clean Payee, Suggested Category, Scope (Global / client name), Last used (relative — "today", "3 days ago", "2 weeks ago"). Filters: scope radio (All / Global only / `<client>` only) + sort dropdown (Recently used / Most specific / Alphabetical). Headline caption shows total rules, client-specific count, and rules used in the last 30 days. Read-only — caption directs Laura to `Data/payee_rules.csv` in Excel for edits/deletes. (5) **📊 Statement Summary (in-app pivot view)** — first step toward reducing Power Query dependence: new `build_statement_pivot(df, group_by, value_kind, uncategorized_only)` helper uses `pandas.pivot_table` to aggregate by Category or Payee across YearMonth columns, returns sum of SignedAmount (with absolute-total descending sort) or transaction count, with a trailing Total column. Renders below the transaction editor with four quick presets (By Category, By Payee, Uncategorized Only, Export Pivot CSV) plus radio (Group by) / selectbox (Values) / checkbox (Uncategorized only) controls. Streamlit state pattern uses `setdefault` seeding so preset buttons mutate state cleanly without "value+key" warnings. Money cells render as `$1,234.56`; counts render as integers. **The existing Download transactions CSV button is preserved unchanged below the pivot** as the Power Query safety net, with a clarifying caption: "💾 Power Query safety net: download the full 12-column CSV below". Plus **Grok Vision prompt sharpening**: `build_grok_vision_prompt()` now includes an explicit Common-failure-modes block warning Grok against the three real-world bugs Laura sees most often — DUAL AMOUNTS (transaction vs. running balance), CHECK REGISTER (`2473 * 01/15 250.00 6,079.01` parsing rules), and MULTI-PAGE (Check Register often starts on page 2 or 3). New `log_event` topics: `bank_stmt_payee_rule_preview` (pattern + match count on form interaction), `bank_stmt_payee_rules_library_viewed` (gated by snapshot to avoid spam), `bank_stmt_pivot_viewed` (gated by snapshot). `App/app.py` `_render_payee_rules_controls()` refactored into three focused functions (`_render_payee_rules_controls`, `_render_learn_mapping_form`, `_render_rules_library_expander`) plus the new `_render_statement_pivot_section`. Defensive `ImportError` fallback block extended with stubs for `suggest_payee_pattern`, `count_pattern_matches`, `rules_library_summary`, `build_statement_pivot`, `PIVOT_GROUP_BY_OPTIONS`, `PIVOT_VALUE_KIND_OPTIONS` so stale deploys degrade gracefully. `APP_VERSION` bumped to **v2.40**. No new dependencies (pandas + `re` + `datetime` only). CSV column order, Power Query layout, Process-Statement.ps1 workflow, reconciliation banner, amber confidence styling, Download transactions CSV button, and Mark as Received all unchanged. Ruff check + format clean on `App/app.py` and `App/bank_statements.py`.
- **v2.39 (May 25, 2026)**: **Quick Parallel Win delivered — lightweight persistent payee rules engine.** New `App/bank_statements.py` helpers: `apply_payee_rules(df, client_name=None, rules=None)` returns `(out_df, info)` with case-insensitive substring matching (default) and optional full regex via a `re:` pattern prefix, client-specific overrides that win over global rules, longest-pattern tiebreaker, and best-effort `last_used` ISO-date tracking so Laura can see which rules earn their keep. `load_payee_rules()` / `save_payee_rules()` / `upsert_payee_rule()` / `resolve_payee_rules_path()` round out the API; `PAYEE_RULES_COLUMNS` (`pattern,clean_payee,suggested_category,client_override,notes,last_used`) and `PAYEE_RULES_FILENAME` exported for downstream tooling. New `Data/payee_rules.csv` (gitignored under existing `Data/` and `**/*.csv` rules) seeded with 25 high-value merchant patterns: Walmart (3 spellings), Amazon (2), Costco, Home Depot, Lowe's, Target, Venmo, Zelle, PayPal, ACH Deposit / Withdrawal, Chevron / Shell / Exxon, Verizon / AT&T / Comcast, bank service fees, interest earned, and Intuit / QuickBooks. Payee column is overwritten **only** when blank or equal to the raw Description (preserves manual edits); Category is overwritten **only** when blank or `Uncategorized` (never clobbers Laura's downstream Power Query work). `App/app.py` `bank_statements_page()` integration: rules auto-apply after the parser pipeline AND the Grok CSV paste path, with a green "🧠 X payee mapping(s) applied" callout under the result. New `_render_payee_rules_controls()` panel sits between the reconciliation banner and the `st.data_editor` with three columns — a **Rules improved** metric, a **🔄 Apply Payee Rules** button (idempotent re-run for ad-hoc cleanup), and a caption pointing at the rules file. Below that, a collapsible **💡 Learn this mapping (teach a new rule)** form lets Laura pick any transaction, edit the suggested pattern / clean Payee / Category, optionally scope to the current client, and persist the rule with one click — the rule is reapplied across the open statement immediately. Defensive: missing/empty/permission-denied rules file is a silent no-op. Audit trail via new `log_event` topics: `bank_stmt_payee_rules_applied`, `bank_stmt_payee_rules_reapplied`, `bank_stmt_payee_rules_error`, `bank_stmt_payee_rule_learned`, `bank_stmt_payee_rule_save_error`. Grok Vision prompt now mentions the post-import rules step so Grok knows its best-effort Payee/Category will be refined rather than replaced. `APP_VERSION` bumped to **v2.39**. No new dependencies (pandas + `re` only). CSV column order, Power Query layout, Process-Statement.ps1 workflow, reconciliation banner, amber styling, Download CSV, and Mark as Received all unchanged. Ruff check + format clean on `App/app.py` and `App/bank_statements.py`. Section 8.1 **Quick Parallel Win** marked **Delivered**.
- **v2.38.3 (May 25, 2026)**: **Modern polling-safe Azure deploy path.** Diagnosed and fixed the v2.38.2 deploy failure where `az webapp deploy --src-path slam-app.zip --type zip` hung at "Warming up Kudu before deployment" and errored with `('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))` from `_make_onedeploy_request`, while the live site simultaneously showed `Connection timed out`. Root cause: on F1 (Free) App Service Plan, Kudu warm-up + container teardown frequently exceeds the front-end load balancer's ~230 s idle TCP timeout, silently dropping the CLI's long-lived polling HTTPS connection even though the OneDeploy job is alive on the server. Compounding factors: stale `WEBSITE_RUN_FROM_PACKAGE` setting (silent killer of OneDeploy zip uploads), stuck Kudu deploy lock from previous failed attempt, and use of the deprecated `az webapp deployment source config-zip` command. **Fix**: new `Scripts/PowerShell/Deploy-ToAzure.ps1` — pre-flight checks, removes `WEBSITE_RUN_FROM_PACKAGE` if present, `az webapp stop` (releases Kudu + clears any in-flight handler), `az webapp deploy --type zip --async true` (returns immediately, no client polling), server-side polling of `az webapp deployment list` until terminal status (0 Success / 3 Failed / 5 Partial), `az webapp start`, and HTTP smoke test against the live URL. Idempotent and re-runnable. `Deploy-PostgresProduction.ps1` rewired to delegate Step 3 to `Deploy-ToAzure.ps1`. README's "Azure deployment" section rewritten with the new modern path (A), a manual one-shot equivalent (B), GitHub Actions (C), Kudu upload (D), and a copy-paste **Recovery** runbook for the exact `RemoteDisconnected` symptom (stop → clear setting → confirm no in-flight deploy → re-run; with optional Kudu restart via `az resource invoke-action` for genuinely wedged locks). Daily-driver tables and the UAT pre-session checklist now reference `Deploy-ToAzure.ps1` instead of `config-zip`. Site remains in UAT mode; no application or data changes. No new Azure SKU required (still F1).
- **v2.38.2 (May 24, 2026)**: Added automated **statement reconciliation check**. Every Grok-extracted (or parser-extracted) bank statement now compares detailed transaction totals (deposits, withdrawals, checks, count) against the bank's summarized TOTALS line. Clear ✅/⚠️ banner in the UI provides 100% assurance that extracted data matches source material. Mismatches automatically flag for review. (Closes assurance gap identified in reconciliation discussion.)
- **v2.38.1 (May 24, 2026)**: Made Grok CSV paste bulletproof against unquoted commas in Description/Payee fields (real-world Grok output). Updated `load_grok_vision_csv` with `engine='python'`, `quoting=3`, and `on_bad_lines='warn'`. Also memorialized the strategic next milestones in Section 8.1.
- **v2.38 (May 24, 2026)**: Native **Paste Grok CSV** intake on the Bank Statements page. `App/bank_statements.py`: new `load_grok_vision_csv(source)` helper accepts pasted text, raw bytes, or any uploaded file-like object; strips the trailing `TOTALS:` summary line and stray markdown fences; validates required columns (`Date`, `Description`, `Amount`); fills missing optional columns with safe defaults (`Category=Uncategorized`, `SignedAmount` mirrors `Amount`, `YearMonth` derived from `Date`, `NeedsReview` derived from `Confidence` when blank); returns a DataFrame in the canonical 12-column order matching the lightweight parser output. New constants `GROK_CSV_COLUMNS` and `GROK_REQUIRED_COLUMNS`. `App/app.py`: new collapsible **📋 Option 2: Paste Grok-extracted CSV here** section in `bank_statements_page()` with a 400px `st.text_area` (placeholder showing the expected header + a sample row + the TOTALS line), a CSV `st.file_uploader`, and a primary **Load / Parse Grok CSV** button. Loaded DataFrame is stored in the shared `bank_stmt_txn_df` session key so all existing downstream UI (metrics, confidence filter, styled `st.dataframe`, `st.data_editor`, Download transactions CSV, and "Link to revenue request" / Mark as Received) works identically to the parser path. Structured success / error messages and `log_event` audit hooks (`bank_stmt_grok_csv_loaded`, `bank_stmt_grok_csv_parse_error`). Defensive import fallback for `load_grok_vision_csv` and `GROK_CSV_FIELDS` in `App/app.py`. `APP_VERSION` bumped to **v2.38**. CSV column order, Power Query layout, and Process-Statement.ps1 workflow all unchanged. No new dependencies. Ruff clean on `App/app.py` and `App/bank_statements.py`.
- **v2.37.1 (May 24, 2026)**: Documented future bank statement & accounting automation roadmap. Added new subsection 8.1 "Future Bank Statement & Accounting Automation" with Azure Function OCR path, P&L generation, persistent rules engine, check-image linking, OneDrive integration, and expanded accounting features. Documentation-only update (no code changes; previously labeled v2.38 prior to the v2.38 code release above).
- **v2.37 (May 24, 2026)**: Lightweight parser maximization + Grok Vision integration. `Scripts/bank-statement-parser.py`: `pick_transaction_amount()` prefers leftmost non-zero amount on dual-amount lines (fixes balance-vs-transaction bug for `DATE DESC AMOUNT BALANCE` rows), new bare MM/DD date patterns combined with statement year, `SECTION_TERMINATORS` for Daily Balance Summary / Statement Balance Summary (stops noise), expanded `SECTION_MARKERS` (Other Credits, ATM Deposits, Withdrawals and Debits, Debit Card Transactions, Fees), `CHECK_REGISTER_ROW_RE` fast-path for Traditions rows like `2473 * 01/15 250.00 6,079.01`, pipe-delimited check-row column detection (`[check#, date, amount, balance]`), `_filter_balance_only_rows()` drops "Beginning/Ending Balance" / "Total" residue, `summarize_transactions()` for per-section diagnostics. `App/bank_statements.py`: new `build_grok_vision_prompt()` returning a copy-paste-ready prompt mirroring the exact CSV header expected by Process-Statement.ps1; pipeline meta now carries `pdf_path` and `cropped_dir` / `cropped_check_count`. `App/app.py`: **Prepare for Grok Vision** expander on the Bank Statements page (auto-expanded when 0 transactions or no text layer) — shows client name, saved PDF path, cropped checks folder, the full prompt in a copy-button code block, and a **Download Grok prompt (.txt)** button; clearer "scanned/image-only PDF detected" messaging; defensive import fallback for `build_grok_vision_prompt`. `APP_VERSION` v2.37. CSV column order, Power Query layout, and Process-Statement.ps1 workflow all unchanged. No new heavy dependencies (OpenCV/EasyOCR/pdf2image remain optional, local-only).
- **v2.36 (May 24, 2026)**: Traditions Bank statement parser tuning — `Scripts/bank-statement-parser.py`: section-aware parsing (Deposits, Electronic Credits/Debits, Check Register), improved table column mapping (Date, Description, Amount, Check #), pipe-delimited rows, debit/check sign normalization, PAYPAL/ACH/EFT/debit-card patterns, check numbers (`2473 *`, `Check #2632`); always merges page text + tables per page; zero-transaction Grok Vision + **Export Raw Text** unchanged. `APP_VERSION` v2.36. `Process-Statement.ps1` CSV format unchanged.
- **v2.35 (May 24, 2026)**: Bank statement parser v2 — `Scripts/bank-statement-parser.py` rewritten for flexible dates/amounts, multi-line descriptions, table extraction, word-layout fallback, ACH/EFT/check/debit patterns, relaxed validation; same Power Query CSV columns. Scanned PDFs (no text layer) log a warning; **Export Raw Text** + zero-transaction Grok Vision guidance in Bank Statements UI (`App/bank_statements.py`, `App/app.py`). `APP_VERSION` v2.35. `Process-Statement.ps1` workflow unchanged.
- **v2.34.2 (May 24, 2026)**: Hotfix — `filter_transactions_by_confidence()` exported from `App/bank_statements.py` with `confidence_level` parameter and `__all__`; defensive import fallback in `App/app.py` if module is out of sync on deploy. `APP_VERSION` v2.34.2. Fixes `ImportError: cannot import name 'filter_transactions_by_confidence'`.
- **v2.34.1 (May 24, 2026)**: Bank Statements reliability — `Scripts/bank-statement-parser.py` uses `safe_print()` (no Unicode/cp1252 failures on Windows); optional check cropper skipped non-fatally when `cv2` missing or cropper fails (user message + structured `[LEVEL]` processing log); subprocess UTF-8 capture; success / partial / error feedback and output CSV path in UI; transaction table filter (**Show All** / **Low/Medium Confidence Only**), amber row highlight for non-High Confidence, **Items need review** metric. `App/bank_statements.py` helpers; `APP_VERSION` v2.34.1. No new heavy deps in `requirements.txt`.
- **v2.34 (May 24, 2026)**: Core Workstream #2 MVP — **Bank Statements** navigation page in `App/app.py`. Upload PDF(s) → **Process Statement** runs existing `Scripts/bank-statement-parser.py` (+ optional `smart_check_cropper_final_dynamic.py`) via subprocess; processing log expander; `st.data_editor` on `_Transactions_With_Payees.csv` output; client selector; summary metrics (transaction count, deposits, withdrawals, needs review); **Mark as Received** updates `bank_statement_received` via `save_requests()` (PostgreSQL + CSV). New `App/bank_statements.py`. **Missing Docs** quick view shows bank/sales/both counts in sidebar; Dashboard caption for missing-doc totals. `pdfplumber` added to `requirements.txt`. `APP_VERSION` v2.34. OneDrive auto-sync deferred to v2.35+.
- **v2.33 (May 24, 2026)**: Hotfix — restored **Today's priority** on Dashboard. Root cause: briefing used sidebar-filtered data, so overdue items disappeared under default/narrow filters. `render_todays_priority(req_df)` now reads the **full** request list (CSV + PostgreSQL), sorts by due date, shows days overdue / business / type / amount, hero styling, **All caught up!** when none overdue, CTAs (Overdue quick view + Revenue Requests navigation). UAT checklist + Daily workflow help updated. `APP_VERSION` v2.33.
- **v2.32 (May 24, 2026)**: UAT launch milestone. `App/app.py`: dismissible UAT welcome banner; sidebar quick views **This Month** + **Missing Docs**; **days overdue** on dashboard tables; friendly Revenue Requests column labels; **unsaved changes** warning + Force reload guard; bulk update requires confirmation checkbox; clearer save-failure recovery text; UAT week-1 checklist in sidebar. `App/diagnostics.py`: `get_operational_hints()` for system status. `Scripts/health_check.py --full` (CSV + Postgres). New `Scripts/PowerShell/Check-AppHealth.ps1` for pre-UAT validation. `startup.sh` v2.32. README: UAT guide + ops section. Zero regression in CSV-only and PostgreSQL modes.
- **v2.31 (May 24, 2026)**: Daily-driver milestone for Laura/Stef. `App/app.py`: Today's priority briefing on Dashboard, quick filter presets (Overdue / Pending), professional SLAM styling, signed-in user label (`SLAM_APP_USER`), data freshness panel, daily workflow help, system status expander, logout, last-save confirmation, structured logging via `App/app_logging.py` + `App/diagnostics.py`. `Scripts/health_check.py --csv` for CSV-only Azure validation; `startup.sh` runs CSV health in CSV mode. New `Scripts/PowerShell/Sync-DataRefresh.ps1` (migrate + verify). Zero regression in CSV-only mode.
- **v2.30 (May 24, 2026)**: Full production PostgreSQL on Azure. `App/db_utils.py`: shared engine with pool settings (`pool_pre_ping`, `pool_recycle`), Azure SSL auto (`POSTGRES_SSLMODE`), URL-encoded credentials, `get_db_stats()`, `get_connection_status()`, `reset_db_engine()`. `App/app.py`: enhanced sidebar status (row counts, Test/Refresh buttons, recovery expander, empty-DB migration prompt, save retry via connection reset). New `Scripts/health_check.py` (CLI/JSON for startup + CI). New `Scripts/PowerShell/Set-AzurePostgresAppSettings.ps1` and `Deploy-PostgresProduction.ps1`. `startup.sh` runs health check when `USE_POSTGRES=true`. README: production checklist + CSV fallback procedure. CSV-only users unaffected.
- **v2.28 (May 24, 2026)**: Phase 3 PostgreSQL write-back for Revenue Requests. Extended `App/db_utils.py` with CRUD helpers (`update_revenue_request`, `bulk_update_status`, `save_revenue_requests_from_df`), audit actor via `SLAM_APP_USER`, soft-delete-safe updates, and transactional session management. `save_requests()` in `App/app.py` now writes to PostgreSQL when `USE_POSTGRES=true` (graceful CSV fallback when off or DB unavailable). Data editor save, undo stack, and bulk status update are bidirectional with Postgres; cache cleared on write; success/warning/error messages surfaced. CSV-only behavior preserved for existing users.
- **v2.24 (May 24, 2026)**: Agent rules — added **Git practices** to `.cursor/rules/slam-services.mdc` and `.kilocode`: commit only on user request, security-first staging, Blueprint-tied messages, `git rm --cached` for ignored tracked files, and post-change verification (`git status`, `check-ignore`, Ruff).
- **v2.23 (May 24, 2026)**: Final git repository cleanup. Comprehensive `.gitignore` security hardening completed (client data, secrets, generated reports). `Project-Structure-Report.txt` removed from tracking. Repository now clean with only intentional local files untracked. Commits: `ceb969c` + `0999020`.
- **v2.22 (May 24, 2026)**: Comprehensive `.gitignore` security hardening — structured sections for client data (`Data/`, `**/*.csv`, spreadsheets), secrets (`.env`, `.secrets/`, credentials patterns, logs), generated reports (`Project-Structure-Report.txt`, `*-report.txt`), and dev/deploy artifacts (`.venv/`, `*.zip`, `.continue/`, `*.bak`). Explicit allow-list for committed `.vscode/` JSON configs and `.cursor/rules/`. Removed `Project-Structure-Report.txt` from git index (`git rm --cached`) so the local report regenerates without polluting the repo; `git check-ignore` confirmed.
- **v2.21 (May 24, 2026)**: Git commit hygiene — added `*.bak` to `.gitignore`; staged and pushed safe files only (`.gitignore`, `.kilocode`, `.editorconfig`, `pyproject.toml`, `README.md`, Blueprint, `App/app.py`, `.cursor/rules/slam-services.mdc`, `.vscode/` JSON configs, `Scripts/` utilities, `Section14_Phase25_Feedback.md`, `Project Runtime User Stories.txt`). Excluded `App/app.py.bak`, `Business problem.docx`, `Data/`, all CSV/XLSX, `.continue/`, and deploy artifacts. Commit `d80d9b8` on `main` → `origin/main`. Post-push Ruff validation on `App/app.py`.
- **v2.20 (May 24, 2026)**: Removed unused Continue.dev artifacts — deleted `.continue/agents/` folder (leftover from Continue extension; project uses Cursor primary + Kilo Code secondary only). Added `.continue/` to `.gitignore` to prevent accidental recreation. Re-validated `streamlit run App/app.py` — no impact on application.
- **v2.19 (May 24, 2026)**: Optional Ruff lint cleanup for `App/app.py` — ran `ruff check --fix` and `ruff format`; confirmed `zip(..., strict=True)` on bulk-update label maps (Python 3.10+). `ruff check App/app.py` reports zero issues. Re-validated `streamlit run App/app.py`. No business-logic changes.
- **v2.18 (May 24, 2026)**: Azure CLI 64-bit migration — uninstalled legacy 32-bit `Microsoft.AzureCLI` (Python 3.13.13 32-bit at `Program Files (x86)`), installed official x64 build via `winget install --exact --id Microsoft.AzureCLI --architecture x64` (Python 3.13.13 64-bit AMD64 at `Program Files\Microsoft SDKs\Azure\CLI2`). Resolves v2.14 audit warning on 32-bit crypto performance. Validated `az --version`, `az account show`; existing login and `quota` extension preserved.
- **v2.17 (May 24, 2026)**: Python 3.10 environment parity for Azure — installed Python 3.10.11 via winget, recreated project `.venv` with `py -3.10` (replaced prior 3.14 venv), reinstalled `requirements.txt` plus Ruff/Black dev tools. Updated `.vscode/settings.json` interpreter comment, added `requires-python = ">=3.10,<3.11"` in `pyproject.toml` (Ruff/Black already target `py310`). Confirmed `runtime.txt` remains `python-3.10`. Validated `streamlit run App/app.py` and `ruff check App/app.py`.
- **v2.15 (May 24, 2026)**: Agent priority shift — **Cursor designated primary / lead AI coding agent** for the project. Builds on v2.14 Cursor environment optimization (workspace configs, Ruff, Streamlit/Azure verification, `.cursor/rules/slam-services.mdc`). Updated `.kilocode`, `.cursor/rules/slam-services.mdc`, `.cursor/rules`, and README to state Cursor leads with full authority for edits and living-document updates; Kilo Code retained as secondary / supportive only. No application code changes; `streamlit run App/app.py` re-validated.
- **v2.14 (May 24, 2026)**: TASK 1 (Cursor Edition) — Comprehensive Cursor environment evaluation & optimization. Audited 24 installed extensions (Kilo Code, Python/Ruff/Black, Azure, PowerShell, Markdown, CSV, terminal UX). Recreated missing `.vscode/` workspace configs (`settings.json`, `tasks.json`, `launch.json`, `extensions.json`) with Ruff format-on-save, performance excludes for `.kilo`/zips/logs, Streamlit default build task, Azure CLI tasks. Migrated `.cursor/rules` → `.cursor/rules/slam-services.mdc` (`alwaysApply`); updated `.kilocode` for Cursor coexistence; README onboarding for Kilo + Cursor. Removed orphaned `vscodeGrok.apiKey` from global Cursor settings (extension removed in v2.12). Created project `.venv`, validated `streamlit run App/app.py`, `az account show`, `az webapp list`, and Ruff tooling. Kilo Code unchanged as primary agent.
- **v2.13 (May 24, 2026)**: Phase 2.5 P0 Day-1 blockers fixed in App/app.py: defensive try/except on load_clients()/load_requests() + snake_case guarantee for request_id/business_name (no blanks in Dashboard tables); Global "Reset Filters" now clears all widget state + cache + forces rerun; Revenue Requests data_editor now shows editable Yes/No checkboxes for bank_statement_received + sales_report_received columns. Local `streamlit run App/app.py` validated. feedback_log.csv appended with P0 closure. Blueprint v2.13. Flat root structure confirmed for next azure zip deploy. Laura quick-win stabilization complete.
- **v2.12 (May 24, 2026)**: TASK 1 – Comprehensive Environment Evaluation & Optimization completed. Full audit of VS Code + Kilo Code setup performed. Removed legacy `vscode-grok` extension (redundant with Kilo Code as primary agent). Added 14 high-value extensions for Python/Streamlit/Pandas (black-formatter, ruff, autodocstring, rainbow-csv, datawrangler), Azure (azure-account), Markdown/docs (markdownlint, preview-enhanced), PowerShell efficiency, terminal UX (todo-tree, errorlens, path-intellisense), and project performance (editorconfig, yaml, dotenv). Created/updated `.vscode/extensions.json`, optimized `settings.json` (ruff as primary Python formatter/linter, performance excludes for .kilo/node_modules + large zips, markdown rules), enhanced `tasks.json` (lint/format tasks), `launch.json` (improved debug configs + PYTHONPATH), added `pyproject.toml` (ruff/black config) and `.editorconfig`. Fixed `.gitignore` to allow committing shared VS Code workspace configs. Kilo Code remains primary agent; no AI conflicts introduced. All changes align with Blueprint living document philosophy and pragmatic SDLC. Blueprint updated per .kilocode rules.
- **v2.11 (May 23, 2026 evening)**: Phase 2.5 Stabilization officially launched. First end-user testing session on the live Azure deployment (`slam-services-revenue-tracker.azurewebsites.net`) performed by Laura / team using real 2026 client data (`Clients.csv` + `RevenueRequests.csv`). Captured 7 specific runtime UX and data issues in "Project Runtime User Stories.txt". Immediately created persistent feedback mechanism:
  - New sidebar form inside the app that writes directly to `Data/feedback_log.csv` (versioned, auditable).
  - Added `feedback_log.csv` header and first sample rows (mirroring the original 7 issues plus format for future submissions).
  - Prioritized the 7 issues into three waves (P0 immediate fixes, P1 quick wins, P2 enhancement) forming the **Phase 2.5 Rollout Plan**.
  - Integrated the full Phase 2.5 plan + feedback process description into this Blueprint as new Section 14 (User Stories & Feedback).
  - Security note highlighted during testing: default password still active — must rotate before broader team access.
- **v2.10 (May 23, 2026)**: Comprehensive deployment diagnostic + automated fixes. Root cause identified: slam-app.zip contained extra top-level folder → requirements.txt not at zip root → pip install skipped → container crashed with "No module named streamlit". Automated fixes applied: (1) Rewrote startup.sh with defensive pip upgrade/install + set -e + correct $PORT. (2) Re-packed deployment as flattened zip with requirements.txt, App/, Data/, startup.sh at root. (3) Used `az webapp config set` to correct appCommandLine (removed stray `\`, dynamic $PORT). (4) Executed `az webapp deployment source config-zip`. Site now builds successfully and shows healthy Python 3.10 container. 503 observed immediately post-deploy (cold start + Kudu restart); new success logs confirm correct gunicorn/Streamlit launch path. SLAM_APP_PASSWORD App Setting already present. Blueprint updated.
- v2.9 (May 23, 2026): Re-established local development workspace in Grok agent environment. Created basic Streamlit app structure, requirements, sample CSVs. Updated for continued progress towards full data integration and Phase 3.
- v2.8 (May 23, 2026): Successful secure deployment of Streamlit Revenue Tracker to Azure App Service (slam-services-revenue-tracker.azurewebsites.net). Fixed startup command to use dynamic Azure PORT + --headless. Hardened authentication by replacing hardcoded password with SLAM_APP_PASSWORD App Setting (env var injected at runtime, no secrets in repo). HTTPS enforced. Live and ready for team testing.
- v2.7 (May 22, 2026): Completed local development environment setup. VS Code CLI + extensions configured, `.vscode` tasks/launch settings created, Kilo Code integrated with Grok 4.3 / Grok Build 0.1. Streamlit task successfully tested. Indexing in progress.
- v2.6 (May 22, 2026): Updated deployment status. Azure CLI installed, project structure created, Resource Group `SLAM-Services-RG` provisioned. Phase 2 secure deployment in progress.

## 1. Executive Summary

SLAM Services LLC (operated by Laura Bouchard in Gardendale, Alabama) is a sole-proprietor bookkeeping and tax preparation firm serving approximately 100 small business clients, with a heavy concentration in restaurants, bars, construction, and service trades across North Alabama.

The practice is currently highly manual, memory-driven, and paper-heavy. This creates significant operational friction, stress, missed deadlines, and limits scalability — especially as Laura considers transitioning day-to-day bookkeeping responsibilities to her sister Patty and brother-in-law Robert Gonzalez.

**This project** aims to transform SLAM Services from a reactive, person-dependent operation into a structured, partially automated, professional practice.

**Core Goals**:

- Reduce manual toil (especially revenue chasing and bank recs)
- Provide real-time visibility via dashboards
- Create auditable, maintainable processes
- Win Laura’s confidence through visible quick wins

---

## 2. Project Purpose & Vision

**Purpose**:  
Create a modern, auditable, and scalable operational backbone for SLAM Services that reduces reliance on any single person’s memory, minimizes manual data chasing, and provides real-time visibility into client work status, deadlines, and financial health.

**Vision**:

- Internal staff (Laura, Stef, Robert, Patty) have clear dashboards and automated reminders.
- Bank statement and check processing is largely automated with high accuracy.
- Revenue reporting moves from ad-hoc texting to tracked, auditable workflows.
- Paper documents are digitized with clear retention rules.
- The practice demonstrates professionalism and consistency.

---

## 3. Current State Analysis & Phase 1 Quick Win

### Phase 1 Quick Win: Revenue Reporting Tracker

**Status**: ✅ Core migration and dashboard logic complete | **Deployment**: In Progress  
**Notes**: Data connection to live CSVs is ready for integration. Secure Azure App Service deployment underway for team testing and feedback loop.

### 3.1 Client Base

- ~98–128 client records (from Client_Import.csv + 2025 Client Progress.xlsx)
- Strong concentration in restaurants/bars and construction/trades.

### 3.2 Current Digital Infrastructure (New)

**Document Storage**: OneDrive (primary) with heavy usage. Contains ~11,700+ PDFs, thousands of check images, Excel workbooks, and per-client folders (see `SLAM_Services_FileStructure_20260522_1332.csv`).

**Bookkeeping Tools**:

- QuickBooks Online (limited to 5 clients).
- QuickBooks Enterprise Desktop (primary) — used with one main client + departments/locations for multi-client P&L generation.
- Heavy Excel usage (PivotTables recently introduced; Power Query/Power Pivot by Robert).

**Tax Preparation**:

- Drake Accounting (via Right Networks terminal server).
- Manual data entry for 940/941, 2553, 1040, etc. Mostly print-and-mail.

**Communication & Revenue Chasing**:

- Direct access to client email accounts for ALDOR alerts (high daily volume).
- Manual texting for monthly revenue requests (highly fragmented and time-consuming).

**Automation Pipeline (In Progress)**:

- Bank statement processing: `smart_check_cropper_final_dynamic.py` + `bank-statement-parser.py` + `Process-Statement.ps1`.
- OneDrive → local processing → CSVs for Power Query.
- Sample output available (`Auto_Body_Center_Jan_26_Statement_Transactions_With_Payees.csv`).

**Hardware & Access**:

- Desktops for Laura & Stef; laptops for Patty & Robert.
- No significant mobile usage currently.

**Key Pain Points**:

- High fragmentation and reliance on Laura’s memory.
- Tech fatigue (“necessary evil” mindset).
- No centralized visibility or automated reminders.
- Revenue chasing and bank recs remain the biggest bottlenecks.

### Phase 1 Quick Win: Revenue Reporting Tracker (Completed May 22, 2026)

**Status**: ✅ Successfully Completed  
**Owner**: Robert Gonzalez + Grok  
**Key Deliverables**:

- Normalized migration of `Client_Import.csv` + `2025 Client Progress.xlsx` → `RevenueRequests.csv`
- Live data location: `Data/Revenue_Tracker_Migration/RevenueRequests.csv`
- Fully functional **Streamlit Revenue Reporting Tracker** (`App/app.py`)
  - Real-time metrics, status filters, pie + bar charts
  - Searchable Clients and Revenue Requests tables
  - Document status visibility and Access Block Notes

**Success Achieved**:

- Centralized visibility into pending revenue requests
- Reduced manual chasing friction
- Live dashboard running locally with real data

---

## 4. Goals & Success Metrics

**Primary Goals**:

- Reduce manual revenue chasing and reconciliation time significantly.
- Achieve high-accuracy automated extraction.
- Create internal operational dashboards.
- Establish clear processes and retention rules.
- Win Laura’s confidence in structured automation.

**Success Metrics**:

- Time saved per month on revenue reporting
- % of clients with up-to-date status visible in dashboard
- Reduction in manual follow-ups
- Laura’s qualitative feedback on reduced stress

---

## 5. Stakeholder Map

| Role               | Person(s)               | Needs / Concerns                      | Access Level     |
| ------------------ | ----------------------- | ------------------------------------- | ---------------- |
| Owner / Bookkeeper | Laura Bouchard          | Control, nuance, reduced stress       | Full             |
| Staff              | Stef (daughter)         | Reduced manual toil, clear processes  | High             |
| Transition Team    | Robert & Patty Gonzalez | Prove value, build sustainable system | High / Admin     |
| Clients            | ~100 small businesses   | Minimal disruption                    | Limited (future) |

---

## 6. Technical Architecture & Platform Strategy (Updated v2.3)

**Hybrid & Code-First Approach**:

- **Frontend/Dashboard**: Streamlit (Python) for high customizability and rapid iteration
- **Data Layer**: Google Drive / OneDrive CSVs (short-term) → PostgreSQL or Azure SQL (long-term)
- **Automation**: Azure Functions + Logic Apps
- **Development**: VS Code + Grok as coding agent

**Platform Decision**:

- **Power Apps / Power Platform**: Evaluated but deprioritized for core solution due to low-code constraints on schema changes, complex custom logic, and Python/Streamlit integration challenges.
- **Preferred Long-Term Platform**: **Microsoft Azure** (code-first) with **PostgreSQL** as the top database recommendation
  - Azure App Service for hosting Streamlit
  - Azure Database for PostgreSQL (Flexible Server) or Supabase
  - Azure Functions for automation pipelines
  - Strong security suitable for sensitive client financial data

**Current Tools in Use**:

- Python scripts (smart_check_cropper, bank-statement-parser, etc.)
- Streamlit dashboard
- Google Drive / OneDrive for data sync

### 6.1 Alignment with Original Business Problem (Power Platform Plan)

The current Blueprint **strongly aligns** with the original `Business problem.docx` in terms of:

- Business challenges (manual processes, memory reliance, stress, scalability)
- Core goals (digitization, real-time visibility, automated reminders, compliance)
- User requirements for bookkeeper and clients
- Key processes (document submission, operations, status tracking)

**Strategic Evolution**:
We have chosen a **code-first approach** (Streamlit + PostgreSQL/Azure) over a pure Power Platform solution. This decision provides:

- Greater flexibility for complex logic (Python-based bank statement parsing, AI extraction)
- Better long-term maintainability and cost control
- Easier integration with existing Python scripts
- Full control over data schema and custom workflows

The original Power Platform plan remains a valuable reference, especially for Dataverse-inspired data model ideas and automation patterns (which we are implementing via Azure Functions and Python).

---

## 7. Data Foundations

**Core Data Model** (PostgreSQL / Azure SQL compatible)

The data model is heavily inspired by the original `Business problem.docx` Dataverse proposal, adapted for a code-first relational database. It uses normalized tables with proper relationships, audit fields, and support for document linking.

### Main Entities & Key Fields

**Clients** (Core master table)

- `client_id` (PK, UUID or serial)
- `business_name`
- `owner_name`
- `email`, `phone`, `address`
- `industry_type` (e.g., Restaurant, Bar, Construction)
- `status` (Active, Inactive, Prospect)
- `onboarding_date`, `notes`
- `access_block_notes` (from existing data)

**RevenueRequests** (Phase 1 focus – tracks revenue chasing)

- `request_id` (PK)
- `client_id` (FK)
- `request_type` (e.g., Monthly Bookkeeping, Sales Tax, Liquor Tax)
- `period` (e.g., "2025-04")
- `amount_due`
- `status` (Pending, Received, Invoiced, Paid)
- `due_date`
- `received_date`
- `document_links` (JSON or separate table)
- `notes`

**Documents**

- `document_id` (PK)
- `client_id` (FK)
- `document_type` (BankStatement, PayrollData, SalesReport, LiquorTaxReport, TaxForm, etc.)
- `file_name`, `file_path` (Google Drive/OneDrive link)
- `upload_date`, `uploaded_by`
- `status` (Received, Processed, Archived)
- `ai_extraction_confidence`
- `linked_to` (e.g., BankReconciliation ID, PayrollRun ID)

**BankStatements**

- `statement_id` (PK)
- `client_id` (FK)
- `document_id` (FK)
- `statement_month`
- `bank_name`
- `starting_balance`, `ending_balance`
- `processing_status`
- `ai_extraction_date`

**Transactions**

- `transaction_id` (PK)
- `statement_id` (FK)
- `client_id` (FK)
- `date`, `description`, `amount`
- `category` (AI-assisted)
- `reconciliation_status` (Matched, Unmatched, Pending)
- `matched_to` (reference to bookkeeping entry)

**BankReconciliations**

- `reconciliation_id` (PK)
- `client_id` (FK)
- `statement_id` (FK)
- `period`
- `status` (In Progress, Completed, Reviewed)
- `difference_amount`
- `completed_date`
- `reviewed_by`

**PayrollRuns**

- `payroll_id` (PK)
- `client_id` (FK)
- `pay_period`
- `pay_date`
- `total_gross`, `total_net`, `total_taxes`
- `status`
- `document_id` (FK)

**SalesTaxFilings** & **LiquorTaxFilings**

- Similar structure to PayrollRuns with filing-specific fields (due_date, filed_date, confirmation_number, liability_amount)

**Invoices**

- `invoice_id` (PK)
- `client_id` (FK)
- `invoice_date`, `due_date`
- `total_amount`
- `status` (Draft, Sent, Paid)
- `linked_services` (JSON array of related Payroll/BankRec/etc. IDs)

**Tasks** / **Communications** / **Reminders**

- Support tracking of deadlines, notes, messages, and automated reminders.

**Audit Fields** (on all tables)

- `created_at`, `updated_at`
- `created_by`, `updated_by`
- `is_deleted` (soft delete)

**Relationships**

- One-to-Many: Client → Documents, RevenueRequests, BankReconciliations, PayrollRuns, etc.
- Many-to-Many: Documents ↔ Services (via junction table if needed)

This schema supports the full scope from the original Business Problem (document management, bank recs, payroll, tax filings, invoicing, reminders).

---

### Current CSV Foundation

- `Clients.csv` and `RevenueRequests.csv` serve as the initial seed for this model.

---

## 8. Core Workstreams

1. Revenue Reporting Automation (Phase 1 Complete)
2. Enhanced Bank Statement & Check Payee Pipeline
3. Internal Dashboards & Task Management
4. Automated Ingestion & Reminders
5. Document Management & Retention
6. Invoicing & Receivables Tracking

### 8.1 Future Bank Statement & Accounting Automation

This subsection captures the forward-looking roadmap for evolving the bank statement pipeline into a fuller, modern bookkeeping platform tailored to SLAM Services. These items extend (and do not replace) the current lightweight in-app pipeline (`Scripts/bank-statement-parser.py` + Bank Statements page) and remain fully compatible with the existing CSV / Power Query / Process-Statement.ps1 workflow.

**Delivered (v2.38 / v2.38.1 / v2.38.2)**

- Native **"Paste Grok-extracted CSV"** support in the Bank Statements page (Option 2). After running Grok Vision, users can paste the full CSV output (or upload the saved file) directly into the app via the **📋 Option 2: Paste Grok-extracted CSV here** section (400px `st.text_area` with placeholder showing the expected header + sample row + trailing `TOTALS:` line, plus a CSV `st.file_uploader`). The `load_grok_vision_csv()` helper in `App/bank_statements.py` accepts pasted text, raw bytes, or any uploaded file-like object; strips the `TOTALS:` summary line and stray markdown fences; validates the required header (`Date`, `Description`, `Amount`); fills missing optional columns with safe defaults; and returns a DataFrame in the canonical 12-column shape that flows straight into the same review UI/metrics/confidence filter/amber row highlight/`st.data_editor`/Download CSV/**Mark as Received** as the parser path. This eliminates the last manual file-saving step for scanned/image-only statements and closes the *save-as-CSV → PowerShell* gap. Process-Statement.ps1 and the Power Query model continue to work unchanged for users who prefer the file-based path.
- **v2.38.1 — bulletproof CSV parsing**: `load_grok_vision_csv` now uses `engine='python'`, `quoting=3` (`csv.QUOTE_NONE`), and `on_bad_lines='warn'` so unquoted commas inside Description/Payee fields (common in real Grok output, e.g. `AMAZON.COM*XX1, INC`) no longer crash the parse with `Expected N fields in line X, saw Y`.
- **v2.38.2 — automated statement reconciliation check**: Every loaded statement now compares the detailed rows against the bank's summarized totals. `load_grok_vision_csv` returns a 2-tuple `(df, grok_totals)` where `grok_totals` is parsed from Grok's trailing `TOTALS: deposits=… withdrawals=… checks=… transactions=…` line (captured before `_strip_grok_csv_noise` removes it). New `reconcile_statement_totals(df, grok_totals)` helper compares deposits, withdrawals (absolute), check count, and total transaction count using `transaction_summary_metrics` for the computed values and a penny-level tolerance for dollar fields. Returns a structured dict (`status`: `match` | `mismatch` | `no_reference`, `message`, `differences`, `needs_review`, `computed`, `reported`). The Bank Statements page renders the result as a prominent ✅/⚠️ banner directly above the **Transactions (review & edit)** section: green success when every total matches, red error with a side-by-side reconciliation table (source vs. computed, per-field diff) when there is a mismatch, and a neutral caption when no source TOTALS line is present (parser path or older Grok output). Mismatches automatically set `bank_stmt_needs_review` in session state so the whole statement is flagged for review, and emit a `bank_stmt_reconciliation_mismatch` audit log event. This closes the assurance gap raised after v2.38.1 — Laura now sees, on every statement, whether what flows into Power Query / Process-Statement.ps1 actually matches the source material.

**Strategic Next Milestone (Highest Priority — next 1–2 weeks)**

- Build a **dedicated Azure Function for heavy OCR processing**. Offload `pdf2image` + EasyOCR/Tesseract (or Azure Document Intelligence prebuilt bank-statement models) and OpenCV-based check cropping from the Streamlit App Service to a purpose-built Function (or Container App). The app uploads the PDF → Function returns structured transactions, cropped check images, and confidence metadata. Graceful fallback to the existing parser or Grok Vision path. Keeps the App Service slim and within reasonable Azure SKU limits while removing the final manual step for the most common case (scanned Traditions Bank statements).

**Quick Parallel Win (Delivered in v2.39)**

- Lightweight **persistent payee rules engine** is live in `App/bank_statements.py` + `Data/payee_rules.csv` (gitignored, seeded with 25 high-value merchant patterns including all three common Walmart spellings, both Amazon spellings, the major fuel/utility/transfer/bank-fee patterns, and Intuit/QuickBooks).
  - **Storage**: `Data/payee_rules.csv` with columns `pattern,clean_payee,suggested_category,client_override,notes,last_used`. Resolution order: `SLAM_PAYEE_RULES_PATH` env override → repo root → cwd → `/home/site/wwwroot` → `App/`. Auto-created on first save.
  - **Matching**: case-insensitive substring on `Description` by default; full regex via a `re:` pattern prefix. Client-specific rules win over global rules; on tie, the longest pattern wins. The `last_used` ISO date is bumped automatically each time a rule fires.
  - **Auto-apply**: every parser pipeline run AND every Grok CSV paste now runs `apply_payee_rules(df, client_name=…)` before the data ever reaches the review editor. A green **"🧠 X payee mapping(s) applied"** callout shows exactly how much the engine improved.
  - **Manual edits preserved**: Payee is overwritten only when blank or equal to the raw Description (Grok's fallback); Category is overwritten only when blank or `Uncategorized`. Re-applying never clobbers Laura's downstream Power Query work.
  - **Learn-this-mapping form**: collapsible **💡 Learn this mapping** expander on the review page lets Laura pick any row, edit the suggested pattern / clean Payee / Category, optionally scope to the current client, and persist with one click — the rule is upserted and reapplied across the open statement immediately. Idempotent `🔄 Apply Payee Rules` button is available for ad-hoc cleanup after edits.
  - **Audit + visibility**: structured `log_event` topics (`bank_stmt_payee_rules_applied`, `bank_stmt_payee_rules_reapplied`, `bank_stmt_payee_rule_learned`, `bank_stmt_payee_rules_error`) plus a **Rules improved** metric next to the Apply button. The Grok Vision prompt now tells Grok its best-effort Payee/Category will be refined (not replaced) by the rules engine after import.
  - **Defensive**: missing or empty rules file is a silent no-op; CSV column order, Power Query layout, and Process-Statement.ps1 workflow are all unchanged.

**Longer-term items (Phase 3 — aspirational)**

- **Automated P&L creation and financial reporting**: Generate per-client Profit & Loss statements (and supporting reports — cash flow, category trends, period-over-period comparisons) directly from parsed transactions once categorization is reliable. Designed to reduce dependence on QuickBooks Desktop for routine reporting.
- **Intelligent check-image cropping + automatic transaction linking**: Extend `smart_check_cropper_final_dynamic.py` so that each cropped check image is automatically linked back to its originating transaction line item (by check number, amount, and date). The reconciliation UI can then display the check image inline next to the parsed row for instant verification.
- **OneDrive folder watcher / auto-sync**: A scheduled job (Azure Function on a timer trigger, or a lightweight watcher service) that monitors designated OneDrive client folders for new bank statement PDFs, ingests them automatically, runs the parser, and surfaces the resulting transactions in the Bank Statements page — eliminating the manual upload step.
- **Broader modern accounting features tailored to SLAM Services**: Role-based views (Laura / Stef / Patty / Robert), client-facing invoicing, receivables tracking with aging buckets, an enhanced audit trail (who changed what, when, and why), and client-specific dashboards. Together these move the platform from a revenue-chasing tool toward a defensible, multi-user bookkeeping practice system.

These capabilities keep the current pipeline simple and reliable while giving us a clear, prioritized path toward full automation. Longer-term items will be sequenced under Phase 3 of the Phased Roadmap (Section 10).

---

## 9. Document Retention Policy (Recommended)

- **Federal (IRS)**: 3–7 years standard, tax returns indefinitely
- **Alabama**: Minimum 6 years for sales/use tax
- **SLAM Policy**: Digitize everything, retain digital copies 7 years minimum, tax returns indefinitely. Use system flags for safe physical destruction.

---

## 10. Phased Roadmap

**Phase 1 – Quick Wins & Proof** (Mostly Complete)

- Revenue Reporting Tracker with Streamlit dashboard (local version ready)

**Phase 2 – Core Operations** (Deployed)

- Azure infrastructure setup complete (Resource Group `SLAM-Services-RG`, App Service on Linux)
- Successful secure deployment of Streamlit Revenue Tracker (v2.8)
- Startup command fixed for dynamic `$PORT` + headless mode
- Basic password protection hardened via `SLAM_APP_PASSWORD` App Setting (never stored in source)
- HTTPS-only enforced; ready for team testing

**Next Immediate Actions**:

- Resolve Azure vCPU quota (for scaling / Always On)
- Optional: Upgrade authentication to Azure Entra ID / Easy Auth
- Connect real `Clients.csv` and `RevenueRequests.csv` to live app (CI/CD or deployment package)
- Begin team user testing & feedback loop

**Phase 3 – Scale & Professionalization**

- Full automation pipelines — including the future bank statement & accounting automation roadmap captured in **Section 8.1**: dedicated Azure Function for heavy OCR (OpenCV / EasyOCR / pdf2image / Tesseract), automated P&L generation from parsed transactions, QuickBooks-style persistent rules engine with fuzzy payee matching, intelligent check-image cropping with automatic linking back to transaction line items, and OneDrive folder watcher / auto-sync for incoming statements.
- Role-based views (Laura / Stef / Patty / Robert) and client-specific dashboards (per Section 8.1).
- Document management with enhanced audit trail and retention enforcement.
- Invoicing and receivables tracking expansion (per Section 8.1).
- Continuous improvement driven by the persistent feedback log (Section 14.3).

---

## 11. Open Questions & Decisions Needed

- Final confirmation on Azure / PostgreSQL migration timeline
- Laura’s comfort level with specific automation features
- Desired metrics for success from Laura’s perspective

---

## 12. Appendices & Related Assets

- Original Business problem.docx
- Python scripts and PowerShell wrappers
- Client_Import.csv, RevenueRequests.csv, etc.
- Streamlit app (`App/app.py`)

---

## 13. Project Management & SDLC Approach

**Current Status** (as of May 22, 2026):

- SDLC Phase 3 (Implementation): Active
- Development environment: Local + Azure CLI configured
- Tooling: Azure CLI v2.86.0 (64-bit), PowerShell, Cursor/VS Code integration

### 13.1 Overview

This project follows a **lightweight, pragmatic Software Development Life Cycle (SDLC)** designed specifically for our small internal digital transformation initiative.

The SDLC provides detailed execution guidance that supports and complements the high-level **Phased Roadmap** (Section 10). It combines:

- **Phase-based structure** for clear milestones, governance, and stakeholder visibility (especially important for Laura).
- **Agile principles** for flexibility, rapid iteration, and quick wins within each phase.

This approach ensures we maintain momentum on Phase 1 while building sustainable, auditable processes.

### 13.2 SDLC Phases

| Phase                                       | Description                                     | Key Activities                                                     | Primary Deliverables                                          | Owner(s)                            | Current Status                      |
| ------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------- | ----------------------------------- | ----------------------------------- |
| **1. Planning & Requirements**              | Gather, document, and prioritize business needs | Stakeholder input, user stories, success metrics, scope refinement | Requirements backlog, prioritized user stories, KPIs          | Robert / Grok                       | In Progress                         |
| **2. Design**                               | Define technical and process architecture       | Data models, process flows, integration design, tool selection     | Design documents, diagrams, decision records                  | Robert / Grok                       | Not Started                         |
| **3. Implementation**                       | Build and configure the solution                | Coding, scripting, Power Automate flows, Dataverse setup           | Functional scripts, flows, prototypes                         | Robert / Grok                       | Bank Statement Parser (In Progress) |
| **4. Testing**                              | Validate quality and correctness                | Unit/integration testing, data validation, edge cases              | Test plans, test results, defect log                          | Robert / Grok + Laura/Stef (review) | Not Started                         |
| **5. Staging & User Acceptance (UAT)**      | End-user validation in controlled environment   | Deploy to staging, hands-on testing, feedback                      | UAT report, approved changes                                  | Laura / Stef + Robert/Grok          | **In Progress (v2.33)**             |
| **6. Deployment**                           | Roll out to production use                      | Go-live, training, documentation handover                          | Production solution, training materials, deployment checklist | Robert / Grok                       | Not Started                         |
| **7. Maintenance & Continuous Improvement** | Ongoing support and evolution                   | Monitoring, enhancements, periodic reviews                         | Change log, version history, retrospectives                   | Robert / Grok + Team                | Not Started                         |

**Note**: These SDLC phases operate within the broader **Phased Roadmap** (Section 10). Phase 1 of the roadmap will primarily cover SDLC Phases 1–6 for the initial quick wins.

### 13.3 Key Practices

**Iterative Development**

- Work in short **1–2 week iterations** (sprints) during active development.
- Each iteration concludes with a brief review and demo.

**Definition of Done (DoD)**  
All work items must satisfy:

- Code/scripts are written, commented, and tested.
- Documentation updated in Blueprint.md.
- Reviewed by Grok.
- Ready for stakeholder visibility (where appropriate).

**Documentation & Decision Making**

- **Blueprint.md** is the **Single Source of Truth**.
- Maintain a **Change Log** at the top of this document.
- Record major decisions in a **Decision Log** (Section 13.5).

**Risk Management**  
A simple **Risk Register** will be maintained to track and mitigate issues such as data quality, user adoption, and technical risks.

### 13.4 RACI Matrix (High-Level)

- **Responsible**: Performs the work (primarily Robert/Grok)
- **Accountable**: Ultimately owns the outcome (Robert with Laura oversight)
- **Consulted**: Must be involved before decision (Laura/Stef on key items)
- **Informed**: Kept updated on progress

### 13.5 Supporting Templates & Logs

- **Decision Log** – To be added as subsection 13.5.1
- **Risk Register** – To be added as subsection 13.5.2
- **User Stories Backlog + Runtime Feedback Process** – Fully implemented in Section 14 (v2.11) as the living **Phase 2.5 Stabilization Backlog and Feedback System**

**Last Updated**: May 23, 2026 (Phase 2.5 kick-off: structured persistent feedback process + Phase 2.5 Rollout Plan integrated)
## 14. User Stories, Runtime Feedback & Phase 2.5 Stabilization (Added v2.11)

**Status (May 23, 2026 evening)**: First live production user-testing session completed on the deployed Azure App Service using real 2026 client data. Seven specific runtime issues were captured in real time and logged for immediate action. This section is the single source of truth for the current stabilization backlog and the new persistent feedback process.

### 14.1 Phase 2.5 Context & Purpose

- **Objective**: Stabilize the live Revenue Tracker so Laura, Stef, Patty and Robert can use it daily without friction before any further feature work or database migration.
- **Trigger**: Real usage on `https://slam-services-revenue-tracker.azurewebsites.net/` with the actual `Clients.csv` + `RevenueRequests.csv` files.
- **Key Inputs**: `Project Runtime User Stories.txt` (7 raw notes) + direct observation.
- **Output Deliverable**: This Section 14 + the living `Data/feedback_log.csv` file (permanently versioned inside the source tree and deployable).

### 14.2 Phase 2.5 Prioritized Rollout Plan (Immediate 1–2 Week Horizon)

| Wave | Priority | Status (v2.25) | Item (from runtime notes) | Current Root Cause in app.py | Target Fix Description | Owner | Success Metric |
|------|----------|----------------|---------------------------|------------------------------|------------------------|-------|----------------|
| P0 – Day 1 | P0 | **Done** | "request_id" and "business_name" columns show blank / no useful data in Dashboard Overdue table and Recent Activity | Tables are selecting columns that do not exist or have different casing after load_clients()/load_requests() transformations | Change column selections in dashboard_page() to always use the standardized snake_case columns that load_requests() guarantees (`business_name`, `request_id`) | Robert | No blank columns in those two tables on next deploy |
| P0 – Day 1 | P0 | **Done** | Global Filter "Reset filters" button does nothing useful (cache clear alone not enough) | Current reset only clears cache but does not reset widget state | Change reset logic to also force a full page rerun + clear any session widgets | Robert | Button reliably clears all filters and shows all data |
| P0 – Day 1 | P0 | **Done** | Revenue Requests page Right-most columns are missing the service Yes/No checkboxes that were added to RevenueRequests.csv | The data_editor is hard-coded to a fixed list of columns; `bank_statement_received` and `sales_report_received` exist in CSV but the UI is not using "Yes/No" checkbox config | Add those two columns explicitly with proper checkbox column config in the data_editor | Robert | Checkboxes visible and editable on the Revenue Requests table |
| P1 – Day 2 | P1 | **Done** (UI) / **Partial** (data) | Request Type filter is missing "Payroll" and "Tax prep" values (only sees what is currently in the live CSV) | The data simply does not contain those request_types yet — they were requested during the 2025 migration but never generated | Add a generation script option or quick data patch (Scripts/generate_revenue_data.py already knows how); document as known gap until full Chart of Accounts mapping exists | Robert + Patty | Payroll and Tax prep appear as filter options when users request them |
| P1 – Day 2 | P1 | **Done** | "Quick Bulk Status Update" dropdown still shows raw request_id instead of friendly business_name values | The multiselect is bound to `df['request_id']` instead of using the request-specific business_name lookup that already exists in the row | Change the label in the multiselect to "rid – business_name" or switch entirely to business_name + multi-row selection | Robert | Users can select by client name in bulk update |
| P2 | P2 | **Done** | Edits in the Revenue Requests table have no undo; users worry about accidental data loss | Current save is irreversible write-back to the single CSV with no transaction log | Implement simple in-memory undo stack (last 5 states) + "Undo Last Save" button before writing to disk; later can be upgraded to full audit fields once on PostgreSQL | Robert | One-click recovery within the session after an edit mistake |
| P2 | P2 | **Done** | "First column" in the Revenue Requests table shows no useful data (index or unnamed column) | pandas index leakage or the data_editor trying to render the implicit index | Explicitly hide the index (`hide_index=True`) + choose only the 11 real columns | Robert | Clean table with only meaningful columns |

**Daily driver (v2.33):** Dashboard **Today's priority** (full overdue list at top — not filter-dependent); v2.32 UAT features (unsaved-change guards, quick views, checklist). Robert runs `Check-AppHealth.ps1 -Full` before UAT sessions.

**Daily driver (v2.31):** Dashboard "Today's priority" briefing, sidebar Overdue/Pending quick views, data freshness + help + logout, `slam_app` logging to Azure log stream. Robert uses `Sync-DataRefresh.ps1` after CSV edits when on PostgreSQL.

**Deploy note (v2.30):** GitHub Actions deploys **code only** (`clean: false` preserves existing `Data/` on App Service). Phase 3 production path: Azure PostgreSQL Flexible Server → `init_db.py` → `migrate_to_postgres.py` → `health_check.py` → `USE_POSTGRES_SSLMODE=require` App Settings → `Deploy-PostgresProduction.ps1`. CSV fallback: `USE_POSTGRES=false` or automatic when DB unreachable. Sidebar Data Source Status + recovery options (v2.29–v2.30).

**P0 items must be fixed and redeployed before any broader team access (Patty + Stef daily use).** — App fixes complete; confirm live deploy after CI secret or manual zip.

### 14.3 Structured Persistent Feedback Process (Core Component of Phase 2.5 & Beyond)

**Goal**: Every observation from Laura, Stef, Patty or Robert is captured in a durable, searchable, versioned format instead of Slack texts or memory.

**Mechanism (already implemented live in the app)**:

1. Any authenticated user opens the sidebar “📣 Submit Runtime Feedback” expander.
2. Required fields: Reported by (select), Category (select), Description (free text), Priority.
3. On submit, the row is **immediately appended** to `Data/feedback_log.csv` inside the running container (and therefore survives the session).
4. On next git pull / redeploy the same file is present with full history.
5. Robert (or designate) reviews the log at the start of every 1-week iteration, triages into P0/P1/P2, updates this Section 14, and marks rows “In Progress” / “Done”.

**CSV Schema** (header already present):
```
timestamp,reported_by,category,description,priority,status,version
```
- `status` values: Open / In Progress / Done / Deferred / Duplicate
- `version` = the app/git version string at the time of submission (helps trace regressions).

**Governance**: The log is treated as source-controlled data. It is **never** deleted. Historical rows are kept indefinitely for project memory and audit purposes (ties directly into the 7-year SLAM document retention policy).

**Manual seed (from first live session – May 23 2026)**:
The original 7 issues from `Project Runtime User Stories.txt` were transcribed into the same format and placed at the top of `feedback_log.csv` so the history is continuous.

### 14.4 How This Section Updates the Overall Roadmap

- Phase 2 (Infrastructure & first live deployment) is now considered **substantively complete** once P0 items are shipped.
- Phase 2.5 is the explicit “stabilize + learn” sprint before Phase 3 (full automation + PostgreSQL + Azure Files / Always On).
- All future user stories for bank statement automation, payroll runs, document management, etc. will be **derived from** entries that first appear in this living feedback log.
- This closes the gap between the original Blueprint promise of a “User Stories Backlog (Section 14)” and actual delivered working practice.

**End of Section 14 (v2.11)**.
