"""Registry boundary and capability declaration (docs/08 §8)."""

from __future__ import annotations

from lightgravity.adapter import (
    HookRegistration,
    SDK_PINNED_VERSION,
    adapter_capabilities,
    default_registry,
    installed_sdk_version,
    sdk_available,
)


def test_default_registry_maps_builtin_handlers() -> None:
    registry = default_registry()
    view = registry.tool("view-file")
    assert view is not None
    assert view.sdk_tool == "view_file"
    assert view.permission == "file.read"
    assert registry.tool("does-not-exist") is None


def test_unattachable_handlers_are_marked() -> None:
    registry = default_registry()
    for handler in ("search-web", "invoke-subagent", "run-workflow", "schedule"):
        registration = registry.tool(handler)
        assert registration is not None, handler
        assert registration.attaches is False, handler


def test_connection_backends_and_verification() -> None:
    registry = default_registry()
    gemini = registry.backend("gemini")
    openai = registry.backend("openai-compat")
    assert gemini is not None and gemini.verified is False
    assert openai is not None and openai.verified is True
    assert openai.supports_api_key_field is False
    assert registry.backend("nope") is None


def test_registry_accepts_explicit_hook_registration() -> None:
    registry = default_registry(
        hooks=[HookRegistration(handler_id="custom", factory=lambda: object())]
    )
    assert registry.hook("custom") is not None
    assert registry.hook("unregistered") is None


def test_capability_snapshot_is_conservative() -> None:
    caps = adapter_capabilities()
    assert caps.sdk_version == SDK_PINNED_VERSION == "0.1.22"
    assert caps.compile is True
    assert caps.subagents is False
    assert caps.mcp is False
    assert caps.triggers is False
    assert caps.search_web is False
    assert "gemini" in caps.unverified_backends
    assert "vertex" in caps.unverified_backends
    assert "openai_compat" in caps.probe_verified_backends
    payload = caps.to_dict()
    assert payload["sdk_version"] == "0.1.22"
    assert payload["mcp"] is False


def test_installed_sdk_is_detected() -> None:
    # The pinned SDK is a root dependency of this package.
    assert sdk_available() is True
    assert installed_sdk_version() == SDK_PINNED_VERSION
