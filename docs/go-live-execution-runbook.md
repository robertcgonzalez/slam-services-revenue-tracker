# Azure DI Bank Statement Go-Live — Execution Runbook (2026-05-29)

**Status**: **Partial cut-over — imaging leg now live.** Register/tabular DI works; **check/imaging leg delivered in production** after cropper threshold fix (2026-05-30). Laura pilot may proceed for imaging smoke; Auto Body sparse-register supplemental append remains a follow-up. See Path A / Path B at end of this document.  
**Session**: Cursor (primary agent) drove Phases 0–3 and documentation; Robert executed Phase 4 live smoke on production.  
**Live URL**: https://slam-services-revenue-tracker.azurewebsites.net/  
**Blueprint record**: v2.44.20 Change Log entry (draft for owner review) supersedes the anticipatory v2.44.19 narrative.

---

## Current execution state (2026-05-29)

| Layer | State |
|-------|--------|
| Gate A1 (B2) | **Done** |
| Gate A2 (P0 imaging deploy) | **Done** — OpenCV, pdf2image, Poppler, page clamping, code-only deploys |
| **Data layer** | **DONE** — `Invoke-DataLayerGoLive.ps1` executed; `slam-services-db` (centralus); **98 clients / 36 requests** migrated; `USE_POSTGRES=true`; app healthy on B2 |
| **Gate A3 (re-smoke)** | **PASS (2026-05-31)** — Deploy `1ef9aa54`; HCC **PASS** (98 rows, 42 crops, gold totals). Auto Body **PASS** — 94 rows (44 reg + 50 supp), withdrawals **$41,130.18** vs gold **$41,403.63**, deposits **$41,786.80**. Evidence: [`Gate-A3-Final-Re-Smoke-Evidence-Guide.md`](gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md). **Laura pilot cleared (Path A).** |

### Gate A3 minimal-interaction flow (2026-05-29+)

1. **Preferred — headless (no browser):** `Invoke-GateA3HeadlessSmoke.ps1 -WaitMinutes 35` (Kudu PDF upload + `SLAM_RUN_GATE_A3_SMOKE` app restart).
2. **Alternative — browser (owner-only):** Bank Statements → upload + **Process Statement** for the two canonical PDFs (no screenshots, CSV downloads, or log copy).
3. **Collect evidence:** `Collect-GateA3Evidence.ps1 -Both -UpdateDocs` (harvests Kudu logs, fills evidence guide + scorecard, writes `deploy-logs-temp\gate-a3-intake-bundle.json`).

**Supporting artifacts:**
- [`Gate-A3-Owner-Execution-Package-Final.md`](gate-a3/Gate-A3-Owner-Execution-Package-Final.md) — deploy + minimal smoke sequence
- [`Gate-A3-Final-Re-Smoke-Evidence-Guide.md`](gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md) — auto-filled by collector
- [`Scripts/PowerShell/Collect-GateA3Evidence.ps1`](../Scripts/PowerShell/Collect-GateA3Evidence.ps1) — autonomous evidence harvest
- [`Scripts/PowerShell/Test-GateA3Poppler.ps1`](../Scripts/PowerShell/Test-GateA3Poppler.ps1) — imaging leg probe (`-CheckSmokeEvidence` after smoke)

Diagnosis, 2026-05-29 baseline evidence, and poppler/assembly fix notes: **Handoff → Gate A3** sections below.

**After collector runs:** Review auto-filled [`Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`](gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md), record final verdict here, propose Path A/B (commit only if owner approves).

### Execution log (data layer — live)

| Time (UTC/local) | Phase | Result |
|------------------|-------|--------|
| 2026-05-29 | P0 preflight | **PASS** — `az` session `robert@NextMoveSolutions.onmicrosoft.com`; CSVs + `.venv` OK |
| 2026-05-29 | P1 provision | **PASS** — `slam-services-db` in **centralus** (eastus restricted on subscription); provider `Microsoft.DBforPostgreSQL` registered; firewall: laptop IP + AllowAzureServices + App Service outbound IPs |
| 2026-05-29 | P2 migrate | **PASS** — `init_db` + migrate; **98 clients, 36 requests** in `slam_services` (local `health_check --verify-only`) |
| 2026-05-29 | P3 app settings | **PASS** — `USE_POSTGRES=true`, `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_SSLMODE`, `POSTGRES_PASSWORD` (portal only) |
| 2026-05-29 | P4 deploy | **PASS** — code-only `slam-app.zip` clean deploy; Kudu `complete=true` |
| 2026-05-29 | P5 health | **PASS** — App Service **Running**; local PG counts match migration |
| 2026-05-29 | Gate A3 | **Owner re-smoke executed** — evidence paste pending analysis |
| 2026-05-30 | Gate A3 | **Re-smoke deploy `4fa54010`** — HCC PASS; Auto Body rows PASS / withdrawals FAIL |

**Notes:** Admin password is in repo-root `.env` (gitignored) only. If laptop cannot reach TCP/5432, use `Scripts/PowerShell/Invoke-PostgresMigrateViaAci.ps1` (blob + one-shot ACI). Removed `AllowAllTemp` firewall rule after migration.

### Cursor — after owner pastes Gate A3 re-smoke evidence

1. Use [`Gate-A3-Final-Re-Smoke-Evidence-Guide.md`](gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md) (owner-filled) and complete [`Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`](gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md).
2. Update this runbook with final Gate A3 verdict, check/imaging leg status, and Path recommendation.
3. **Propose** exact commit scope + message and `apply docs` decision (only execute after human approval and only on Path A success).

### Hard owner-only blockers

| Blocker | Why |
|---------|-----|
| DB admin password | Cannot invent or read from `.env` in chat — one secure prompt on your machine |
| Gate A3 live browser smoke | Real PDFs + Processing log on production URL |
| `az login` if session expired | Interactive auth |

**Never do:** Upload `Data/` to App Service or `-IncludeData` production deploys.

---

## Timeline honesty (read this first)

| When | What happened |
|------|----------------|
| **Prior work (planning)** | `Set-AzureBankStatementDIAppSettings.ps1`, `docs/DI-Go-Live-Commands.md`, `docs/DI-Go-Live-Execution-Prompt.md`, `db/schema.sql`, rename prompt, and Blueprint **v2.44.19** / README **“Post DI Go-Live”** text were written as **forward-looking / anticipatory** artifacts — they described the *intended* state, not Azure reality. |
| **2026-05-29 (this session)** | **Actual production execution**: S0 upgrade, DI App Settings applied, code deploy, health check, Robert live smoke. |
| **After smoke** | Register/tabular DI shows basic function but **non-repeatable** results; **check/imaging leg failed** in production. **Do not** treat the go-live as complete for daily driver use or Laura pilot until blockers below are resolved. |

---

