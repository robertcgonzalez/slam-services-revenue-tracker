#Requires -Version 5.1
<#
.SYNOPSIS
  Clear a blocking Azure App Service Startup Command (appCommandLine) via REST API.

.DESCRIPTION
  When appCommandLine is set to a raw `streamlit run ...` command, Oryx bypasses the
  deployed startup.sh and cold starts often fail the ~30s warmup probe (503 Application Error).

  `az webapp config set --startup-file ""` is unreliable; this script uses the REST PATCH
  that succeeded in the May 2026 automated recovery, then recycles the app and smoke-tests.

.EXAMPLE
  .\Scripts\PowerShell\Clear-AzureStartupCommand.ps1

.EXAMPLE
  .\Scripts\PowerShell\Clear-AzureStartupCommand.ps1 -SkipRecycle -WhatIf
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName = "slam-services-revenue-tracker",
    [switch]$SkipRecycle,
    [switch]$SkipSmokeTest,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg"     -ForegroundColor Green }
function Write-Warn2($m)  { Write-Host "  [WARN] $m"     -ForegroundColor Yellow }
function Write-Err2($m)   { Write-Host "  [ERR] $m"      -ForegroundColor Red }

Write-Step "Inspect current appCommandLine"
$before = az webapp config show -g $ResourceGroup -n $WebAppName `
    --query "appCommandLine" -o tsv 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Err2 "Could not read web app config. Run: az login"
    exit 1
}
if ($before) {
    Write-Warn2 "Current appCommandLine: $before"
} else {
    Write-Ok "appCommandLine is already empty"
    Write-Warn2 "With oryx-manifest.toml + output.tar.zst, empty appCommandLine often serves the Python placeholder. Use Set-AzureStartupCommand.ps1 to set ./startup.sh"
}

if ($WhatIf) {
    Write-Host "WhatIf: would PATCH appCommandLine to empty and recycle $WebAppName" -ForegroundColor Yellow
    exit 0
}

if (-not $before) {
    Write-Ok "No clear needed"
} else {
    Write-Step "Clear appCommandLine via REST API (reliable method)"
    $subId = az account show --query id -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $subId) {
        Write-Err2 "Could not resolve subscription id. Run: az login"
        exit 1
    }
    $uri = "https://management.azure.com/subscriptions/$subId/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$WebAppName/config/web?api-version=2022-03-01"
    $after = az rest --method PATCH --uri $uri `
        --body '{"properties":{"appCommandLine":""}}' `
        --query "properties.appCommandLine" -o tsv
    if ($LASTEXITCODE -ne 0) {
        Write-Err2 "REST PATCH failed"
        exit 1
    }
    if ($after) {
        Write-Warn2 "REST returned non-empty appCommandLine: $after"
    } else {
        Write-Ok "appCommandLine cleared (empty string)"
    }
}

if (-not $SkipRecycle) {
    Write-Step "Recycle container (stop + start)"
    az webapp stop -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
    Write-Ok "Stopped"
    Start-Sleep -Seconds 5
    az webapp start -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
    Write-Ok "Started"
}

if (-not $SkipSmokeTest) {
    Write-Step "HTTP smoke test (expect 401 Easy Auth or 2xx after cold start)"
    $url = "https://$WebAppName.azurewebsites.net/"
    $maxTries = 18
    $ok = $false
    for ($i = 1; $i -le $maxTries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing -MaximumRedirection 0 -ErrorAction Stop
            $code = [int]$resp.StatusCode
        } catch {
            if ($_.Exception.Response) {
                $code = [int]$_.Exception.Response.StatusCode.value__
            } else {
                Write-Host ("    try {0,2}/{1}: not ready ({2})" -f $i, $maxTries, $_.Exception.Message.Split("`n")[0]) -ForegroundColor DarkGray
                Start-Sleep -Seconds 10
                continue
            }
        }
        if ($code -eq 401 -or ($code -ge 200 -and $code -lt 500)) {
            Write-Ok "HTTP $code from $url (401 means Easy Auth redirect, expected when healthy)"
            $ok = $true
            break
        }
        Write-Host ("    try {0,2}/{1}: HTTP {2}" -f $i, $maxTries, $code) -ForegroundColor DarkGray
        Start-Sleep -Seconds 10
    }
    if (-not $ok) {
        Write-Warn2 "Smoke test did not get 401/2xx within ~3 minutes. Check: az webapp log tail -g $ResourceGroup -n $WebAppName"
        exit 1
    }
}

Write-Step "Done"
Write-Host "  Verify: .\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure"
Write-Host "  Live URL: https://$WebAppName.azurewebsites.net/"
