# CAPA Escalation & Usage Instructions

This document defines **when and how** to create a formal Corrective Action (CAPA) record under the SLAM Services QMS baseline.

## When to Open a Formal CAPA

Escalate a `feedback_log.csv` entry (or direct observation) to a CAPA **only** when at least one of the following is true:

1. **P0 / Blocking** — The issue prevents Laura or Stef from completing daily revenue tracking or bank statement work.
2. **Recurring** — The same class of problem has appeared in two or more versions or across multiple client statements / users.
3. **Systemic** — Affects data integrity, security, multiple clients, auditability, or Laura’s fundamental confidence in the system.
4. **Cross-version impact** — The root cause lives in architecture, shared libraries, deployment process, or QMS controls themselves.
5. **Management Review or State Alignment decision** — The review explicitly logs an action as a formal CAPA.

**Default rule**: Most items stay in `feedback_log.csv` + Section 14 triage. Only the minority that meet the above criteria become CAPAs. This keeps overhead near zero.

## How to Open a CAPA

1. Copy the relevant row details from `Data/feedback_log.csv`.
2. Create a new file in `QMS/CAPA/` using `CAPA-YYYY-NNN.md` (increment the number).
3. Fill the template:
   - Description (copy from feedback)
   - Root cause (do real analysis — 5 Whys or evidence-based diagnosis is required)
   - Containment (if needed)
   - Corrective action plan with owner + date
4. Add a row in `feedback_log.csv` (or update the existing row) with `status = "In Progress - CAPA-YYYY-NNN"` and a note linking to the new file.
5. Announce in the next iteration planning / Section 14 update.

## During the Fix

- Every significant diagnostic, decision, or partial fix should be recorded in the Blueprint Change Log (not buried in the CAPA file).
- The CAPA file is the **coordination and closure record**, not the history of the fix.

## Verification & Closure

- Verification must be **objective** (test result, before/after numbers, direct confirmation from Laura, re-execution of the original failing scenario with evidence).
- After verification, complete the CAPA template, update the feedback_log row to "Done", and reference the exact Blueprint Change Log entry that delivered the fix.
- Prevention of recurrence is mandatory — even if it is "added a guard in `_is_clean_payee`" or "updated the State Alignment inputs list".

## Anti-Bloat Reminders

- A CAPA that produces only a one-line code comment and no process change is usually a regular bug fix, not a CAPA.
- Do not open a CAPA for every documentation typo or minor UI friction.
- If three similar small issues appear, consider whether a single CAPA on the pattern is more appropriate than three separate files.

## Required Elements of a Formal CAPA

Every CAPA must include (at minimum):

1. Clear description of the nonconformity (from feedback_log).
2. Root cause analysis (5 Whys or equivalent evidence-based diagnosis — already the norm in major Change Log entries).
3. Immediate containment / mitigation (if applicable).
4. Corrective action with owner and target date.
5. Verification of effectiveness (regression test, user confirmation, or before/after metric).
6. Closure recorded with link to the specific Blueprint Change Log entry that delivered the fix.
7. Prevention of recurrence (process change, rule, guard, or automation — the anti-bloat standing order helps here).

## Relationship to Other QMS Artifacts

- CAPAs are a primary input to Management Reviews.
- Patterns discovered across multiple CAPAs are prime material for State Alignment runs.
- High-severity or long-open CAPAs must appear on the Risk Register.

---

*Note: The 7-element structure above was previously documented in Blueprint Section 15.3. It has been moved here as part of the 2026-05-28 hub evolution so that operational QMS detail lives in the QMS folder.*

---

**Current open CAPAs**: List the files in this folder (none at initial baseline activation).

*When in doubt, keep the item in feedback_log + Section 14. Escalate to CAPA only when the criteria above are clearly met.*