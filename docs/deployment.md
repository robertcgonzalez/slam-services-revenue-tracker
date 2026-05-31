# Azure Deployment Guide

**Purpose**: All paths for deploying the SLAM Services Revenue Tracker (Streamlit app) to the production Azure App Service (`slam-services-revenue-tracker`).

**Single Source of Truth reference**: See the latest `SLAM Services - Digital Transformation Blueprint.md` Change Log for context on why each path exists.

---

## Prerequisites (common to all paths)

- Azure CLI logged in (`az login`) **or** use of the dedicated dual-agent Service Principal (see [docs/security/dual-agent-azure-credentials.md](security/dual-agent-azure-credentials.md) for setup).
- Appropriate RBAC on the `SLAM-Services-RG` resource group (or via the `dual-agent-slam-services` Service Principal).
- The deployment package must contain at root: `requirements.txt`, `runtime.txt`, `startup.sh`, `App/`, `Scripts/`
- `Data/` is **never** included in code deploys (gitignored + intentionally preserved on the server via `clean: false`)

---

## Recommended Path: Modern Polling-Safe Deploy (`Deploy-ToAzure.ps1`)

This is the current production path (v2.38.3+). It avoids the ~230s load-balancer timeout that kills long-lived `config-zip` and synchronous `webapp deploy` calls on the F1 tier.

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1
# Mandatory after every code deploy (see "Post-deploy Gate A3 smoke gate" below):
.\Scripts\PowerShell\Invoke-GateA3HeadlessSmoke.ps1 -WaitMinutes 35
.\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both
```

Optional: run headless smoke in the same session as deploy (default off for safety; adds ~35 minutes):

```powershell
.\Scripts\PowerShell\Deploy-ToAzure.ps1 -RunGateA3Smoke
```

What it does (idempotent & safe):

1. Pre-flight checks (login, web app exists, zip root entries in local `slam-app.zip`).
2. Sets **`COMPRESS_DESTINATION_DIR=false`** (Python Oryx may still compress — see below).
3. Removes `WEBSITE_RUN_FROM_PACKAGE` if present (silent killer of OneDeploy uploads).
4. Restarts Kudu (scm) so Oryx sees updated app settings.
5. **`-CleanDeploy`**: removes stale `output.tar.zst` / `oryx-manifest.toml` on wwwroot (preserves `Data/`).
6. **`az webapp stop`** — releases Kudu and clears any stuck deploy lock.
7. **`az webapp deploy --type zip --async true --track-status false`** — CLI returns after upload; script polls Kudu deployment status separately (`-CleanDeploy` adds `--clean true`).
8. **Guarantee step** — retries until `startup.sh`, `runtime.txt`, and `apt.txt` exist and `startup.sh` is executable: VFS seed from repo + extract from `output.tar.zst` when Oryx compressed the build. **Deploy fails (exit 1) if this step does not succeed.**
9. **`az webapp start`** + HTTP smoke test (detects the Oryx “Hey, Python developers!” placeholder page).

Zip root layout (enforced by the build script):
```
requirements.txt
runtime.txt
startup.sh
apt.txt
pyproject.toml
App/
Scripts/
```

### Why root files disappear after a “successful” deploy (May 2026 root cause)

With `SCM_DO_BUILD_DURING_DEPLOYMENT=true`, **Python Oryx often compresses the entire build** into `output.tar.zst` at wwwroot and writes `oryx-manifest.toml` with `CompressDestinationDir="true"`.

`COMPRESS_DESTINATION_DIR=false` is set by `Deploy-ToAzure.ps1`, but **Oryx documents that setting for Node.js**; on Python 3.10 it is frequently **ignored**, so Kudu `ls /home/site/wwwroot` shows only `output.tar.zst`, `requirements.txt`, and `oryx-manifest.toml` — **not** `startup.sh`, `runtime.txt`, or `apt.txt` at the root. The platform then serves the default **“Hey, Python developers!”** placeholder because there is no executable `startup.sh` at wwwroot.

The three files **are inside** `output.tar.zst` (paths `./startup.sh`, `./runtime.txt`, `./apt.txt`). The deploy script now **always** guarantees they land at wwwroot after Oryx finishes (VFS upload from the repo + selective `tar` extract from the zst archive).

Manual verification:

```powershell
.\Scripts\PowerShell\Verify-AzureWwwRoot.ps1
```

Kudu evidence (healthy wwwroot root):

```bash
ls -la /home/site/wwwroot/startup.sh /home/site/wwwroot/runtime.txt /home/site/wwwroot/apt.txt
```

### Manual recovery (if wwwroot root files are missing)

Run from the repo (app can stay running; idempotent):

```powershell
.\Scripts\PowerShell\Deploy-ToAzure.ps1 -SkipDeploy -SkipSmokeTest
# Re-seeds/extracts wwwroot startup files without uploading a new zip.
```

Or extract from the Oryx archive in Kudu (one command per line in the debug console):

```bash
cd /home/site/wwwroot
zstd -d -f output.tar.zst -o /tmp/oryx-flat.tar
tar -xf /tmp/oryx-flat.tar ./startup.sh ./runtime.txt ./apt.txt
chmod +x startup.sh
ls -la startup.sh runtime.txt apt.txt
az webapp restart -g SLAM-Services-RG -n slam-services-revenue-tracker
```

### Build zip hygiene (reduces Oryx tarball size)

`Build-AzureDeployZip.ps1` excludes `__pycache__`, `Scripts/spike/`, test PDFs under `Scripts/_streamlit_bank_uploads/`, and uses forward-slash zip entries (not `Compress-Archive`). A typical code-only zip is ~0.25 MB instead of multi‑MB with accidental local artifacts.

---

## Manual One-Shot (full control)

Use when you need to debug or run steps individually.

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Build-AzureDeployZip.ps1

az webapp stop -g SLAM-Services-RG -n slam-services-revenue-tracker

az webapp config appsettings delete `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --setting-names WEBSITE_RUN_FROM_PACKAGE

