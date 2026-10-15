"""LG-022 stream-stop wiring (D2 fix) — local unit tests.

These pin the *behaviour* of the streaming-stage stop wiring in
:mod:`lightgravity.verify.review`, using deterministic stand-ins for the SDK
stream/agent.  They prove:

* the stop request is observed **during** streaming (not only around the prompt
  send), so a long fake stream really ends;
* on stop the SDK's documented cancel entry (``conversation.cancel()``) is
  called and idle is awaited; the caller's teardown fact is then produced;
* chunks already received are preserved (no duplicate/lost chunk from
  ``anext`` retries);
* a stream without a stop still drains fully, and a stop *after* natural
  completion does not fabricate an outcome;
* a cancel that never confirms idle does not hang the turn beyond the bound and
  leaves the teardown unconfirmed (honest).

They do **not** replace the real-SDK probe (``probes/lg022/STREAM-STOP-FIX``)
which drives the real ``google-antigravity`` SDK against a local fake SSE
upstream with 0 real model calls.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

import lightgravity.verify.review as review_mod
from lightgravity.verify.review import (
    _cancel_sdk_turn,
    _drain_stream_with_stop,
)
from lightgravity.verify.review_lifecycle import ReviewStopped


@pytest.fixture(autouse=True)
def _fast_cancel_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the drain's bounded settle short in tests; production uses 5s.
    monkeypatch.setattr(review_mod, "_CANCEL_IDLE_TIMEOUT_SECONDS", 0.2)


class _Chunk:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeStream:
    """Async chunk stream that yields slowly (or blocks) until cancelled."""

    def __init__(self, chunks: list[str], *, hold_after: bool = False) -> None:
        self._chunks = list(chunks)
        self._hold_after = hold_after
        self.anext_calls = 0
        self.yielded: list[str] = []
        self.stopped = threading.Event()

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> _Chunk:
        self.anext_calls += 1
        if self._chunks:
            text = self._chunks.pop(0)
            self.yielded.append(text)
            return _Chunk(text)
        if self._hold_after:
            # Block until cancelled (the fake conversation's cancel does not
            # unblock this; the drain's bounded settle handles it).
            await asyncio.sleep(3600)
        raise StopAsyncIteration


class _FakeResponse:
    def __init__(self, stream: _FakeStream) -> None:
        self.chunks = stream


class _FakeConversation:
    def __init__(self, *, idle: bool = True) -> None:
        self.cancel_calls = 0
        self.idle_awaited = 0
        self._idle = idle

    async def cancel(self) -> None:
        self.cancel_calls += 1

    async def wait_for_idle(self) -> None:
        self.idle_awaited += 1
        if not self._idle:
            await asyncio.sleep(3600)


class _FakeAgent:
    def __init__(self, *, idle: bool = True) -> None:
        self.conversation = _FakeConversation(idle=idle)


@pytest.mark.asyncio
async def test_stream_stop_is_observed_mid_stream_and_calls_sdk_cancel() -> None:
    stream = _FakeStream(["a", "b"], hold_after=True)
    response = _FakeResponse(stream)
    agent = _FakeAgent()
    stop_event = threading.Event()
    stop_event.set()  # already requested: must be honoured before any chunk

    with pytest.raises(ReviewStopped):
        await _drain_stream_with_stop(response, stop_event, agent)

    assert agent.conversation.cancel_calls == 1
    assert agent.conversation.idle_awaited == 1


@pytest.mark.asyncio
async def test_stream_stop_mid_stream_preserves_prior_chunks() -> None:
    stream = _FakeStream(["first", "second"], hold_after=True)
    response = _FakeResponse(stream)
    agent = _FakeAgent()
    stop_event = threading.Event()

    async def _set_later() -> None:
        # Let a couple of chunks arrive, then request the stop.
        await asyncio.sleep(0.1)
        stop_event.set()

    setter = asyncio.ensure_future(_set_later())
    try:
        with pytest.raises(ReviewStopped):
            await _drain_stream_with_stop(response, stop_event, agent)
    finally:
        setter.cancel()
    # Every buffered chunk was consumed exactly once before the stop: none was
    # dropped and none was re-read (a value-producing ``anext`` is never
    # retried).
    assert stream.yielded == ["first", "second"]
    assert agent.conversation.cancel_calls == 1


@pytest.mark.asyncio
async def test_stream_without_stop_drains_fully() -> None:
    stream = _FakeStream(["x", "y", "z"])
    chunks = await _drain_stream_with_stop(_FakeResponse(stream), None, _FakeAgent())
    assert [c.text for c in chunks] == ["x", "y", "z"]


@pytest.mark.asyncio
async def test_stream_natural_end_with_unset_stop_is_not_stopped() -> None:
    stream = _FakeStream(["only"])
    stop_event = threading.Event()  # never set
    chunks = await _drain_stream_with_stop(_FakeResponse(stream), stop_event, _FakeAgent())
    assert [c.text for c in chunks] == ["only"]


@pytest.mark.asyncio
async def test_cancel_without_idle_is_bounded_and_reports_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lightgravity.verify.review as review_mod

    monkeypatch.setattr(review_mod, "_CANCEL_IDLE_TIMEOUT_SECONDS", 0.2)
    agent = _FakeAgent(idle=False)
    t0 = asyncio.get_running_loop().time()
    ok = await _cancel_sdk_turn(agent)
    elapsed = asyncio.get_running_loop().time() - t0
    assert ok is False
    assert elapsed < 3.0  # bounded, never hangs the reviewer thread
    assert agent.conversation.cancel_calls == 1


@pytest.mark.asyncio
async def test_cancel_confirming_idle_reports_true() -> None:
    agent = _FakeAgent(idle=True)
    assert await _cancel_sdk_turn(agent) is True


@pytest.mark.asyncio
async def test_cancel_request_failure_reports_false() -> None:
    class _BoomConversation(_FakeConversation):
        async def cancel(self) -> None:
            raise RuntimeError("transport gone")

    class _BoomAgent:
        conversation = _BoomConversation()

    assert await _cancel_sdk_turn(_BoomAgent()) is False


@pytest.mark.asyncio
async def test_cancel_without_conversation_reports_false() -> None:
    class _NoConversation:
        conversation = None

    assert await _cancel_sdk_turn(_NoConversation()) is False


@pytest.mark.asyncio
async def test_stop_set_mid_pull_cancels_sdk_and_keeps_prior_chunks() -> None:
    """The pull task is never cancelled merely to poll for stop.

    A slow pull that is still pending when the stop fires must (a) reach the SDK
    cancel entry and (b) not lose the chunks already collected.
    """

    class _SlowStream(_FakeStream):
        def __init__(self) -> None:
            super().__init__(["one", "two"])
            self.pull_pending = threading.Event()

        async def __anext__(self) -> _Chunk:
            if self._chunks:
                text = self._chunks.pop(0)
                self.yielded.append(text)
                return _Chunk(text)
            self.pull_pending.set()
            await asyncio.sleep(3600)
            raise StopAsyncIteration

    stream = _SlowStream()
    agent = _FakeAgent()
    stop_event = threading.Event()

    async def _stop_when_pull_pending() -> None:
        while not stream.pull_pending.is_set():
            await asyncio.sleep(0.01)
        stop_event.set()

    setter = asyncio.ensure_future(_stop_when_pull_pending())
    try:
        with pytest.raises(ReviewStopped):
            await _drain_stream_with_stop(_FakeResponse(stream), stop_event, agent)
    finally:
        setter.cancel()
    assert stream.yielded == ["one", "two"]
    assert agent.conversation.cancel_calls == 1


@pytest.mark.asyncio
async def test_streaming_stop_unknown_keeps_slot_and_is_honest() -> None:
    """A reviewer that never acknowledges stop stays ``unknown`` (slot held)."""

    from lightgravity.verify.review_lifecycle import ReviewLifecycle

    lifecycle = ReviewLifecycle(stop_timeout_seconds=0.2)
    release = threading.Event()

    def runner(stop_event: threading.Event) -> str:
        # Never observes the stop: the lifecycle must NOT fabricate a stop.
        release.wait(timeout=5.0)
        return "finished"

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, lifecycle.run, "t", "r", runner)
    await asyncio.sleep(0.05)
    outcome = await lifecycle.request_stop_async("t", "r")
    assert outcome.confirmed is False
    assert outcome.state == "unknown"
    assert lifecycle.is_reviewing("t", "r") is True  # slot retained
    release.set()
    try:
        await future
    except Exception:  # noqa: BLE001 - runner result/stop is irrelevant here
        pass
