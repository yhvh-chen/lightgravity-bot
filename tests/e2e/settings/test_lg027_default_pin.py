"""LG-027 QA: default-connection change does not hot-swap an active Member.

Runs the real ``build_runtime`` assembly (FileStore + ConnectionService +
GraphDispatcher + real pin provider) and drives it through the real HTTP API.
All upstreams are unreachable loopback addresses, so the execution fails fast
and **no network/model call happens** — this test is about *config pinning*, not
model success.

It verifies the milestone acceptance: changing the default keeps an existing
Member on its pinned (old) connection, while a newly created Task/Run resolves
the new default.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.token import RuntimeToken

TOKEN = "lg027-pin-token"
CONN_A = "lg027-conn-a"
CONN_B = "lg027-conn-b"
REF_A = "lg027-ref-a"
REF_B = "lg027-ref-b"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


async def _wait_for(predicate: Callable[[], bool], *, timeout: float = 20.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


def _members(state: RuntimeState) -> list[dict[str, Any]]:
    base = state.settings.data_dir / "members"
    if not base.is_dir():
        return []
    return [dict(state.store.read("member", p.stem).entity) for p in sorted(base.glob("*.md"))]


async def _create_connection(
    client: httpx.AsyncClient, conn_id: str, ref: str, model: str
) -> None:
    response = await client.post(
        "/api/v1/settings/connections",
        headers={"X-LG-Token": TOKEN},
        json={
            "id": conn_id,
            "backend": "openai-compat",
            "model": model,
            "base_url": "http://127.0.0.1:9/v1",
            "credential_ref": ref,
        },
    )
    assert response.status_code == 201, response.text
    stored = await client.put(
        f"/api/v1/settings/credentials/{ref}",
        headers={"X-LG-Token": TOKEN},
        json={"action": "set", "value": f"fake-{ref}"},
    )
    assert stored.status_code == 200, stored.text


async def _new_task(client: httpx.AsyncClient, request_id: str) -> str:
    response = await client.post(
        "/api/v1/tasks",
        json={
            "request_id": request_id,
            "title": f"pin probe {request_id}",
            "objective": "Return OK.",
            "acceptance_criteria": ["OK is returned"],
            "workspace_ref": "ws",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["task_id"]


async def test_default_change_does_not_hot_swap_active_member(
    tmp_path: Path, monkeypatch: Any
) -> None:
    settings = _settings(tmp_path)
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
            await _create_connection(client, CONN_A, REF_A, "deepseek-v4-flash")
            await _create_connection(client, CONN_B, REF_B, "deepseek-reasoner")

            view = (await client.get("/api/v1/settings")).json()
            patched = await client.patch(
                "/api/v1/settings",
                headers={"X-LG-Token": TOKEN},
                json={
                    "expected_revision": view.get("revision") if view.get("exists") else None,
                    "default_worker_connection_ref": CONN_A,
                },
            )
            assert patched.status_code == 200, patched.text

            task_a = await _new_task(client, "lg027-pin-a")
            member_a = await _wait_for(lambda: bool(_members(state)))
            assert member_a
            first_member = _members(state)[0]
            assert first_member["connection_pin"]["connection_id"] == CONN_A
            run_a = state.store.read("task", task_a).entity["active_run"]

            # Operator switches the global default while the first Run exists.
            view = (await client.get("/api/v1/settings")).json()
            patched = await client.patch(
                "/api/v1/settings",
                headers={"X-LG-Token": TOKEN},
                json={
                    "expected_revision": view.get("revision"),
                    "default_worker_connection_ref": CONN_B,
                },
            )
            assert patched.status_code == 200, patched.text

            # The active Member keeps the old pin; its Run pin is unchanged.
            await asyncio.sleep(0.3)
            kept = _members(state)[0]
            assert kept["connection_pin"]["connection_id"] == CONN_A
            assert state.store.read("run", run_a).entity["connection_pin"]["connection_id"] == CONN_A

            # A new Task/Run resolves the *new* default.
            before = len(_members(state))
            task_b = await _new_task(client, "lg027-pin-b")
            added = await _wait_for(lambda: len(_members(state)) > before)
            assert added
            new_member = [m for m in _members(state) if m["connection_pin"]["connection_id"] == CONN_B]
            assert new_member, [m["connection_pin"]["connection_id"] for m in _members(state)]
            run_b = state.store.read("task", task_b).entity["active_run"]
            assert state.store.read("run", run_b).entity["connection_pin"]["connection_id"] == CONN_B
