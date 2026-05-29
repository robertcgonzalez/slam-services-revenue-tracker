#Requires -Version 5.1
<#
.SYNOPSIS
  Modern, polling-safe Azure App Service deploy for SLAM Revenue Tracker (v2.38.3+).

.DESCRIPTION
  Replaces the legacy `az webapp deployment source config-zip` and the
  client-side polling of `az webapp deploy` (which silently drops at
  ~230s on F1 tier with "RemoteDisconnected" while Kudu warms up).

  Safe modern flow:
    1. Pre-flight: az login, resource exists, zip exists.
    2. Set COMPRESS_DESTINATION_DIR=false (Python Oryx may still compress; see post-steps).
    3. Remove WEBSITE_RUN_FROM_PACKAGE if present.
    4. Optional CleanDeploy: remove stale output.tar.zst / oryx-manifest.toml via Kudu.
    5. Stop the web app -> releases Kudu.
    6. Upload zip via `az webapp deploy --async true`
    7. Poll Kudu deployment status until terminal.
    8. Guarantee startup.sh, runtime.txt, apt.txt at wwwroot (VFS seed + Oryx tarball extract).
    9. Start the web app and run lightweight HTTP smoke test.

  Idempotent and re-runnable. By default merges into wwwroot (preserves server files).
  Use -CleanDeploy for code-only pushes that should drop stale wwwroot folders
  (does not restore CSV data — use PostgreSQL for production data).
  Use after .\Scripts\PowerShell\Build-AzureDeployZip.ps1.

.EXAMPLE
  .\Scripts\PowerShell\Deploy-ToAzure.ps1

.EXAMPLE
  .\Scripts\PowerShell\Deploy-ToAzure.ps1 -CleanDeploy -TimeoutSeconds 900
#>
param(
    [string]$ResourceGroup = "SLAM-Services-RG",
    [string]$WebAppName    = "slam-services-revenue-tracker",
    [string]$ZipPath       = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "slam-app.zip"),
    [int]$TimeoutSeconds   = 600,
    [int]$PollIntervalSec  = 10,
    [int]$WwwRootVerifyRetries = 18,
    [int]$WwwRootVerifyIntervalSec = 15,
    [switch]$SkipStop,
    [switch]$SkipSmokeTest,
    [switch]$CleanDeploy,
    [switch]$SkipWwwRootGuarantee,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg"     -ForegroundColor Green }
function Write-Warn2($m)  { Write-Host "  [WARN] $m"     -ForegroundColor Yellow }
function Write-Err2($m)   { Write-Host "  [ERR] $m"      -ForegroundColor Red }

function Get-KuduAuthHeader {
    param([string]$ResourceGroup, [string]$WebAppName)
    $pubJson = az webapp deployment list-publishing-credentials `
        -g $ResourceGroup -n $WebAppName -o json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $pubJson) { return $null }
    $pub = $pubJson | ConvertFrom-Json
    $token = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("$($pub.publishingUserName):$($pub.publishingPassword)")
    )
    return @{ Authorization = "Basic $token" }
}

function Test-KuduWwwRootFile {
    param([string]$ScmBase, [hashtable]$Headers, [string]$RelativePath)
    try {
        $uri = "$ScmBase/api/vfs/site/wwwroot/$RelativePath"
        Invoke-WebRequest -Uri $uri -Headers $Headers -Method Head -UseBasicParsing -TimeoutSec 45 | Out-Null
        return $true
    }
    catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 404) { return $false }
        throw
    }
}

function Invoke-KuduCommand {
    param(
        [string]$ScmBase,
        [hashtable]$Headers,
        [string]$Command,
        [string]$Dir = "/home/site/wwwroot",
        [int]$TimeoutSec = 600
    )
    $body = @{
        command = $Command
        dir     = $Dir
    } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Method Post -Uri "$ScmBase/api/command" `
        -Headers $Headers -Body $body -ContentType "application/json" -TimeoutSec $TimeoutSec
}

function Get-KuduWwwRootListing {
    param([string]$ScmBase, [hashtable]$Headers)
    $r = Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers -Command "ls -la" -TimeoutSec 90
    return $r.Output
}

