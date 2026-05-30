<#
.SYNOPSIS
    Launch autonomous Gate A3 post-smoke collection (replaces manual paste workflow).

.DESCRIPTION
    Delegates to Collect-GateA3Evidence.ps1. After minimal browser smoke (two canonical PDFs),
    run this script to harvest logs, parse metrics, and update gate-a3 documentation.
#>
$ErrorActionPreference = 'Stop'
$collector = Join-Path $PSScriptRoot "PowerShell\Collect-GateA3Evidence.ps1"

Write-Host "=== Gate A3 Autonomous Results ===" -ForegroundColor Cyan
Write-Host "Harvesting SMOKE_EVIDENCE from Azure and updating docs..."
Write-Host ""

& $collector -Both -UpdateDocs @args
exit $LASTEXITCODE
