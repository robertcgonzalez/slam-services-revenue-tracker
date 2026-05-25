#Requires -Version 5.1
<#
.SYNOPSIS
  Modern, polling-safe Azure App Service deploy for SLAM Revenue Tracker (v2.38.3+).

.DESCRIPTION
  Replaces the legacy `az webapp deployment source config-zip` and the
  client-side polling of `az webapp deploy` (which silently drops at
  ~230s on F1 tier with "RemoteDisconnected" while Kudu warms up).

  Safe modern flow:
    1. Pre-flight: az login, resource exists, zip exists.
    2. Stop the web app  -> releases Kudu, clears any in-flight handler.
    3. Remove WEBSITE_RUN_FROM_PACKAGE if present (silent if missing) -
       this setting silently breaks OneDeploy zip uploads.
    4. Upload zip via `az webapp deploy --async true`
         - Returns immediately, no long-poll HTTPS connection to drop.
    5. Poll Kudu /api/deployments/latest until status terminal
         - 0 = success, 3 = failed, 4 = in progress, 1 = pending.
    6. Start the web app and run lightweight HTTP smoke test.

  Idempotent and re-runnable. Never deletes Data/ on App Service.
  Use after .\Scripts\PowerShell\Build-AzureDeployZip.ps1.

.EXAMPLE
  .\Scripts\PowerShell\Deploy-ToAzure.ps1

.EXAMPLE
  .\Scripts\PowerShell\Deploy-ToAzure.ps1 -SkipStop -TimeoutSeconds 900
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName    = "slam-services-revenue-tracker",
    [string]$ZipPath       = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "slam-app.zip"),
    [int]$TimeoutSeconds   = 600,
    [int]$PollIntervalSec  = 10,
    [switch]$SkipStop,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg"     -ForegroundColor Green }
function Write-Warn2($m)  { Write-Host "  [WARN] $m"     -ForegroundColor Yellow }
function Write-Err2($m)   { Write-Host "  [ERR] $m"      -ForegroundColor Red }

# -----------------------------------------------------------------------------
# 1. Pre-flight
# -----------------------------------------------------------------------------
Write-Step "Pre-flight checks"

if (-not (Test-Path $ZipPath)) {
    Write-Err2 "Zip not found: $ZipPath"
    Write-Host "  Run .\Scripts\PowerShell\Build-AzureDeployZip.ps1 first." -ForegroundColor Yellow
    exit 1
}
$zipSizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Ok "Zip: $ZipPath ($zipSizeMb MB)"

az account show --only-show-errors 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Err2 "Not logged in to Azure CLI. Run: az login"
    exit 1
}
Write-Ok "Azure CLI session active"

$appState = az webapp show -g $ResourceGroup -n $WebAppName --query "state" -o tsv 2>$null
if ($LASTEXITCODE -ne 0 -or -not $appState) {
    Write-Err2 "Web app '$WebAppName' not found in resource group '$ResourceGroup'."
    exit 1
}
Write-Ok "Web app found (current state: $appState)"

# -----------------------------------------------------------------------------
# 2. Clear conflicting app settings (idempotent)
# -----------------------------------------------------------------------------
Write-Step "Clearing WEBSITE_RUN_FROM_PACKAGE (if present)"
$hasRunFromPkg = az webapp config appsettings list -g $ResourceGroup -n $WebAppName `
    --query "[?name=='WEBSITE_RUN_FROM_PACKAGE'].value | [0]" -o tsv 2>$null
if ($hasRunFromPkg) {
    az webapp config appsettings delete `
        -g $ResourceGroup -n $WebAppName `
        --setting-names WEBSITE_RUN_FROM_PACKAGE --only-show-errors | Out-Null
    Write-Ok "Removed WEBSITE_RUN_FROM_PACKAGE (was: $hasRunFromPkg)"
} else {
    Write-Ok "WEBSITE_RUN_FROM_PACKAGE not set - good"
}

# -----------------------------------------------------------------------------
# 3. Stop web app to release Kudu (avoids stale deploy lock)
# -----------------------------------------------------------------------------
if (-not $SkipStop) {
    Write-Step "Stopping web app (releases Kudu + clears any stuck deploy lock)"
    az webapp stop -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
    Write-Ok "Web app stopped"
    Start-Sleep -Seconds 8
}

# -----------------------------------------------------------------------------
# 4. Async OneDeploy upload (no client-side polling = no RemoteDisconnected)
# -----------------------------------------------------------------------------
Write-Step "Uploading zip via OneDeploy (async)"
$deployJson = az webapp deploy `
    -g $ResourceGroup `
    -n $WebAppName `
    --src-path "$ZipPath" `
    --type zip `
    --async true `
    --only-show-errors `
    -o json 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Err2 "Async upload submission failed:"
    Write-Host $deployJson
    exit 1
}
Write-Ok "Upload accepted by Kudu - server-side deployment in progress"

