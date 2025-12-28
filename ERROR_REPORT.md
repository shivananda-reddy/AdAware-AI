# Error Report

This document lists the issues identified in the codebase during the review.

## Findings

1. **Missing consent flag in API schema**
   - `backend/services/pipeline.py` checks `payload.consent` before invoking LLM enrichment, but `HoverPayload` in `backend/schemas.py` did not define this field. Any request relying on LLM consent would raise an attribute error and fail the request. A `consent: bool = False` field was added to the schema to align with pipeline expectations.

2. **Mutable default values in Pydantic models**
   - Several list fields (`flags`, `subcategories`, `brand_entities`, `emotions`, and `rule_triggers`) used mutable defaults. With Pydantic v2, these lists can be shared across instances, leading to accidental state leakage between responses. They were updated to use `Field(default_factory=list)` to ensure each instance gets its own list.

3. **Duplicate imports and logger initialization**
   - `backend/main.py` repeated imports and logger setup, introducing dead code and risking inconsistent initialization. The duplicate block was removed so the application bootstraps from a single, clean set of imports.
