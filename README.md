# SLAM Services Grok Projects Workspace

**Purpose**  
This is the central workspace for the **SLAM Services Digital Transformation Project**.

It contains all project assets, documentation, data, scripts, and the deployed Streamlit application.

---

## 📌 Current Status (as of May 24, 2026 — Blueprint v2.34)

- **Phase 1** — Revenue Reporting Tracker: **Complete**
- **Phase 2** — Secure Azure Deployment: **Complete** (F1 tier)
- **Phase 2.5** — Stabilization (P0–P2): **Complete in app**
- **Bank Statements MVP (v2.34)** — Upload PDF → process → review transactions → Mark as Received (Core Workstream #2)
- **UAT (v2.32)** — Laura/Stef user acceptance testing; unsaved-change guards, new quick views, ops health script
- **Daily driver (v2.31)** — Dashboard briefing, quick filters, help panel, logging, CSV/DB freshness
- **P0 Azure CSV path (v2.26)** — **Fixed and live** (manual zip deploy confirmed)
- **Local dev (v2.27)** — **Working** — Python 3.10 `.venv` rebuilt; Streamlit runs locally
- **Phase 3** — **Production PostgreSQL on Azure** (SSL, health checks, deploy scripts; CSV fallback preserved)

**Live Application**:  
→ [http://slam-services-revenue-tracker.azurewebsites.net/](http://slam-services-revenue-tracker.azurewebsites.net/)

**Single Source of Truth**:  
**`SLAM Services - Digital Transformation Blueprint.md`**

---

## Azure deployment (v2.26)

Client CSVs are **not in git**. Choose one:

### A. Manual flat zip (recommended when restoring Data)

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
az webapp deployment source config-zip `
  -g SLAM-Services-RG `
  -n slam-services-revenue-tracker `
  --src slam-app.zip
```

Zip root must contain: `requirements.txt`, `App/`, `Data/Revenue_Tracker_Migration/`, `startup.sh`, `runtime.txt`.

### B. GitHub Actions (code-only; preserves existing Data)

Push to `main` with `AZUREAPPSERVICEPUBLISHPROFILE` set. Workflow uses `clean: false` so an existing `Data/` folder on the App Service is not deleted.

### C. Kudu upload

Upload `Data/Revenue_Tracker_Migration/` to `/home/site/wwwroot/Data/Revenue_Tracker_Migration/` (Advanced Tools → Kudu → Debug console).

### Optional App Settings

| Setting | Purpose |
|--------|---------|
| `SLAM_APP_PASSWORD` | Production login (required for team access) |
| `SLAM_DATA_PATH` | Override CSV folder (e.g. `/home/site/wwwroot/Data/Revenue_Tracker_Migration`) |
| `USE_POSTGRES` | `true` when Azure PostgreSQL is provisioned and migrated |
| `DATABASE_URL` or `POSTGRES_*` | PostgreSQL connection (never commit) |
| `SLAM_APP_USER` | Optional audit label for PostgreSQL write-back (default: `streamlit`) |
| `POSTGRES_SSLMODE` | SSL mode for Azure (default: `require` when host is `*.postgres.database.azure.com`) |

---

## UAT week guide (v2.32)

**For Laura / Stef** — first week on the live app:

| Step | Action |
|------|--------|
| 1 | Log in at the live URL (password from Robert) |
| 2 | Confirm your name shows in the sidebar (`SLAM_APP_USER` in Azure) |
| 3 | **Dashboard** → read Today's priority → dismiss welcome banner when ready |
| 4 | Try sidebar quick views: **Overdue**, **This Month**, **Missing Docs** |
| 5 | **Bank Statements** → upload a test PDF → **Process Statement** → review table |
| 6 | **Revenue Requests** → edit a row → **Save** → wait for green confirmation |
| 7 | If you see **unsaved changes**, save before switching pages |
| 8 | Use **Undo Last Change** once to verify recovery works |
| 9 | Submit feedback via sidebar form if anything blocks daily work |

**For Robert** — before each UAT session:

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
az webapp deployment source config-zip -g SLAM-Services-RG -n slam-services-revenue-tracker --src slam-app.zip
```

Verify Azure App Settings: `SLAM_APP_PASSWORD`, `SLAM_APP_USER=Laura` (or Stef).

---

## Daily driver tips (v2.32)

| For | Do this |
|-----|---------|
| Laura / Stef | **Dashboard** → Today's priority → **Bank Statements** (PDF pipeline) → **Missing Docs** / **Revenue Requests** → **Save** |
| Robert (CSV updated) | `.\Scripts\PowerShell\Sync-DataRefresh.ps1` to push CSV changes into PostgreSQL |
| Robert (pre-UAT) | `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` |
| Robert (deploy) | `.\Scripts\PowerShell\Build-AzureDeployZip.ps1` then `az webapp deployment source config-zip` |
| Health (CSV mode) | `python Scripts/health_check.py --csv` |
| Health (Postgres) | `python Scripts/health_check.py` |
| Health (both) | `python Scripts/health_check.py --full` |

Set `SLAM_APP_USER=Laura` (or Stef) in Azure App Settings so saves and sidebar show the correct name.

---

## Production PostgreSQL checklist (v2.30)

Use this sequence for Laura/Stef go-live. CSV mode remains available as fallback.

| Step | Action | Verify |
|------|--------|--------|
| 1 | Provision Azure PostgreSQL Flexible Server (below) | `az postgres flexible-server show -g SLAM-Services-RG -n slam-services-db` |
| 2 | `python Scripts/init_db.py` | Schema created |
| 3 | `python Scripts/migrate_to_postgres.py` | Row counts match CSV |
| 4 | `python Scripts/health_check.py` | Exit code 0, clients/requests > 0 |
| 5 | Set App Settings (`Set-AzurePostgresAppSettings.ps1` or Azure Portal) | `USE_POSTGRES=true`, `POSTGRES_SSLMODE=require` |
| 6 | Deploy code (`Deploy-PostgresProduction.ps1` or manual zip) | App starts, startup log shows health check |
| 7 | Log in → sidebar **Data Source Status** | ✅ PostgreSQL connected + row counts |
| 8 | Revenue Requests → edit → save → Force reload | Patch persists |

### CSV fallback (zero disruption)

If PostgreSQL has issues, Robert can revert to CSV mode instantly:

```powershell
.\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 -DisablePostgres
# Or Azure Portal: set USE_POSTGRES=false
```

The app auto-falls back to CSV when Postgres is unreachable (even if `USE_POSTGRES=true`).

---

## Azure PostgreSQL (Phase 3 — v2.30)

CSV mode remains the default. Enable PostgreSQL only after provisioning and migration.

### 1. Create Azure Database for PostgreSQL Flexible Server

Replace `<secure-password>` with a strong admin password (store in a password manager — never commit).

```powershell
# Variables — adjust region/SKU as needed
$RG = "SLAM-Services-RG"
$LOCATION = "eastus"
$SERVER = "slam-services-db"
$ADMIN = "slamadmin"
$DB = "slam_services"

az postgres flexible-server create `
  --resource-group $RG `
  --name $SERVER `
  --location $LOCATION `
  --tier Burstable `
  --sku-name Standard_B1ms `
  --storage-size 32 `
  --version 16 `
  --admin-user $ADMIN `
  --admin-password "<secure-password>"

az postgres flexible-server db create `
  --resource-group $RG `
  --server-name $SERVER `
  --database-name $DB

# Allow Azure services (required for App Service → Postgres)
az postgres flexible-server firewall-rule create `
  --resource-group $RG `
  --name AllowAzureServices `
  --server-name $SERVER `
  --start-ip-address 0.0.0.0 `
  --end-ip-address 0.0.0.0
```

Host for App Settings: `$SERVER.postgres.database.azure.com`

### 2. Initialize schema + migrate CSV data (local or Cloud Shell)

Create a local `.env` (gitignored) with connection vars, then:

```powershell
cd C:\SLAM-Services-Project
.\.venv\Scripts\Activate.ps1

# .env example (never commit):
# POSTGRES_HOST=slam-services-db.postgres.database.azure.com
# POSTGRES_USER=slamadmin
# POSTGRES_PASSWORD=<secure-password>
# POSTGRES_DB=slam_services

python Scripts/init_db.py
python Scripts/migrate_to_postgres.py --dry-run
python Scripts/migrate_to_postgres.py
```

Re-run `migrate_to_postgres.py` safely after CSV updates — upserts are idempotent.

### 3. Configure App Service App Settings

```powershell
$PGHOST = "$SERVER.postgres.database.azure.com"

az webapp config appsettings set `
  -g SLAM-Services-RG `
  -n slam-services-revenue-tracker `
  --settings `
    USE_POSTGRES=true `
    POSTGRES_HOST=$PGHOST `
    POSTGRES_USER=$ADMIN `
    POSTGRES_PASSWORD="<secure-password>" `
    POSTGRES_DB=$DB `
    SLAM_APP_USER="Laura"
```

Deploy updated app code, then verify the sidebar **Data Source Status** shows **PostgreSQL — connected**.

```powershell
# Optional: one-command deploy after .env is configured
.\Scripts\PowerShell\Deploy-PostgresProduction.ps1

# Or configure App Settings interactively
.\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 `
  -PostgresHost "$SERVER.postgres.database.azure.com" `
  -PostgresUser $ADMIN
```

**Note:** Azure Flexible Server may require username format `slamadmin@slam-services-db` — use whichever format your server accepts in `POSTGRES_USER`.

### Health check (local or Kudu SSH)

```powershell
python Scripts/health_check.py
python Scripts/health_check.py --json
python Scripts/health_check.py --csv    # CSV-only / fallback validation
```

After CSV edits (sync to PostgreSQL):

```powershell
.\Scripts\PowerShell\Sync-DataRefresh.ps1
.\Scripts\PowerShell\Sync-DataRefresh.ps1 -DryRun
```

---

## Local verification

### First-time or broken venv (recommended)

If `pip install` fails with **Access is denied** on `.venv`, stop orphaned Streamlit processes first, then rebuild:

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Setup-LocalVenv.ps1
.\.venv\Scripts\Activate.ps1
streamlit run App/app.py
```

Manual equivalent:

```powershell
cd C:\SLAM-Services-Project
# Stop any streamlit/python using .venv, then:
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt ruff black
ruff check App/ Scripts/
streamlit run App/app.py
```

Migration dry-run (no DB required):

```powershell
python Scripts/migrate_to_postgres.py --dry-run
```

### PostgreSQL full round-trip test (edit → save → reload)

Requires `.env` with `POSTGRES_*` or `DATABASE_URL`, plus migrated data:

```powershell
cd C:\SLAM-Services-Project
.\.venv\Scripts\Activate.ps1

python Scripts/init_db.py
python Scripts/migrate_to_postgres.py

$env:USE_POSTGRES = "true"
$env:SLAM_APP_USER = "Robert"
streamlit run App/app.py
```

In the app: log in → sidebar **Data Source Status** should show PostgreSQL connected → **Revenue Requests** → edit a status or amount → **Save All Changes to Database** → **Force reload data** → confirm the edit persisted.

CSV-only mode (default, unchanged):

```powershell
# Do not set USE_POSTGRES — or explicitly:
Remove-Item Env:USE_POSTGRES -ErrorAction SilentlyContinue
streamlit run App/app.py
```

Post-deploy: log in to the live URL; confirm dashboard metrics load (no CSV path error). Check App Service log stream for `Data folder found` from `startup.sh`.

---

## How to Work with Cursor + Kilo Code

**Cursor** (Composer / Agent / inline edit) is the **primary / lead** AI coding agent for this project. **Kilo Code** remains available as a **secondary** tool when you want an alternate workflow — it does not override Cursor’s lead role.

When starting a new session in Cursor, begin with:

> "Reference the full SLAM Services Digital Transformation Blueprint.md (latest version) and this README.md. [Your request]"

### Key Files

- **`SLAM Services - Digital Transformation Blueprint.md`** — Main living document + Change Log
- `App/app.py` — Streamlit Revenue Reporting Tracker
- `App/db_utils.py` — PostgreSQL models + CRUD helpers
- `Scripts/init_db.py` — Idempotent schema initialization
- `Scripts/migrate_to_postgres.py` — CSV → PostgreSQL migration
- `Scripts/health_check.py` — PostgreSQL + `--csv` + `--full` health check
- `Scripts/PowerShell/Check-AppHealth.ps1` — Pre-UAT / post-deploy validation
- `Scripts/PowerShell/Sync-DataRefresh.ps1` — CSV → PostgreSQL refresh (idempotent)
- `Scripts/PowerShell/Deploy-PostgresProduction.ps1` — Build + deploy helper
- `App/diagnostics.py` — Data freshness + system info for sidebar
- `App/app_logging.py` — Structured `slam_app` logs (Azure log stream)
- `Scripts/PowerShell/Set-AzurePostgresAppSettings.ps1` — Enable/disable Postgres settings
- `requirements.txt` — Python dependencies
- `.cursor/rules/slam-services.mdc` — Cursor primary project rules (`alwaysApply`)
- `.kilocode` — Shared agent principles (Cursor leads; Kilo secondary)
- `.vscode/` — Shared tasks, launch, lint/format settings
- `Data/Revenue_Tracker_Migration/` — Source data (local; not in git)

---

## Project Goals

- Reduce manual revenue chasing work for Laura and Stef
- Build visible, reliable automation
- Enable smooth handover to Patty & Robert
- Maintain high standards for security and data privacy

---

## Folder Structure