## Owner confirmation log

| Gate | Owner signal | Date |
|------|--------------|------|
| Phase 1 — S0 upgrade | `proceed` (CLI) | 2026-05-29 |
| Phase 2 — real setter (no `-WhatIf`) | `proceed` | 2026-05-29 |
| Phase 3 — deploy | `proceed` (defaults; stop/start + smoke OK) | 2026-05-29 |
| Phase 4 — smoke plan | **Approved** (Mark as Received: test-only or skip; full Processing log for ≥1 PDF) | 2026-05-29 |
| Phase 4 — execution | Robert (human) on live URL | 2026-05-29 |
| Rollback test (`-DisableDI`) | **Not exercised** this session | — |
| Laura / team pilot | **Not scheduled** — blocked on check leg | — |

---

## Pre-flight baseline (Phase 0 — read-only, 2026-05-29)

| Item | Value |
|------|-------|
| Azure account | `Azure subscription 1` · `robert@NextMoveSolutions.onmicrosoft.com` |
| DI resource `slam-bank-statements` | **F0** → upgraded in Phase 1 |
| App Service | `slam-services-revenue-tracker` · Running |
| `AZURE_DI_*` on App Service | **Absent** (only legacy `AZURE_OCR_FUNCTION_*` → old Function URL) |
| Local health | CSV OK (99 clients, 36 requests); Postgres not configured in local shell |
| Test PDFs | `Data/Auto_Body_Center_Jan_26_Statement.pdf` ✅ · `Data/HCC 2026-04.pdf` ✅ · `Data/Altitude_Base_Coatings_Jan_26_Statement.pdf` ❌ |
| Doc vs reality | Blueprint v2.44.19 + README claimed go-live **already done** — **incorrect** until this session |

---

## Phase 1 — DI resource S0 upgrade

**Command:**

```powershell
az cognitiveservices account update `
  --name slam-bank-statements `
  --resource-group SLAM-Services-RG `
  --sku S0
```

**Verification:**

| | SKU |
|---|-----|
| Before | F0 |
| After | **S0** |

Endpoint unchanged: `https://slam-bank-statements.cognitiveservices.azure.com/`

---

## Phase 2 — Production DI App Settings

**Command:**

```powershell
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1
```

**Settings applied (values redacted in logs; keys = 84 chars):**

| Setting | Value (non-secret) |
|---------|-------------------|
| `AZURE_DI_ENDPOINT` | `https://slam-bank-statements.cognitiveservices.azure.com/` |
| `AZURE_DI_MODEL` | `prebuilt-bankStatement.us` |
| `AZURE_DI_CHECK_MODEL` | `prebuilt-check.us` |
| `SLAM_IMAGING_FIRST_PAGE` | `5` |
| `SLAM_IMAGING_LAST_PAGE` | `9` |
| `AZURE_OCR_FUNCTION_URL` / `KEY` | Repointed to DI endpoint (backward-compat aliases) |

**Rollback (valid anytime):**

```powershell
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI
# Optional: .\Scripts\PowerShell\Deploy-ToAzure.ps1
```

---

## Phase 3 — Code deploy

| Step | Result |
|------|--------|
| `Build-AzureDeployZip.ps1` | `slam-app.zip` **181.81 MB** (includes local `Data/`) |
| `Deploy-ToAzure.ps1` | Client script **interrupted** ~15 min on `az webapp deploy --async true` |
| Kudu OneDeploy | **Successful** — deploy id `e39d90f2-fc0b-40b1-a4b0-063c51836b85`, completed **2026-05-29T05:26:05 UTC** |
| Recovery | Manual `az webapp start`; HTTP **200** on retry |
| `Check-AppHealth.ps1 -Full -CheckAzure` | CSV OK locally; App Service **Running**; **no DI probe** |

**Root `requirements.txt` note:** Contains `streamlit`, `pandas`, `azure-ai-documentintelligence`, etc. — **does not** include `opencv-python-headless`, `pdf2image`, `pillow`, or `easyocr` (relevant to Phase 4 cropper failure).

---

## Phase 4 — Robert live smoke (production)

> **Headline:** Register extraction showed partial promise. **The check/imaging leg (intelligent check linking from photographed pages) — the main reason for paid DI — failed in production** and must be treated as the gating issue for any “go-live complete” declaration.

**Executor:** Robert (owner). **Cursor did not** access the live URL.  
**Evidence:** 10 screenshots + 3 CSV exports from live runs (owner-held; **not** committed to git — client data).

**Mark as Received:** Per approved plan — use test request only or **skip** real write-back. **Outcome not reported** in smoke summary (assume flow presence only unless owner adds detail).

### Part A — Pre-smoke (reported)

- Sidebar / Bank Statements page showed DI pipeline **configured** (per screenshots — owner evidence).
- No persistent “Azure OCR is not configured” blocker before processing.

### PDF 1 — `HCC 2026-04.pdf` (Hernandez Custom Concrete)

| Metric | Result |
|--------|--------|
| Register / tabular (`prebuilt-bankStatement.us`) | **98 transactions** extracted |
| Check / imaging leg | **Failed** |
| Processing log (key lines) | `Check cropper skipped: opencv (cv2) not installed` |
| Azure check analyzer | Error: **"The page range exceeds the number of pages in the document."** |
| Categorization | Very large **Uncategorized** bucket (~**$119k** in one pivot view) |
| Payee rules | Improved **21** rows |
| vs spike/local | Does **not** match prior HCC spike quality |

### PDF 2 — `Auto_Body_Center_Jan_26_Statement.pdf` (Auto Body Center — hard Traditions)

| Metric | Result |
|--------|--------|
| Register pass | **Functional but inconsistent** across runs |
| Best run | **49** transactions (44 register + **5** from checks) |
| Other runs | **42** transactions; one run **37** (0 from checks) |
| Historical baseline (local v2.44.1 / spike) | ~**92** transactions · deposits **$41,786.80** · withdrawals **$41,403.63** · ~**56** crops |
| Check payee quality (when checks appeared) | **Poor** — Low confidence; wrong names (e.g. Hallmark Hyundai, HALLMARK NISSAN) |
| Payee rules | Helped **13–16** rows in some runs |
| Check / imaging leg | **Unreliable** — sometimes 5 checks, sometimes 0; cropper often skipped (OpenCV) |

### Phase 4 verdict

| Leg | Production state after 2026-05-29 session |
|-----|-------------------------------------------|
| **Register / tabular DI** | **Partial** — works at basic level; **not repeatable** on same PDF; counts well below local baseline on Auto Body |
| **Check / imaging DI** | **Failed** — **the primary paid-tier benefit is not delivered in production** |
| **Intelligent check linking** | **Not achieved** — this was the core promise of the two-leg design |
| **Daily driver / Laura pilot** | **Not ready** |

