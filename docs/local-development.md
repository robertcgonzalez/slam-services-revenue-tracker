# Local Development & PostgreSQL Guide

**Purpose**: How to develop and test on **local Windows** (primary).

**Policy (May 2026)**: All work — including heavy Local Enhanced OCR and Azure CV — runs on local Windows. See [environment-policy.md](environment-policy.md).

---

## Quick Decision Tree

| I want to...                              | Recommended Path |
|-------------------------------------------|------------------|
| Run the full Local Enhanced OCR pipeline (EasyOCR + check cropper + payee extraction) against real PDFs | **Local Windows** — `Install-LocalHeavyOcr.ps1` + poppler on PATH |
| G1 hybrid CV check leg (cache-backed or live Read) | Local Windows — `AZURE_CV_*` or `SLAM_CV_CACHE_DIR` in `.env`; use `.\run_local.ps1` |
| Light work, Dashboard, Revenue Requests, rules engine | Local Windows `.venv` (Python 3.10) |
| Test PostgreSQL round-trips (edit → save → reload) | Local Windows with `.env` + `USE_POSTGRES=true` |
| Pre-UAT / production smoke test           | `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` |

---

## Local Windows (primary)

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Setup-LocalVenv.ps1 -InstallHeavyOcr
copy Scripts\spike\cv-read.env.sample .env
.\run_local.ps1
```

`run_local.ps1` activates `.venv`, loads `.env`, sets `PYTHONPATH=App`, and checks for `pdftoppm`. `App/app.py` also loads `.env` on startup.

Heavy stack only (if venv already exists): `.\Scripts\PowerShell\Install-LocalHeavyOcr.ps1`

Verify capabilities:

```powershell
$env:PYTHONPATH = "App"
python -c "import local_enhanced_ocr as o; print(o.detect_capabilities())"
```

---

## Local Windows — light-only shortcut

If you only need Dashboard / Revenue Requests (no OCR):

```powershell
.\Scripts\PowerShell\Setup-LocalVenv.ps1
.\run_local.ps1
```

---

## PostgreSQL Development & Migration

CSV mode is always the safe fallback. Enable Postgres only after you have a working local or Azure instance.

### Local round-trip test (edit → save → reload)

Requires a local Postgres (or the Azure one) + `.env`:

```powershell
cd C:\SLAM-Services-Project
.\.venv\Scripts\Activate.ps1

python Scripts/init_db.py
python Scripts/migrate_to_postgres.py --dry-run
python Scripts/migrate_to_postgres.py

$env:USE_POSTGRES = "true"
$env:SLAM_APP_USER = "Robert"
streamlit run App/app.py
```

In the app:
- Sidebar **Data Source Status** should show **PostgreSQL — connected**
- Revenue Requests → edit a row → **Save All Changes to Database**
- **Force reload data** → verify the change persisted

To go back to CSV-only instantly:

```powershell
Remove-Item Env:USE_POSTGRES -ErrorAction SilentlyContinue
# or
.\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 -DisablePostgres
```

### Production Azure PostgreSQL checklist

See the full provisioning + migration steps in the Blueprint (Phase 3 section) or the older detailed runbooks that were previously in the README. Key scripts:

- `Scripts/init_db.py`
- `Scripts/migrate_to_postgres.py`
- `Scripts/PowerShell/Set-AzurePostgresAppSettings.ps1`
- `Scripts/PowerShell/Deploy-PostgresProduction.ps1`
- `Scripts/PowerShell/Sync-DataRefresh.ps1` (push local CSV changes into Postgres)

Health check (local or via Kudu):

```powershell
python Scripts/health_check.py
python Scripts/health_check.py --json
python Scripts/health_check.py --csv     # validates CSV fallback path
```

---

## Health & Diagnostics

| Command | Purpose |
|---------|---------|
| `python Scripts/health_check.py --full` | CSV + Postgres + row counts + schema connectivity |
| `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` | Pre-UAT / post-deploy (includes live URL reachability + DI status after go-live) |
| Sidebar **🔧 System status** (in-app) | Live capability detection, runtime, data freshness |

**Production schema note**: The live Postgres tables are defined in `db/schema.sql` (the single source of truth). Local repro uses the same definition via `init_db.py` or direct `psql`. See `docs/data-model.md` ("Current Implemented" section) for details.

---

## Common Environment Variables

| Variable | Default / Notes |
|----------|-----------------|
| `USE_POSTGRES` | `false` (CSV mode). Set `true` to enable DB writes. |
| `SLAM_APP_USER` | Actor name shown in UI and written to Postgres (e.g. `Laura`). |
| `SLAM_LOCAL_OCR_DPI_TEXT` / `SLAM_LOCAL_OCR_DPI_CROP` | 300/250 on local Windows for max fidelity (override in `.env` if needed). |
| `SLAM_LOCAL_OCR_MAX_CHECKS` | 40 (default); raise if cropping truncates on long statements. |
| `AZURE_CV_ENDPOINT` / `AZURE_CV_KEY` | Live Azure CV Read on check photos (Local Enhanced auto-enables when set). Keep in `.env` only. |
| `SLAM_IMAGING_FIRST_PAGE` / `SLAM_IMAGING_LAST_PAGE` | Imaging-page scope for CV crop OCR (Traditions hard PDF: `5` / `9`). |
| `SLAM_CV_CACHE_DIR` | Optional cache for zero-cost dev reruns (reuses saved CV JSON; enables CV leg without live calls). |
| `SLAM_CLIENT_NAME` | Optional client hint for bank profile / payee scoring. |
| `AZURE_DI_ENDPOINT` / `AZURE_DI_KEY` + `AZURE_DI_MODEL` / `AZURE_DI_CHECK_MODEL` | Production Azure Document Intelligence (two-leg bank statement pipeline). Normally set via `Set-AzureBankStatementDIAppSettings.ps1` on the App Service; use the local equivalent setter for Robert's machine. |
| `SLAM_HYBRID_CV_ENABLED` | Legacy optional gate for production; not required for Local Enhanced (Sprint 3.3). |

---

## Related Files

- `App/local_enhanced_ocr.py` — the in-process v2.44.3 pipeline (heavy-OCR path)
- `Scripts/test_local_ocr_regression.py` — regression harness (run on local Windows)
- [environment-policy.md](environment-policy.md) — official dev-environment policy

---

**Last major update**: May 28, 2026 — removed GitHub Codespaces / `.devcontainer` path; local Windows only. Historical deployment and OCR pipeline decisions live in the Blueprint Change Log.
