"""LG-109 draft tests: transient credentials, no writes, budgets and limits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lightgravity.adapter.credentials import Secret
from lightgravity.adapter.proxy import configure_generation_ledger, global_generation_counter
from lightgravity.settings import (
    ConnectionService,
    ConnectionTestLog,
    ConnectionTester,
    DraftConnectionSpec,
    SettingsConfigInvalid,
)
from lightgravity.settings.testing import LAYER_CONFIG_PARSE, LAYER_CREDENTIAL, LAYER_RUNTIME_NETWORK
from lightgravity.store import RevisionConflict

from settings_helpers import FakeProxy


def _native_calls() -> tuple[list[tuple[str, Secret | None]], Any]:
    calls: list[tuple[str, Secret | None]] = []

    def runner(spec, credential, endpoint, timeout):  # type: ignore[no-untyped-def]
        calls.append((spec.backend, credential))
        return True, "fake native probe stop_confirmed=True"

    return calls, runner


def _configure(data_dir: Path, *, limit: int | None = None) -> None:
    configure_generation_ledger(data_dir, limit=limit)


def test_new_draft_network_uses_transient_secret_and_writes_nothing(
    service: ConnectionService,
    secret_store: Any,
    data_dir: Path,
    tmp_path: Path,
) -> None:
    _configure(data_dir)
    calls, runner = _native_calls()
    log = ConnectionTestLog(tmp_path / "diagnostics")
    tester = ConnectionTester(
        service,
        diagnostics=log,
        allow_network=True,
        native_runner=runner,
        allow_loopback_native=True,
        native_base_url="http://127.0.0.1:9",
    )
    result = tester.test_draft(
        DraftConnectionSpec(
            backend="gemini",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        credential_value="sk-draft-secret",
        allow_network=True,
    )
    assert result.draft is True
    assert result.connection_id is None
    assert result.connection_revision is None
    assert result.overall == "verified"
    assert result.layer(LAYER_RUNTIME_NETWORK).status == "passed"  # type: ignore[union-attr]
    assert calls and calls[0][0] == "gemini"
    assert calls[0][1] is not None
    assert calls[0][1].reveal() == "sk-draft-secret"  # type: ignore[union-attr]
    assert "sk-draft-secret" not in json.dumps(result.to_dict())

    # Draft must not create a Connection/secret/default/diagnostic.
    assert service.list_connections() == []
    assert secret_store.list_refs() == []
    assert log.history("any") == []
    assert not (data_dir / "settings" / "SETTINGS.md").exists()
    assert not (data_dir / "resources" / "connections").exists()
    assert global_generation_counter().snapshot()["count"] == 1


def test_draft_static_test_runs_without_network_or_secret_side_effect(
    service: ConnectionService, data_dir: Path
) -> None:
    _configure(data_dir)
    calls, runner = _native_calls()
    tester = ConnectionTester(
        service, allow_network=True, native_runner=runner
    )
    result = tester.test_draft(
        DraftConnectionSpec(
            backend="gemini",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        credential_value="sk-draft-secret",
        allow_network=False,
    )
    assert result.layer(LAYER_CONFIG_PARSE).status == "passed"  # type: ignore[union-attr]
    assert result.layer(LAYER_CREDENTIAL).status == "passed"  # type: ignore[union-attr]
    network = result.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "skipped"
    assert calls == []
    assert tester.network_calls == 0
    assert service.list_connections() == []
    assert global_generation_counter().snapshot()["count"] == 0


def test_edit_same_identity_reuses_saved_secret_only_from_memory(
    service: ConnectionService, data_dir: Path
) -> None:
    _configure(data_dir)
    service.create_connection(
        "gemini",
        backend="gemini",
        model="gemini-3.8-flash",
        auth_mode="api_key",
        credential_ref="gemini-key",
        credential_value="sk-saved-secret",
        actor="test",
        request_id="req-gemini",
    )
    calls, runner = _native_calls()
    tester = ConnectionTester(service, allow_network=True, native_runner=runner)
    result = tester.test_draft(
        DraftConnectionSpec(
            backend="gemini",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        existing_connection_id="gemini",
        expected_revision=0,
        allow_network=True,
    )
    assert result.draft is True
    assert result.connection_id == "gemini"
    assert result.connection_revision == 0
    assert result.overall == "verified"
    assert calls[0][1] is not None and calls[0][1].reveal() == "sk-saved-secret"  # type: ignore[union-attr]
    assert "sk-saved-secret" not in json.dumps(result.to_dict())
    # The saved secret and connection stay exactly where they were.
    assert service.secret_store.get("gemini-key").reveal() == "sk-saved-secret"  # type: ignore[union-attr]
    assert service.get_connection("gemini")["revision"] == 0


def test_edit_changed_recipient_requires_fresh_key_and_never_reuses_old(
    service: ConnectionService, data_dir: Path
) -> None:
    _configure(data_dir)
    service.create_connection(
        "gemini",
        backend="gemini",
        model="gemini-3.8-flash",
        auth_mode="api_key",
        credential_ref="gemini-key",
        credential_value="sk-old-secret",
        actor="test",
        request_id="req-gemini",
    )
    calls, runner = _native_calls()
    tester = ConnectionTester(service, allow_network=True, native_runner=runner)
    with pytest.raises(SettingsConfigInvalid) as refused:
        tester.test_draft(
            DraftConnectionSpec(
                backend="vertex",
                model="gemini-3.8-flash",
                auth_mode="api_key",
            ),
            existing_connection_id="gemini",
            expected_revision=0,
            allow_network=True,
        )
    assert refused.value.details["diagnostics"][0]["code"] == "credential_recipient_changed"
    assert calls == []

    result = tester.test_draft(
        DraftConnectionSpec(
            backend="vertex",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        credential_value="sk-fresh-secret",
        existing_connection_id="gemini",
        expected_revision=0,
        allow_network=True,
    )
    assert result.overall == "verified"
    assert calls[0][0] == "vertex"
    assert calls[0][1] is not None and calls[0][1].reveal() == "sk-fresh-secret"  # type: ignore[union-attr]
    assert "sk-old-secret" not in json.dumps(result.to_dict())


def test_edit_requires_current_revision_and_reports_conflict(
    service: ConnectionService, data_dir: Path
) -> None:
    _configure(data_dir)
    service.create_connection("gemini", backend="gemini", model="gemini-3.8-flash", actor="test", request_id="req")
    _calls, runner = _native_calls()
    tester = ConnectionTester(service, native_runner=runner)
    with pytest.raises(SettingsConfigInvalid):
        tester.test_draft(
            DraftConnectionSpec(backend="gemini", model="gemini-3.8-flash"),
            existing_connection_id="gemini",
        )
    with pytest.raises(RevisionConflict):
        tester.test_draft(
            DraftConnectionSpec(backend="gemini", model="gemini-3.8-flash"),
            existing_connection_id="gemini",
            expected_revision=9,
        )


def test_global_cap_zero_blocks_native_network_and_corrupt_ledger_fails_closed(
    service: ConnectionService, data_dir: Path
) -> None:
    _configure(data_dir, limit=0)
    calls, runner = _native_calls()
    tester = ConnectionTester(service, allow_network=True, native_runner=runner)
    result = tester.test_draft(
        DraftConnectionSpec(backend="gemini", model="gemini-3.8-flash"),
        credential_value="sk-draft",
        allow_network=True,
    )
    network = result.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "skipped"
    assert "budget exhausted" in network.detail
    assert calls == []
    assert global_generation_counter().snapshot()["count"] == 0

    _configure(data_dir)
    history = data_dir / "generation" / "generation.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text("{not-json}\n", encoding="utf-8")
    calls, runner = _native_calls()
    tester = ConnectionTester(service, allow_network=True, native_runner=runner)
    result = tester.test_draft(
        DraftConnectionSpec(backend="gemini", model="gemini-3.8-flash"),
        credential_value="sk-draft",
        allow_network=True,
    )
    network = result.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "skipped"
    assert "corrupt" in network.detail and "fail closed" in network.detail
    assert calls == []


def test_unlimited_repeated_drafts_each_reserve_and_never_hit_lg108_lifetime_bug(
    service: ConnectionService, data_dir: Path
) -> None:
    _configure(data_dir, limit=None)
    calls, runner = _native_calls()
    tester = ConnectionTester(service, allow_network=True, native_runner=runner)
    for _ in range(2):
        result = tester.test_draft(
            DraftConnectionSpec(backend="gemini", model="gemini-3.8-flash"),
            credential_value="sk-draft",
            allow_network=True,
        )
        assert result.layer(LAYER_RUNTIME_NETWORK).status == "passed"  # type: ignore[union-attr]
    assert len(calls) == 2
    assert tester.network_calls == 2
    assert global_generation_counter().snapshot()["count"] == 2


def test_litert_draft_is_static_only_and_adc_never_requests_metadata(
    service: ConnectionService, data_dir: Path
) -> None:
    _configure(data_dir)
    workspace = Path(service.repository.store.workspace_root)
    workspace.mkdir(parents=True, exist_ok=True)
    model = workspace / "local.litertlm"
    model.write_text("never read by the backend", encoding="utf-8")
    calls, runner = _native_calls()
    tester = ConnectionTester(service, allow_network=True, native_runner=runner)
    litert = tester.test_draft(
        DraftConnectionSpec(
            backend="litert",
            auth_mode="none",
            model_path=str(model),
            litert_backend="GPU",
        ),
        allow_network=True,
    )
    assert litert.layer(LAYER_CONFIG_PARSE).status == "passed"  # type: ignore[union-attr]
    network = litert.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "skipped"
    assert "static-only" in network.detail
    assert calls == []

    adc_tester = ConnectionTester(
        service,
        allow_network=True,
        native_runner=runner,
        adc_available=False,
    )
    adc = adc_tester.test_draft(
        DraftConnectionSpec(
            backend="vertex",
            model="gemini-3.8-flash",
            auth_mode="adc",
            project="demo-project",
            location="us-central1",
        ),
        allow_network=True,
    )
    network = adc.layer(LAYER_RUNTIME_NETWORK)
    assert network is not None and network.status == "skipped"
    assert "no gcloud or metadata request" in network.detail
    assert calls == []

    calls, runner = _native_calls()
    tester = ConnectionTester(
        service,
        allow_network=True,
        native_runner=runner,
        adc_available=True,
    )
    adc_ok = tester.test_draft(
        DraftConnectionSpec(
            backend="vertex",
            model="gemini-3.8-flash",
            auth_mode="adc",
            project="demo-project",
            location="us-central1",
        ),
        allow_network=True,
    )
    assert adc_ok.overall == "verified"
    assert calls and calls[0][0] == "vertex" and calls[0][1] is None


def test_openai_loopback_draft_probe_uses_existing_proxy_without_writes(
    service: ConnectionService, data_dir: Path, tmp_path: Path
) -> None:
    _configure(data_dir)
    created: list[FakeProxy] = []

    def factory(credential: Secret, upstream: str, max_calls: int) -> FakeProxy:
        proxy = FakeProxy(credential, upstream, max_calls)
        created.append(proxy)
        return proxy

    def http_post(url: str, body: bytes, timeout: float) -> tuple[int, dict[str, Any]]:
        return 200, {"choices": [{"message": {"content": "pong"}}], "model": "fake"}

    tester = ConnectionTester(
        service,
        allow_network=True,
        http_post=http_post,
        proxy_factory=factory,
        max_network_calls=1,
    )
    spec = DraftConnectionSpec(
        backend="openai-compat",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        auth_mode="proxy_api_key",
    )
    first = tester.test_draft(spec, credential_value="sk-draft", allow_network=True)
    second = tester.test_draft(spec, credential_value="sk-draft", allow_network=True)
    assert first.overall == "verified" and second.overall == "verified"
    assert tester.network_calls == 2
    assert all(proxy.is_running is False for proxy in created)
    assert service.list_connections() == []
    assert service.secret_store.list_refs() == []
