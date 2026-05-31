#Requires -Version 5.1
<#
.SYNOPSIS
  Configure the SLAM Services App Service for the production Azure Document Intelligence
  bank statement pipeline (two-leg: prebuilt-bankStatement.us + per-crop prebuilt-check.us).

.DESCRIPTION
  Sets the required App Settings on slam-services-revenue-tracker (or the renamed
  production App Service) so that Bank Statements Phase 1 (and future richer flows)
  use Azure Document Intelligence as the primary OCR / extraction engine.

  This is the production "go live" counterpart to Set-LocalAzureBankStatementEnv.ps1.

  The script deliberately starts the check imaging leg on prebuilt-check.us (the
  owner decision from the 2026 go-live review). Content Understanding or a custom
  model can be evaluated later without changing this baseline.

  Supports immediate rollback via -Disable.

.PARAMETER ResourceGroup
  Default: SLAM-Services-RG

.PARAMETER WebAppName
  Default: slam-services-revenue-tracker (update after any rename)

.PARAMETER DisableDI
  Removes the DI-related settings (reverts Bank Statements to parser + Grok paste only).

.EXAMPLE
  # Normal production enablement (after S0 upgrade of slam-bank-statements)
  .\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1

.EXAMPLE
  # Immediate rollback (no code change required)
  .\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName = "slam-services-revenue-tracker",
    [string]$DiAccountName = "slam-bank-statements",
    [switch]$DisableDI,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Write-WhatIf($msg) {
    if ($WhatIf) {
        Write-Host "[WHATIF] $msg" -ForegroundColor Yellow
    }
}

Write-Host "=== SLAM Services — Azure Document Intelligence (Bank Statements) ===" -ForegroundColor Cyan
Write-Host "Target App Service : $WebAppName ($ResourceGroup)" -ForegroundColor Gray
Write-Host "DI Cognitive Account: $DiAccountName" -ForegroundColor Gray

if ($DisableDI) {
    Write-Host ""
    Write-Host "Disabling Azure Document Intelligence path..." -ForegroundColor Yellow
    Write-WhatIf "Would remove AZURE_DI_* and related imaging settings"

    if (-not $WhatIf) {
        az webapp config appsettings delete `
            -g $ResourceGroup `
            -n $WebAppName `
            --setting-names `
                AZURE_DI_ENDPOINT `
                AZURE_DI_KEY `
                AZURE_DI_MODEL `
                AZURE_DI_CHECK_MODEL `
                SLAM_IMAGING_FIRST_PAGE `
                SLAM_IMAGING_LAST_PAGE `
                CONTENTUNDERSTANDING_ENDPOINT `
                CONTENTUNDERSTANDING_KEY `
                CONTENTUNDERSTANDING_CHECK_ANALYZER `
                AZURE_OCR_FUNCTION_URL `
                AZURE_OCR_FUNCTION_KEY | Out-Null
    }

    Write-Host "DI settings removed. Bank Statements will fall back to local parser + Grok Vision paste." -ForegroundColor Green
    Write-Host "Restart the App Service (or wait for next request) for changes to take effect."
    exit 0
}

# --- Pull current values from the DI account (same logic as the local setter) ---
Write-Host ""
Write-Host "Retrieving endpoint + key from $DiAccountName ..." -ForegroundColor Cyan

$endpoint = az cognitiveservices account show `
    --name $DiAccountName `
    --resource-group $ResourceGroup `
    --query "properties.endpoint" `
    --output tsv 2>$null

if ([string]::IsNullOrWhiteSpace($endpoint)) {
    Write-Error "Could not read endpoint for $DiAccountName. Is the resource in $ResourceGroup and do you have access?"
}

$key = az cognitiveservices account keys list `
    --name $DiAccountName `
    --resource-group $ResourceGroup `
    --query "key1" `
    --output tsv 2>$null

if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Error "Could not read key1 for $DiAccountName."
}

