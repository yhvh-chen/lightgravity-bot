"""LG-111 integration: persisted last_test summary, DELETE and host policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from lightgravity.contracts import AppError, ErrorCode, error_envelope
from lightgravity.settings import (
    ConnectionService,
    ConnectionTestLog,
    ConnectionTester,
    FileSecretStore,
    build_settings_router,
)
from lightgravity.settings.testing import DraftConnectionSpec
from lightgravity.store import FileStore


def _service(tmp_path: Path, *, log: ConnectionTestLog | None = None) -> ConnectionService:
    return ConnectionService(
        FileStore(tmp_path / "data", tmp_path / "data" / "workspaces"),
        secret_store=FileSecretStore(tmp_path / "secrets"),
        test_diagnostics=log,
    )


def _client(service: ConnectionService) -> TestClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_envelope().model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors():
            clean = dict(error)
            clean.pop("input", None)
            errors.append(clean)
        envelope = error_envelope(
            ErrorCode.VALIDATION_FAILED,
            "request failed schema validation",
            details={"errors": errors},
        )
        return JSONResponse(status_code=422, content=envelope.model_dump(mode="json"))

    app.include_router(build_settings_router(service), prefix="/api/v1")
    return TestClient(app)


def test_last_test_is_only_the_latest_saved_safe_diagnostic(tmp_path: Path) -> None:
    log = ConnectionTestLog(tmp_path / "diagnostics")
    service = _service(tmp_path, log=log)
    service.create_connection(
        "deepseek",
        credential_ref="deepseek-key",
        credential_value="sk-saved-secret",
        actor="test",
        request_id="req-create",
    )
    assert service.get_connection("deepseek")["last_test"] is None

    tester = ConnectionTester(service, diagnostics=log, allow_network=False)
    saved = tester.test("deepseek", allow_network=False)
    summary = service.get_connection("deepseek")["last_test"]
    assert summary == {
        "overall": saved.overall,
        "finished_at": saved.finished_at,
        "test_id": saved.test_id,
        "connection_revision": saved.connection_revision,
        "credential_version": saved.credential_version,
    }
    assert set(summary) == {
        "overall",
        "finished_at",
        "test_id",
        "connection_revision",
        "credential_version",
    }
    assert "layers" not in summary and "note" not in summary
    assert "sk-saved-secret" not in str(summary)
    listing = _client(service).get("/api/v1/settings/connections")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["last_test"] == summary

    # A transient draft result is not a saved version and never enters last_test.
    draft = tester.test_draft(
        DraftConnectionSpec(
            backend="gemini",
            model="gemini-3.8-flash",
            auth_mode="api_key",
        ),
        credential_value="sk-draft-secret",
        allow_network=False,
    )
    assert draft.draft is True
    assert log.latest("deepseek")["test_id"] == saved.test_id
    assert service.get_connection("deepseek")["last_test"]["test_id"] == saved.test_id

    # The summary is bound to the old revision; a later edit leaves it for the
    # UI to render as stale rather than silently rebinding it.
    service.update_connection(
        "deepseek", expected_revision=0, actor="test", title="Renamed"
    )
    stale = service.get_connection("deepseek")["last_test"]
    assert stale is not None
    assert stale["connection_revision"] == 0
    assert service.get_connection("deepseek")["revision"] == 1


def test_delete_connection_success_revision_404_and_secret_preservation(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.create_connection(
        "deepseek",
        credential_ref="shared-key",
        credential_value="sk-delete-secret",
        actor="test",
        request_id="req-create",
    )
    client = _client(service)

    deleted = client.request(
        "DELETE",
        "/api/v1/settings/connections/deepseek",
        json={"expected_revision": 0},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True, "id": "deepseek"}
    assert deleted.headers["cache-control"] == "no-store"
    assert service.list_connections() == []
    # The secret store is shared and must not be auto-deleted with the record.
    secret = service.secret_store.get("shared-key")
    assert secret is not None and secret.reveal() == "sk-delete-secret"

    missing = client.request(
        "DELETE",
        "/api/v1/settings/connections/deepseek",
        json={"expected_revision": 0},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    service.create_connection("stale", actor="test", request_id="req-stale")
    service.update_connection("stale", expected_revision=0, actor="test", title="v1")
    conflict = client.request(
        "DELETE",
        "/api/v1/settings/connections/stale",
        json={"expected_revision": 0},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "revision_conflict"

    invalid = client.request(
        "DELETE", "/api/v1/settings/connections/stale", json={}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_failed"


def test_delete_is_blocked_by_default_and_agent_references_without_rewriting(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.create_connection("deepseek", actor="test", request_id="req-create")
    service.update_settings(
        expected_revision=None,
        actor="test",
        default_worker_connection_ref="deepseek",
    )
    store = service.repository.store
    store.create(
        "agent",
        "helper",
        {"title": "Helper", "enabled": True, "connection_ref": "deepseek"},
        actor="test",
        request_id="req-agent",
    )
    before_settings = service.get_settings()
    before_agent = store.read("agent", "helper").entity

    client = _client(service)
    blocked = client.request(
        "DELETE",
        "/api/v1/settings/connections/deepseek",
        json={"expected_revision": 0},
    )
    assert blocked.status_code == 422
    error = blocked.json()["error"]
    assert error["code"] == "reference_invalid"
    assert error["details"]["detail"] == "connection_still_referenced"
    assert error["details"]["references"]["default_roles"] == ["worker"]
    assert error["details"]["references"]["agent_refs"] == ["helper"]

    # The failed delete did not remove the record, default or agent reference.
    assert service.get_connection("deepseek")["id"] == "deepseek"
    assert service.get_settings() == before_settings
    assert store.read("agent", "helper").entity == before_agent


def test_capabilities_bind_execution_to_the_actual_deepseek_host(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    deepseek = service.create_connection(
        "deepseek",
        credential_ref="deepseek-key",
        actor="test",
        request_id="req-deepseek",
    )
    assert deepseek["capabilities"] == {
        "configurable": True,
        "testable": True,
        "executable": True,
        "vendor_verified": True,
    }
    service.update_settings(
        expected_revision=None,
        actor="test",
        default_worker_connection_ref="deepseek",
    )

    custom = service.create_connection(
        "custom",
        backend="openai-compat",
        model="custom-model",
        base_url="https://custom.example/v1",
        auth_mode="proxy_api_key",
        credential_ref="custom-key",
        actor="test",
        request_id="req-custom",
    )
    # LG-230: any host executes and may be the default; only DeepSeek is
    # shown as vendor-verified.
    assert custom["capabilities"] == {
        "configurable": True,
        "testable": True,
        "executable": True,
        "vendor_verified": False,
    }
    service.update_settings(
        expected_revision=service.get_settings()["revision"],
        actor="test",
        default_worker_connection_ref="custom",
    )

    loopback = service.create_connection(
        "loopback",
        backend="openai-compat",
        model="custom-model",
        base_url="http://127.0.0.1:9/v1",
        auth_mode="proxy_api_key",
        credential_ref="loop-key",
        actor="test",
        request_id="req-loop",
    )
    assert loopback["capabilities"]["executable"] is True
    assert loopback["capabilities"]["vendor_verified"] is False


def test_legacy_custom_record_is_preserved_and_executable(
    tmp_path: Path,
) -> None:
    store = FileStore(tmp_path / "data", tmp_path / "data" / "workspaces")
    store.create(
        "connection",
        "legacy-custom",
        {
            "title": "Legacy custom",
            "enabled": True,
            "backend": "openai-compat",
            "model": "legacy-model",
            "base_url": "https://legacy.example/v1",
            "credential_ref": "legacy-key",
        },
        actor="test",
        request_id="req-legacy",
    )
    service = ConnectionService(
        store, secret_store=FileSecretStore(tmp_path / "secrets")
    )
    view = service.get_connection("legacy-custom")
    assert view["auth_mode"] is None
    assert view["base_url"] == "https://legacy.example/v1"
    assert view["credential_ref"] == "legacy-key"
    assert view["capabilities"] == {
        "configurable": True,
        "testable": True,
        "executable": True,
        "vendor_verified": False,
    }
    # Reading never migrates/rewrites the old record.
    stored = store.read("connection", "legacy-custom").entity
    assert stored["base_url"] == "https://legacy.example/v1"
    assert stored["credential_ref"] == "legacy-key"
    assert "auth_mode" not in stored
