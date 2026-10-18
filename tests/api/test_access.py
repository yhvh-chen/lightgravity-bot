"""Local access policy: default-deny, token enforcement and origin rules (LG-012)."""

from __future__ import annotations

import types
from collections.abc import AsyncIterator

import httpx
import pytest

from lightgravity.api.access import (
    TOKEN_HEADER,
    LocalAccessPolicy,
    is_admin_only_request,
    is_sensitive_request,
)
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.contracts import AppError


class _FakeRequest:
    def __init__(
        self,
        host: str,
        *,
        headers: dict[str, str] | None = None,
        path: str = "/api/v1/settings",
        method: str = "PATCH",
    ) -> None:
        self.headers = headers or {}
        self.url = types.SimpleNamespace(path=path)
        self.client = types.SimpleNamespace(host=host)
        self.method = method


@pytest.fixture
async def token_client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, access_policy=LocalAccessPolicy(token="sesame"))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_default_denies_sensitive_writes_but_allows_reads(
    deny_client: httpx.AsyncClient,
) -> None:
    read = await deny_client.get("/api/v1/settings")
    assert read.status_code == 200

    write = await deny_client.patch("/api/v1/settings", json={})
    assert write.status_code == 401
    body = write.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["details"]["reason"] == "authorization_not_configured"

    create = await deny_client.post("/api/v1/settings/connections", json={"id": "x"})
    assert create.status_code == 401


async def test_token_policy_requires_header_on_sensitive_writes(
    token_client: httpx.AsyncClient,
) -> None:
    denied = await token_client.patch("/api/v1/settings", json={})
    assert denied.status_code == 401

    allowed = await token_client.patch(
        "/api/v1/settings", json={}, headers={TOKEN_HEADER: "sesame"}
    )
    assert allowed.status_code == 200

    read = await token_client.get("/api/v1/settings")
    assert read.status_code == 200


def test_non_loopback_requires_configured_token() -> None:
    request = _FakeRequest("10.1.2.3")
    with pytest.raises(AppError) as unconfigured:
        LocalAccessPolicy().authorize(request, sensitive=False)  # type: ignore[arg-type]
    assert unconfigured.value.details["reason"] == "token_not_configured"

    policy = LocalAccessPolicy(token="sesame")
    with pytest.raises(AppError):
        policy.authorize(request, sensitive=False)  # type: ignore[arg-type]
    policy.authorize(  # type: ignore[arg-type]
        _FakeRequest("10.1.2.3", headers={TOKEN_HEADER: "sesame"}), sensitive=False
    )


def test_sensitive_classification_and_escape_hatch() -> None:
    assert is_sensitive_request(_FakeRequest("127.0.0.1", method="PATCH")) is True
    assert (
        is_sensitive_request(
            _FakeRequest("127.0.0.1", method="GET", path="/api/v1/settings/connections")
        )
        is False
    )
    # LG-144: the full vector rebuild is a protected/admin write.
    rebuild = _FakeRequest(
        "127.0.0.1", method="POST", path="/api/v1/vector/rebuild"
    )
    assert is_sensitive_request(rebuild) is True
    assert is_admin_only_request(rebuild) is True
    assert (
        is_sensitive_request(
            _FakeRequest("127.0.0.1", method="GET", path="/api/v1/vector/rebuild")
        )
        is False
    )
    # Explicit test/tool injection may allow sensitive writes on loopback.
    LocalAccessPolicy(allow_sensitive_without_token=True).authorize(
        _FakeRequest("127.0.0.1"), sensitive=True  # type: ignore[arg-type]
    )