function Publish-WwwRootStartupFiles {
    param([string]$RepoRoot, [string]$ScmBase, [hashtable]$Headers)
    $files = @("startup.sh", "runtime.txt", "apt.txt")
    foreach ($name in $files) {
        $local = Join-Path $RepoRoot $name
        if (-not (Test-Path $local)) {
            throw "Local file missing for Kudu seed: $local"
        }
        $bytes = [IO.File]::ReadAllBytes($local)
        $uri = "$ScmBase/api/vfs/site/wwwroot/$name"
        Invoke-RestMethod -Method Put -Uri $uri -Headers $Headers -Body $bytes `
            -ContentType "application/octet-stream" -TimeoutSec 120 | Out-Null
        Write-Ok "Seeded wwwroot/$name via Kudu VFS"
    }
    Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers -Command "chmod +x startup.sh" -TimeoutSec 60 | Out-Null
}

function Expand-OryxCompressedStartupArtifacts {
    param([string]$ScmBase, [hashtable]$Headers)
    # Python Oryx often ignores COMPRESS_DESTINATION_DIR and packs wwwroot into output.tar.zst.
    # Kudu /api/command runs one shell statement (no multi-line scripts); use discrete steps.
    if (-not (Test-KuduWwwRootFile -ScmBase $ScmBase -Headers $Headers -RelativePath "output.tar.zst")) {
        return
    }
    $steps = @(
        @{ Cmd = "zstd -d -f output.tar.zst -o /tmp/oryx-flat.tar"; Label = "decompress output.tar.zst" },
        @{ Cmd = "tar -xf /tmp/oryx-flat.tar ./startup.sh ./runtime.txt ./apt.txt"; Label = "extract startup artifacts" },
        @{ Cmd = "tar -xf /tmp/oryx-flat.tar -C /home/site/wwwroot ./App ./Scripts"; Label = "sync App and Scripts to wwwroot" },
        @{ Cmd = "chmod +x startup.sh"; Label = "chmod startup.sh" }
    )
    foreach ($step in $steps) {
        $r = Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers -Command $step.Cmd -TimeoutSec 600
        if ($r.ExitCode -ne 0) {
            throw "$($step.Label) failed (exit $($r.ExitCode)): $($r.Error)"
        }
    }
    # Streamlit runs wwwroot/App/app.py — refresh from tarball when missing or after Oryx rebuild.
    $r = Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers `
        -Command "tar -xf /tmp/oryx-flat.tar -C /home/site/wwwroot ./App ./Scripts" -TimeoutSec 300
    if ($r.ExitCode -eq 0) {
        Write-Ok "Synced ./App and ./Scripts from Oryx tarball to wwwroot"
    }
    elseif (-not (Test-KuduWwwRootFile -ScmBase $ScmBase -Headers $Headers -RelativePath "App/app.py")) {
        Write-Warn2 "Could not sync App/ from tarball: $($r.Error)"
    }
    Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers -Command "rm -f /tmp/oryx-flat.tar" -TimeoutSec 60 | Out-Null
    Write-Ok "Extracted startup.sh, runtime.txt, apt.txt from output.tar.zst"
}

function Clear-StaleOryxCompressedArtifacts {
    param([string]$ScmBase, [hashtable]$Headers)
    $r = Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers `
        -Command "rm -f output.tar.zst output.tar.gz oryx-manifest.toml" -TimeoutSec 120
    if ($r.ExitCode -eq 0) {
        Write-Ok "Removed stale output.tar.zst / oryx-manifest.toml (Data/ untouched)"
    }
}

function Test-WwwRootStartupArtifacts {
    param([string]$ScmBase, [hashtable]$Headers)
    $required = @("startup.sh", "runtime.txt", "apt.txt")
    $missing = @()
    foreach ($name in $required) {
        if (-not (Test-KuduWwwRootFile -ScmBase $ScmBase -Headers $Headers -RelativePath $name)) {
            $missing += $name
        }
    }
    if ($missing.Count -gt 0) {
        return @{ Ok = $false; Missing = $missing; Executable = $false }
    }
    Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers -Command "chmod +x startup.sh" -TimeoutSec 60 | Out-Null
    $cmd = Invoke-KuduCommand -ScmBase $ScmBase -Headers $Headers -Command "test -x startup.sh" -TimeoutSec 60
    $execOk = ($cmd.ExitCode -eq 0)
    return @{ Ok = $true; Missing = @(); Executable = $execOk }
}

function Ensure-WwwRootStartupArtifacts {
    param(
        [string]$RepoRoot,
        [string]$ScmBase,
        [hashtable]$Headers,
        [int]$MaxAttempts,
        [int]$IntervalSec
    )
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $check = Test-WwwRootStartupArtifacts -ScmBase $ScmBase -Headers $Headers
        if ($check.Ok -and $check.Executable) {
            return $true
        }

        if ($attempt -eq 1) {
            Write-Host (Get-KuduWwwRootListing -ScmBase $ScmBase -Headers $Headers) -ForegroundColor DarkGray
        }

        Write-Host ("    [verify {0}/{1}] missing={2} exec={3}" -f $attempt, $MaxAttempts,
            ($(if ($check.Missing.Count) { $check.Missing -join ',' } else { '-' })),
            $check.Executable) -ForegroundColor DarkGray

        if (Test-KuduWwwRootFile -ScmBase $ScmBase -Headers $Headers -RelativePath "output.tar.zst") {
            try {
                Expand-OryxCompressedStartupArtifacts -ScmBase $ScmBase -Headers $Headers
            }
            catch {
                Write-Warn2 "Tarball extract: $($_.Exception.Message)"
            }
        }

        try {
            Publish-WwwRootStartupFiles -RepoRoot $RepoRoot -ScmBase $ScmBase -Headers $Headers
        }
        catch {
            Write-Warn2 "VFS seed: $($_.Exception.Message)"
        }

        if ($attempt -lt $MaxAttempts) {
            Start-Sleep -Seconds $IntervalSec
        }
    }
    return $false
}

function Restart-KuduSite {
    param([string]$ResourceGroup, [string]$WebAppName)
    try {
        az resource invoke-action `
            --resource-group $ResourceGroup `
            --name "$WebAppName/scm" `
            --resource-type Microsoft.Web/sites/host `
            --action restart --api-version 2022-03-01 --only-show-errors 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Kudu (scm) restarted so Oryx picks up app settings"
            Start-Sleep -Seconds 12
        }
    }
    catch {
        Write-Warn2 "Could not restart Kudu scm host (continuing): $($_.Exception.Message)"
    }
}

# -----------------------------------------------------------------------------
# 1. Pre-flight
# -----------------------------------------------------------------------------
Write-Step "Pre-flight checks"

if (-not (Test-Path $ZipPath)) {
    Write-Err2 "Zip not found: $ZipPath"
    Write-Host "  Run .\Scripts\PowerShell\Build-AzureDeployZip.ps1 first." -ForegroundColor Yellow
    exit 1
}
$zipSizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Ok "Zip: $ZipPath ($zipSizeMb MB)"

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipCheck = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    foreach ($name in @("startup.sh", "runtime.txt", "apt.txt", "requirements.txt")) {
        if (-not ($zipCheck.Entries | Where-Object { $_.FullName -eq $name })) {
            Write-Err2 "Local zip missing root entry: $name (re-run Build-AzureDeployZip.ps1)"
            exit 1
        }
    }
    Write-Ok "Local zip contains required root entries"
}
finally {
    $zipCheck.Dispose()
}

az account show --only-show-errors 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Err2 "Not logged in to Azure CLI. Run: az login"
    exit 1
}
Write-Ok "Azure CLI session active"

$appState = az webapp show -g $ResourceGroup -n $WebAppName --query "state" -o tsv 2>$null
if ($LASTEXITCODE -ne 0 -or -not $appState) {
    Write-Err2 "Web app '$WebAppName' not found in resource group '$ResourceGroup'."
    exit 1
}
Write-Ok "Web app found (current state: $appState)"

$appCommandLine = az webapp config show -g $ResourceGroup -n $WebAppName `
    --query "appCommandLine" -o tsv 2>$null
if ($appCommandLine) {
    Write-Warn2 "appCommandLine is set (bypasses deployed startup.sh): $appCommandLine"
    Write-Host "  Run .\Scripts\PowerShell\Clear-AzureStartupCommand.ps1 before deploy if the site shows the Python placeholder." -ForegroundColor Yellow
}

$scmBase = "https://$WebAppName.scm.azurewebsites.net"
$kuduHeaders = Get-KuduAuthHeader -ResourceGroup $ResourceGroup -WebAppName $WebAppName

# -----------------------------------------------------------------------------
# 2. App settings + Kudu refresh
# -----------------------------------------------------------------------------
Write-Step "Ensuring Oryx deploy settings (COMPRESS_DESTINATION_DIR=false)"
$compressSetting = az webapp config appsettings list -g $ResourceGroup -n $WebAppName `
    --query "[?name=='COMPRESS_DESTINATION_DIR'].value | [0]" -o tsv 2>$null
if ($compressSetting -and $compressSetting.ToString().ToLower() -eq "false") {
    Write-Ok "COMPRESS_DESTINATION_DIR already false"
}
else {
    az webapp config appsettings set -g $ResourceGroup -n $WebAppName `
        --settings COMPRESS_DESTINATION_DIR=false --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err2 "Failed to set COMPRESS_DESTINATION_DIR=false"
        exit 1
    }
    Write-Ok "Set COMPRESS_DESTINATION_DIR=false"
}
Write-Host "  Note: Python Oryx may still compress to output.tar.zst; deploy script guarantees flat startup files after build." -ForegroundColor DarkGray

