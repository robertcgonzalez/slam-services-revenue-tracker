# Full Deployment Resolution — Un-seize the Project (End-to-End by Agents)

**Goal:** Get the production App Service `slam-services-revenue-tracker` fully live and functional so the project is no longer seized.

The Streamlit revenue tracker UI must be reachable at the live URL and working (actual app login/dashboard, not Microsoft "Sign in to your account" page or 503/Service Unavailable).

All latest code, startup.sh, and deployment artifacts from the most recent clean deploy must be active in the container.

**IMAGING_LEG poppler=ok** must be confirmed in the container startup logs (geometric cropper + per-crop DI enabled).

Postgres connection must either be made reliable (firewall rules + connection string + any DB user/DB creation) **or** safely fallen back (USE_POSTGRES=false with CSV mode) so the app starts cleanly without hanging.

Every step — az CLI commands, config changes (auth, app settings, startup command), restarts, log inspection, health checks, smoke tests, imaging leg verification — must be executed by Cursor itself using its authenticated Azure extension and terminal.

**Do not** output any "run this yourself" commands for a human/owner. The agents own the entire resolution.

Drive until the site is demonstrably working end-to-end for both the tabular revenue requests path and the imaging/check cropper + DI path.

When the full goal is achieved and verified on the live production systems, end with **TASK COMPLETE**.

**Mode:** reviewer-implementer
**Max turns:** 20 (use as many as needed for cold starts, deploys, and verification)