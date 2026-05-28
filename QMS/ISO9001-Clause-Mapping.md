# ISO 9001:2015 Clause Mapping — SLAM Services QMS Baseline

**Status**: Living operational artifact (moved from Blueprint Section 15.5 during hub evolution, 2026-05-28).

**Purpose**: This document provides the detailed evidence mapping of existing project controls to ISO 9001:2015 clauses. It supports the lightweight QMS baseline declared in the Blueprint (Section 15).

**Owner**: Robert. Updated during Management Reviews or after significant process changes.

**Relationship to Blueprint**: The Blueprint Section 15 contains the high-level baseline declaration and "why". This file owns the detailed, updatable clause-by-clause evidence.

**Update rule**: Any changes here should be summarized in a Blueprint Change Log entry and considered during the next Management Review or State Alignment run.

---

## Control Mapping — Existing Project Artifacts to ISO 9001:2015 Clauses

This table is the core evidence that the project already operates a de-facto QMS. Only the most relevant controls are listed.

| ISO 9001:2015 Clause | Intent | Existing SLAM Control(s) | Primary Evidence Location | Gap Status (v2.44.8) |
| --- | --- | --- | --- | --- |
| **4 Context of the organization** | Understand internal/external issues, interested parties, scope | Constitution (purpose), Blueprint Executive Summary + Stakeholder Map (Section 5), Business problem.docx | Blueprint Sections 1–5, Constitution | None material |
| **5 Leadership** | Commitment, policy, organizational roles | CONSTITUTION.md (immutable non-negotiables + decision framework), Agent operating model (Cursor/Grok roles), Laura’s confidence as primary metric | CONSTITUTION.md, README agent section, every Change Log entry | None |
| **6 Planning** | Risks & opportunities, objectives, change planning | Section 11 (Open Questions), spike decision briefs (B1–B6), proposed state alignment process, owner decision logs | Blueprint Section 11, Documents/g1_decision_brief_*, Scripts/spike/POST_* | Lightweight Risk Register CSV not yet formalized (acceptable for v1) |
| **7 Support** | Resources, competence, awareness, communication, documented information | Local Windows dev policy (`docs/environment-policy.md`), health_check.py + capability detection, agent contracts, Documentation Roles Matrix + anti-bloat rule, full Change Log | README, .cursor/rules/slam-services.mdc, .grok/AGENT.md, docs/, Blueprint Change Log | None |
| **8 Operation** | Planning & control of processes, control of externally provided processes | Bank statement pipeline (parser + OCR + rules + reconciliation banner), payee rules engine, _is_clean_payee guard, verification sequences before every git/deploy | App/, Scripts/, health checks, UAT checklists | None for current scope |
| **9 Performance evaluation** | Monitoring, measurement, analysis, evaluation, internal audit, management review | feedback_log.csv + Section 14, health_check.py, capability reports in sidebar, rigorous before/after metrics in every major Change Log entry | feedback_log.csv, Section 14, Scripts/health_check.py, Blueprint | Formal internal audit program not present (out of v1 scope); Management Review now defined in Blueprint 15.4 |
| **10 Improvement** | Nonconformity & corrective action, continual improvement | feedback_log.csv + Section 14 triage, root-cause discipline in Change Log (v2.44.3 etc.), documentation hygiene passes, state alignment proposal, anti-bloat standing order as preventive control | feedback_log.csv, Section 14, Blueprint Change Log entries, docs/proposed-state-alignment-process.md | None — this is one of the project’s strongest areas |

---

## Version History

- **2026-05-28**: Table moved from Blueprint Section 15.5 into this dedicated QMS companion as part of the hub evolution. Content preserved verbatim at time of move. Future updates will be tracked here.

*This document is intentionally focused. It is the single source for the detailed clause mapping.*