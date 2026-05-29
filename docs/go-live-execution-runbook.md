# Azure DI Bank Statement Go-Live — Execution Runbook (2026-05-29)

**Status**: **Partial cut-over only.** Register/tabular DI works at a basic level. **The check/imaging leg — the primary paid-tier benefit of this go-live — is not delivered in production.** Do not use the DI path for Laura daily driver until that leg is fixed or the team explicitly chooses register-only + rollback (see Path A / Path B at end of this document).  
**Session**: Cursor (primary agent) drove Phases 0–3 and documentation; Robert executed Phase 4 live smoke on production.  
**Live URL**: https://slam-services-revenue-tracker.azurewebsites.net/  
**Blueprint record**: v2.44.20 Change Log entry (draft for owner review) supersedes the anticipatory v2.44.19 narrative.

---

## Current execution state + next autonomous steps (2026-05-29, updated post data layer)

| Layer | State |
|-------|--------|
| Gate A1 (B2) | **Done** |
| Gate A2 (P0 imaging deploy) | **Done** — OpenCV, pdf2image, Poppler, page clamping, code-only deploys |
| **Data layer** | **DONE** — `Invoke-DataLayerGoLive.ps1` executed; `slam-services-db` (centralus); **98 clients / 36 requests** migrated; `USE_POSTGRES=true`; app healthy on B2 |
| **Gate A3 (re-smoke)** | **ONLY REMAINING HARD GATE** — Live Robert re-smoke on production with the two real PDFs. All P0 imaging fixes deployed. |

**See new dedicated artifacts:** `docs/gate-a3/` (Pre-Smoke Checklist + Evidence Template + Post-Smoke Scorecard Scaffolding + Launch Directive).

**Easiest launch command (from repo root):**
```powershell
.\Scripts\Launch-GateA3Orchestration.ps1
```

**Status note:** Data layer cut-over complete via `Invoke-DataLayerGoLive.ps1`. Production is now on PostgreSQL. The only remaining blocker for full imaging + register DI daily driver use is Gate A3 validation of the check/imaging leg after all P0 fixes.

### Gate A3 Preparation (Current Focus)

All supporting material lives in `docs/gate-a3/`:

- **Gate-A3-Orchestration-Launch-Directive.md** — Primary launch artifact for `grok -p` or Cursor.
- **Gate-A3-Pre-Smoke-Checklist-and-Evidence-Template.md** — What the human uses during the live smoke.
- **Gate-A3-Post-Smoke-Scorecard-Scaffolding.md** — Cursor completes this after results are pasted.
- Additional diagnostic and decision material as needed.

**Cursor standing order:** Keep these artifacts and this runbook in sync. The runbook is the single source of truth for status; the `gate-a3/` folder contains the detailed working templates.

