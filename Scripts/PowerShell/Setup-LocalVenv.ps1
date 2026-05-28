#Requires -Version 5.1
<#
.SYNOPSIS
  Recreate the project .venv with Python 3.10 (matches Azure runtime.txt).

.DESCRIPTION
  Stops stale Streamlit/Python processes using this repo's .venv, removes the
  old environment, creates a fresh venv, and installs requirements.txt plus
  dev tools (ruff, black). Run from repo root when pip imports fail after
  package changes.

.EXAMPLE
  .\Scripts\PowerShell\Setup-LocalVenv.ps1
  .\.venv\Scripts\Activate.ps1
  streamlit run App/app.py
#>
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$InstallHeavyOcr
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

Write-Host "=== SLAM Services — Setup Local venv (Python 3.10) ===" -ForegroundColor Cyan

# Stop processes that lock .venv (common after failed pip install or orphaned Streamlit)
Get-Process python, streamlit -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*SLAM-Services-Project*" } |
    ForEach-Object {
        Write-Host "Stopping $($_.ProcessName) (PID $($_.Id))..."
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Seconds 2

if (Test-Path (Join-Path $RepoRoot ".venv")) {
    Write-Host "Removing existing .venv..."
    cmd /c "rmdir /s /q `"$RepoRoot\.venv`""
}

Write-Host "Creating venv with py -3.10..."
py -3.10 -m venv (Join-Path $RepoRoot ".venv")

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $RepoRoot "requirements.txt") ruff black

Write-Host ""
Write-Host "Verifying imports..." -ForegroundColor Green
& $python -c "import numpy, pandas, streamlit, sqlalchemy, psycopg2; print('OK:', pandas.__version__, streamlit.__version__)"

Write-Host ""
Write-Host "Done. Activate with: .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
Write-Host "Run app: streamlit run App/app.py" -ForegroundColor Green

if ($InstallHeavyOcr) {
    Write-Host ""
    Write-Host "Installing heavy OCR + CV packages..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "Install-LocalHeavyOcr.ps1") -RepoRoot $RepoRoot
}

Write-Host ""
Write-Host "=== For Local Enhanced OCR + Azure CV check leg work ===" -ForegroundColor Yellow
Write-Host "After activating the venv, run:" -ForegroundColor Yellow
Write-Host "  .\Scripts\PowerShell\Install-LocalHeavyOcr.ps1" -ForegroundColor Cyan
Write-Host "  (or re-run this script with -InstallHeavyOcr)" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT for pdf2image (check cropper) on Windows:" -ForegroundColor Red
Write-Host "  You MUST have poppler in your PATH. Non-admin method:" -ForegroundColor Red
Write-Host "  1. Download latest from: https://github.com/oschwartz10612/poppler-windows/releases" -ForegroundColor Cyan
Write-Host "  2. Extract to a permanent folder, e.g. C:\Tools\poppler" -ForegroundColor Cyan
Write-Host "  3. Add C:\Tools\poppler\Library\bin to your User PATH (System Properties → Environment Variables)" -ForegroundColor Cyan
Write-Host "  4. Restart this terminal completely." -ForegroundColor Cyan
Write-Host ""
Write-Host "Then create a .env file with AZURE_CV_ENDPOINT / AZURE_CV_KEY or SLAM_CV_CACHE_DIR for the CV path." -ForegroundColor Yellow
Write-Host ""
Write-Host "To run the app on Windows (recommended):" -ForegroundColor Green
Write-Host "  .\run_local.ps1" -ForegroundColor Green
Write-Host "  (loads .env, sets PYTHONPATH, checks poppler)" -ForegroundColor Green
Write-Host ""
Write-Host "To test imports (when diagnosing):" -ForegroundColor Yellow
Write-Host '  $env:PYTHONPATH = "App"; python -c "import local_enhanced_ocr; print(local_enhanced_ocr.detect_capabilities())"' -ForegroundColor Cyan
