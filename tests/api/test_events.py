"""Persistent event subscription: replay, dedupe, Last-Event-ID, disconnect."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import FastAPI

from lightgravity.store import new_id

from api_helpers import (
    AsgiEventStream,
    create_task,
    wait_for_phase,
    wire_program_reviewer,
)


async def test_sse_replays_from_cursor_and_dedupes(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    stream_id = new_id("task")
    for _ in range(3):
        app.state.store.append_event(
            stream_id, {"type": "error.recorded", "actor": "test", "payload": {}}
        )

    stream = AsgiEventStream(app)
    await stream.start("/api/v1/events/stream", query=f"cursor=v1:{stream_id}:0")
    assert stream.status == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    events = await stream.events(3)
    await stream.close()

    assert [event["id"] for event in events] == [
        f"v1:{stream_id}:1",
        f"v1:{stream_id}:2",
        f"v1:{stream_id}:3",
    ]
    assert all(event["event"] == "error.recorded" for event in events)

    # Last-Event-ID replays strictly after the acknowledged seq, no duplicates.
    replay = AsgiEventStream(app)
    await replay.start(
        "/api/v1/events/stream",
        headers={"Last-Event-ID": f"v1:{stream_id}:2"},
    )
    events = await replay.events(1)
    await replay.close()
    assert [event["id"] for event in events] == [f"v1:{stream_id}:3"]


async def test_sse_live_broadcast_and_disconnect_keeps_run_alive(
    run_app: FastAPI, run_api: httpx.AsyncClient, fake_executor: Any
) -> None:
    # Opt in to the deterministic machine-gate reviewer: this test is about SSE
    # disconnect not cancelling work, not about the independent-reviewer gate.
    wire_program_reviewer(run_app)
    fake_executor.gate = asyncio.Event()
    task_id = await create_task(run_api)
    await asyncio.wait_for(fake_executor.started.wait(), timeout=5)

    stream = AsgiEventStream(run_app)
    await stream.start("/api/v1/events/stream")
    for _ in range(200):
        if run_app.state.context.broker.subscriber_count:
            break
        await asyncio.sleep(0.01)
    assert run_app.state.context.broker.subscriber_count >= 1

    run_app.state.store.append_event(
        task_id, {"type": "error.recorded", "actor": "test", "payload": {"live": True}}
    )
    events = await stream.events(1)
    assert events and events[0]["event"] == "error.recorded"
    await stream.close()
    assert run_app.state.context.broker.subscriber_count == 0

    # The browser disconnected; the worker must still finish and trigger real
    # machine verification. This summary-only fake has no candidate evidence.
    fake_executor.gate.set()
    detail = await wait_for_phase(run_api, task_id, {"verifying"})
    snapshot = (await run_api.get(f"/api/v1/tasks/{task_id}/acceptance")).json()
    assert detail["run"]["state"] == "verifying"
    assert detail["acceptance"]["status"] == "pending"
    assert not snapshot["checks"]["satisfied"]
    assert snapshot["checks"]["results"][0]["status"] == "failed"


async def test_sse_invalid_cursor_errors(api: httpx.AsyncClient) -> None:
    async with api.stream(
        "GET", "/api/v1/events/stream", params={"cursor": "nope"}
    ) as response:
        assert response.status_code == 422
        body = await response.aread()
    assert b"config_invalid" in body
