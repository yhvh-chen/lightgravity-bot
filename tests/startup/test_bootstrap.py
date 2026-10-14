"""Runtime assembly: health/settings reachable, token protection, readiness (LG-020)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.minimal import AgentInit, ConnectionInit, initialize_minimal
from lightgravity.runtime.token import RuntimeToken

TEST_TOKEN = "test-token-lg020"
CONNECTION_ID = "lg-primary"
CREDENTIAL_REF = "lg-worker-key"


async def test_health_advertises_real_executor(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["capabilities"]["sdk_adapter"] is True
    assert body["capabilities"]["settings"] is True


async def test_history_and_settings_readable_without_token(
    client: httpx.AsyncClient,
) -> None:
    tasks = await client.get("/api/v1/tasks")
    assert tasks.status_code == 200
    settings = await client.get("/api/v1/settings")
    assert settings.status_code == 200


async def test_sensitive_write_default_denied_then_token_unlocks(
    client: httpx.AsyncClient,
) -> None:
    denied = await client.patch("/api/v1/settings", json={})
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "unauthorized"

    allowed = await client.patch(
        "/api/v1/settings", json={}, headers={"X-LG-Token": TEST_TOKEN}
    )
    assert allowed.status_code == 200
    assert allowed.json()["exists"] is True


def test_execution_readiness_recovers_after_explicit_config(
    runtime: RuntimeState,
) -> None:
    before = runtime.execution_report()
    assert runtime.executor_wired is True
    assert before["execution_ready"] is False
    assert before["default_worker_connection_ref"] is None

    report = initialize_minimal(
        runtime.store,
        runtime.connections,
        connection=ConnectionInit(
            id=CONNECTION_ID,
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            credential_ref=CREDENTIAL_REF,
        ),
        agent=AgentInit(
            id="developer",
            connection_ref=CONNECTION_ID,
            skill_refs=("implementation", "verification"),
            tool_refs=("view-file", "edit-file", "run-command"),
        ),
        tools=("view-file", "edit-file", "run-command"),
        skills={"implementation": "# Impl\n", "verification": "# Verify\n"},
        set_worker_default=True,
    )
    assert "connection:lg-primary" in report.created
    assert "agent:developer" in report.created

    missing_credential = runtime.execution_report()
    assert missing_credential["default_worker_connection_ref"] == CONNECTION_ID
    assert missing_credential["credential_configured"] is False
    assert missing_credential["execution_ready"] is False
    assert any("credential" in reason for reason in missing_credential["reasons"])

    runtime.connections.set_credential(CREDENTIAL_REF, "sk-not-a-real-key")
    ready = runtime.execution_report()
    assert ready["credential_configured"] is True
    assert ready["execution_ready"] is True
    assert ready["reasons"] == []

    connection_file = (
        runtime.settings.data_dir / "resources" / "connections" / f"{CONNECTION_ID}.md"
    )
    text = connection_file.read_text("utf-8")
    assert CREDENTIAL_REF in text
    assert "sk-not-a-real-key" not in text


def test_disabled_executor_is_reported_honestly(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
            wire_real_executor=False,
        )
    )
    assert state.executor_wired is False
    assert any("disabled" in warning for warning in state.warnings)
    report = state.execution_report()
    assert report["execution_ready"] is False
    assert any("not wired" in reason for reason in report["reasons"])


@pytest.fixture
async def disabled_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("t", "generated"),
            serve_frontend=False,
            wire_real_executor=False,
        )
    )
    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_disabled_executor_health_still_serves_instance(
    disabled_client: httpx.AsyncClient,
) -> None:
    health = await disabled_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["capabilities"]["sdk_adapter"] is False
    tasks = await disabled_client.get("/api/v1/tasks")
    assert tasks.status_code == 200
