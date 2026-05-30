# Gate A3 — Owner Execution Package (Final)

**Status:** Autonomous evidence collection is live. Manual screenshots, log copy/paste, CSV inspection, and number transcription are **not** required for assessment.

## Minimal flow (three steps)

### Step 1 — Deploy + verify (PowerShell)

```powershell
cd C:\SLAM-Services-Project
$ErrorActionPreference = 'Stop'

.\Scripts\PowerShell\Build-AzureDeployZip.ps1
.\Scripts\PowerShell\Deploy-ToAzure.ps1 -TimeoutSeconds 900
.\Scripts\PowerShell\Test-GateA3Poppler.ps1 -RestartIfLogMissing
```

Stop if `Test-GateA3Poppler.ps1` fails.

### Step 2 — Browser smoke (owner only — real client PDFs)

Open https://slam-services-revenue-tracker.azurewebsites.net/ → **Bank Statements**.

Upload and **Process Statement** for each (order does not matter):

- `HCC 2026-04.pdf`
- `Auto_Body_Center_Jan_26_Statement.pdf`

When processing finishes, the Processing log should include **"Validation evidence emitted to logs"** for each file. No screenshots or CSV downloads needed.

### Step 3 — Autonomous collection (PowerShell)

```powershell
.\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both -UpdateDocs
```

Optional: wait for evidence if you run the collector immediately after the first PDF:

```powershell
.\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both -WaitMinutes 30 -UpdateDocs
```

Combined imaging + evidence check after smoke:

```powershell
.\Scripts\PowerShell\Test-GateA3Poppler.ps1 -CheckSmokeEvidence
```

## What the collector updates

- `docs/gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md`
- `docs/gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`
- `deploy-logs-temp/gate-a3-intake-bundle.json`

## Pass signals

- `IMAGING_LEG poppler=ok` in logs (Poppler probe green)
- HCC: crops > 0, supplemental rows > 0 when imaging leg is live
- Auto Body: deposits/withdrawals move toward gold ($41,786.80 / $41,403.63)
- No persistent "cropper skipped: poppler" warnings

## 2026-05-29 baselines (for comparison)

- HCC: 98 register + 0 supplemental (poppler missing)
- Auto Body: 49 rows vs gold 92 txns
