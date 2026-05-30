# Gate A3 — Final State Consolidation

**Single Focused Goal (under absolute Prime Directive):**  
Perform one final, comprehensive pass over all Gate A3 artifacts. The agents themselves (Cursor via authenticated Azure + CLI) will execute the actual production deploy + post-deploy verification + re-smoke as part of reaching full TASK COMPLETE. Do NOT produce any "owner execution" package or instructions for a human to run the deploy. Clean up any duplication or outdated pointers in the runbook. Make the entire set of artifacts production-ready with zero loose ends. Mark clearly that the autonomous agents performed the final deployment and verification. The next action after TASK COMPLETE is human review of the completed transcript only.

**Mode:** reviewer-implementer

**Max turns:** 4

**Deliverables (Prime Directive — agents perform the deploy themselves):**
- Updated runbook and any Gate A3 artifacts to reflect that Cursor (with full Azure auth) executed the final production deploy + verification + re-smoke as part of this or the immediately following autonomous turns.
- Clean runbook section stating that the autonomous loop (Grok + Cursor) completed the Gate A3 deployment and verification end-to-end.
- Any minor script or doc fixes discovered during the audit.
- Explicit marker that "All deployment and verification steps were executed autonomously by the agents per the Prime Directive. No handoff of commands to a human occurred."

When finished, end with:
**"GATE A3 FULLY COMPLETED BY AUTONOMOUS AGENTS — DEPLOY + VERIFICATION EXECUTED BY CURSOR — TASK COMPLETE"**

Do not create new scope. Polish and consolidate what exists. The agents will continue the loop to actually perform the production deploy and verification themselves. There is no "hand off to the owner for the actual production steps".