"""Persisted-event fan-out, cursor helpers and a broadcasting Store proxy.

LG-012 (docs/08 §4.4/§5.1/§7).  Events are always written to the append-only
JSONL stream through the LG-004 ``Store`` **first**; only then is the in-process
broker notified.  That ordering is what makes SSE an optional subscription:
a browser that connects late replays from disk and a browser that disconnects
never affects the resident worker.

:class:`BroadcastingStore` is a thin Store proxy that delegates every read/write
and republishes the persisted :class:`~lightgravity.store.models.EventRecord`.
It is *not* a second source of truth: it holds no state.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Protocol, cast

from ..contracts import AppError, ErrorCode
from ..store import ClaimResult, EventRecord, IndexReport, MessageRecord, TaskSummary, Versioned
from ..store.protocol import Store

_DEFAULT_QUEUE_SIZE = 1024

#: Opaque cursor ``v1:<stream_id>:<seq>`` (docs/08 §4.4/§5.1).  ``.+`` is
#: greedy so a stream id containing ``:`` still parses (the trailing group is
#: digits only).
_CURSOR_RE = re.compile(r"^v1:(.+):([0-9]+)$")


class _BodyCapable(Protocol):
    """The concrete store accepts Markdown ``body``; the frozen Store protocol
    (docs/08 §7) does not model it.  Used only for forwarding in the proxy."""

    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        actor: str,
        request_id: str,
        body: str | None = None,
    ) -> Versioned: ...

    def write(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        expected_revision: int | None,
        actor: str,
        body: str | None = None,
    ) -> Versioned: ...


class Subscription:
    """One broker subscriber; ``receive`` supports a safe idle timeout.

    Timing out a ``Queue.get`` is safe (unlike cancelling an async generator's
    ``__anext__``), which is why the broker exposes this object instead of an
    async iterator.
    """

    def __init__(self, broker: EventBroker, queue: asyncio.Queue[EventRecord | None]) -> None:
        self._broker = broker
        self._queue = queue
        self._closed = False

    async def receive(self, timeout: float | None = None) -> EventRecord | None:
        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._broker.unsubscribe(self._queue)


class EventBroker:
    """In-process pub/sub for persisted events.

    ``publish`` is synchronous because events are persisted synchronously from
    the event loop (coordinator worker and API requests share the loop).  A
    subscriber that cannot keep up is closed instead of blocking writers; the
    client reconnects with its cursor and replays from disk, so no event is
    silently skipped at the protocol level.
    """

    def __init__(self, *, queue_size: int = _DEFAULT_QUEUE_SIZE) -> None:
        self._subscribers: set[asyncio.Queue[EventRecord | None]] = set()
        self._queue_size = queue_size

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, record: EventRecord) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                self._close_subscriber(queue)

    def _close_subscriber(self, queue: asyncio.Queue[EventRecord | None]) -> None:
        # Drop buffered records and wake the consumer so it can reconnect and
        # replay from its last acknowledged cursor.
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

    def subscribe(self) -> Subscription:
        queue: asyncio.Queue[EventRecord | None] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return Subscription(self, queue)

    def unsubscribe(self, queue: asyncio.Queue[EventRecord | None]) -> None:
        self._subscribers.discard(queue)


class BroadcastingStore:
    """Store proxy that republishes every persisted event to an :class:`EventBroker`."""

    def __init__(self, inner: Store, broker: EventBroker) -> None:
        self._inner = inner
        self._broker = broker

    @property
    def inner(self) -> Store:
        return self._inner

    @property
    def broker(self) -> EventBroker:
        return self._broker

    @property
    def data_dir(self) -> Path:
        return Path(getattr(self._inner, "data_dir"))

    @property
    def workspace_root(self) -> Path:
        return Path(getattr(self._inner, "workspace_root"))

    # ------------------------------------------------------------------ reads
    def read(self, kind: str, entity_id: str) -> Versioned:
        return self._inner.read(kind, entity_id)

    def read_events(
        self, stream_id: str, *, after_seq: int = 0, limit: int = 500
    ) -> list[EventRecord]:
        return self._inner.read_events(stream_id, after_seq=after_seq, limit=limit)

    def read_messages(
        self, task_id: str, *, after: str | None = None, limit: int = 200
    ) -> list[MessageRecord]:
        return self._inner.read_messages(task_id, after=after, limit=limit)

    def list_tasks(self) -> list[TaskSummary]:
        return self._inner.list_tasks()

    def rebuild_index(self) -> IndexReport:
        return self._inner.rebuild_index()

    def resolve_path(self, relative: str, *, write: bool) -> Path:
        return self._inner.resolve_path(relative, write=write)

    # ----------------------------------------------------------------- writes
    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        actor: str,
        request_id: str,
        body: str | None = None,
    ) -> Versioned:
        return cast(_BodyCapable, self._inner).create(
            kind, entity_id, content, actor=actor, request_id=request_id, body=body
        )

    def write(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        expected_revision: int | None,
        actor: str,
        body: str | None = None,
    ) -> Versioned:
        return cast(_BodyCapable, self._inner).write(
            kind,
            entity_id,
            content,
            expected_revision=expected_revision,
            actor=actor,
            body=body,
        )

    def append_event(self, stream_id: str, event: dict[str, Any]) -> EventRecord:
        record = self._inner.append_event(stream_id, event)
        self._broker.publish(record)
        return record

    def append_message(self, task_id: str, message: dict[str, Any]) -> MessageRecord:
        return self._inner.append_message(task_id, message)

    def claim(self, task_id: str, owner: str, *, lease_seconds: int) -> ClaimResult:
        return self._inner.claim(task_id, owner, lease_seconds=lease_seconds)

    def renew(self, task_id: str, owner: str, *, lease_seconds: int) -> bool:
        return self._inner.renew(task_id, owner, lease_seconds=lease_seconds)

    def release(self, task_id: str, owner: str) -> None:
        self._inner.release(task_id, owner)


# --------------------------------------------------------------------- cursors
def event_cursor(record: EventRecord) -> str:
    return f"v1:{record.stream_id}:{record.seq}"


def parse_stream_cursor(cursor: str | None) -> tuple[str, int] | None:
    """Parse ``v1:<stream_id>:<seq>`` into ``(stream_id, seq)``."""

    if not cursor:
        return None
    match = _CURSOR_RE.match(cursor)
    if match is None:
        raise AppError(
            ErrorCode.CONFIG_INVALID,
            f"invalid event cursor {cursor!r}",
            details={"cursor": cursor},
        )
    return match.group(1), int(match.group(2))


def format_sse(record: EventRecord) -> str:
    payload = json.dumps(record.event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event_cursor(record)}\nevent: {record.type}\ndata: {payload}\n\n"


__all__ = [
    "BroadcastingStore",
    "EventBroker",
    "Subscription",
    "event_cursor",
    "format_sse",
    "parse_stream_cursor",
]
