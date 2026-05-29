# Dual-Agent Setup Script for Windows + PowerShell
# Run this from the dual-agent directory.
#
# This script now detects uv and will use it automatically if available
# (strongly recommended — much faster on Windows).

$ErrorActionPreference = "Stop"

Write-Host "=== dual-agent setup ===" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location $root

$useUv = $false
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "uv detected — using fast path." -ForegroundColor Green
    $useUv = $true
} else {
    Write-Host "uv not found. Using standard python venv + pip (slower)." -ForegroundColor Yellow
    Write-Host "For much faster installs, get uv: https://docs.astral.sh/uv/" -ForegroundColor DarkGray
}

if ($useUv) {
    uv venv .venv
    uv pip install -e .
} else {
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
        python -m venv .venv
    }

    Write-Host "Activating environment..."
    & ".\.venv\Scripts\Activate.ps1"

    Write-Host "Upgrading pip and installing the package..."
    python -m pip install --upgrade pip
    pip install -e .
}

if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from template..."
    Copy-Item .env.example .env
    Write-Host "IMPORTANT: Edit .env and add your CURSOR_API_KEY" -ForegroundColor Red
    Write-Host "Get the key from: https://cursor.com/dashboard/integrations" -ForegroundColor Yellow
} else {
    Write-Host ".env already exists — leaving it alone."
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Make sure your CURSOR_API_KEY is in .env"
Write-Host "  2. Activate:  .\.venv\Scripts\Activate.ps1"
Write-Host "  3. Run:       dual-agent --help"
Write-Host "  4. Example:   dual-agent run 'Improve the payee extraction rules engine'"
Write-Host ""
Write-Host "Tip: For future global installs, run: .\scripts\install-global.ps1" -ForegroundColor DarkGray
Write-Host ""
