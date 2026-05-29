# Fast setup using uv (recommended on Windows)
# Run this from the dual-agent directory.

$ErrorActionPreference = "Stop"

Write-Host "=== dual-agent fast setup with uv ===" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location $root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is not installed." -ForegroundColor Red
    Write-Host "Install it from: https://docs.astral.sh/uv/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installing uv, re-run this script." -ForegroundColor Yellow
    exit 1
}

Write-Host "uv found. Creating environment and installing dependencies..."

# Create venv + install in one go (very fast)
uv venv .venv
uv pip install -e .

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "Created .env — please add your CURSOR_API_KEY before first use." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete (using uv)!" -ForegroundColor Green
Write-Host ""
Write-Host "Activate with:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "Then run:" -ForegroundColor Cyan
Write-Host "  dual-agent --help" -ForegroundColor Gray
Write-Host ""
