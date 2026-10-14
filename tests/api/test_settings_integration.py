"""Integration of the LG-025 settings router through the real app factory (LG-012)."""

from __future__ import annotations

import httpx
from fastapi import FastAPI

SECRET_VALUE = "sk-lg012-donotprint-1234567890"


async def test_settings_connections_defaults_and_additive_routes(
    api: httpx.AsyncClient,
) -> None:
    initial = await api.get("/api/v1/settings")
    assert initial.status_code == 200
    assert initial.headers["cache-control"] == "no-store"
    assert initial.json()["exists"] is False

    created = await api.post(
        "/api/v1/settings/connections",
        json={"id": "deepseek", "credential_ref": "deepseek-default"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["id"] == "deepseek"
    assert created.headers["etag"] == '"0"'

    # Additive detail route recorded for the integration owner (LG-025/LG-012).
    detail = await api.get("/api/v1/settings/connections/deepseek")
    assert detail.status_code == 200
    assert detail.json()["credential"]["configured"] is False

    default = await api.patch(
        "/api/v1/settings", json={"default_worker_connection_ref": "deepseek"}
    )
    assert default.status_code == 200, default.text
    assert default.json()["default_worker_connection_ref"] == "deepseek"
    assert default.json()["defaults"]["worker"]["resolved"] is True


async def test_credentials_never_echo_and_reference_blocking(api: httpx.AsyncClient) -> None:
    await api.post(
        "/api/v1/settings/connections",
        json={"id": "deepseek", "credential_ref": "deepseek-default"},
    )

    put = await api.put(
        "/api/v1/settings/credentials/deepseek-default",
        json={"action": "set", "value": SECRET_VALUE},
    )
    assert put.status_code == 200, put.text
    assert put.headers["cache-control"] == "no-store"
    assert SECRET_VALUE not in put.text
    assert put.json()["configured"] is True
    assert put.json()["source"] == "secret_store"

    fetched = await api.get("/api/v1/settings/connections/deepseek")
    assert SECRET_VALUE not in fetched.text
    assert fetched.json()["credential"]["configured"] is True

    blocked = await api.delete("/api/v1/settings/credentials/deepseek-default")
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "reference_invalid"
    assert blocked.json()["error"]["details"]["references"]["connections"] == ["deepseek"]


async def test_health_reports_wired_capabilities(api: httpx.AsyncClient) -> None:
    health = await api.get("/api/v1/health")
    assert health.status_code == 200
    capabilities = health.json()["capabilities"]
    assert capabilities["store"] is True
    assert capabilities["events_sse"] is True
    assert capabilities["settings"] is True
    assert capabilities["resources"] is True
    assert capabilities["files"] is True
    # The fake executor is not the real SDK adapter.
    assert capabilities["sdk_adapter"] is False
