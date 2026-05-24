# SLAM Services Grok Projects Workspace

**Purpose**  
This is the central workspace for the **SLAM Services Digital Transformation Project**.

It contains all project assets, documentation, data, scripts, and the deployed Streamlit application.

---

## 📌 Current Status (as of May 24, 2026 — Blueprint v2.25)

- **Phase 1** — Revenue Reporting Tracker: **Complete**
- **Phase 2** — Secure Azure Deployment: **Complete** (F1 tier)
- **Phase 2.5** — Stabilization (P0–P2): **Complete in app**; deploy via GitHub Actions (`AZUREAPPSERVICEPUBLISHPROFILE` secret) or manual zip
- **Status**: Live on Azure. CI deploy pipeline hardened; confirm production after next successful deploy.

**Live Application**:  
→ [http://slam-services-revenue-tracker.azurewebsites.net/](http://slam-services-revenue-tracker.azurewebsites.net/)

**Single Source of Truth**:  
**`SLAM Services - Digital Transformation Blueprint.md`**

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
