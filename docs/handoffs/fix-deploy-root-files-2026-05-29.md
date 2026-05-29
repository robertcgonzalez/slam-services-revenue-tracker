# Handoff — Fix OneDeploy / CleanDeploy Root File Delivery (Critical)

**Date**: 2026-05-29  
**Symptom**: After `Build-AzureDeployZip.ps1` + `Deploy-ToAzure.ps1 -CleanDeploy`, the critical root files `startup.sh`, `runtime.txt`, and `apt.txt` are **missing** from `/home/site/wwwroot/`.  
Kudu `ls` confirms they do not exist, even though:
- The build script explicitly verifies and includes them.
- The zip is created as a flat archive.
- Kudu OneDeploy reports "complete" with zero build errors.
- The app is on B2 tier.

Result: Oryx falls back to the default Python placeholder page ("Hey, Python developers!") because there is no `startup.sh` to execute.

**Target**: Cursor (primary driver via automated dual-agent orchestrator)

---

## Authoritative Diagnosis (Current Session)

The automated deployment pipeline is broken for delivering the required root-level startup artifacts.

Evidence from live Kudu sessions:
- `ls -la /home/site/wwwroot/startup.sh` → "No such file or directory"
- Same for `runtime.txt` and `apt.txt`
- Other files from the zip (App/, requirements.txt, etc.) sometimes appear, but the three essential root files for Oryx do not.
- This has now failed consistently across normal deploys and `-CleanDeploy` attempts.
- The previous forcing of `appCommandLine` was removed earlier; that is not the current blocker.

The deploy scripts (`Build-AzureDeployZip.ps1` and `Deploy-ToAzure.ps1`) + the way we invoke `az webapp deploy --type zip --clean` are not reliably producing a wwwroot state where Oryx will find and run `startup.sh`.

---

## Goal for This Handoff

Make the deployment pipeline (build + deploy) **reliably** place `startup.sh`, `runtime.txt`, and `apt.txt` at the root of `/home/site/wwwroot/` after every successful deploy (especially with `-CleanDeploy`), so that the real Streamlit Revenue Tracker starts via Oryx.

---

## Exact Work Cursor Must Drive

1. **Deeply investigate the current deploy pipeline**
   - Examine `Scripts/PowerShell/Build-AzureDeployZip.ps1` (how the flat zip is constructed, what is included/excluded, staging logic).
   - Examine `Scripts/PowerShell/Deploy-ToAzure.ps1` (especially the `-CleanDeploy` path, `az webapp deploy` invocation, polling logic, and any post-deploy steps).
   - Understand how `az webapp deploy --type zip --clean` behaves on this App Service (B2 tier, Python|3.10, OneDeploy).

2. **Identify the root cause**
   - Why do the three root files disappear or fail to extract even when the build script says they are present and Kudu reports success?
   - Check zip structure, manifest behavior, Oryx interaction with clean deploys, possible leftover `oryx-manifest.toml` or `output.tar.zst` interference, folder nesting issues, etc.
   - Reproduce/analyze the exact failure mode using available tools (local zip inspection, Kudu if possible, deployment logs).

3. **Implement a robust fix**
   - Modify the build and/or deploy scripts so the critical root files are guaranteed to land at `/home/site/wwwroot/`.
   - Add explicit post-deploy verification: after a deploy, the scripts must confirm that `startup.sh`, `runtime.txt`, and `apt.txt` exist and are executable (fail the deploy loudly if they do not).
   - Consider improvements such as:
     - Better zip layout / explicit file list for OneDeploy
     - Post-clean verification + retry logic
     - Alternative reliable deployment method for these root files when the normal path fails
     - Improved logging of what actually landed in wwwroot

4. **Update related documentation and handoff patterns**
   - Document the fix and the new verification behavior in `docs/deployment.md`.
   - If useful, create or update a small helper (e.g. a verification script) that can be run manually or in CI.

5. **Validate end-to-end**
   - After changes, perform a real deploy (using the updated scripts) and have the user confirm via Kudu that the three files now exist at the root.
   - Confirm the live site no longer shows the Python placeholder and serves the real Revenue Tracker (after proper cold start on B2).

---

## Constraints (Non-Negotiable)

- Cursor drives the investigation and implementation.
- Use the existing PowerShell deployment scripts as the primary mechanism — improve them rather than replacing the whole system.
- Preserve the "code-only, preserve Data/" contract and the flat structure intent of the current build.
- Production safety first: changes must be reversible and must not risk losing server-side CSV data.
- Follow the spirit of previous successful Azure recovery handoffs in this `docs/handoffs/` folder (focus on operational reliability, clear evidence, minimal over-engineering).

---

## Success Criteria (This Phase)

- After running the updated `Build-AzureDeployZip.ps1` + `Deploy-ToAzure.ps1 -CleanDeploy`, Kudu shows:
  - `startup.sh` present and executable at `/home/site/wwwroot/startup.sh`
  - `runtime.txt` and `apt.txt` also present at root
- The deploy script itself (or a called verification step) explicitly confirms these files landed.
- The live site (`https://slam-services-revenue-tracker.azurewebsites.net/`) serves the real Streamlit application (not the Python placeholder) after a cold start.
- Clear before/after evidence is provided (Kudu listings, deployment log excerpts, HTTP responses).

When the phase is complete, end with:

**"HANDOFF COMPLETE — ready for Grok review"**

Include a short summary of the root cause found and the changes made, plus the final Kudu verification output.

---

**You have full autonomy to explore the scripts, run commands (via the user), inspect the zip, analyze deployment logs, implement fixes, add verification, and drive this to a working state.** Provide evidence at each major step. Prioritize a reliable, maintainable fix over clever workarounds.