# Azure App Service Rename — Ready-to-Paste Cursor Prompt + Runbook

**Purpose**: This document contains (1) a complete, high-signal prompt you can copy verbatim into Cursor (the primary agent), and (2) the permanent runbook that Cursor will be instructed to produce.

**Owner decision (2026 DI go-live review)**: The current name `slam-services-revenue-tracker` is misleading. The App Service hosts the full SLAM Services platform. Rename it to a durable, accurate name (`slam-services` or `slam-services-app` recommended).

**When to use this prompt**: After the DI settings are live and stable (or in the same production-hardening window as the schema work). It is deliberately **not** a blocker for the DI pipeline itself.

---

## The Prompt (copy everything below the line)

```
You are Cursor (primary agent) working on the SLAM Services project in C:\slam-services-project.

The owner has directed that the production Azure App Service (currently named `slam-services-revenue-tracker`) must be renamed because the name only reflects one feature. The application is now the full operational platform for SLAM Services (Revenue Requests + Bank Statements with the new Azure Document Intelligence two-leg pipeline + future modules).

Target new name (confirm with owner at start): `slam-services` (preferred) or `slam-services-app`. Use the exact final name the owner confirms.

CRITICAL AZURE CONSTRAINTS (you must respect these exactly):
- Azure App Service names are IMMUTABLE for the public *.azurewebsites.net hostname. There is no `az webapp update --name` that changes the public URL.
- The current live URL is https://slam-services-revenue-tracker.azurewebsites.net/ and is referenced in many places.
- We must achieve zero (or near-zero) downtime for Laura's daily driver.

SAFE PRODUCTION RENAME STRATEGY (execute in this exact order unless owner approves a shortcut):

1. Discovery (read-only first pass)
   - Use grep + rg to find EVERY hard-coded reference to `slam-services-revenue-tracker` (and the old URL) across the entire repo (exclude .git, __pycache__, docs-backups, node_modules, *.zip, *.csv, *.pdf).
   - Produce a clean table: File | Line | Context (the string and surrounding 1 line).
   - Also check the GitHub secret name usage and any Kudu / Advanced Tools notes in docs.

2. Pre-flight validation (local + Azure)
   - Confirm you are logged in: `az account show`.
   - Confirm the current App Service exists and is healthy.
   - Confirm the App Service Plan (F1 or B1) name and location.
   - Confirm RBAC on SLAM-Services-RG is sufficient for webapp create + config.

3. Create the new App Service (exact replica)
   - Create a new App Service with the chosen name in the **same** Resource Group and **same** App Service Plan.
   - Immediately copy **all** current App Settings from the old app (including the DI keys we just set in the go-live, SLAM_APP_PASSWORD, Postgres creds, etc.).
   - Copy any connection strings, appCommandLine, startup command, etc.
   - Do **not** enable "always on" or change SKU yet — keep parity with the old F1 (or the B1 if it was upgraded).

4. Deploy code to the new app (zero-drift)
   - Use the existing modern deploy path or a temporary publish profile.
   - Prefer the same GitHub Action pattern (clean:false) once the publish profile secret is updated.
   - Verify that `startup.sh`, requirements, App/, Scripts/ all land correctly.
   - After deploy, run the equivalent of `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full` against the **new** hostname.

5. Update the repository (mandatory git verification before every commit)
   - For every file discovered in step 1, perform the rename of the old name/URL to the new name.
   - Also update the GitHub Actions workflow (the AZURE_WEBAPP_NAME variable and any comments).
   - Update the PowerShell default parameter values in all Set-*, Deploy-*, Check-* scripts.
   - Update README.md live URL, docs/deployment.md (multiple places), health scripts, any other docs.
   - Produce a short `docs/app-service-rename-runbook.md` (or update the one in this prompt) that becomes the permanent record.
   - Before any git commit, run the canonical verifier (single source, Prime Directive aligned):
        .\Scripts\PowerShell\Invoke-GitVerification.ps1
        (plus any app-service-rename-specific name scan + ruff if Python touched)
   - Commit message must reference the 2026 DI go-live context and the rename decision.

6. GitHub secret rotation
   - In the GitHub repo settings, update (or add) the `AZUREAPPSERVICEPUBLISHPROFILE` secret with the publish profile of the **new** app.
   - Document the exact steps the owner must perform in the Portal (Get publish profile on the new app).
   - If the old secret name is reused, note the timing of the GitHub Action re-run.

7. Traffic cut-over & validation (with owner)
   - Keep the old app running as a hot standby for at least 7–14 days.
   - Update any team bookmarks / shared links to the new URL.
   - Run a full Laura + team smoke session on the new hostname (login, Revenue Requests, Bank Statements with real DI processing, save, health sidebar).
   - Monitor Azure Log Stream + Application Insights on the new app for 48h.
   - Only after owner sign-off: begin decommissioning the old resource (after a final backup of its App Settings and any Kudu console artifacts).

8. Rollback (pre-planned, one-command where possible)
   - DNS / bookmark level: point back to the old URL (still live).
   - GitHub secret: revert to the old publish profile.
   - If any data divergence occurred (extremely unlikely), the CSV fallback + Postgres are the ultimate source of truth.
   - The old app name remains in the repo history; we simply stop using it.

9. Documentation & handoff
   - The runbook you produce must be clear enough that Patty or Robert can repeat the process in 2027 if another rename is ever needed.
   - Update the "Live Application" line in README.md as the very last step before the final commit of the rename series.

NON-NEGOTIABLES (you must obey):
- Laura's confidence and zero daily-driver disruption are more important than a clean name.
- Never delete the old App Service until the owner explicitly approves after the observation window.
- Every file change must pass the project's git verification sequence before commit.
- You are Cursor (primary). If you need Grok for review of the prompt or runbook, you may ask, but you own the execution.
- Anti-bloat: do not create unnecessary new scripts or abstractions just because we are renaming.

Start by:
a) Confirming the exact target name with the owner in this session.
b) Running the discovery grep and showing the full table of references.
c) Producing the first draft of `docs/app-service-rename-runbook.md` (or the permanent location the owner prefers) that the rest of the work will follow.

When you are finished, the repo + Azure reality must match, the new URL must be the only one documented as "live", the old app is a documented hot standby, and a future engineer can understand exactly what happened and why.

Begin.
```

---

## Permanent Rename Runbook (what Cursor will produce)

After the Cursor session using the prompt above, the following file (or an equivalent in `docs/`) will exist and be the authoritative record:

`docs/app-service-rename-runbook.md`

It will contain (at minimum):
- Date of the rename
- Old name → new name
- Exact Azure CLI commands that were used (with resource IDs redacted for security)
- Complete before/after list of every file changed
- The GitHub secret rotation steps the owner performed
- The 7–14 day observation checklist that was signed off
- Rollback instructions (even if no longer needed)
- Link to the Blueprint Change Log entry

This runbook + the schema work + the DI setter together represent the "production hardened" state after the 2026 go-live.

---

**End of prompt + runbook package**
