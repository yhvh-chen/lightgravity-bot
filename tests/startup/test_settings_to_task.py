"""Settings-only first-run integration: configure -> default -> new Task entry.

This is a real end-to-end local integration (fast, no network, no real model
call): a fresh runtime seeds one worker, the operator uses only the Settings
API to create a connection, store its credential, run a static test and set the
worker default, and a newly created Task then reaches the executor.  The
upstream is deliberately unauthorized so the failure is honest and fast; the
point of this test is that the *entry* exists and is pinned to the default
connection, not that the model succeeded (that is LG-010's real closure).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.minimal import DEFAULT_AGENT_ID
from lightgravity.runtime.token import RuntimeToken

from conftest import make_settings

TOKEN = "test-token-lg020-settings"
CONNECTION_ID = "lg-settings-conn"
CREDENTIAL_REF = "lg-test-key"
#: Loopback is not an authorized upstream host, so the executor fails fast
#: without any real network call while still exercising the whole entry.
BASE_URL = "http://127.0.0.1:9/v1"


def _headers() -> dict[str, str]:
    return {"X-LG-Token": TOKEN}


async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 8.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()


def _members(state: RuntimeState) -> list[dict[str, Any]]:
    base = state.settings.data_dir / "members"
    if not base.is_dir():
        return []
    return [dict(state.store.read("member", child.stem).entity) for child in sorted(base.glob("*.md"))]


def _subtasks(state: RuntimeState) -> list[str]:
    base = state.settings.data_dir / "subtasks"
    if not base.is_dir():
        return []
    return [child.name for child in sorted(base.iterdir()) if child.is_dir()]


async def test_settings_only_path_reaches_a_pinned_execution_entry(
    tmp_path: Path, monkeypatch: Any
) -> None:
    settings: Settings = make_settings(tmp_path)
    (settings.workspace_root / "ws").mkdir(parents=True, exist_ok=True)
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken(TOKEN, "generated"),
            serve_frontend=False,
        )
    )

    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. First start: history + settings readable, execution unavailable.
            assert (await client.get("/api/v1/tasks")).status_code == 200
            assert (await client.get("/api/v1/settings")).status_code == 200
            before = state.execution_report()
            assert before["execution_ready"] is False
            assert DEFAULT_AGENT_ID in before["agent_refs"]  # seeded automatically

            # 2. Settings: create connection, store credential, static test, default.
            created = await client.post(
                "/api/v1/settings/connections",
                headers=_headers(),
                json={
                    "id": CONNECTION_ID,
                    "backend": "openai-compat",
                    "model": "deepseek-v4-flash",
                    "base_url": BASE_URL,
                    "credential_ref": CREDENTIAL_REF,
                },
            )
            assert created.status_code == 201, created.text
            assert CREDENTIAL_REF in created.text
            assert "test-not-real" not in created.text

            credential = await client.put(
                f"/api/v1/settings/credentials/{CREDENTIAL_REF}",
                headers=_headers(),
                json={"action": "set", "value": "test-not-real"},
            )
            assert credential.status_code == 200
            assert credential.json()["configured"] is True
            assert "test-not-real" not in credential.text

            tested = await client.post(
                f"/api/v1/settings/connections/{CONNECTION_ID}/test",
                headers=_headers(),
                json={"allow_network": False},
            )
            assert tested.status_code == 200, tested.text
            assert tested.json()["layers"]  # separate layers, no fake online claim

            settings_view = (await client.get("/api/v1/settings")).json()
            revision = settings_view.get("revision") if settings_view.get("exists") else None
            patched = await client.patch(
                "/api/v1/settings",
                headers=_headers(),
                json={
                    "expected_revision": revision,
                    "default_worker_connection_ref": CONNECTION_ID,
                },
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["default_worker_connection_ref"] == CONNECTION_ID
            assert state.execution_report()["execution_ready"] is True

            # 3. A new Task reaches the executor via the seeded agent + default.
            created_task = await client.post(
                "/api/v1/tasks",
                json={
                    "request_id": "lg020-settings-req",
                    "title": "settings-only entry",
                    "objective": "Reply with a one-line acknowledgement.",
                    "acceptance_criteria": ["a one-line acknowledgement is returned"],
                    "workspace_ref": "ws",
                },
            )
            assert created_task.status_code == 200, created_task.text
            task_id = created_task.json()["task_id"]

            reached = await _wait_for(
                lambda: bool(_subtasks(state)) and bool(_members(state))
            )
            assert reached, "the Task never reached the execution entry"

            members = _members(state)
            assert [member["role_ref"] for member in members] == [DEFAULT_AGENT_ID]
            member = members[0]
            assert member["connection_ref"] == CONNECTION_ID
            assert member["connection_pin"]["connection_id"] == CONNECTION_ID
            assert member["connection_pin"]["credential_ref"] == CREDENTIAL_REF
            # No secret value is ever persisted on the Member.
            assert "test-not-real" not in str(member)

            task = state.store.read("task", task_id).entity
            assert task["active_run"]
            assert _subtasks(state)
