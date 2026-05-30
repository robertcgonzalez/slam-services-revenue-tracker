# Development Environment Policy

**Last updated**: 2026-05-28

## Official policy

**Local Windows** is the primary and supported environment for all work, including:

- Streamlit app (Dashboard, Revenue Requests, Bank Statements)
- Local Enhanced OCR (`App/local_enhanced_ocr.py`)
- Hybrid Azure CV check leg (`App/hybrid_cv_check_leg.py`)
- PostgreSQL round-trip testing

**Docker** is not used for local development.

**GitHub Codespaces** and **dev containers** (`.devcontainer/`, `.devcontainers/`) are **permanently unsupported and actively blocked**. The entire devcontainer definition, Docker assets, and all Codespaces onboarding scripts/recipes were purged from the repo (see commit history for v2.44.16 final removal). 

.gitignore contains a hardened permanent block. Any reappearance of these files on disk (even from Cursor "Add Dev Container Configuration" command) must be deleted immediately. Re-introduction requires explicit owner approval and a Constitution change — this is a hard boundary.

## Setup path

1. `.\Scripts\PowerShell\Setup-LocalVenv.ps1` (add `-InstallHeavyOcr` for the full OCR stack)
2. Copy `Scripts\spike\cv-read.env.sample` → `.env` (gitignored)
3. `.\run_local.ps1` (loads `.env`, sets `PYTHONPATH`, checks poppler)

## Rules for agents

- Default to **local Windows** instructions (PowerShell, `run_local.ps1`, `.env`).
- Do not require or document Codespaces, Docker, or remote dev-container connections for validation or testing.
- Repo-root `.env` is loaded by `run_local.ps1` (PowerShell parse + preflight `load_dotenv`) and by `App/bank_statements.py` on import (`load_dotenv` at module init). `App/app.py` does not load `.env` directly.
