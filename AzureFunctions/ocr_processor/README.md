# SLAM Services OCR Processor — Azure Function

**Source code status**: **v2.43 — intelligent check ↔ transaction linking.** Building on the v2.42 real-OCR pipeline, the Function now matches each cropped check image to its parsed transaction and replaces the parser's heuristic Payee with the human-written name extracted from the "Pay to the order of" line via EasyOCR. HTTP wire contract is preserved; matched transactions carry a new optional `linked_check_id` field and matched checks carry `extracted_check_number`/`extracted_payee`/`linked_transaction_index`.

> **Note on general deployment hygiene**: For the project's overall Azure deployment patterns, recovery runbooks, and modern polling-safe practices, see the main repo's `docs/deployment.md`. This document focuses on Function-specific details.

> **Deployed Azure state (as of v2.43.1, May 25, 2026)**: the live Function App `slam-ocr-function` is still running the **v2.41 skeleton stub** (`/api/ocr/health` returns `version: "v2.41-skeleton"`, the process endpoint returns 2 mock transactions). A v2.43 zip deploy attempt via Kudu `/api/zipdeploy?Deployer=oryx-build` failed after ~3 minutes — almost certainly because `easyocr` pulls in `torch` (~700 MB Linux wheel) which busts the Y1 Consumption build sandbox. `WEBSITE_RUN_FROM_PACKAGE` was restored to the v2.41-skeleton blob; the Function is back to its healthy baseline. The v2.43 source code in `function_app.py` (`PIPELINE_VERSION = "v2.43"`) is **ready** to deploy the moment one of the four packaging paths below is chosen. **The Streamlit App Service `slam-services-revenue-tracker` already has `AZURE_OCR_FUNCTION_URL` + `AZURE_OCR_FUNCTION_KEY` set correctly** — once a v2.43 build lands in Azure, no app-side change is needed and Laura's Bank Statements page picks up the intelligent check linking automatically.

## Purpose

Offload heavy OCR / check-cropping (pdfplumber, pdf2image, EasyOCR, OpenCV) from the Streamlit App Service to a dedicated Function. The Streamlit Bank Statements page calls this endpoint, the Function returns structured transactions in the canonical 12-column shape (`Date, Description, Payee, Amount, Check#, Category, SubCategory, SignedAmount, YearMonth, Confidence, NeedsReview, ReviewReason`), and the existing review UI / payee rules engine / reconciliation banner / Power Query workflow consume the response unchanged.

## Endpoints

- `POST /api/ocr/process` — main OCR endpoint. Accepts `multipart/form-data` (preferred) or JSON with a `pdf_b64` field. Function-key auth.
- `GET /api/ocr/health` — anonymous health probe used by the Streamlit sidebar status indicator. Now also reports per-library `capabilities` so the UI can diagnose missing dependencies.

See `function_app.py` for the full wire format.

## v2.43 pipeline overview

`_run_ocr_pipeline(pdf_bytes, metadata, parent_logs)` runs four stages in order, each gracefully degrading if its dependencies are missing or it fails on a particular PDF:

1. **Fast path — `pdfplumber`** (native text-layer PDFs).
   - Extracts text + words + tables from every page.
   - Feeds the result into the same regex parser used by `Scripts/bank-statement-parser.py` (`_SECTION_MARKERS`, `_CHECK_REGISTER_ROW_RE`, `_pick_transaction_amount`, `_parse_table_rows`, `_filter_balance_only_rows`, etc.).
   - Confidence baseline: `High`.
2. **Scanned fallback — `pdf2image` + `easyocr`**.
   - Only triggered when the fast path returns fewer than `OCR_FAST_PATH_MIN_ROWS` (default 3) transactions.
   - Rasterizes each page at `OCR_DPI_TEXT` DPI (default 300), runs `easyocr.Reader(["en"]).readtext()` per page, and re-buckets tokens by y-coordinate to recover line order. The OCR lines feed the same regex parser, so the response shape is identical.
   - Confidence baseline: `Medium`, `NeedsReview = "Yes"`, `ReviewReason` notes the OCR fallback.
   - Page cap: `OCR_MAX_PAGES_RASTER` (default 30) so Y1 Consumption memory stays bounded.
3. **Check cropping — `cv2` + `pdf2image` + `PIL` + `easyocr`** (best-effort).
   - Port of `Scripts/smart_check_cropper_final_dynamic.py`. Rasterizes at `OCR_DPI_CROP` DPI (default 250), runs three adaptive thresholds, finds external contours, filters by width/height/aspect ratio, validates with EasyOCR keyword detection (`pay to`, `order of`, `memo`, `dollars`), rejects bank-contact junk blocks, and deduplicates with an 8×8 perceptual hash.
   - Returns each surviving check as a base64 PNG in `cropped_checks` (with `check_id`, `page`, `width`, `height`, `aspect_ratio`).
   - v2.43 also keeps the per-token EasyOCR detections (`detail=1, paragraph=False`) in memory — not in the response — so the matcher can locate the payee line spatially without a second OCR pass.
   - Capped at `OCR_MAX_CHECKS` (default 40) so very long statements don't blow memory.
