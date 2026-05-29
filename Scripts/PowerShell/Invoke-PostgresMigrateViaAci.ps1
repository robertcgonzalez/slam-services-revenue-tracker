#Requires -Version 5.1
<#
.SYNOPSIS
  Run init_db + migrate_to_postgres inside Azure when local outbound TCP/5432 is blocked.
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$ServerName = "slam-services-db",
    [string]$AdminUser = "slamadmin",
    [string]$DatabaseName = "slam_services",
    [string]$StorageAccount = "slamocrstg2605251016",
    [string]$ContainerName = "slam-migration-temp",
    [string]$Location = "centralus",
    [Parameter(Mandatory = $true)]
    [string]$AdminPassword,
    [string]$DataPath = "",
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok($m)  { Write-Host "  [OK] $m" -ForegroundColor Green }

$csvDir = if ($DataPath) { $DataPath } else { Join-Path $RepoRoot "Data\Revenue_Tracker_Migration" }
$clients = Join-Path $csvDir "Clients.csv"
$requests = Join-Path $csvDir "RevenueRequests.csv"
if (-not (Test-Path $clients) -or -not (Test-Path $requests)) {
    throw "Clients.csv / RevenueRequests.csv not found under $csvDir"
}

$fqdn = az postgres flexible-server show -g $ResourceGroup -n $ServerName --query fullyQualifiedDomainName -o tsv
if (-not $fqdn) { throw "Server $ServerName not found" }
Write-Ok "Postgres host: $fqdn"

if ($WhatIf) {
    Write-Host "[WhatIf] Would upload CSVs and run ACI migration in $Location"
    exit 0
}

$aciState = az provider show -n Microsoft.ContainerInstance --query registrationState -o tsv 2>$null
if ($aciState -ne "Registered") {
    Write-Step "Registering Microsoft.ContainerInstance"
    az provider register --namespace Microsoft.ContainerInstance --wait | Out-Null
}

Write-Step "Upload migration CSVs to private blob"
$key = az storage account keys list -g $ResourceGroup -n $StorageAccount --query "[0].value" -o tsv
az storage container create -n $ContainerName --account-name $StorageAccount --account-key $key --public-access off 2>$null | Out-Null
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$prefix = "migrate-$stamp"
az storage blob upload --account-name $StorageAccount --account-key $key -c $ContainerName -f $clients -n "$prefix/Clients.csv" | Out-Null
az storage blob upload --account-name $StorageAccount --account-key $key -c $ContainerName -f $requests -n "$prefix/RevenueRequests.csv" | Out-Null
Write-Ok "CSVs uploaded"

Write-Step "Build migration bundle"
$bundleDir = Join-Path $env:TEMP "slam-migrate-bundle"
if (Test-Path $bundleDir) { Remove-Item $bundleDir -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $bundleDir "App") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $bundleDir "Scripts") -Force | Out-Null
Copy-Item (Join-Path $RepoRoot "App\db_utils.py") (Join-Path $bundleDir "App\")
Set-Content (Join-Path $bundleDir "App\__init__.py") -Value ""
Copy-Item (Join-Path $RepoRoot "Scripts\init_db.py") (Join-Path $bundleDir "Scripts\")
Copy-Item (Join-Path $RepoRoot "Scripts\migrate_to_postgres.py") (Join-Path $bundleDir "Scripts\")
$bundleZip = Join-Path $env:TEMP "slam-migrate-bundle.zip"
if (Test-Path $bundleZip) { Remove-Item $bundleZip -Force }
Compress-Archive -Path (Join-Path $bundleDir "*") -DestinationPath $bundleZip
az storage blob upload --account-name $StorageAccount --account-key $key -c $ContainerName -f $bundleZip -n "$prefix/bundle.zip" | Out-Null
$runnerPath = Join-Path $RepoRoot "Scripts\aci_migrate_runner.py"
az storage blob upload --account-name $StorageAccount --account-key $key -c $ContainerName -f $runnerPath -n "$prefix/aci_migrate_runner.py" | Out-Null
Write-Ok "Bundle + runner uploaded"

$aciName = "slam-pg-migrate-$stamp"
$pythonEntry = "import os,base64; exec(base64.b64decode(os.environ['BOOTSTRAP_B64']))"

$bootstrapPy = @'
import os, subprocess, sys, base64
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "azure-storage-blob", "pandas", "sqlalchemy", "psycopg2-binary", "python-dotenv"])
from azure.storage.blob import BlobServiceClient
acc = os.environ["STORAGE_ACCOUNT"]
key = os.environ["STORAGE_KEY"]
container = os.environ["BLOB_CONTAINER"]
prefix = os.environ["BLOB_PREFIX"]
svc = BlobServiceClient(account_url=f"https://{acc}.blob.core.windows.net", credential=key)
blob = svc.get_blob_client(container, f"{prefix}/aci_migrate_runner.py")
open("/aci_migrate_runner.py", "wb").write(blob.download_blob().readall())
subprocess.check_call([sys.executable, "/aci_migrate_runner.py"])
'@
$bootstrapB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($bootstrapPy))

