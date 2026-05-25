#Requires -Version 5.1
<#
.SYNOPSIS
  Set AZURE_OCR_FUNCTION_URL + AZURE_OCR_FUNCTION_KEY in the current PowerShell
  session so a locally-run Streamlit app can talk to the deployed slam-ocr-function
  Azure Function (v2.43.1).

.DESCRIPTION
  Pulls the default function key live from the slam-ocr-function Function App
  using `az functionapp keys list`, then sets both env vars on the current
  process via $env:NAME = value. Optionally writes them into a .env-style file
  for later sourcing.

  The Streamlit Bank Statements page reads these env vars in two places:
    1. azure_ocr_status() in App/bank_statements.py — drives the sidebar
       "Azure OCR Function: configured ✅ / not configured" badge.
    2. run_azure_ocr_pipeline() — actually POSTs the PDF to the Function.

  Both are read at app startup, so after running this script you MUST restart
  Streamlit (Ctrl+C and `streamlit run App/app.py` again) in the same shell.

.PARAMETER ResourceGroup
  Resource group hosting the OCR Function (default: SLAM-OCR-Functions-RG).

.PARAMETER FunctionAppName
  Function App name (default: slam-ocr-function).

.PARAMETER WriteEnvFile
  If set, also writes the two key=value lines into the given file path so it
  can be re-sourced in a future shell via:
      Get-Content <path> | ForEach-Object { $k,$v = $_ -split '=',2; Set-Item "Env:$k" $v }

.PARAMETER Check
  Skip the keys lookup; just print whether the env vars are already set in
  this session (no Azure calls). Useful as a quick "configured?" probe.

.EXAMPLE
  # Most common — set vars in current session, then restart Streamlit in same shell
  . .\Scripts\PowerShell\Set-LocalAzureOcrEnv.ps1
  streamlit run App\app.py

.EXAMPLE
  # Persist to a .env file (DO NOT commit — covered by .gitignore)
  .\Scripts\PowerShell\Set-LocalAzureOcrEnv.ps1 -WriteEnvFile .\.env.local

.NOTES
  Requires: az CLI logged in with reader+keys access to SLAM-OCR-Functions-RG.
  Deployment state as of v2.43.1: the Function is currently running the v2.41
  skeleton stub (returns 0 transactions). Setting these env vars is still
  useful — the Streamlit UI lights up "configured ✅" and a roundtrip call
  succeeds — but the v2.43 real-OCR + check-linking pipeline is NOT live in
  Azure yet (see Blueprint v2.43.1 Change Log for the infra decision tree).
#>
param(
    [string]$ResourceGroup = "SLAM-OCR-Functions-RG",
    [string]$FunctionAppName = "slam-ocr-function",
    [string]$WriteEnvFile = "",
    [switch]$Check
)

$ErrorActionPreference = "Stop"

if ($Check) {
    $haveUrl = -not [string]::IsNullOrWhiteSpace($env:AZURE_OCR_FUNCTION_URL)
    $haveKey = -not [string]::IsNullOrWhiteSpace($env:AZURE_OCR_FUNCTION_KEY)
    Write-Host "AZURE_OCR_FUNCTION_URL: $(if ($haveUrl) {'set'} else {'NOT set'})"
    Write-Host "AZURE_OCR_FUNCTION_KEY: $(if ($haveKey) {'set (' + $env:AZURE_OCR_FUNCTION_KEY.Length + ' chars)'} else {'NOT set'})"
    if ($haveUrl -and $haveKey) {
        Write-Host "OK - Streamlit will show 'Azure OCR Function: configured'." -ForegroundColor Green
    } else {
        Write-Host "Run without -Check to pull the key from Azure and set both vars." -ForegroundColor Yellow
    }
    return
}

$functionUrl = "https://$FunctionAppName.azurewebsites.net/api/ocr/process"

Write-Host "Looking up default function key for $FunctionAppName in $ResourceGroup ..."
try {
    $key = az functionapp keys list `
        --name $FunctionAppName `
        --resource-group $ResourceGroup `
        --query "functionKeys.default" `
        --output tsv 2>$null
} catch {
    Write-Error "az CLI call failed: $($_.Exception.Message). Run 'az login' first."
    return
}

if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Error "Default function key was empty. Check that you have keys read access on $FunctionAppName."
    return
}

$env:AZURE_OCR_FUNCTION_URL = $functionUrl
$env:AZURE_OCR_FUNCTION_KEY = $key

Write-Host "Set in current shell:" -ForegroundColor Green
Write-Host "  AZURE_OCR_FUNCTION_URL = $functionUrl"
Write-Host "  AZURE_OCR_FUNCTION_KEY = (live, $($key.Length) chars)"

if ($WriteEnvFile) {
    $parent = Split-Path -Parent $WriteEnvFile
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    @(
        "AZURE_OCR_FUNCTION_URL=$functionUrl",
        "AZURE_OCR_FUNCTION_KEY=$key"
    ) | Out-File -Encoding ascii -FilePath $WriteEnvFile -Force
    Write-Host "Wrote env file: $WriteEnvFile" -ForegroundColor Green
    Write-Host "  (covered by .gitignore -- do NOT commit)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Quick health probe:" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "https://$FunctionAppName.azurewebsites.net/api/ocr/health" -TimeoutSec 30
    Write-Host "  $FunctionAppName/api/ocr/health -> status=$($health.status) version=$($health.version)"
    if ($health.version -like "*skeleton*") {
        Write-Host "  WARNING: deployed Function is still the v2.41 skeleton — Azure OCR mode will" -ForegroundColor Yellow
        Write-Host "  return 0 transactions until v2.43 is actually deployed (see Blueprint v2.43.1)." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Health probe failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next: restart Streamlit IN THIS SAME SHELL to pick up the env vars:" -ForegroundColor Cyan
Write-Host "  streamlit run App\app.py"