4. **Check ↔ transaction matching (v2.43, NEW)** — `_match_checks_to_transactions`.
   - For each cropped check, extracts (a) the check number (3–6 digit token scored top-right of the crop) and (b) the payee name (tokens on the "Pay to the order of" line, with fallback to the next line down when EasyOCR groups the entire header into one bbox).
   - Tries three matching strategies in priority order:
     - **Primary** — exact match on `Check#` (normalized: leading zeros stripped).
     - **Secondary** — amount equality within `$0.01` when a `$X.YZ` amount can be parsed from the check image.
     - **Tertiary** — fuzzy match between the extracted payee and the transaction's Description (`difflib.SequenceMatcher` ratio ≥ 0.60).
   - When a match is found, the matched transaction gets:
     - A new optional `linked_check_id` field (e.g. `"P00C01"`) so the App can render the cropped image inline next to the Check# row.
     - The extracted payee written back to `Payee` (only when it's more informative than what the parser already had — fuzzy ratio < 0.85 against the current Payee).
     - `Confidence` bumped to `High`, `NeedsReview="No"`, `ReviewReason="Payee from check image (<reason>)"`.
   - The cropped check entry gets `extracted_check_number`, `extracted_payee`, `extracted_payee_confidence`, and `linked_transaction_index` (`-1` when no match).
   - Unmatched checks are still returned in `cropped_checks` for manual review.
   - Every match attempt is logged at `[INFO]` level (`P00C00 -> txn #4 via check# 1234; Payee '' -> 'John Smith'`) so the Streamlit Processing log explains every Payee swap.

The EasyOCR `Reader` is **lazy-loaded and cached at module scope** so warm invocations skip the 30–60s model-download cold start.

## App Settings (Function App)

| Setting                       | Default | Purpose                                                            |
| ----------------------------- | ------- | ------------------------------------------------------------------ |
| `OCR_DPI_TEXT`                | `300`   | Raster DPI used by the EasyOCR fallback.                           |
| `OCR_DPI_CROP`                | `250`   | Raster DPI used by the check cropper (memory-friendly).            |
| `OCR_MAX_PAGES_RASTER`        | `30`    | Hard cap on pages processed in the OCR fallback / cropper.         |
| `OCR_MAX_CHECKS`              | `40`    | Hard cap on cropped checks per request.                            |
| `OCR_FAST_PATH_MIN_ROWS`      | `3`     | Fast-path threshold below which the EasyOCR fallback kicks in.     |
| `OCR_FUNCTION_ANON_LOCAL`     | unset   | If `1`, allows anonymous `/ocr/process` for local `func start` only — **never set in Azure**. |

## Dependencies

See `requirements.txt`. Key packages:

- `azure-functions>=1.18.0`
- `pdfplumber>=0.11.0`
- `pdf2image>=1.17.0` *(requires `poppler-utils` on the OS; ships with the Linux Y1 image)*
- `easyocr>=1.7.0` *(downloads its English model into `/tmp` on first call)*
- `pillow>=10.0.0`
- `opencv-python-headless>=4.8.0`
- `numpy>=1.26.0`

## Local run

```powershell
cd AzureFunctions\ocr_processor
Copy-Item local.settings.json.sample local.settings.json
python -m pip install -r requirements.txt
func start
# Then in another shell:
Invoke-RestMethod -Uri http://localhost:7071/api/ocr/health
```

`OCR_FUNCTION_ANON_LOCAL=1` in `local.settings.json` makes the `/ocr/process` route anonymous for local testing only.

### Smoke-test the real OCR with a sample PDF

```powershell
$pdfBytes = [System.IO.File]::ReadAllBytes("C:\path\to\sample-statement.pdf")
$b64 = [Convert]::ToBase64String($pdfBytes)
$body = @{ pdf_b64 = $b64; filename = "sample.pdf"; client = "Smoke Test" } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Uri "http://localhost:7071/api/ocr/process" -Method Post -ContentType "application/json" -Body $body |
    ConvertTo-Json -Depth 6 |
    Out-File local-ocr-response.json
```

The first call will download the EasyOCR English model (~64 MB) into `~/.EasyOCR`; subsequent calls are fast.

## Deploy / redeploy to Azure

Infrastructure (Resource Group, Storage Account, Linux Y1 Consumption plan, Function App) was provisioned in v2.41 — see Blueprint v2.41 Change Log for the original runbook.

### v2.43.1 deployment status & open infra decision

The v2.41 skeleton blob (`function-releases/slam-ocr-function-v2.41-skeleton.zip`, ~5 KB, no OCR libs) is the active package. The v2.43 source code is on disk but **not yet deployed** because the heavy ML stack (`easyocr` + `torch` ≈ 700 MB manylinux wheel, plus `opencv-python-headless`, `pdf2image`, `pdfplumber`, `pillow`, `numpy`) busts the Y1 Linux Consumption build sandbox. A v2.43.1 redeploy attempt with Oryx remote build (`az functionapp deployment source config-zip --build-remote true` and then `Invoke-RestMethod .../api/zipdeploy?isAsync=true&Deployer=oryx-build` via Kudu basic auth) failed after ~3 minutes with `status=Failed` and no recoverable build log (Kudu Lite on Y1 doesn't expose `/api/vfs/LogFiles/` or full deployment logs).

**Four candidate paths forward** (Laura's call):

| Option | Effort | Cost | Trade-off |
| ------ | ------ | ---- | --------- |
| **A. Pre-bundle manylinux wheels** | ~30-60 min in WSL/Docker | none | Build `.python_packages/lib/site-packages` locally with `pip install --target ... --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.10 -r requirements.txt`, zip the whole thing (~800 MB-1 GB), rotate `WEBSITE_RUN_FROM_PACKAGE`. Skips Oryx entirely; approaches Y1's 5 GB content share cap. |
| **B. Upgrade to Elastic Premium EP1** | ~10-20 min after upgrade | ~$144/mo | 3.5 GB RAM, 250 GB disk, always-warm. Oryx remote build handles heavy ML wheels comfortably. Easiest technically but ongoing OpEx. |
| **C. Pivot to Azure Document Intelligence** | ~half-day rewrite | pay-per-page (~$0.01-0.05/page) | Drops `easyocr` + `torch` + `opencv-python-headless`; uses the `prebuilt-bankStatement.us` model. Mirrors the v2.45 roadmap item below; no Y1 infra change needed. |
| **D. Stay on v2.41-skeleton** | 0 | 0 | Laura's daily workflow already has two working paths (Lightweight Parser + Grok CSV paste). Real Azure OCR only matters for scanned PDFs the Lightweight Parser can't read; Grok Vision covers that today. Defer until a real scanned PDF actually blocks her. |

### Two-step redeploy runbook (when an option is chosen)

```powershell
# 1) Build a fresh zip (from the repo root)
$zip = "C:\Temp\slam-ocr-function-v2.43.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path AzureFunctions\ocr_processor\* -DestinationPath $zip -Force
# (Option A only: do the manylinux pip install --target into the source folder FIRST
#  so .python_packages/lib/site-packages is included in the zip.)

# 2) Upload to the SAS-secured release blob and rotate WEBSITE_RUN_FROM_PACKAGE
$RG_STG = "SLAM-Services-RG"
$STG    = "slamocrstg2605251016"
$RG     = "SLAM-OCR-Functions-RG"
$APP    = "slam-ocr-function"

az storage blob upload `
    --account-name $STG `
    --container-name function-releases `
    --name slam-ocr-function-v2.43.zip `
    --file $zip `
    --overwrite `
    --auth-mode login

# Generate a 5-year read-only SAS for the new blob
$expiry = (Get-Date).AddYears(5).ToString("yyyy-MM-ddTHH:mm:ssZ")
$sas = az storage blob generate-sas `
    --account-name $STG --container-name function-releases `
    --name slam-ocr-function-v2.43.zip `
    --permissions r --expiry $expiry --https-only `
    --auth-mode login --as-user --full-uri -o tsv

# Rotate WEBSITE_RUN_FROM_PACKAGE via ARM REST (az CLI mangles & in SAS URLs)
$subId = az account show --query id -o tsv
$body = @{ properties = @{ WEBSITE_RUN_FROM_PACKAGE = $sas } } | ConvertTo-Json -Depth 4
$body | Out-File -Encoding utf8 -NoNewline C:\Temp\arm-rfp.json
az rest --method patch `
    --uri "https://management.azure.com/subscriptions/$subId/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/appsettings?api-version=2023-12-01" `
    --body "@C:\Temp\arm-rfp.json"

az functionapp restart --name $APP --resource-group $RG

# 3) Health check (expect version: v2.43 after a 30-60s cold start)
Start-Sleep -Seconds 45
Invoke-RestMethod -Uri "https://$APP.azurewebsites.net/api/ocr/health"
```

> **Gotcha** (bit us twice during v2.43.1 deploy attempt): `az functionapp config appsettings set --settings WEBSITE_RUN_FROM_PACKAGE=<SAS URL>` silently truncates the SAS URL at the first `&` even when quoted, even from a `@settings.json` file. Use the `az rest PATCH /config/appsettings` path above with the full settings dict in a single JSON body — that's the only reliable way to set SAS-laden App Settings on Linux Function Apps.

> **Oryx remote-build path** (only viable on Options B or C; Y1 Consumption can't fit the v2.43 stack): remove `WEBSITE_RUN_FROM_PACKAGE`, set `SCM_DO_BUILD_DURING_DEPLOYMENT=true` + `ENABLE_ORYX_BUILD=true`, ensure basic publishing credentials are `allow=true` on both `scm` and `ftp` (via `az rest PUT .../basicPublishingCredentialsPolicies/{scm,ftp}` with `{"properties":{"allow":true}}`), then `az functionapp deployment source config-zip --resource-group $RG --name $APP --src $zip --build-remote true`. The v2.43.1 attempt of this path failed in ~3 minutes on Y1; expect ~10 minutes on EP1.

The `WEBSITE_RUN_FROM_PACKAGE` App Setting points at the SAS URL of `function-releases/slam-ocr-function-*.zip` (5-year expiry, HTTPS-only, read-only). Each redeploy uploads a new uniquely-named blob and rotates the SAS URL on the App Setting — the previous blob stays in place as a one-click rollback target.

### Streamlit App Settings

These were set in v2.41 and stay the same:

- `AZURE_OCR_FUNCTION_URL` → `https://slam-ocr-function.azurewebsites.net/api/ocr/process`
- `AZURE_OCR_FUNCTION_KEY` → `az functionapp keys list --name slam-ocr-function --resource-group SLAM-OCR-Functions-RG --query functionKeys.default -o tsv`

## Verification

After a redeploy, expect to see in the response:

- `status: "success"` for native text-layer PDFs with ≥3 transactions.
- `version: "v2.43"`.
- `transactions` populated with realistic `Date`, `Description`, `Amount`, `SignedAmount`, `Check#`, `Confidence` values; **matched** transactions (those linked to a cropped check) carry an extra `linked_check_id` field, a richer `Payee` taken from the check image, `Confidence="High"`, and a `ReviewReason="Payee from check image (...)"` audit note.
- `grok_totals` matching the underlying statement (used by the reconciliation banner).
- `cropped_checks` containing one or more base64 PNGs for any actual check images in the PDF; each entry now also carries `extracted_check_number`, `extracted_payee`, `extracted_payee_confidence`, and `linked_transaction_index` (`-1` for manual-review fallthrough).
- `logs` showing structured `[INFO]`/`[WARN]`/`[OK]` lines from each pipeline stage, including the new check-linking lines (`P00C00 -> txn #4 via check# 1234; Payee '' -> 'John Smith'`).

### Sample matched-transaction snippet

```jsonc
{
  "transactions": [
    {
      "Date": "2026-05-10",
      "Description": "Check #1234",
      "Payee": "John Smith",              // ← from check image (was "")
      "Amount": "-1234.56",
      "Check#": "1234",
      "Category": "Uncategorized",
      "SubCategory": "",
      "SignedAmount": "-1234.56",
      "YearMonth": "2026-05",
      "Confidence": "High",               // ← bumped from Medium/blank
      "NeedsReview": "No",
      "ReviewReason": "Payee from check image (check# 1234)",
      "linked_check_id": "P00C01"         // ← v2.43 only
    }
  ],
  "cropped_checks": [
    {
      "check_id": "P00C01",
      "page": 1,
      "width": 980,
      "height": 420,
      "aspect_ratio": 2.33,
      "image_b64": "<base64 PNG>",
      "notes": "v2.43 grid+dedup (thresh 0)",
      "extracted_check_number": "1234",
      "extracted_payee": "John Smith",
      "extracted_payee_confidence": 0.91,
      "linked_transaction_index": 4
    }
  ],
  "logs": [
    "[INFO] Check-linking: matching 3 cropped check(s) against 27 transaction(s).",
    "[INFO]   P00C01 -> txn #4 via check# 1234; Payee '' -> 'John Smith' (check#='1234', conf=0.91).",
    "[INFO] Check-linking: 3/3 cropped check(s) linked to transactions; 0 unmatched (returned for manual review)."
  ]
}
```

## Roadmap

- **v2.44 (next)** — render the `cropped_checks` PNG inline on the Bank Statements review page next to each linked `Check#` row using `linked_check_id` (currently the metadata flows through `_parse_ocr_response_to_df` but is not yet displayed).
- **v2.45+** — optional Azure Document Intelligence prebuilt bank-statement model as a fourth, highest-fidelity branch (selectable per-client via App Setting).
