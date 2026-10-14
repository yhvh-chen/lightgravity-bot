"""Credential resolution stays in memory and is never rendered as plaintext."""

from __future__ import annotations

from lightgravity.adapter import (
    EnvCredentialResolver,
    InMemoryCredentialResolver,
    Secret,
    default_env_var_name,
    mask_values,
)


def test_default_env_var_name_normalizes_slug() -> None:
    assert default_env_var_name("deepseek-api-key") == "DEEPSEEK_API_KEY"
    assert default_env_var_name("DEEPSEEK_API_KEY") == "DEEPSEEK_API_KEY"


def test_env_resolver_prefers_mapping_then_ref_then_normalized() -> None:
    env = {"MY_KEY": "mapped", "deepseek-api-key": "verbatim", "DEEPSEEK_API_KEY": "norm"}
    resolver = EnvCredentialResolver(env, mapping={"deepseek": "MY_KEY"})
    assert resolver.resolve("deepseek").reveal() == "mapped"  # type: ignore[union-attr]
    assert resolver.resolve("deepseek-api-key").reveal() == "verbatim"  # type: ignore[union-attr]
    assert resolver.resolve("deep") is None
    assert resolver.resolve("Deepseek.Api.Key").reveal() == "norm"  # type: ignore[union-attr]


def test_env_resolver_absent_or_blank_is_none() -> None:
    resolver = EnvCredentialResolver({"EMPTY": "   "})
    assert resolver.resolve("missing") is None
    assert resolver.resolve("empty") is None
    assert resolver.resolve("") is None


def test_in_memory_resolver() -> None:
    resolver = InMemoryCredentialResolver({"ref": "value"})
    assert resolver.resolve("ref").reveal() == "value"  # type: ignore[union-attr]
    assert resolver.resolve("other") is None


def test_secret_never_renders_value() -> None:
    secret = Secret("sk-super-secret-value")
    assert secret.reveal() == "sk-super-secret-value"
    assert "sk-super-secret-value" not in repr(secret)
    assert "sk-super-secret-value" not in str(secret)
    assert "redacted" in repr(secret)


def test_mask_values_replaces_secret_anywhere() -> None:
    payload = {"message": "token sk-live-123 leaked", "nested": ["sk-live-123"]}
    masked = mask_values(payload, ["sk-live-123"])
    assert "sk-live-123" not in str(masked)
    assert masked["message"].startswith("token <redacted>")
    assert masked["nested"] == ["<redacted>"]
