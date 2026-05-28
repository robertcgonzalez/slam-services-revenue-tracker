#Requires -Version 5.1
<#
.SYNOPSIS
  Sync repo-root .env with Azure Document Intelligence (slam-bank-statements).

.DESCRIPTION
  Pulls endpoint + key1 from the FormRecognizer resource `slam-bank-statements` in
  SLAM-Services-RG and writes:

    AZURE_DI_ENDPOINT
    AZURE_DI_KEY
    AZURE_DI_MODEL=prebuilt-bankStatement.us
    AZURE_DI_CHECK_MODEL=prebuilt-check.us

  Also sets AZURE_OCR_FUNCTION_URL / AZURE_OCR_FUNCTION_KEY to the same values for
  backward compatibility with older env var names.

  Bank Statements: register/tabular via Document Intelligence (this resource). Check-image
  pages prefer Content Understanding when CONTENTUNDERSTANDING_* is set in .env; otherwise
  prebuilt-check.us on this DI resource (see Set-LocalAzureContentUnderstandingEnv.ps1).

.EXAMPLE
  .\Scripts\PowerShell\Set-LocalAzureBankStatementEnv.ps1
  .\run_local.ps1
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$AccountName = "slam-bank-statements",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $EnvFile) {
    $EnvFile = Join-Path $RepoRoot ".env"
}

Write-Host "Azure Document Intelligence — $AccountName ($ResourceGroup)" -ForegroundColor Cyan

$endpoint = az cognitiveservices account show `
    --name $AccountName `
    --resource-group $ResourceGroup `
    --query "properties.endpoint" `
    --output tsv
if ([string]::IsNullOrWhiteSpace($endpoint)) {
    Write-Error "Could not read endpoint for $AccountName."
}

$key = az cognitiveservices account keys list `
    --name $AccountName `
    --resource-group $ResourceGroup `
    --query "key1" `
    --output tsv
if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Error "Could not read key1 for $AccountName."
}

$lines = @{
    "AZURE_DI_ENDPOINT"          = $endpoint.Trim()
    "AZURE_DI_KEY"              = $key.Trim()
    "AZURE_DI_MODEL"            = "prebuilt-bankStatement.us"
    "AZURE_DI_CHECK_MODEL"      = "prebuilt-check.us"
    "AZURE_OCR_FUNCTION_URL"    = $endpoint.Trim()
    "AZURE_OCR_FUNCTION_KEY"    = $key.Trim()
    "SLAM_IMAGING_FIRST_PAGE"   = "5"
    "SLAM_IMAGING_LAST_PAGE"    = "9"
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

if (-not $replaced.ContainsKey("AZURE_DI_ENDPOINT")) {
    if ($out.Count -gt 0 -and $out[$out.Count - 1] -ne "") { $out.Add("") }
    $out.Add("# Azure Document Intelligence — synced by Set-LocalAzureBankStatementEnv.ps1")
    foreach ($kv in $lines.GetEnumerator() | Sort-Object Name) {
        if (-not $replaced.ContainsKey($kv.Key)) {
            $out.Add("$($kv.Key)=$($kv.Value)")
        }
    }
}

$out | Set-Content -Path $EnvFile -Encoding UTF8
$sku = az cognitiveservices account show `
    --name $AccountName `
    --resource-group $ResourceGroup `
    --query "sku.name" `
    --output tsv

Write-Host "Updated: $EnvFile" -ForegroundColor Green
Write-Host "  AZURE_DI_ENDPOINT = $($endpoint.Trim())"
Write-Host "  AZURE_DI_KEY      = ($($key.Length) chars)"
Write-Host "  SKU               = $sku"
Write-Host "  Models: prebuilt-bankStatement.us + prebuilt-check.us"
if ($sku -eq "F0") {
    Write-Host ""
    Write-Host "WARNING: F0 (free) tier may limit PDF pages analyzed. For full 10-page" -ForegroundColor Yellow
    Write-Host "statements, upgrade slam-bank-statements to S0 in Azure Portal." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Restart Streamlit after this script (full stop, then .\run_local.ps1)." -ForegroundColor Yellow
