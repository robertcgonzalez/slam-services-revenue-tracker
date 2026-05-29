#Requires -Version 5.1
<#
.SYNOPSIS
  Single-shot data-layer go-live: Azure Postgres + local migrate + App Service wire + redeploy.

.DESCRIPTION
  Minimizes owner involvement to:
    1) One secure password prompt (unless -AdminPassword is passed  - avoid CLI history)
    2) Gate A3 re-smoke in the browser (human only)

  Phases (skippable via switches):
    P0  Preflight (az login, local CSVs, .venv)
    P1  Provision-AzurePostgres.ps1
    P2  init_db + migrate_to_postgres (dry-run then apply) + health_check --verify-only
    P3  Set-AzurePostgresAppSettings.ps1
    P4  Build-AzureDeployZip + Deploy-ToAzure -CleanDeploy
    P5  Check-AppHealth.ps1 -Full -CheckAzure

  Client CSVs never leave the laptop; nothing is uploaded to wwwroot.

.PARAMETER AdminPassword
  PostgreSQL admin password. If omitted, prompted once and reused for provision + App Settings.

.EXAMPLE
  .\Scripts\PowerShell\Invoke-DataLayerGoLive.ps1

.EXAMPLE
  .\Scripts\PowerShell\Invoke-DataLayerGoLive.ps1 -WhatIf

.EXAMPLE
  .\Scripts\PowerShell\Invoke-DataLayerGoLive.ps1 -SkipProvision   # server exists; migrate + wire only
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$ServerName = "slam-services-db",
    [string]$Location = "centralus",
    [string]$AdminUser = "slamadmin",
    [string]$DatabaseName = "slam_services",
    [string]$WebAppName = "slam-services-revenue-tracker",
    [string]$AdminPassword = "",
    [string]$DataPath = "",
    [switch]$WhatIf,
    [switch]$SkipProvision,
    [switch]$SkipMigrate,
    [switch]$SkipAppSettings,
    [switch]$SkipDeploy,
    [switch]$SkipHealthCheck,
    [switch]$SkipLocalEnv,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn2($m)  { Write-Host "  [WARN] $m" -ForegroundColor Yellow }

function Get-SecurePassword([string]$promptLabel) {
    if ($AdminPassword) { return $AdminPassword }
    if ($env:SLAM_POSTGRES_ADMIN_PASSWORD) { return $env:SLAM_POSTGRES_ADMIN_PASSWORD }
    if ($NonInteractive) {
        throw "NonInteractive: set -AdminPassword or SLAM_POSTGRES_ADMIN_PASSWORD"
    }
    $secure = Read-Host $promptLabel -AsSecureString
    return [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

function Set-PostgresSessionEnv {
    param([string]$HostFqdn, [string]$User, [string]$Password, [string]$Db)
    $env:POSTGRES_HOST = $HostFqdn
    $env:POSTGRES_USER = $User
    $env:POSTGRES_PASSWORD = $Password
    $env:POSTGRES_DB = $Db
    $env:POSTGRES_SSLMODE = "require"
    $env:USE_POSTGRES = "true"
}

function Update-LocalEnvFile {
    param([string]$EnvPath, [hashtable]$Keys)
    $lines = @()
    if (Test-Path $EnvPath) {
        $lines = Get-Content -Path $EnvPath -Encoding UTF8
    }
    foreach ($key in $Keys.Keys) {
        $val = $Keys[$key]
        $pattern = "^\s*$([regex]::Escape($key))\s*="
        $replacement = "$key=$val"
        $found = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match $pattern) {
                $lines[$i] = $replacement
                $found = $true
                break
            }
        }
        if (-not $found) {
            if ($lines.Count -gt 0 -and $lines[-1] -ne "") { $lines += "" }
            $lines += $replacement
        }
    }
    if ($WhatIf) {
        Write-Host "[WhatIf] Would update $EnvPath (keys: $($Keys.Keys -join ', '))" -ForegroundColor DarkGray
        return
    }
    Set-Content -Path $EnvPath -Value $lines -Encoding UTF8
    Write-Ok "Updated local .env Postgres keys (password not printed)"
}

