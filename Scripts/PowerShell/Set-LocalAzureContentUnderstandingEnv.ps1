#Requires -Version 5.1
<#
.SYNOPSIS
  Add Content Understanding (Foundry) variables to repo-root .env.

.DESCRIPTION
  Bank statement check-image pages use Azure AI Content Understanding when these are set:

    CONTENTUNDERSTANDING_ENDPOINT=https://<your-project>.services.ai.azure.com
    CONTENTUNDERSTANDING_KEY=<key>
    CONTENTUNDERSTANDING_CHECK_ANALYZER=prebuilt-check.us

  Register/tabular pages still use Document Intelligence (slam-bank-statements) via
  Set-LocalAzureBankStatementEnv.ps1.

  This script does NOT auto-discover a Foundry endpoint in SLAM-Services-RG today — create
  a Microsoft Foundry resource in Azure AI Studio, enable Content Understanding, deploy
  default GPT-4.1 / text-embedding-3-large, then paste endpoint + key below or pass -Endpoint
  and -Key.

.EXAMPLE
  .\Scripts\PowerShell\Set-LocalAzureContentUnderstandingEnv.ps1 `
    -Endpoint "https://my-foundry.services.ai.azure.com" `
    -Key "<your-key>"
#>
param(
    [string]$Endpoint = "",
    [string]$Key = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $EnvFile) {
    $EnvFile = Join-Path $RepoRoot ".env"
}

if ([string]::IsNullOrWhiteSpace($Endpoint)) {
    Write-Host "Content Understanding — manual setup" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1. Azure AI Studio -> your Foundry project -> Keys and endpoint"
    Write-Host "  2. Copy the endpoint (must end with .services.ai.azure.com)"
    Write-Host "  3. Re-run with -Endpoint and -Key, or add to .env:"
    Write-Host ""
    Write-Host "     CONTENTUNDERSTANDING_ENDPOINT=https://<project>.services.ai.azure.com"
    Write-Host "     CONTENTUNDERSTANDING_KEY=<key>"
    Write-Host "     CONTENTUNDERSTANDING_CHECK_ANALYZER=prebuilt-check.us"
    Write-Host ""
    exit 0
}

$endpoint = $Endpoint.Trim().TrimEnd("/")
if ($endpoint -notmatch "\.services\.ai\.azure\.com") {
    Write-Warning "Endpoint should be a Foundry URL (*.services.ai.azure.com), not cognitiveservices.azure.com."
}

if ([string]::IsNullOrWhiteSpace($Key)) {
    Write-Error "Pass -Key with the Foundry API key."
}

$lines = @{
    "CONTENTUNDERSTANDING_ENDPOINT"       = $endpoint
    "CONTENTUNDERSTANDING_KEY"            = $Key.Trim()
    "CONTENTUNDERSTANDING_CHECK_ANALYZER" = "prebuilt-check.us"
}

$existing = @()
if (Test-Path $EnvFile) {
    $existing = Get-Content $EnvFile -Encoding UTF8
}

$out = New-Object System.Collections.Generic.List[string]
$replaced = @{}
foreach ($line in $existing) {
    $trim = $line.Trim()
    if (-not $trim -or $trim.StartsWith("#")) {
        $out.Add($line)
        continue
    }
    $eq = $trim.IndexOf("=")
    if ($eq -lt 1) {
        $out.Add($line)
        continue
    }
    $name = $trim.Substring(0, $eq).Trim()
    if ($lines.ContainsKey($name)) {
        $out.Add("$name=$($lines[$name])")
        $replaced[$name] = $true
    } else {
        $out.Add($line)
    }
}

if (-not $replaced.ContainsKey("CONTENTUNDERSTANDING_ENDPOINT")) {
    if ($out.Count -gt 0 -and $out[$out.Count - 1] -ne "") { $out.Add("") }
    $out.Add("# Azure Content Understanding (check imaging pages)")
    foreach ($kv in $lines.GetEnumerator() | Sort-Object Name) {
        if (-not $replaced.ContainsKey($kv.Key)) {
            $out.Add("$($kv.Key)=$($kv.Value)")
        }
    }
}

$out | Set-Content -Path $EnvFile -Encoding UTF8
Write-Host "Updated: $EnvFile" -ForegroundColor Green
Write-Host "  CONTENTUNDERSTANDING_ENDPOINT = $endpoint"
Write-Host "  CONTENTUNDERSTANDING_KEY      = ($($Key.Length) chars)"
Write-Host ""
Write-Host "Restart Streamlit after updating .env (.\run_local.ps1)." -ForegroundColor Yellow
