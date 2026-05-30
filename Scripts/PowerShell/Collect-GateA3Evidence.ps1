<#
.SYNOPSIS
    Autonomous Gate A3 smoke evidence collector (Kudu logs + optional /tmp sidecars).

.DESCRIPTION
    Harvests SMOKE_EVIDENCE lines from App Service docker logs via Kudu VFS,
    parses metrics, and materializes docs/gate-a3 evidence + scorecard.

    Minimal human flow: upload + process the two canonical PDFs in the browser,
    then run this script — no screenshots, CSV downloads, or manual transcription.

.PARAMETER HCC
    Require only HCC evidence.

.PARAMETER AutoBody
    Require only Auto Body evidence.

.PARAMETER Both
    Require evidence for both canonical PDFs (default when no filter switch).

.PARAMETER Latest
    Use the most recent SMOKE_EVIDENCE per smoke_key (default).

.PARAMETER Minutes
    Only consider log files modified within this window (0 = all recent logs).

.PARAMETER WaitMinutes
    Poll Kudu logs until required evidence appears or timeout.

.PARAMETER UpdateDocs
    Write Gate-A3-Final-Re-Smoke-Evidence-Guide.md, scorecard, and intake bundle.

.PARAMETER DryRun
    Parse and print only; do not update documentation.

.EXAMPLE
    .\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both -UpdateDocs

.EXAMPLE
    .\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both -WaitMinutes 30 -UpdateDocs
#>
[CmdletBinding()]
param(
    [switch]$HCC,
    [switch]$AutoBody,
    [switch]$Both,
    [switch]$Latest,
    [int]$Minutes = 0,
    [int]$WaitMinutes = 0,
    [switch]$UpdateDocs,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$ResourceGroup = "SLAM-Services-RG"
$AppName       = "slam-services-revenue-tracker"
$ScmBase       = "https://$AppName.scm.azurewebsites.net"
$ParserScript  = Join-Path $RepoRoot "Scripts\Python\parse_gate_a3_evidence.py"
$LogDump       = Join-Path $RepoRoot "deploy-logs-temp\gate-a3-smoke-log-harvest.txt"
$BundleDir     = Join-Path $RepoRoot "deploy-logs-temp"

function Get-KuduHeaders {
    $pubJson = az webapp deployment list-publishing-credentials -g $ResourceGroup -n $AppName -o json
    $pub = $pubJson | ConvertFrom-Json
    $token = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("$($pub.publishingUserName):$($pub.publishingPassword)")
    )
    return @{ Authorization = "Basic $token" }
}

function Get-DeployId {
    try {
        $d = az webapp log deployment list -g $ResourceGroup -n $AppName --query "[0].id" -o tsv
        return $d
    } catch { return "" }
}

function Get-RequiredKeys {
    if ($HCC -and -not $AutoBody -and -not $Both) { return @("hcc") }
    if ($AutoBody -and -not $HCC -and -not $Both) { return @("auto_body") }
    return @("hcc", "auto_body")
}

function Harvest-KuduLogs {
    param([hashtable]$Headers)
    $logUri = "$ScmBase/api/vfs/LogFiles/?recursive=true"
    $entries = Invoke-RestMethod -Uri $logUri -Headers $Headers
    $dockerLogs = $entries | Where-Object {
        $_.name -like "*docker.log" -or $_.name -like "*default_docker.log" `
            -or $_.name -like "*containerStream.log"
    } | Sort-Object name -Descending

    if ($Minutes -gt 0) {
        $cutoff = (Get-Date).ToUniversalTime().AddMinutes(-$Minutes)
        $dockerLogs = $dockerLogs | Where-Object {
            $_.modified_time_utc -and [datetime]$_.modified_time_utc -ge $cutoff
        }
    }

    $blob = New-Object System.Text.StringBuilder
    [void]$blob.AppendLine("# Gate A3 log harvest $(Get-Date -Format o)")
    foreach ($log in $dockerLogs | Select-Object -First 10) {
        try {
            $logPath = "$ScmBase/api/vfs/LogFiles/$($log.name)"
            $resp = Invoke-WebRequest -Uri $logPath -Headers $Headers -UseBasicParsing -TimeoutSec 90
            [void]$blob.AppendLine("===== $($log.name) =====")
            [void]$blob.AppendLine($resp.Content)
        } catch {
            Write-Warning "Could not read $($log.name): $_"
        }
    }

    # Headless smoke runner log + sidecars under /tmp (best-effort)
    try {
        $runnerLog = Invoke-WebRequest -Uri "$ScmBase/api/vfs/site/wwwroot/tmp/gate-a3-smoke.log" -Headers $Headers `
            -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
        [void]$blob.AppendLine("===== wwwroot/tmp/gate-a3-smoke.log =====")
        [void]$blob.AppendLine($runnerLog.Content)
    } catch {
        Write-Host "  (no /tmp/gate-a3-smoke.log yet)" -ForegroundColor DarkGray
    }

    try {
        $tmp = Invoke-RestMethod -Uri "$ScmBase/api/vfs/tmp/" -Headers $Headers
        $sidecars = $tmp | Where-Object { $_.name -like "slam-smoke-*.json" }
        foreach ($sc in $sidecars | Sort-Object modified_time_utc -Descending | Select-Object -First 4) {
            $body = Invoke-RestMethod -Uri "$ScmBase/api/vfs/tmp/$($sc.name)" -Headers $Headers
            [void]$blob.AppendLine("===== sidecar $($sc.name) =====")
            [void]$blob.AppendLine(($body | ConvertTo-Json -Depth 8))
        }
    } catch {
        Write-Host "  (no /tmp sidecars or VFS unavailable)" -ForegroundColor DarkGray
    }

    $dir = Split-Path $LogDump -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $text = $blob.ToString()
    Set-Content -Path $LogDump -Value $text -Encoding UTF8
    return $text
}

