"""Shared helpers and fixtures for the LG-050 team tests.

Fixtures live here (rather than in a ``conftest.py``) because every test
directory in this repository inserts a top-level ``conftest`` module name and
an extra ``tests/team/conftest.py`` would shadow ``tests/startup``'s
``from conftest import ...`` imports.  Test modules import the fixtures they
need explicitly; pytest discovers them in the importing module's namespace.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.team import TeamAccounts

ADMIN_PASSWORD = "admin-secret-pw"
MEMBER_PASSWORD = "member-secret-pw"


def make_team_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
        team_mode=True,
    )


@pytest.fixture
def team_settings(tmp_path: Path) -> Settings:
    return make_team_settings(tmp_path)


@pytest.fixture
def seeded_accounts(team_settings: Settings) -> TeamAccounts:
    store = TeamAccounts(team_settings.team_accounts_path)
    store.add("admin", ADMIN_PASSWORD, "admin")
    store.add("alice", MEMBER_PASSWORD, "member")
    return store


@pytest.fixture
def team_app(team_settings: Settings, seeded_accounts: TeamAccounts) -> FastAPI:
    return create_app(team_settings)


@pytest.fixture
async def team_client(team_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with team_app.router.lifespan_context(team_app):
        transport = httpx.ASGITransport(app=team_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def login(
    client: httpx.AsyncClient, username: str, password: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


async def login_admin(client: httpx.AsyncClient) -> httpx.Response:
    return await login(client, "admin", ADMIN_PASSWORD)


async def login_member(client: httpx.AsyncClient) -> httpx.Response:
    return await login(client, "alice", MEMBER_PASSWORD)


def error_code(response: httpx.Response) -> str:
    return str(response.json()["error"]["code"])
