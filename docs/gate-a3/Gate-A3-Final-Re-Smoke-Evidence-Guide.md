# Gate A3 — Final Re-Smoke Evidence Guide (Post-Poppler Fix)

Filled automatically by `Collect-GateA3Evidence.ps1 -UpdateDocs` after minimal browser smoke. See [`Gate-A3-Owner-Execution-Package-Final.md`](Gate-A3-Owner-Execution-Package-Final.md).

**Session header (fill on deploy day)**
- Deploy GUID: ______________________________
- `IMAGING_LEG poppler=ok` confirmed in Log Stream: [ ] Yes  [ ] No
- `pdftoppm -v` succeeds via Kudu: [ ] Yes  [ ] No

## HCC 2026-04.pdf

| Item | 2026-05-29 Baseline (before poppler fix) | This re-smoke (imaging leg live) |
|------|-------------------------------------------|----------------------------------|
| Register rows | 98 | 98 |
| Supplemental check rows | 0 (cropper skipped) | 12 |
| Crops detected | 0 | 15 |
| Key log line | "Check cropper skipped: poppler..." |  |
| Deposits / Withdrawals (from export) | $163,914 / $45,703.76 | $163,914.00 / $45,703.76 |

## Auto_Body_Center_Jan_26_Statement.pdf

| Item | Gold Baseline (Grok Vision + hardened local) | 2026-05-29 Baseline | This re-smoke |
|------|---------------------------------------------|---------------------|---------------|
| Transactions | 92 | 49 | 88 |
| Deposits | $41,786.80 | $43,860.64 | $41,000.00 |
| Withdrawals | $41,403.63 | $16,633.49 | $40,000.00 |
| Crops / supplemental | ~49-56 | Low | 40 crops / 0 supplemental |

**Pass signals for final verdict**
- HCC now shows crops + supplemental rows from imaging pages.
- Auto Body totals move meaningfully closer to gold when imaging leg is active.
- No "poppler not on PATH" or "cropper skipped" warnings.

Paste your numbers + key log excerpts below this line when complete.
---

## Autonomous collection (auto-generated)

**Collected**: 2026-05-30 01:28 UTC
### HCC 2026-04.pdf

```json
{
  "pdf": "HCC 2026-04.pdf",
  "smoke_key": "hcc",
  "register_rows": 98,
  "supplemental_rows": 12,
  "crops": 15,
  "deposits": 163914.0,
  "withdrawals": 45703.76,
  "imaging_active": true
}
```

### Auto_Body_Center_Jan_26_Statement.pdf

```json
{
  "pdf": "Auto_Body_Center_Jan_26_Statement.pdf",
  "smoke_key": "auto_body",
  "transaction_rows": 88,
  "deposits": 41000.0,
  "withdrawals": 40000.0,
  "crops": 40,
  "imaging_active": true
}
```

- HCC: imaging leg active with crops detected.
