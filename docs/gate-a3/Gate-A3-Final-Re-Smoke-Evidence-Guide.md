# Gate A3 — Final Re-Smoke Evidence Guide (Post-Poppler Fix)

Filled automatically by `Collect-GateA3Evidence.ps1 -UpdateDocs` after minimal browser smoke. See [`Gate-A3-Owner-Execution-Package-Final.md`](Gate-A3-Owner-Execution-Package-Final.md).

**Session header (fill on deploy day)**
- Deploy GUID: 4fa54010-72b0-46cd-8398-897eae0f703c
- `IMAGING_LEG poppler=ok` confirmed in Log Stream: [x] Yes  [ ] No
- `pdftoppm -v` succeeds via Kudu: [ ] Yes  [ ] No

## HCC 2026-04.pdf

| Item | 2026-05-29 Baseline (before poppler fix) | This re-smoke (imaging leg live) |
|------|-------------------------------------------|----------------------------------|
| Register rows | 98 | 98 |
| Supplemental check rows | 0 (cropper skipped) | 0 |
| Crops detected | 0 | 42 |
| Key log line | "Check cropper skipped: poppler..." | [INFO] Check cropper (geometry, DPI=400, pages 5-9, max=70)…; [INFO] Effective thresholds (DPI-scaled): min_size=(160x66 |
| Deposits / Withdrawals (from export) | $163,914 / $45,703.76 | $163,914.00 / $45,703.76 |

## Auto_Body_Center_Jan_26_Statement.pdf

| Item | Gold Baseline (Grok Vision + hardened local) | 2026-05-29 Baseline | This re-smoke |
|------|---------------------------------------------|---------------------|---------------|
| Transactions | 92 | 49 | 110 |
| Deposits | $41,786.80 | $43,860.64 | $41,786.80 |
| Withdrawals | $41,403.63 | $16,633.49 | $354,909.14 |
| Crops / supplemental | ~49-56 | Low | 56 crops / 66 supplemental |

**Pass signals for final verdict**
- HCC now shows crops + supplemental rows from imaging pages.
- Auto Body totals move meaningfully closer to gold when imaging leg is active.
- No "poppler not on PATH" or "cropper skipped" warnings.

Paste your numbers + key log excerpts below this line when complete.
---

## Autonomous collection (auto-generated)

**Collected**: 2026-05-31 06:03 UTC
### HCC 2026-04.pdf

```json
{
  "pdf": "HCC 2026-04.pdf",
  "smoke_key": "hcc",
  "client": "HCC",
  "register_rows": 98,
  "supplemental_rows": 0,
  "transaction_rows": 98,
  "crops": 42,
  "likely_checks": 0,
  "likely_deposits": 0,
  "deposits": 163914.0,
  "withdrawals": 45703.76,
  "needs_review": 98,
  "payee_rules_applied": 6,
  "payee_rows_changed": 24,
  "payee_rules_total": 25,
  "payee_merge_count": 1,
  "register_is_sparse": false,
  "register_incomplete": false,
  "supplemental_by_amount": 0,
  "supplemental_skipped_duplicates": 0,
  "payee_merge_by_amount": 1,
  "imaging_active": true,
  "cropper_skipped": false,
  "check_engine": "azure_document_intelligence",
  "status": "success",
  "duration_s": 18.27,
  "errors": [],
  "warnings": [],
  "sample_payees": [
    "Zelle",
    "Chevron",
    "Shell"
  ],
  "log_excerpt": [
    "[INFO] [DIAG] Cropper rejections this run: 2227 (size=2122, aspect=0, variance=0, rough_dup=105). Effective thresholds at 300 DPI shown above. Set SLAM_CROP_MIN_HEIGHT / SLAM_CROP_MIN_VARIANCE etc. to tune.",
    "[INFO] Check cropper extracted 42 unique crop(s).",
    "[INFO] Cropped 42 check/deposit image(s) to `/home/site/wwwroot/Scripts/cropped_checks_final_dynamic`.",
    "[INFO] Crop breakdown: 42 likely checks + 0 likely deposit slips. Deposit slips are saved with metadata for later income stream analysis (extraction deferred).",
    "[INFO] Organized crops \u2192 42 checks in /home/site/wwwroot/Scripts/cropped_checks_final_dynamic/checks, 0 deposit slips in /home/site/wwwroot/Scripts/cropped_checks_final_dynamic/deposits",
    "[INFO] Document Intelligence check model on 42 cropped PNG(s) (`prebuilt-check.us`) \u2014 cropping + per-crop analysis (primary path)\u2026",
    "[INFO] Check pass (document_intelligence_crops): 40 check(s) from imaging pages 5-7.",
    "[OK] Azure Document Intelligence: 98 transaction(s) in 18.27s.",
    "[OK] Combined 98 transaction row(s): 98 register + 0 supplemental rows appended (register pass authoritative; 40 check leg row(s) used for payee merge only); payee merge on 1 row(s).",
    "[INFO] Imaging leg complete: 0 likely checks + 0 deposit slips cropped. 40 check extractions attempted via Document Intelligence. Deposit slip data extraction deferred.",
    "[INFO] Architecture: Register leg via prebuilt bank statement model | Imaging leg via geometric crops + per-crop Document Intelligence `prebuilt-check.us`. Deposit slips cropped + saved for future processing.",
    "[INFO] Check analysis strategy used: document_intelligence_crops (approx 42 Azure check calls made this run). On free tiers expect partial results \u2014 consider a dedicated check resource for full crop coverage."
  ]
}
```

### Auto_Body_Center_Jan_26_Statement.pdf

```json
{
  "pdf": "Auto_Body_Center_Jan_26_Statement.pdf",
  "smoke_key": "auto_body",
  "client": "Auto Body Center",
  "register_rows": 44,
  "supplemental_rows": 50,
  "transaction_rows": 94,
  "crops": 56,
  "likely_checks": 0,
  "likely_deposits": 0,
  "deposits": 41786.8,
  "withdrawals": 41130.18,
  "needs_review": 94,
  "payee_rules_applied": 3,
  "payee_rows_changed": 18,
  "payee_rules_total": 25,
  "payee_merge_count": 3,
  "register_is_sparse": false,
  "register_incomplete": true,
  "supplemental_by_amount": 14,
  "supplemental_skipped_duplicates": 0,
  "payee_merge_by_amount": 3,
  "imaging_active": true,
  "cropper_skipped": false,
  "check_engine": "azure_document_intelligence",
  "status": "success",
  "duration_s": 13.2,
  "errors": [],
  "warnings": [],
  "sample_payees": [
    "Hallmark Hyundai",
    "Virement Baseball",
    "Traditions Bank"
  ],
  "log_excerpt": [
    "[INFO] [DIAG] Cropper rejections this run: 3282 (size=3189, aspect=0, variance=0, rough_dup=93). Effective thresholds at 300 DPI shown above. Set SLAM_CROP_MIN_HEIGHT / SLAM_CROP_MIN_VARIANCE etc. to tune.",
    "[INFO] Check cropper extracted 56 unique crop(s).",
    "[INFO] Cropped 56 check/deposit image(s) to `/home/site/wwwroot/Scripts/cropped_checks_final_dynamic`.",
    "[INFO] Crop breakdown: 56 likely checks + 0 likely deposit slips. Deposit slips are saved with metadata for later income stream analysis (extraction deferred).",
    "[INFO] Organized crops \u2192 56 checks in /home/site/wwwroot/Scripts/cropped_checks_final_dynamic/checks, 0 deposit slips in /home/site/wwwroot/Scripts/cropped_checks_final_dynamic/deposits",
    "[INFO] Document Intelligence check model on 56 cropped PNG(s) (`prebuilt-check.us`) \u2014 cropping + per-crop analysis (primary path)\u2026",
    "[INFO] Check pass (document_intelligence_crops): 55 check(s) from imaging pages 5-9.",
    "[OK] Azure Document Intelligence: 94 transaction(s) in 13.2s.",
    "[OK] Combined 94 transaction row(s): 44 register + 50 supplemental from checks (0 deduped by register; 14 without check#); payee merge on 3 row(s).",
    "[INFO] Imaging leg complete: 0 likely checks + 0 deposit slips cropped. 55 check extractions attempted via Document Intelligence. Deposit slip data extraction deferred.",
    "[INFO] Architecture: Register leg via prebuilt bank statement model | Imaging leg via geometric crops + per-crop Document Intelligence `prebuilt-check.us`. Deposit slips cropped + saved for future processing.",
    "[INFO] Check analysis strategy used: document_intelligence_crops (approx 56 Azure check calls made this run). On free tiers expect partial results \u2014 consider a dedicated check resource for full crop coverage."
  ]
}
```

- HCC: imaging leg active with crops detected.
- Auto Body: totals near gold baseline.
