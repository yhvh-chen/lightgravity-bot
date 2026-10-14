"""Fixtures for LG-015 Team/Resources tests (own directory, tmp data only)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


def create_resource(
    app: FastAPI,
    kind: str,
    resource_id: str,
    content: dict,
    *,
    body: str = "",
) -> None:
    app.state.store.create(
        kind,
        resource_id,
        content,
        actor="test",
        request_id=f"req-{resource_id}",
        body=body,
    )


__all__ = ["create_resource"]
