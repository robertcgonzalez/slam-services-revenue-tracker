#Requires -Version 5.1
<#
.SYNOPSIS
  Spike-only: Provision an Azure Computer Vision (S1) resource for the Phase 1
  CV Read check-payee extraction prototype.

.DESCRIPTION
  Creates (or validates) a dedicated Computer Vision resource in the SLAM
  Services subscription for the hybrid OCR spike. This is the resource that
  Phase 1's `phase1_cv_read_prototype.py` will call with the Read API on
  individually cropped check images.

  The script is intentionally thin, idempotent where possible, and follows the
  exact conventions used by the rest of the project's Azure PowerShell scripts
  (Deploy-ToAzure.ps1, Set-AzurePostgresAppSettings.ps1, etc.).

  After successful creation it prints the two values you need for the local
  `.env` file that the prototype consumes:
    AZURE_CV_ENDPOINT=https://<name>.cognitiveservices.azure.com/
    AZURE_CV_KEY=<key1>

  IMPORTANT: This script lives under Scripts/spike/. It is NOT production
  infrastructure. It will never be called from the app or CI.

.PARAMETER ResourceGroup
  Target resource group. Defaults to the project's standard "SLAM-Services-RG".

.PARAMETER Location
  Azure region. Defaults to "eastus" (matches all prior SLAM Azure work).

.PARAMETER AccountName
  Name for the Computer Vision resource. Defaults to "slam-cv-read" (clear,
  short, spike-specific). Change only if you already have a name collision.

.PARAMETER Sku
  Pricing tier. Per the spike plan this must be S1 (or higher). Default S1.

.EXAMPLE
  # Most common usage (after az login)
  .\Scripts\spike\Provision-AzureComputerVisionRead.ps1

.EXAMPLE
  # Custom name + explicit RG (rare)
  .\Scripts\spike\Provision-AzureComputerVisionRead.ps1 `
      -ResourceGroup "SLAM-Services-RG" `
      -AccountName "slam-cv-read-prod-test"

.NOTES
  - Requires Azure CLI (az) logged in with Contributor (or Owner) on the RG.
  - Creates ONE billable resource (S1 Computer Vision ≈ $100-150/month list,
    but the spike uses only a few hundred Read transactions → pennies).
  - The Read feature is enabled by default on the ComputerVision kind.
  - Safe to re-run; it will detect an existing resource with the same name.
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$Location      = "eastus",
    [string]$AccountName   = "slam-cv-read",
    [string]$Sku           = "S1"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg"     -ForegroundColor Green }
function Write-Warn2($m)  { Write-Host "  [WARN] $m"     -ForegroundColor Yellow }
function Write-Err2($m)   { Write-Host "  [ERR] $m"      -ForegroundColor Red }

Write-Step "Phase 1 spike — Azure Computer Vision Read provisioning"

# -----------------------------------------------------------------------------
# 1. Pre-flight
# -----------------------------------------------------------------------------
Write-Step "Pre-flight checks"

$azVersion = az version --query '"azure-cli"' -o tsv 2>$null
if (-not $azVersion) {
    Write-Err2 "Azure CLI not found or not logged in."
    Write-Host "  Run: az login" -ForegroundColor Yellow
    exit 1
}
Write-Ok "Azure CLI present (version $azVersion)"

az account show --only-show-errors 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Err2 "No active Azure CLI session."
    Write-Host "  Run: az login" -ForegroundColor Yellow
    exit 1
}
$subName = az account show --query name -o tsv
Write-Ok "Logged in to subscription: $subName"

# Check (or create) the resource group — we reuse the project's standard RG
$rgExists = az group exists -n $ResourceGroup 2>$null
if ($rgExists -ne "true") {
    Write-Warn2 "Resource group '$ResourceGroup' does not exist. Creating it..."
    az group create -n $ResourceGroup -l $Location --only-show-errors | Out-Null
}
Write-Ok "Resource group ready: $ResourceGroup ($Location)"

