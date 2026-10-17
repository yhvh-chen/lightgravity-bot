"""LG-104/LG-109 provider matrix and capability facts (static, no network)."""

from __future__ import annotations

from pathlib import Path

from lightgravity.adapter import (
    ResourceCompiler,
    build_sdk_config,
    default_registry,
)
from lightgravity.adapter.provider_matrix import (
    auth_requires_credential,
    credential_recipient_identity,
    effective_auth_mode,
    validate_provider_fields,
)
from lightgravity.store import FileStore

from helpers import build_agent, build_basic_environment


def _codes(diagnostics: list[dict]) -> set[str]:
    return {str(item.get("code")) for item in diagnostics}


def test_registry_separates_configurable_testable_executable_vendor_facts() -> None:
    registry = default_registry()

    gemini = registry.backend("gemini")
    vertex = registry.backend("vertex")
    litert = registry.backend("litert")
    deepseek = registry.backend("openai-compat")

    assert gemini is not None and vertex is not None
    assert litert is not None and deepseek is not None
    for backend in (gemini, vertex, litert):
        assert backend.configurable is True
        assert backend.testable is True
        assert backend.executable is False
        assert backend.vendor_verified is False
        assert backend.verified is False
    assert deepseek.configurable is True
    assert deepseek.testable is True
    assert deepseek.executable is True
    assert deepseek.vendor_verified is True


def test_old_connections_infer_auth_without_rewriting() -> None:
    assert effective_auth_mode("gemini", None) == "api_key"
    assert effective_auth_mode("vertex", None, project="p", location="us") == "adc"
    assert effective_auth_mode("vertex", None, credential_ref="vertex-key") == "api_key"
    assert effective_auth_mode("openai-compat", None) == "proxy_api_key"
    assert effective_auth_mode("litert", None) == "none"
    assert auth_requires_credential("gemini", "api_key") is True
    assert auth_requires_credential("vertex", "adc") is False
    assert auth_requires_credential("litert", "none") is False


def test_provider_matrix_accepts_each_supported_shape() -> None:
    shapes = [
        dict(
            backend="gemini",
            auth_mode="api_key",
            model="gemini-3.8-flash",
            base_url=None,
            project=None,
            location=None,
            model_path=None,
            litert_backend=None,
        ),
        dict(
            backend="vertex",
            auth_mode="api_key",
            model="gemini-3.8-flash",
            base_url=None,
            project=None,
            location=None,
            model_path=None,
            litert_backend=None,
        ),
        dict(
            backend="vertex",
            auth_mode="adc",
            model="gemini-3.8-flash",
            base_url=None,
            project="project",
            location="us-central1",
            model_path=None,
            litert_backend=None,
        ),
        dict(
            backend="openai-compat",
            auth_mode="proxy_api_key",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            project=None,
            location=None,
            model_path=None,
            litert_backend=None,
        ),
        dict(
            backend="litert",
            auth_mode="none",
            model=None,
            base_url=None,
            project=None,
            location=None,
            model_path="models/local.litertlm",
            litert_backend=None,
        ),
    ]
    for shape in shapes:
        _, diagnostics = validate_provider_fields(**shape)
        assert diagnostics == [], (shape, diagnostics)


