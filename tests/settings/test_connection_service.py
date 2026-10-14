"""Connection/SETTINGS policy, credentials, conflicts and pinning (docs/07)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.contracts import AppError
from lightgravity.settings import (
    ConnectionReferenceInvalid,
    ConnectionService,
    FileSecretStore,
    SettingsConfigInvalid,
)
from lightgravity.store import FileStore, RevisionConflict

from settings_helpers import ToggleFailStore, make_service_with_env


def _create_default(service: ConnectionService, connection_id: str = "deepseek") -> dict:
    return service.create_connection(
        connection_id,
        credential_ref="deepseek-default",
        actor="test",
        request_id=f"req-{connection_id}",
    )


def test_create_fills_first_version_defaults(service: ConnectionService) -> None:
    result = _create_default(service)
    assert result["backend"] == "openai-compat"
    assert result["model"] == "deepseek-v4-flash"
    assert result["base_url"] == "https://api.deepseek.com/v1"
    assert result["enabled"] is True
    assert result["credential"]["configured"] is False
    assert "credential_value" not in result


def test_unverified_backend_rejected(service: ConnectionService) -> None:
    with pytest.raises(SettingsConfigInvalid):
        service.create_connection(
            "gemini",
            backend="gemini",
            model="gemini-2.0",
            base_url="https://example.invalid",
            actor="test",
            request_id="req-gemini",
        )
    assert service.list_connections() == []


def test_repository_backend_requirements(service: ConnectionService) -> None:
    repository = service.repository
    with pytest.raises(SettingsConfigInvalid):
        repository.validate_backend("openai-compat", model="m", base_url=None)
    with pytest.raises(SettingsConfigInvalid):
        repository.validate_backend("openai-compat", model=None, base_url="http://x")


def test_revision_conflict_is_real(service: ConnectionService) -> None:
    created = _create_default(service)
    updated = service.update_connection(
        "deepseek", expected_revision=created["revision"], actor="test", title="renamed"
    )
    assert updated["revision"] == created["revision"] + 1
    assert updated["title"] == "renamed"
    with pytest.raises(RevisionConflict):
        service.update_connection(
            "deepseek", expected_revision=created["revision"], actor="test", title="stale"
        )


def test_default_reference_legality(service: ConnectionService) -> None:
    with pytest.raises(ConnectionReferenceInvalid):
        service.update_settings(
            expected_revision=None, actor="test", default_worker_connection_ref="missing"
        )
    created = _create_default(service)
    settings = service.update_settings(
        expected_revision=None, actor="test", default_worker_connection_ref="deepseek"
    )
    assert settings["default_worker_connection_ref"] == "deepseek"
    assert settings["defaults"]["worker"]["resolved"] is True
    assert settings["revision"] == 0

    # A disabled connection may not be a default: disabling requires clearing.
    with pytest.raises(ConnectionReferenceInvalid):
        service.update_connection(
            "deepseek",
            expected_revision=created["revision"],
            actor="test",
            enabled=False,
        )
    cleared = service.update_connection(
        "deepseek",
        expected_revision=created["revision"],
        actor="test",
        enabled=False,
        clear_defaults=True,
    )
    assert cleared["enabled"] is False
    assert service.get_settings()["default_worker_connection_ref"] is None

    # Re-enabling and setting the default again works.
    service.update_connection(
        "deepseek", expected_revision=cleared["revision"], actor="test", enabled=True
    )
    settings_rev = service.get_settings()["revision"]
    service.update_settings(
        expected_revision=settings_rev,
        actor="test",
        default_worker_connection_ref="deepseek",
    )
    assert service.get_settings()["defaults"]["worker"]["resolved"] is True


def test_credential_lifecycle_and_reference_blocking(service: ConnectionService) -> None:
    created = service.create_connection(
        "deepseek",
        credential_ref="deepseek-default",
        credential_value="sk-initial",
        actor="test",
        request_id="req-cred",
    )
    status = service.credential_status("deepseek-default")
    assert status.configured is True
    assert status.source == "secret_store"
    first_version = status.version
    assert first_version is not None

    # keep semantics: no value / empty value never deletes
    kept = service.update_connection(
        "deepseek", expected_revision=created["revision"], actor="test", title="still-here"
    )
    assert service.credential_status("deepseek-default").version == first_version
    assert kept["credential"]["configured"] is True
    service.update_connection(
        "deepseek",
        expected_revision=kept["revision"],
        actor="test",
        credential_action="keep",
        credential_value="",
    )
    assert service.credential_status("deepseek-default").version == first_version

    # removing the credential while referenced is blocked
    with pytest.raises(ConnectionReferenceInvalid):
        service.remove_credential("deepseek-default")

    # removing the reference, then the secret
    current = service.get_connection("deepseek")
    service.update_connection(
        "deepseek",
        expected_revision=current["revision"],
        actor="test",
        credential_action="remove",
    )
    assert service.get_connection("deepseek")["credential_ref"] is None
    removed = service.remove_credential("deepseek-default")
    assert removed.configured is False


def test_set_credential_requires_non_empty(service: ConnectionService) -> None:
    with pytest.raises(SettingsConfigInvalid):
        service.create_connection(
            "deepseek",
            credential_ref="ref",
            credential_value="  ",
            actor="test",
            request_id="req-empty",
        )


def test_environment_credential_is_reported_without_value(
    store: FileStore, secret_store: FileSecretStore
) -> None:
    service = make_service_with_env(store, secret_store, {"ENV_REF": "env-secret-value"})
    created = service.create_connection(
        "deepseek",
        credential_ref="env-ref",
        actor="test",
        request_id="req-env",
    )
    status = service.credential_status("env-ref")
    assert status.configured is True
    assert status.source == "environment"
    assert status.version is None
    public = service.get_connection("deepseek")
    assert "env-secret-value" not in str(public)
    # Removing an environment-provided credential cannot delete the env var; once
    # it is unreferenced the store delete is a no-op and it stays configured.
    service.update_connection(
        "deepseek",
        expected_revision=created["revision"],
        actor="test",
        credential_action="remove",
    )
    result = service.remove_credential("env-ref")
    assert result.configured is True
    assert result.source == "environment"


def test_pinning_is_stable_across_default_and_connection_edits(
    service: ConnectionService,
) -> None:
    created = _create_default(service)
    service.update_settings(
        expected_revision=None, actor="test", default_worker_connection_ref="deepseek"
    )
    service.create_connection(
        "secondary",
        credential_ref="secondary-ref",
        actor="test",
        request_id="req-secondary",
    )
    pinned = service.resolve_default("worker")
    assert pinned is not None
    assert pinned.connection_id == "deepseek"
    assert service.pinned_is_current(pinned) is True

    # Changing the default does not mutate an already pinned connection.
    service.update_settings(
        expected_revision=service.get_settings()["revision"],
        actor="test",
        default_worker_connection_ref="secondary",
    )
    assert pinned.connection_id == "deepseek"
    assert service.pinned_is_current(pinned) is True
    assert service.resolve_default("worker").connection_id == "secondary"  # type: ignore[union-attr]

    # Editing the pinned connection makes the snapshot stale, not auto-swapped.
    service.update_connection(
        "deepseek", expected_revision=created["revision"], actor="test", title="edited"
    )
    assert service.pinned_is_current(pinned) is False


def test_pinning_tracks_credential_version(service: ConnectionService) -> None:
    service.create_connection(
        "deepseek",
        credential_ref="deepseek-default",
        credential_value="sk-one",
        actor="test",
        request_id="req-pin",
    )
    pinned = service.pin_connection("deepseek")
    assert service.pinned_is_current(pinned) is True
    service.set_credential("deepseek-default", "sk-two")
    assert service.pinned_is_current(pinned) is False


def test_cross_file_failure_rolls_back_secret_and_settings(
    store: FileStore, secret_store: FileSecretStore
) -> None:
    service = ConnectionService(store, secret_store=secret_store)
    created = service.create_connection(
        "deepseek",
        credential_ref="deepseek-default",
        credential_value="sk-original",
        actor="test",
        request_id="req-rollback",
    )
    service.update_settings(
        expected_revision=None, actor="test", default_worker_connection_ref="deepseek"
    )

    failing = ToggleFailStore(store)
    failing_service = ConnectionService(failing, secret_store=secret_store)
    failing.fail_kinds = {"connection"}
    with pytest.raises(AppError):
        failing_service.update_connection(
            "deepseek",
            expected_revision=created["revision"],
            actor="test",
            enabled=False,
            clear_defaults=True,
            credential_action="set",
            credential_value="sk-new",
        )

    # settings default restored, secret restored, connection untouched
    assert failing_service.get_settings()["default_worker_connection_ref"] == "deepseek"
    assert secret_store.get("deepseek-default").reveal() == "sk-original"  # type: ignore[union-attr]
    assert failing_service.get_connection("deepseek")["enabled"] is True


def test_settings_public_view_never_contains_secret(service: ConnectionService) -> None:
    service.create_connection(
        "deepseek",
        credential_ref="deepseek-default",
        credential_value="sk-super-secret",
        actor="test",
        request_id="req-secret",
    )
    service.update_settings(
        expected_revision=None, actor="test", default_worker_connection_ref="deepseek"
    )
    rendered = str(service.get_settings()) + str(service.list_connections())
    assert "sk-super-secret" not in rendered
