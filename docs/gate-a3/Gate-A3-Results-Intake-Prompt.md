# Gate A3 — Results Intake Prompt (for Grok or Cursor)

**Purpose**: When autonomous collection is unavailable, use this prompt with pasted evidence. **Preferred path:** run `Collect-GateA3Evidence.ps1 -Both -UpdateDocs` and analyze `deploy-logs-temp/gate-a3-intake-bundle.json`.

---

**Prompt to paste (to Grok or Cursor):**

---

You are acting as the analyst for Gate A3 of the SLAM Services production go-live.

**Context (authoritative):**
- All P0 imaging work (OpenCV, pdf2image, Poppler, page clamping, deploy hygiene) has been deployed to B2.
- Data layer is live on PostgreSQL via `Invoke-DataLayerGoLive.ps1` (98 clients / 36 requests).
- The only remaining gate is validation of the **check/imaging leg** on the live production App Service using the two real PDFs.

The human has just completed the live re-smoke and pasted the evidence below (Processing logs, results per PDF, observations).

**Your task:**
1. Carefully analyze the pasted evidence against the criteria in `docs/gate-a3/Gate-A3-Post-Smoke-Scorecard-Scaffolding.md`.
2. Fill out the scorecard completely and honestly.
3. Produce a clear overall verdict on the check/imaging leg (PASS / CONDITIONAL PASS / NEEDS MORE WORK / FAIL for production use).
4. Recommend Path A, Path A with caveats, Path B (register-only), or further work.
5. Update (or propose updates to) the main runbook with the final Gate A3 status.
6. Propose the exact next commit scope and message (only if the verdict supports it).
7. Be direct about any remaining risks or inconsistencies observed.

**Pasted evidence from human:**

```
[PASTE THE FILLED EVIDENCE TEMPLATE + KEY PROCESSING LOG EXCERPTS HERE]
```

**Output format:**
- Completed scorecard table
- Clear 1-2 sentence overall verdict on the check/imaging leg
- Path recommendation with reasoning
- Proposed runbook updates (specific rows/sections)
- Proposed commit message + scope (if applicable)
- Any immediate recommended follow-up actions for the human

Use the files in `docs/gate-a3/` as the source of truth for criteria. Do not soften hard failures.

---

**Prime Directive Override:** After analysis the autonomous agents continue. The loop (Grok + Cursor) will decide on and execute commit / apply docs / deployment steps / pilot actions itself using full authenticated capabilities. There is no handoff for the human to "decide on execution". The only human involvement is post-TASK-COMPLETE review of the completed transcript.

**Important constraints:**
- Never claim the live smoke was performed by AI.
- Respect that client data in the pasted report stays out of git.
- The runbook remains the single source of truth.