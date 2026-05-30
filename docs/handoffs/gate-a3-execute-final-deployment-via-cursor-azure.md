# Gate A3 — Execute Final Deployment Using Cursor's Azure Context

**Single Focused Goal:**  
**PRIME DIRECTIVE (INVIOLABLE — reinforced):** Drive the complete deployment + verification sequence for Gate A3 using the Cursor agent's existing authenticated Azure session (via the Azure extension). The agents MUST execute every deployment, az command, zip build, container operation, GUID capture, and post-deploy smoke themselves. Do not hand any steps back to the owner or produce commands for a human. Use Cursor's terminal, Azure extension, and any available tools to:

1. Build the deploy zip.
2. Run the full deployment via the existing `Deploy-ToAzure.ps1` (or direct equivalent using Cursor's Azure capabilities).
3. Run `Test-GateA3Poppler.ps1` (or equivalent verification).
4. Confirm `IMAGING_LEG poppler=ok` and capture the Deploy GUID.
5. Report clear success or failure with remediation.

**Mode:** reviewer-implementer (Cursor drives execution using its logged-in Azure context)

**Max turns:** 6

**Context you must use:**
- The authoritative owner execution package is at: `docs/gate-a3/Gate-A3-Owner-Execution-Package-Final.md`
- Scripts live in `Scripts/PowerShell/` (especially `Deploy-ToAzure.ps1`, `Build-AzureDeployZip.ps1`, `Test-GateA3Poppler.ps1`).
- You (the Cursor agent) are already logged into Azure via the extension in this environment.
- The target is the real production resources: Resource Group `SLAM-Services-RG`, App Service `slam-services-revenue-tracker`.
- Goal is to make the imaging leg live so a subsequent owner re-smoke can validate it.

**Rules:**
- Leverage your authenticated Azure session fully. Do not require the owner to run `az login` or any manual steps.
- If the existing PowerShell scripts work inside your terminal with the current Azure context, use them.
- If direct use of the Azure extension or VS Code Azure tasks is better, use those.
- Capture the exact Deploy GUID.
- Verify the imaging leg is enabled.
- Produce a clear pass/fail result with the Deploy GUID.

**Success criteria:**
- Deployment succeeds.
- `pdftoppm` is present on the live App Service.
- Log Stream (or equivalent) shows `IMAGING_LEG poppler=ok`.
- A Deploy GUID is captured.

When complete, end with:
**"DEPLOYMENT EXECUTED — DEPLOY GUID: [ID] — IMAGING_LEG STATUS: [ok / missing]"**

Do not stop or hand steps back. Drive this to completion using your authenticated Azure context. This is the final autonomous step before the owner only needs to do the browser re-smoke.