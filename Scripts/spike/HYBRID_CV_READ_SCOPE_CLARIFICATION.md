# Scope Clarification — Azure CV Read Hybrid (Photo Leg Only)

**Date**: 2026-05-27  
**Status**: Authoritative for all hybrid CV Read integration work (G1 decision support and beyond)

## Scope Boundary

This spike and any subsequent bounded integration is **strictly limited** to improving the *attached image register* of checks and deposit slips (the "photo leg").

- The **tabular bank statement register** (the transaction rows extracted from the statement text and layout) continues to be owned and managed entirely by the existing logic in `App/app.py` (and the relevant parsers in `App/bank_statements.py` / `App/local_enhanced_ocr.py`).
- CV-enhanced payee data extracted from check and deposit slip images will be **wrapped into** the initial tabular bank statement read process. The hybrid output enhances specific fields on rows that the core tabular parser has already produced.
- The hybrid CV Read path is an enhancement layer only. It does **not** replace, restructure, or take ownership of the core register extraction, row counts, totals, or canonical 12-column structure.

All G2 validation work, integration sprint design, UI choices, and future decisions must respect this boundary. Any proposal that would move ownership of the tabular register away from `App/app.py` is out of scope.

**References**: This clarification governs `POST_SPIKE_INTEGRATION_PLAN.md` and all related G1/G2 artifacts.
