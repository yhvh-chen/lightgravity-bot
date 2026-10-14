"""Real endpoint tests for /api/v1/health and /api/v1/version (LG-002)."""

from __future__ import annotations

import httpx

from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX, CONTRACT_VERSION, SCHEMA_NAMESPACE


async def test_health_reports_liveness_and_capabilities(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(f"{API_PREFIX}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["schema_version"] == SCHEMA_NAMESPACE
    assert body["capabilities"]["health"] is True
    assert body["capabilities"]["version"] is True
    # Unimplemented features must not be advertised as available.
    assert body["capabilities"]["sdk_adapter"] is False


async def test_version_reports_runtime_facts(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API_PREFIX}/version")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["schema_version"] == SCHEMA_NAMESPACE
    assert body["python_version"].startswith("3.12")
    assert body["platform"]


async def test_unknown_path_returns_error_envelope(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(f"{API_PREFIX}/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
