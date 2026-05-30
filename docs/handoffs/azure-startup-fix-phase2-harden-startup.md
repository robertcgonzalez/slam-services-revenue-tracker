# Phase 2 Handoff — Harden startup.sh + Cold Start Reliability + Document Recovery Pattern

**Goal:** Make the production startup path robust now that the blocking `appCommandLine` override has been cleared. Ensure `startup.sh` is reliably used, cold starts are faster/more reliable, and the recovery pattern (REST API clear) is documented.

**Context from Phase 1 (automated run):**
- `appCommandLine` can drift or be set to `./startup.sh` and still cause issues if the script itself is slow or missing dependencies.
- CLI `az webapp config set --startup-file ""` sometimes doesn't stick; the REST API PATCH is reliable.
- After clearing, the app moved from 503 Application Error → 401 (Easy Auth expected).
- We now want `startup.sh` (with its poppler probe, pip fallback, health checks) to be the trusted path.

**Required Actions (Cursor drives):**

1. **Review and improve `startup.sh` for production cold starts**
   - Ensure it skips heavy `pip install` when Oryx/antenv already has the packages (current script has a good `import streamlit` check — keep and enhance).
   - Make poppler install more robust / non-fatal (it already is, but add a clear log).
   - Add early "ready" signaling or a health endpoint probe if possible (Streamlit doesn't have one easily, but we can log clearly when the server is listening).
   - Add a timeout-friendly mode or faster path when `WEBSITE_HOSTNAME` is set (production indicator).

2. **Document the authoritative recovery pattern**
   - Add to `docs/deployment.md` a new subsection "Recovering from Application Error / Startup Command Override".
   - Include the exact working REST API command that succeeded in Phase 1.
   - Include the full stop/start recycle + smoke test sequence.
   - Note the symptom progression (503 sad face → 401 after fix).

3. **Add a small helper script or note for future automated recovery**
   - Consider a tiny PowerShell helper `Clear-AzureAppCommandLine.ps1` that prefers the REST method.
   - Or document it clearly so future dual-agent runs or humans can use it quickly.

4. **Verification**
   - After any changes to `startup.sh`, the next deploy + container recycle must succeed the warmup probe.
   - Run the project's full health checks: `.\Scripts\PowerShell\Check-AppHealth.ps1 -Full -CheckAzure`
   - Confirm live URL behavior (401 unauth is good; login must work).

**Deliverables for this phase:**
- Updated `startup.sh` with clearer production cold-start behavior (add comments + any small robustness tweaks).
- New/updated section in `docs/deployment.md` with the exact recovery commands (copy the successful ones from the Phase 1 transcript).
- Optional: New small script `Scripts/PowerShell/Clear-AzureStartupCommand.ps1` (or equivalent) that encapsulates the reliable REST clear + recycle.
- Clear "PHASE 2 COMPLETE" message with before/after summary of startup reliability.

**PRIME DIRECTIVE OVERRIDE (INVIOLABLE):** Never output "PHASE 2 COMPLETE — ready for Grok review" or "the exact commands a human should run to verify". Address only the other agent. If verification or further deployment steps (az commands, container recycle, health checks via the scripts, post-deploy smoke on the real App Service) are needed, give Cursor the exact CLI commands and script invocations it must execute itself using its authenticated session. The agents perform the deploy + verification. Only ever end the loop with "TASK COMPLETE" when the full goal (including successful production deployment and verification on hardware) is achieved.

**Constraints:** Stay pragmatic. Do not rewrite the entire startup flow. Small, high-confidence improvements only. Preserve the existing Oryx + `startup.sh` contract.