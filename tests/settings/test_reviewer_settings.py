"""LG-017 R1 additive reviewer settings (docs/08 1.7.0).

The independent reviewer runs on its own default connection, a separate role
from the coordinator/worker, so the settings layer must expose it.  These are
unit tests over the Store/SETTINGS.md path; no network, no real secret value.
"""

from __future__ import annotations

import pytest

from lightgravity.settings import (
    ConnectionReferenceInvalid,
    ConnectionService,
    FileSecretStore,
    ROLE_REVIEWER,
    SettingsConfigInvalid,
)
from lightgravity.store import FileStore


def _service(store: FileStore, secret_store: FileSecretStore) -> ConnectionService:
    return ConnectionService(store, secret_store=secret_store)


def _connection(service: ConnectionService, connection_id: str) -> None:
    service.create_connection(
        connection_id,
        credential_ref=f"{connection_id}-ref",
        actor="test",
        request_id=f"req-{connection_id}",
    )


def test_settings_view_includes_reviewer_default(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    view = service.get_settings()
    assert "default_reviewer_connection_ref" in view
    assert view["default_reviewer_connection_ref"] is None
    assert ROLE_REVIEWER in view["defaults"]
    assert view["defaults"][ROLE_REVIEWER] is None


def test_set_reviewer_default_and_resolve(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    _connection(service, "reviewer-conn")
    result = service.update_settings(
        expected_revision=0,
        actor="test",
        default_reviewer_connection_ref="reviewer-conn",
    )
    assert result["default_reviewer_connection_ref"] == "reviewer-conn"
    pinned = service.resolve_default(ROLE_REVIEWER)
    assert pinned is not None
    assert pinned.connection_id == "reviewer-conn"
    assert pinned.role == ROLE_REVIEWER


def test_reviewer_default_is_independent_from_worker(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    _connection(service, "worker-conn")
    _connection(service, "reviewer-conn")
    service.update_settings(
        expected_revision=0,
        actor="test",
        default_worker_connection_ref="worker-conn",
        default_reviewer_connection_ref="reviewer-conn",
    )
    assert service.resolve_default("worker").connection_id == "worker-conn"  # type: ignore[union-attr]
    reviewer = service.resolve_default(ROLE_REVIEWER)
    assert reviewer is not None and reviewer.connection_id == "reviewer-conn"
    assert reviewer.connection_id != "worker-conn"


def test_missing_reviewer_ref_rejected(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    with pytest.raises(ConnectionReferenceInvalid):
        service.update_settings(
            expected_revision=0,
            actor="test",
            default_reviewer_connection_ref="nope",
        )


def test_disabled_reviewer_ref_rejected(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    service.create_connection(
        "reviewer-conn",
        credential_ref="reviewer-conn-ref",
        enabled=False,
        actor="test",
        request_id="req-reviewer-conn",
    )
    with pytest.raises(ConnectionReferenceInvalid):
        service.update_settings(
            expected_revision=0,
            actor="test",
            default_reviewer_connection_ref="reviewer-conn",
        )


def test_reviewer_reference_is_reported(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    _connection(service, "reviewer-conn")
    service.update_settings(
        expected_revision=0,
        actor="test",
        default_reviewer_connection_ref="reviewer-conn",
    )
    refs = service.references_to("reviewer-conn")
    assert ROLE_REVIEWER in refs.default_roles


def test_clear_reviewer_default(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    _connection(service, "reviewer-conn")
    service.update_settings(
        expected_revision=0,
        actor="test",
        default_reviewer_connection_ref="reviewer-conn",
    )
    cleared = service.update_settings(
        expected_revision=service.get_settings()["revision"],
        actor="test",
        default_reviewer_connection_ref=None,
    )
    assert cleared["default_reviewer_connection_ref"] is None
    assert service.resolve_default(ROLE_REVIEWER) is None


def test_invalid_expected_revision_still_enforced(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    _connection(service, "reviewer-conn")
    service.update_settings(
        expected_revision=0,
        actor="test",
        default_reviewer_connection_ref="reviewer-conn",
    )
    with pytest.raises(SettingsConfigInvalid):
        service.update_settings(
            expected_revision=None,
            actor="test",
            default_worker_connection_ref=None,
        )
