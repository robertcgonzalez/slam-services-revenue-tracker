#Requires -Version 5.1
<#
.SYNOPSIS
  Build a flat Azure deployment zip including Data/ (local only — never commit zip or CSVs).

.DESCRIPTION
  Creates slam-app.zip at repo root with requirements.txt, App/, Data/, startup.sh,
  runtime.txt, and Scripts/ at the zip root (no extra parent folder).

.EXAMPLE
  .\Scripts\PowerShell\Build-AzureDeployZip.ps1
  az webapp deployment source config-zip -g SLAM-Services-RG -n slam-services-revenue-tracker --src slam-app.zip
#>
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ZipName = "slam-app.zip"
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$dataDir = Join-Path $RepoRoot "Data\Revenue_Tracker_Migration"
$clients = Join-Path $dataDir "Clients.csv"
$requests = Join-Path $dataDir "RevenueRequests.csv"

if (-not (Test-Path $clients) -or -not (Test-Path $requests)) {
    Write-Warning "Clients.csv / RevenueRequests.csv not found under Data\Revenue_Tracker_Migration."
    Write-Warning "Zip will deploy code only — restore CSVs via Kudu or re-run with local Data present."
}

$zipPath = Join-Path $RepoRoot $ZipName
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

$staging = Join-Path $env:TEMP "slam-deploy-$(Get-Random)"
New-Item -ItemType Directory -Path $staging -Force | Out-Null

try {
    $include = @(
        "requirements.txt",
        "runtime.txt",
        "startup.sh",
        "App",
        "Scripts",
        "pyproject.toml"
    )
    if (Test-Path $dataDir) {
        $include += "Data"
    }

    foreach ($item in $include) {
        $src = Join-Path $RepoRoot $item
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $staging $item) -Recurse -Force
        }
    }

  # Verify flat layout
    $mustExist = @(
        (Join-Path $staging "requirements.txt"),
        (Join-Path $staging "App\app.py"),
        (Join-Path $staging "startup.sh")
    )
    foreach ($f in $mustExist) {
        if (-not (Test-Path $f)) {
            throw "Staging missing required file: $f"
        }
    }

    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force
    Write-Host "Created flat deployment zip: $zipPath"
    Write-Host "Verify root contains: requirements.txt, App/, startup.sh, Data/ (if local data present)"
}
finally {
    if (Test-Path $staging) {
        Remove-Item $staging -Recurse -Force
    }
}
