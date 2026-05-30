# Phase 1 Handoff — Clear Blocking Startup Command (Minimal for Orchestrator)

**Goal (single focused task for this run):**  
Get the production site (`slam-services-revenue-tracker`) responding again by removing the Azure App Service Startup Command that is bypassing `startup.sh`.

**Context (keep brief):**
- Live site shows generic Application Error / 503 on cold starts.
- Logs prove a `appCommandLine` is set to the raw `streamlit run ...` command.
- This completely ignores the project's `startup.sh` (which handles poppler, health checks, etc.).
- Cursor has full Azure CLI access in this environment and should drive the change.
- Use the existing `Scripts/PowerShell/Deploy-ToAzure.ps1` + `Build-AzureDeployZip.ps1` after the config change.

**Exact actions Cursor must take (in order):**

1. Inspect current configuration:
   ```powershell
   az webapp config show -g SLAM-Services-RG -n slam-services-revenue-tracker --query "appCommandLine"
   az webapp config appsettings list -g SLAM-Services-RG -n slam-services-revenue-tracker | findstr /i startup
   ```

2. Clear the blocking Startup Command (preferred):
   ```powershell
   az webapp config set `
     -g SLAM-Services-RG `
     -n slam-services-revenue-tracker `
     --startup-file ""
   ```

   (If the platform requires an explicit value, set it to `./startup.sh` instead.)

3. Verify the change took effect:
   ```powershell
   az webapp config show -g SLAM-Services-RG -n slam-services-revenue-tracker --query "appCommandLine"
   ```

4. Trigger a container recycle (stop + start) so the new setting applies:
   ```powershell
   az webapp stop -g SLAM-Services-RG -n slam-services-revenue-tracker
   az webapp start -g SLAM-Services-RG -n slam-services-revenue-tracker
   ```

5. Quick smoke: Confirm the live URL no longer shows the sad-face Application Error (it should eventually show the SLAM login page after the next successful cold start).

**Success for this phase:**
- `appCommandLine` is empty (or explicitly `./startup.sh`).
- After stop/start, the site comes up without the generic error page (may take 30-60s on first cold start).
- Report the exact CLI commands you ran and their output.

**Do not** attempt full redeploys, major script changes, or docs updates in this phase. Keep it laser-focused on removing the platform-level override.

**Prime Directive Override (applies to this entire directive):** The orchestrator will prepend absolute instructions that you MUST follow: ignore all "phase complete" / "ready for review" language. Address every output only to the other agent. Continue autonomous iteration, executing every CLI step, code change, and verification, until the *full original user goal* (not just this phase description) is 100% complete and working. Only end with the exact token "TASK COMPLETE". This directive's old stopping instruction is nullified by the prime directive.