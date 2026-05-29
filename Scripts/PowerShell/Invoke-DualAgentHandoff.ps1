#Requires -Version 5.1
<#
.SYNOPSIS
  Convenient wrapper to launch automated Grok ↔ Cursor handoffs using the project's dual-agent tool.

.DESCRIPTION
  Makes it easy to run phased production fixes (like the Azure startup error recovery) from the repo root
  without manually cd'ing into tools/dual-agent and activating the Python 3.10 venv.

  Uses the hardened local venv (Python 3.10 + bridge compatibility shims) that was validated during the
  May 2026 Azure Application Error incident.

.EXAMPLE
  # Run the Phase 1 clear command handoff
  .\Scripts\PowerShell\Invoke-DualAgentHandoff.ps1 -Directive "docs/handoffs/azure-startup-fix-phase1-clear-command.md" -MaxTurns 4

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
    [int]$MaxTurns = 6,
    [string]$DualAgentRoot = (Join-Path $PSScriptRoot "..\..\tools\dual-agent")
)

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
    # Make path relative to repo root if needed, then reference from dual-agent dir
    $directivePath = if ([System.IO.Path]::IsPathRooted($Directive)) { $Directive } else { Join-Path $RepoRoot $Directive }
    if (-not (Test-Path $directivePath)) {
        Write-Error "Directive file not found: $directivePath"
        exit 1
    }
    $relativeFromDualAgent = (Resolve-Path $directivePath).Path.Replace($RepoRoot, "..\..").TrimStart('\','/')
    "@$relativeFromDualAgent"
} else {
    $Task
}

Write-Host "=== SLAM Dual-Agent Handoff ===" -ForegroundColor Cyan
Write-Host "Target : $target"
Write-Host "Mode   : $Mode"
Write-Host "MaxTurns: $MaxTurns"
Write-Host "Using  : Python 3.10 venv with hardened Cursor SDK bridge + robust handoff (source = single truth)" -ForegroundColor DarkGray
Write-Host ""

Push-Location $DualAgentRoot
try {
    & $dualAgentVenvPython -m dual_agent run $target --mode $Mode --max-turns $MaxTurns
} finally {
    Pop-Location
}

Write-Host "`nHandoff complete. Review the transcript above or in .dual-agent-sessions/." -ForegroundColor Green
