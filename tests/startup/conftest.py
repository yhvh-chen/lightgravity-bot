"""Fixtures for LG-020 startup/distribution tests.

Everything runs against a temporary data dir / workspace / secret store built
through the real :func:`lightgravity.api.bootstrap.build_runtime`; no network,
no real model, no writes to the repository ``bot-data``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.token import RuntimeToken

TEST_TOKEN = "test-token-lg020"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def token() -> RuntimeToken:
    return RuntimeToken(TEST_TOKEN, "generated")


@pytest.fixture
def runtime(tmp_settings: Settings, token: RuntimeToken) -> RuntimeState:
    return build_runtime(
        StartupOptions(settings=tmp_settings, token=token, serve_frontend=False)
    )


@pytest.fixture
async def client(runtime: RuntimeState) -> AsyncIterator[httpx.AsyncClient]:
    async with runtime.app.router.lifespan_context(runtime.app):
        transport = httpx.ASGITransport(app=runtime.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            yield http_client
