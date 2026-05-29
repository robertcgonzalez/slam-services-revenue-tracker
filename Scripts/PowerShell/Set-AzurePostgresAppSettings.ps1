#Requires -Version 5.1
<#
.SYNOPSIS
  Configure Azure App Service for PostgreSQL production mode (v2.30).

.DESCRIPTION
  Sets USE_POSTGRES and POSTGRES_* App Settings on slam-services-revenue-tracker.
  Does NOT create the database - run Azure CLI provisioning first (see README).

.PARAMETER PostgresHost
  e.g. slam-services-db.postgres.database.azure.com

.PARAMETER PostgresUser
  Admin user (Azure may require user@servername format)

.PARAMETER PostgresPassword
  Database password (prompted securely if omitted)

.EXAMPLE
  .\Scripts\PowerShell\Set-AzurePostgresAppSettings.ps1 `
    -PostgresHost "slam-services-db.postgres.database.azure.com" `
    -PostgresUser "slamadmin"
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName = "slam-services-revenue-tracker",
    [Parameter(Mandatory = $true)]
    [string]$PostgresHost,
    [Parameter(Mandatory = $true)]
    [string]$PostgresUser,
    [string]$PostgresPassword = "",
    [string]$PostgresDb = "slam_services",
    [string]$AppUser = "Laura",
    [switch]$DisablePostgres
)

$ErrorActionPreference = "Stop"

if (-not $DisablePostgres -and -not $PostgresPassword) {
    $secure = Read-Host "PostgreSQL password" -AsSecureString
    $PostgresPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

if ($DisablePostgres) {
    Write-Host "Disabling PostgreSQL - app will use CSV mode."
    az webapp config appsettings set `
        -g $ResourceGroup `
        -n $WebAppName `
        --settings USE_POSTGRES=false
    Write-Host "Done. Restart the app or wait for the next request."
    exit 0
}

Write-Host "Enabling PostgreSQL on $WebAppName ..."
az webapp config appsettings set `
    -g $ResourceGroup `
    -n $WebAppName `
    --settings `
        USE_POSTGRES=true `
        POSTGRES_HOST=$PostgresHost `
        POSTGRES_USER=$PostgresUser `
        POSTGRES_PASSWORD=$PostgresPassword `
        POSTGRES_DB=$PostgresDb `
        POSTGRES_SSLMODE=require `
        SLAM_APP_USER=$AppUser

Write-Host "App Settings updated. Deploy latest code, then verify sidebar Data Source Status."
Write-Host "Fallback: re-run with -DisablePostgres to return to CSV mode."
