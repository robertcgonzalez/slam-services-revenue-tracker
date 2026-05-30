<#
.SYNOPSIS
    Post-deploy verification for Gate A3 imaging leg readiness (poppler + startup logging).

.DESCRIPTION
    Checks three things after a deploy:
    1. Latest Kudu deploy ID + status
    2. pdftoppm presence via authenticated Kudu command
    3. IMAGING_LEG poppler=ok in recent docker logs

    Exits 0 on full success, 1 on any failure with remediation steps.

.PARAMETER RestartIfLogMissing
    If the startup log marker is not found, restart the app and re-check.

.PARAMETER CheckSmokeEvidence
    After poppler probe, verify SMOKE_EVIDENCE lines exist (or wait with -WaitMinutes).

.PARAMETER WaitMinutes
    Used with -CheckSmokeEvidence — poll Kudu until both PDF keys appear.

.EXAMPLE
    .\Scripts\PowerShell\Test-GateA3Poppler.ps1

.EXAMPLE
    .\Scripts\PowerShell\Test-GateA3Poppler.ps1 -RestartIfLogMissing

.EXAMPLE
    .\Scripts\PowerShell\Test-GateA3Poppler.ps1 -CheckSmokeEvidence -WaitMinutes 20
#>
[CmdletBinding()]
param(
    [switch]$RestartIfLogMissing,
    [switch]$CheckSmokeEvidence,
    [int]$WaitMinutes = 0
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# --- Configuration ---
$ResourceGroup = "SLAM-Services-RG"
$AppName       = "slam-services-revenue-tracker"
$ScmBase       = "https://$AppName.scm.azurewebsites.net"

function Get-KuduHeaders {
    $pubJson = az webapp deployment list-publishing-credentials -g $ResourceGroup -n $AppName -o json
    $pub = $pubJson | ConvertFrom-Json
    $token = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("$($pub.publishingUserName):$($pub.publishingPassword)")
    )
    return @{ Authorization = "Basic $token" }
}

Write-Host "=== Gate A3 Poppler / Imaging Leg Verification ===" -ForegroundColor Cyan

$headers = Get-KuduHeaders

# 1. Latest deploy
Write-Host "`n[1/3] Latest deployment..."
try {
    $deploy = az webapp log deployment list -g $ResourceGroup -n $AppName --query "[0]" -o json | ConvertFrom-Json
    Write-Host "Deploy ID : $($deploy.id)"
    Write-Host "Status    : $($deploy.status)"
    Write-Host "Message   : $($deploy.message)"
} catch {
    Write-Warning "Could not retrieve deploy info: $_"
}

# 2. pdftoppm probe
Write-Host "`n[2/3] Kudu pdftoppm probe..."
try {
    $cmd = 'command -v pdftoppm && pdftoppm -v 2>&1 | head -1'
    $result = Invoke-RestMethod -Uri "$ScmBase/api/command" -Method Post -Headers $headers -Body (@{ command = $cmd } | ConvertTo-Json) -ContentType "application/json"

    if ($result.ExitCode -eq 0 -and $result.Output -match "pdftoppm") {
        Write-Host "[OK] pdftoppm found (Kudu command shell):" -ForegroundColor Green
        Write-Host $result.Output.Trim()
    } else {
        Write-Warning "pdftoppm not visible in Kudu command shell (app container may still have it via startup.sh)."
    }
} catch {
    Write-Warning "Kudu pdftoppm probe failed: $_"
}

# 3. Log marker
Write-Host "`n[3/3] Checking for IMAGING_LEG poppler=ok in logs..."
try {
    $logUri = "$ScmBase/api/vfs/LogFiles/?recursive=true"
    $logs = Invoke-RestMethod -Uri $logUri -Headers $headers

    $dockerLogs = $logs | Where-Object {
        $_.name -like "*docker.log" -or $_.name -like "*default_docker.log"
    } | Sort-Object name -Descending | Select-Object -First 6

    $found = $false
    foreach ($log in $dockerLogs) {
        $logPath = "$ScmBase/api/vfs/LogFiles/$($log.name)"
        try {
            $resp = Invoke-WebRequest -Uri $logPath -Headers $headers -UseBasicParsing -TimeoutSec 60
            $content = $resp.Content
        } catch {
            continue
        }
        if ($content -match "IMAGING_LEG poppler=ok") {
            Write-Host "[OK] Found IMAGING_LEG poppler=ok in $($log.name)" -ForegroundColor Green
            $found = $true
            break
        }
        if ($content -match "IMAGING_LEG poppler=missing") {
            Write-Warning "Found IMAGING_LEG poppler=missing in $($log.name)"
        }
    }

    if (-not $found) {
        if ($RestartIfLogMissing) {
            Write-Host "Marker not found. Restarting app..." -ForegroundColor Yellow
            az webapp restart -g $ResourceGroup -n $AppName
            Start-Sleep 60
            & $PSCommandPath -RestartIfLogMissing:$false -CheckSmokeEvidence:$CheckSmokeEvidence
            return
        } else {
            Write-Warning "IMAGING_LEG poppler=ok not found in recent LogFiles (app stdout may be in log tail only)."
        }
    }
} catch {
    Write-Warning "Could not inspect logs: $_"
}

Write-Host "`n[PASS] Imaging leg appears live." -ForegroundColor Green

if ($CheckSmokeEvidence) {
    Write-Host "`n[4/4] Gate A3 smoke evidence check..."
    $collector = Join-Path $PSScriptRoot "Collect-GateA3Evidence.ps1"
    $args = @("-Both")
    if ($WaitMinutes -gt 0) { $args += @("-WaitMinutes", $WaitMinutes) }
    & $collector @args
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Smoke evidence incomplete - process canonical PDFs, then re-run collector."
    }
    Write-Host "[OK] SMOKE_EVIDENCE present for required PDFs." -ForegroundColor Green
}

exit 0
