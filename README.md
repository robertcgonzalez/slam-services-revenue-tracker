# SLAM Services Revenue Tracker

**Live Application**: [https://slam-services-revenue-tracker.azurewebsites.net/](https://slam-services-revenue-tracker.azurewebsites.net/)

**Purpose**: Operational backbone for SLAM Services LLC bookkeeping. Reduces manual revenue chasing, automates bank statement processing (with intelligent check linking and persistent payee rules), and provides real-time visibility into revenue requests and missing documentation. Built for Laura & Stef as daily drivers, with a clean handoff path to Patty & Robert.

**Single Source of Truth**: `SLAM Services - Digital Transformation Blueprint.md` (complete history, architecture decisions, and Change Log).

---

## Quick Start

### Local Windows (primary)

All development and testing runs on your machine. There is no Docker or GitHub Codespaces dev-container path in this repo.

**Prerequisites**: Python 3.10 (`py -3.10`), Git, and [poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases) (`pdftoppm` on PATH).

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Setup-LocalVenv.ps1 -InstallHeavyOcr
copy Scripts\spike\cv-read.env.sample .env   # edit AZURE_CV_* or SLAM_CV_CACHE_DIR
.\run_local.ps1
```

Open http://localhost:8501. For heavy OCR only after the base venv exists:

```powershell
.\Scripts\PowerShell\Install-LocalHeavyOcr.ps1
```

Full guide: [docs/local-development.md](docs/local-development.md). Environment policy: [docs/environment-policy.md](docs/environment-policy.md).

### Health checks

```powershell
python Scripts/health_check.py --full
.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure   # pre-UAT / post-deploy
```

---

## Current Status (June 2026 — Post DI Go-Live)

- **Development environment**: Local Windows only (including heavy OCR and Azure CV). No Docker/Codespaces dev container in repo.
- **Azure Document Intelligence Bank Statements (2026 go-live)**: The two-leg DI pipeline (`prebuilt-bankStatement.us` + geometric cropper v5 + `prebuilt-check.us` per imaging crop) is now the primary production engine for Bank Statements when the App Service settings are configured. See `docs/DI-Go-Live-Commands.md`, the new `Scripts/PowerShell/Set-AzureBankStatementDIAppSettings.ps1`, and the approved plan in the Grok session notes. The old Azure OCR Function remains parked. Grok Vision paste and lightweight parser stay as zero-risk fallbacks.
- **Production schema captured**: `db/schema.sql` is the new canonical, heavily commented definition of the live Postgres tables (`clients` + `revenue_requests` with the `bank_statement_received` / `sales_report_received` flags). `docs/data-model.md` now clearly separates "Current Implemented" from future aspirational entities.
- **G1 Sprint 3.4 (v2.44.13)**: CV round-trip complete — hybrid payees drive the final transaction table; see `Documents/cursor_g1_sprint_3_4_pipeline_finalization.md`.
- **G1 Sprint 3.4+ (v2.44.14)**: Bank Statements has no processing-mode radio — the app auto-runs the richest pipeline. Azure CV is the **only** reader for cropped check/deposit images (no EasyOCR on crops).
- **G1 Sprint 3.2**: Hybrid CV check leg wired in `App/local_enhanced_ocr.py`. Validate on local Windows.
- **Bank Statements core workflow**: Upload PDF → Azure Document Intelligence (primary when configured) / Lightweight Parser / Local Enhanced OCR (Robert) / paste Grok CSV → automated reconciliation → persistent payee rules engine (v2.39) with **💡 Learn this mapping** → Mark as Received.
- **G1 Hybrid CV Check Leg spike (Phases 0–7)**: Complete and isolated under `Scripts/spike/`. Strong results (7× clean-payee improvement on the hardest PDF). Owner decision B1 (Traditions-first integration sprint) approved. Feature-flagged; EasyOCR strict path remains the production default.
- **Azure OCR Function**: `slam-ocr-function` (Y1 Consumption) exists but is parked on the v2.41 skeleton pending infra decision. The full v2.43/v2.44.3 intelligent check-linking pipeline is available locally via the in-process `App/local_enhanced_ocr.py`.
- **Production PostgreSQL**: Provisioned, migrated, and now has an explicit canonical schema definition (`db/schema.sql`). CSV mode remains the zero-disruption fallback.
- **Daily driver (Laura/Stef)**: Dashboard, Revenue Requests, Bank Statements, quick views, payee rules, and UAT stabilization all live on the F1 App Service.
- **Full history**: See the Blueprint Change Log (v2.30 → v2.44.19+) for every architectural decision, spike, and hygiene pass.

---

## Azure CV on check photos (Local Enhanced)

**Local Enhanced OCR** uses Azure Computer Vision Read on imaging-page check crops when `AZURE_CV_ENDPOINT` + `AZURE_CV_KEY` or `SLAM_CV_CACHE_DIR` are set in `.env` (see `Scripts/spike/cv-read.env.sample`). That is the **only** automated reader for crop images — EasyOCR is used for full-page tabular fallback only, never on individual check crops. Without CV creds or cache, crops are still produced for review but payee intelligence from photos is skipped.

---

## Documentation & Agent Workflow

**Cursor** is the **primary / lead** AI coding agent. **Grok** is the official **secondary** agent. Both follow the same rules.

When starting any agent session (Cursor or Grok), begin with:

> "Read CONSTITUTION.md first. Then reference the full SLAM Services Digital Transformation Blueprint.md (latest version) and this README.md. [Your request]"

### Documentation Roles Matrix

This is the **single authoritative map** of every document’s defined purpose. Content must live in exactly one place.

| Document | Primary Consumer | Defined Role & Purpose | What Belongs Here (and only here) | What Does **Not** Belong Here |
|----------|------------------|------------------------|-----------------------------------|-------------------------------|
| `SLAM Services - Digital Transformation Blueprint.md` | Humans + agents (deep reference) | **Living Single Source of Truth + complete project history**. The authoritative record of vision, architecture, decisions, roadmap, SDLC, and all major milestones. | Full Change Log (narrative history), executive summary, phased roadmap, technical architecture, stakeholder map, risk/decision logs, Section 14 feedback system, detailed "why" behind every significant change. | Day-to-day commands, quick-start recipes, injected agent constraints (keep thin), the "map" of which doc does what. |
| `README.md` | Humans (onboarding + daily reference) + agents (cross-reference) | **Practical human onboarding, current status snapshot, command reference, and the single authoritative "Documentation Roles & Agent Workflow" guide**. The one place anyone looks first to understand how to work with the project and where information lives. | Current status banner, Quick Start, local/Azure health recipes (entry points), this Documentation Roles Matrix, folder structure, project goals. Detailed procedural guides live in `docs/`. | Long historical narrative (belongs in Blueprint), hard agent prompt constraints (belong in the two injected contracts). |
| `.cursor/rules/slam-services.mdc` | Cursor (Composer / Agent / inline edit) — **always injected** | **Lean, self-contained primary agent contract**. Contains only the non-negotiable rules that must be in Cursor's context window on every invocation. | Agent role declaration (Cursor lead), reference to Blueprint + README, the two core standing orders (anti-bloat/role-respect + git via thorough confirmation), security/Laura-confidence, verification habits, tech stack pointers, one-sentence pointer to this matrix. | Long explanations, history, commands, the full matrix (pointer only). Must stay minimal. |
| `.grok/AGENT.md` | Grok 4.3 (this TUI and other Grok-assisted sessions) — **secondary agent** | **Official Grok secondary agent context** (canonical location). Carries the same hard constraints as the Cursor contract so Grok sessions stay consistent with project rules. | Same two core standing orders (anti-bloat + git confirmation), updated "Cursor primary + Grok secondary" reality, pointer to this matrix. Short and focused. | Anything that duplicates the Cursor contract or the human docs. |

### Key Files

- `CONSTITUTION.md` — Layer 0 immutable goals and agent operating model (read first).
- `SLAM Services - Digital Transformation Blueprint.md` — Living SSOT + full Change Log.
- `App/app.py` — Streamlit application (Dashboard, Revenue Requests, Bank Statements pages).
- `App/local_enhanced_ocr.py` — v2.44.3 in-process port of the intelligent check-linking pipeline.
- `Scripts/health_check.py`, `Scripts/init_db.py`, `Scripts/migrate_to_postgres.py` — Postgres lifecycle.
- `Scripts/PowerShell/Deploy-ToAzure.ps1` + `Build-AzureDeployZip.ps1` — modern safe deploy path.
- `Scripts/PowerShell/Set-AzureBankStatementDIAppSettings.ps1` — one-command production enablement for the Azure Document Intelligence bank statement pipeline (post-2026 go-live).
- `db/schema.sql` — canonical, production-grade definition of the current live Postgres schema (clients + revenue_requests with the bank/sales received flags).
- `docs/deployment.md`, `docs/DI-Go-Live-Commands.md`, `docs/local-development.md`, and `docs/proposed-state-alignment-process.md` — detailed operational recipes, the exact go-live command sequence, and future-process proposals.
- `.cursor/rules/slam-services.mdc` and `.grok/AGENT.md` — the two thin agent contracts.
- `Data/Revenue_Tracker_Migration/` — source CSVs (local only; never committed).

**Legacy note**: `.kilocode/` and `Export-KiloCode-Output` are retired (Kilo Code era). See Blueprint v2.44.2 for the transition.

---

## Folder Structure

```
.
├── .github/workflows/
│   └── deploy-azure.yml           # Active GitHub Actions deploy (clean: false)
├── .vscode/                       # Shared team settings (committed)
├── App/                           # Streamlit application
│   ├── app.py
│   ├── bank_statements.py         # Parser + rules engine + OCR orchestration
│   ├── local_enhanced_ocr.py      # v2.44.3 in-process heavy pipeline (Robert only)
│   ├── db_utils.py
│   ├── diagnostics.py
│   └── payee_extractor/           # G1 profile-driven payee scoring (spike)
├── AzureFunctions/
│   └── ocr_processor/             # Azure Function (v2.43 pipeline, currently parked)
├── Data/                          # Client data (gitignored)
│   └── Revenue_Tracker_Migration/ # Source of truth CSVs for CSV mode
├── Scripts/
│   ├── PowerShell/                # Deploy, health, Postgres sync, venv helpers
│   │   ├── Deploy-ToAzure.ps1     # Modern polling-safe deploy orchestrator
│   │   ├── Check-AppHealth.ps1
│   │   └── ...
│   ├── health_check.py
│   ├── init_db.py
│   ├── migrate_to_postgres.py
│   ├── bank-statement-parser.py
│   └── spike/                     # G1 Azure CV Read exploratory work (Phases 0–7)
│       ├── artifacts/             # Large diagnostic outputs (gitignored patterns)
│       └── POST_SPIKE_INTEGRATION_PLAN.md
├── docs/                          # Detailed operational guides (extracted from old README)
│   ├── deployment.md              # All Azure deploy paths + recovery runbooks
│   ├── local-development.md       # Local venv, Postgres dev workflow
│   └── proposed-state-alignment-process.md  # Lightweight future template for proactive doc/feature gap reviews (not yet active)
├── CONSTITUTION.md
├── README.md                      # You are here (onboarding + roles matrix)
├── SLAM Services - Digital Transformation Blueprint.md
├── requirements.txt
├── runtime.txt
├── startup.sh
└── pyproject.toml                 # Ruff + Black config (Python 3.10 target)
```

**What is intentionally not shown**:
- `__pycache__/`, `*.pyc`, `.venv/`, `node_modules/`, `docs-backups/`, `Export-KiloCode-Output/`
- `Scripts/spike/artifacts/` (thousands of PNG/JSON diagnostic files — summarized in the spike docs)
- All `*.csv`, `*.pdf`, `*.zip` (client data or build artifacts — gitignored)

---

## Project Goals

- Reduce manual revenue chasing work for Laura and Stef
- Build visible, reliable automation (especially bank statement → payee → revenue request flow)
- Enable smooth, low-risk handover to Patty & Robert
- Maintain absolute standards for security, data privacy, and Laura’s confidence

---

## Deep Guides

- [docs/local-development.md](docs/local-development.md) — Local venv, Local Enhanced OCR one-time install, PostgreSQL round-trip testing, health commands.
- [docs/deployment.md](docs/deployment.md) — Modern `Deploy-ToAzure.ps1` path, manual steps, GitHub Actions, Kudu data uploads, full `RemoteDisconnected` recovery runbook, important App Settings.
- [docs/proposed-state-alignment-process.md](docs/proposed-state-alignment-process.md) — Minimal template for the future proactive state-driven documentation/feature alignment system (logged as future work in Blueprint).

All long-form historical narrative, architecture rationale, and detailed decision records live in the **Blueprint**.

---

*This README is deliberately concise. Its job is to get a human (or agent) oriented in under two minutes and to serve as the canonical home of the Documentation Roles Matrix. Everything else has a defined home.*