# -----------------------------------------------------------------------------
# 2. Create (or validate) the Computer Vision account
# -----------------------------------------------------------------------------
Write-Step "Computer Vision resource: $AccountName (kind=ComputerVision, sku=$Sku)"

$existing = az cognitiveservices account show `
    -g $ResourceGroup `
    -n $AccountName `
    --only-show-errors 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue

if ($existing) {
    Write-Ok "Resource already exists (provisioningState=$($existing.provisioningState))"
    if ($existing.kind -ne "ComputerVision") {
        Write-Err2 "Existing resource is kind='$($existing.kind)', not ComputerVision."
        exit 1
    }
    if ($existing.sku.name -ne $Sku) {
        Write-Warn2 "Existing SKU is $($existing.sku.name). The spike plan calls for S1."
    }
} else {
    Write-Host "  Creating new Computer Vision account..." -ForegroundColor Gray
    az cognitiveservices account create `
        --name $AccountName `
        --resource-group $ResourceGroup `
        --location $Location `
        --kind ComputerVision `
        --sku $Sku `
        --yes `
        --only-show-errors | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Err2 "Failed to create the Computer Vision resource."
        exit 1
    }
    Write-Ok "Computer Vision resource created successfully."
}

# -----------------------------------------------------------------------------
# 3. Retrieve endpoint + key (the two values the spike prototype needs)
# -----------------------------------------------------------------------------
Write-Step "Retrieving endpoint and key for local .env"

$endpoint = "https://$AccountName.cognitiveservices.azure.com/"
$keys = az cognitiveservices account keys list `
    -g $ResourceGroup `
    -n $AccountName `
    --only-show-errors | ConvertFrom-Json

$key1 = $keys.key1
if (-not $key1) {
    Write-Err2 "Could not retrieve key1. Check your permissions."
    exit 1
}

Write-Ok "Endpoint : $endpoint"
Write-Ok "Key1     : $key1   (keep this secret)"

# -----------------------------------------------------------------------------
# 4. Emit ready-to-paste .env block
# -----------------------------------------------------------------------------
Write-Step "Copy the block below into your local .env (never commit it)"

$envBlock = @"
# Azure Computer Vision Read — Phase 1 spike only
# Generated by Scripts/spike/Provision-AzureComputerVisionRead.ps1 on $(Get-Date -Format o)
AZURE_CV_ENDPOINT=$endpoint
AZURE_CV_KEY=$key1
"@

Write-Host ""
Write-Host $envBlock -ForegroundColor Green
Write-Host ""

# Also write it to a local file the user can copy from (still gitignored)
$envFile = Join-Path $RepoRoot ".env.cv-read-spike"
$envBlock | Out-File -FilePath $envFile -Encoding utf8 -Force
Write-Ok "Also written to: $envFile (add the two lines to your real .env)"

# -----------------------------------------------------------------------------
# 5. Summary & next steps
# -----------------------------------------------------------------------------
Write-Step "Provisioning complete — next steps for Phase 1"

Write-Host @"
  1. Add the two AZURE_CV_* lines above to your local .env (or Codespace secret).
  2. In the Codespace (or locally with the SDK installed):
       pip install azure-cognitiveservices-vision-computervision python-dotenv
       python Scripts/spike/phase1_cv_read_prototype.py --real
  3. The prototype will now call the real Read API on the 40 cropped check PNGs.

Resource details (for reference / cleanup later):
  Resource group : $ResourceGroup
  Account name   : $AccountName
  Kind           : ComputerVision
  SKU            : $Sku
  Endpoint       : $endpoint

To delete later (when the spike is over):
  az cognitiveservices account delete -g $ResourceGroup -n $AccountName

All spike work remains isolated under Scripts/spike/.
"@ -ForegroundColor White

Write-Host "`n=== Phase 1 Azure CV Read resource is ready ===" -ForegroundColor Green
