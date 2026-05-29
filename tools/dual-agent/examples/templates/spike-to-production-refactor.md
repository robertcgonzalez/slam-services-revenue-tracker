---
name: spike-to-production-refactor
category: architecture
difficulty: medium-hard
recommended_mode: architect-coder
---

# Task: Refactor Spike Code into Production Structure

The user has accumulated a large amount of high-value logic inside `Scripts/spike/`. The goal is to carefully promote the best pieces into the real `App/` package while maintaining backward compatibility and test coverage.

## Typical Scope
- Payee extraction logic (from `Scripts/spike/payee_extractor/` → `App/payee_extractor/`)
- Hybrid CV + OCR helpers
- Check cropping improvements
- Bank-specific configuration and profiles
- Validation / grading utilities that have proven useful

## Instructions
1. Identify the highest-ROI modules or functions currently living only in spike.
2. Design a clean production API (new modules, classes, or functions in `App/`).
3. Perform the migration while preserving exact behavior on all existing test artifacts and harnesses.
4. Add proper documentation, type hints, and module-level explanations.
5. Update any spike harnesses that depend on the old locations (they should become thin wrappers or import from the new location).
6. Ensure the change does not break the main `App/app.py` or Azure Functions paths unless explicitly scoped.

## Success Criteria
- The production `App/` package is meaningfully better (more maintainable, better abstractions, fewer duplicated concepts).
- All existing automated tests, rescoring workflows, and human validation packages continue to work.
- Clear migration notes or deprecation path documented.
- No surprises in the main application or deployed functions.

## Recommended First Targets (based on current project state)
- The mature payee extractor engine + profiles
- Any well-tested hybrid pipeline components
- Useful diagnostic / visualization helpers that have survived multiple sprints

Use the various `G1_*`, `POST_E1_*`, and `EXTRACTOR_EVOLUTION_DESIGN.md` documents as context for what has already proven valuable.