---

## Root causes — check/imaging leg failure (production)

### 1. OpenCV not installed on App Service

- Processing log: **`Check cropper skipped: opencv (cv2) not installed`**
- Geometric cropper v5 (`check_cropper_v5`) requires `cv2` — see `App/bank_statements.py` guard.
- **Root `requirements.txt`** deployed to Azure lacks `opencv-python-headless` (and related imaging deps). Local spike / Function App path includes them in `AzureFunctions/ocr_processor/requirements.txt` but production zip uses root `requirements.txt`.

### 2. Azure `prebuilt-check.us` page range error

- Error: **"The page range exceeds the number of pages in the document."**
- App Settings fix imaging to pages **5–9** (`SLAM_IMAGING_FIRST_PAGE` / `LAST_PAGE`). Likely causes to investigate:
  - HCC PDF has **fewer than 9 pages** — blind 5–9 range invalid for that document.
  - Full-page fallback path may pass invalid page indices to DI when cropper is skipped.
- Requires code fix: clamp imaging range to `min(last_page, document_page_count)` per PDF.

### 3. Contributing factors

| Factor | Notes |
|--------|-------|
| **Deploy zip 181 MB** | Full `Data/` bundled — contributed to deploy script client timeout; unrelated to cropper but ops risk |
| **Non-repeatable register results** | Same PDF → 37 / 42 / 49 rows — needs investigation (DI async, assembly logic, or UI state) |
| **Missing heavy deps on F1** | No `pdf2image` / `pillow` in root requirements — may affect other paths |
| **Uncategorized volume** | Large buckets remain; rules help partially (13–21 rows) |

---

## Post-execution hardening observations

| # | Observation | Priority |
|---|-------------|----------|
| 1 | Add **`opencv-python-headless`** (+ `pdf2image`, `pillow` as needed) to **root `requirements.txt`** and redeploy | **P0** — blocks cropper |
| 2 | **Clamp imaging page range** per PDF before `prebuilt-check.us` / full-page analyze | **P0** — blocks check analyzer on shorter PDFs |
| 3 | Fix **`Deploy-ToAzure.ps1`** poll: replace broken `az webapp deployment list` with `az webapp log deployment list` | P1 |
| 4 | Consider **code-only deploy zip** (exclude `Data/`) for routine pushes — 181 MB upload timeout | P1 |
| 5 | Add **DI reachability probe** to `Check-AppHealth.ps1` / `health_check.py` | P2 |
| 6 | Investigate **register pass inconsistency** (same PDF, different row counts) | P1 |
| 7 | Re-validate against spike baselines after P0 fixes on **both** smoke PDFs | P0 |
| 8 | Exercise **rollback test** (`-DisableDI` + optional redeploy) before pilot | P2 |
| 9 | **Mark as Received** controlled write-back test (test request only) | P2 |

### Risks of quick fix (P0 — especially OpenCV on F1)

Adding `opencv-python-headless` and related imaging packages to the **production** App Service is the obvious P0 fix, but it is not zero-risk on **F1**:

| Risk | Detail |
|------|--------|
| **Deploy size & cold start** | OpenCV + `pdf2image` + `pillow` add tens of MB to the install footprint. Combined with a 181 MB zip habit, deploy time and F1 cold-start latency can worsen (already saw ~30s+ HTTP timeouts post-deploy). |
| **Memory pressure on F1** | F1 has a **~1 GB RAM** ceiling. Cropping loads page images in-process; concurrent Streamlit users + DI API calls + OpenCV may cause OOM or intermittent 503s under load. |
| **Build time on Kudu** | `pip install` of OpenCV on Linux during deploy can be slow or fail on constrained hosts; may need Oryx/build tuning or pre-built wheels only. |
| **Partial fix illusion** | Installing OpenCV alone does not guarantee spike-level payee quality; Auto Body smoke already showed **poor check payees** even when 5 checks appeared. Page-range clamp + register consistency still required. |
| **DI cost without value** | S0 is live; failed or half-working check calls still consume pages. Until the leg works, every Process Statement may bill for register pages without delivering check linking. |
| **Scope creep** | “Quick” fix can expand to `easyocr`, `numpy`, poppler/`pdf2image` system deps — Function App already bundles these; App Service may need more than one requirements line. |

**Mitigation:** Test on a **code-only zip** deploy; consider **B1** if memory errors appear; re-smoke both PDFs with full Processing logs; keep `-DisableDI` rollback one command away.

---

## Rollback posture

**Instant settings rollback (no code change required for behavior revert):**

```powershell
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI
```

**SKU rollback (rare):**

```powershell
az cognitiveservices account update `
  --name slam-bank-statements `
  --resource-group SLAM-Services-RG `
  --sku F0
