# Gate A3 Closure Checklist (Final)

**Primary sequence:** [`Gate-A3-Owner-Execution-Package-Final.md`](Gate-A3-Owner-Execution-Package-Final.md) — deploy → minimal browser smoke (two PDFs) → `Collect-GateA3Evidence.ps1 -Both -UpdateDocs`. This checklist is a short summary.

1. Deploy current source
   ```powershell
   cd C:\SLAM-Services-Project
   .\Scripts\PowerShell\Build-AzureDeployZip.ps1
   .\Scripts\PowerShell\Deploy-ToAzure.ps1 -TimeoutSeconds 900
   ```

2. Verify imaging leg is live
   ```powershell
   .\Scripts\PowerShell\Test-GateA3Poppler.ps1 -RestartIfLogMissing
   ```
   Confirm in Log Stream:
   - `IMAGING_LEG poppler=ok`

3. Owner performs clean re-smoke on both PDFs
   - HCC 2026-04.pdf
   - Auto_Body_Center_Jan_26_Statement.pdf

4. Owner fills `docs/gate-a3/Gate-A3-Final-Re-Smoke-Evidence-Guide.md` with numbers + key log lines from the new run.

5. Final scorecard + Path recommendation issued (Grok + Cursor review of evidence).