function Invoke-PythonStep {
    param([string]$Label, [string[]]$PythonArgs)
    $py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { throw "Missing $py - create .venv and install requirements first." }
    Write-Step $Label
    if ($WhatIf) {
        Write-Host "[WhatIf] $py $($PythonArgs -join ' ')" -ForegroundColor DarkGray
        return
    }
    & $py @PythonArgs
    if ($LASTEXITCODE -ne 0) { throw "$Label failed (exit $LASTEXITCODE)" }
    Write-Ok $Label
}

# --- P0 Preflight ---
Write-Step "P0  - Preflight"
if ($WhatIf) {
    Write-Host "[WhatIf] Would verify az login, CSVs, .venv" -ForegroundColor DarkGray
} else {
    az account show --only-show-errors 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Not logged in. Run: az login" }
    Write-Ok "Azure CLI session active"

    $csvDir = if ($DataPath) { $DataPath } else { Join-Path $RepoRoot "Data\Revenue_Tracker_Migration" }
    if (-not (Test-Path (Join-Path $csvDir "Clients.csv"))) {
        throw "Clients.csv not found under $csvDir"
    }
    if (-not (Test-Path (Join-Path $csvDir "RevenueRequests.csv"))) {
        throw "RevenueRequests.csv not found under $csvDir"
    }
    Write-Ok "Local migration CSVs present"

    $venvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "Missing .venv  - run local setup per docs/local-development.md" }
    Write-Ok ".venv Python ready"
}

$needsPassword = (-not $SkipProvision) -or (-not $SkipMigrate) -or (-not $SkipAppSettings)
if (-not $WhatIf -and $needsPassword -and -not $AdminPassword) {
    $AdminPassword = Get-SecurePassword "PostgreSQL admin password (one prompt  - provision, migrate, App Service)"
}

# --- P1 Provision ---
if (-not $SkipProvision) {
    Write-Step "P1  - Provision Azure PostgreSQL"
    $provArgs = @{
        ResourceGroup = $ResourceGroup
        ServerName    = $ServerName
        Location      = $Location
        AdminUser     = $AdminUser
        DatabaseName  = $DatabaseName
        WebAppName    = $WebAppName
    }
    if ($WhatIf) { $provArgs["WhatIf"] = $true }
    if ($AdminPassword) { $provArgs["AdminPassword"] = $AdminPassword }
    & (Join-Path $PSScriptRoot "Provision-AzurePostgres.ps1") @provArgs
    if (-not $WhatIf -and $LASTEXITCODE -ne 0) { throw "Provision-AzurePostgres.ps1 failed" }
}

$fqdn = if ($WhatIf) {
    "${ServerName}.postgres.database.azure.com"
} else {
    az postgres flexible-server show -g $ResourceGroup -n $ServerName --query fullyQualifiedDomainName -o tsv 2>$null
}
if (-not $fqdn -and -not $WhatIf) {
    throw "Could not read FQDN for $ServerName  - run P1 or pass an existing server name."
}
Write-Ok "Postgres host: $fqdn"

if (-not $SkipLocalEnv) {
    Update-LocalEnvFile -EnvPath (Join-Path $RepoRoot ".env") -Keys @{
        POSTGRES_HOST     = $fqdn
        POSTGRES_USER     = $AdminUser
        POSTGRES_PASSWORD = if ($AdminPassword) { $AdminPassword } else { "<set-after-prompt>" }
        POSTGRES_DB       = $DatabaseName
        POSTGRES_SSLMODE  = "require"
        USE_POSTGRES      = "true"
    }
}

if ($AdminPassword) {
    Set-PostgresSessionEnv -HostFqdn $fqdn -User $AdminUser -Password $AdminPassword -Db $DatabaseName
}

