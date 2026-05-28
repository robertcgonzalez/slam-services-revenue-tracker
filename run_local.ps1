# Helper script for local Windows development of the SLAM app
# Usage: .\run_local.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$streamlit = Join-Path $RepoRoot ".venv\Scripts\streamlit.exe"

if (-not (Test-Path $python)) {
    Write-Host "ERROR: .venv not found. Run .\Scripts\PowerShell\Setup-LocalVenv.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Using venv Python: $python" -ForegroundColor Cyan
$env:PYTHONPATH = "App"

$dotenvPath = Join-Path $RepoRoot ".env"
if (Test-Path $dotenvPath) {
    Write-Host "Loading .env from repo root..." -ForegroundColor Cyan
    Get-Content $dotenvPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
        if ($name) { Set-Item -Path "Env:$name" -Value $value }
    }
} else {
    Write-Host "No .env found — copy Scripts\spike\cv-read.env.sample to .env for Azure CV / Postgres." -ForegroundColor Yellow
}

# Free port 8501 if a stale Streamlit left it bound (common cause of ERR_EMPTY_RESPONSE)
try {
    $conn = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $stalePid = $conn.OwningProcess
        Write-Host "Port 8501 in use (PID $stalePid) — stopping stale process..." -ForegroundColor Yellow
        Stop-Process -Id $stalePid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
} catch {
    Write-Host "Could not auto-check port 8501 (run: netstat -ano | findstr :8501)" -ForegroundColor DarkYellow
}

Write-Host "Preflight import check..." -ForegroundColor Cyan
& $python -c @"
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(r'$RepoRoot') / '.env')
import streamlit
import bank_statements
print('Preflight OK — streamlit', streamlit.__version__)
"@
if ($LASTEXITCODE -ne 0) {
    Write-Host "Import failed. Run .\Scripts\PowerShell\Test-AppStartup.ps1 for details." -ForegroundColor Red
    exit 1
}

Write-Host "Checking for poppler (pdftoppm)..." -ForegroundColor Yellow
try {
    $pdftoppm = Get-Command pdftoppm -ErrorAction Stop
    Write-Host "poppler found at $($pdftoppm.Source)" -ForegroundColor Green
} catch {
    Write-Host "WARNING: pdftoppm not found in PATH. The check cropper will not work." -ForegroundColor Red
    Write-Host "Download from https://github.com/oschwartz10612/poppler-windows/releases and add the bin folder to PATH." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting Streamlit..." -ForegroundColor Green
Write-Host "Open http://127.0.0.1:8501 (not only localhost) after you see the URL in this window." -ForegroundColor Green
Write-Host "Leave this window open — if the app crashes, the traceback appears here." -ForegroundColor Yellow
Write-Host ""

if (Test-Path $streamlit) {
    & $streamlit run App/app.py `
        --logger.level=debug `
        --server.address=127.0.0.1 `
        --server.port=8501
} else {
    & $python -m streamlit run App/app.py `
        --logger.level=debug `
        --server.address=127.0.0.1 `
        --server.port=8501
}
