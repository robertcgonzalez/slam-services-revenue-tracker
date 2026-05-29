#Requires -Version 5.1
<#
.SYNOPSIS
  Build a flat Azure deployment zip (code-only by default; local Data/ optional).

.DESCRIPTION
  Creates slam-app.zip at repo root with requirements.txt, App/, startup.sh,
  apt.txt, runtime.txt, and Scripts/ at the zip root (no extra parent folder).

  By default omits Data/ so routine deploys stay small and preserve server CSVs
  (App Service deploy uses clean: false). Use -IncludeData when bootstrapping a
  new slot or refreshing CSVs from the laptop.

  Uses .NET ZipFile (not Compress-Archive) for predictable forward-slash entry
  names and smaller archives (excludes __pycache__, local test PDFs, spike/).

.EXAMPLE
  .\Scripts\PowerShell\Build-AzureDeployZip.ps1
  .\Scripts\PowerShell\Deploy-ToAzure.ps1

.EXAMPLE
  .\Scripts\PowerShell\Build-AzureDeployZip.ps1 -IncludeData
  # Full zip with local Data/Revenue_Tracker_Migration (bootstrap only).
#>
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ZipName = "slam-app.zip",
    [switch]$IncludeData
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$dataDir = Join-Path $RepoRoot "Data\Revenue_Tracker_Migration"
$clients = Join-Path $dataDir "Clients.csv"
$requests = Join-Path $dataDir "RevenueRequests.csv"

if ($IncludeData -and ((-not (Test-Path $clients)) -or (-not (Test-Path $requests)))) {
    Write-Warning "Clients.csv / RevenueRequests.csv not found under Data\Revenue_Tracker_Migration."
    Write-Warning "Zip will deploy code only - restore CSVs via Kudu or re-run with local Data present."
}

$zipPath = Join-Path $RepoRoot $ZipName
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

$staging = Join-Path $env:TEMP "slam-deploy-$(Get-Random)"
New-Item -ItemType Directory -Path $staging -Force | Out-Null

function Test-SlamDeployExclude {
    param([string]$RelativePath)
    $rel = $RelativePath -replace '\\', '/'
    if ($rel -match '(^|/)(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache)(/|$)') { return $true }
    if ($rel -match '\.(pyc|pyo)$') { return $true }
    if ($rel -match '(^|/)Scripts/spike(/|$)') { return $true }
    if ($rel -match '(^|/)Scripts/_streamlit_bank_uploads(/|$)') { return $true }
    if ($rel -match '(^|/)Scripts/cropped_checks') { return $true }
    if ($rel -match '(^|/)App/.*\.bak$') { return $true }
    return $false
}

function Copy-SlamDeployTree {
    param(
        [string]$SourceRoot,
        [string]$DestRoot,
        [string]$RelativePrefix = ""
    )
    Get-ChildItem -Path $SourceRoot -Force | ForEach-Object {
        $rel = if ($RelativePrefix) { "$RelativePrefix/$($_.Name)" } else { $_.Name }
        $rel = $rel -replace '\\', '/'
        if (Test-SlamDeployExclude -RelativePath $rel) { return }

        $destPath = Join-Path $DestRoot $_.Name
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Path $destPath -Force | Out-Null
            Copy-SlamDeployTree -SourceRoot $_.FullName -DestRoot $destPath -RelativePrefix $rel
        }
        else {
            $parent = Split-Path $destPath -Parent
            if (-not (Test-Path $parent)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }
            Copy-Item -Path $_.FullName -Destination $destPath -Force
        }
    }
}

function Add-ZipFlatEntry {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$FullPath,
        [string]$EntryName
    )
    $entryName = $EntryName -replace '\\', '/'
    $entry = $Archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    try {
        $bytes = [IO.File]::ReadAllBytes($FullPath)
        $stream.Write($bytes, 0, $bytes.Length)
    }
    finally {
        $stream.Dispose()
    }
}

function Add-ZipDirectoryRecursive {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$SourceDir,
        [string]$ZipPrefix
    )
    $baseLen = $SourceDir.TrimEnd('\').Length + 1
    Get-ChildItem -Path $SourceDir -Recurse -File -Force | ForEach-Object {
        $rel = $_.FullName.Substring($baseLen) -replace '\\', '/'
        $entryName = if ($ZipPrefix) { "$ZipPrefix/$rel" } else { $rel }
        if (Test-SlamDeployExclude -RelativePath $entryName) { return }
        Add-ZipFlatEntry -Archive $Archive -FullPath $_.FullName -EntryName $entryName
    }
}

