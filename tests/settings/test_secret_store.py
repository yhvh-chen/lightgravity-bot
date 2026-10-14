"""Controlled secret store: lifecycle, versions and permissions (docs/07 §4)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from lightgravity.adapter.credentials import CredentialResolver, EnvCredentialResolver
from lightgravity.settings import (
    ConnectionService,
    FileSecretStore,
    SecretStoreCredentialResolver,
    SettingsConfigInvalid,
)


def test_put_get_version_status(secret_store: FileSecretStore) -> None:
    version = secret_store.put("deepseek-default", "sk-unit-test-value")
    assert version.startswith("cred_")
    secret = secret_store.get("deepseek-default")
    assert secret is not None
    assert secret.reveal() == "sk-unit-test-value"
    assert repr(secret) == "Secret(<redacted>)"

    status = secret_store.status("deepseek-default")
    assert status.configured is True
    assert status.source == "secret_store"
    assert status.version == version


def test_update_changes_version_but_not_value_in_metadata(
    secret_store: FileSecretStore,
) -> None:
    first = secret_store.put("ref-a", "value-one")
    second = secret_store.put("ref-a", "value-two")
    assert first != second
    assert secret_store.version("ref-a") == second
    assert secret_store.get("ref-a").reveal() == "value-two"  # type: ignore[union-attr]

    metadata = (secret_store.directory / "metadata.json").read_text("utf-8")
    assert "value-one" not in metadata
    assert "value-two" not in metadata
    payload = json.loads(metadata)
    assert payload["ref-a"]["version"] == second


def test_delete_removes_value_and_version(secret_store: FileSecretStore) -> None:
    secret_store.put("ref-b", "value")
    assert secret_store.delete("ref-b") is True
    assert secret_store.get("ref-b") is None
    assert secret_store.version("ref-b") is None
    assert secret_store.delete("ref-b") is False


def test_empty_value_never_deletes_existing(secret_store: FileSecretStore) -> None:
    secret_store.put("ref-c", "keep-me")
    with pytest.raises(SettingsConfigInvalid):
        secret_store.put("ref-c", "   ")
    assert secret_store.get("ref-c").reveal() == "keep-me"  # type: ignore[union-attr]


def test_invalid_ref_rejected(secret_store: FileSecretStore) -> None:
    with pytest.raises(SettingsConfigInvalid):
        secret_store.put("../escape", "value")
    with pytest.raises(SettingsConfigInvalid):
        secret_store.put("Upper", "value")


def test_owner_only_permissions(secret_store: FileSecretStore) -> None:
    secret_store.put("ref-d", "value")
    assert secret_store.check_permissions() == []
    dir_mode = stat.S_IMODE(os.stat(secret_store.directory).st_mode)
    assert dir_mode == 0o700
    entry = secret_store.directory / "ref-d.secret"
    assert stat.S_IMODE(os.stat(entry).st_mode) == 0o600

    os.chmod(entry, 0o644)
    issues = secret_store.check_permissions()
    assert any("ref-d.secret" in issue for issue in issues)


def test_resolver_prefers_store_then_environment(secret_store: FileSecretStore) -> None:
    resolver = SecretStoreCredentialResolver(
        secret_store,
        env_resolver=EnvCredentialResolver(env={"ENV_ONLY_REF": "env-value"}),
    )
    assert resolver.resolve("env-only-ref").reveal() == "env-value"  # type: ignore[union-attr]
    assert resolver.source("env-only-ref").source == "environment"

    secret_store.put("env-only-ref", "store-value")
    assert resolver.resolve("env-only-ref").reveal() == "store-value"  # type: ignore[union-attr]
    assert resolver.source("env-only-ref").source == "secret_store"

    assert resolver.resolve("missing-ref") is None
    assert resolver.source("missing-ref").configured is False


def test_unreadable_directory_does_not_leak(tmp_path: Path) -> None:
    store = FileSecretStore(tmp_path / "nested" / "secrets")
    store.put("ref-e", "value")
    assert (tmp_path / "nested" / "secrets" / "ref-e.secret").read_text("utf-8") == "value"


def test_service_resolver_satisfies_adapter_protocol(service: ConnectionService) -> None:
    assert isinstance(service.credential_resolver, CredentialResolver)
    service.set_credential("ref-f", "value")
    secret = service.credential_resolver.resolve("ref-f")
    assert secret is not None and secret.reveal() == "value"
