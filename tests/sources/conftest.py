"""Fixtures for the LG-034 source-intake tests.

The tests exercise the endpoints the way the integration owner will assemble
them: a **real** ``create_app`` app (real FileStore, real access policy, real
coordinator lifespan) with ``build_sources_router()`` mounted at ``/api/v1``.
That keeps the API actually wired into an app rather than tested as an isolated
helper, while ``api/app.py`` itself (owned by another task) is untouched.

All state lives under pytest ``tmp_path``; no network, no real model, no
delivery Run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.api.sources import build_sources_router
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def build_app(settings: Settings) -> FastAPI:
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    # One-line wiring the integration owner applies to api/app.py.
    app.include_router(build_sources_router(), prefix=API_PREFIX)
    return app


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return build_app(settings)


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


@pytest.fixture
def workspace(settings: Settings) -> Path:
    root = settings.workspace_root
    root.mkdir(parents=True, exist_ok=True)
    return root