Write-Step "Clearing WEBSITE_RUN_FROM_PACKAGE (if present)"
$hasRunFromPkg = az webapp config appsettings list -g $ResourceGroup -n $WebAppName `
    --query "[?name=='WEBSITE_RUN_FROM_PACKAGE'].value | [0]" -o tsv 2>$null
if ($hasRunFromPkg) {
    az webapp config appsettings delete `
        -g $ResourceGroup -n $WebAppName `
        --setting-names WEBSITE_RUN_FROM_PACKAGE --only-show-errors | Out-Null
    Write-Ok "Removed WEBSITE_RUN_FROM_PACKAGE (was: $hasRunFromPkg)"
}
else {
    Write-Ok "WEBSITE_RUN_FROM_PACKAGE not set - good"
}

Restart-KuduSite -ResourceGroup $ResourceGroup -WebAppName $WebAppName

if ($kuduHeaders -and $CleanDeploy) {
    Write-Step "CleanDeploy: clearing stale Oryx compressed artifacts on wwwroot (preserves Data/)"
    try {
        Clear-StaleOryxCompressedArtifacts -ScmBase $scmBase -Headers $kuduHeaders
    }
    catch {
        Write-Warn2 "Pre-clean via Kudu failed (continuing): $($_.Exception.Message)"
    }
}

# -----------------------------------------------------------------------------
# 3–5. Upload + poll (optional)
# -----------------------------------------------------------------------------
if ($SkipDeploy) {
    Write-Step "SkipDeploy: skipping zip upload (wwwroot guarantee + start only)"
}
else {
# -----------------------------------------------------------------------------
# 3. Stop web app
# -----------------------------------------------------------------------------
if (-not $SkipStop) {
    Write-Step "Stopping web app (releases Kudu + clears any stuck deploy lock)"
    az webapp stop -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
    Write-Ok "Web app stopped"
    Start-Sleep -Seconds 8
}

# -----------------------------------------------------------------------------
# 4. Async OneDeploy upload
# -----------------------------------------------------------------------------
Write-Step "Uploading zip via OneDeploy (async)"
if ($CleanDeploy) {
    Write-Host "  CleanDeploy: az webapp deploy --clean true (code-only; server Data/ not in zip)." -ForegroundColor Yellow
}
# --track-status false: avoid CLI blocking on long Oryx builds (we poll via log deployment list).
$deployArgs = @(
    "webapp", "deploy",
    "-g", $ResourceGroup,
    "-n", $WebAppName,
    "--src-path", $ZipPath,
    "--type", "zip",
    "--async", "true",
    "--track-status", "false",
    "--timeout", "1800000",
    "--only-show-errors",
    "-o", "json"
)
if ($CleanDeploy) {
    $deployArgs += @("--clean", "true")
}
$deployJson = az @deployArgs 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Err2 "Async upload submission failed:"
    Write-Host $deployJson
    exit 1
}
Write-Ok "Upload accepted by Kudu - server-side deployment in progress"

# -----------------------------------------------------------------------------
# 5. Poll deployment status
# -----------------------------------------------------------------------------
Write-Step "Polling deployment status (timeout: ${TimeoutSeconds}s)"

$statusMap = @{
    0 = "Success"
    1 = "Pending"
    2 = "Building"
    3 = "Failed"
    4 = "InProgress"
    5 = "PartiallySuccessful"
    6 = "BuildPending"
}

$start = Get-Date
$lastStatus = -1
$lastMessage = ""
$terminal = $false
$finalStatus = -1

while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSeconds) {
    Start-Sleep -Seconds $PollIntervalSec
    $latest = az webapp log deployment list -g $ResourceGroup -n $WebAppName `
        --query "[0].{status:status,message:message,id:id,complete:complete}" `
        -o json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    if (-not $latest) {
        Write-Host "    ...waiting for Kudu to register deployment" -ForegroundColor DarkGray
        continue
    }
    $code = [int]$latest.status
    $label = if ($statusMap.ContainsKey($code)) { $statusMap[$code] } else { "Unknown($code)" }
    if ($code -ne $lastStatus -or $latest.message -ne $lastMessage) {
        $elapsed = [int]((Get-Date) - $start).TotalSeconds
        Write-Host ("    [{0,4}s] status={1} ({2}) {3}" -f $elapsed, $code, $label, $latest.message) -ForegroundColor DarkGray
        $lastStatus = $code
        $lastMessage = $latest.message
    }
    if ($latest.complete -and $code -ne 3) {
        $terminal = $true
        $finalStatus = $code
        break
    }
}

if (-not $terminal) {
    Write-Warn2 "Polling window elapsed without a terminal status."
    Write-Host "  Check Kudu: $scmBase/api/deployments" -ForegroundColor Yellow
}

if ($terminal -and $finalStatus -eq 3) {
    Write-Err2 "Kudu deployment reported failure (status=3)."
    exit 1
}

# Allow Oryx post-build to finish writing output.tar.zst
Start-Sleep -Seconds 20

} # end if (-not SkipDeploy)

# -----------------------------------------------------------------------------
# 6. Guarantee wwwroot startup artifacts
# -----------------------------------------------------------------------------
Write-Step "Guaranteeing wwwroot startup artifacts (startup.sh, runtime.txt, apt.txt)"

if ($SkipWwwRootGuarantee) {
    Write-Warn2 "SkipWwwRootGuarantee set - not verifying wwwroot (not recommended)"
}
elseif (-not $kuduHeaders) {
    Write-Err2 "Could not read publishing credentials - cannot verify wwwroot"
    exit 1
}
else {
    $guaranteed = Ensure-WwwRootStartupArtifacts `
        -RepoRoot $RepoRoot -ScmBase $scmBase -Headers $kuduHeaders `
        -MaxAttempts $WwwRootVerifyRetries -IntervalSec $WwwRootVerifyIntervalSec

    Write-Step "Final wwwroot listing (Kudu)"
    Write-Host (Get-KuduWwwRootListing -ScmBase $scmBase -Headers $kuduHeaders) -ForegroundColor DarkGray

    if (-not $guaranteed) {
        Write-Err2 "Deploy FAILED: startup.sh, runtime.txt, and apt.txt are not all present and executable at wwwroot root."
        Write-Host "  Manual: Kudu -> Debug console -> ls -la /home/site/wwwroot" -ForegroundColor Yellow
        Write-Host "  Or: .\Scripts\PowerShell\Verify-AzureWwwRoot.ps1" -ForegroundColor Yellow
        exit 1
    }

    $final = Test-WwwRootStartupArtifacts -ScmBase $scmBase -Headers $kuduHeaders
    Write-Ok "startup.sh is present and executable at wwwroot root"
    Write-Ok "runtime.txt and apt.txt present at wwwroot root"

    Write-Step "Ensuring platform runs wwwroot/startup.sh (not Oryx default Gunicorn placeholder)"
    $startupCmd = "./startup.sh"
    $currentCmd = az webapp config show -g $ResourceGroup -n $WebAppName --query "appCommandLine" -o tsv 2>$null
    if ($currentCmd -ne $startupCmd) {
        $setScript = Join-Path $PSScriptRoot "Set-AzureStartupCommand.ps1"
        if (Test-Path $setScript) {
            & $setScript -ResourceGroup $ResourceGroup -WebAppName $WebAppName `
                -StartupCommand $startupCmd -SkipSmokeTest
        }
        else {
            Write-Warn2 "Set-AzureStartupCommand.ps1 not found — set Startup Command manually to: $startupCmd"
        }
    }
    else {
        Write-Ok "appCommandLine already points to $startupCmd"
    }

    if (Test-KuduWwwRootFile -ScmBase $scmBase -Headers $kuduHeaders -RelativePath "output.tar.zst") {
        Write-Warn2 "output.tar.zst still present (Oryx compressed build). Flat startup files were seeded/extracted for platform startup."
        try {
            $manifest = Invoke-RestMethod -Uri "$scmBase/api/vfs/site/wwwroot/oryx-manifest.toml" -Headers $kuduHeaders -TimeoutSec 45
            if ($manifest -match 'CompressDestinationDir="true"') {
                Write-Host "  oryx-manifest.toml has CompressDestinationDir=true (Python Oryx often ignores COMPRESS_DESTINATION_DIR=false)." -ForegroundColor DarkGray
            }
        }
        catch { }
    }
}

