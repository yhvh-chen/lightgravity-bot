"""Host/Origin guard: loopback-first, trusted Host only (LG-020)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.hostguard import normalize_host
from lightgravity.runtime.token import RuntimeToken


def test_normalize_host_handles_ports_and_ipv6() -> None:
    assert normalize_host("127.0.0.1:8000") == "127.0.0.1"
    assert normalize_host("LocalHost:5173") == "localhost"
    assert normalize_host("[::1]:8000") == "[::1]"
    assert normalize_host("") == ""


@pytest.fixture
def guarded(tmp_settings: Settings) -> RuntimeState:
    return build_runtime(
        StartupOptions(
            settings=tmp_settings,
            token=RuntimeToken("guard-token", "generated"),
            serve_frontend=False,
            allowed_hosts=("app.localhost",),
        )
    )


@pytest.fixture
async def guarded_client(guarded: RuntimeState) -> AsyncIterator[httpx.AsyncClient]:
    async with guarded.app.router.lifespan_context(guarded.app):
        transport = httpx.ASGITransport(app=guarded.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            yield http_client


async def test_loopback_host_is_allowed(guarded_client: httpx.AsyncClient) -> None:
    response = await guarded_client.get("/api/v1/health")
    assert response.status_code == 200


async def test_unknown_host_is_rejected(guarded_client: httpx.AsyncClient) -> None:
    response = await guarded_client.get(
        "/api/v1/health", headers={"host": "evil.example"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_host"


async def test_cross_origin_is_rejected(guarded_client: httpx.AsyncClient) -> None:
    response = await guarded_client.get(
        "/api/v1/health", headers={"origin": "http://evil.example"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


async def test_explicitly_allowed_host_and_origin(
    guarded_client: httpx.AsyncClient,
) -> None:
    response = await guarded_client.get(
        "/api/v1/health",
        headers={"host": "app.localhost", "origin": "http://app.localhost"},
    )
    assert response.status_code == 200
