"""Frozen contract constants (docs/08-interface-contract.md §2, §4)."""

from __future__ import annotations

SCHEMA_NAMESPACE = "lightgravity.bot/v1"
#: docs/08 §13: 1.4.0 (2026-10-15) registers LG-015's additive
#: ``PATCH /resources/{kind}/{id}`` controlled write, the ``GET /team/available``
#: and ``GET /team/members`` read endpoints, and the additive Task-message
#: ``resource_proposal`` field that routes a bounded resource change through the
#: coordinator and ``ResourceService.update``, with the actual result/conflict
#: written back as ``resource_result.status``.  Existing endpoint semantics,
#: error codes, event types, enums and state transitions are unchanged.
#:
#: 1.3.1 (2026-10-15) marks LG-014's ``POST /files/upload``/
#: ``GET /files/download`` (registered as planned in 1.3.0) as implemented and
#: states the machine-check evidence-reference semantics: workspace-relative refs
#: resolve under the authorized workspace root, executor artifacts are
#: canonicalized as ``evidence:<run_id>/<name>@sha256:<hex>`` under the Task/Run
#: evidence root, and raw absolute paths are rejected.
#:
#: 1.3.0 registered LG-009's additive Task ``checks`` authorization and
#: ``acceptance`` candidate-binding fields (``candidate_ref``/
#: ``candidate_plan_hash``/``check_records``/``note``), the read-only
#: ``GET /tasks/{task_id}/acceptance`` endpoint, LG-025's settings detail/default
#: endpoints, and the singleton global-conversation messages endpoints.
CONTRACT_VERSION = "1.4.0"
API_PREFIX = "/api/v1"

__all__ = ["SCHEMA_NAMESPACE", "CONTRACT_VERSION", "API_PREFIX"]
