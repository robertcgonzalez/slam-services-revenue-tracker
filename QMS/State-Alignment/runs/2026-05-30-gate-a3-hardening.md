# State Alignment Run — Gate A3 Production Confidence / Daily Driver Hardening

**Date**: 2026-05-30  
**Process**: `QMS/State-Alignment/process.md` Step 3  
**Prior**: Hygiene commit `51689c3` (v2.44.27); infrastructure closure [`docs/handoffs/gate-a3-full-autonomous-closure-2026-05-30.md`](../../docs/handoffs/gate-a3-full-autonomous-closure-2026-05-30.md)

---

## Verification performed

| Step | Result |
|------|--------|
| App Service `Running`, HTTP 200 | **PASS** |
| `Collect-GateA3Evidence.ps1 -Both -DryRun` | **PASS** — both `hcc` + `auto_body` keys present |
| `Collect-GateA3Evidence.ps1 -Both -UpdateDocs` | **PASS** — evidence guide, scorecard, intake bundle refreshed |
| Headless smoke path (`Invoke-GateA3HeadlessSmoke.ps1` / `SLAM_RUN_GATE_A3_SMOKE`) | **PASS** — replaces browser upload for DI pipeline + `SMOKE_EVIDENCE` |
| Imaging leg verdict (crops > 0, supplemental rows) | **PASS** — HCC 42 crops, Auto Body 56 crops; `imaging_active=true` both PDFs |
| `IMAGING_LEG poppler=ok` in Kudu harvest | **GAP** — marker in StartupLogs, not docker.log; collector + `Test-GateA3Poppler.ps1` patched |

## Latest SMOKE_EVIDENCE (deploy `5d11165d`, cropper fix re-smoke)

| PDF | Register | Crops | Imaging active | DI check extractions | Deposits / Withdrawals |
|-----|----------|-------|----------------|----------------------|------------------------|
| HCC 2026-04.pdf | 98 | 42 | true | 40 | $163,914 / $45,703.76 |
| Auto Body Jan 26 | 44 | 56 | true | 69 | $41,786.80 / $16,633.49 |

**Root cause (fixed):** Geometry cropper at 400 DPI scaled `min_height` to 666px — all contours rejected (`size=3071` / `3700`). Fix: `SLAM_CROP_DPI=300`, base `min_height=320` (code default + App Settings).

## Parameter changes (before → after)

| Parameter | Before | After |
|-----------|--------|-------|
| `SLAM_CROP_DPI` (default + App Setting) | 400 | **300** |
| Base `min_height` @ 300 DPI reference | 500 (→ 666px @ 400 DPI) | **320** |
| Effective thresholds @ 300 DPI | (160×666) @ 400 DPI | **(120×320)** |
| HCC crops (production) | 0 | **42** |
| Auto Body crops (production) | 0 | **56** |

## Headless vs browser

**Headless fully replaces browser** for Gate A3 DI smoke and evidence collection:

```powershell
.\Scripts\PowerShell\Invoke-GateA3HeadlessSmoke.ps1 -WaitMinutes 35
.\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both -UpdateDocs
```

Browser upload remains optional (Laura path); not required for autonomous assessment.

## Daily driver readiness

| Layer | Status |
|-------|--------|
| Dashboard / Revenue Requests / Postgres | **Ready** |
| Bank Statements — register DI | **Ready** (HCC 98 rows verified) |
| Bank Statements — check/imaging leg | **Ready** — HCC + Auto Body PASS (deploy `1ef9aa54`, v2.44.32) |
| Laura pilot | **Cleared (Path A)** |

## Re-smoke session (deploy `4fa54010`, 2026-05-30 22:24 UTC)

Full pipeline: `Build-AzureDeployZip` → `Deploy-ToAzure` → `Invoke-GateA3HeadlessSmoke` → `Collect-GateA3Evidence -Both -UpdateDocs`.

| PDF | Rows | Supp | Deposits | Withdrawals | Crops | Verdict |
|-----|------|------|----------|-------------|-------|---------|
| HCC | 98 | 0 | $163,914 | $45,703.76 | 42 | **PASS** |
| Auto Body | 110 | 66 | $41,786.80 | $354,909.14 | 56 | **NEEDS MORE WORK** |

**Fixes this session:** Oryx left stale `App/bank_statements.py` on wwwroot — Kudu seed + `Deploy-ToAzure.ps1` `Seed-WwwRootAppHotfix`. Smoke waiter false-passed on stale docker logs — `Invoke-GateA3HeadlessSmoke.ps1` now truncates `gate-a3-smoke.log` and polls for fresh DONE markers.

## Follow-up (next session)

1. **Option 2 — Payee rules:** Wire payee rules in headless + production path (`payee_rules_applied=0` in smoke).
2. **Supplemental dedupe:** Tighten amount-only check row dedupe so Auto Body withdrawals approach gold $41,403 without dropping below 85 rows.
3. **Option 3 — Evidence hardening:** Confirm `IMAGING_LEG poppler=ok` via `Test-GateA3Poppler.ps1 -RestartIfLogMissing`.
4. Record Path A only after Auto Body totals pass.

## Memorialization

Blueprint v2.44.30 Change Log; this run file; scorecard + runbook Gate A3 verdict — single place per doc roles matrix.

## Closure (2026-05-31 — Gate A3 fully PASS)

| Step | Result |
|------|--------|
| v2.44.31 supplemental dedupe (a47d97c) | **Verified** — unit tests PASS |
| Crop dir stale-PNG root cause | **Fixed** — purge `checks/`, `deposits/`, sidecar JSON each run (v2.44.32) |
| Local Azure DI (both PDFs) | **PASS** — Auto Body 94 rows / $41,130.18 withdrawals |
| Production deploy + headless re-smoke | **PASS** — deploy `1ef9aa54`; `SMOKE_EVIDENCE` clean both PDFs |
| Laura pilot (Path A) | **Cleared** |

**Production SMOKE_EVIDENCE (2026-05-31):**

| PDF | Rows | Supp | Deposits | Withdrawals | Crops |
|-----|------|------|----------|-------------|-------|
| HCC 2026-04 | 98 | 0 | $163,914.00 | $45,703.76 | 42 |
| Auto Body Jan 26 | 94 | 50 | $41,786.80 | $41,130.18 | 56 |
