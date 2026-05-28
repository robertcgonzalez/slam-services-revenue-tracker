# Azure Deployment Guide

**Purpose**: All paths for deploying the SLAM Services Revenue Tracker (Streamlit app) to the production Azure App Service (`slam-services-revenue-tracker`).

**Single Source of Truth reference**: See the latest `SLAM Services - Digital Transformation Blueprint.md` Change Log for context on why each path exists.

---

## Prerequisites (common to all paths)

- Azure CLI logged in (`az login`)
- Appropriate RBAC on the `SLAM-Services-RG` resource group
- The deployment package must contain at root: `requirements.txt`, `runtime.txt`, `startup.sh`, `App/`, `Scripts/`
- `Data/` is **never** included in code deploys (gitignored + intentionally preserved on the server via `clean: false`)

---

## Recommended Path: Modern Polling-Safe Deploy (`Deploy-ToAzure.ps1`)

This is the current production path (v2.38.3+). It avoids the ~230s load-balancer timeout that kills long-lived `config-zip` and synchronous `webapp deploy` calls on the F1 tier.

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

What it does (idempotent & safe):

1. Pre-flight checks (login, web app exists, zip exists).
2. Removes `WEBSITE_RUN_FROM_PACKAGE` if present (silent killer of OneDeploy uploads).
3. **`az webapp stop`** — releases Kudu and clears any stuck deploy lock.
4. **`az webapp deploy --type zip --async true`** — returns immediately.
5. Server-side polling of `az webapp deployment list` until terminal status (0 Success / 3 Failed / 5 Partial).
6. **`az webapp start`** + HTTP smoke test against the live URL.

Zip root layout (enforced by the build script):
```
requirements.txt
runtime.txt
startup.sh
pyproject.toml
App/
Scripts/
```

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

See `Scripts/PowerShell/Set-AzurePostgresAppSettings.ps1` for a helper that configures the Postgres-related settings.

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

## Related Scripts

- `Scripts/PowerShell/Build-AzureDeployZip.ps1` — produces the flat `slam-app.zip`
- `Scripts/PowerShell/Deploy-ToAzure.ps1` — the modern safe deploy orchestrator
- `Scripts/PowerShell/Deploy-PostgresProduction.ps1` — wrapper that calls the above + Postgres settings
- `Scripts/PowerShell/Sync-DataRefresh.ps1` — push local CSV changes into the live Postgres instance

---

**Last major update to this guide**: Extracted from README during 2026-05-27 documentation TLC pass. All historical rationale lives in the Blueprint Change Log (v2.38.3, v2.44.x deployment notes).