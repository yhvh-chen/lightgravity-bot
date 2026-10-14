"""Frozen contract constants (docs/08-interface-contract.md §2, §4)."""

from __future__ import annotations

SCHEMA_NAMESPACE = "lightgravity.bot/v1"
#: docs/08 §13: 1.2.0 (2026-10-15) registers LG-008's additive control fields
#: (Run ``plan``/``plan_hash``/``plan_source``; Subtask ``objective``/
#: ``capability``/``key``/``write``/``config_hash``/``owner``/
#: ``lease_expires_at``/``fail_reason``/``blocked_by``). HTTP endpoints, error
#: codes, event types, enums and state transitions are unchanged from 1.1.0,
#: which pinned the probe-verified OpenAI-compatible
#: ``LocalOpenAIAgentConfig`` → DeepSeek path.
CONTRACT_VERSION = "1.2.0"
API_PREFIX = "/api/v1"

__all__ = ["SCHEMA_NAMESPACE", "CONTRACT_VERSION", "API_PREFIX"]
