"""LG-104 provider fields, storage, compatibility and capability policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.settings import (
    ConnectionReferenceInvalid,
    ConnectionService,
    FileSecretStore,
    SettingsConfigInvalid,
)
from lightgravity.store import FileStore, RevisionConflict


def _create(service: ConnectionService, connection_id: str, **fields) -> dict:
    return service.create_connection(
        connection_id,
        actor="test",
        request_id=f"req-{connection_id}",
        **fields,
    )


def test_new_provider_shapes_are_saved_and_serialized_without_secret(
    service: ConnectionService,
) -> None:
    gemini = _create(
        service,
        "gemini-api",
        backend="gemini",
        model="gemini-3.8-flash",
        auth_mode="api_key",
        credential_ref="gemini-key",
        credential_value="sk-gemini-secret",
    )
    assert gemini["auth_mode"] == "api_key"
    assert gemini["capabilities"] == {
        "configurable": True,
        "testable": True,
        "executable": False,
        "vendor_verified": False,
    }
    assert "sk-gemini-secret" not in str(gemini)

    vertex_express = _create(
        service,
        "vertex-express",
        backend="vertex",
        model="gemini-3.8-flash",
        auth_mode="api_key",
        credential_ref="vertex-key",
        credential_value="sk-vertex-secret",
    )
    assert vertex_express["project"] is None
    assert vertex_express["location"] is None

    vertex_adc = _create(
        service,
        "vertex-adc",
        backend="vertex",
        model="gemini-3.8-flash",
        auth_mode="adc",
        project="demo-project",
        location="us-central1",
    )
    assert vertex_adc["credential_ref"] is None
    assert vertex_adc["credential"]["configured"] is False
    assert vertex_adc["project"] == "demo-project"
    assert vertex_adc["location"] == "us-central1"

    workspace = Path(service.repository.store.workspace_root)
    workspace.mkdir(parents=True, exist_ok=True)
    model = workspace / "local.litertlm"
    model.write_text("not a real model; the backend must never read this", encoding="utf-8")
    litert = _create(
        service,
        "litert-local",
        backend="litert",
        model=None,
        auth_mode="none",
        model_path=str(model),
    )
    assert litert["litert_backend"] is None
    assert litert["model_path"] == str(model)
    assert "not a real model" not in str(litert)

    openai = _create(service, "deepseek", credential_ref="deepseek-key")
    assert openai["backend"] == "openai-compat"
    assert openai["capabilities"]["executable"] is True
    assert openai["capabilities"]["vendor_verified"] is True


def test_illegal_provider_combinations_are_rejected(service: ConnectionService) -> None:
    with pytest.raises(SettingsConfigInvalid):
        _create(
            service,
            "vertex-mixed",
            backend="vertex",
            model="gemini-3.8-flash",
            auth_mode="api_key",
            project="p",
            location="us-central1",
        )
    with pytest.raises(SettingsConfigInvalid):
        _create(
            service,
            "litert-missing-path",
            backend="litert",
            auth_mode="none",
        )
    with pytest.raises(SettingsConfigInvalid):
        _create(
            service,
            "litert-bad-backend",
            backend="litert",
            auth_mode="none",
            model_path="local.litertlm",
            litert_backend="TPU",
        )
    with pytest.raises(SettingsConfigInvalid):
        _create(
            service,
            "gemini-endpoint",
            backend="gemini",
            model="gemini-3.8-flash",
            auth_mode="api_key",
            base_url="https://evil.example/v1",
        )
    assert service.list_connections() == []


def test_litert_model_path_is_confined_to_allowed_roots(
    service: ConnectionService, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    model = outside / "model.litertlm"
    model.write_text("content", encoding="utf-8")
    with pytest.raises(SettingsConfigInvalid) as rejected:
        _create(
            service,
            "litert-outside",
            backend="litert",
            auth_mode="none",
            model_path=str(model),
        )
    assert rejected.value.details["diagnostics"][0]["code"] == "model_path_outside_roots"


def test_old_connection_unknown_fields_defaults_and_body_are_preserved(
    store: FileStore, secret_store: FileSecretStore
) -> None:
    store.create(
        "connection",
        "legacy",
        {
            "title": "Legacy DeepSeek",
            "enabled": True,
            "backend": "openai-compat",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com/v1",
            "credential_ref": "legacy-key",
            "unknown_extension": {"keep": [1, 2, 3]},
        },
        body="# Legacy notes\n\nDo not rewrite this body.\n",
        actor="test",
        request_id="legacy-create",
    )
    service = ConnectionService(store, secret_store=secret_store)
    before = service.get_connection("legacy")
    assert before["auth_mode"] is None
    assert before["project"] is None

    updated = service.update_connection(
        "legacy", expected_revision=0, actor="test", title="Renamed"
    )
    assert updated["revision"] == 1
    assert updated["credential_ref"] == "legacy-key"
    assert updated["backend"] == "openai-compat"
    assert updated["model"] == "deepseek-v4-flash"

    versioned = store.read("connection", "legacy")
    assert versioned.entity["unknown_extension"] == {"keep": [1, 2, 3]}
    assert "Do not rewrite this body." in versioned.body
    # Old files are not migrated with the new optional keys on an unrelated edit.
    assert "auth_mode" not in versioned.entity


def test_explicit_null_clears_fields_while_omitted_fields_preserve(
    service: ConnectionService,
) -> None:
    _create(
        service,
        "vertex-adc",
        backend="vertex",
        model="gemini-3.8-flash",
        auth_mode="adc",
        project="old-project",
        location="us-central1",
        credential_ref="old-key-legacy",
    )
    switched = service.update_connection(
        "vertex-adc",
        expected_revision=0,
        actor="test",
        backend="vertex",
        auth_mode="api_key",
        project=None,
        location=None,
        credential_action="set",
        credential_value="sk-new-express",
    )
    assert switched["auth_mode"] == "api_key"
    assert switched["project"] is None
    assert switched["location"] is None
    assert switched["model"] == "gemini-3.8-flash"  # omitted -> preserved
    assert switched["base_url"] is None
    assert switched["credential"]["configured"] is True

    # Explicit null on a model_path clears it for LiteRT; omitted fields stay.
    workspace = Path(service.repository.store.workspace_root)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "x.litertlm").write_text("x", encoding="utf-8")
    _create(
        service,
        "litert",
        backend="litert",
        auth_mode="none",
        model_path=str(workspace / "x.litertlm"),
        litert_backend="CPU",
    )
    cleared = service.update_connection(
        "litert",
        expected_revision=0,
        actor="test",
        litert_backend=None,
    )
    assert cleared["litert_backend"] is None
    assert cleared["model_path"] == str(workspace / "x.litertlm")


def test_provider_change_does_not_reuse_or_delete_the_old_secret(
    service: ConnectionService,
) -> None:
    _create(
        service,
        "deepseek",
        credential_ref="deepseek-key",
        credential_value="sk-old-deepseek",
    )
    changed = service.update_connection(
        "deepseek",
        expected_revision=0,
        actor="test",
        backend="gemini",
        auth_mode="api_key",
        model="gemini-3.8-flash",
        base_url=None,
        credential_action="keep",
    )
    # The old secret file remains, but the connection no longer references it:
    # no later test/execution can send it to the new provider.
    assert changed["credential_ref"] is None
    assert changed["credential"]["configured"] is False
    assert service.secret_store.get("deepseek-key") is not None

    with_new_key = service.update_connection(
        "deepseek",
        expected_revision=changed["revision"],
        actor="test",
        credential_action="set",
        credential_value="sk-new-gemini",
        credential_ref="gemini-key",
    )
    assert with_new_key["credential_ref"] == "gemini-key"
    assert with_new_key["credential"]["configured"] is True
    assert service.secret_store.get("deepseek-key").reveal() == "sk-old-deepseek"  # type: ignore[union-attr]


def test_revision_conflict_and_default_executable_policy(service: ConnectionService) -> None:
    _create(service, "deepseek")
    with pytest.raises(RevisionConflict):
        service.update_connection(
            "deepseek", expected_revision=1, actor="test", title="stale"
        )

    gemini = _create(
        service,
        "gemini",
        backend="gemini",
        model="gemini-3.8-flash",
        auth_mode="api_key",
        credential_ref="gemini-key",
    )
    for ref in ("gemini",):
        with pytest.raises(ConnectionReferenceInvalid):
            service.update_settings(
                expected_revision=None,
                actor="test",
                default_worker_connection_ref=ref,
            )
    assert gemini["capabilities"]["executable"] is False

    settings = service.update_settings(
        expected_revision=None,
        actor="test",
        default_worker_connection_ref="deepseek",
    )
    assert settings["defaults"]["worker"]["resolved"] is True
