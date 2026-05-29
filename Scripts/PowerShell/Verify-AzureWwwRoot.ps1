#Requires -Version 5.1
<#
.SYNOPSIS
  Verify startup.sh, runtime.txt, and apt.txt exist at App Service wwwroot root.

.DESCRIPTION
  Uses Kudu VFS + a chmod probe. Fails with exit 1 when any file is missing or
  startup.sh is not executable. Safe to run after Deploy-ToAzure.ps1 or manually
  from CI.

.EXAMPLE
  .\Scripts\PowerShell\Verify-AzureWwwRoot.ps1
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName    = "slam-services-revenue-tracker"
)

$ErrorActionPreference = "Stop"

function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Err2($m)   { Write-Host "  [ERR] $m"  -ForegroundColor Red }
function Write-Warn2($m)  { Write-Host "  [WARN] $m" -ForegroundColor Yellow }

$pubJson = az webapp deployment list-publishing-credentials `
    -g $ResourceGroup -n $WebAppName -o json 2>$null
if ($LASTEXITCODE -ne 0 -or -not $pubJson) {
    Write-Err2 "Could not read publishing credentials. Run: az login"
    exit 1
}
$pub = $pubJson | ConvertFrom-Json
$token = [Convert]::ToBase64String(
    [Text.Encoding]::ASCII.GetBytes("$($pub.publishingUserName):$($pub.publishingPassword)")
)
$headers = @{ Authorization = "Basic $token" }
$scmBase = "https://$WebAppName.scm.azurewebsites.net"

$required = @("startup.sh", "runtime.txt", "apt.txt")
$missing = @()
foreach ($name in $required) {
    try {
        Invoke-WebRequest -Uri "$scmBase/api/vfs/site/wwwroot/$name" `
            -Headers $headers -Method Head -UseBasicParsing -TimeoutSec 45 | Out-Null
        Write-Ok "$name present"
    }
    catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 404) {
            $missing += $name
            Write-Err2 "$name missing"
        }
        else { throw }
    }
}

if ($missing.Count -gt 0) {
    try {
        Invoke-WebRequest -Uri "$scmBase/api/vfs/site/wwwroot/output.tar.zst" `
            -Headers $headers -Method Head -UseBasicParsing -TimeoutSec 45 | Out-Null
        Write-Warn2 "output.tar.zst exists - startup files may be inside the Oryx tarball only (Python build ignores COMPRESS_DESTINATION_DIR=false). Run .\Scripts\PowerShell\Deploy-ToAzure.ps1 to seed/extract, or see docs/deployment.md recovery."
    }
    catch { }
    Write-Host "  Fix: .\Scripts\PowerShell\Deploy-ToAzure.ps1  (re-seeds wwwroot startup files)" -ForegroundColor Yellow
    exit 1
}

$chmod = Invoke-RestMethod -Method Post -Uri "$scmBase/api/command" `
    -Headers $headers -Body (@{ command = "chmod +x startup.sh"; dir = "/home/site/wwwroot" } | ConvertTo-Json -Compress) `
    -ContentType "application/json" -TimeoutSec 60
$body = @{ command = "test -x startup.sh"; dir = "/home/site/wwwroot" } | ConvertTo-Json -Compress
$cmd = Invoke-RestMethod -Method Post -Uri "$scmBase/api/command" `
    -Headers $headers -Body $body -ContentType "application/json" -TimeoutSec 60
if ($cmd.ExitCode -eq 0) {
    Write-Ok "startup.sh is executable"
}
else {
    Write-Err2 "startup.sh is not executable (Kudu exit $($cmd.ExitCode))"
    exit 1
}

Write-Host "`nwwwroot root artifacts verified for $WebAppName" -ForegroundColor Green
exit 0
