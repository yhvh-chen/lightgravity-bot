"""LG-249: health exposes the real Team mention without a frontend fallback."""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.team import TeamAccounts

from team_helpers import seeded_accounts, team_settings


@pytest.mark.parametrize("mention", ["@bot", "!lg", "  @ops  "])
async def test_team_health_exposes_exact_configured_mention(
    team_settings: Settings,
    seeded_accounts: TeamAccounts,
    mention: str,
) -> None:
    settings = replace(team_settings, team_bot_mention=mention)
    app: FastAPI = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            body = response.json()
            # The exact resolved setting, not a default substituted by the API.
            assert body["team_bot_mention"] == mention
            # Existing health compatibility stays intact.
            assert body["status"] == "ok"
            assert body["capabilities"]["health"] is True
            assert body["capabilities"]["global_chat"] is True
