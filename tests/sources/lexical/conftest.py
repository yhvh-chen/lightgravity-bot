"""Fixtures for the LG-036 lexical-index tests.

These build a **real** ``SourceStore`` + ``LexicalSearchService`` over pytest
``tmp_path`` and mount the real ``build_search_router()`` onto a real
``create_app`` app, so the tests exercise the endpoint the way the integration
owner assembles it (``api/app.py`` is untouched).  No network, no model call,
no delivery Run.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.api.search import build_search_router
from lightgravity.api.sources import build_sources_router
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX
from lightgravity.sources import SourceStore, build_source_service
from lightgravity.sources.lexical import LexicalSearchService


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
    app.include_router(build_search_router(), prefix=API_PREFIX)
    return app


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return build_app(settings)


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
def source_store(settings: Settings) -> SourceStore:
    return SourceStore(settings.data_dir)


@pytest.fixture
def service(source_store: SourceStore) -> LexicalSearchService:
    return LexicalSearchService(source_store)


@pytest.fixture
def source_service(settings: Settings, source_store: SourceStore, service: LexicalSearchService):
    return build_source_service(
        data_dir=settings.data_dir,
        task_store=None,
        resolve_path=None,
        events=None,
    )


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