try {
    $include = @(
        "requirements.txt",
        "runtime.txt",
        "startup.sh",
        "apt.txt",
        "App",
        "Scripts",
        "pyproject.toml"
    )
    if ($IncludeData -and (Test-Path $dataDir)) {
        $include += "Data"
        Write-Host "IncludeData: bundling Data/ in zip." -ForegroundColor Yellow
    }
    else {
        Write-Host "Code-only zip (default): omitting Data/ - server CSVs preserved on deploy." -ForegroundColor Yellow
    }

    foreach ($item in $include) {
        $src = Join-Path $RepoRoot $item
        if (-not (Test-Path $src)) {
            continue
        }
        $dest = Join-Path $staging $item
        if ($item -eq "Scripts") {
            New-Item -ItemType Directory -Path $dest -Force | Out-Null
            Copy-SlamDeployTree -SourceRoot $src -DestRoot $dest
            Write-Host "Scripts/: excluded spike/, __pycache__, test PDFs from deploy zip." -ForegroundColor DarkGray
        }
        elseif ((Get-Item $src).PSIsContainer) {
            New-Item -ItemType Directory -Path $dest -Force | Out-Null
            Copy-SlamDeployTree -SourceRoot $src -DestRoot $dest
        }
        else {
            Copy-Item -Path $src -Destination $dest -Force
        }
    }

    $mustExist = @(
        (Join-Path $staging "requirements.txt"),
        (Join-Path $staging "runtime.txt"),
        (Join-Path $staging "App\app.py"),
        (Join-Path $staging "startup.sh"),
        (Join-Path $staging "apt.txt")
    )
    foreach ($f in $mustExist) {
        if (-not (Test-Path $f)) {
            throw "Staging missing required file: $f"
        }
    }

    # Normalize startup.sh to LF for Linux (Azure wwwroot)
    $startupPath = Join-Path $staging "startup.sh"
    $startupText = [IO.File]::ReadAllText($startupPath) -replace "`r`n", "`n"
    [IO.File]::WriteAllText($startupPath, $startupText, [Text.UTF8Encoding]::new($false))

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipStream = [IO.File]::Open($zipPath, [IO.FileMode]::Create, [IO.FileAccess]::ReadWrite)
    try {
        $archive = New-Object System.IO.Compression.ZipArchive($zipStream, [IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($rootFile in @("requirements.txt", "runtime.txt", "startup.sh", "apt.txt", "pyproject.toml")) {
                $path = Join-Path $staging $rootFile
                if (Test-Path $path) {
                    Add-ZipFlatEntry -Archive $archive -FullPath $path -EntryName $rootFile
                }
            }
            foreach ($dir in @("App", "Scripts", "Data")) {
                $dirPath = Join-Path $staging $dir
                if (Test-Path $dirPath) {
                    Add-ZipDirectoryRecursive -Archive $archive -SourceDir $dirPath -ZipPrefix $dir
                }
            }
        }
        finally {
            $archive.Dispose()
        }
    }
    finally {
        $zipStream.Dispose()
    }

    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $rootNames = @("requirements.txt", "runtime.txt", "startup.sh", "apt.txt")
        foreach ($name in $rootNames) {
            $entry = $zip.Entries | Where-Object {
                ($_.FullName -eq $name) -or ($_.FullName -eq "$name/")
            } | Select-Object -First 1
            if (-not $entry) {
                throw "Zip missing required root entry: $name"
            }
            if ($entry.FullName -match '[\\]') {
                throw "Zip entry must use forward slashes only: $($entry.FullName)"
            }
        }
        $badPaths = $zip.Entries | Where-Object { $_.FullName -match '\\' }
        if ($badPaths) {
            throw "Zip contains backslash paths (breaks Linux extract): $($badPaths[0].FullName)"
        }
        Write-Host "Zip root verified: $($rootNames -join ', ')" -ForegroundColor DarkGray
        Write-Host "Zip entries: $($zip.Entries.Count)" -ForegroundColor DarkGray
    }
    finally {
        $zip.Dispose()
    }

    $zipSizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
    Write-Host "Created flat deployment zip: $zipPath ($zipSizeMb MB)"
    Write-Host "Verify root contains: requirements.txt, apt.txt, App/, startup.sh"
    if ($IncludeData) {
        Write-Host "  Data/ included (bootstrap)."
    }
}
finally {
    if (Test-Path $staging) {
        Remove-Item $staging -Recurse -Force
    }
}
