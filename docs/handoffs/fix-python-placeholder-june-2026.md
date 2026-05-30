# Handoff — Fix Default Python Placeholder Page (Current Deployment)

> **SUPERSEDED (2026-05-30):** This handoff assumed `Deploy-ToAzure.ps1` should **not** set `appCommandLine`. Gate A3 work restored the canonical policy: production requires **`appCommandLine = ./startup.sh`** when Oryx compresses the build. See **`docs/deployment.md`** (Managing the Azure Startup Command). Recovery: `Set-AzureStartupCommand.ps1` or redeploy via `Deploy-ToAzure.ps1` — not clear-to-empty.

**Date**: 2026-06 (current session)  
**Symptom**: Live site `slam-services-revenue-tracker.azurewebsites.net` shows the classic Azure "Hey, Python developers!" placeholder page with the cartoon illustration instead of the SLAM Revenue Tracker Streamlit UI.  
**Target**: Cursor (primary driver via dual-agent orchestrator)  
**Source**: Grok analysis + recent edit to the deploy script

---

## Diagnosis (Authoritative)

The placeholder page appears when Oryx does not find a working startup mechanism for the Python app.

Root cause in this session:
- `Scripts/PowerShell/Deploy-ToAzure.ps1` contained logic that forcibly set `appCommandLine` (Startup Command) to `./startup.sh` on every deploy.
- Setting this at the platform level can cause Oryx to bypass or mishandle the project's `startup.sh` (which contains the correct `streamlit run App/app.py` + health checks + poppler handling).
- Even after a deploy, if the platform setting is present (or stale), the real app never starts and Oryx falls back to its default Python welcome page.

**Good news**: The forcing logic has already been removed from `Deploy-ToAzure.ps1` in this session (the "Ensuring Startup Command..." block and related section were deleted, and the top-level description was updated).

The remaining work is operational cleanup + redeploy + verification.

---

## Goal for This Handoff

Drive the live site from the default Python placeholder page to serving the real Streamlit Revenue Tracker application (expecting 401 Easy Auth or the login/dashboard UI).

## Exact Work Cursor Must Drive

1. **Clear any polluting platform startup command on the live app**
   - Use the existing, tested script: `.\Scripts\PowerShell\Clear-AzureStartupCommand.ps1`
   - This uses the reliable REST PATCH method (proven in prior 2026 incidents) + recycle + smoke test.
   - Verify `appCommandLine` is now empty after the run.

2. **Rebuild the deployment package with the fixed script**
   - Run: `.\Scripts\PowerShell\Build-AzureDeployZip.ps1`

3. **Deploy using the corrected flow**
   - Run: `.\Scripts\PowerShell\Deploy-ToAzure.ps1`
   - The deploy script must no longer touch `appCommandLine`.

4. **Validate success on the live URL**
   - After the deploy + container recycle, wait for cold start (60–120s on F1 is normal for this app).
   - Confirm the browser no longer shows the "Hey, Python developers!" placeholder or cartoon.
   - Expected healthy response: HTTP 401 (Easy Auth login redirect) or 2xx with actual Revenue Tracker content.
   - Run the project health checker: `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure`

5. **If still not correct**
   - Inspect logs: `az webapp log tail -g SLAM-Services-RG -n slam-services-revenue-tracker`
   - Confirm `startup.sh` is present at the root of `/home/site/wwwroot` after the deploy.
   - Re-run the clear script + redeploy if needed.
   - Report exact HTTP status codes and key log lines.

## Constraints (Non-Negotiable)

- Cursor drives execution. Use the existing PowerShell scripts — do not invent new deploy mechanisms.
- Production safety: preserve `Data/` on the server (the scripts already use `clean: false` by default).
- MVP/operational focus: get the real app live and verifiable. No unrelated refactors.
- Follow the patterns from the successful May/June 2026 Azure startup recoveries (documented in this `docs/handoffs/` folder).

## Success Criteria for This Phase

- `appCommandLine` on the App Service is empty (or explicitly set to a value that lets `startup.sh` win).
- Live URL returns 401 or serves real Streamlit content (no Python placeholder page).
- `Check-AppHealth.ps1 -Full -CheckAzure` reports healthy.
- Clear before/after evidence (CLI output, HTTP codes, log excerpts).

When complete, end with:  
**"HANDOFF COMPLETE — ready for Grok review"**  
and provide a concise summary of commands run + final state of the live site.

---

**You have full autonomy to execute the commands, interpret results, handle retries, and drive this to a verified working state.** Report progress and final evidence.