"""LG-022 R1 regression: independent-reviewer lifecycle off the coordinator loop.

These are unit/regression tests over deterministic doubles (no network/model).

They pin the two blocking LG-022 QA defects:

* **D1** — the reviewer turn must be callable from inside a *running* event
  loop.  ``run_review_turn``'s synchronous entry point must not raise
  ``RuntimeError: asyncio.run() cannot be called from a running event loop``;
* **D2** — a review runs off the coordinator's loop (status/control keep being
  served) and can be stopped with an honest ``confirmed`` / ``unknown``
  verdict.  ``unknown`` keeps the slot; a stopped review never fabricates an
  outcome.

The real DeepSeek path is **not** exercised here and is left to the independent
re-verification owner.
"""

from __future__ import annotations

import asyncio
import threading

from lightgravity.verify.review import _run_coro_sync
from lightgravity.verify.review_lifecycle import (
    REVIEW_STOP_CONFIRMED,
    REVIEW_STOP_NOT_FOUND,
    REVIEW_STOP_UNKNOWN,
    ReviewLifecycle,
    ReviewStopped,
    run_review_off_loop,
)


def test_d1_run_coro_sync_inside_running_loop() -> None:
    """The exact D1 failure: a coroutine run from a running loop must not raise."""

    async def work() -> str:
        await asyncio.sleep(0.001)
        return "ok"

    async def main() -> str:
        # This is the shape of the real coordinator call path.
        return _run_coro_sync(work())

    assert asyncio.run(main()) == "ok"


def test_d1_run_coro_sync_outside_loop() -> None:
    async def work() -> str:
        return "plain"

    assert _run_coro_sync(work()) == "plain"


def test_d2_review_runs_off_loop_and_loop_stays_responsive() -> None:
    """While a review runs, the loop must keep scheduling other coroutines."""

    release = threading.Event()

    def runner(stop_event: threading.Event):
        release.wait(timeout=5.0)
        return "reviewed"

    async def main() -> tuple[str, int, Any]:
        lifecycle = ReviewLifecycle(stop_timeout_seconds=2.0)
        loop = asyncio.get_running_loop()
        future = run_review_off_loop(loop, lifecycle, "task_1", "run_1", runner)
        # The loop is free to do other work while the review runs on its thread.
        ticks = 0
        while not future.done() and ticks < 50:
            await asyncio.sleep(0.01)
            ticks += 1
        release.set()
        result = await future
        return result, ticks, lifecycle.is_reviewing("task_1", "run_1")

    result, ticks, reviewing = asyncio.run(main())
    assert result == "reviewed"
    assert ticks > 0  # the loop really was served during the review
    assert reviewing is False  # released after completion


def test_d2_stop_confirmed_releases_slot() -> None:
    """A cooperative runner observes the stop and the stop is confirmed."""

    lifecycle = ReviewLifecycle(stop_timeout_seconds=3.0)

    def runner(stop_event: threading.Event):
        # Wait until stopped, then acknowledge at a safe boundary.
        stop_event.wait(timeout=5.0)
        raise ReviewStopped("task_1", "run_1")

    async def main() -> tuple[Any, bool]:
        loop = asyncio.get_running_loop()
        future = run_review_off_loop(loop, lifecycle, "task_1", "run_1", runner)
        # Give the executor thread a moment to register the review.
        for _ in range(100):
            if lifecycle.is_reviewing("task_1", "run_1"):
                break
            await asyncio.sleep(0.005)
        assert lifecycle.is_reviewing("task_1", "run_1") is True
        stop = await lifecycle.request_stop_async("task_1", "run_1")
        try:
            await future
        except ReviewStopped:
            pass
        return stop, lifecycle.is_reviewing("task_1", "run_1")

    stop, reviewing = asyncio.run(main())
    assert stop.confirmed is True
    assert stop.state == REVIEW_STOP_CONFIRMED
    assert reviewing is False


def test_d2_stop_unknown_keeps_slot() -> None:
    """An unresponsive runner yields ``unknown`` and keeps the slot."""

    release = threading.Event()
    lifecycle = ReviewLifecycle(stop_timeout_seconds=0.2)

    def runner(stop_event: threading.Event):
        # Deliberately ignores the stop event until released.
        release.wait(timeout=5.0)
        return "late"

    async def main() -> tuple[Any, bool]:
        loop = asyncio.get_running_loop()
        future = run_review_off_loop(loop, lifecycle, "task_1", "run_1", runner)
        for _ in range(100):
            if lifecycle.is_reviewing("task_1", "run_1"):
                break
            await asyncio.sleep(0.005)
        stop = await lifecycle.request_stop_async("task_1", "run_1")
        reviewing = lifecycle.is_reviewing("task_1", "run_1")
        release.set()
        await future
        return stop, reviewing

    stop, reviewing = asyncio.run(main())
    assert stop.confirmed is False
    assert stop.state == REVIEW_STOP_UNKNOWN
    assert reviewing is True  # slot retained, terminal state not written


def test_d2_stop_not_found_when_no_review() -> None:
    lifecycle = ReviewLifecycle()

    async def main():
        return await lifecycle.request_stop_async("task_1", "run_1")

    stop = asyncio.run(main())
    assert stop.confirmed is False
    assert stop.state == REVIEW_STOP_NOT_FOUND
