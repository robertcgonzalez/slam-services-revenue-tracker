---
name: large-scale-cleanup
category: maintenance
difficulty: medium
recommended_mode: critic-refiner
---

# Task: Large-Scale Codebase Hygiene / Technical Debt Reduction

The project has gone through many rapid sprints (G1, G2, multiple OCR/CV spikes). There is accumulated technical debt, duplication, and outdated code.

## Instructions
1. Perform a broad but targeted audit of the requested area (e.g. `App/`, `Scripts/`, specific modules).
2. Identify the highest-impact problems:
   - Duplicated logic
   - Dead or near-dead code paths
   - Inconsistent error handling / logging
   - Poor module boundaries
   - Outdated comments or docs that no longer match reality
   - Missing or weak tests on critical paths
3. Propose a prioritized cleanup plan.
4. Execute the highest-value cleanups with minimal risk.
5. Leave clear notes on anything that was intentionally left for later (with justification).

## Good Targets
- The `Scripts/` directory (many one-off spike scripts)
- `App/` core modules after major extractor or pipeline changes
- Any area that has had 3+ major refactors in the last few months

Be ruthless but responsible. The goal is to make the codebase easier to work in, not just to make it "prettier".
