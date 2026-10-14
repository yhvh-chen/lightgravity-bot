"""Secret detection and redaction helpers (docs/08 §9, §10)."""

from __future__ import annotations

import pytest

from lightgravity.adapter import REDACTED, is_sensitive_key, redact, sensitive_paths


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "apiKey",
        "access_token",
        "authorization",
        "bearer",
        "client_secret",
        "password",
        "private_key",
        "token",
    ],
)
def test_sensitive_keys_detected(key: str) -> None:
    assert is_sensitive_key(key) is True


@pytest.mark.parametrize(
    "key",
    ["credential_ref", "model", "base_url", "max_output_tokens", "compaction_threshold"],
)
def test_non_sensitive_keys_ignored(key: str) -> None:
    assert is_sensitive_key(key) is False


def test_redact_masks_nested_values_only() -> None:
    payload = {
        "connection": {"backend": "gemini", "api_key": "sk-live-123", "model": "m"},
        "budget": {"max_output_tokens": 512},
    }
    result = redact(payload)
    assert result["connection"]["api_key"] == REDACTED
    assert result["connection"]["backend"] == "gemini"
    assert result["budget"]["max_output_tokens"] == 512


def test_sensitive_paths_reports_locations() -> None:
    payload = {"a": {"github_token": "x"}, "list": [{"password": "y"}]}
    paths = sensitive_paths(payload)
    assert "a.github_token" in paths
    assert "list[0].password" in paths
