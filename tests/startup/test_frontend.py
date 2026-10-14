"""One-process static frontend serving with SPA fallback + token injection (LG-020)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.token import RuntimeToken

TOKEN = "frontend-token-lg020"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>LG</title></head>"
        "<body><div id=\"root\"></div></body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('app')\n", encoding="utf-8")
    return dist


@pytest.fixture
async def frontend_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    state = build_runtime(
        StartupOptions(
            settings=_settings(tmp_path),
            token=RuntimeToken(TOKEN, "generated"),
            frontend_dist=_make_dist(tmp_path),
            serve_frontend=True,
        )
    )
    assert state.frontend_served is True
    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_index_injects_token_and_is_no_store(
    frontend_client: httpx.AsyncClient,
) -> None:
    response = await frontend_client.get("/")
    assert response.status_code == 200
    assert TOKEN in response.text
    assert "__LG_RUNTIME_TOKEN__" in response.text
    assert "no-store" in response.headers["cache-control"]


async def test_static_asset_is_served(frontend_client: httpx.AsyncClient) -> None:
    response = await frontend_client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


async def test_spa_deep_link_falls_back_to_index(
    frontend_client: httpx.AsyncClient,
) -> None:
    response = await frontend_client.get("/board/task_123")
    assert response.status_code == 200
    assert "__LG_RUNTIME_TOKEN__" in response.text


async def test_unknown_api_path_is_not_the_spa(
    frontend_client: httpx.AsyncClient,
) -> None:
    response = await frontend_client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


async def test_missing_build_serves_minimal_bootstrap_page(tmp_path: Path) -> None:
    state = build_runtime(
        StartupOptions(
            settings=_settings(tmp_path),
            token=RuntimeToken(TOKEN, "generated"),
            frontend_dist=tmp_path / "missing-dist",
            serve_frontend=True,
        )
    )
    assert state.frontend_served is False
    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/")
    assert response.status_code == 200
    assert "backend is running" in response.text
    assert TOKEN in response.text
