#Requires -Version 5.1
<#
.SYNOPSIS
    Canonical, single-source implementation of the mandatory SLAM Services git verification sequence.

.DESCRIPTION
    This is the ONLY authoritative implementation of the "full git verification sequence" required by:
      - .cursor/rules/slam-services.mdc (Cursor primary agent contract)
      - .grok/AGENT.md (Grok secondary agent contract)
      - docs/memorialization-discipline.md (Session Close checklist)
      - CONSTITUTION.md (agent operating model)

    It is the hygienic gate that MUST be executed before any git add / commit / push by humans or agents
    (including inside dual-agent orchestrator loops).

    Alignment note (Prime Directive, tools/dual-agent/dual_agent/orchestrator.py):
    Inside any dual-agent autonomous run, agents are required to execute every production-touching step
    themselves. This script is the standardized, callable form of the verification so agents can invoke it
    atomically, inspect the result, and — when clean — proceed directly to commit + push to origin main
    without handing any sequence or commands to a human.

    Exit code 0  = verification passed cleanly (safe to commit/push per policy)
    Exit code 1  = issues detected (sensitive paths, unignored secrets, etc.) — DO NOT COMMIT

    The script never performs git add/commit/push itself. That decision remains with the caller
    (per the 4-step memorialization checklist).

.EXAMPLE
    .\Scripts\PowerShell\Invoke-GitVerification.ps1
    if ($LASTEXITCODE -eq 0) {
        git add -A
        git commit -m "feat: ..."
        git push origin main
    }

.NOTES
    Single source of truth. Do not duplicate the command sequence elsewhere.
    Update this script (and bump the version comment) when .gitignore sensitive patterns change materially.
    Future: A Python equivalent may be added under Scripts/Python/ for non-Windows dual-agent contexts.
#>

[CmdletBinding()]
param(
    [switch]$Quiet,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptVersion = "1.0.1"  # 2026-05-30: safelist docs/security/*.md setup guides (not secret stores)

function Test-IsSecuritySetupGuideDoc {
    param([string]$Path)
    # Committed markdown setup guides under docs/security/ are documentation, not credential files.
    return $Path -match '^docs/security/.+\.md$'
}

function Write-Section($title) {
    if (-not $Quiet) {
        Write-Host ""
        Write-Host "=== $title ===" -ForegroundColor Cyan
    }
}

$issues = @()
$clean = $true

# 1. Basic status
Write-Section "GIT STATUS"
git status --short

# 2. Staged diff summary (what would actually be committed)
Write-Section "STAGED CHANGES (git diff --cached --stat)"
git diff --cached --stat

# 3. Explicit sensitive-path scan on staged files (belt-and-suspenders beyond .gitignore)
Write-Section "SENSITIVE PATH SCAN — STAGED"
$stagedRaw = git diff --cached --name-only 2>$null
$staged = @($stagedRaw | Where-Object { $_ -and $_.Trim() })
$sensitivePatterns = @(
    'Data/',
    '\.csv$',
    '\.xlsx$',
    '\.xls$',
    '\.env$',
    '\.log$',
    '\.zip$',
    'deploy-logs',
    'Project-Structure-Report',
    '.*-report\.txt$',
    '\.secret',
    'credentials',
    'SLAM_APP_PASSWORD'
)

foreach ($file in $staged) {
    if (Test-IsSecuritySetupGuideDoc $file) { continue }
    foreach ($pat in $sensitivePatterns) {
        if ($file -match $pat) {
            $issues += "STAGED SENSITIVE: $file (matched $pat)"
            $clean = $false
        }
    }
}

if ($staged.Count -eq 0) {
    Write-Host "(no staged files)" -ForegroundColor DarkGray
}

# 4. Untracked / ignored check for dangerous items that should never be committed
Write-Section "UNTRACKED / IGNORED SENSITIVE CHECK (git ls-files --others --exclude-standard)"
$untrackedRaw = git ls-files --others --exclude-standard 2>$null
$untracked = @($untrackedRaw | Where-Object { $_ -and $_.Trim() })
foreach ($file in $untracked) {
    if (Test-IsSecuritySetupGuideDoc $file) { continue }
    foreach ($pat in $sensitivePatterns) {
        if ($file -match $pat) {
            $issues += "UNTRACKED SENSITIVE (would be addable): $file (matched $pat)"
            $clean = $false
        }
    }
}

# 5. git check-ignore -v on the whole tree (respects .gitignore as the primary defense)
Write-Section "GIT CHECK-IGNORE -V (current .gitignore defense)"
$ignored = git check-ignore -v . 2>$null | Select-String -Pattern "(Data/|\.csv|\.env|secrets|logs|\.zip|report)" | Select-Object -First 30
if ($ignored) {
    $ignored | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "(no high-signal ignored sensitive paths surfaced in top 30)" -ForegroundColor DarkGray
}

# Final summary
Write-Section "VERIFICATION SUMMARY (Invoke-GitVerification.ps1 v$scriptVersion)"

if ($clean -and ($issues.Count -eq 0)) {
    Write-Host "RESULT: CLEAN" -ForegroundColor Green
    Write-Host "No sensitive client data, secrets, logs, zips, or deploy artifacts detected in staged or high-risk untracked files."
    Write-Host "Per project contracts and Prime Directive, it is safe to proceed with commit + push to origin main."
    $exitCode = 0
} else {
    Write-Host "RESULT: ISSUES DETECTED — DO NOT COMMIT" -ForegroundColor Red
    Write-Host ""
    foreach ($i in $issues) {
        Write-Host "  - $i" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Remediate (git restore, .gitignore update, or manual removal) then re-run this script."
    Write-Host "Only when this script exits 0 is the tree considered verified for autonomous commit+push."
    $exitCode = 1
}

if ($Json) {
    $result = [pscustomobject]@{
        version     = $scriptVersion
        timestamp   = (Get-Date).ToString("o")
        clean       = ($exitCode -eq 0)
        issues      = $issues
        stagedCount = $staged.Count
    }
    $result | ConvertTo-Json -Depth 3
}

exit $exitCode