def test_provider_matrix_rejects_illegal_combinations_without_secret_values() -> None:
    cases = [
        (
            dict(
                backend="gemini",
                auth_mode="api_key",
                model=None,
                base_url=None,
                project=None,
                location=None,
                model_path=None,
                litert_backend=None,
            ),
            "model_missing",
        ),
        (
            dict(
                backend="gemini",
                auth_mode="api_key",
                model="m",
                base_url="https://example.invalid/v1",
                project=None,
                location=None,
                model_path=None,
                litert_backend=None,
            ),
            "field_not_supported",
        ),
        (
            dict(
                backend="vertex",
                auth_mode="api_key",
                model="m",
                base_url=None,
                project="p",
                location=None,
                model_path=None,
                litert_backend=None,
            ),
            "field_not_supported",
        ),
        (
            dict(
                backend="vertex",
                auth_mode="adc",
                model="m",
                base_url=None,
                project=None,
                location=None,
                model_path=None,
                litert_backend=None,
            ),
            "project_missing",
        ),
        (
            dict(
                backend="openai-compat",
                auth_mode="proxy_api_key",
                model="m",
                base_url=None,
                project=None,
                location=None,
                model_path=None,
                litert_backend=None,
            ),
            "endpoint_missing",
        ),
        (
            dict(
                backend="litert",
                auth_mode="none",
                model=None,
                base_url=None,
                project=None,
                location=None,
                model_path=None,
                litert_backend=None,
            ),
            "model_path_missing",
        ),
        (
            dict(
                backend="litert",
                auth_mode="none",
                model=None,
                base_url=None,
                project=None,
                location=None,
                model_path="m.litertlm",
                litert_backend="TPU",
            ),
            "litert_backend_invalid",
        ),
    ]
    for shape, expected in cases:
        _, diagnostics = validate_provider_fields(**shape)
        assert expected in _codes(diagnostics), (shape, diagnostics)
        assert "sk-super-secret" not in str(diagnostics)


def test_credential_recipient_identity_is_provider_auth_endpoint_origin() -> None:
    deepseek_a = credential_recipient_identity(
        backend="openai-compat",
        auth_mode="proxy_api_key",
        base_url="https://api.deepseek.com/v1",
        project=None,
        location=None,
    )
    deepseek_same_origin = credential_recipient_identity(
        backend="openai-compat",
        auth_mode="proxy_api_key",
        base_url="https://API.DEEPSEEK.COM:443/another-path",
        project=None,
        location=None,
    )
    other_host = credential_recipient_identity(
        backend="openai-compat",
        auth_mode="proxy_api_key",
        base_url="https://evil.example/v1",
        project=None,
        location=None,
    )
    assert deepseek_a == deepseek_same_origin
    assert deepseek_a != other_host
    assert credential_recipient_identity(
        backend="gemini",
        auth_mode="api_key",
        base_url=None,
        project=None,
        location=None,
    ) != credential_recipient_identity(
        backend="vertex",
        auth_mode="api_key",
        base_url=None,
        project=None,
        location=None,
    )


def test_new_provider_configs_compile_static_but_do_not_execute(
    store: FileStore,
    compiler: ResourceCompiler,
) -> None:
    build_basic_environment(
        store,
        backend="gemini",
        base_url=None,
        credential_ref="gemini-key",
    )
    build_agent(store)
    compiled = compiler.compile_agent("developer")
    assert compiled.executable is False
    assert "backend_unverified" in compiled.executable_reasons
    assert compiled.connection is not None
    assert compiled.connection.auth_mode is None  # old file, inferred not rewritten
    assert compiled.connection.executable is False
    assert compiled.connection.vendor_verified is False
    result = build_sdk_config(compiled)
    from google.antigravity import LocalAgentConfig

    assert isinstance(result.config, LocalAgentConfig)
    assert result.config.api_key is None


def test_litert_compiles_static_config_without_inference(
    store: FileStore,
    compiler: ResourceCompiler,
) -> None:
    build_basic_environment(
        store,
        backend="litert",
        base_url=None,
        credential_ref=None,
    )
    model_path = Path(store.workspace_root) / "models" / "local.litertlm"
    store.write(
        "connection",
        "primary",
        {
            "backend": "litert",
            "model": None,
            "model_path": str(model_path),
            "litert_backend": "CPU",
            "auth_mode": "none",
            "credential_ref": None,
        },
        expected_revision=0,
        actor="test",
    )
    build_agent(store)
    compiled = compiler.compile_agent("developer")
    assert compiled.executable is False
    assert compiled.connection is not None
    assert compiled.connection.model_path == str(model_path)
    result = build_sdk_config(compiled)
    from google.antigravity import LiteRTAgentConfig

    assert isinstance(result.config, LiteRTAgentConfig)
    assert result.config.model_path == str(model_path)
    assert result.config.backend.value == "cpu"
