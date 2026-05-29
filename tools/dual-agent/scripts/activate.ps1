# Quick activation helper for dual-agent development
# Usage:  . .\scripts\activate.ps1

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (Test-Path ".venv\Scripts\Activate.ps1") {
    & ".\.venv\Scripts\Activate.ps1"
    Write-Host "Activated dual-agent venv" -ForegroundColor Green
    Write-Host "Run: dual-agent --help" -ForegroundColor Cyan
} else {
    Write-Host "No .venv found. Run scripts\setup.ps1 first." -ForegroundColor Red
}