Write-Step "Run one-shot ACI: $aciName"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"

$subId = az account show --query id -o tsv
$aciUri = "https://management.azure.com/subscriptions/$subId/resourceGroups/$ResourceGroup/providers/Microsoft.ContainerInstance/containerGroups/${aciName}?api-version=2023-05-01"
$aciBody = @{
    location = $Location
    properties = @{
        containers = @(
            @{
                name = $aciName
                properties = @{
                    image = "mcr.microsoft.com/devcontainers/python:3.10-bullseye"
                    command = @("python", "-c", $pythonEntry)
                    resources = @{
                        requests = @{
                            cpu        = 1
                            memoryInGB = 2.0
                        }
                    }
                    environmentVariables = @(
                        @{ name = "STORAGE_ACCOUNT"; value = $StorageAccount }
                        @{ name = "BLOB_CONTAINER"; value = $ContainerName }
                        @{ name = "BLOB_PREFIX"; value = $prefix }
                        @{ name = "PG_HOST"; value = $fqdn }
                        @{ name = "PG_USER"; value = $AdminUser }
                        @{ name = "PG_DB"; value = $DatabaseName }
                        @{ name = "BOOTSTRAP_B64"; value = $bootstrapB64 }
                        @{ name = "STORAGE_KEY"; secureValue = $key }
                        @{ name = "PG_PASSWORD"; secureValue = $AdminPassword }
                    )
                }
            }
        )
        osType = "Linux"
        restartPolicy = "Never"
    }
}
$aciBodyFile = Join-Path $env:TEMP "slam-aci-$stamp.json"
$aciBody | ConvertTo-Json -Depth 12 | Set-Content -Path $aciBodyFile -Encoding utf8
az rest --method put --uri $aciUri --body "@$aciBodyFile" | Out-Null
if ($LASTEXITCODE -ne 0) {
    $ErrorActionPreference = $prevEap
    throw "ACI create (az rest) failed"
}

Write-Ok "Container started; polling logs (up to 15 min)"
$deadline = (Get-Date).AddMinutes(15)
$ok = $false
do {
    Start-Sleep -Seconds 25
    $logs = az container logs -g $ResourceGroup -n $aciName 2>$null
    if ($logs -match "MIGRATION_OK") { $ok = $true; break }
    if ($logs -match "Traceback|ERROR:") { break }
    $state = az container show -g $ResourceGroup -n $aciName --query "containers[0].instanceView.currentState.state" -o tsv 2>$null
    if ($state -eq "Terminated") { break }
} while ((Get-Date) -lt $deadline)

$logs = az container logs -g $ResourceGroup -n $aciName 2>$null
Write-Host $logs
az container delete -g $ResourceGroup -n $aciName --yes 2>$null | Out-Null
$ErrorActionPreference = $prevEap

if (-not $ok -and $logs -match "MIGRATION_OK") { $ok = $true }
if (-not $ok) { throw "ACI migration did not report MIGRATION_OK" }
Write-Ok "Migration completed via ACI"
