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
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
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
Write-Host "Run app: streamlit run App/app.py"
