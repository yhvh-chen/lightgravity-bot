"""Gated real DeepSeek check of the Settings-only execution entry (LG-020).

Skipped unless ``LG020_REAL_DEEPSEEK=1`` and ``DEEPSEEK_API_KEY`` are present.
It performs **at most one** real model call (hard cap forwarded to the executor)
and never prints or stores the credential.  The default test run does not consume
model calls; the deterministic ``test_settings_to_task`` test covers wiring.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.token import RuntimeToken

from conftest import make_settings

TOKEN = "real-deepseek-token-lg020"
CONNECTION_ID = "deepseek-live"
CREDENTIAL_REF = "deepseek-api-key"
BASE_URL = "https://api.deepseek.com/v1"

pytestmark = pytest.mark.skipif(
    os.environ.get("LG020_REAL_DEEPSEEK") != "1" or not os.environ.get("DEEPSEEK_API_KEY"),
    reason="set LG020_REAL_DEEPSEEK=1 with DEEPSEEK_API_KEY to run the real check",
)


async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 90.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


def _subtasks(state: RuntimeState) -> list[dict[str, Any]]:
    base = state.settings.data_dir / "subtasks"
    if not base.is_dir():
        return []
    return [dict(state.store.read("subtask", child.name).entity) for child in sorted(base.iterdir())]


async def test_real_deepseek_call_via_settings_default(tmp_path: Path) -> None:
    settings: Settings = make_settings(tmp_path)
    (settings.workspace_root / "ws").mkdir(parents=True, exist_ok=True)
    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken(TOKEN, "generated"),
            serve_frontend=False,
            max_proxy_calls=1,
            model_calls_cap=1,
        )
    )

    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"X-LG-Token": TOKEN}
            created = await client.post(
                "/api/v1/settings/connections",
                headers=headers,
                json={
                    "id": CONNECTION_ID,
                    "backend": "openai-compat",
                    "model": "deepseek-v4-flash",
                    "base_url": BASE_URL,
                    "credential_ref": CREDENTIAL_REF,
                },
            )
            assert created.status_code == 201, created.text
            assert os.environ["DEEPSEEK_API_KEY"] not in created.text

            view = (await client.get("/api/v1/settings")).json()
            patched = await client.patch(
                "/api/v1/settings",
                headers=headers,
                json={
                    "expected_revision": view.get("revision") if view.get("exists") else None,
                    "default_worker_connection_ref": CONNECTION_ID,
                },
            )
            assert patched.status_code == 200, patched.text
            report = state.execution_report()
            assert report["execution_ready"] is True, report

            task = await client.post(
                "/api/v1/tasks",
                json={
                    "request_id": "lg020-real-req",
                    "title": "real settings entry",
                    "objective": "Reply with exactly the word OK and nothing else.",
                    "acceptance_criteria": ["the reply contains OK"],
                    "workspace_ref": "ws",
                },
            )
            assert task.status_code == 200, task.text
            task_id = task.json()["task_id"]

            reached = await _wait_for(
                lambda: any(
                    item.get("acceptance", {}).get("status") in {"passed", "failed"}
                    for item in _subtasks(state)
                )
            )
            assert reached, "no subtask reached a terminal acceptance state"
            states = [item["state"] for item in _subtasks(state)]
            assert state.executor is not None
            run_ref = state.store.read("task", task_id).entity["active_run"]
            run = state.store.read("run", run_ref).entity
            print(
                "LG020-REAL-EVIDENCE "
                + str(
                    {
                        "model_calls_made": state.executor.model_calls_made,
                        "subtask_states": states,
                        "connection_pin": run.get("connection_pin"),
                        "run_state": run.get("state"),
                        "task_phase": state.store.read("task", task_id).entity["phase"],
                    }
                )
            )
            assert state.executor.model_calls_made == 1, state.executor.model_calls_made
            assert "passed" in states, states
            task_entity = state.store.read("task", task_id).entity
            assert task_entity["active_run"]