$sku = az cognitiveservices account show `
    --name $DiAccountName `
    --resource-group $ResourceGroup `
    --query "sku.name" `
    --output tsv 2>$null

Write-Host "  Endpoint : $endpoint"
Write-Host "  Key      : ($($key.Length) chars)"
Write-Host "  SKU      : $sku" -ForegroundColor $(if ($sku -eq "F0") { "Yellow" } else { "Green" })

if ($sku -eq "F0") {
    Write-Host ""
    Write-Host "WARNING: The DI resource is still on F0 (free). Owner decision was to upgrade to S0 before broad production use." -ForegroundColor Yellow
    Write-Host "         Run the upgrade in the Azure Portal (or via az cognitiveservices account update) before the Laura pilot." -ForegroundColor Yellow
    Write-Host ""
}

# --- Build the settings payload (owner decision: prebuilt-check.us first) ---
$settings = @{
    "AZURE_DI_ENDPOINT"                 = $endpoint.Trim()
    "AZURE_DI_KEY"                      = $key.Trim()
    "AZURE_DI_MODEL"                    = "prebuilt-bankStatement.us"
    "AZURE_DI_CHECK_MODEL"              = "prebuilt-check.us"
    "SLAM_IMAGING_FIRST_PAGE"           = "5"
    "SLAM_IMAGING_LAST_PAGE"            = "9"
    # Geometry cropper v5 — Gate A3 validated (HCC ~42, Auto Body ~58 crops @ 300 DPI)
    "SLAM_CROP_DPI"                     = "300"
    "SLAM_CROP_MIN_HEIGHT"              = "320"
    # Backward-compat aliases so older code paths (if any) still work
    "AZURE_OCR_FUNCTION_URL"            = $endpoint.Trim()
    "AZURE_OCR_FUNCTION_KEY"            = $key.Trim()
}

# Optional: if a Content Understanding resource is later provisioned, those
# vars (CONTENTUNDERSTANDING_*) can be added here or via a companion script.
# Per go-live decision we deliberately start with prebuilt-check.us.

Write-Host ""
Write-Host "Applying Azure Document Intelligence settings to $WebAppName ..." -ForegroundColor Cyan

if ($WhatIf) {
    Write-Host "[WHATIF] Would set the following App Settings:" -ForegroundColor Yellow
    $settings.GetEnumerator() | Sort-Object Name | ForEach-Object {
        $val = if ($_.Key -like "*KEY*") { "($($_.Value.Length) chars)" } else { $_.Value }
        Write-Host "  $($_.Key) = $val"
    }
    Write-Host ""
    Write-Host "Run without -WhatIf to apply."
    exit 0
}

# az webapp config appsettings set accepts a hash in recent versions; we use the explicit form for reliability
$argList = @(
    "-g", $ResourceGroup,
    "-n", $WebAppName,
    "--settings"
)
foreach ($k in $settings.Keys) {
    $argList += "$k=$($settings[$k])"
}

& az webapp config appsettings set @argList | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Error "az webapp config appsettings set failed. Check RBAC and that the App Service exists."
}

Write-Host "Settings applied successfully." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps (per approved 2026 DI go-live plan):"
Write-Host "  1. Redeploy the latest code (GitHub Action or .\Scripts\PowerShell\Deploy-ToAzure.ps1)"
Write-Host "  2. .\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure"
Write-Host "  3. Robert smoke test on the live URL using real PDFs from Data/"
Write-Host "  4. Schedule Laura + full-team pilot session"
Write-Host ""
Write-Host "Rollback at any time:"
Write-Host "  .\Scripts\PowerShell\Set-AzureBankStatementDIAppSettings.ps1 -DisableDI"
Write-Host ""
Write-Host "The Grok Vision paste path and lightweight parser remain fully available as safe fallbacks."
Write-Host "No data or CSV workflow is affected." -ForegroundColor Green
