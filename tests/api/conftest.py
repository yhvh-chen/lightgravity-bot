"""Fixtures for the LG-012 API tests.

All data goes to pytest ``tmp_path``; the app is built through the real
``create_app`` factory with an explicit access policy, so the tests exercise the
frozen wiring rather than a mock app.  The default ``app`` uses the honest
``UnavailableExecutor`` (no SDK); tests that need a controllable Run inject the
``FakeExecutor`` through the ``run_app`` fixture.  Shared doubles and polling
helpers live in :mod:`api_helpers`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings

from api_helpers import FakeExecutor


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


@pytest.fixture
def fake_executor() -> FakeExecutor:
    return FakeExecutor()


@pytest.fixture
def run_app(settings: Settings, fake_executor: FakeExecutor) -> FastAPI:
    return create_app(
        settings,
        executor=fake_executor,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )


@pytest.fixture
async def run_api(run_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with run_app.router.lifespan_context(run_app):
        transport = httpx.ASGITransport(app=run_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


@pytest.fixture
async def deny_client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, access_policy=LocalAccessPolicy())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client