function Test-EvidenceComplete {
    param([string]$LogText, [string[]]$RequiredKeys)
    $found = @{}
    foreach ($line in ($LogText -split "`n")) {
        if ($line -notmatch 'SMOKE_EVIDENCE') { continue }
        foreach ($key in @("hcc", "auto_body")) {
            if ($line -match "`"smoke_key`":`"$key`"") { $found[$key] = $true }
        }
    }
    $missing = $RequiredKeys | Where-Object { -not $found.ContainsKey($_) }
    return @{ Complete = ($missing.Count -eq 0); Missing = $missing; Found = @($found.Keys) }
}

Write-Host "=== Gate A3 Evidence Collector ===" -ForegroundColor Cyan
$required = Get-RequiredKeys
Write-Host "Required keys: $($required -join ', ')"

$headers = Get-KuduHeaders
$deployId = Get-DeployId
if ($deployId) { Write-Host "Deploy ID: $deployId" }

$deadline = if ($WaitMinutes -gt 0) { (Get-Date).AddMinutes($WaitMinutes) } else { Get-Date }

do {
    Write-Host "`nHarvesting Kudu logs..." -ForegroundColor White
    $logText = Harvest-KuduLogs -Headers $headers
    $check = Test-EvidenceComplete -LogText $logText -RequiredKeys $required

    if ($check.Complete) {
        Write-Host "[OK] Found SMOKE_EVIDENCE for: $($check.Found -join ', ')" -ForegroundColor Green
        break
    }

    $missing = $check.Missing -join ', '
    if ($WaitMinutes -le 0) {
        Write-Error "Incomplete evidence - missing: $missing. Process canonical PDFs on Bank Statements, then re-run."
    }

    Write-Host "Waiting for evidence ($missing)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30
    $headers = Get-KuduHeaders
} while ((Get-Date) -lt $deadline)

if (-not $check.Complete) {
    Write-Error "Timed out after ${WaitMinutes}m - still missing: $($check.Missing -join ', ')"
}

$pyArgs = @(
    $ParserScript,
    "--log-file", $LogDump,
    "--deploy-id", $deployId,
    "--require-both"
)
if ($required.Count -eq 1) {
    $pyArgs = $pyArgs | Where-Object { $_ -ne "--require-both" }
}

if ($UpdateDocs -and -not $DryRun) {
    $pyArgs += "--update-docs"
    $pyArgs += @("--bundle-dir", $BundleDir)
}

Write-Host "`nParsing evidence..." -ForegroundColor White
$python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
& $python @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Poppler marker check in same harvest
if ($logText -match "IMAGING_LEG poppler=ok") {
    Write-Host "[OK] IMAGING_LEG poppler=ok present in harvested logs." -ForegroundColor Green
} else {
    Write-Warning "IMAGING_LEG poppler=ok not found - run Test-GateA3Poppler.ps1 before trusting imaging metrics."
}

Write-Host "`n[PASS] Gate A3 evidence collection complete." -ForegroundColor Green
Write-Host "Log harvest: $LogDump"
if ($UpdateDocs -and -not $DryRun) {
    Write-Host "Updated: docs\gate-a3\Gate-A3-Final-Re-Smoke-Evidence-Guide.md"
    Write-Host "Updated: docs\gate-a3\Gate-A3-Post-Smoke-Scorecard-Scaffolding.md"
    Write-Host "Bundle:    deploy-logs-temp\gate-a3-intake-bundle.json"
}
exit 0