### Owner minimum path (one command + one password + re-smoke)

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Invoke-DataLayerGoLive.ps1
```

1. Enter the **PostgreSQL admin password once** when prompted (provision + migrate + App Service settings).
2. Wait for P1–P5 to finish (~15–45 min; first Postgres create can take several minutes).
3. **You only:** Gate A3 re-smoke on the live URL (both PDFs); paste the report template at the bottom of this runbook.

Dry-run (no Azure changes): `.\Scripts\PowerShell\Invoke-DataLayerGoLive.ps1 -WhatIf`

**Owner signal for Cursor to execute P1–P5 on your machine:** `provision Postgres now` (Cursor runs the same script; you enter the password at the prompt).

### Execution log (data layer — live)

| Time (UTC/local) | Phase | Result |
|------------------|-------|--------|
| 2026-05-29 | P0 preflight | **PASS** — `az` session `robert@NextMoveSolutions.onmicrosoft.com`; CSVs + `.venv` OK |
| 2026-05-29 | P1 provision | **PASS** — `slam-services-db` in **centralus** (eastus restricted on subscription); provider `Microsoft.DBforPostgreSQL` registered; firewall: laptop IP + AllowAzureServices + App Service outbound IPs |
| 2026-05-29 | P2 migrate | **PASS** — `init_db` + migrate; **98 clients, 36 requests** in `slam_services` (local `health_check --verify-only`) |
| 2026-05-29 | P3 app settings | **PASS** — `USE_POSTGRES=true`, `POSTGRES_HOST`, `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_SSLMODE`, `POSTGRES_PASSWORD` (portal only) |
| 2026-05-29 | P4 deploy | **PASS** — code-only `slam-app.zip` clean deploy; Kudu `complete=true` |
| 2026-05-29 | P5 health | **PASS** — App Service **Running**; local PG counts match migration |
| 2026-05-29 | Gate A3 | **PENDING** — owner re-smoke (see template at end of runbook) |

**Notes:** Admin password is in repo-root `.env` (gitignored) only. If laptop cannot reach TCP/5432, use `Scripts/PowerShell/Invoke-PostgresMigrateViaAci.ps1` (blob + one-shot ACI). Removed `AllowAllTemp` firewall rule after migration.

### Cursor — ready now (no owner signal required)

| Action | Status |
|--------|--------|
| `Invoke-DataLayerGoLive.ps1` orchestrator | **Done** (P1–P5) |
| `Invoke-PostgresMigrateViaAci.ps1` | **Added** — fallback when outbound :5432 blocked |
| Local preflight | **Done** (see execution log) |
| Runbook SSOT update + Gate A3 artifacts | `docs/gate-a3/` integrated (checklist, template, scorecard, launch directive) |
| Blueprint/README `apply docs` | **Deferred** until Gate A3 PASS |

### Cursor — after owner says `provision Postgres now`

1. Run `Invoke-DataLayerGoLive.ps1` (or `-SkipProvision` if server already exists).
2. Log verification: App Settings key names only; deploy id from `az webapp log deployment list`; HTTP 200.
3. Update runbook running log (P1–P4 dates/results); Final production state → PostgreSQL.
4. Prepare Gate A3 artifacts in `docs/gate-a3/` (checklist, evidence template, scorecard scaffolding) and link them from this runbook.

### Cursor — after owner pastes Gate A3 re-smoke report

1. Use the artifacts in `docs/gate-a3/`:
   - Pre-Smoke Checklist + Evidence Template (human fills during smoke)
   - Post-Smoke Scorecard Scaffolding (Cursor completes after results pasted)
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
| Latest code deploy | OneDeploy **bd23f330** **2026-05-29** (~06:49 UTC); **P0 imaging code deployed** (2.45 MB code-only zip) |
| Register DI on live URL | **Partial / inconsistent** |
| Check/imaging DI on live URL | **Deployed — awaiting Gate A3 re-smoke** (P0 deps + page clamp on B2) |
| Path | **Path A** (approved); B2 upgrade plan approved **2026-05-29** |
| Data layer (production) | **CSV mode, no files on server** — **blocked**; Postgres not provisioned |
| Go-live complete for daily driver? | **No** — data layer + Gate A3 re-smoke |

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
| A3 | — | Robert re-smoke (live URL) | **Ready** — owner runs smoke; paste report template |
| 5–8 | — | Schema / pilot / rename / rollback test | Not completed or blocked |

---

## Handoff

This runbook + `docs/DI-Go-Live-Commands.md` + `docs/deployment.md` + `db/schema.sql` allow Patty or Robert to understand **what was actually done on 2026-05-29** and **where production stands**.

**Blueprint:** See v2.44.20 Change Log entry (corrects v2.44.19 planning text).

**Before Laura pilot:** Resolve P0 blockers (OpenCV on App Service, page-range clamping), re-run Phase 4 smoke until **check/imaging leg passes**, then schedule pilot per `docs/DI-Go-Live-Commands.md` Step 6.

---

## Data layer failure — post B2 deploy (2026-05-29, diagnosed)

**Symptom:** After login, app shows **Critical: CSV files — not found** (or stops before Bank Statements). Gate A3 re-smoke **blocked**.

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

### Recommended path forward (no client CSV on App Service)

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

### Gate status impact

| Gate | Status |
|------|--------|
| A1 B2 | Done |
| A2 P0 deploy | Done (imaging code live) |
| **Data layer** | **BLOCKED** — Postgres package ready (below) |
| A3 re-smoke | Waiting on data layer |

---

## PostgreSQL provisioning package (Path A — data layer unblock)

**Policy:** Client CSVs stay on Robert’s laptop (`Data/Revenue_Tracker_Migration/`, gitignored). **Never** bundle `Data/` in App Service deploys. Data lives in **Azure PostgreSQL** only.

**End-to-end wrapper (preferred):** `Scripts/PowerShell/Invoke-DataLayerGoLive.ps1`  
**Granular script:** `Scripts/PowerShell/Provision-AzurePostgres.ps1` (P1 only)  
**Owner trigger for Cursor to run P1-P5:** say **`provision Postgres now`**

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

Robert re-smoke both PDFs; paste report per **Gate A3 — owner report template** below.

### After data layer — Cursor autonomous steps

| Step | Owner | Cursor |
|------|-------|--------|
| P1–P5 Full data layer | Run `Invoke-DataLayerGoLive.ps1` **or** say `provision Postgres now` | Same script when triggered; password at your prompt only |
| P2 only (server exists) | `Invoke-DataLayerGoLive.ps1 -SkipProvision` | — |
| Gate A3 Re-smoke | Browser + PDFs | Analyze pasted report only |

### Rollback

```powershell
.\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 -DisablePostgres
# App returns to CSV mode — will fail again without server-side CSV (by design)
```

| Phase | Date | Result |
|-------|------|--------|
| P1 Provision | — | Pending |
| P2 Migrate | — | Pending |
| P3 App settings | — | Pending |
| P4 Redeploy | — | Pending |

---

## Path A execution record — B2 + deploy (2026-05-29)

**Executor:** Cursor (`az` CLI + deploy scripts). **Gate A3:** pending owner re-smoke.

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

**Production-ready for check leg?** **No** until Gate A3 re-smoke passes (see criteria below).

---

## Code changes in P0 deploy (2026-05-29)

**Status:** **Deployed** to production (deploy `bd23f330`). **Check/imaging leg verdict:** pending Gate A3.

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

> **Superseded:** The detailed modern checklists, evidence templates, and post-smoke scorecards now live in `docs/gate-a3/`.
> Use `.\Scripts\Launch-GateA3Orchestration.ps1` to generate the current versions.
> The content below is retained only for historical reference from the original Phase 4 smoke.

**Current recommended material:** See `docs/gate-a3/Gate-A3-Pre-Smoke-Checklist-and-Evidence-Template.md` and the Post-Smoke Scorecard Scaffolding.

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
