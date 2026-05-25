#Requires -Version 5.1
<#
.SYNOPSIS
  Refresh PostgreSQL from local/Azure CSVs (v2.31 daily-driver ops).

.DESCRIPTION
  Runs migrate_to_postgres.py (idempotent upsert) then health_check.py.
  Use after Laura/Stef update RevenueRequests.csv on disk or when CSV is source of truth.

.EXAMPLE
  .\Scripts\PowerShell\Sync-DataRefresh.ps1
  .\Scripts\PowerShell\Sync-DataRefresh.ps1 -DryRun
#>
param(
    [switch]$DryRun,
    [string]$DataPath = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "=== Step 1: CSV health ==="
& $python Scripts/health_check.py --csv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== Step 2: Migrate CSV -> PostgreSQL ==="
$migrateArgs = @("Scripts/migrate_to_postgres.py")
if ($DryRun) { $migrateArgs += "--dry-run" }
if ($DataPath) { $migrateArgs += "--data-path", $DataPath }
& $python @migrateArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($DryRun) {
    Write-Host "Dry run complete — no database writes."
    exit 0
}

Write-Host "=== Step 3: PostgreSQL health ==="
& $python Scripts/health_check.py
exit $LASTEXITCODE
