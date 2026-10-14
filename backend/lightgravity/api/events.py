"""SSE event subscription (LG-012, docs/08 §4.4).

``GET /events/stream`` is a *subscription*, never a control channel.  On connect
the handler subscribes to the in-process broker **first**, then replays the
persisted JSONL from the requested cursor, then streams live records while
deduplicating by ``(stream_id, seq)``.  A client disconnect only cancels this
generator; the coordinator's background worker is untouched.

Cursor sources: ``?cursor=v1:<stream_id>:<seq>`` or the ``Last-Event-ID``
header (standard EventSource reconnect).  With a cursor the stream is scoped to
that stream id, which is what makes gap-free replay well defined.  Without a
cursor the client receives only new events from the moment of subscription.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from .context import ApiContext, get_context
from .eventbus import format_sse, parse_stream_cursor

#: Keep-alive comment interval so proxies do not drop an idle subscription.
_HEARTBEAT_SECONDS = 15.0
_REPLAY_PAGE = 1000


async def _event_source(
    ctx: ApiContext, parsed: tuple[str, int] | None
) -> AsyncIterator[str]:
    stream_filter = parsed[0] if parsed is not None else None
    last_seq = parsed[1] if parsed is not None else 0

    subscription = ctx.broker.subscribe()
    try:
        if stream_filter is not None:
            while True:
                records = ctx.store.read_events(
                    stream_filter, after_seq=last_seq, limit=_REPLAY_PAGE
                )
                if not records:
                    break
                for record in records:
                    last_seq = max(last_seq, record.seq)
                    yield format_sse(record)
                if len(records) < _REPLAY_PAGE:
                    break
        while True:
            try:
                live_record = await subscription.receive(timeout=_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if live_record is None:
                return
            if stream_filter is not None:
                if live_record.stream_id != stream_filter or live_record.seq <= last_seq:
                    continue
                last_seq = live_record.seq
            yield format_sse(live_record)
    finally:
        subscription.close()


def build_events_router() -> APIRouter:
    router = APIRouter(tags=["events"])

    @router.get("/events/stream")
    async def event_stream(
        ctx: Annotated[ApiContext, Depends(get_context)],
        cursor: Annotated[str | None, Query()] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        # Parse before returning so an invalid cursor yields a real 422 error
        # envelope instead of a half-started stream.
        parsed = parse_stream_cursor(cursor or last_event_id)
        return StreamingResponse(
            _event_source(ctx, parsed),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router


__all__ = ["build_events_router"]
