"""An established SSE stream dies when the team session is revoked (LG-050)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from lightgravity.api import events as events_module


class _FakeSubscription:
    def __init__(self) -> None:
        self.closed = False

    async def receive(self, timeout: float) -> Any:
        await asyncio.sleep(0.005)
        raise TimeoutError

    def close(self) -> None:
        self.closed = True


class _FakeStore:
    def read_events(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _FakeTeam:
    def __init__(self) -> None:
        self.valid = True
        self.revoked: list[str | None] = []

    def resolve(self, session_id: str | None) -> Any | None:
        if self.valid:
            return SimpleNamespace(username="alice", role="member")
        return None


async def test_sse_stream_ends_when_session_is_revoked(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(events_module, "_SESSION_CHECK_SECONDS", 0.02)
    team = _FakeTeam()
    subscription = _FakeSubscription()
    ctx = SimpleNamespace(
        broker=SimpleNamespace(subscribe=lambda: subscription),
        store=_FakeStore(),
        team=team,
    )

    async def consume() -> None:
        async for _chunk in events_module._event_source(ctx, None, "sid"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    assert not task.done()  # still open while the session is valid
    team.valid = False
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done()
    assert subscription.closed is True
