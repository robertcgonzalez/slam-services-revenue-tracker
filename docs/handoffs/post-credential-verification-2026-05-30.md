# Post-Credential Setup Verification – Full Deployment Resolution

**Goal (Single Focused Task):**  
Using only the dedicated `dual-agent-slam-services` Service Principal (injected via environment variables), complete end-to-end verification that the production site `slam-services-revenue-tracker` is fully operational and un-seized.

**Specific Requirements:**
1. Authenticate to Azure using **only** the injected service principal credentials. Confirm identity is not a personal account.
2. Verify the live site returns the real Streamlit application (not Microsoft sign-in, not 503, not placeholder).
3. Confirm `IMAGING_LEG poppler=ok` is active in the current running container (pull recent startup logs if needed).
4. Run the project's health checks and any available imaging leg / Gate A3 smoke tests against the live site.
5. Test basic application functionality (login with configured credentials, dashboard loads, etc.).
6. If Postgres connectivity is still failing, note the exact error and whether the expanded firewall rules resolved it (or recommend next steps).
7. Produce a clear summary of what is now working vs. any remaining blockers.

**Constraints:**
- All Azure operations must use the service principal.
- Do not fall back to local user credentials or IDE extensions.
- Drive all steps autonomously (CLI, log inspection, verification).

**Success Criteria:**
- Site is demonstrably serving the real application.
- Imaging leg status is confirmed.
- Clear pass/fail report on health and functional smoke tests.
- Identity confirmation that the dual-agent service principal was used.

When the full verification is complete, end with:
**TASK COMPLETE – VERIFICATION RESULTS**

**Mode:** reviewer-implementer
**Max turns:** 15 (use as needed for log collection, cold starts, and thorough testing)