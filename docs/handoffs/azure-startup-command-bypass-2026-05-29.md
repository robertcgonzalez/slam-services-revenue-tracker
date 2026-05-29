# Handoff Directive — Fix Azure App Service "Application Error" (Startup Command Bypass)

**Date**: 2026-05-29  
**Status**: Production outage — live site returning generic Application Error page  
**Target Agent**: Cursor (primary / lead per CONSTITUTION.md)  
**Source**: Grok analysis of captured Azure logs

---

## Authoritative Diagnosis (from live container logs)

The site `slam-services-revenue-tracker.azurewebsites.net` is down with the classic Oryx sad-face "Application Error".

From the user's captured logs (`deploy-logs-temp/LogFiles/StartupLogs/` — specifically the May 29 failure on instance `lw1mdlwk0000X9` and contrasting successes):

- **Root cause**: A **Startup Command** (`appCommandLine`) is set at the Azure App Service platform level:
  ```
  python -m streamlit run App/app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
  ```
- Because this setting exists, **`startup.sh` is completely ignored** on every container start (Oryx directly executes the userStartupCommand).
- The raw `streamlit run` + heavy imports (`opencv-python-headless`, `azure-ai-documentintelligence`, `pdf2image`, `azure-ai-contentunderstanding`, etc.) takes **31–40+ seconds** to print "You can now view your Streamlit app in your browser".
- Azure warmup probe frequently fails the ~30s window on cold container starts → container killed with `ContainerTimeout` → Application Error page.
- User's `startup.sh` (pip upgrade, requirements install, poppler-utils fallback, CSV/Postgres health checks) never runs.
- The site sometimes comes up on lucky warm instances but is fundamentally unstable on the F1 tier with this dependency set.

This is a **platform configuration + cold-start timeout** problem, not a code crash in most cases.

---

## Hard Constraints (Non-Negotiable)

1. **Cursor drives the fix**. You have full autonomy to make the required Azure configuration changes, script updates, and documentation updates.
2. Use the project's existing deployment mechanisms (`Scripts/PowerShell/Build-AzureDeployZip.ps1` + `Deploy-ToAzure.ps1`). Do not invent new deploy paths.
3. Production safety first: any change must be reversible and must not lose the existing `Data/` folder on the App Service (the `clean: false` contract).
4. Follow CONSTITUTION.md (Laura’s confidence as primary metric, pragmatic minimalism, documentation roles discipline) and `.cursor/rules/slam-services.mdc`.
5. Do not over-engineer. The goal is reliable uptime for Laura/Stef daily use, not a perfect startup system.

---

## Mandate — Execute This Now

Fix the production outage so the live URL reliably serves the Streamlit login/dashboard instead of the Application Error page.

### Immediate Actions Required

1. **Inspect current Azure configuration**
   - Use Azure CLI to show the exact current Startup Command / `appCommandLine` setting on `slam-services-revenue-tracker`.
   - Check related settings: `SCM_DO_BUILD_DURING_DEPLOYMENT`, `WEBSITES_PORT`, `USE_POSTGRES`, and any custom `STARTUP_COMMAND`.

2. **Remove or correct the blocking Startup Command**
   - The preferred fix: Clear the Startup Command entirely so the deployed `startup.sh` at the zip root is honored again by Oryx.
   - Alternative (if platform requires an explicit command): Set it to `./startup.sh`.
   - Provide the user with the exact `az webapp config set` (or Portal steps) command to apply the fix safely.

3. **Validate + harden `startup.sh` for the new reality (if needed)**
   - Ensure it still works correctly when it becomes the actual entrypoint.
   - Consider small robustness improvements for cold starts (e.g., early logging, better timeout resilience, explicit readiness signaling) without major rewrites.
   - Confirm poppler-utils handling and health check behavior remain correct.

4. **Update documentation**
   - `docs/deployment.md` must clearly state the current correct way to manage (or avoid) the Startup Command setting going forward.
   - Note any required App Service settings for reliable Streamlit cold starts on this stack.
   - Add a short "Startup Troubleshooting" section referencing the symptoms seen here.

5. **Provide the user with a complete, copy-pasteable recovery + verification sequence**
   - Exact commands to apply the fix.
   - Post-fix redeploy command (using the existing PowerShell scripts).
   - Full validation using the project's health tools:
     - `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure`
     - Python `Scripts/health_check.py --full`
     - Browser smoke of the live URL
   - Rollback steps in case the change makes it worse.

### Required Deliverables (in this or immediate next turn)

- Exact Azure CLI commands (or Portal navigation) to inspect and clear/fix the Startup Command.
- Any minimal changes to `startup.sh` or related files (with clear justification).
- Updated `docs/deployment.md` with the corrected startup behavior.
- A "Post-Fix Verification Checklist" the user can run immediately after the change.
- Clear statement of what success looks like (site returns normal Streamlit UI consistently, including after container recycle).

---

## Context You Must Use

- `startup.sh` (current intended entrypoint)
- `Scripts/PowerShell/Deploy-ToAzure.ps1` and `Build-AzureDeployZip.ps1`
- `docs/deployment.md` (primary deployment reference)
- `App/app.py` (top-level imports and data path resolution at startup)
- `apt.txt` and Oryx build behavior
- Existing health check scripts (`Scripts/health_check.py`, `Scripts/PowerShell/Check-AppHealth.ps1`)

Treat the logs in `deploy-logs-temp/` as the authoritative evidence of the failure mode.

---

## Success Criteria

- Live site (`https://slam-services-revenue-tracker.azurewebsites.net/`) consistently returns the SLAM Services login page (or dashboard) instead of the Application Error page.
- A container restart / new instance no longer produces the warmup timeout.
- The user has a one-command or one-Portal-change path to apply the fix today.
- Documentation is updated so this class of problem does not recur without clear guidance.
- All changes respect the existing deploy hygiene and Data/ preservation contract.

---

**Handoff complete.** Cursor: take ownership and drive the fix to completion. Report back the exact commands + doc diff + verification steps when ready for human execution.

**Next human action after Cursor finishes**: Apply the recommended Azure change, run a redeploy, and execute the verification checklist. Paste results back for review.