# --- P2 Local migration ---
if (-not $SkipMigrate) {
    if (-not $AdminPassword -and -not $WhatIf) {
        throw "Admin password required for migration (re-run with password prompt or -AdminPassword)."
    }
    $migrateArgs = @("Scripts/init_db.py")
    Invoke-PythonStep -Label "P2a - init_db.py" -PythonArgs $migrateArgs

    $dryArgs = @("Scripts/migrate_to_postgres.py", "--dry-run")
    if ($DataPath) { $dryArgs += @("--data-path", $DataPath) }
    Invoke-PythonStep -Label "P2b - migrate (dry-run)" -PythonArgs $dryArgs

    $migArgs = @("Scripts/migrate_to_postgres.py")
    if ($DataPath) { $migArgs += @("--data-path", $DataPath) }
    Invoke-PythonStep -Label "P2c - migrate (apply)" -PythonArgs $migArgs

    Invoke-PythonStep -Label "P2d - health_check (verify-only)" -PythonArgs @("Scripts/health_check.py", "--verify-only")
}

# --- P3 App Service settings ---
if (-not $SkipAppSettings) {
    Write-Step "P3  - Wire App Service (USE_POSTGRES + POSTGRES_*)"
    if ($WhatIf) {
        Write-Host "[WhatIf] Set-AzurePostgresAppSettings.ps1 -PostgresHost $fqdn ..." -ForegroundColor DarkGray
    } else {
        if (-not $AdminPassword) { throw "Password required for App Service settings." }
        & (Join-Path $PSScriptRoot "Set-AzurePostgresAppSettings.ps1") `
            -ResourceGroup $ResourceGroup `
            -WebAppName $WebAppName `
            -PostgresHost $fqdn `
            -PostgresUser $AdminUser `
            -PostgresDb $DatabaseName `
            -PostgresPassword $AdminPassword
        if ($LASTEXITCODE -ne 0) { throw "Set-AzurePostgresAppSettings.ps1 failed" }
        Write-Ok "App Settings applied (names only in Azure portal)"
    }
}

# --- P4 Redeploy ---
if (-not $SkipDeploy) {
    Write-Step "P4  - Code-only deploy (clean wwwroot)"
    if ($WhatIf) {
        Write-Host "[WhatIf] Build-AzureDeployZip.ps1; Deploy-ToAzure.ps1 -CleanDeploy -TimeoutSeconds 900" -ForegroundColor DarkGray
    } else {
        & (Join-Path $PSScriptRoot "Build-AzureDeployZip.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Build-AzureDeployZip.ps1 failed" }
        & (Join-Path $PSScriptRoot "Deploy-ToAzure.ps1") `
            -ResourceGroup $ResourceGroup `
            -WebAppName $WebAppName `
            -CleanDeploy `
            -TimeoutSeconds 900
        if ($LASTEXITCODE -ne 0) { throw "Deploy-ToAzure.ps1 failed" }
        Write-Ok "Deploy finished  - confirm via Kudu log if shell timed out"
    }
}

# --- P5 Health ---
if (-not $SkipHealthCheck) {
    Write-Step "P5  - Post-deploy health"
    if ($WhatIf) {
        Write-Host "[WhatIf] Check-AppHealth.ps1 -Full -CheckAzure" -ForegroundColor DarkGray
    } else {
        $healthScript = Join-Path $PSScriptRoot "Check-AppHealth.ps1"
        if (Test-Path $healthScript) {
            & $healthScript -Full -CheckAzure
        } else {
            Write-Warn2 "Check-AppHealth.ps1 not found  - skip or run manually"
        }
    }
}

Write-Step "Owner-only  - Gate A3 re-smoke"
Write-Host @"

  URL: https://${WebAppName}.azurewebsites.net/
  PDFs: Data/Auto_Body_Center_Jan_26_Statement.pdf, Data/HCC 2026-04.pdf

  Before smoke: sidebar -> Data Source Status -> PostgreSQL with non-zero clients/requests.

  Paste report using template in docs/go-live-execution-runbook.md (Gate A3  - owner report template).

"@ -ForegroundColor White

Write-Host "Rollback: .\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 -DisablePostgres" -ForegroundColor DarkGray
