#Requires -Version 5.1
<#
.SYNOPSIS
  Provision Azure Database for PostgreSQL Flexible Server for SLAM production.

.DESCRIPTION
  Creates slam-services-db (or custom name) in SLAM-Services-RG, database slam_services,
  firewall rules for Azure services + your current public IP, and prints next steps
  for local init/migrate + Set-AzurePostgresAppSettings.ps1.

  Does NOT upload client CSVs to App Service. Migration runs from Robert's laptop only.

.PARAMETER AdminPassword
  Server admin password (min complexity per Azure policy). Prompted securely if omitted.

.EXAMPLE
  .\Scripts\PowerShell\Provision-AzurePostgres.ps1
  # Then on laptop: init_db, migrate, Set-AzurePostgresAppSettings, redeploy

.EXAMPLE
  .\Scripts\PowerShell\Provision-AzurePostgres.ps1 -WhatIf
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$ServerName = "slam-services-db",
    [string]$Location = "centralus",
    [string]$AdminUser = "slamadmin",
    [string]$AdminPassword = "",
    [string]$DatabaseName = "slam_services",
    [string]$SkuName = "Standard_B1ms",
    [string]$Tier = "Burstable",
    [int]$StorageSizeGb = 32,
    [string]$PgVersion = "16",
    [string]$WebAppName = "slam-services-revenue-tracker",
    [switch]$WhatIf,
    [switch]$SkipFirewall,
    [switch]$SkipDatabase
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn2($m)  { Write-Host "  [WARN] $m" -ForegroundColor Yellow }

az account show --only-show-errors 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Not logged in. Run: az login"
}

if (-not $AdminPassword -and -not $WhatIf) {
    $secure = Read-Host "PostgreSQL admin password ($AdminUser)" -AsSecureString
    $AdminPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$existing = az postgres flexible-server show -g $ResourceGroup -n $ServerName 2>$null
$serverExists = ($LASTEXITCODE -eq 0) -and $existing
$ErrorActionPreference = $prevEap

if ($serverExists) {
    Write-Warn2 "Server '$ServerName' already exists in $ResourceGroup  - skipping create."
} elseif ($WhatIf) {
    Write-Host "[WhatIf] Would create flexible server $ServerName ($SkuName / $Tier) in $Location"
} else {
    Write-Step "Creating PostgreSQL Flexible Server: $ServerName"
    $pgState = az provider show -n Microsoft.DBforPostgreSQL --query registrationState -o tsv 2>$null
    if ($pgState -ne "Registered") {
        Write-Warn2 "Registering Microsoft.DBforPostgreSQL (was: $pgState) - may take 1-3 minutes"
        az provider register --namespace Microsoft.DBforPostgreSQL --wait 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Microsoft.DBforPostgreSQL not registered. Run: az provider register --namespace Microsoft.DBforPostgreSQL"
        }
        Write-Ok "Provider registered"
    }

    $publicAccess = "Enabled"
    try {
        $myIp = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 10).Trim()
        if ($myIp) { $publicAccess = $myIp }
    } catch {
        Write-Warn2 "Could not detect public IP - using --public-access Enabled"
    }

    $prevAzEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    az postgres flexible-server create `
        --resource-group $ResourceGroup `
        --name $ServerName `
        --location $Location `
        --admin-user $AdminUser `
        --admin-password $AdminPassword `
        --sku-name $SkuName `
        --tier $Tier `
        --storage-size $StorageSizeGb `
        --version $PgVersion `
        --public-access $publicAccess `
        --yes 2>&1 | ForEach-Object { if ($_ -match '^\s*ERROR:') { Write-Host $_ -ForegroundColor Red } }
    $createExit = $LASTEXITCODE
    $ErrorActionPreference = $prevAzEap
    if ($createExit -ne 0) { throw "flexible-server create failed (exit $createExit)" }
    Write-Ok "Server created"
}

$ErrorActionPreference = "Continue"
$fqdn = az postgres flexible-server show -g $ResourceGroup -n $ServerName --query fullyQualifiedDomainName -o tsv 2>$null
$ErrorActionPreference = $prevEap
if (-not $fqdn) {
    if ($WhatIf) { $fqdn = "${ServerName}.postgres.database.azure.com" }
    else { throw "Could not read server FQDN" }
}
Write-Ok "FQDN: $fqdn"

if (-not $SkipDatabase) {
  if ($WhatIf) {
      Write-Host "[WhatIf] Would create database $DatabaseName"
  } else {
      $dbExists = az postgres flexible-server db show -g $ResourceGroup -s $ServerName -d $DatabaseName 2>$null
      if ($LASTEXITCODE -eq 0) {
          Write-Warn2 "Database '$DatabaseName' already exists"
      } else {
          Write-Step "Creating database $DatabaseName"
          az postgres flexible-server db create `
              -g $ResourceGroup -s $ServerName -d $DatabaseName
          Write-Ok "Database $DatabaseName ready"
      }
  }
}

