#Requires -Version 5.1
<#
.SYNOPSIS
  Sync dedicated check-imaging Document Intelligence resource into repo-root .env.

.DESCRIPTION
  Writes keys for resource `slam-check-reader` (FormRecognizer S0) used for
  ``prebuilt-check.us`` on statement imaging pages (5–9 by default).

  Register/tabular pages remain on `slam-bank-statements` via Set-LocalAzureBankStatementEnv.ps1.

  This is Document Intelligence (*.cognitiveservices.azure.com), not Foundry Content
  Understanding (*.services.ai.azure.com). Content Understanding Studio can target the
  same prebuilt-check.us model; the app uses the DI API on this resource.

.EXAMPLE
  .\Scripts\PowerShell\Set-LocalAzureCheckReaderEnv.ps1
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$AccountName = "slam-check-reader",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $EnvFile) {
    $EnvFile = Join-Path $RepoRoot ".env"
}

Write-Host "Azure check reader — $AccountName ($ResourceGroup)" -ForegroundColor Cyan

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
    "AZURE_DI_CHECK_ENDPOINT" = $endpoint.Trim()
    "AZURE_DI_CHECK_KEY"      = $key.Trim()
    "AZURE_DI_CHECK_MODEL"    = "prebuilt-check.us"
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

if (-not $replaced.ContainsKey("AZURE_DI_CHECK_ENDPOINT")) {
    if ($out.Count -gt 0 -and $out[$out.Count - 1] -ne "") { $out.Add("") }
    $out.Add("# Check imaging — slam-check-reader (Set-LocalAzureCheckReaderEnv.ps1)")
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
Write-Host "  AZURE_DI_CHECK_ENDPOINT = $($endpoint.Trim())"
Write-Host "  AZURE_DI_CHECK_KEY      = ($($key.Length) chars)"
Write-Host "  SKU                     = $sku"
Write-Host ""
Write-Host "Restart Streamlit (.\run_local.ps1) after updating .env." -ForegroundColor Yellow