# -----------------------------------------------------------------------------
# 7. Start app + smoke test
# -----------------------------------------------------------------------------
Write-Step "Starting web app"
az webapp start -g $ResourceGroup -n $WebAppName --only-show-errors | Out-Null
Write-Ok "Start signal sent"

if (-not $SkipSmokeTest) {
    Write-Step "HTTP smoke test (cold-start can take 60-120s on B2)"
    $url = "https://$WebAppName.azurewebsites.net/"
    $maxTries = 18
    $smokeOk = $false
    for ($i = 1; $i -le $maxTries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 20 -UseBasicParsing -ErrorAction Stop
            $bodyPreview = $resp.Content.Substring(0, [Math]::Min(500, $resp.Content.Length))
            if ($bodyPreview -match "Hey, Python developers") {
                Write-Host ("    try {0,2}/{1}: HTTP {2} but Python placeholder HTML detected" -f $i, $maxTries, $resp.StatusCode) -ForegroundColor Yellow
            }
            elseif ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                Write-Ok "HTTP $($resp.StatusCode) from $url (not the Oryx placeholder page)"
                $smokeOk = $true
                break
            }
        }
        catch {
            Write-Host ("    try {0,2}/{1}: not ready yet ({2})" -f $i, $maxTries, $_.Exception.Message.Split("`n")[0]) -ForegroundColor DarkGray
        }
        Start-Sleep -Seconds 10
    }
    if (-not $smokeOk) {
        Write-Warn2 "Smoke test did not confirm a healthy app response (site may still be warming up)."
    }
}

Write-Step "Done"
Write-Host "  Live URL : https://$WebAppName.azurewebsites.net/"
Write-Host "  Verify   : .\Scripts\PowerShell\Verify-AzureWwwRoot.ps1"
Write-Host "  Log tail : az webapp log tail -g $ResourceGroup -n $WebAppName"
Write-Host "  Kudu UI  : $scmBase/"

if ($terminal -and $finalStatus -eq 3) { exit 1 }
exit 0
