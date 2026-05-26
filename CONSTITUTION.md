# SLAM Services Project Constitution

**Version**: 1.0  
**Date**: May 26, 2026  
**Status**: Foundational document for the Cursor + Grok agent operating model (post v2.44.2 architecture work).

---

## Purpose

SLAM Services LLC is transforming from a highly manual, memory-driven, paper-heavy bookkeeping and tax practice into a structured, partially automated, professional operation.

The goal is to reduce reliance on any single person’s memory, minimize manual data chasing (especially revenue requests and bank reconciliations), provide real-time visibility, and create auditable, maintainable processes — enabling a smooth transition of day-to-day work to Patty & Robert while winning and maintaining Laura’s confidence.

---

## Non-Negotiables

These are immutable:

- **Laura’s confidence** is the primary success metric. Visible quick wins, clean reliable code, and minimal disruption take priority.
- **Security and data privacy are absolute**. Client financial data (CSVs, statements, etc.) must never enter git. Never commit secrets, `.env` files, or sensitive material.
- **Pragmatic minimalism**. Prefer simple, maintainable, low-maintenance solutions over complex or overly elegant ones. "Good enough for daily driver use" beats perfect but delayed.
- **Document role discipline**. All agents must respect the Documentation Roles Matrix in README.md. Content must live in exactly one place according to defined roles. Never introduce duplication across documents.

---

## Decision-Making Framework

- When in doubt, default to what increases Laura’s confidence and reduces manual toil for the daily users (Laura, Stef).
- Prefer paths that are reliable, observable, and easy for non-technical team members to understand and maintain.
- Run the full local verification sequence (`git status`, `git diff --cached --stat`, `git check-ignore -v`, explicit sensitive-path scan + before/after summary) before any git operation.
- "Good enough" that works reliably today is usually better than ideal that ships later.

---

## Agent Operating Model

- **Cursor** (Composer / Agent / inline edit) is the **primary / lead** AI coding agent.
- **Grok** (this environment and other Grok-assisted sessions) is the official **secondary** agent.
- Neither overrides the other; both follow the same project rules.

**Core rules for all agents**:
- The Documentation Roles Matrix in README.md is the single authoritative map of every document’s purpose. Read it before any documentation work.
- Follow the **anti-bloat / role-respect** standing order: never introduce duplication. Content must live in exactly one place according to the roles.
- Follow the **git authority via confirmation** rule: you may perform git operations only after executing and logging the full local verification sequence.
- Thin agent contracts (`.cursor/rules/slam-services.mdc` and `.grok/AGENT.md`) are the only things that belong in an agent’s default context window. Everything else is referenced by pointer, not embedded.

---

## Core Success Criteria

- Laura and Stef can complete daily revenue tracking, bank statement processing, and status management with significantly less manual chasing and reliance on memory.
- The system is reliable and transparent enough that Patty & Robert can confidently take over day-to-day operations.
- The practice demonstrates professionalism and consistency through clear processes, auditability, and minimal disruption during the transition.

## Maintenance & Evolution

The Constitution is maintained through **periodic review by agents**.

- **Review frequency**: As frequently as the context demands (no fixed schedule).
- **Authority**: Agents decide when content should move between layers or documents, provided the change improves clarity, reduces bloat, or better serves the project's goals.
- **Constraint**: All changes must preserve the essence and goals of the overall project.
- **Documentation**: Significant updates to the Constitution or major shifts in document boundaries should be recorded in the Blueprint Change Log.

---

*This Constitution is the primary artifact that should be loaded first by any agent working on the project. It is deliberately short and high-signal. Detailed history, rationale, and current status live in the Blueprint and README per the Documentation Roles Matrix.*