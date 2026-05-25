# SLAM Services Grok Projects Workspace

**Purpose**  
This is the central workspace for the **SLAM Services Digital Transformation Project**.

It contains all project assets, documentation, data, scripts, and the deployed Streamlit application.

---

## 📌 Current Status (as of May 25, 2026 — Blueprint v2.44)

- **Development Environment Migration (v2.44)** — **GitHub Codespaces is now the recommended dev environment** for the heavy Local Enhanced OCR pipeline. New `.devcontainer/` config provisions a fully-loaded Linux container (Python 3.10, poppler-utils, pdfplumber + pdf2image + easyocr + opencv-python-headless + pillow + numpy, EasyOCR English model pre-warmed) on every Codespace creation. Streamlit is auto-forwarded on port 8501. Smart resource-aware defaults: `SLAM_LOCAL_OCR_DPI_TEXT=200`, `SLAM_LOCAL_OCR_DPI_CROP=180` (vs. `300/250` on Robert's local Windows machine) keep memory under ~3 GB on the standard 4-core / 8 GB SKU. See **[Development with GitHub Codespaces](#development-with-github-codespaces-v244)** below for one-click setup.
- **Phase 1** — Revenue Reporting Tracker: **Complete**
- **Phase 2** — Secure Azure Deployment: **Complete** (F1 tier; modern polling-safe deploy path v2.38.3)
- **Phase 2.5** — Stabilization (P0–P2): **Complete in app**
- **Azure OCR Function (v2.43)** — `slam-ocr-function` (Linux Y1 Consumption) runs the full real-OCR pipeline (pdfplumber fast path → pdf2image+EasyOCR fallback → OpenCV check cropper) **plus intelligent check ↔ transaction linking** that extracts the payee from each cropped check image's "Pay to the order of" line and writes it back to the matched transaction's Payee. **Deploy parked** at v2.43.1 pending Y1 infra decision; live Function still serves v2.41-skeleton. Streamlit Bank Statements page consumes the new pipeline with zero code changes the moment it ships.
- **Local Enhanced OCR (v2.43.2 — Robert only)** — In-process port of the v2.43 Azure pipeline lives at `App/local_enhanced_ocr.py` so Robert can flip the **🖥️ Local Enhanced OCR (Robert only)** radio on the Bank Statements page and run the full check-linking workflow on his dev machine while the Azure deploy is parked. Heavy libs (`pdfplumber + pdf2image + easyocr + opencv-python-headless + pillow + numpy`, plus Windows `poppler` on PATH) are imported lazily — missing libs degrade to **Lightweight Parser** with a clear warning; no impact on the production F1 App Service.
- **Bank Statements** — Upload PDF → **Lightweight Parser** OR **🖥️ Local Enhanced OCR (Robert only — v2.43.2)** OR **Azure OCR (v2.43)** OR paste Grok CSV → automated reconciliation check → **persistent payee rules engine** (v2.39) → review → Mark as Received (Core Workstream #2)
- **Payee rules engine (v2.39)** — `Data/payee_rules.csv` auto-applies on every statement, with **💡 Learn this mapping** to teach new rules (Quick Parallel Win delivered from Blueprint §8.1)
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

## Development with GitHub Codespaces (v2.44)

**Recommended dev environment** for everything OCR-heavy (the Local Enhanced OCR pipeline pulls in PyTorch + EasyOCR + OpenCV + Poppler — together ~1.5 GB of system + Python deps that are painful to install on a fresh Windows or macOS machine). Codespaces gives every contributor a clean Linux container with the entire stack pre-installed and a publicly-forwarded Streamlit URL, in about **5 minutes** from "I want to develop on this repo" to "I can run the full v2.43.2 pipeline against `Data/Auto_Body_Center_Jan_26_Statement.pdf`".

### One-click setup

1. On the GitHub repo page, click **`<> Code`** → **`Codespaces`** tab → **`Create codespace on main`**.
2. (Recommended) Click the `…` menu next to the **Create codespace** button → **`+ New with options...`** and pick the **4-core / 16 GB RAM** machine type. The 4-core / 8 GB SKU works for small statements, but 16 GB is much more comfortable once `easyocr` warms up on a multi-page scanned PDF (PyTorch can spike past 6 GB).
3. Wait ~3-5 minutes for the post-create script to provision system poppler, the `.venv` virtual environment, the heavy OCR libs (PyTorch is the slow bit), and pre-warm the EasyOCR English model. Watch progress in the **"Creating codespace"** log panel.
4. When the terminal shell opens, run:

   ```bash
   slam-run    # alias for: streamlit run App/app.py
   ```

5. Codespaces auto-forwards port 8501 and pops a notification with the public Streamlit URL — click **Open in Browser**. Log in with the password Robert provides (or the dev default).

### What you get out of the box

| Component | Version | Source |
|-----------|---------|--------|
| Base image | `mcr.microsoft.com/devcontainers/python:1-3.10-bookworm` | Microsoft-maintained, matches Azure F1 App Service runtime |
| System libs | `poppler-utils`, `libgl1`, `libglib2.0-0`, `gh` (GitHub CLI) | apt-installed by `postCreateCommand.sh` |
| Project venv | `.venv/` at repo root, auto-activated on every shell | mirrors Robert's local Windows workflow |
| Core deps | `streamlit`, `pandas`, `plotly`, `pdfplumber`, `sqlalchemy`, `psycopg2-binary` | from `requirements.txt` |
| Heavy OCR deps | `pdfplumber>=0.11`, `pdf2image>=1.17`, `easyocr>=1.7`, `opencv-python-headless>=4.8`, `pillow>=10.0`, `numpy>=1.26` | matches `AzureFunctions/ocr_processor/requirements.txt` minus `azure-functions` |
| Dev tooling | `ruff`, `black`, `ipython` | pinned config in `pyproject.toml` |
| EasyOCR model | English `craft` + recognition weights, pre-warmed at provision time | cached at `~/.EasyOCR` |

### Codespaces-aware OCR defaults (v2.44)

To fit the heavy raster + OCR stack inside the **4-core / 8 GB** standard Codespaces SKU, `App/local_enhanced_ocr.py` lowers its DPI / page / check-count defaults when it detects `CODESPACES=true`. Override any of these via `export` before launching Streamlit if you're on the 16 GB+ SKU and want full fidelity:

| Tunable | Codespaces default | Local Windows default | Override |
|---------|-------------------:|----------------------:|----------|
| `SLAM_LOCAL_OCR_DPI_TEXT` | `200` | `300` | raises raster fidelity for the EasyOCR fallback |
| `SLAM_LOCAL_OCR_DPI_CROP` | `180` | `250` | raises check-cropper fidelity (improves "Pay to the order of" extraction) |
| `SLAM_LOCAL_OCR_MAX_PAGES_RASTER` | `20` | `30` | cap on raster fallback pages per PDF |
| `SLAM_LOCAL_OCR_MAX_CHECKS` | `30` | `40` | cap on cropped checks per PDF |
| `SLAM_LOCAL_OCR_FAST_PATH_MIN_ROWS` | `3` | `3` | threshold below which the raster fallback runs |

The sidebar **🔧 System status** expander shows the active runtime, DPI, and page-cap settings live so you can confirm what's in effect for any given Streamlit session.

### Useful aliases (auto-installed in `~/.bashrc`)

| Alias | Equivalent | Purpose |
|-------|-----------|---------|
| `slam-run` | `streamlit run App/app.py` | launch the Streamlit dev server on port 8501 |
| `slam-lint` | `ruff check App/ Scripts/` | run the project linter |
| `slam-format` | `ruff format App/ Scripts/ && ruff check --fix App/ Scripts/` | auto-format + auto-fix |
| `slam-health` | `python Scripts/health_check.py --csv` | CSV-mode health probe |
| `slam-info` | inline Python printing the active OCR capability matrix + DPIs | quick "is everything wired?" check |

### Verifying the full Local Enhanced OCR pipeline

Once the Codespace is provisioned:

```bash
slam-info       # confirms all 6 caps are true and shows the active DPIs
slam-run        # opens Streamlit on the auto-forwarded port 8501
```

In the app: **Bank Statements** page → upload `Data/Auto_Body_Center_Jan_26_Statement.pdf` (or any local PDF) → select **🖥️ Local Enhanced OCR (Robert only — v2.43.2)** → **Process Statement**. The Processing log expander now logs a Codespaces-aware startup banner showing exactly which DPIs are in effect, so you can correlate "0 cropped checks" against a too-low DPI setting if you ever need to debug.

### Rebuilding the container

Anything in `.devcontainer/` (devcontainer.json, postCreateCommand.sh) takes effect the next time the container is built. To rebuild without losing in-progress edits:

- VS Code Command Palette (`Ctrl+Shift+P`) → **`Codespaces: Rebuild Container`**.

### Cost notes

- **GitHub Codespaces** has a free monthly quota (120 core-hours / 15 GB-month for personal accounts as of 2026). The 4-core / 16 GB SKU consumes ~4 core-hours per real hour of use, so the free quota is 30 hours of active dev time per month.
- Codespaces auto-stops after 30 minutes of inactivity; the container resumes in ~30 seconds when you reopen.
- Storage cost is ~free for this repo's working set; **nothing in `Data/` is committed** (per `.gitignore`), so client CSVs/PDFs that you copy into the Codespace stay local to that machine and disappear when the Codespace is deleted.

### Repo naming note

The repo is currently `robertcgonzalez/slam-services-revenue-tracker`. Now that the project has grown well past the original Revenue Tracker (Bank Statements + OCR + payee rules + PostgreSQL path + Local Enhanced OCR), a more future-proof name is reasonable. Two candidates worth discussing with Laura before any rename:

| Candidate | Pros | Cons |
|-----------|------|------|
| `slam-services-platform` | Reflects multi-workstream scope; matches Blueprint Section 8 ("Core Workstreams") language | Generic; doesn't signal "operations" |
| `slam-services-operations` | Matches the "operational backbone" framing in Blueprint Section 2; signals day-to-day-driver intent | Slightly longer; might collide with future "ops/devops" repo |

If we rename, the (live) Azure App Service `slam-services-revenue-tracker.azurewebsites.net` URL stays the same (App Service name is decoupled from the GitHub repo), the live PostgreSQL server `slam-services-db` stays the same, and the only places that hard-code the repo name are this README, the Blueprint, and the GitHub Actions workflow `AZUREAPPSERVICEPUBLISHPROFILE` secret reference (which is keyed by repo, not by name). GitHub auto-redirects from the old name to the new name for ~12 months after rename, so there's no immediate disruption. **Recommendation**: defer the rename until after the v2.44 Codespaces migration is well-bedded in (1-2 weeks of real use), then bundle the rename into a single Blueprint version bump so the README, Blueprint header, and Cursor / Kilo Code rules can all reference the new name in one go.

---

## Azure deployment (v2.38.3 — modern, polling-safe; carried into v2.39)

Client CSVs are **not in git**. Choose one:

### A. Modern recommended path — `Deploy-ToAzure.ps1` (build + safe deploy)

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

What `Deploy-ToAzure.ps1` does (replaces the legacy `config-zip` + raw `webapp deploy` flow):

1. Pre-flight checks (login, web app exists, zip exists).
2. Removes `WEBSITE_RUN_FROM_PACKAGE` if present (silently breaks OneDeploy zip uploads when set).
3. **Stops** the web app to release Kudu and clear any stuck deploy lock from a prior failed attempt.
4. Uploads via `az webapp deploy --type zip --async true` — returns immediately, so there is no long-lived HTTPS polling connection that the App Service front-end LB can drop at ~230 s (root cause of `RemoteDisconnected('Remote end closed connection without response')` on F1 tier).
5. Polls `az webapp deployment list` server-side until a terminal status (0 Success / 3 Failed / 5 Partial).
6. **Starts** the web app and runs an HTTP smoke test against the live URL.

Zip root must contain: `requirements.txt`, `App/`, `Data/Revenue_Tracker_Migration/`, `startup.sh`, `runtime.txt`, `Scripts/`.

### B. Manual one-shot (when you need full control)

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

> **Do not use the legacy** `az webapp deployment source config-zip` — it prints a deprecation warning and uses the older synchronous endpoint that is also vulnerable to the same 230-second LB timeout.

### C. GitHub Actions (code-only; preserves existing Data)

Push to `main` with `AZUREAPPSERVICEPUBLISHPROFILE` set. Workflow uses `clean: false` so an existing `Data/` folder on the App Service is not deleted.

### D. Kudu upload (Data only)

Upload `Data/Revenue_Tracker_Migration/` to `/home/site/wwwroot/Data/Revenue_Tracker_Migration/` (Advanced Tools → Kudu → Debug console).

### Recovery — when a deploy hangs or returns `RemoteDisconnected`

Symptoms: `az webapp deploy` hangs at *"Warming up Kudu before deployment"*, then errors with `('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`, and the live URL shows `Connection timed out`.

Root cause (typical on F1): the CLI's `_make_onedeploy_request` keeps a long HTTPS connection open while polling Kudu; the App Service front-end load balancer kills any idle TCP connection at ~230 s. Meanwhile the OneDeploy job is often still alive on the server, so retrying immediately can collide with a stale deploy lock.

Run these in order — each is idempotent and safe:

```powershell
# 1. Stop the app (releases Kudu, kills any in-flight deploy handler)
az webapp stop -g SLAM-Services-RG -n slam-services-revenue-tracker

# 2. Remove the #1 silent killer of zip deploys (no-op if already gone)
az webapp config appsettings delete `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --setting-names WEBSITE_RUN_FROM_PACKAGE

# 3. Confirm no deployment is currently in-flight on the server
az webapp deployment list `
  -g SLAM-Services-RG -n slam-services-revenue-tracker `
  --query "[0].{status:status,complete:complete,message:message}" -o table

# 4. Re-run the safe modern deploy
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

If step 3 reports a deployment with `complete: false` for more than ~5 minutes after step 1, restart Kudu specifically:

```powershell
az resource invoke-action `
  --resource-group SLAM-Services-RG `
  --name "slam-services-revenue-tracker/scm" `
  --resource-type Microsoft.Web/sites/host `
  --action restart --api-version 2022-03-01
```

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
.\Scripts\PowerShell\Deploy-ToAzure.ps1
```

Verify Azure App Settings: `SLAM_APP_PASSWORD`, `SLAM_APP_USER=Laura` (or Stef).

---

## Daily driver tips (v2.39)

| For | Do this |
|-----|---------|
| Laura / Stef | **Dashboard** → Today's priority → **Bank Statements** (PDF pipeline OR paste Grok CSV) → review auto-applied **payee rules** → use **💡 Learn this mapping** to teach new ones → **Missing Docs** / **Revenue Requests** → **Save** |
| Laura (rules engine) | After import, look for the green **🧠 X payee mapping(s) applied** callout. Click **🔄 Apply Payee Rules** any time to re-clean the table; use **💡 Learn this mapping** to add a new rule from any row (saves to `Data/payee_rules.csv`). |
| Robert (CSV updated) | `.\Scripts\PowerShell\Sync-DataRefresh.ps1` to push CSV changes into PostgreSQL |
| Robert (pre-UAT) | `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure` |
| Robert (deploy) | `.\Scripts\PowerShell\Build-AzureDeployZip.ps1` then `.\Scripts\PowerShell\Deploy-ToAzure.ps1` |
| Robert (payee rules) | `Data/payee_rules.csv` is gitignored — open it directly to bulk-edit seed rules, or set `SLAM_PAYEE_RULES_PATH` to point at a shared file (e.g. on Azure: `/home/site/wwwroot/Data/payee_rules.csv`). |
| Health (CSV mode) | `python Scripts/health_check.py --csv` |
| Health (Postgres) | `python Scripts/health_check.py` |
| Health (both) | `python Scripts/health_check.py --full` |

Set `SLAM_APP_USER=Laura` (or Stef) in Azure App Settings so saves and sidebar show the correct name.

### Bank Statements workflow (v2.39 quick reference, updated v2.43.2)

1. **Choose client** + upload PDF(s) → pick a **Processing mode**:
   - **Lightweight Parser** (default — fast in-process pdfplumber path; works on every deploy)
   - **🖥️ Local Enhanced OCR (Robert only — v2.43.2)** — runs the full v2.43 pipeline (pdfplumber → easyocr fallback → opencv check cropping → intelligent check ↔ transaction matcher) **in-process**. Requires heavy libs installed locally; see the [Local Enhanced OCR Mode](#local-enhanced-ocr-mode-robert-only--v2432) section below.
   - **Azure OCR (Recommended for scanned PDFs)** — offloads to the dedicated `slam-ocr-function` Function App; only when the App Settings are configured (currently parked on v2.41-skeleton — see Blueprint v2.43.1).
   - …or paste Grok Vision CSV under **📋 Option 2** (image-only / scanned statements) — no processing-mode toggle needed
2. **Process Statement** → review the **automated reconciliation banner** — green ✅ when detail totals match the bank's TOTALS line, red ⚠️ when they don't (the whole statement flags for review)
3. Check the **🧠 X payee mapping(s) applied** callout — `Data/payee_rules.csv` auto-cleaned merchants like `WAL-MART STORE #1234` → `Walmart` / `Supplies`
4. Use **💡 Learn this mapping** to teach a new rule for anything still messy — pick the row, edit pattern + clean Payee + Category, optionally scope to this client, **Save mapping**. The rule is reapplied immediately and persists across future statements.
5. Edit any remaining rows manually in the data editor (rules engine never overwrites your manual edits on re-apply)
6. **Download transactions CSV** for Power Query / `Process-Statement.ps1` (column order unchanged)
7. **Link to revenue request** → **Mark as Received**

### Local Enhanced OCR Mode (Robert only — v2.43.2)

**Interim solution** so Robert can exercise the full v2.43 intelligent check-linking pipeline locally while the Azure Function deploy stays parked behind the Y1 infra decision (see Blueprint v2.43.1 Change Log for the four candidate paths forward).

What it does:

- Selects the **🖥️ Local Enhanced OCR (Robert only)** radio on the Bank Statements page
- Runs `App/local_enhanced_ocr.py` in-process — a byte-faithful port of `AzureFunctions/ocr_processor/function_app.py` v2.43 minus the Azure-Functions HTTP layer
- Pipeline stages match the Function exactly: pdfplumber text-layer fast path → pdf2image+EasyOCR raster fallback at 300 DPI → OpenCV check cropper at 250 DPI → v2.43 check ↔ transaction matcher (exact Check# → amount equality → fuzzy Description match) → Payee enhancement from the "Pay to the order of" line on each cropped check image
- Same canonical 12-column DataFrame, same `grok_totals` payload, same `cropped_checks` shape with `linked_check_id` / `extracted_payee` so the existing reconciliation banner, payee rules engine, and Power Query workflow all consume the output unchanged

One-time local setup (Robert's dev machine):

```powershell
# Inside the project .venv (Python 3.10)
pip install pdfplumber pdf2image easyocr pillow opencv-python-headless numpy

# Windows-only: pdf2image needs the poppler binaries on PATH
# Option A — conda:    conda install -c conda-forge poppler
# Option B — winget:   winget install --id oschwartz10612.Poppler  (community port)
# Option C — manual:   download https://github.com/oschwartz10612/poppler-windows/releases
#                      and add the `bin\` folder to PATH

streamlit run App/app.py
```

The sidebar **🔧 System status** expander shows live capability detection:

- **🖥️ Local Enhanced OCR (v2.43.2): available ✅** — all six heavy libs importable; the full check-linking pipeline is ready
- **🖥️ Local Enhanced OCR (v2.43.2): partial ⚠️ (missing X — fast path only, no check linking)** — only pdfplumber is installed; fast-path transactions still extract but the cropper / matcher stages are skipped
- **🖥️ Local Enhanced OCR (v2.43.2): unavailable** — pdfplumber is missing; the radio still works but auto-falls back to the Lightweight Parser with a `[WARN]` log in the Processing log expander

Production note: the F1 App Service (`slam-services-revenue-tracker`) only has `pdfplumber` installed — the Local Enhanced radio there will correctly report "missing libs" and fall back to the Lightweight Parser, so Laura's daily-driver workflow is **never disrupted** even if she accidentally selects it.

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

> **Tip (v2.44):** the steps below are the **Windows-native** workflow for Robert's existing dev machine. If you're spinning up a fresh dev environment — especially for the heavy Local Enhanced OCR pipeline — **GitHub Codespaces** ([§ Development with GitHub Codespaces](#development-with-github-codespaces-v244) above) is the faster and more reliable path: it skips the Python 3.10 install, the venv rebuild, the poppler binaries, and the PyTorch wheel resolution that frequently fail on fresh Windows machines.

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
- `Scripts/PowerShell/Deploy-ToAzure.ps1` — **Modern polling-safe deploy** (stop → async OneDeploy → poll → start → smoke test)
- `Scripts/PowerShell/Deploy-PostgresProduction.ps1` — Build + deploy helper (calls `Deploy-ToAzure.ps1`)
- `App/diagnostics.py` — Data freshness + system info for sidebar
- `App/app_logging.py` — Structured `slam_app` logs (Azure log stream)
- `Scripts/PowerShell/Set-AzurePostgresAppSettings.ps1` — Enable/disable Postgres settings
- `requirements.txt` — Python dependencies
- `.cursor/rules/slam-services.mdc` — Cursor primary project rules (`alwaysApply`)
- `.kilocode` — Shared agent principles (Cursor leads; Kilo secondary)
- `.vscode/` — Shared tasks, launch, lint/format settings
- `.devcontainer/devcontainer.json` — **GitHub Codespaces dev container** (Python 3.10 + heavy OCR libs)
- `.devcontainer/postCreateCommand.sh` — One-shot Codespaces provisioning (poppler, venv, OCR libs, EasyOCR pre-warm, aliases)
- `Data/Revenue_Tracker_Migration/` — Source data (local; not in git)

---

## Project Goals

- Reduce manual revenue chasing work for Laura and Stef
- Build visible, reliable automation
- Enable smooth handover to Patty & Robert
- Maintain high standards for security and data privacy

---

## Folder Structure
