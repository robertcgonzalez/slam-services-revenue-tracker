# Example High-Value Tasks for dual-agent

These are battle-tested task descriptions that work especially well with the reviewer-implementer and researcher-builder modes.

## Code Quality & Hardening

```bash
dual-agent run "Audit the entire payee_extractor/ directory for robustness, error handling, and logging. Add production-grade error boundaries, structured logging, and defensive checks. Do not change external behavior." --mode reviewer-implementer --max-turns 6
```

## Large Refactors

```bash
dual-agent run "Refactor the OCR pipeline (Scripts/e2e_local_ocr.py and related modules) to separate concerns better. Introduce clear stage interfaces, improve testability, and reduce god-function smell. Keep all existing functionality working." --mode architect-coder
```

## New Feature Spikes

```bash
dual-agent run "Research and implement support for a new bank statement format (Chase business checking). Add detection, parsing, and payee extraction. Start with a spike document, then implement the minimal viable parser." --mode researcher-builder
```

## Security / Compliance

```bash
dual-agent run "Perform a security and data-leakage review of all code that touches customer bank statements and checks. Identify every place PII or financial data is logged, stored temporarily, or transmitted. Propose and implement fixes." --mode critic-refiner
```

## Documentation + Code Alignment

```bash
dual-agent run "Go through the current README.md and docs/ and make sure every major module and script is accurately described. Where the docs are wrong or missing, fix the docs AND add missing docstrings / module headers in the code." --mode reviewer-implementer
```

## Performance Pass

```bash
dual-agent run "Profile the current local OCR pipeline end-to-end on a representative batch of statements. Identify the top 3 slowest areas and optimize them (algorithmic + implementation). Document before/after numbers." --mode researcher-builder
```

## Migration / Porting

```bash
dual-agent run "Port the critical path of the check leg detection logic from the old hybrid_cv_check_leg.py into a clean, well-tested module under App/. Maintain exact behavioral parity on the existing test images." --mode architect-coder
```
