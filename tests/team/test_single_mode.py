"""Single-user mode stays unchanged when team mode is off (LG-050 §1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.config import Settings


def test_team_settings_are_off_by_default() -> None:
    settings = Settings.from_env({})
    assert settings.team_mode is False
    assert settings.team_bot_mention == "@bot"
    assert settings.team_session_ttl_seconds == 28800
    assert settings.team_accounts is None
    assert settings.team_accounts_path == Path("bot-data") / "team" / "accounts.json"


def test_team_env_overrides() -> None:
    settings = Settings.from_env(
        {
            "LIGHTGRAVITY_TEAM_MODE": "yes",
            "LIGHTGRAVITY_TEAM_ACCOUNTS": "/tmp/custom-accounts.json",
            "LIGHTGRAVITY_TEAM_SESSION_TTL_SECONDS": "60",
            "LIGHTGRAVITY_TEAM_COOKIE_SECURE": "on",
            "LIGHTGRAVITY_TEAM_BOT_MENTION": "!lg",
        }
    )
    assert settings.team_mode is True
    assert settings.team_accounts == Path("/tmp/custom-accounts.json")
    assert settings.team_session_ttl_seconds == 60
    assert settings.team_cookie_secure is True
    assert settings.team_bot_mention == "!lg"


@pytest.fixture
def single_app(settings: Settings) -> tuple[FastAPI, list[str]]:
    calls: list[str] = []

    def responder(content: str, classification: Any) -> str:
        calls.append(content)
        return f"BOT:{content}"

    return create_app(settings, responder=responder), calls


@pytest.fixture
async def single_client(
    single_app: tuple[FastAPI, list[str]],
) -> AsyncIterator[httpx.AsyncClient]:
    app, _calls = single_app
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_single_mode_me_and_login(
    single_client: httpx.AsyncClient, settings: Settings
) -> None:
    me = await single_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "mode": "single",
        "authenticated": True,
        "username": None,
        "role": "admin",
    }
    login = await single_client.post(
        "/api/v1/auth/login", json={"username": "x", "password": "y"}
    )
    assert login.status_code == 404
    # No accounts file is created as a side effect of running single-user mode.
    assert not settings.team_accounts_path.exists()


async def test_single_mode_global_message_still_routes_without_mention(
    single_client: httpx.AsyncClient, single_app: tuple[FastAPI, list[str]]
) -> None:
    _app, calls = single_app
    response = await single_client.post(
        "/api/v1/conversations/global/messages",
        json={"message_id": "msg_single_1", "content": "hello without mention"},
    )
    assert response.status_code == 200
    assert response.json()["kind"] != "recorded"
    assert len(calls) == 1
    # Author is not injected in single-user mode.
    history = await single_client.get("/api/v1/conversations/global/messages")
    item = next(
        entry
        for entry in history.json()["items"]
        if entry["message_id"] == "msg_single_1"
    )
    assert "author" not in item["message"]
