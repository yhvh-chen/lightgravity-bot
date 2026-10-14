"""Frozen contract constants (docs/08-interface-contract.md §2, §4)."""

from __future__ import annotations

SCHEMA_NAMESPACE = "lightgravity.bot/v1"
#: docs/08 §13: 1.1.0 (2026-10-15) pins the first-version real backend to the
#: probe-verified OpenAI-compatible ``LocalOpenAIAgentConfig`` → DeepSeek path.
#: HTTP endpoints, error codes, event types, entity fields, enums and state
#: transitions are unchanged from 1.0.0.
CONTRACT_VERSION = "1.1.0"
API_PREFIX = "/api/v1"

__all__ = ["SCHEMA_NAMESPACE", "CONTRACT_VERSION", "API_PREFIX"]
