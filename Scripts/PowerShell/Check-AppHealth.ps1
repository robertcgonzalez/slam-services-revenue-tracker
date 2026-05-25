#Requires -Version 5.1
<#
.SYNOPSIS
  Pre-UAT / post-deploy health validation for SLAM Revenue Tracker (v2.32).

.DESCRIPTION
  Runs local health_check.py (CSV + optional PostgreSQL) and optionally
  queries Azure App Service state. Use before Laura/Stef UAT sessions.

.EXAMPLE
  .\Scripts\PowerShell\Check-AppHealth.ps1
  .\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure
#>
param(
    [switch]$Full,
    [switch]$CheckAzure,
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName = "slam-services-revenue-tracker"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "=== SLAM Revenue Tracker health (v2.32) ===" -ForegroundColor Cyan

if ($Full) {
    & $python Scripts/health_check.py --full
} else {
    & $python Scripts/health_check.py --csv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python Scripts/health_check.py
}

$healthExit = $LASTEXITCODE

if ($CheckAzure) {
    Write-Host "`n=== Azure App Service ===" -ForegroundColor Cyan
    $state = az webapp show -g $ResourceGroup -n $WebAppName --query "{state:state,host:defaultHostName}" -o json 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host $state
        $url = "https://$WebAppName.azurewebsites.net/"
        Write-Host "Live URL: $url"
        Write-Host "Tip: Portal -> Log stream -> filter 'slam_app' for login/save events"
    } else {
        Write-Warning "Azure CLI check skipped (not logged in or app not found)."
    }
}

Write-Host "`n=== UAT readiness ===" -ForegroundColor Cyan
Write-Host "  1. SLAM_APP_PASSWORD set in Azure App Settings"
Write-Host "  2. SLAM_APP_USER=Laura or Stef per user session"
Write-Host "  3. Log in -> Dashboard shows Today's priority"
Write-Host "  4. Revenue Requests -> edit -> Save -> green confirmation"

exit $healthExit
