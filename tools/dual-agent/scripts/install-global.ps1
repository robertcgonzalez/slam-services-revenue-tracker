# dual-agent Global Installation Script (Windows + PowerShell)
#
# This script installs dual-agent into your personal Grok tools directory:
#   ~/.grok/tools/dual-agent
#
# It also creates a convenient launcher in ~/.grok/bin
#
# After running, add ~/.grok/bin to your PATH (one-time) to use `dual-agent` from anywhere.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== dual-agent Global Installer ===" -ForegroundColor Cyan
Write-Host ""

$grokHome = Join-Path $env:USERPROFILE ".grok"
$toolsDir = Join-Path $grokHome "tools"
$targetDir = Join-Path $toolsDir "dual-agent"
$binDir = Join-Path $grokHome "bin"
$launcherPath = Join-Path $binDir "dual-agent.ps1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Split-Path -Parent $scriptDir

Write-Host "Source:      $sourceDir"
Write-Host "Target:      $targetDir"
Write-Host "Launcher:    $launcherPath"
Write-Host ""

# 1. Create directories
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

# 2. Copy the entire dual-agent source to the global location
if (Test-Path $targetDir) {
    Write-Host "Existing installation found at $targetDir" -ForegroundColor Yellow
    $response = Read-Host "Overwrite existing global installation? (y/N)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "Aborted." -ForegroundColor Red
        exit 1
    }
    Remove-Item -Recurse -Force $targetDir
}

Write-Host "Copying files to global location..."
robocopy $sourceDir $targetDir /E /NFL /NDL /NJH /NJS | Out-Null
Write-Host "Files copied." -ForegroundColor Green

# 3. Detect package manager (uv preferred)
$useUv = $false
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "uv detected — using it for faster setup." -ForegroundColor Green
    $useUv = $true
} else {
    Write-Host "uv not found. Falling back to python -m venv + pip (slower)." -ForegroundColor Yellow
    Write-Host "Tip: Install uv from https://docs.astral.sh/uv/ for much faster installs on Windows." -ForegroundColor DarkGray
}

Set-Location $targetDir

# 4. Create virtual environment
$venvPath = Join-Path $targetDir ".venv"

if (Test-Path $venvPath) {
    Write-Host "Removing old virtual environment..."
    Remove-Item -Recurse -Force $venvPath
}

if ($useUv) {
    Write-Host "Creating venv with uv..."
    uv venv .venv
    Write-Host "Installing dependencies with uv (this is fast)..."
    uv pip install -e .
} else {
    Write-Host "Creating venv with python..."
    python -m venv .venv
    & ".\.venv\Scripts\Activate.ps1"
    Write-Host "Upgrading pip..."
    python -m pip install --upgrade pip | Out-Null
    Write-Host "Installing package (this may take a minute)..."
    pip install -e . | Out-Null
    deactivate
}

Write-Host "Dependencies installed." -ForegroundColor Green

# 5. Create the launcher script in ~/.grok/bin
$launcherContent = @"
# dual-agent launcher (auto-generated)
# This file lives in ~/.grok/bin and should be in your PATH

`$grokHome = "`$env:USERPROFILE\.grok"
`$toolDir = Join-Path `$grokHome "tools\dual-agent"
`$python = Join-Path `$toolDir ".venv\Scripts\python.exe"

if (-not (Test-Path `$python)) {
    Write-Host "dual-agent is not properly installed." -ForegroundColor Red
    Write-Host "Run: ~/.grok/tools/dual-agent/scripts/install-global.ps1 again" -ForegroundColor Yellow
    exit 1
}

# Improve Unicode support on Windows
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONLEGACYWINDOWSSTDIO = "1"

& `$python -m dual_agent `$args
"@

Set-Content -Path $launcherPath -Value $launcherContent -Encoding UTF8
Write-Host "Launcher created at $launcherPath" -ForegroundColor Green

# 6. Copy .env.example if user doesn't have one yet in global location
$globalEnv = Join-Path $targetDir ".env"
$globalEnvExample = Join-Path $targetDir ".env.example"

if (-not (Test-Path $globalEnv) -and (Test-Path $globalEnvExample)) {
    Copy-Item $globalEnvExample $globalEnv
    Write-Host "Created $globalEnv (edit this with your CURSOR_API_KEY)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Add this directory to your PATH (one time):" -ForegroundColor White
Write-Host "   `$env:Path += `";`$env:USERPROFILE\.grok\bin`"" -ForegroundColor Gray
Write-Host "   (Add it permanently in System Environment Variables or your PowerShell profile)"
Write-Host ""
Write-Host "2. Edit your Cursor API key:" -ForegroundColor White
Write-Host "   code $globalEnv" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Test it:" -ForegroundColor White
Write-Host "   dual-agent --help" -ForegroundColor Gray
Write-Host "   dual-agent modes" -ForegroundColor Gray
Write-Host ""
Write-Host "You can now run 'dual-agent' from any directory." -ForegroundColor Green
Write-Host ""
Write-Host "=== Post-install steps (strongly recommended) ===" -ForegroundColor Cyan
Write-Host "1. Run:  dual-agent doctor" -ForegroundColor White
Write-Host "   (This now performs a live Cursor agent creation test — the best validation.)"
Write-Host ""
Write-Host "2. After any future changes to the source in tools/dual-agent/, re-run this script" -ForegroundColor White
Write-Host "   from the source directory to keep your global install in sync." -ForegroundColor White
Write-Host ""
Write-Host "The source tree (tools/dual-agent/ in the repo) is the canonical version." -ForegroundColor DarkGray
Write-Host ""
