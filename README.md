# SLAM Services Revenue Tracker

**Live Application**: [https://slam-services-revenue-tracker.azurewebsites.net/](https://slam-services-revenue-tracker.azurewebsites.net/)

**Purpose**: Operational backbone for SLAM Services LLC bookkeeping. Reduces manual revenue chasing, automates bank statement processing (with intelligent check linking and persistent payee rules), and provides real-time visibility into revenue requests and missing documentation. Built for Laura & Stef as daily drivers, with a clean handoff path to Patty & Robert.

**Single Source of Truth**: `SLAM Services - Digital Transformation Blueprint.md` (complete history, architecture decisions, and Change Log).

---

## Quick Start

### Recommended: GitHub Codespaces (for heavy OCR / Local Enhanced OCR work)

The heavy Local Enhanced OCR pipeline (EasyOCR + OpenCV check cropper + payee extraction) is painful to set up on a fresh Windows or macOS machine. Codespaces gives you a fully-provisioned Linux container in ~5 minutes.

1. GitHub repo → **Code** → **Codespaces** → **Create codespace on main** (prefer the 4-core/16 GB machine type).
2. Wait for the post-create script (poppler + `.venv` + heavy OCR libs + EasyOCR model pre-warm).
3. In the terminal:

   ```bash
   slam-run     # streamlit run App/app.py (port 8501 auto-forwarded)
   ```

4. Open the forwarded URL and log in with the password Robert provides.

See [docs/local-development.md](docs/local-development.md) for full Codespaces details, aliases (`slam-info`, `slam-lint`, etc.), and DPI tuning.

### Local Windows (light work or full OCR)

```powershell
cd C:\SLAM-Services-Project
.\Scripts\PowerShell\Setup-LocalVenv.ps1
.\.venv\Scripts\Activate.ps1
streamlit run App/app.py
```

For the **🖥️ Local Enhanced OCR (Robert only)** radio you also need the heavy libs + poppler (see [docs/local-development.md](docs/local-development.md)).

### Health checks

```powershell
python Scripts/health_check.py --full
.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure   # pre-UAT / post-deploy
```

---

## Current Status (May 27, 2026 — Blueprint v2.44.5)

- **Development environment**: GitHub Codespaces is now the recommended home for all heavy Local Enhanced OCR work (v2.44). The primary mirroring Codespace is `slam-v2-44-codespaces-migration`.
- **Bank Statements core workflow**: Upload PDF → Lightweight Parser / Local Enhanced OCR (Robert) / Azure OCR (parked) / paste Grok CSV → automated reconciliation → persistent payee rules engine (v2.39) with **💡 Learn this mapping** → Mark as Received.
- **G1 Hybrid CV Check Leg spike (Phases 0–7)**: Complete and isolated under `Scripts/spike/`. Strong results (7× clean-payee improvement on the hardest PDF). Owner decision B1 (Traditions-first integration sprint) approved. Feature-flagged; EasyOCR strict path remains the production default.
- **Azure OCR Function**: `slam-ocr-function` (Y1 Consumption) exists but is parked on the v2.41 skeleton pending infra decision. The full v2.43/v2.44.3 intelligent check-linking pipeline is available locally via the in-process `App/local_enhanced_ocr.py`.
- **Production PostgreSQL**: Provisioned and migrated; CSV mode remains the zero-disruption fallback.
- **Daily driver (Laura/Stef)**: Dashboard, Revenue Requests, Bank Statements, quick views, payee rules, and UAT stabilization all live on the F1 App Service.
- **Full history**: See the Blueprint Change Log (v2.30 → v2.44.5) for every architectural decision, spike, and hygiene pass.

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
| `README.md` | Humans (onboarding + daily reference) + agents (cross-reference) | **Practical human onboarding, current status snapshot, command reference, and the single authoritative "Documentation Roles & Agent Workflow" guide**. The one place anyone looks first to understand how to work with the project and where information lives. | Current status banner, Quick Start, Codespaces/local/Azure health recipes (entry points), this Documentation Roles Matrix, folder structure, project goals. Detailed procedural guides live in `docs/`. | Long historical narrative (belongs in Blueprint), hard agent prompt constraints (belong in the two injected contracts). |
| `.cursor/rules/slam-services.mdc` | Cursor (Composer / Agent / inline edit) — **always injected** | **Lean, self-contained primary agent contract**. Contains only the non-negotiable rules that must be in Cursor's context window on every invocation. | Agent role declaration (Cursor lead), reference to Blueprint + README, the two core standing orders (anti-bloat/role-respect + git via thorough confirmation), security/Laura-confidence, verification habits, tech stack pointers, one-sentence pointer to this matrix. | Long explanations, history, commands, the full matrix (pointer only). Must stay minimal. |
| `.grok/AGENT.md` | Grok 4.3 (this TUI and other Grok-assisted sessions) — **secondary agent** | **Official Grok secondary agent context** (canonical location). Carries the same hard constraints as the Cursor contract so Grok sessions stay consistent with project rules. | Same two core standing orders (anti-bloat + git confirmation), updated "Cursor primary + Grok secondary" reality, pointer to this matrix. Short and focused. | Anything that duplicates the Cursor contract or the human docs. |

### Key Files

- `CONSTITUTION.md` — Layer 0 immutable goals and agent operating model (read first).
- `SLAM Services - Digital Transformation Blueprint.md` — Living SSOT + full Change Log.
- `App/app.py` — Streamlit application (Dashboard, Revenue Requests, Bank Statements pages).
- `App/local_enhanced_ocr.py` — v2.44.3 in-process port of the intelligent check-linking pipeline.
- `Scripts/health_check.py`, `Scripts/init_db.py`, `Scripts/migrate_to_postgres.py` — Postgres lifecycle.
- `Scripts/PowerShell/Deploy-ToAzure.ps1` + `Build-AzureDeployZip.ps1` — modern safe deploy path.
- `.devcontainer/` — GitHub Codespaces definition (devcontainer.json + 7-stage postCreateCommand.sh).
- `docs/deployment.md`, `docs/local-development.md`, `docs/codespaces-connection-recipe.md`, and `docs/proposed-state-alignment-process.md` — detailed operational recipes and future-process proposals.
- `.cursor/rules/slam-services.mdc` and `.grok/AGENT.md` — the two thin agent contracts.
- `Data/Revenue_Tracker_Migration/` — source CSVs (local only; never committed).

**Legacy note**: `.kilocode/` and `Export-KiloCode-Output` are retired (Kilo Code era). See Blueprint v2.44.2 for the transition.

---

## Folder Structure

```
.
├── .devcontainer/                 # GitHub Codespaces (Python 3.10 + full OCR stack)
│   ├── devcontainer.json
│   ├── Dockerfile
│   └── postCreateCommand.sh       # 7-stage provisioner (poppler, venv, heavy libs, aliases)
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
│   ├── local-development.md       # Codespaces, local venv, Postgres dev workflow
│   ├── codespaces-connection-recipe.md  # How to reliably connect agents to the primary heavy-OCR Codespace
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

- [docs/local-development.md](docs/local-development.md) — Codespaces setup, local venv, Local Enhanced OCR one-time install, PostgreSQL round-trip testing, health commands.
- [docs/deployment.md](docs/deployment.md) — Modern `Deploy-ToAzure.ps1` path, manual steps, GitHub Actions, Kudu data uploads, full `RemoteDisconnected` recovery runbook, important App Settings.
- [docs/codespaces-connection-recipe.md](docs/codespaces-connection-recipe.md) — Reliable agent connection recipe for the primary heavy-OCR Codespace (`slam-v2-44-codespaces-migration`).
- [docs/proposed-state-alignment-process.md](docs/proposed-state-alignment-process.md) — Minimal template for the future proactive state-driven documentation/feature alignment system (logged as future work in Blueprint).

All long-form historical narrative, architecture rationale, and detailed decision records live in the **Blueprint**.

---

*This README is deliberately concise. Its job is to get a human (or agent) oriented in under two minutes and to serve as the canonical home of the Documentation Roles Matrix. Everything else has a defined home.*