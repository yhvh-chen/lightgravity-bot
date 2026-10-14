"""Settings HTTP router factory: contract shape, conflicts and secret safety."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from lightgravity.contracts import AppError
from lightgravity.settings import (
    ConnectionService,
    ConnectionTester,
    build_settings_router,
)


def _app(service: ConnectionService, *, tester: ConnectionTester | None = None) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope().model_dump(mode="json"))

    app.include_router(
        build_settings_router(service, tester=tester), prefix="/api/v1"
    )
    return app


def _client(service: ConnectionService, *, tester: ConnectionTester | None = None) -> TestClient:
    return TestClient(_app(service, tester=tester))


def test_connection_crud_and_conflict(service: ConnectionService) -> None:
    client = _client(service)
    created = client.post(
        "/api/v1/settings/connections",
        json={
            "id": "deepseek",
            "credential_ref": "deepseek-default",
            "credential_value": "sk-router-secret",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["backend"] == "openai-compat"
    assert body["model"] == "deepseek-v4-flash"
    assert created.headers["etag"] == '"0"'
    assert "sk-router-secret" not in created.text

    listing = client.get("/api/v1/settings/connections")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == ["deepseek"]

    detail = client.get("/api/v1/settings/connections/deepseek")
    assert detail.status_code == 200
    assert detail.json()["credential"]["configured"] is True

    patched = client.patch(
        "/api/v1/settings/connections/deepseek",
        json={"expected_revision": 0, "title": "DeepSeek"},
    )
    assert patched.status_code == 200
    assert patched.json()["revision"] == 1

    conflict = client.patch(
        "/api/v1/settings/connections/deepseek",
        json={"expected_revision": 0, "title": "stale"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "revision_conflict"


def test_settings_defaults_and_legality(service: ConnectionService) -> None:
    client = _client(service)
    invalid = client.patch(
        "/api/v1/settings", json={"default_worker_connection_ref": "missing"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "reference_invalid"

    client.post(
        "/api/v1/settings/connections",
        json={"id": "deepseek", "credential_ref": "deepseek-default"},
    )
    ok = client.patch(
        "/api/v1/settings", json={"default_worker_connection_ref": "deepseek"}
    )
    assert ok.status_code == 200
    assert ok.json()["default_worker_connection_ref"] == "deepseek"
    assert ok.json()["defaults"]["worker"]["resolved"] is True

    fetched = client.get("/api/v1/settings")
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "no-store"


def test_credential_routes_never_echo_and_guard_origin(service: ConnectionService) -> None:
    client = _client(service)
    secret_value = "sk-donotprint-1234567890"
    put = client.put(
        "/api/v1/settings/credentials/deepseek-default",
        json={"action": "set", "value": secret_value},
    )
    assert put.status_code == 200
    assert put.headers["cache-control"] == "no-store"
    assert secret_value not in put.text
    assert put.json()["configured"] is True
    assert put.json()["source"] == "secret_store"

    keep = client.put(
        "/api/v1/settings/credentials/deepseek-default",
        json={"action": "keep", "value": ""},
    )
    assert keep.status_code == 200
    assert keep.json()["configured"] is True

    cross_origin = client.delete(
        "/api/v1/settings/credentials/deepseek-default",
        headers={"Origin": "https://evil.example"},
    )
    assert cross_origin.status_code == 401

    removed = client.delete(
        "/api/v1/settings/credentials/deepseek-default",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert removed.status_code == 200
    assert removed.json()["configured"] is False


def test_credential_delete_blocked_while_referenced(service: ConnectionService) -> None:
    client = _client(service)
    client.post(
        "/api/v1/settings/connections",
        json={
            "id": "deepseek",
            "credential_ref": "deepseek-default",
            "credential_value": "sk-referenced",
        },
    )
    blocked = client.delete("/api/v1/settings/credentials/deepseek-default")
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "reference_invalid"


def test_test_endpoint_returns_layered_result(service: ConnectionService) -> None:
    tester = ConnectionTester(service, allow_network=False)
    client = _client(service, tester=tester)
    client.post(
        "/api/v1/settings/connections",
        json={
            "id": "deepseek",
            "credential_ref": "deepseek-default",
            "credential_value": "sk-test",
        },
    )
    response = client.post(
        "/api/v1/settings/connections/deepseek/test", json={"allow_network": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "not_run"
    names = [layer["name"] for layer in body["layers"]]
    assert names == [
        "config_parse",
        "credential",
        "capability",
        "runtime_network",
        "tool_probe",
        "structured_output",
    ]
    assert body["connection_revision"] == 0


def test_test_endpoint_requires_tester(service: ConnectionService) -> None:
    client = _client(service)
    client.post(
        "/api/v1/settings/connections", json={"id": "deepseek"}
    )
    response = client.post("/api/v1/settings/connections/deepseek/test", json={})
    assert response.status_code == 503
