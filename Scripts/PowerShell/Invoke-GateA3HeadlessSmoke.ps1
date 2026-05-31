<#
.SYNOPSIS
    Upload canonical Gate A3 PDFs to App Service /tmp and run headless DI smoke via Kudu.
#>
[CmdletBinding()]
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$AppName       = "slam-services-revenue-tracker",
    [switch]$SkipUpload,
    [int]$WaitMinutes = 25
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$ScmBase = "https://$AppName.scm.azurewebsites.net"
$pdfs = @(
    @{ Local = "Data\HCC 2026-04.pdf"; Remote = "HCC_2026-04.pdf" },
    @{ Local = "Data\Auto_Body_Center_Jan_26_Statement.pdf"; Remote = "Auto_Body_Center_Jan_26_Statement.pdf" }
)

function Get-KuduHeaders {
    $pubJson = az webapp deployment list-publishing-credentials -g $ResourceGroup -n $AppName -o json
    $pub = $pubJson | ConvertFrom-Json
    $token = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("$($pub.publishingUserName):$($pub.publishingPassword)")
    )
    return @{ Authorization = "Basic $token" }
}

$headers = Get-KuduHeaders
Write-Host "=== Gate A3 Headless Smoke (Kudu) ===" -ForegroundColor Cyan

function Set-VfsFile {
    param([string]$Uri, [byte[]]$Bytes, [hashtable]$Headers)
    $putHeaders = $Headers.Clone()
    $putHeaders['If-Match'] = '*'
    Invoke-WebRequest -Method Put -Uri $Uri -Headers $putHeaders -Body $Bytes `
        -ContentType "application/octet-stream" -UseBasicParsing -TimeoutSec 300 | Out-Null
}

if (-not $SkipUpload) {
    foreach ($p in $pdfs) {
        $local = Join-Path $RepoRoot $p.Local
        if (-not (Test-Path $local)) { throw "Missing local PDF: $local" }
        $bytes = [IO.File]::ReadAllBytes($local)
        $uri = "$ScmBase/api/vfs/site/wwwroot/tmp/$($p.Remote)"
        Set-VfsFile -Uri $uri -Bytes $bytes -Headers $headers
        Write-Host "[OK] Uploaded wwwroot/tmp/$($p.Remote) ($([math]::Round($bytes.Length/1KB)) KB)" -ForegroundColor Green
    }
}

$runner = "Scripts/Python/run_gate_a3_headless_smoke.py"
if (-not (Test-Path (Join-Path $RepoRoot $runner))) {
    throw "Runner missing: $runner"
}

function Test-FreshSmokeLogComplete {
    param([string]$LogText)
    if ([string]::IsNullOrWhiteSpace($LogText)) { return $false }
    return ($LogText -match "DONE HCC 2026-04\.pdf") -and `
        ($LogText -match "DONE Auto_Body_Center_Jan_26_Statement\.pdf")
}

# Clear prior run markers so we never accept stale SMOKE_EVIDENCE from older docker logs.
$smokeLogUri = "$ScmBase/api/vfs/site/wwwroot/tmp/gate-a3-smoke.log"
Write-Host "Truncating gate-a3-smoke.log (fresh-run marker)..." -ForegroundColor DarkGray
Set-VfsFile -Uri $smokeLogUri -Bytes @() -Headers $headers

# Kudu /api/command runs in the Kudu sandbox (no Oryx antenv). Run DI in the app container via
# SLAM_RUN_GATE_A3_SMOKE + restart so startup.sh launches the runner with production deps.
Write-Host "Enabling SLAM_RUN_GATE_A3_SMOKE and restarting app (DI runs in app container)..." -ForegroundColor Yellow
az webapp config appsettings set -g $ResourceGroup -n $AppName `
    --settings SLAM_RUN_GATE_A3_SMOKE=true -o none | Out-Null
az webapp restart -g $ResourceGroup -n $AppName | Out-Null

$deadline = (Get-Date).AddMinutes($WaitMinutes)
$ok = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 45
    try {
        $logText = (Invoke-WebRequest -Uri $smokeLogUri -Headers $headers -UseBasicParsing -TimeoutSec 120).Content
        if (Test-FreshSmokeLogComplete -LogText $logText) {
            $ok = $true
            break
        }
        $tail = ($logText -split "`n") | Where-Object { $_ -match "^DONE |^=== Processing" } | Select-Object -Last 2
        if ($tail) {
            Write-Host "  In progress: $($tail -join ' | ')" -ForegroundColor DarkGray
        } else {
            Write-Host "  Waiting for gate-a3-smoke.log output..." -ForegroundColor DarkGray
        }
    }
    catch {
        Write-Host "  Waiting for gate-a3-smoke.log..." -ForegroundColor DarkGray
    }
}

az webapp config appsettings set -g $ResourceGroup -n $AppName `
    --settings SLAM_RUN_GATE_A3_SMOKE=false -o none | Out-Null

if (-not $ok) {
    Write-Host "=== /tmp/gate-a3-smoke.log (tail) ===" -ForegroundColor Yellow
    try {
        $logText = (Invoke-WebRequest -Uri "$ScmBase/api/vfs/site/wwwroot/tmp/gate-a3-smoke.log" -Headers $headers -UseBasicParsing -TimeoutSec 60).Content
        ($logText -split "`n") | Select-Object -Last 30 | ForEach-Object { Write-Host $_ }
    }
    catch {
        Write-Warning "Could not read /tmp/gate-a3-smoke.log: $_"
    }
    Write-Error "Headless smoke did not emit SMOKE_EVIDENCE within ${WaitMinutes}m."
}

Write-Host "[PASS] Headless Gate A3 smoke evidence collected." -ForegroundColor Green
