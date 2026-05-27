# Local Development & PostgreSQL Guide

**Purpose**: How to develop and test locally or in GitHub Codespaces, including the recommended heavy-OCR environment and the PostgreSQL path.

**Primary environment for heavy OCR work (v2.44+)**: The GitHub Codespace named `slam-v2-44-codespaces-migration` (or any new Codespace created from the `.devcontainer/` config).

---

## Quick Decision Tree

| I want to...                              | Recommended Path |
|-------------------------------------------|------------------|
| Run the full Local Enhanced OCR pipeline (EasyOCR + check cropper + payee extraction) against real PDFs | **GitHub Codespaces** (4-core/16 GB recommended) |
| Light work, Dashboard, Revenue Requests, rules engine (no heavy OCR) | Local Windows `.venv` (Python 3.10) or any Codespace |
| Test PostgreSQL round-trips (edit → save → reload) | Local or Codespace with `.env` + `USE_POSTGRES=true` |
| Pre-UAT / production smoke test           | `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` |

---

## GitHub Codespaces (Recommended for OCR-Heavy Work)

### One-click setup

1. On the GitHub repo → **Code** → **Codespaces** tab → **Create codespace on main**.
2. (Strongly recommended) Click the `…` menu → **+ New with options...** → pick the **4-core / 16 GB RAM** machine type.
3. Wait 3–5 minutes. The post-create script provisions poppler, the `.venv`, heavy OCR libs (PyTorch is the slow part), and pre-warms the EasyOCR English model.
4. When the shell opens:

   ```bash
   slam-run     # alias → streamlit run App/app.py
   ```

5. Port 8501 is auto-forwarded. Click the notification to open the public URL.

### What you get

- Base: Microsoft `python:1-3.10-bookworm` (matches Azure F1 runtime)
- System: `poppler-utils`, `libgl1`, `libglib2.0-0`, `gh`
- Full heavy OCR stack identical to the Azure Function (minus `azure-functions`)
- Aliases: `slam-run`, `slam-lint`, `slam-format`, `slam-health`, `slam-info`
- Codespaces-aware OCR defaults (lower DPI to fit in 8 GB): see `.devcontainer/devcontainer.json`

### Verifying the full pipeline

```bash
slam-info      # confirms 6/6 capabilities + active DPIs
slam-run
```

In the app: Bank Statements → upload `Data/Auto_Body_Center_Jan_26_Statement.pdf` → select **🖥️ Local Enhanced OCR (Robert only — v2.44.3)**.

The sidebar **🔧 System status** expander shows the active runtime and DPI settings live.

### Rebuilding the container

VS Code Command Palette → **Codespaces: Rebuild Container** (keeps your uncommitted edits).

### Cost & lifecycle notes

- Free personal quota: 120 core-hours / 15 GB-month (2026).
- 4-core SKU ≈ 4 core-hours per wall-clock hour.
- Auto-stops after 30 min inactivity; resumes in ~30 s.
- `Data/` is never committed (per `.gitignore`) — client PDFs/CSVs you copy in stay local to that Codespace.

---

## Local Windows Development (Python 3.10 .venv)

### First-time or broken venv (recommended)

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Setup-LocalVenv.ps1
.\.venv\Scripts\Activate.ps1
streamlit run App/app.py
```

Manual equivalent:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt ruff black
# For Local Enhanced OCR work only:
pip install pdfplumber pdf2image easyocr pillow opencv-python-headless numpy
# Windows-only poppler for pdf2image (one of):
#   conda install -c conda-forge poppler
#   winget install --id oschwartz10612.Poppler
#   Manual: https://github.com/oschwartz10612/poppler-windows/releases
ruff check App/ Scripts/
streamlit run App/app.py
```

### Local Enhanced OCR (Robert only) — one-time setup

The radio button **🖥️ Local Enhanced OCR (Robert only — v2.44.3)** runs a byte-faithful in-process port of the v2.43 Azure pipeline.

It requires the six heavy libraries above. When they are missing the radio gracefully falls back to the Lightweight Parser (pdfplumber only) with a clear warning. Production F1 never has the heavy libs, so Laura is never affected.

See sidebar **🔧 System status** for live capability detection.

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
| `python Scripts/health_check.py --full` | CSV + Postgres + row counts |
| `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` | Pre-UAT / post-deploy (includes live URL reachability) |
| `slam-info` (Codespaces) | Local Enhanced OCR capability matrix + active DPIs |
| `slam-health` | Quick CSV-mode probe |
| Sidebar **🔧 System status** (in-app) | Live capability detection, runtime, data freshness |

---

## Common Environment Variables

| Variable | Default / Notes |
|----------|-----------------|
| `USE_POSTGRES` | `false` (CSV mode). Set `true` to enable DB writes. |
| `SLAM_APP_USER` | Actor name shown in UI and written to Postgres (e.g. `Laura`). |
| `SLAM_LOCAL_OCR_DPI_TEXT` / `SLAM_LOCAL_OCR_DPI_CROP` | 200/220 in Codespaces (lower to fit 8 GB); 300/250 on Robert's local Windows for max fidelity. |
| `SLAM_LOCAL_OCR_MAX_CHECKS` | 50 (v2.44.3) |

---

## Related Files

- `.devcontainer/devcontainer.json` + `postCreateCommand.sh` — Codespaces definition and 7-stage provisioner
- `docs/codespaces-connection-recipe.md` — how Cursor/Grok reliably SSH into the primary mirroring Codespace (must-use for heavy OCR regression testing)
- `App/local_enhanced_ocr.py` — the in-process v2.44.3 pipeline (heavy-OCR path)
- `Scripts/test_local_ocr_regression.py` — the regression harness that must be run inside the mirroring Codespace

---

**Last major update**: Extracted & condensed during 2026-05-27 README TLC pass. Historical deployment and OCR pipeline decisions live in the Blueprint Change Log.