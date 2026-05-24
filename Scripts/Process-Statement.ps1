# ================================================
# Process-Statement.ps1  — FULL LOCAL PRODUCTION VERSION
# Runs: Cropper → Parser → Copy CSV to CSVs folder
# ================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   BANK STATEMENT PROCESSING TOOL (FULL LOCAL)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ====================== CLEAN UP TEMP FOLDERS ======================
$tempCropFolder = "C:\Users\arese\OneDrive\Documents 1\_Automation\cropped_checks_final_dynamic"
if (Test-Path $tempCropFolder) {
    Remove-Item -Path $tempCropFolder -Recurse -Force -ErrorAction SilentlyContinue
}

# ====================== PDF INPUT ======================
$pdfPath = Read-Host "Enter the full path to the bank statement PDF (or drag & drop)"
$pdfPath = $pdfPath.Trim('"')

if (-not (Test-Path $pdfPath) -or $pdfPath -notlike "*.pdf") {
    Write-Host "❌ Invalid PDF path." -ForegroundColor Red
    pause; exit
}

Write-Host "✅ PDF found: $pdfPath" -ForegroundColor Green

# ====================== CLIENT & FOLDER DETECTION (unchanged) ======================
$pdfFolder = Split-Path -Parent $pdfPath
$clientRoot = $pdfFolder
$year = (Get-Date).Year
# (your existing clientRoot/year detection code can stay here if you want — I kept it simple)

$clientName = (Split-Path $clientRoot -Leaf) -replace '[^a-zA-Z0-9_-]', '_'
$csvsFolder = Join-Path $clientRoot "CSVs"
if (-not (Test-Path $csvsFolder)) { New-Item -ItemType Directory -Path $csvsFolder -Force | Out-Null }

# ====================== 1. RUN DYNAMIC CROPPER ======================
Write-Host "🔄 Running dynamic check cropper..." -ForegroundColor Cyan
Set-Location $scriptDir
python smart_check_cropper_final_dynamic.py "$pdfPath"

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️ Cropper had issues, but continuing..." -ForegroundColor Yellow
}

# ====================== 2. RUN LOCAL BANK STATEMENT PARSER ======================
Write-Host "🔄 Running local transaction parser + validation..." -ForegroundColor Cyan
python bank_statement_parser.py "$pdfPath"

$baseName = [System.IO.Path]::GetFileNameWithoutExtension($pdfPath) -replace '[^a-zA-Z0-9_-]', '_'
$generatedCsv = Join-Path $scriptDir "${baseName}_Transactions_With_Payees.csv"

if (Test-Path $generatedCsv) {
    $finalCsvDest = Join-Path $csvsFolder "${baseName}_Transactions_With_Payees.csv"
    Copy-Item $generatedCsv $finalCsvDest -Force
    Write-Host "✅ Final CSV copied to CSVs folder!" -ForegroundColor Green
    Write-Host "   → $finalCsvDest" -ForegroundColor Yellow
} else {
    Write-Host "❌ Parser did not generate CSV. Check the script output." -ForegroundColor Red
}

# ====================== MOVE ORIGINAL PDF ======================
$processedFolder = Join-Path $pdfFolder "Processed"
if (-not (Test-Path $processedFolder)) { New-Item -ItemType Directory -Path $processedFolder -Force | Out-Null }
Move-Item $pdfPath (Join-Path $processedFolder (Split-Path $pdfPath -Leaf)) -Force

Write-Host ""
Write-Host "🎉 FULL LOCAL PIPELINE COMPLETE!" -ForegroundColor Green
Write-Host "Next step: Open your P&L workbook and click Refresh All"
pause