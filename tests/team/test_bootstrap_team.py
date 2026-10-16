"""Team-mode runtime assembly: policy wired, token not injected (LG-050 §6)."""

from __future__ import annotations

from pathlib import Path

import httpx

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.token import RuntimeToken
from lightgravity.team import TeamAccessPolicy


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
        team_mode=True,
    )


async def test_team_runtime_uses_session_policy_and_hides_token(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><html><head></head><body>app</body></html>", "utf-8"
    )
    state = build_runtime(
        StartupOptions(
            settings=_settings(tmp_path),
            token=RuntimeToken("super-secret-token", "environment"),
            frontend_dist=dist,
            serve_frontend=True,
            wire_real_executor=False,
        )
    )
    assert isinstance(
        getattr(state.app.state, "access_policy", None), TeamAccessPolicy
    )
    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            page = await client.get("/")
            assert "super-secret-token" not in page.text
            assert 'window.__LG_RUNTIME_TOKEN__=""' in page.text
            # Anonymous business access is still denied at the assembled runtime.
            assert (await client.get("/api/v1/team/available")).status_code == 401
            assert (await client.get("/api/v1/auth/me")).json()["mode"] == "team"


def test_team_runtime_state_is_honest(tmp_path: Path) -> None:
    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=_settings(tmp_path),
            token=RuntimeToken("t", "environment"),
            serve_frontend=False,
            wire_real_executor=False,
        )
    )
    report = state.execution_report()
    assert report["token_source"] == "environment"
    assert report["execution_ready"] is False  # no executor/credential configured