if (-not $SkipFirewall) {
    Write-Step "Firewall rules"
    if ($WhatIf) {
        Write-Host "[WhatIf] Would add AllowAzureServices (0.0.0.0) + current public IP"
    } else {
        az postgres flexible-server firewall-rule create `
            -g $ResourceGroup -n $ServerName `
            --rule-name AllowAzureServices `
            --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 `
            2>$null | Out-Null
        Write-Ok "AllowAzureServices (App Service + Azure backends)"

        try {
            $myIp = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 10).Trim()
            if ($myIp) {
                az postgres flexible-server firewall-rule create `
                    -g $ResourceGroup -n $ServerName `
                    --rule-name "AllowLaptop_$($myIp -replace '\.', '_')" `
                    --start-ip-address $myIp --end-ip-address $myIp `
                    2>$null | Out-Null
                Write-Ok "Allow laptop IP: $myIp"
            }
        } catch {
            Write-Warn2 "Could not detect public IP  - add a firewall rule manually for your laptop."
        }

        $outbound = az webapp show -g $ResourceGroup -n $WebAppName --query outboundIpAddresses -o tsv 2>$null
        if ($outbound) {
            $ips = $outbound -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' }
            $i = 0
            foreach ($ip in $ips | Select-Object -First 8) {
                $i++
                az postgres flexible-server firewall-rule create `
                    -g $ResourceGroup -n $ServerName `
                    --rule-name "AllowWebApp_$i" `
                    --start-ip-address $ip --end-ip-address $ip `
                    2>$null | Out-Null
            }
            if ($i -gt 0) { Write-Ok "Added up to $i App Service outbound IP rule(s)" }
        }
    }
}

if (-not $WhatIf) {
Write-Step "Next steps (run in order)"
Write-Host @"

1) LOCAL .env (repo root, gitignored)  - add for migration session only:
   POSTGRES_HOST=$fqdn
   POSTGRES_USER=$AdminUser
   POSTGRES_PASSWORD=<same admin password>
   POSTGRES_DB=$DatabaseName
   POSTGRES_SSLMODE=require
   USE_POSTGRES=true

2) LOCAL migration (from C:\SLAM-Services-Project, .venv active):
   python Scripts/init_db.py
   python Scripts/migrate_to_postgres.py --dry-run
   python Scripts/migrate_to_postgres.py

3) APP SERVICE settings (password via secure prompt):
   .\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 `
     -PostgresHost "$fqdn" `
     -PostgresUser "$AdminUser" `
     -PostgresDb "$DatabaseName"

4) REDEPLOY code-only + clean wwwroot junk:
   .\Scripts\PowerShell\Build-AzureDeployZip.ps1
   .\Scripts\PowerShell\Deploy-ToAzure.ps1 -CleanDeploy -TimeoutSeconds 900

5) VERIFY: https://${WebAppName}.azurewebsites.net/
   Sidebar -> Data Source Status -> PostgreSQL connected (client/request counts)

6) GATE A3: Robert re-smoke (Bank Statements, both PDFs)

"@ -ForegroundColor White

Write-Host "Rollback DB mode: Set-AzurePostgresAppSettings.ps1 -DisablePostgres" -ForegroundColor DarkGray
}