```

**Rollback test record:** Not performed in this session.

Grok Vision paste and lightweight parser remain available as fallbacks when DI is disabled.

---

## Final production state (live — update after each gate)

| Component | State |
|-----------|-------|
| DI SKU | **S0** |
| App Service tier | **B2** (upgraded **2026-05-29**, Cursor/`az`; Always On true; start limit 1800) |
| `AZURE_DI_*` on App Service | **Set** (Phase 2) |
| Latest code deploy | OneDeploy **`e74643bd`** **2026-05-30** (Oryx startup re-seed fix); prior **`c6b525f7`** 2026-05-29; P0 deploy **`bd23f330`** |
| Register DI on live URL | **TBD** — awaiting `Collect-GateA3Evidence.ps1` harvest |
| Check/imaging DI on live URL | **Infrastructure OK** (poppler verified 2026-05-30); **verdict PENDING** DI smoke evidence |
| Path | **Path A** (approved); B2 upgrade plan approved **2026-05-29** |
| Data layer (production) | **PostgreSQL** — `slam-services-db` (centralus, Ready); `USE_POSTGRES=true`; **98 clients / 36 requests** migrated |
| Go-live complete for daily driver? | **No** — Gate A3 `SMOKE_EVIDENCE` verdict pending (infrastructure criteria met) |

---

## Running log (session summary)

| Phase | Date | Action | Result |
|-------|------|--------|--------|
| 0 | 2026-05-29 | Pre-flight | F0, no `AZURE_DI_*`; doc gap documented |
| 1 | 2026-05-29 | S0 upgrade | Verified S0 |
| 2 | 2026-05-29 | Setter (real) | DI settings live |
| 3 | 2026-05-29 | Build + deploy | Zip 181 MB; Kudu OK; script timeout |
| 3d | 2026-05-29 | Health | Running; no DI probe |
| 4 | 2026-05-29 | Robert smoke | **Register partial; check leg failed** |
| A0 | 2026-05-29 | P0 code in repo | Imaging deps, apt.txt, page clamp, deploy scripts — **not deployed** |
| A1 | 2026-05-29 | B1→B2 + settings | **Done** — sku=B2, alwaysOn=true, `WEBSITES_CONTAINER_START_TIME_LIMIT=1800` |
| A2 | 2026-05-29 | Code-only deploy | **Done** — `bd23f330`, 2.45 MB zip; Kudu "Deployment successful"; HTTP 200 |
| A3 | 2026-05-29 | Robert re-smoke (live URL) | **Executed** — both PDFs processed; screenshots + CSV exports owner-held; evidence paste pending |
| A3b | 2026-05-29 | Cursor autonomous review | **Done** — diagnosis, poppler fix, assembly fix, owner execution package |
| A3c | 2026-05-30 | Full autonomous closure (SP) | **Infrastructure PASS** — app started, Postgres synced, deploy + poppler OK; DI smoke evidence pending ([`gate-a3-full-autonomous-closure-2026-05-30.md`](../handoffs/gate-a3-full-autonomous-closure-2026-05-30.md)) |
| 5–8 | — | Schema / pilot / rename / rollback test | Not completed or blocked |

---

## Handoff

This runbook + `docs/DI-Go-Live-Commands.md` + `docs/deployment.md` + `db/schema.sql` allow Patty or Robert to understand **what was actually done on 2026-05-29** and **where production stands**.

**Blueprint:** See v2.44.20 Change Log entry (corrects v2.44.19 planning text).

**Gate A3 autonomous work (2026-05-29–30):** Complete per handoffs in `docs/handoffs/gate-a3-*.md` — production CLI validation, DI totals root cause, poppler reliability fix, assembly hardening, Oryx startup re-seed, full autonomous closure session **2026-05-30** ([`gate-a3-full-autonomous-closure-2026-05-30.md`](../handoffs/gate-a3-full-autonomous-closure-2026-05-30.md)). **Infrastructure criteria met** (HTTP 200, poppler OK, Postgres OK). **Final Gate A3 verdict pending** — run `Collect-GateA3Evidence.ps1 -Both -UpdateDocs` after minimal browser smoke on the two canonical PDFs.

**Before Laura pilot:** Gate A3 verdict must confirm **check/imaging leg passes** on re-smoke evidence; then schedule pilot per `docs/DI-Go-Live-Commands.md` Step 6.

### Gate A3 — DI Totals Discrepancy Diagnosis (2026-05-29, Cursor implementer)

**Symptom (owner re-smoke):** Summary totals beneath the Processing log / register-only view looked correct; the banner metrics, `data_editor` table, and **Download transactions CSV** showed inflated withdrawal totals (all three matched each other).

**Root cause:** Two-leg assembly in `_run_azure_ocr_via_document_intelligence` (`App/bank_statements.py` ~2308–2340). After the register pass (`analyze_bank_statement_pdf`), the pipeline always concatenated “supplemental” check-image rows from `checks_to_transaction_rows`. Azure DI register output **does not populate `Check#`** on Traditions-style PDFs, so every imaging-leg row appeared “unmatched” and was appended—even though the register pass already included those withdrawals as generic debits. On production (geometry cropper active, ~50+ crops), this double-counted withdrawals and jacked up totals. Payee rules (`apply_payee_rules` → `Data/payee_rules.csv`) touch **Payee/Category only**—not amounts—confirmed not the corruption source.

**Call chain (wrong totals):** `app.py` `_run_bank_statement_azure_process` (L2419) → `run_azure_ocr_pipeline` → `_run_azure_ocr_via_document_intelligence` → register pass + cropper + check pass → `combined = register_txns + supplemental_check_txns` → `_parse_ocr_response_to_df` → `st.session_state["bank_stmt_txn_df"]` → `transaction_summary_metrics` / `data_editor` / Download CSV (L2167, L2302, L2317).

**Correct totals source:** Register-leg `register_txns` immediately after `analyze_bank_statement_pdf` (logged as `Register pass: N transaction(s)`). Deposits already matched gold on Auto Body ($41,786.80); supplemental append was corrupting withdrawals.

**Minimal fix (in repo, not deployed):**
1. **`App/bank_statements.py`:** Append supplemental check rows **only when** `len(register_txns) < 3` (sparse register). Otherwise register pass is authoritative for totals; imaging leg runs `_merge_azure_checks_into_transactions` for payee enrichment only. Normalize check numbers via `_normalize_check_number` when matching.
2. **`App/azure_document_intelligence.py`:** `analyze_checks_from_crop_directory` reads PNGs from `checks/` subfolder (cropper moves files out of root)—restores per-crop DI on production.

**Timing (~1 min/PDF):** Logged in Processing log as `Register pass: …` (includes `duration_sec` from Azure DI meta) and check-pass lines (`Check pass (document_intelligence_crops): …`); `log_event` keys `bank_stmt_azure_di_request` / `bank_stmt_azure_di_response` / `bank_stmt_azure_di_pipeline_done`.

**Rollback test:** Exercise `-DisableDI` once before the next owner smoke so the team has a verified fallback if the patched assembly misbehaves on an edge-case PDF.

**Deploy:** Patch requires code deploy to App Service; owner re-smoke both PDFs after deploy to confirm UI totals match register pass.

---


---

**GATE A3 AUTONOMOUS PHASE COMPLETE — OWNER ACTION REQUIRED**

All fixes (assembly double-counting + poppler reliability on App Service) are in the current source tree.

**Single handoff document:**
→ [`Gate-A3-Owner-Execution-Package-Final.md`](gate-a3/Gate-A3-Owner-Execution-Package-Final.md)

Copy the sequence in that file:
1. Deploy current source + run `Test-GateA3Poppler.ps1`
2. Confirm `IMAGING_LEG poppler=ok`
3. Re-smoke both PDFs (HCC 2026-04.pdf and Auto Body Jan 26)
4. Fill `Gate-A3-Final-Re-Smoke-Evidence-Guide.md`
5. Paste results back for final scorecard + verdict.

Everything else below this line is historical context or superseded.

---

**Gate A3 — Owner Re-Smoke Evidence (2026-05-29)**

Owner performed live re-smoke on both target PDFs and exported the following to `deploy-logs-temp/` as baselines:

**HCC 2026-04.pdf** (Hernandez Custom Concrete)
- Processing Log (owner-provided):
  - Register pass: **98 transaction(s)** from Azure DI (pages 1-4).
  - Check cropper skipped: poppler (pdftoppm) not on PATH.
  - Check pass: **0 check(s)** from imaging pages 5-7.
  - Combined: **98 register + 0 supplemental**.
  - Duration: 27.48s.
