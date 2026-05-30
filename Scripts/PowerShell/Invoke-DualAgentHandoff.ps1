#Requires -Version 5.1
<#
.SYNOPSIS
  The reliable entry point for automated Grok ↔ Cursor handoffs on the SLAM Services project.

.DESCRIPTION
  This is the preferred way to run dual-agent work. It:
  - Always uses the hardened Python 3.10 venv
  - Automatically runs `dual-agent doctor` first (catches most breakage before it wastes turns)
  - Forces the correct working directory (--cwd) so both agents see the full project
  - Uses robust .env loading (tools/dual-agent/.env takes priority)

  PRIME DIRECTIVE (enforced in the Python orchestrator): full autonomous iteration until the ENTIRE task is complete.
  Agents never produce human summaries mid-run. Old "phase N complete — ready for review" signals are ignored.
  Use higher -MaxTurns (15-30) for ambitious end-to-end goals. The loop will drive every possible code + CLI + verification step.

  ON SLAM: Git changes inside any autonomous run must still pass `.\Scripts\PowerShell\Invoke-GitVerification.ps1` (the canonical gate aligned to the contracts and this Prime Directive). When clean, agents complete the commit + push to main themselves.

  Run this from the repo root. It should now be the "it just works" path.
#>
<#
.DESCRIPTION
  Makes it easy to run phased production fixes from the repo root without manually cd'ing into tools/dual-agent.
  Uses the hardened local Python 3.10 venv.

.EXAMPLE
  # Run the Phase 1 clear command handoff
  .\Scripts\PowerShell\Invoke-DualAgentHandoff.ps1 -Directive "docs/handoffs/azure-startup-fix-phase1-clear-command.md" -MaxTurns 12  # higher for full autonomous runs per prime directive

  # Run a custom task
  .\Scripts\PowerShell\Invoke-DualAgentHandoff.ps1 -Task "Improve error messages in bank_statements.py" -Mode reviewer-implementer

  # Use a different mode
  .\Scripts\PowerShell\Invoke-DualAgentHandoff.ps1 -Directive "docs/handoffs/my-phase.md" -Mode freeform
#>
param(
    [string]$Directive,
    [string]$Task,
    [ValidateSet("reviewer-implementer", "researcher-builder", "freeform", "architect-coder", "critic-refiner")]
    [string]$Mode = "reviewer-implementer",
    [int]$MaxTurns = 12,
    [string]$DualAgentRoot = (Join-Path $PSScriptRoot "..\..\tools\dual-agent"),
    [switch]$SkipDoctor
)

# === Inject Azure credentials for Cursor agent autonomy ===
$azureEnv = @{}
if ($env:AZURE_CLIENT_ID) { $azureEnv['AZURE_CLIENT_ID'] = $env:AZURE_CLIENT_ID }
if ($env:AZURE_CLIENT_SECRET) { $azureEnv['AZURE_CLIENT_SECRET'] = $env:AZURE_CLIENT_SECRET }
if ($env:AZURE_TENANT_ID) { $azureEnv['AZURE_TENANT_ID'] = $env:AZURE_TENANT_ID }

# Merge into the environment the Python process will see
foreach ($key in $azureEnv.Keys) {
    [System.Environment]::SetEnvironmentVariable($key, $azureEnv[$key], 'Process')
}

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not $Directive -and -not $Task) {
    Write-Error "You must provide either -Directive (path to a .md handoff file) or -Task (free text task)."
    exit 1
}

$dualAgentVenvPython = Join-Path $DualAgentRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $dualAgentVenvPython)) {
    Write-Error "Dual-agent Python 3.10 venv not found at $dualAgentVenvPython. Run the setup in tools/dual-agent first."
    exit 1
}

$target = if ($Directive) {
    $directivePath = if ([System.IO.Path]::IsPathRooted($Directive)) { $Directive } else { Join-Path $RepoRoot $Directive }
    if (-not (Test-Path $directivePath)) {
        Write-Error "Directive file not found: $directivePath"
        exit 1
    }
    # Use absolute path with @ prefix — the dual-agent CLI supports file references this way and it is far more reliable than fragile relative string replacement.
    "@$directivePath"
} else {
    $Task
}

Write-Host "=== SLAM Dual-Agent Handoff ===" -ForegroundColor Cyan
Write-Host "Target : $target"
Write-Host "Mode   : $Mode"
Write-Host "MaxTurns: $MaxTurns"
Write-Host "Repo CWD: $RepoRoot (forced for both agents)"
Write-Host "Using  : Python 3.10 venv with hardened Cursor SDK bridge" -ForegroundColor DarkGray
Write-Host ""

# Always run doctor first unless explicitly skipped. This catches 90% of "it broke again" cases before wasting turns.
if (-not $SkipDoctor) {
    Write-Host "Running dual-agent doctor for pre-flight validation..." -ForegroundColor Yellow
    & $dualAgentVenvPython -m dual_agent doctor
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Warning "Doctor reported issues. Fix them above, then re-run this script (or add -SkipDoctor if you are sure)."
        exit 1
    }
    Write-Host ""
}

Push-Location $DualAgentRoot
try {
    # Force the collaboration working directory to the repo root so both Grok and Cursor see the same project context.
    & $dualAgentVenvPython -m dual_agent run $target --mode $Mode --max-turns $MaxTurns --cwd $RepoRoot
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Handoff complete. Transcript saved under .dual-agent-sessions/ in the repo root." -ForegroundColor Green
