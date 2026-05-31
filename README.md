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

## Current Status (June 2026 — v2.45.3)

- **Laura/Stef pilot active (Path A)**; Gate A3 HCC PASS; **Auto Body withdrawal residual OPEN** (Δ $273.45 vs gold — see re-smoke run file below).
- **Deploy discipline:** after every `Deploy-ToAzure.ps1`, run Gate A3 headless smoke + evidence collection — see [`docs/deployment.md`](docs/deployment.md) (or `-RunGateA3Smoke`).
- **v2.45.3 deploy** (`1dfb6b3f`): v2.45.2 tightening live on Azure; re-smoke evidence in [`QMS/State-Alignment/runs/2026-05-31-v2453-deploy-resmoke.md`](QMS/State-Alignment/runs/2026-05-31-v2453-deploy-resmoke.md).

### Production (Azure App Service — DI-only)

- **Bank Statements**: **Azure Document Intelligence only** when `AZURE_DI_*` App Settings are set. `App/app.py` hardcodes `run_mode = "azure_ocr"` and stops with a clear error if Azure DI is not configured — no processing-mode radios, no Local Enhanced path, no lightweight-parser fallback on the live UI.
- **DI pipeline**: Two-leg path in `App/bank_statements.py` + `App/azure_document_intelligence.py` — register via `prebuilt-bankStatement.us`, imaging via geometric cropper v5 + `prebuilt-check.us` per crop. Enablement: `Scripts/PowerShell/Set-AzureBankStatementDIAppSettings.ps1`; runbook: `docs/DI-Go-Live-Commands.md`, `docs/go-live-execution-runbook.md`.
- **Gate A3 (check/imaging leg)**: **HCC PASS; Auto Body withdrawals NEEDS WORK** (production re-smoke 2026-05-31, deploy `1dfb6b3f`). HCC: 98 rows, gold totals, 42 crops, `payee_rules_applied` 6. Auto Body: **94 rows**, deposits **$41,786.80** (gold match), withdrawals **$41,130.18** vs gold **$41,403.63** (50 supplemental, 56 crops, `payee_rules_applied` 3). Headless smoke: `Invoke-GateA3HeadlessSmoke.ps1` then `Collect-GateA3Evidence.ps1 -Both -UpdateDocs`. Detail: [`QMS/State-Alignment/runs/2026-05-31-v2453-deploy-resmoke.md`](QMS/State-Alignment/runs/2026-05-31-v2453-deploy-resmoke.md).
- **Data layer**: Azure PostgreSQL (`USE_POSTGRES=true`); canonical schema in `db/schema.sql` and `docs/data-model.md`.
- **Daily driver (Laura/Stef)**: Dashboard, Revenue Requests, Bank Statements, payee rules on App Service (B2). QMS visibility in sidebar + `health_check.py --qms` (O-002, v2.44.21).

### Local Enhanced (Robert's Windows machine only)

- **Heavy OCR + hybrid CV**: `App/local_enhanced_ocr.py` — full intelligent check-linking pipeline, Azure CV Read on check crops when `AZURE_CV_*` or `SLAM_CV_CACHE_DIR` in `.env`. Install via `Setup-LocalVenv.ps1 -InstallHeavyOcr` / `Install-LocalHeavyOcr.ps1`. **Not wired into production Streamlit UI.**
- **G1 spike artifacts**: Phases 0–7 complete — canonical index [`Scripts/spike/README.md`](Scripts/spike/README.md) (v2.44.27).

### Parked / fallback

- **Azure OCR Function** (`slam-ocr-function`): parked; not the production path.
- **CSV mode**: zero-disruption fallback when Postgres is disabled (requires server-side CSVs — not for daily driver).

**Full history**: Blueprint Change Log (v2.30 → **v2.45.0**). State Alignment process: [`QMS/State-Alignment/process.md`](QMS/State-Alignment/process.md) (active since v2.44.9).

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
| `.cursor/rules/slam-services.mdc` | Cursor (Composer / Agent / inline edit) — **always injected** | **Lean, self-contained primary agent contract**. Contains only the non-negotiable rules that must be in Cursor's context window on every invocation. | Agent role declaration (Cursor lead), reference to Blueprint + README, the two core standing orders (anti-bloat/role-respect + git via canonical `Invoke-GitVerification.ps1` + Prime Directive alignment for dual-agent), security/Laura-confidence, verification habits, tech stack pointers, one-sentence pointer to this matrix. | Long explanations, history, commands, the full matrix (pointer only). Must stay minimal. |
| `.grok/AGENT.md` | Grok 4.3 (this TUI and other Grok-assisted sessions) — **secondary agent** | **Official Grok secondary agent context** (canonical location). Carries the same hard constraints as the Cursor contract so Grok sessions stay consistent with project rules. | Same two core standing orders (anti-bloat + git via canonical `Invoke-GitVerification.ps1` + Prime Directive alignment), updated "Cursor primary + Grok secondary" reality, pointer to this matrix. Short and focused. | Anything that duplicates the Cursor contract or the human docs. |

### Key Files

- `CONSTITUTION.md` — Layer 0 immutable goals and agent operating model (read first).
- `SLAM Services - Digital Transformation Blueprint.md` — Living SSOT + full Change Log.
- `App/app.py` — Streamlit application (Dashboard, Revenue Requests, Bank Statements pages).
- `App/local_enhanced_ocr.py` — v2.44.3 in-process port of the intelligent check-linking pipeline.
- `Scripts/health_check.py`, `Scripts/init_db.py`, `Scripts/migrate_to_postgres.py` — Postgres lifecycle.
- `Scripts/PowerShell/Deploy-ToAzure.ps1` + `Build-AzureDeployZip.ps1` — modern safe deploy path.
- `Scripts/PowerShell/Set-AzureBankStatementDIAppSettings.ps1` — one-command production enablement for the Azure Document Intelligence bank statement pipeline (post-2026 go-live).
- `db/schema.sql` — canonical, production-grade definition of the current live Postgres schema (clients + revenue_requests with the bank/sales received flags).
- `docs/deployment.md`, `docs/DI-Go-Live-Commands.md`, `docs/local-development.md`, and [`QMS/State-Alignment/process.md`](QMS/State-Alignment/process.md) — operational recipes, go-live sequence, and active State Alignment process.
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
│   └── (State Alignment: QMS/State-Alignment/process.md — active)
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
- [QMS/State-Alignment/process.md](QMS/State-Alignment/process.md) — Active State Alignment process (QMS continual improvement; superseded `docs/proposed-state-alignment-process.md`).

All long-form historical narrative, architecture rationale, and detailed decision records live in the **Blueprint**.

---

*This README is deliberately concise. Its job is to get a human (or agent) oriented in under two minutes and to serve as the canonical home of the Documentation Roles Matrix. Everything else has a defined home.*