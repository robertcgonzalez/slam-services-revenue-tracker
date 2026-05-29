---
name: azure-di-hybrid-integration
category: integration
difficulty: hard
recommended_mode: researcher-builder
---

# Task: Azure Document Intelligence + Local Hybrid Improvements

Work on the integration between local OCR/CV pipelines and Azure Document Intelligence (or Content Understanding).

## Focus Areas
- Better pre-filtering or routing decisions (when to use local vs Azure)
- Improved post-processing / reconciliation between the two sources
- Handling cases where one system succeeds and the other fails (especially on checks or complex layouts)
- Cost/latency optimization while maintaining quality
- Structured output consistency (CSV schema, confidence scores, etc.)

## Instructions
1. Review current usage of Azure DI in `App/azure_document_intelligence.py`, `App/azure_content_understanding.py`, and any spike harnesses that call them.
2. Analyze recent failure cases from real bank statements or check images.
3. Design and implement improvements to the hybrid decision logic or output merging.
4. Add good observability (logging, metrics, or diagnostic artifacts) so it's easier to understand why a particular document took a certain path.
5. Validate on a mix of easy and hard real documents.

## Deliverables
- Clear improvements to the hybrid path with before/after evidence
- Updated configuration or routing logic
- Documentation explaining the decision criteria
- Any new test harnesses or evaluation scripts that make future hybrid work easier