- Export CSV: `2026-05-29T20-11_export.csv` (98 rows, deposits $163,914, withdrawals $45,703.76, 0 Check#).
- Imaging leg completely disabled in this run due to missing poppler in the App Service container.

**Auto_Body_Center_Jan_26_Statement.pdf**
- Export CSV: `2026-05-29T20-08_export.csv` (49 rows, deposits $43,860.64, withdrawals $16,633.49, 2 unique Check#).
- Gold baseline (Grok Vision + hardened parser): 92 transactions, deposits $41,786.80, withdrawals $41,403.63, ~49-56 checks.
- This output shows the familiar lower transaction count and suppressed withdrawal total seen in prior incomplete DI runs.

**Additional context from owner**
- UI showed "Version v2.44 · Mode: postgresql" (APP_VERSION string + data mode, **not** the Kudu/Azure deploy ID. Real IDs are GUIDs such as c6b525f7...).
- Screenshots from the exact UI the owner saw during the re-smoke (including the "correct" vs "jacked" summary discrepancy) are also in `deploy-logs-temp/`.

**Critical deployment finding**: The production App Service container is missing `poppler` (pdftoppm). This hard-disables the geometric cropper v5 step. Consequently the entire paid-tier imaging leg (per-crop `prebuilt-check.us`) never executes on live, regardless of code. This is why HCC produced 0 crops/supplemental rows.

The two main export CSVs above are now the authoritative record of this re-smoke for scorecard purposes. The 49-row Auto Body output and the clean 98-row HCC register-only output can be directly compared to the historical gold baselines.

### Gate A3 — Poppler Reliability Task – Complete via Orchestrator (2026-05-29)

Dual-agent handoff executed: `docs/handoffs/gate-a3-make-poppler-reliable-app-service.md`

**Root cause confirmed**: Production `startup.sh` had an `AZURE_PROD=true` branch that skipped runtime `apt-get`, assuming Oryx + `apt.txt` would deliver `poppler-utils`. It did not. Result: cropper disabled on every container start → imaging leg never ran (directly observed in 2026-05-29 re-smoke: "Check cropper skipped: poppler (pdftoppm) not on PATH").

**Fix applied (via Cursor implementer)**:
- `startup.sh`: Removed the production skip. Probe now always attempts timed `apt-get install poppler-utils` (20s update + 45s install) with structured logging:
  - `IMAGING_LEG poppler=ok` → geometric cropper v5 + per-crop DI enabled.
  - `IMAGING_LEG poppler=missing` → register-only DI.
- `Deploy-ToAzure.ps1`: Added `Test-PopplerViaKudu` post-deploy probe (non-fatal).
- Runbook updated with verification steps and owner deployment note.

**Owner deploy + verify + re-smoke:** [`Gate-A3-Owner-Execution-Package-Final.md`](gate-a3/Gate-A3-Owner-Execution-Package-Final.md) (authoritative copy-paste sequence).

### Gate A3 — Path to Final Verdict (context; owner steps in execution package)

**Two blockers identified in the 2026-05-29 re-smoke — both fixed in current source, awaiting one owner deploy:**

| # | Blocker | Before (2026-05-29 evidence) | Fix (in repo) |
|---|---------|-------------------------------|---------------|
| 1 | **Poppler missing** — imaging leg never ran | HCC log: `Check cropper skipped: poppler (pdftoppm) not on PATH` → 98 register + 0 supplemental | `startup.sh`: always attempt timed `apt-get install poppler-utils` even in prod fast-path; emit `IMAGING_LEG poppler=ok` / `poppler=missing` |
| 2 | **Assembly double-counting** — jacked UI totals | Auto Body: banner/table/Download CSV showed inflated withdrawals; per-file register view correct. Traditions PDFs omit Check# on register pass → all check-leg rows appended as supplemental | `App/bank_statements.py`: supplemental check rows only when register sparse (`< 3` rows); payee merge-only otherwise |

**2026-05-29 before baseline (owner-held in `deploy-logs-temp/`):**
- **HCC 2026-04.pdf:** 98 register + 0 supplemental · cropper skipped · export 98 rows · withdrawals $45,703.76
- **Auto Body Jan 26:** 49 rows · deposits $43,860.64 · withdrawals $16,633.49 vs gold 92 txns / $41,786.80 / $41,403.63
- UI screenshots show correct numbers in some per-file views vs wrong banner + table + main Download CSV

#### Success criteria — next owner re-smoke

| PDF | Expect |
|-----|--------|
| **HCC 2026-04.pdf** | Cropper runs (no poppler skip) · check-pass on imaging pages · non-zero crops/supplemental where pages exist · no page-range error |
| **Auto Body Jan 26** | Row count and deposit/withdrawal totals **closer to gold** (92 / $41,786.80 / $41,403.63) · banner metrics = table = Download CSV (no jacked mismatch) |

Owner fills [`Gate-A3-Final-Re-Smoke-Evidence-Guide.md`](gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md) and pastes results (see execution package). Cursor completes [`Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`](gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md) → final verdict + Path A/B.

### Gate A3 Verdict (2026-05-30 — deploy `4fa54010`)

| PDF | Rows | Deposits | Withdrawals | Crops | Verdict |
|-----|------|----------|-------------|-------|---------|
| HCC 2026-04 | 98 (0 supp) | $163,914.00 | $45,703.76 | 42 | **PASS** — matches gold |
| Auto Body Jan 26 | 110 (44 reg + 66 supp) | $41,786.80 | $354,909.14 | 56 | **NEEDS MORE WORK** — row count OK; withdrawal totals inflated |

**Path recommendation:** **NEEDS MORE WORK** — tighten supplemental dedupe before Laura pilot. HCC ready for register+imaging payee merge; Auto Body check leg over-counts withdrawals when appending unmatched check rows.

**Fixes applied this session:** `Invoke-GateA3HeadlessSmoke.ps1` waits on fresh `gate-a3-smoke.log` (not stale docker logs); `Deploy-ToAzure.ps1` seeds `App/bank_statements.py` + `check_cropper_v5.py` post-Oryx; Kudu hotfix seeded totals-assembly code for re-smoke.

Scorecard: [`Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`](gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md)

---

## Data layer failure — post B2 deploy (2026-05-29, diagnosed) — RESOLVED

> **Resolved 2026-05-29:** `Invoke-DataLayerGoLive.ps1` completed P1–P5; production on PostgreSQL (`slam-services-db`, 98 clients / 36 requests). Retained for audit trail only.

**Symptom (historical):** After login, app showed **Critical: CSV files — not found** (or stopped before Bank Statements). Gate A3 re-smoke was **blocked**.

### Root cause (confirmed via App Service settings + code + subscription inventory)

| Finding | Detail |
|---------|--------|
| **Active data mode** | **CSV** — `USE_POSTGRES` is **not set** on `slam-services-revenue-tracker` (no `POSTGRES_*` / `DATABASE_URL` App Settings). |
| **Startup behavior** | `App/app.py` lines 285–294: when Postgres not requested, `resolve_data_path()` must find `Clients.csv` + `RevenueRequests.csv` or **`st.stop()`** — main app never loads. |
| **Why CSV missing on server** | Code-only deploy (`bd23f330`, 2.45 MB) **correctly omitted `Data/`** per policy. Earlier 181 MB deploys had bundled gitignored CSVs; that path is **retired**. |
| **PostgreSQL in Azure** | **No PostgreSQL Flexible Server** in subscription (`az postgres flexible-server list` → empty). Production was never switched to DB mode on this app. |
| **wwwroot clutter** | OneDeploy/Oryx uses **`CleanOutputPath False`** — old artifacts remain (`SLAM-Services-Project/`, `.kilo/`, etc.) from historic full-repo zips. Harmless for CSV path but confusing diagnostics; unrelated to missing CSVs. |
| **Bank Statements needs clients** | Page requires ≥1 row in `clients_df` (client selectbox) — empty DB/CSV still blocks smoke even if login worked. |

**Conclusion:** The app is non-functional for UAT because production still assumes **CSV-on-wwwroot**, but we intentionally stopped shipping client files to App Service. **PostgreSQL was planned (v2.30) but never provisioned or wired on this web app.**

---

**Gate A3 — Poppler Reliability Fix (duplicate section removed)**

> **Superseded:** Full poppler fix narrative is under **Handoff → Gate A3 — Poppler Reliability Task** above. Owner deploy/verify/re-smoke: [`Gate-A3-Owner-Execution-Package-Final.md`](gate-a3/Gate-A3-Owner-Execution-Package-Final.md).

### Recommended path forward (no client CSV on App Service) — DONE

**Primary (aligns with architecture):**

1. **Provision** Azure Database for PostgreSQL Flexible Server in `SLAM-Services-RG` (e.g. `slam-services-db`).
2. **From Robert’s laptop only** (gitignored `Data/Revenue_Tracker_Migration/` — never in deploy zip):
   - `python Scripts/init_db.py`
   - `python Scripts/migrate_to_postgres.py` (targets Azure DB via env / connection string)
3. **Configure App Service:** `.\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1` (+ password).
4. **Redeploy code-only** with cleanup: `.\Scripts\PowerShell\Deploy-ToAzure.ps1 -CleanDeploy -TimeoutSeconds 900`
5. Verify sidebar **Data Source Status → PostgreSQL connected** with client/request counts.
6. **Then** run Gate A3 re-smoke (Bank Statements + both PDFs).

**Not acceptable:** Uploading `Data/Revenue_Tracker_Migration/` to wwwroot or `-IncludeData` production deploys.

**Optional hardening (repo):** `data_paths.py` error text updated to point at Postgres migration, not Kudu CSV upload. `Deploy-ToAzure.ps1` adds **`-CleanDeploy`** (`az webapp deploy --clean true`) to remove stale wwwroot folders on code-only pushes.

| Gate | Status |
|------|--------|
| A1 B2 | Done |
| A2 P0 deploy | Done |
| **Data layer** | **Done** (2026-05-29) |
| A3 re-smoke | **Pending owner** — [`Gate-A3-Owner-Execution-Package-Final.md`](gate-a3/Gate-A3-Owner-Execution-Package-Final.md) |

---

## PostgreSQL provisioning package (Path A — data layer unblock) — DONE

> **Completed 2026-05-29** via `Invoke-DataLayerGoLive.ps1`. Retained as reference for rollback/re-provision.

**Policy:** Client CSVs stay on Robert’s laptop (`Data/Revenue_Tracker_Migration/`, gitignored). **Never** bundle `Data/` in App Service deploys. Data lives in **Azure PostgreSQL** only.

**End-to-end wrapper (preferred):** `Scripts/PowerShell/Invoke-DataLayerGoLive.ps1`  
**Granular script:** `Scripts/PowerShell/Provision-AzurePostgres.ps1` (P1 only)

### Phase P1 — Create server (Azure CLI)

Defaults: `slam-services-db` · `SLAM-Services-RG` · **`centralus`** (eastus may be subscription-restricted) · Burstable **`Standard_B1ms`** · 32 GiB · PostgreSQL **16** · admin **`slamadmin`** · DB **`slam_services`**.

```powershell
# Option A — one script (prompts for password)
.\Scripts\PowerShell\Provision-AzurePostgres.ps1

# Option B — raw commands (replace <PASSWORD> — never commit)
$RG="SLAM-Services-RG"; $SVR="slam-services-db"

az postgres flexible-server create `
  --resource-group $RG --name $SVR --location eastus `
  --admin-user slamadmin --admin-password "<PASSWORD>" `
  --sku-name Standard_B1ms --tier Burstable `
  --storage-size 32 --version 16 --yes

az postgres flexible-server db create -g $RG -s $SVR -d slam_services

# Azure services + laptop + App Service outbound IPs
az postgres flexible-server firewall-rule create -g $RG -s $SVR `
  -n AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0

$myIp = (Invoke-RestMethod https://api.ipify.org).Trim()
az postgres flexible-server firewall-rule create -g $RG -s $SVR `
  -n AllowLaptop --start-ip-address $myIp --end-ip-address $myIp

# FQDN for next steps:
az postgres flexible-server show -g $RG -n $SVR --query fullyQualifiedDomainName -o tsv
```

**SKU note:** `Standard_B2s` / GeneralPurpose is available if Burstable CPU is tight during DI + Streamlit; start with B1ms for cost.

### Phase P2 — Local migration (Robert’s laptop only)

Prereq: local CSVs exist under `Data/Revenue_Tracker_Migration/`. Add to **repo-root `.env`** (gitignored):

```ini
POSTGRES_HOST=slam-services-db.postgres.database.azure.com
POSTGRES_USER=slamadmin
POSTGRES_PASSWORD=<same as Azure admin>
POSTGRES_DB=slam_services
POSTGRES_SSLMODE=require
USE_POSTGRES=true
```

```powershell
cd C:\SLAM-Services-Project
.\.venv\Scripts\Activate.ps1   # or your venv

python Scripts/init_db.py
python Scripts/migrate_to_postgres.py --dry-run
python Scripts/migrate_to_postgres.py
python Scripts/health_check.py --verify-only
```

Expect ~99 clients / ~36 requests (or current local CSV counts). **No CSV files are copied to App Service.**

### Phase P3 — Wire App Service

```powershell
.\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 `
  -PostgresHost "slam-services-db.postgres.database.azure.com" `
  -PostgresUser "slamadmin" `
  -PostgresDb "slam_services"
# Password: secure prompt inside script
```

Verify settings names only (no secret values in logs):

```powershell
az webapp config appsettings list -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --query "[?starts_with(name, 'USE_POSTGRES') || starts_with(name, 'POSTGRES_')].name" -o tsv
```

### Phase P4 — Clean code redeploy + verify

```powershell
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1 -CleanDeploy -TimeoutSeconds 900
.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure
```

Live: https://slam-services-revenue-tracker.azurewebsites.net/ — sidebar **Data Source Status** must show **PostgreSQL** with non-zero clients/requests.

### Phase P5 — Gate A3 (owner only)

Robert: deploy + verify + re-smoke per [`Gate-A3-Owner-Execution-Package-Final.md`](gate-a3/Gate-A3-Owner-Execution-Package-Final.md); paste completed [`Gate-A3-Final-Re-Smoke-Evidence-Guide.md`](gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md).

### After data layer — status

| Step | Status |
|------|--------|
| P1–P5 Full data layer | **Done** (2026-05-29) |
| Gate A3 final deploy + re-smoke | **Infrastructure done (2026-05-30)** — DI smoke evidence **pending** ([`gate-a3-full-autonomous-closure-2026-05-30.md`](../handoffs/gate-a3-full-autonomous-closure-2026-05-30.md)) |
| Gate A3 scorecard + verdict | **Pending** — after `Collect-GateA3Evidence.ps1 -Both -UpdateDocs` |

### Rollback

```powershell
.\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 -DisablePostgres
# App returns to CSV mode — will fail again without server-side CSV (by design)
```

| Phase | Date | Result |
|-------|------|--------|
| P1 Provision | 2026-05-29 | **Done** |
| P2 Migrate | 2026-05-29 | **Done** |
| P3 App settings | 2026-05-29 | **Done** |
| P4 Redeploy | 2026-05-29 | **Done** |

---

## Path A execution record — B2 + deploy (2026-05-29)

**Executor:** Cursor (`az` CLI + deploy scripts). **Gate A3:** infrastructure PASS 2026-05-30; DI smoke evidence pending.

### A1 — B1→B2 infrastructure

| Item | Detail |
|------|--------|
| Plan | `SLAM-Services-Plan` in `SLAM-Services-RG` |
| Before | **B1** (Basic), East US |
| After | **B2** (Basic), `provisioningState: Succeeded` |
| Always On | Already **true** before upgrade; unchanged |
| App settings added | `WEBSITES_CONTAINER_START_TIME_LIMIT=1800` |
| App settings existing | `SCM_DO_BUILD_DURING_DEPLOYMENT=true` (Poppler / Oryx) |
| Restart | Issued after upgrade |

### A2 — Code-only deploy (P0 imaging)

| Item | Detail |
|------|--------|
| Deploy id | **`bd23f330-928e-4343-8dcb-f34ef39467e9`** |
| Received (UTC) | **2026-05-29T06:49:26Z** |
| Kudu outcome | **"Deployment successful"** (OneDeploy) |
| Zip size | **2.45 MB** (code-only; no `Data/`) |
| Zip build fix | Excluded **`Scripts/spike/`** (~184 MB) — first build was **176 MB** without exclusion |
| Deploy script | `Deploy-ToAzure.ps1 -TimeoutSeconds 900` — **client hung ~10 min** on `az webapp deploy` upload; server completed; manual `az webapp start` + verify |
| Post-deploy HTTP | **200** after ~90s cold start |
| Prior deploy (reference) | `e39d90f2` (2026-05-29 ~05:26 UTC, 181 MB zip, pre-P0) |

### Issues / lessons (ops)

1. **Never bundle `Scripts/spike/`** in production zip — use updated `Build-AzureDeployZip.ps1` (excludes `spike/`).
2. **`az webapp deploy` can block the shell** even with `--async true`; confirm via `az webapp log deployment list` before re-uploading.
3. **First Process Statement after deploy** may be slow (`startup.sh` pip install on container recycle).

**Production-ready for check leg?** **No** until Gate A3 `SMOKE_EVIDENCE` collected and verdict recorded (infrastructure verified 2026-05-30).

---

## Code changes in P0 deploy (2026-05-29)

**Status:** **Deployed** to production (deploy `e74643bd` 2026-05-30; prior `bd23f330`). **Check/imaging leg verdict:** infrastructure OK; DI smoke evidence pending Gate A3 collector.

| Change | Files |
|--------|--------|
| Imaging Python deps (no EasyOCR) | `requirements.txt` — `opencv-python-headless`, `pdf2image`, `pillow`, `numpy` |
| Poppler system package | `apt.txt` — `poppler-utils`; probed/fallback in `startup.sh` |
| Page-range clamp | `App/azure_document_intelligence.py` — skip imaging when `SLAM_IMAGING_FIRST_PAGE` exceeds PDF page count; clamp `last` to document length |
| Cropper dependency visibility | `App/bank_statements.py` — `geometry_imaging_deps_status()`, stricter `cropper_available()` (OpenCV + pdf2image + Poppler) |
| Deploy ergonomics | `Scripts/PowerShell/Deploy-ToAzure.ps1` — `az webapp log deployment list`; OneDeploy `complete` + `status ≠ 3` = success |
| Code-only zip default | `Scripts/PowerShell/Build-AzureDeployZip.ps1` — omits `Data/` by default; **excludes `Scripts/spike/`** (~184 MB); use `-IncludeData` only for bootstrap |

**Recommended deploy (after B2 upgrade):**

```powershell
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

Ensure App Service has `SCM_DO_BUILD_DURING_DEPLOYMENT=true` if `apt.txt` must run via Oryx (Poppler); startup.sh also attempts a best-effort `apt-get` when `pdftoppm` is missing.

**Remediation track:** **Path A selected** (owner approved 2026-05-29). Path B not active.

---

## Owner gates (hard stops — Cursor must not execute)

| Gate | Who | Trigger to proceed | Status |
|------|-----|-------------------|--------|
| **A1 — B1→B2 plan upgrade** | Cursor (`az`) | — | **Done** 2026-05-29 |
| **A3 — Live re-smoke** | Robert | Owner pastes re-smoke report (template below) | **Ready** — deploy live, awaiting smoke |

Everything else (runbook updates, zip build prep, code-only deploy after A1, checklists) — Cursor drives autonomously.

---

## B2 infrastructure upgrade (Path A) — condensed

**Goal:** `SLAM-Services-Plan` **B1 → B2**; enable Always On; extend container start time; Oryx build for `apt.txt` (Poppler).

**Do not run until Gate A1 approval.** Full working plan: approved B2 upgrade plan (session artifact); this block is the runbook SSOT.

```powershell
$RG = "SLAM-Services-RG"; $PLAN = "SLAM-Services-Plan"; $APP = "slam-services-revenue-tracker"

# Baseline (expect B1) — save output
az appservice plan show -g $RG -n $PLAN --query "{sku:sku.name,tier:sku.tier}" -o table

az appservice plan update -g $RG -n $PLAN --sku B2
az webapp config set -g $RG -n $APP --always-on true
az webapp config appsettings set -g $RG -n $APP `
  --settings WEBSITES_CONTAINER_START_TIME_LIMIT=1800 SCM_DO_BUILD_DURING_DEPLOYMENT=true

# Verify: sku=B2, alwaysOn=true — save output to running log
az appservice plan show -g $RG -n $PLAN --query "{sku:sku.name,tier:sku.tier}" -o table
az webapp config show -g $RG -n $APP --query alwaysOn -o tsv

az webapp restart -g $RG -n $APP
```

**Timing (recommendation):** Low-use window (~5–10 min user impact). **Order:** **B2 upgrade first**, then **code-only deploy** (heavy `pip`/Oryx on B2 + Always On). Deploy-before-B2 risks B1 OOM/timeouts during first imaging install.

**Rollback (plan):** `az appservice plan update -g $RG -n $PLAN --sku B1`

| Phase | Date | Owner | Result |
|-------|------|-------|--------|
| B2 upgrade | 2026-05-29 | Cursor (`az`) | B1→B2 succeeded; restart issued |
| Post-upgrade verify | 2026-05-29 | Cursor (`az`) | sku=B2, alwaysOn=true, start limit=1800 |

---

## After Gate A1 — Cursor autonomous plan (Gate A2)

**Trigger:** Owner reports A1 complete (B2 + Always On verified) — paste verify CLI output optional.

**Pre-deploy (local, no Azure SKU changes):**

1. Confirm repo has P0 imaging changes (`requirements.txt`, `apt.txt`, `startup.sh`, `App/azure_document_intelligence.py`, `App/bank_statements.py`, deploy scripts).
2. Optional quick sanity: `ruff check App/azure_document_intelligence.py App/bank_statements.py` (non-blocking if env lacks ruff).
3. Ensure `slam-app.zip` not committed; build fresh zip only.

**Deploy commands (exact):**

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
# Confirm zip size is modest (code-only; no Data/ unless bootstrap)
.\Scripts\PowerShell\Deploy-ToAzure.ps1 -TimeoutSeconds 900
```

**Post-deploy verification (Cursor):**

```powershell
az webapp log deployment list `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --query "[0].{id:id, status:status, active:active, message:message}" -o jsonc

az webapp show -g SLAM-Services-RG -n slam-services-revenue-tracker --query state -o tsv

.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure
```

HTTP head smoke on live URL (200 or expected redirect — not prolonged 503).

**Runbook updates after A2:** Running log row A2 (date, zip MB, deploy id, pass/fail); Final production state → latest deploy time; Gate A1 → **Done**; App Service tier → **B2**.

**Do not:** commit unless owner requests; run Gate A3 smoke; bump Blueprint/README.

Expect **15–30+ min** first heavy deploy on B2 (Oryx + OpenCV wheels).

---

## Gate A3 — Robert re-smoke checklist (production URL)

> **Superseded:** Owner handoff is [`docs/gate-a3/Gate-A3-Owner-Execution-Package-Final.md`](gate-a3/Gate-A3-Owner-Execution-Package-Final.md). Evidence: [`Gate-A3-Final-Re-Smoke-Evidence-Guide.md`](gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md). Scorecard: [`Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`](gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md).

**URL:** https://slam-services-revenue-tracker.azurewebsites.net/  
**PDFs (local, do not commit exports):** `Data/Auto_Body_Center_Jan_26_Statement.pdf`, `Data/HCC 2026-04.pdf`

(Old checklist table and instructions removed — use the new artifacts in `docs/gate-a3/` instead.)

### Gate A3 — Cursor analysis template (after owner report)

**Superseded by** `docs/gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`.

Use the modern scorecard after the human pastes results. The old inline template below has been removed in favor of the dedicated, maintained artifacts in `docs/gate-a3/`.

---

## Decision paths

### Path A — Quick remediation sprint (**ACTIVE**)

| Item | Detail |
|------|--------|
| **Goal** | Restore two-leg DI in production: cropper runs + `prebuilt-check.us` succeeds + acceptable payee quality on both smoke PDFs. |
| **Work** | (1) Add `opencv-python-headless`, `pdf2image`, `pillow`, `numpy` to root `requirements.txt` (match Function App baseline). (2) Code: clamp `SLAM_IMAGING_*` to document page count in `azure_document_intelligence.py` / `bank_statements.py`. (3) Optional: code-only deploy zip; fix `Deploy-ToAzure.ps1` poll command. (4) Redeploy; re-run Phase 4 smoke (both PDFs, full Processing logs). (5) Update runbook + Blueprint with re-smoke results. |
| **Effort (estimate)** | **~0.5–1.5 dev days** for deps + page clamp + deploy + smoke; **+0.5–2 days** if register inconsistency or payee quality need deeper fixes. |
| **Risks** | See **Risks of quick fix** above (F1 memory, deploy size, partial success). |
| **Re-smoke pass criteria** | Auto Body: repeatable row count near baseline (~92), reconciliation green or explained, **≥50 crops analyzed**, payees not garbage; HCC: check leg no page-range error, non-zero sensible check rows. |
| **Docs** | v2.44.20 stands; add v2.44.21 or amend runbook when re-smoke passes. |
| **Cost** | Keep S0; monitor DI pages during fix iterations. |

### Path B — Rollback + stabilize on register-only for now (not selected)

| Item | Detail |
|------|--------|
| **Goal** | Stop paying for / advertising a broken check leg; return team to known-safe workflows while planning a proper imaging fix (possibly B1 + full deps). |
| **Work** | (1) `Set-AzureBankStatementDIAppSettings.ps1 -DisableDI` (optional redeploy). (2) Communicate: **Grok Vision paste + lightweight parser + Local Enhanced (Robert)** remain; DI register-only was not reliable enough for daily driver. (3) Optionally downgrade DI to F0 if not actively testing. (4) Schedule imaging sprint later with B1 evaluation. |
| **Effort (estimate)** | **~15–30 minutes** for rollback + smoke that Bank Statements still loads; **no** check linking in production. |
| **Operational picture** | Bank Statements page shows “not configured” for DI; team uses established fallbacks. No false confidence from partial DI output. |
| **Risks** | Sunk S0 setup; team may expect DI to still be “on” if docs are unclear — **v2.44.20 + README must state check leg not delivered** even if settings remain (Path B removes settings). |
| **Docs** | v2.44.20 + README: infrastructure session documented; **check/imaging leg not in production**; pilot blocked. Runbook records rollback date when executed. |
| **When to revisit** | Dedicated sprint with F1/B1 sizing, full requirements parity with local spike, and Phase 4 smoke before any Laura pilot. |

---

*End of execution runbook — authoritative transcript for the 2026-05-29 Cursor-driven DI go-live session.*
