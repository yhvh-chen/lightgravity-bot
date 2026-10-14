"""Frozen contract constants (docs/08-interface-contract.md §2, §4)."""

from __future__ import annotations

SCHEMA_NAMESPACE = "lightgravity.bot/v1"
#: docs/08 §13: 1.3.0 (2026-10-15) registers LG-009's additive Task ``checks``
#: authorization and ``acceptance`` candidate-binding fields (``candidate_ref``/
#: ``candidate_plan_hash``/``check_records``/``note``), the read-only
#: ``GET /tasks/{task_id}/acceptance`` endpoint, LG-025's settings detail/default
#: endpoints, and the singleton global-conversation messages endpoints.  It also
#: records the LG-014 ``POST /files/upload``/``GET /files/download`` paths as
#: planned (not implemented).  Existing endpoint semantics, error codes, event
#: types, enums and state transitions are unchanged from 1.2.0.
CONTRACT_VERSION = "1.3.0"
API_PREFIX = "/api/v1"

__all__ = ["SCHEMA_NAMESPACE", "CONTRACT_VERSION", "API_PREFIX"]
