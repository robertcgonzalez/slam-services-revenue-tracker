<#
.SYNOPSIS
    Launcher for the Gate A3 Live Orchestration procedure from a Grok CLI prompt.

.DESCRIPTION
    This script provides a clean, repeatable way to launch the full Gate A3 preparation
    work (runbook updates, checklists, evidence templates, post-smoke analysis scaffolding)
    from a Grok-side prompt.

    It supports two modes:
    1. Grok CLI direct (recommended for now) - produces rich output you can hand to Cursor.
    2. dual-agent tool (once CURSOR_API_KEY is configured and the handoff is validated).

    The procedure respects all constitutional rules: Cursor as primary executor,
    single hard limit on live browser smoke with real PDFs, runbook as SSOT,
    full git verification before any commits.

.EXAMPLE
    .\Scripts\Launch-GateA3Orchestration.ps1

.EXAMPLE
    .\Scripts\Launch-GateA3Orchestration.ps1 -Mode DualAgent -MaxTurns 10
#>

[CmdletBinding()]
param(
    [ValidateSet("GrokCLI", "DualAgent")]
    [string]$Mode = "GrokCLI",

    [int]$MaxTurns = 12,

    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$directive = Join-Path $repoRoot "docs\gate-a3\Gate-A3-Orchestration-Launch-Directive.md"
$outputDir = Join-Path $repoRoot "docs\gate-a3"
$outputFile = Join-Path $outputDir "gate-a3-launch-output.md"

if (-not (Test-Path $directive)) {
    Write-Error "Launch directive not found at $directive. Run from the repo root or ensure the file exists."
}

Write-Host "=== SLAM Services Gate A3 Orchestration Launcher ===" -ForegroundColor Cyan
Write-Host "Mode: $Mode"
Write-Host "Directive: $directive"
Write-Host ""

switch ($Mode) {
    "GrokCLI" {
        Write-Host "Launching via grok CLI (recommended path)..." -ForegroundColor Green

        $grokCmd = "grok -p `"@$directive`" --cwd `"$repoRoot`" --output-format markdown > `"$outputFile`""

        if ($WhatIf) {
            Write-Host "[WHATIF] Would run: $grokCmd" -ForegroundColor Yellow
            return
        }

        Write-Host "Executing: grok -p @docs/gate-a3/Gate-A3-Orchestration-Launch-Directive.md ..."
        Push-Location $repoRoot
        try {
            grok -p "@$directive" --cwd $repoRoot --output-format markdown | Out-File -FilePath $outputFile -Encoding UTF8
            Write-Host "Success. Output written to: $outputFile" -ForegroundColor Green
            Write-Host ""
            Write-Host "Next steps:" -ForegroundColor Cyan
            Write-Host "1. Review the generated output."
            Write-Host "2. Paste the relevant sections (or the whole directive) to Cursor with instructions to execute the mandate."
            Write-Host "3. Cursor will update the runbook and produce the Gate A3 checklist + templates."
        }
        finally {
            Pop-Location
        }
    }

    "DualAgent" {
        Write-Host "Launching via dual-agent tool (autonomous Grok ↔ Cursor loop)..." -ForegroundColor Green

        $dualAgentCmd = "dual-agent run `"@$directive`" --mode reviewer-implementer --max-turns $MaxTurns"

        if ($WhatIf) {
            Write-Host "[WHATIF] Would run: $dualAgentCmd" -ForegroundColor Yellow
            return
        }

        # Check for key first
        $envFile = Join-Path $repoRoot ".env"
        if (-not (Test-Path $envFile)) {
            Write-Warning ".env file not found. dual-agent requires CURSOR_API_KEY."
        }

        Write-Host "Running: dual-agent run ... (this will create a real bidirectional session)"
        & dual-agent run "@$directive" --mode reviewer-implementer --max-turns $MaxTurns

        Write-Host ""
        Write-Host "dual-agent session completed. Check the session transcript for artifacts produced."
        Write-Host "You can resume with: dual-agent resume <session-id>"
    }
}

Write-Host ""
Write-Host ""
Write-Host "=== Next Steps After Launch ===" -ForegroundColor Cyan
Write-Host "1. Review the generated output file."
Write-Host "2. Feed it (or the directive) to Cursor with maximum autonomy instructions."
Write-Host "3. Cursor will update the runbook + produce/refine Gate A3 artifacts."
Write-Host ""
Write-Host "Reminder (hard limit): Cursor must NEVER perform the live browser re-smoke with real PDFs."
Write-Host "All git operations must use the canonical verifier: .\Scripts\PowerShell\Invoke-GitVerification.ps1 (Prime Directive aligned, single source per contracts)."
Write-Host ""

if (Test-Path $outputFile) {
    Write-Host "Output file ready: $outputFile" -ForegroundColor Green
    $open = Read-Host "Open the output file now in default editor? (Y/n)"
    if ($open -ne 'n' -and $open -ne 'N') {
        Start-Process $outputFile
    }
}