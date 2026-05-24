# SLAM Services Grok Projects Workspace

**Purpose**  
This is the central workspace for the **SLAM Services Digital Transformation Project**.

It contains all project assets, documentation, data, scripts, and the deployed Streamlit application.

---

## 📌 Current Status (as of May 24, 2026 — Blueprint v2.26)

- **Phase 1** — Revenue Reporting Tracker: **Complete**
- **Phase 2** — Secure Azure Deployment: **Complete** (F1 tier)
- **Phase 2.5** — Stabilization (P0–P2): **Complete in app**
- **P0 (May 24)** — Azure CSV path / deploy packaging: **Fixed in code** — redeploy required (see below)
- **Phase 3 prep** — PostgreSQL dual-mode + migration script skeleton: **In repo** (`USE_POSTGRES` off by default)
- **Status**: Redeploy with `Data/` present on App Service (manual zip or preserved folder + CI `clean: false`)

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

---

## Local verification

```powershell
cd C:\SLAM-Services-Project
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ruff check App/
ruff format App/ Scripts/migrate_to_postgres.py
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