az webapp deploy `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --src-path slam-app.zip --type zip --async true

az webapp deployment list `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --query "[0].{status:status,message:message,complete:complete}" -o table

az webapp start -g SLAM-Services-RG -n slam-services-revenue-tracker
```

> **Never use the legacy** `az webapp deployment source config-zip` — it prints a deprecation warning and uses the synchronous endpoint vulnerable to the 230s timeout.

---

## GitHub Actions (code-only deploys)

Push to `main`. The active workflow is `.github/workflows/deploy-azure.yml`.

- Uses `clean: false` so existing `Data/` on the App Service is preserved.
- Requires the `AZUREAPPSERVICEPUBLISHPROFILE` secret (full publish profile XML from the Azure Portal).
- Runs lint/setup + builds a flat package + deploys + post-deploy smoke check.

A legacy workflow (`main_slam-services-revenue-tracker.yml`) may still exist from the initial Azure Web App quickstart — the `deploy-azure.yml` is the maintained one.

---

## Data-Only Upload (Kudu)

When you only need to push new CSV data or `payee_rules.csv` (never code):

1. Open **Advanced Tools → Kudu → Debug console** (or use `az webapp deployment` with a tiny zip containing only the files you want).
2. Upload to `/home/site/wwwroot/Data/Revenue_Tracker_Migration/` (or the path configured via `SLAM_DATA_PATH`).

`Data/` is gitignored everywhere and must never enter a code deployment package.

---

## Recovery: When a Deploy Hangs or Returns `RemoteDisconnected`

**Symptoms**:
- `az webapp deploy` hangs at *"Warming up Kudu before deployment"*
- Error: `('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`
- Live site shows `Connection timed out`

**Root cause (typical on F1)**: The CLI's long-lived HTTPS polling connection is killed by the App Service front-end LB at ~230s idle, while the OneDeploy job is still running on the server. A stale deploy lock often remains.

### Safe recovery sequence (run in order — each step is idempotent)

```powershell
# 1. Stop the app (releases Kudu, kills any in-flight handler)
az webapp stop -g SLAM-Services-RG -n slam-services-revenue-tracker

# 2. Remove the silent killer of zip deploys
az webapp config appsettings delete `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --setting-names WEBSITE_RUN_FROM_PACKAGE

# 3. Confirm no deployment is currently in-flight
az webapp deployment list `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --query "[0].{status:status,complete:complete,message:message}" -o table
```

If step 3 still shows `complete: false` after 5+ minutes:

```powershell
# 4. (Rare) Force-restart Kudu specifically
az resource invoke-action `
  --resource-group SLAM-Services-RG `
  --name "slam-services-revenue-tracker/scm" `
  --resource-type Microsoft.Web/sites/host `
  --action restart --api-version 2022-03-01
```

Then re-run the modern deploy:

```powershell
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

---

## Optional / Important App Settings

| Setting                    | Purpose |
|---------------------------|---------|
| `SLAM_APP_PASSWORD`       | Production login (required) |
| `SLAM_APP_USER`           | Audit actor shown in UI / written to Postgres (e.g. `Laura`, `Stef`) |
| `SLAM_DATA_PATH`          | Override CSV folder (default: `Data/Revenue_Tracker_Migration`) |
| `USE_POSTGRES`            | `true` when Azure PostgreSQL is active |
| `DATABASE_URL` or `POSTGRES_*` | PostgreSQL connection (never commit) |
| `POSTGRES_SSLMODE`        | Usually `require` for `*.postgres.database.azure.com` |
| `COMPRESS_DESTINATION_DIR` | Must be `false` for flat wwwroot startup files (set automatically by `Deploy-ToAzure.ps1`) |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` — Oryx installs Python deps and processes `apt.txt` (Poppler) at deploy time |
| `SLAM_RUN_GATE_A3_SMOKE` | Optional: `true`/`1`/`yes` runs headless Gate A3 DI smoke in background at container start (requires canonical PDFs in `wwwroot/tmp/`; logs → `wwwroot/tmp/gate-a3-smoke.log`). See `startup.sh`. |

See `Scripts/PowerShell/Set-AzurePostgresAppSettings.ps1` for a helper that configures the Postgres-related settings.

---

## Post-deploy Gate A3 smoke gate (mandatory)

After **every** `Deploy-ToAzure.ps1` (or equivalent zip deploy to production), run the headless Bank Statements regression on the two canonical PDFs. This verifies DI, imaging leg, payee rules, and `SMOKE_EVIDENCE` on the live App Service — not just HTTP reachability.

**Prerequisites**: `Data\HCC 2026-04.pdf` and `Data\Auto_Body_Center_Jan_26_Statement.pdf` present locally; Azure CLI logged in; allow **~35 minutes** (upload + app restart + DI processing).

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Invoke-GateA3HeadlessSmoke.ps1 -WaitMinutes 35
.\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both
```

- `Invoke-GateA3HeadlessSmoke.ps1` — Kudu upload to `wwwroot/tmp/`, enables `SLAM_RUN_GATE_A3_SMOKE`, restarts app, polls `gate-a3-smoke.log` for fresh DONE markers.
- `Collect-GateA3Evidence.ps1 -Both` — harvests `SMOKE_EVIDENCE` from Kudu logs; **exits non-zero** if either canonical key is missing. Add `-UpdateDocs` when refreshing scorecard artifacts under `docs/gate-a3/`.

**Do not** treat a deploy as complete until both scripts exit 0. GitHub Actions deploys must run the same pair (or an equivalent documented step) before declaring production healthy.

**Combined with deploy** (opt-in switch, default off):

```powershell
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1 -RunGateA3Smoke
```

---

## Health & Smoke Checks After Deploy

```powershell
# Full pre-UAT / post-deploy validation (includes Azure reachability)
.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure

# Or the Python health probe (works locally or via Kudu SSH)
python Scripts/health_check.py --full
```

Live URL: https://slam-services-revenue-tracker.azurewebsites.net/

---

## Managing the Azure Startup Command (Critical for Streamlit Apps)

**Production must use:** `appCommandLine` = **`./startup.sh`**. If it is empty while `output.tar.zst` exists, visitors see the **“Hey, Python developers!”** placeholder (Streamlit never starts).

```powershell
.\Scripts\PowerShell\Set-AzureStartupCommand.ps1
```

`Deploy-ToAzure.ps1` applies this after each deploy. A raw `streamlit run ...` startup command bypasses `startup.sh` and often causes 503 on cold start — do not use that.

### Login flow (two steps)

1. **Microsoft sign-in** (Easy Auth on the App Service) — work/school account in the allowed tenant.
2. **SLAM app password** (Streamlit “Enter Password” screen) — value from the `SLAM_APP_PASSWORD` App Setting (ask Robert if you do not have it).

Hard-refresh (Ctrl+F5) or an incognito window if you still see the Python placeholder after a fix.

### Recovering from startup command drift

**Canonical production value:** `appCommandLine` = **`./startup.sh`**. `Deploy-ToAzure.ps1` enforces this after each deploy (via `Set-AzureStartupCommand.ps1` when needed).

| Symptom | Likely cause | Recovery |
| --- | --- | --- |
| **503 Application Error** on cold start | Raw `streamlit run ...` override bypasses `startup.sh` | Clear the bad override, then set `./startup.sh` (see below) |
| **"Hey, Python developers!"** placeholder | Empty `appCommandLine` while Oryx compressed build (`output.tar.zst`) exists | Set `./startup.sh` directly — do **not** leave empty |

#### One-command recovery (preferred)

**503 / raw streamlit override** — clear the override, then apply the canonical command:

```powershell
.\Scripts\PowerShell\Clear-AzureStartupCommand.ps1
.\Scripts\PowerShell\Set-AzureStartupCommand.ps1
```

**Python placeholder page** — skip clear; set the startup command:

```powershell
.\Scripts\PowerShell\Set-AzureStartupCommand.ps1
```

Or redeploy (sets `./startup.sh` automatically after wwwroot guarantee):

```powershell
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

`Clear-AzureStartupCommand.ps1` is **only** for removing a blocking raw `streamlit run ...` override. Leaving `appCommandLine` empty after clear often reproduces the placeholder when Oryx has compressed the build.

#### Verify after recovery

```powershell
az webapp config show -g SLAM-Services-RG -n slam-services-revenue-tracker --query "appCommandLine"
# Expected: ./startup.sh

.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure
python Scripts/health_check.py --full
```

### Prevention & Future Runs
- Do **not** set a raw `streamlit run ...` startup command in the Azure portal — it bypasses `startup.sh` and often causes 503 on cold start.
- After any deploy that touches `startup.sh`, run `Deploy-ToAzure.ps1` (or confirm `appCommandLine` is `./startup.sh`) and smoke-test the live URL.
- `startup.sh` skips pip when Oryx antenv already has packages and uses a faster production path when `WEBSITE_HOSTNAME` is set.
- See `docs/handoffs/azure-startup-fix-phase*.md` for the incident timeline and dual-agent handoff pattern.

---

## Related Scripts

- `Scripts/PowerShell/Build-AzureDeployZip.ps1` — produces the flat `slam-app.zip`
- `Scripts/PowerShell/Deploy-ToAzure.ps1` — the modern safe deploy orchestrator (`-RunGateA3Smoke` optional post-deploy Gate A3 regression)
- `Scripts/PowerShell/Invoke-GateA3HeadlessSmoke.ps1` — mandatory post-deploy DI smoke (canonical PDFs)
- `Scripts/PowerShell/Collect-GateA3Evidence.ps1` — harvest `SMOKE_EVIDENCE` after smoke (`-Both` required)
- `Scripts/PowerShell/Verify-AzureWwwRoot.ps1` — post-deploy Kudu check for root startup files
- `Scripts/PowerShell/Set-AzureStartupCommand.ps1` — set `appCommandLine` to `./startup.sh` (canonical production value)
- `Scripts/PowerShell/Clear-AzureStartupCommand.ps1` — remove a blocking raw `streamlit run ...` override only (then run Set-AzureStartupCommand or redeploy)
- `Scripts/PowerShell/Deploy-PostgresProduction.ps1` — wrapper that calls the above + Postgres settings
- `Scripts/PowerShell/Sync-DataRefresh.ps1` — push local CSV changes into the live Postgres instance

---

**Last major update to this guide**: 2026-05-31 — mandatory post-deploy Gate A3 smoke gate (`Invoke-GateA3HeadlessSmoke.ps1` + `Collect-GateA3Evidence.ps1 -Both`); `Deploy-ToAzure.ps1 -RunGateA3Smoke`. Earlier history in Blueprint Change Log.

---

## Production Bank Statement DI Go-Live (Azure Document Intelligence)

**Owner-approved baseline (2026 review)**:
- Primary engine: two-leg Document Intelligence (`prebuilt-bankStatement.us` for register pages + geometric cropper v5 + `prebuilt-check.us` per imaging-page crop).
- Check leg starts on `prebuilt-check.us` (evaluate Content Understanding or custom model later).
- App Service tier: remain on F1 for initial pilot; upgrade to B1 only if real usage demonstrates CPU/latency caps.
- DI resource (`slam-bank-statements`): upgrade from F0 to S0 **before** Laura pilot exposure.
- Rollout: full team (any client Laura, Patty, Stef, or Robert wants to process) — no artificial pilot scoping.
- UI language: present the DI path as the current production capability (adjust away from permanent "Phase 1" framing while preserving the Grok Vision safe fallback).

### Prerequisites
- Azure CLI logged in with RBAC on `SLAM-Services-RG`.
- `slam-bank-statements` resource upgraded to S0 (or accept F0 limits only for a very short internal validation window).
- Latest code deployed (the `azure-ai-documentintelligence` package is already in `requirements.txt`).

### One-Command Production Enablement
```powershell
cd C:\slam-services-project
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1
```

The script:
- Pulls the live endpoint + key from the `slam-bank-statements` cognitive services resource.
- Sets `AZURE_DI_ENDPOINT`, `AZURE_DI_KEY`, `AZURE_DI_MODEL=prebuilt-bankStatement.us`, `AZURE_DI_CHECK_MODEL=prebuilt-check.us`, imaging page tunables, and backward-compat `AZURE_OCR_FUNCTION_*` aliases.
- Supports `-DisableDI` for instant rollback (no code change, no redeploy required).
- Supports `-WhatIf` for safe dry-run.

After running the setter:
1. Redeploy (`Deploy-ToAzure.ps1` or GitHub Action).
2. `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` (enhanced version reports DI status).
3. Robert validates with real PDFs from `Data/`.
4. Schedule the full-team pilot session.

### Rollback (one command)
```powershell
.\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI
```
The Bank Statements page immediately falls back to the lightweight parser + Grok Vision paste paths. Zero data impact.

### Cost & Monitoring
- DI usage is pay-per-page (prebuilt models). The page pre-filter in `App/azure_di_utils.py` skips blank/reconciliation/summary pages before any paid call.
- Monitor in the Azure Portal under the `slam-bank-statements` resource → Metrics (calls, pages analyzed, errors).
- Set budget alerts on the subscription for the first 30 days.
- Expected cost at current volume: low single-digit dollars per month after S0 upgrade.

### Health & Verification After Go-Live
Use the enhanced health checks (see "Health & Smoke Checks" above plus the DI-specific probes added in the go-live pass). Always run a full regression on at least two hard scanned statements (e.g., `Auto_Body_Center_Jan_26_Statement.pdf`) before declaring the path ready for Laura's daily driver.

### Related Artifacts
- **Execution transcript**: `docs/go-live-execution-runbook.md` (2026-05-29 session — partial go-live; check-leg blockers documented)
- Setter: `Scripts/PowerShell/Set-AzureBankStatementDIAppSettings.ps1`
- Local equivalent (for Robert): `Scripts/PowerShell/Set-LocalAzureBankStatementEnv.ps1`
- Implementation: `App/app.py` (Bank Statements page), `App/bank_statements.py`, `App/azure_document_intelligence.py`, `App/azure_di_utils.py`, `App/check_cropper_v5.py`
- Schema (current production tables that Bank Statements writes to): `db/schema.sql`
- Full decision record: Blueprint Change Log entry for the 2026 DI go-live.

---

## Production Postgres Schema Reference

The live Azure PostgreSQL instance (when `USE_POSTGRES=true`) contains only the tables defined in `db/schema.sql`.

**Current implemented tables (production as of 2026 DI go-live)**:
- `clients`
- `revenue_requests` (the `bank_statement_received` and `sales_report_received` booleans are written directly by the Bank Statements page after successful DI processing or Grok Vision paste)

**Canonical definition**: `db/schema.sql` (heavily commented, matches `App/db_utils.py` SQLAlchemy models exactly).

**Local repro**: `python Scripts/init_db.py` (or `psql $DATABASE_URL -f db/schema.sql`).

**Verification**: The enhanced `Check-AppHealth.ps1 -Full` and `health_check.py --full` now include schema connectivity and basic drift awareness.

**Future entities** (Documents, Transactions, BankReconciliations, Payroll, Tax Filings, etc.) remain aspirational in `docs/data-model.md` until they are implemented and promoted into `db/schema.sql`.

Never assume a table exists in production unless it is listed in `db/schema.sql`.

**Last schema baseline update**: Captured as part of the 2026 Azure DI Bank Statement go-live + schema robustness workstream.
