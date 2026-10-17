"""Installed-SDK auth construction for Gemini/Vertex/LiteRT (static, no network)."""

from __future__ import annotations

from lightgravity.adapter import (
    ConnectionSdkSpec,
    Secret,
    build_connection_sdk_config,
)


def test_gemini_api_key_config_uses_real_sdk_class_and_key_only_in_memory() -> None:
    from google.antigravity import LocalAgentConfig

    secret = "sk-dummy-not-real"
    config = build_connection_sdk_config(
        ConnectionSdkSpec(
            backend="gemini",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        credential=Secret(secret),
    )
    assert isinstance(config, LocalAgentConfig)
    assert config.api_key == secret
    assert config.vertex is None
    assert config.project is None and config.location is None
    assert repr(Secret(secret)) == "Secret(<redacted>)"


def test_vertex_express_and_adc_build_distinct_real_sdk_auth_shapes() -> None:
    from google.antigravity import LocalAgentConfig

    express = build_connection_sdk_config(
        ConnectionSdkSpec(
            backend="vertex",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        credential="sk-dummy-not-real",
    )
    assert isinstance(express, LocalAgentConfig)
    assert express.vertex is True
    assert express.api_key == "sk-dummy-not-real"
    assert express.project is None and express.location is None

    adc = build_connection_sdk_config(
        ConnectionSdkSpec(
            backend="vertex",
            model="gemini-3.8-flash",
            auth_mode="adc",
            project="demo-project",
            location="us-central1",
        )
    )
    assert isinstance(adc, LocalAgentConfig)
    assert adc.vertex is True
    assert adc.api_key is None
    assert adc.project == "demo-project"
    assert adc.location == "us-central1"


def test_litert_config_is_static_and_never_downloads() -> None:
    from google.antigravity import LiteRTAgentConfig

    config = build_connection_sdk_config(
        ConnectionSdkSpec(
            backend="litert",
            model=None,
            auth_mode="none",
            model_path="/workspace/models/local.litertlm",
            litert_backend="NPU",
        )
    )
    assert isinstance(config, LiteRTAgentConfig)
    assert config.model_path == "/workspace/models/local.litertlm"
    assert config.backend.value == "npu"
    assert config.download_if_missing is False


def test_openai_compatible_config_stays_unchanged() -> None:
    from google.antigravity import LocalOpenAIAgentConfig

    config = build_connection_sdk_config(
        ConnectionSdkSpec(
            backend="openai-compat",
            model="deepseek-v4-flash",
            auth_mode="proxy_api_key",
            base_url="https://api.deepseek.com/v1",
        )
    )
    assert isinstance(config, LocalOpenAIAgentConfig)
    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.model == "deepseek-v4-flash"


def test_loopback_endpoint_override_is_only_for_explicit_sdk_probes() -> None:
    config = build_connection_sdk_config(
        ConnectionSdkSpec(
            backend="gemini",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        credential=Secret("sk-dummy-not-real"),
        endpoint_base_url="http://127.0.0.1:9",
    )
    target = config.models[0]
    assert target.endpoint.base_url == "http://127.0.0.1:9"
    assert target.endpoint.api_key == "sk-dummy-not-real"
