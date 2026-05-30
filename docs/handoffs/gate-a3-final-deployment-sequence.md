# Gate A3 — Final Deployment + Verification Sequence (Owner Execution)

**Single Focused Goal (Prime Directive — agents perform the deployment themselves):**  
The autonomous agents (Cursor with full authenticated Azure + terminal access) will themselves execute the complete deployment sequence, post-deploy verification of `IMAGING_LEG poppler=ok`, capture of the Deploy GUID, container operations, and the subsequent re-smoke + evidence collection inside the loop. Produce any improved helper scripts or consolidated command blocks that the *agents* will invoke directly (never instructions for an owner/human to run). The deliverable is the evidence and logs proving the agents successfully performed the production deployment and verification on the real hardware.

**Mode:** reviewer-implementer

**Max turns:** 4

**Constraints (Prime Directive — full agent autonomy on hardware):**
- Must be directly executable by Cursor (authenticated Azure extension + terminal) inside the autonomous loop.
- Agents perform the deploy + verify + re-smoke themselves; produce no "owner package" or human-run sequence.
- Must reference/improve `Test-GateA3Poppler.ps1` etc. so the agents can invoke them end-to-end.
- Include clear success/failure signals the agents will check and log.
- The output is evidence that the agents executed the full sequence on production.

**Deliverable:**
- Any improved helper scripts the agents will call.
- The exact commands + arguments the agents will use in the next autonomous turns to perform the real deployment, verification, GUID capture, and re-smoke.
- Updated runbook / package text stating "Deployment and verification executed autonomously by Cursor per Prime Directive."

When finished, end with **"DEPLOYMENT SEQUENCE READY FOR AGENTS TO EXECUTE — NO HUMAN HANDOFF"**.

Do the work. Do not add scope. The agents will continue the loop and actually run the deployment on the live systems.