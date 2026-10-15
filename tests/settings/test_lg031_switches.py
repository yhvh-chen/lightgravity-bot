"""LG-031 additive decentralized switches in SETTINGS.md (docs/08 §6.5).

The three switches are non-secret, default-closed values.  A missing or invalid
value must resolve to the closed/deterministic path; an explicit write opens the
opt-in path.  No network, no model, no secret value.
"""

from __future__ import annotations

import pytest

from lightgravity.collaboration import ClaimPolicyReader
from lightgravity.settings import ConnectionService, FileSecretStore, SettingsConfigInvalid
from lightgravity.store import FileStore


def _service(store: FileStore, secret_store: FileSecretStore) -> ConnectionService:
    return ConnectionService(store, secret_store=secret_store)


def test_defaults_are_closed(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    view = service.get_settings()
    assert view["decentralized_claim_enabled"] is False
    assert view["collab_requests_enabled"] is False
    assert view["claim_lease_seconds"] == 300
    # The claim policy reader (used by the endpoints) agrees: closed by default.
    policy = ClaimPolicyReader(store).read()
    assert policy.enabled is False
    assert policy.collab_requests_enabled is False
    assert policy.lease_seconds == 300


def test_enable_and_read_back(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    result = service.update_settings(
        expected_revision=0,
        actor="test",
        decentralized_claim_enabled=True,
        collab_requests_enabled=True,
        claim_lease_seconds=120,
    )
    assert result["decentralized_claim_enabled"] is True
    assert result["collab_requests_enabled"] is True
    assert result["claim_lease_seconds"] == 120
    policy = ClaimPolicyReader(store).read()
    assert policy.enabled is True
    assert policy.collab_requests_enabled is True
    assert policy.lease_seconds == 120


def test_omitted_field_keeps_current_value(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    service.update_settings(
        expected_revision=0, actor="test", decentralized_claim_enabled=True
    )
    revision = int(service.get_settings()["revision"])
    # A second update that only touches the collaboration switch must not reset
    # the claim switch back to the closed default.
    service.update_settings(
        expected_revision=revision, actor="test", collab_requests_enabled=True
    )
    view = service.get_settings()
    assert view["decentralized_claim_enabled"] is True
    assert view["collab_requests_enabled"] is True


def test_invalid_lease_seconds_rejected(store: FileStore, secret_store: FileSecretStore) -> None:
    service = _service(store, secret_store)
    with pytest.raises(SettingsConfigInvalid):
        service.update_settings(
            expected_revision=0, actor="test", claim_lease_seconds=0
        )
