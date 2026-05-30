# Dual-Agent — Project Status, Roadmap & Recommendations

**Date**: 2026-05 (Current)
**Status**: Prime Directive Update — Full autonomous end-to-end iteration is now the enforced procedure (overrides all phased/human-review patterns). Core prompts + docs updated so agents continue until the complete task goal with no intermediate human summaries.

**Prime Directive (runtime-enforced)**: The loop iterates for every possible agent-executable step (code, CLI with full auth, tests, deploys, verification) until 100% of the user's original task is done. Only `TASK COMPLETE` ends it.

**SLAM alignment (June 2026)**: The project's canonical `Invoke-GitVerification.ps1` + updated thin contracts now make the "full autonomous verification → commit → push to main" path executable and consistent with the Prime Directive inside dual-agent runs on this repo. The verification script is the single-source hygienic gate.

**Date of last structural change**: 2026-06 (this update)
**Prior Status**: Phase 1 + Phase 2 + Hardening Complete (Single source of truth + robust Cursor handoff + live doctor validation)
**Owner**: Built for SLAM Services project by Grok (xAI) in collaboration with user

---

## What Was Built

### Phase 1 — Foundation & Distribution (Completed)
- Full autonomous installation system for Windows
- Strong support for both `pip` and `uv` (uv is strongly preferred on Windows for speed)
- Proper **global installation** support (`~/.grok/tools/dual-agent`)
- Persistent availability via PowerShell profile modification (`~/.grok/bin` added to PATH)
- `dual-agent doctor` health check command
- Multiple Windows-specific robustness fixes (encoding, Unicode in Rich, Pydantic strictness, launcher improvements)
- Clean separation between development source (`tools/dual-agent` in repo) and user global install

### Phase 2 — Domain-Specific Value (Completed)
- Deep exploration of the SLAM Services codebase (payee extraction, OCR pipelines, Azure DI, spike work, hybrid CV systems)
- Creation of **6 high-quality, ready-to-use pre-baked templates** specifically designed for this project:
  - `payee-extractor-hardening`
  - `ocr-pipeline-robustness`
  - `spike-to-production-refactor`
  - `azure-di-hybrid-integration`
  - `large-scale-cleanup`
  - Plus general templates
- New `dual-agent templates` command (list + view full templates)
- Templates are embedded in the tool and available after global install

### Core Architecture
- **Mediator pattern**: The Python orchestrator runs two independent agents:
  - Grok (via `grok` CLI headless + JSON)
  - Cursor (via official `cursor-sdk` + `CURSOR_API_KEY`)
- Supports multiple collaboration modes with different relationship dynamics (reviewer-implementer is currently the strongest for code quality work)
- Session persistence and resume capability
- Full working directory context for both agents

---

## Current Capabilities (as of this commit)

**Major June 2026 refresh**: The source tree in `tools/dual-agent/` is now the single source of truth. Global installs are snapshots that should be refreshed after source changes via `install-global.ps1`.

- Robust Cursor handoff with reliable text extraction (`wait()` + multiple fallbacks), agent resumption via IDs, and rich diagnostics per turn.
- `dual-agent doctor` now performs a **live Cursor agent creation test** (the #1 source of previous "it doesn't work" reports) when a valid key is present.
- All collaboration modes correctly receive relationship prompts on the first turn.
- Windows 3.10/3.14 bridge shims + encoding robustness preserved.
- Run structured, multi-turn autonomous collaborations between Grok and Cursor agents
- Use high-signal templates tailored to SLAM Services work (payee extraction, OCR/CV pipelines, spike-to-prod migrations, etc.)
- Global `dual-agent` command available in every PowerShell session (refresh after source edits)
- `dual-agent doctor` + `dual-agent templates` fully functional
- Solid Windows support (hardened venv recommended via the Invoke-DualAgentHandoff.ps1 wrapper)

**This successfully eliminates manual copy-paste loops** between the two agents for scoped tasks.

---

## Future Features & Roadmap (Prioritized)

### High Priority (High ROI)
1. **Live Rich TUI Dashboard** (Phase 3)
   - Real-time side-by-side view of Grok and Cursor output
   - Turn counter, status, cost/latency estimates
   - Streaming updates instead of batch
   - This was the most requested "wow" feature

2. **Better Template System**
   - `dual-agent suggest "description of task"` → recommends best template + mode
   - Ability to create and save custom templates easily
   - Template versioning / library

3. **Self-Update & Installation Improvements**
   - `dual-agent self update` (pull latest from repo + reinstall)
   - One-command global install from anywhere (`dual-agent install --global`)

### Medium Priority
4. **Enhanced Collaboration Modes & Prompt Engineering**
   - More sophisticated handoff logic between agents
   - Support for "Grok leads research, Cursor executes" more robustly
   - Ability to inject project-specific rules / AGENTS.md automatically

5. **Observability & Cost Tracking**
   - Track number of turns, tokens (where possible), time spent
   - Session analytics (`dual-agent stats`)

6. **MCP / Tool Exposure**
   - Expose dual-agent itself as an MCP tool so either Grok or Cursor can call the other mid-task

### Lower Priority / Nice to Have
- Web UI for monitoring long-running collaborations
- Support for cloud Cursor agents (not just local SDK)
- Integration with Cursor Hooks for automatic triggering
- Multi-repo support

---

## Recommendations

### For Daily Use
- Keep the global installation as your primary way to run it.
- Use `dual-agent doctor` before important runs.
- Start most tasks with one of the built-in templates (especially `payee-extractor-hardening` and `spike-to-production-refactor`).
- Use `--max-turns 4-6` for most work unless you have a very well-scoped task.
- Prefer `reviewer-implementer` mode for code quality work.

### For Development of the Tool Itself
- Work in `C:\slam-services-project\tools\dual-agent`
- After changes, re-run `scripts\install-global.ps1` (or the manual sync commands) to update your global copy
- The source in this repo is the canonical version

### Model & Key Guidance
- The Cursor side uses the `CURSOR_MODEL` you set in the global `.env` (currently `composer-2.5`)
- This is independent of your Cursor IDE settings
- Grok side uses whatever the `grok` CLI is configured with on your machine
- Keep your `CURSOR_API_KEY` secure (it's in `.env` in the global location)

---

## Known Limitations & Gotchas

- Rich library can still have occasional Unicode/encoding issues on some Windows terminals (mitigated with `PYTHONIOENCODING=utf-8`)
- The orchestrator currently does **not** stream live output in a beautiful TUI (this is the main missing piece)
- Cursor SDK is still in beta — some advanced features may change
- No automatic cost tracking yet
- Does not replace normal interactive use of Cursor IDE — it is a complementary automation tool

---

## Summary of Value Delivered

This project successfully created a **working, distributable, project-aware autonomous collaboration system** between Grok and Cursor.

The biggest wins:
- Eliminated manual output pasting for complex tasks
- Created reusable, high-context templates for this specific codebase
- Made the tool trivially available from any terminal
- Strong foundation for future advanced features (especially the live dashboard)

**Status**: Ready for productive use on SLAM Services work today.

---

*Document generated as part of the initial dual-agent implementation effort.*
