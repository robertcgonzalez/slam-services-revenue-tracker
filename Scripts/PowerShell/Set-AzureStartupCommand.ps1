#Requires -Version 5.1
<#
.SYNOPSIS
  Set Azure App Service Startup Command to the deployed startup.sh (via REST API).

.DESCRIPTION
  When appCommandLine is empty and oryx-manifest.toml exists with compressed output,
  Oryx generates a Gunicorn default-app launcher ("Hey, Python developers!") instead
  of running /home/site/wwwroot/startup.sh.

  This script sets appCommandLine to /home/site/wwwroot/startup.sh (reliable REST PATCH),
  then recycles the app.

.EXAMPLE
  .\Scripts\PowerShell\Set-AzureStartupCommand.ps1
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName = "slam-services-revenue-tracker",
    # Use relative path — REST JSON rejects "//" in /home/site/... (parsed as comment).
    [string]$StartupCommand = "./startup.sh",
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
Write-Host "  Current: '$before'" -ForegroundColor DarkGray
Write-Host "  Target : '$StartupCommand'" -ForegroundColor DarkGray

if ($WhatIf) {
    Write-Host "WhatIf: would PATCH appCommandLine and recycle $WebAppName" -ForegroundColor Yellow
    exit 0
}

if ($before -eq $StartupCommand) {
    Write-Ok "appCommandLine already set correctly"
}
else {
    Write-Step "Set appCommandLine (az webapp config set)"
    $after = az webapp config set -g $ResourceGroup -n $WebAppName `
        --startup-file $StartupCommand --query "appCommandLine" -o tsv 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Err2 "az webapp config set --startup-file failed"
        exit 1
    }
    if ($after -ne $StartupCommand) {
        Write-Warn2 "REST returned: '$after' (expected '$StartupCommand')"
    }
    else {
        Write-Ok "appCommandLine set to $StartupCommand"
    }
}

if (-not $SkipRecycle) {
    Write-Step "Recycle container (stop + start)"
    az webapp stop -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
    Start-Sleep -Seconds 5
    az webapp start -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
    Write-Ok "Recycled"
}

if (-not $SkipSmokeTest) {
    Write-Step "HTTP smoke test (expect Streamlit or 401 Easy Auth — not Python placeholder)"
    $url = "https://$WebAppName.azurewebsites.net/"
    $maxTries = 24
    for ($i = 1; $i -le $maxTries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 20 -UseBasicParsing -ErrorAction Stop
            $code = $resp.StatusCode
            $body = $resp.Content
        }
        catch {
            if ($_.Exception.Response) {
                $code = [int]$_.Exception.Response.StatusCode.value__
                $body = ""
            }
            else {
                Start-Sleep -Seconds 10
                continue
            }
        }
        if ($body -match "Hey, Python developers") {
            Write-Host ("    try {0,2}/{1}: HTTP {2} — still Python placeholder" -f $i, $maxTries, $code) -ForegroundColor Yellow
        }
        elseif ($body -match "Sign in to your account" -or $code -eq 401) {
            Write-Ok "HTTP $code — Easy Auth (expected). Sign in, then use SLAM app password."
            exit 0
        }
        elseif ($body -match "streamlit|Enter Password|SLAM") {
            Write-Ok "HTTP $code — Revenue Tracker UI detected"
            exit 0
        }
        else {
            Write-Host ("    try {0,2}/{1}: HTTP {2}" -f $i, $maxTries, $code) -ForegroundColor DarkGray
        }
        Start-Sleep -Seconds 10
    }
    Write-Warn2 "Smoke test inconclusive — check log stream for STREAMLIT_LAUNCH"
}

Write-Step "Done"