# -----------------------------------------------------------------------------
# 5. Poll Kudu deployment status (server-side, no long-lived HTTPS)
# -----------------------------------------------------------------------------
Write-Step "Polling deployment status (timeout: ${TimeoutSeconds}s)"

# Status codes: 0=success, 1=pending, 2=building, 3=failed, 4=in-progress
$statusMap = @{
    0 = "Success"
    1 = "Pending"
    2 = "Building"
    3 = "Failed"
    4 = "InProgress"
    5 = "PartiallySuccessful"
    6 = "BuildPending"
}

$start = Get-Date
$lastStatus = -1
$lastMessage = ""
$terminal = $false
$finalStatus = -1

while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSeconds) {
    Start-Sleep -Seconds $PollIntervalSec
    $latest = az webapp deployment list -g $ResourceGroup -n $WebAppName `
        --query "[0].{status:status,message:message,id:id,complete:complete}" `
        -o json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    if (-not $latest) {
        Write-Host "    ...waiting for Kudu to register deployment" -ForegroundColor DarkGray
        continue
    }
    $code = [int]$latest.status
    $label = if ($statusMap.ContainsKey($code)) { $statusMap[$code] } else { "Unknown($code)" }
    if ($code -ne $lastStatus -or $latest.message -ne $lastMessage) {
        $elapsed = [int]((Get-Date) - $start).TotalSeconds
        Write-Host ("    [{0,4}s] status={1} ({2})" -f $elapsed, $code, $label) -ForegroundColor DarkGray
        $lastStatus = $code
        $lastMessage = $latest.message
    }
    if ($code -in 0,3,5 -and $latest.complete) {
        $terminal = $true
        $finalStatus = $code
        break
    }
}

if (-not $terminal) {
    Write-Warn2 "Polling window elapsed without a terminal status."
    Write-Host "  Check Kudu directly: https://$WebAppName.scm.azurewebsites.net/api/deployments" -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# 6. Start app + smoke test
# -----------------------------------------------------------------------------
Write-Step "Starting web app"
az webapp start -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
Write-Ok "Start signal sent"

if (-not $SkipSmokeTest) {
    Write-Step "HTTP smoke test (cold-start can take 60-120s on F1)"
    $url = "https://$WebAppName.azurewebsites.net/"
    $maxTries = 18  # ~3 minutes
    for ($i = 1; $i -le $maxTries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                Write-Ok "HTTP $($resp.StatusCode) from $url"
                break
            }
        } catch {
            Write-Host ("    try {0,2}/{1}: not ready yet ({2})" -f $i, $maxTries, $_.Exception.Message.Split("`n")[0]) -ForegroundColor DarkGray
        }
        Start-Sleep -Seconds 10
    }
}

Write-Step "Done"
Write-Host "  Live URL : https://$WebAppName.azurewebsites.net/"
Write-Host "  Log tail : az webapp log tail -g $ResourceGroup -n $WebAppName"
Write-Host "  Kudu UI  : https://$WebAppName.scm.azurewebsites.net/"

if ($terminal -and $finalStatus -eq 0) { exit 0 }
elseif ($terminal -and $finalStatus -eq 3) { exit 1 }
else { exit 0 }
