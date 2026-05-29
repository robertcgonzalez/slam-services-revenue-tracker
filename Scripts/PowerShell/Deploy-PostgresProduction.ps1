#Requires -Version 5.1
<#
.SYNOPSIS
  End-to-end PostgreSQL production deploy helper (v2.30).

.DESCRIPTION
  Post-migration deploy only (P4). For full data-layer go-live (provision + migrate + wire + deploy),
  use Invoke-DataLayerGoLive.ps1 instead.

  1. Runs health_check.py (if .env configured)
  2. Builds flat Azure zip
  3. Deploys to App Service (-CleanDeploy by default)
  4. Reminds operator to verify Data Source Status in the app

.EXAMPLE
  .\Scripts\PowerShell\Deploy-PostgresProduction.ps1
  .\Scripts\PowerShell\Deploy-PostgresProduction.ps1 -SkipHealthCheck
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName = "slam-services-revenue-tracker",
    [string]$ZipName = "slam-app.zip",
    [switch]$SkipHealthCheck,
    [switch]$SkipDeploy,
    [switch]$NoCleanDeploy
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

if (-not $SkipHealthCheck) {
    Write-Host "=== Step 1: PostgreSQL health check ==="
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        & $venvPython Scripts/health_check.py
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Health check failed or DB not configured. Continue only if deploying CSV mode."
            $confirm = Read-Host "Continue deploy anyway? (y/N)"
            if ($confirm -ne "y") { exit 1 }
        }
    } else {
        Write-Warning "No .venv found — skipping health check."
    }
}

Write-Host "=== Step 2: Build deployment zip ==="
& (Join-Path $PSScriptRoot "Build-AzureDeployZip.ps1") -ZipName $ZipName

if ($SkipDeploy) {
    Write-Host "SkipDeploy set — zip ready at $RepoRoot\$ZipName"
    exit 0
}

Write-Host "=== Step 3: Deploy to Azure (modern polling-safe path) ==="
$deployParams = @{
    ResourceGroup   = $ResourceGroup
    WebAppName      = $WebAppName
    ZipPath         = (Join-Path $RepoRoot $ZipName)
    TimeoutSeconds  = 900
}
if (-not $NoCleanDeploy) { $deployParams["CleanDeploy"] = $true }
& (Join-Path $PSScriptRoot "Deploy-ToAzure.ps1") @deployParams

Write-Host "=== Done ==="
Write-Host "Verify: https://${WebAppName}.azurewebsites.net/"
Write-Host "  - Log in"
Write-Host "  - Sidebar: Data Source Status should show PostgreSQL connected"
Write-Host "  - Revenue Requests: edit → save → Force reload"
