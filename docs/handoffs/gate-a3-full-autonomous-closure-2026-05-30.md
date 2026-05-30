# Gate A3 — Full Autonomous Closure (Service Principal Only)

**Status (2026-05-30, Cursor session):** Production **restored and healthy** (HTTP 200). Infrastructure closure criteria met except DI `SMOKE_EVIDENCE` (headless smoke blocked by Oryx tarball boot path — fix shipped in repo; one more orchestrated run needed).

**Executor:** Cursor via `dual-agent-slam-services` service principal only (`a856cf9c-b750-4e04-a19e-73620d74108d`).

## Evidence summary

| Criterion | Result | Evidence |
|-----------|--------|----------|
| App Service running | **PASS** | Was **Stopped** (403); started via SP; state **Running** |
| Streamlit UI reachable | **PASS** | HTTP **200**, Streamlit title (intermittent **503** during cold recycle) |
| `IMAGING_LEG poppler=ok` | **PASS** | StartupLogs `2026_05_30_lw0mdlwk0000Y5_success.log` — e.g. `2026-05-30T05:22:40Z` |
| PostgreSQL | **PASS** | `USE_POSTGRES=true`; startup: `PostgreSQL connection OK` — **clients=98, requests=36** |
| SP-only Azure ops | **PASS** | All `az`/Kudu/deploy via injected SP; no personal `az login` |
| Gate A3 DI smoke (`SMOKE_EVIDENCE`) | **PENDING** | Collector missing `hcc`/`auto_body`; root cause: Oryx `output.tar.zst` overwrote flat wwwroot on boot |

## Actions performed (autonomous)

1. Authenticated with service principal from `tools/dual-agent/.env`.
2. Started `slam-services-revenue-tracker` (was stopped).
3. Enabled `USE_POSTGRES=true`; synced Postgres firewall for outbound IPs.
4. Built and deployed `slam-app.zip` (deploy IDs `dd1e9ff4`, `e74643bd`).
5. Verified imaging + DB via StartupLogs and HTTP probes.
6. Implemented/fixed headless smoke path:
   - `startup.sh`: `SLAM_RUN_GATE_A3_SMOKE` background runner → `wwwroot/tmp/gate-a3-smoke.log`
   - `Invoke-GateA3HeadlessSmoke.ps1`: app-container smoke via app setting + restart (not Kudu sandbox)
   - `Collect-GateA3Evidence.ps1`: harvest `containerStream` + `wwwroot/tmp/gate-a3-smoke.log`
   - `Deploy-ToAzure.ps1`: re-seed `startup.sh` after Oryx sync; `If-Match: *` on VFS puts
7. Diagnosed Oryx: each boot extracts `output.tar.zst` to `/tmp/<id>/` with **stale** startup; **fix:** `Deploy-ToAzure.ps1` now re-seeds repo `startup.sh` after Oryx sync (`If-Match: *`). Latest deploy restored HTTP 200.

## Postgres (documented)

- Server: `slam-services-db.postgres.database.azure.com` (Ready, PG 16)
- App settings: `USE_POSTGRES=true`, `POSTGRES_*` configured
- Live check (startup): **98 clients / 36 requests**

## Next command (finish DI evidence)

After app is stable (no `output.tar.zst` on wwwroot):

```powershell
.\Scripts\PowerShell\Invoke-GateA3HeadlessSmoke.ps1 -WaitMinutes 35
.\Scripts\PowerShell\Collect-GateA3Evidence.ps1 -Both -UpdateDocs
```

Minimal browser alternative: upload + process the two canonical PDFs once, then run the collector.

## Closure phrase

Emit **`TASK COMPLETE — GATE A3 AUTONOMOUSLY CLOSED ON LIVE SYSTEMS`** only after `Collect-GateA3Evidence.ps1 -Both` exits 0 on production.
