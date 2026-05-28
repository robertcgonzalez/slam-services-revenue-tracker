#Requires -Version 5.1
<#
.SYNOPSIS
  Install heavy Local Enhanced OCR + optional Azure CV SDK into the project .venv.

.DESCRIPTION
  Installs heavy OCR + CV packages for native Windows (same stack as production pipeline).
  Requires an existing .venv (run Setup-LocalVenv.ps1 first) and poppler on PATH
  for pdf2image (see Setup-LocalVenv.ps1 output for download link).

.EXAMPLE
  .\.venv\Scripts\Activate.ps1
  .\Scripts\PowerShell\Install-LocalHeavyOcr.ps1
  .\run_local.ps1
#>
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$SkipCvSdk
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv — run .\Scripts\PowerShell\Setup-LocalVenv.ps1 first."
}

Write-Host "=== SLAM Services — Install Local Heavy OCR (Windows) ===" -ForegroundColor Cyan
Write-Host "PyTorch via easyocr is large (~1.5 GB); first install may take several minutes." -ForegroundColor Yellow

& $python -m pip install --upgrade pip
& $python -m pip install --upgrade `
    "pdfplumber>=0.11" `
    "pdf2image>=1.17" `
    "pillow>=10.0" `
    "numpy>=1.26" `
    "opencv-python-headless>=4.8" `
    "easyocr>=1.7"

if (-not $SkipCvSdk) {
    Write-Host "Installing Azure Computer Vision SDK (hybrid CV check leg)..." -ForegroundColor Cyan
    & $python -m pip install --upgrade `
        "azure-cognitiveservices-vision-computervision>=0.9" `
        "msrest>=0.7"
}

Write-Host ""
Write-Host "Pre-warming EasyOCR English model (~30 MB)..." -ForegroundColor Cyan
& $python -c @"
import easyocr
easyocr.Reader(['en'], gpu=False, verbose=False)
print('EasyOCR model OK')
"@

$env:PYTHONPATH = "App"
Write-Host ""
Write-Host "Capability matrix:" -ForegroundColor Green
& $python -c "import local_enhanced_ocr as o; import json; print(json.dumps(o.detect_capabilities(), indent=2))"

try {
    $pdftoppm = Get-Command pdftoppm -ErrorAction Stop
    Write-Host "poppler (pdftoppm): $($pdftoppm.Source)" -ForegroundColor Green
} catch {
    Write-Host "WARNING: pdftoppm not on PATH — check cropper / pdf2image will fail until poppler is installed." -ForegroundColor Red
    Write-Host "  https://github.com/oschwartz10612/poppler-windows/releases" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. Copy Scripts\spike\cv-read.env.sample to .env and run .\run_local.ps1" -ForegroundColor Green
