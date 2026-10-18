"""Shared pytest fixtures for the engineering skeleton."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from lightgravity.api.app import create_app
from lightgravity.config import Settings


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, enable_intake_worker=False)
    # httpx.ASGITransport does not run lifespan events; do it explicitly so
    # startup behaviour (data dir creation) is exercised.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            yield http_client
