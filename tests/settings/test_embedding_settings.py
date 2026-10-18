"""LG-117 independent Embedding settings: precedence, secrets, cache, API.

No test contacts a real embedding service.  The network draft protocol is
covered separately with a local deterministic HTTP server in
``test_embedding_draft.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings as AppSettings
from lightgravity.contracts import AppError
from lightgravity.settings import (
    ConnectionService,
    FileSecretStore,
    build_settings_router,
)
from lightgravity.settings.embedding import EMBEDDING_CREDENTIAL_REF
from lightgravity.sources.vectors.index import VectorIndex
from lightgravity.store import FileStore

SECRET_REF = EMBEDDING_CREDENTIAL_REF


def _service(
    data_dir: Path, secret_dir: Path, *, env: dict[str, str] | None = None
) -> ConnectionService:
    return ConnectionService(
        FileStore(data_dir, data_dir / "workspaces"),
        secret_store=FileSecretStore(secret_dir),
        env=env or {},
    )


def _client(service: ConnectionService) -> TestClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_envelope().model_dump(mode="json"),
        )

    app.include_router(build_settings_router(service), prefix="/api/v1")
    return TestClient(app)


def _put(client: TestClient, body: dict, **kwargs) -> object:
    return client.put("/api/v1/settings/embedding", json=body, **kwargs)


def test_env_fallback_when_no_saved_block(tmp_path: Path) -> None:
    service = _service(
        tmp_path / "data",
        tmp_path / "secrets",
        env={
            "LIGHTGRAVITY_VECTOR_BASE_URL": "http://127.0.0.1:9999/v1",
            "LIGHTGRAVITY_VECTOR_MODEL": "env-embed",
            "LIGHTGRAVITY_VECTOR_TOKEN": "env-token-value",
            "LIGHTGRAVITY_VECTOR_TIMEOUT_SECONDS": "12",
            "LIGHTGRAVITY_VECTOR_COLD_TIMEOUT_SECONDS": "30",
        },
    )
    view = service.get_settings()["embedding"]
    assert view["enabled"] is True
    assert view["base_url"] == "http://127.0.0.1:9999/v1"
    assert view["model"] == "env-embed"
    assert view["timeout_seconds"] == 12
    assert view["cold_timeout_seconds"] == 30
    assert view["source"] == "environment"
    assert view["credential"] == {
        "ref": None,
        "configured": True,
        "source": "environment",
        "version": None,
    }
    assert "env-token-value" not in json.dumps(view)


def test_env_without_required_values_is_honestly_disabled(tmp_path: Path) -> None:
    service = _service(
        tmp_path / "data",
        tmp_path / "secrets",
        env={"LIGHTGRAVITY_VECTOR_BASE_URL": "http://127.0.0.1:9999/v1"},
    )
    view = service.get_settings()["embedding"]
    assert view["enabled"] is False
    assert view["source"] == "environment"
    assert service.embedding.backend().configured is False


def test_saved_block_overrides_env_and_false_disables(tmp_path: Path) -> None:
    service = _service(
        tmp_path / "data",
        tmp_path / "secrets",
        env={
            "LIGHTGRAVITY_VECTOR_BASE_URL": "http://env.example/v1",
            "LIGHTGRAVITY_VECTOR_MODEL": "env-model",
            "LIGHTGRAVITY_VECTOR_TIMEOUT_SECONDS": "5",
        },
    )
    client = _client(service)
    response = _put(
        client,
        {
            "expected_revision": 0,
            "enabled": False,
            "base_url": "https://saved.example/v1",
            "model": "saved-model",
            "credential_action": "keep",
            "timeout_seconds": 40,
            "cold_timeout_seconds": 90,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is False
    assert body["base_url"] == "https://saved.example/v1"
    assert body["model"] == "saved-model"
    assert body["source"] == "settings"
    assert body["timeout_seconds"] == 40
    assert body["cold_timeout_seconds"] == 90
    assert body["revision"] == 0
    assert service.embedding.backend().configured is False
    assert service.embedding.resolve().unavailable_reason == "embedding_disabled"

    # A later defaults write preserves the embedding block (deep merge).
    service.update_settings(expected_revision=0, actor="test")
    assert service.get_settings()["embedding"]["source"] == "settings"
    raw = service.repository.read_settings()
    assert raw.embedding is not None
    assert raw.embedding["enabled"] is False


def test_saved_credential_ref_never_falls_back_to_environment(tmp_path: Path) -> None:
    service = _service(
        tmp_path / "data",
        tmp_path / "secrets",
        env={"LIGHTGRAVITY_VECTOR_TOKEN": "env-token-must-not-be-used"},
    )
    client = _client(service)
    saved_secret = "saved-embedding-secret-123456"
    created = _put(
        client,
        {
            "expected_revision": 0,
            "enabled": True,
            "base_url": "https://embed.example/v1",
            "model": "embeddinggemma-2-Q8_0",
            "credential_action": "set",
            "credential_value": saved_secret,
        },
    )
    assert created.status_code == 200, created.text
    assert saved_secret not in created.text
    assert created.headers["cache-control"] == "no-store"
    view = created.json()
    assert view["credential"] == {
        "ref": SECRET_REF,
        "configured": True,
        "source": "secret_store",
        "version": view["credential"]["version"],
    }
    assert view["credential"]["version"]

    fetched = client.get("/api/v1/settings")
    assert fetched.status_code == 200
    assert saved_secret not in fetched.text
    assert fetched.json()["embedding"]["credential"]["configured"] is True

    # Deleting the saved secret leaves the saved ref authoritative: the env
    # token is not silently substituted for it.
    service.secret_store.delete(SECRET_REF)
    missing = service.get_settings()["embedding"]
    assert missing["credential"]["configured"] is False
    assert missing["credential"]["source"] is None
    resolved = service.embedding.resolve()
    assert resolved.secret is None
    assert resolved.unavailable_reason == "embedding_credential_missing"
    assert service.embedding.backend().configured is False


def test_credential_actions_keep_set_remove_and_revision_conflict(tmp_path: Path) -> None:
    service = _service(tmp_path / "data", tmp_path / "secrets")
    client = _client(service)
    base = {
        "expected_revision": 0,
        "enabled": True,
        "base_url": "https://embed.example/v1",
        "model": "embed-model",
    }
    first = _put(
        client,
        {**base, "credential_action": "set", "credential_value": "first-secret"},
    )
    assert first.status_code == 200, first.text
    revision = first.json()["revision"]
    version_one = first.json()["credential"]["version"]

    # keep preserves the exact stored secret/version.
    kept = _put(
        client,
        {
            **base,
            "expected_revision": revision,
            "credential_action": "keep",
        },
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["credential"]["version"] == version_one
    assert service.secret_store.get(SECRET_REF) is not None

    # Reusing keep with a value does not silently become set.
    bad = _put(
        client,
        {
            **base,
            "expected_revision": kept.json()["revision"],
            "credential_action": "keep",
            "credential_value": "must-not-be-written",
        },
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "config_invalid"
    assert service.secret_store.get(SECRET_REF) is not None

    stale = _put(
        client,
        {
            **base,
            "expected_revision": revision,
            "credential_action": "remove",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"
    # The failed remove did not delete the existing secret.
    assert service.secret_store.get(SECRET_REF) is not None

    removed = _put(
        client,
        {
            **base,
            "expected_revision": kept.json()["revision"],
            "credential_action": "remove",
        },
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["credential"]["configured"] is False
    assert service.secret_store.get(SECRET_REF) is None
    assert service.repository.read_settings().embedding["credential_ref"] is None


def test_embedding_validation_and_first_creation_revision(tmp_path: Path) -> None:
    service = _service(tmp_path / "data", tmp_path / "secrets")
    client = _client(service)
    missing = _put(
        client,
        {
            "expected_revision": 0,
            "enabled": True,
            "base_url": None,
            "model": None,
            "credential_action": "keep",
        },
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "config_invalid"

    bad_url = _put(
        client,
        {
            "expected_revision": 0,
            "enabled": True,
            "base_url": "file:///tmp/socket",
            "model": "m",
            "credential_action": "keep",
        },
    )
    assert bad_url.status_code == 422

    wrong_revision = _put(
        client,
        {
            "expected_revision": 7,
            "enabled": False,
            "credential_action": "keep",
        },
    )
    assert wrong_revision.status_code == 422
    assert wrong_revision.json()["error"]["code"] == "config_invalid"

    created = _put(
        client,
        {
            "expected_revision": 0,
            "enabled": False,
            "base_url": None,
            "model": None,
            "credential_action": "keep",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["revision"] == 0
    assert service.repository.read_settings().exists is True

    missing_revision = _put(
        client,
        {"enabled": False, "credential_action": "keep"},
    )
    assert missing_revision.status_code == 422


def test_embedding_save_is_independent_of_chat_defaults(tmp_path: Path) -> None:
    service = _service(tmp_path / "data", tmp_path / "secrets")
    client = _client(service)
    created_connection = client.post(
        "/api/v1/settings/connections",
        json={"id": "deepseek", "credential_ref": "deepseek-key"},
    )
    assert created_connection.status_code == 201
    defaulted = client.patch(
        "/api/v1/settings", json={"default_worker_connection_ref": "deepseek"}
    )
    assert defaulted.status_code == 200
    revision = defaulted.json()["revision"]

    saved = _put(
        client,
        {
            "expected_revision": revision,
            "enabled": True,
            "base_url": "https://embed.example/v1",
            "model": "embed-only",
            "credential_action": "keep",
        },
    )
    assert saved.status_code == 200, saved.text
    view = client.get("/api/v1/settings").json()
    assert view["default_worker_connection_ref"] == "deepseek"
    assert view["embedding"]["model"] == "embed-only"
    # Embedding is not a selectable Connection/default role.
    assert view["defaults"]["worker"]["id"] == "deepseek"
    assert "embedding" not in view["defaults"]


def test_cache_compatibility_and_vector_service_invalidation(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    secret_dir = tmp_path / "secrets"
    service = _service(data_dir, secret_dir, env={})
    client = _client(service)
    created = _put(
        client,
        {
            "expected_revision": 0,
            "enabled": True,
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "model-new",
            "credential_action": "keep",
        },
    )
    assert created.status_code == 200, created.text
    insertion = created.json()["revision"]

    cache = VectorIndex(data_dir / "sources-index" / "vectors")
    cache.replace_all([], model="model-old", dim=3)
    view = service.get_settings()["embedding"]
    assert view["cache"]["compatible"] is False
    assert view["cache"]["reason"] == "model_mismatch_rebuild_required"
    assert view["cache"]["vector_model"] == "model-old"

    app_settings = AppSettings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=secret_dir,
    )
    app = create_app(
        app_settings,
        connection_service=service,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    with TestClient(app) as api:
        status = api.get("/api/v1/vector/status")
        assert status.status_code == 200
        assert status.json()["enabled"] is True
        assert status.json()["backend"]["model"] == "model-new"
        assert status.json()["model_mismatch_rebuild_required"] is True
        assert (
            status.json()["cache"]["reason"]
            == "model_mismatch_rebuild_required"
        )

        changed = api.put(
            "/api/v1/settings/embedding",
            json={
                "expected_revision": insertion,
                "enabled": True,
                "base_url": "http://127.0.0.1:9999/v1",
                "model": "model-newer",
                "credential_action": "keep",
            },
        )
        assert changed.status_code == 200, changed.text
        after = api.get("/api/v1/vector/status")
        assert after.status_code == 200
        # The cached service was invalidated and rebuilt from the new setting.
        assert after.json()["backend"]["model"] == "model-newer"
        assert after.json()["model_mismatch_rebuild_required"] is True

        disabled = api.put(
            "/api/v1/settings/embedding",
            json={
                "expected_revision": changed.json()["revision"],
                "enabled": False,
                "base_url": "http://127.0.0.1:9999/v1",
                "model": "model-newer",
                "credential_action": "keep",
            },
        )
        assert disabled.status_code == 200, disabled.text
        fallback = api.get("/api/v1/vector/search", params={"q": "alpha"})
        assert fallback.status_code == 200
        assert fallback.json()["index_status"] == "index_unavailable"
        assert fallback.json()["lexical_fallback"] is True


def test_embedding_endpoints_require_protected_settings_access(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    secret_dir = tmp_path / "secrets"
    service = _service(data_dir, secret_dir, env={})
    app_settings = AppSettings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=secret_dir,
    )
    # No token injected: the default local policy denies sensitive writes.
    app = create_app(app_settings, connection_service=service)
    with TestClient(app) as api:
        denied = api.put(
            "/api/v1/settings/embedding",
            json={"enabled": False, "credential_action": "keep"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "unauthorized"
        denied_test = api.post(
            "/api/v1/settings/embedding/test-draft",
            json={"base_url": "http://127.0.0.1:1/v1", "model": "m"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert denied_test.status_code == 401
        # The read-only view remains available under the normal settings read
        # policy; nothing was written.
        read = api.get("/api/v1/settings")
        assert read.status_code == 200
        assert read.json()["embedding"]["source"] == "none"
