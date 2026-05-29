<#
.SYNOPSIS
    Helper to launch rapid post-smoke analysis after the human pastes Gate A3 results.

.DESCRIPTION
    After Robert pastes the filled evidence from the smoke, run this script.
    It will guide you to feed the results into Grok (or Cursor) using the dedicated
    intake prompt for fast, high-quality verdict + runbook updates.
#>

$repoRoot = Split-Path $PSScriptRoot -Parent
$intakePrompt = Join-Path $repoRoot "docs\gate-a3\Gate-A3-Results-Intake-Prompt.md"

Write-Host "=== Gate A3 Post-Smoke Analysis Launcher ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Have the human paste the completed evidence (from the template in docs/gate-a3/)."
Write-Host "2. Copy the entire content of:"
Write-Host "   $intakePrompt"
Write-Host ""
Write-Host "3. Paste it into Grok (or Cursor) and append the actual pasted smoke results after the 'Pasted evidence' marker."
Write-Host ""
Write-Host "This will produce the scorecard, verdict, runbook updates, and commit proposal quickly."
Write-Host ""
Write-Host "After analysis, review the output and decide on commits / apply docs / pilot."

if (Test-Path $intakePrompt) {
    $open = Read-Host "Open the intake prompt file now? (Y/n)"
    if ($open -ne 'n' -and $open -ne 'N') {
        Start-Process $intakePrompt
    }
}