"""Layered connection testing: separation, binding and staleness (docs/07 §5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lightgravity.settings import (
    ConnectionService,
    ConnectionTestLog,
    ConnectionTester,
)
from lightgravity.settings.testing import (
    LAYER_CAPABILITY,
    LAYER_CONFIG_PARSE,
    LAYER_CREDENTIAL,
    LAYER_RUNTIME_NETWORK,
    LAYER_STRUCTURED_OUTPUT,
    LAYER_TOOL_PROBE,
)

from settings_helpers import FakeProxy


def _make_tester(
    service: ConnectionService,
    http_post: Any,
    *,
    diagnostics: ConnectionTestLog | None = None,
    max_network_calls: int = 1,
) -> tuple[ConnectionTester, list[FakeProxy]]:
    created: list[FakeProxy] = []

    def factory(credential: Any, upstream: str, max_calls: int) -> FakeProxy:
        proxy = FakeProxy(credential, upstream, max_calls)
        created.append(proxy)
        return proxy

    tester = ConnectionTester(
        service,
        diagnostics=diagnostics,
        allow_network=True,
        http_post=http_post,
        proxy_factory=factory,
        max_network_calls=max_network_calls,
    )
    return tester, created


def _connection(service: ConnectionService, *, credential: bool = True) -> dict:
    return service.create_connection(
        "deepseek",
        credential_ref="deepseek-default",
        credential_value="sk-test" if credential else None,
        actor="test",
        request_id="req-test",
    )


def test_network_layer_passes_and_binds_revision_and_credential(
    service: ConnectionService, tmp_path: Path
) -> None:
    _connection(service)
    calls: list[tuple[str, bytes, float]] = []

    def http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        calls.append((url, body, timeout))
        return 200, {"choices": [{"message": {"content": "pong"}}], "model": "deepseek-flash"}

    log = ConnectionTestLog(tmp_path / "diagnostics")
    tester, created = _make_tester(service, http_post, diagnostics=log)
    result = tester.test("deepseek", allow_network=True)

    assert result.overall == "verified"
    assert result.layer(LAYER_CONFIG_PARSE).status == "passed"  # type: ignore[union-attr]
    assert result.layer(LAYER_CREDENTIAL).status == "passed"  # type: ignore[union-attr]
    assert result.layer(LAYER_CAPABILITY).status == "declared"  # type: ignore[union-attr]
    network = result.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "passed"
    assert "stop_confirmed=True" in network.detail
    assert result.connection_revision == 0
    assert result.credential_version == service.credential_status("deepseek-default").version
    assert tester.network_calls == 1
    assert len(created) == 1 and created[0].is_running is False
    assert len(calls) == 1

    # Old test is stale after the connection or credential changes.
    assert result.is_stale(0, result.credential_version) is False
    assert result.is_stale(1, result.credential_version) is True
    assert result.is_stale(0, "cred_other") is True

    stored = log.latest("deepseek")
    assert stored is not None and stored["test_id"] == result.test_id


def test_network_layer_failure_is_not_hidden(service: ConnectionService) -> None:
    _connection(service)

    def http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        return 401, {}

    tester, created = _make_tester(service, http_post)
    result = tester.test("deepseek", allow_network=True)
    assert result.overall == "failed"
    network = result.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "failed"
    assert "401" in network.detail
    # capability remains only a declaration even when the network fails
    capability = result.layer(LAYER_CAPABILITY)
    assert capability is not None and capability.status == "declared"
    assert len(created) == 1 and created[0].is_running is False


def test_network_skipped_without_opt_in(service: ConnectionService) -> None:
    _connection(service)

    def http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        raise AssertionError("network must not be used")

    tester, _ = _make_tester(service, http_post)
    result = tester.test("deepseek", allow_network=False)
    assert result.overall == "not_run"
    network = result.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "skipped"
    assert tester.network_calls == 0


def test_missing_credential_fails_before_network(service: ConnectionService) -> None:
    _connection(service, credential=False)

    def http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        raise AssertionError("network must not be attempted without a credential")

    tester, _ = _make_tester(service, http_post)
    result = tester.test("deepseek", allow_network=True)
    assert result.overall == "failed"
    credential = result.layer(LAYER_CREDENTIAL)
    assert credential is not None and credential.status == "failed"
    network = result.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "failed"


def test_optional_probe_layers_are_separate_and_skipped(service: ConnectionService) -> None:
    _connection(service)

    def http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        return 200, {"choices": [{"message": {"content": "ok"}}], "model": "deepseek-flash"}

    tester, _ = _make_tester(service, http_post)
    result = tester.test(
        "deepseek", allow_network=True, probe_tools=True, probe_structured=True
    )
    tools = result.layer(LAYER_TOOL_PROBE)
    structured = result.layer(LAYER_STRUCTURED_OUTPUT)
    assert tools is not None and tools.status == "skipped"
    assert structured is not None and structured.status == "skipped"


def test_network_budget_is_bounded(service: ConnectionService) -> None:
    _connection(service)

    def http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        return 200, {"choices": [{"message": {"content": "ok"}}], "model": "deepseek-flash"}

    tester, _ = _make_tester(service, http_post, max_network_calls=1)
    first = tester.test("deepseek", allow_network=True)
    second = tester.test("deepseek", allow_network=True)
    assert first.layer(LAYER_RUNTIME_NETWORK).status == "passed"  # type: ignore[union-attr]
    assert second.layer(LAYER_RUNTIME_NETWORK).status == "skipped"  # type: ignore[union-attr]
    assert tester.network_calls == 1
