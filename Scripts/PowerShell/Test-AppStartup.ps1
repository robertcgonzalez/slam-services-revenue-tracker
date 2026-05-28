#Requires -Version 5.1
<#
.SYNOPSIS
  Preflight checks before streamlit run — surfaces import errors in the terminal.

.EXAMPLE
  .\Scripts\PowerShell\Test-AppStartup.ps1
#>
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv — run Setup-LocalVenv.ps1 first."
}

$env:PYTHONPATH = "App"
$dotenvPath = Join-Path $RepoRoot ".env"
if (Test-Path $dotenvPath) {
    Get-Content $dotenvPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
        if ($name) { Set-Item -Path "Env:$name" -Value $value }
    }
}

Write-Host "=== SLAM App startup preflight ===" -ForegroundColor Cyan
Write-Host "Python: $python" -ForegroundColor Gray
& $python --version

Write-Host "`n[1/4] Core imports..." -ForegroundColor Yellow
& $python -c "import streamlit, pandas; print('streamlit', streamlit.__version__)"

Write-Host "`n[2/4] App modules..." -ForegroundColor Yellow
& $python -c @"
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(r'$RepoRoot') / '.env')
import bank_statements
print('bank_statements OK')
"@

Write-Host "`n[3/4] Data folder..." -ForegroundColor Yellow
& $python -c @"
from data_paths import resolve_data_path
path, logs = resolve_data_path()
print('DATA_PATH:', path)
if path is None:
    print('WARN: CSV data missing — app will show an error after login, not a blank browser.')
    for line in logs[-5:]:
        print(' ', line)
"@

Write-Host "`n[4/4] Heavy OCR caps (optional)..." -ForegroundColor Yellow
& $python -c @"
import local_enhanced_ocr as o
print(o.detect_capabilities())
"@

Write-Host "`nPreflight passed. Start app with: .\run_local.ps1" -ForegroundColor Green
Write-Host "If browser is blank, use http://127.0.0.1:8501 and read the PowerShell window for tracebacks." -ForegroundColor Yellow
