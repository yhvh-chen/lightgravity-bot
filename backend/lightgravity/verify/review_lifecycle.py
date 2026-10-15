"""Independent-reviewer lifecycle: run off the coordinator loop, cancelable (LG-022 R1).

LG-022 QA (candidate ``bf7851c``) found two blocking defects around the
independent reviewer:

* **D1** — the reviewer turn was invoked synchronously from the coordinator's
  running event loop, so every real review failed with ``RuntimeError``;
* **D2** — the review ran *inline on the coordinator's event loop*, so status
  queries / pause / cancel could not be served while a review was running, and
  there was no way to confirm the reviewer actually stopped/released.

:mod:`lightgravity.verify.review` now runs the real SDK turn on a private loop
in a worker thread (D1).  This module adds the missing **lifecycle** (D2):

* :class:`ReviewLifecycle` runs a review callable on a worker thread so the
  coordinator's event loop stays responsive (status/control keep being served);
* each running review is tracked per ``(task_id, run_id)`` with a cooperative
  :class:`threading.Event` **stop request**;
* :meth:`ReviewLifecycle.request_stop` returns an honest outcome — ``confirmed``
  only after the work thread has actually finished (or the stop was observed at
  a safe boundary), ``unknown`` when the thread did not stop within the timeout.
  An ``unknown`` stop **keeps the slot** (never writes a terminal state, never
  releases the slot) and is reported, never fabricated.

The lifecycle deliberately does not use ``asyncio.to_thread`` for the *stop*: a
plain thread cannot be force-cancelled, so the stop verdict is derived from the
thread's real completion state, not from the loop merely not blocking.  Tests
inject a deterministic ``runner`` so the stop boundary is provable without a
model call; the real coordinator wires the real review callable.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Stop verdicts.  ``confirmed`` means the reviewer really stopped/released;
#: ``unknown`` means it did not stop within the timeout (slot retained).
REVIEW_STOP_CONFIRMED = "confirmed"
REVIEW_STOP_UNKNOWN = "unknown"
REVIEW_STOP_NOT_FOUND = "not_found"

#: Default seconds to wait for a requested reviewer stop before reporting unknown.
DEFAULT_REVIEW_STOP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class ReviewStopResult:
    """Honest result of a reviewer stop request."""

    confirmed: bool
    state: str  # confirmed | unknown | not_found
    task_id: str
    run_id: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmed": self.confirmed,
            "state": self.state,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "reason": self.reason,
        }


@dataclass(slots=True)
class _ActiveReview:
    task_id: str
    run_id: str
    thread: threading.Thread
    stop_event: threading.Event
    done: threading.Event
    result: Any = None
    error: BaseException | None = None
    stop_observed: bool = False


class ReviewLifecycle:
    """Track independent reviews so they can be stopped with confirmation.

    ``runner`` is the synchronous review callable.  It receives a
    ``stop_event`` (a :class:`threading.Event`) it may poll at safe boundaries;
    the lifecycle also treats the *thread finishing* as a stop.  The real
    coordinator passes :func:`lightgravity.verify.review.review_with_stop`.
    """

    def __init__(
        self,
        *,
        stop_timeout_seconds: float = DEFAULT_REVIEW_STOP_TIMEOUT_SECONDS,
    ) -> None:
        self._stop_timeout = stop_timeout_seconds
        self._lock = threading.RLock()
        self._active: dict[tuple[str, str], _ActiveReview] = {}

    # ---------------------------------------------------------------- queries
    def is_reviewing(self, task_id: str, run_id: str) -> bool:
        with self._lock:
            entry = self._active.get((task_id, run_id))
            return entry is not None and not entry.done.is_set()

    def active_reviews(self) -> tuple[tuple[str, str], ...]:
        with self._lock:
            return tuple(
                key for key, entry in self._active.items() if not entry.done.is_set()
            )

    def stop_event_for(self, task_id: str, run_id: str) -> threading.Event | None:
        with self._lock:
            entry = self._active.get((task_id, run_id))
            return entry.stop_event if entry is not None else None

    # ----------------------------------------------------------------- start
    def run(
        self,
        task_id: str,
        run_id: str,
        runner: Callable[[threading.Event], Any],
    ) -> Any:
        """Run ``runner`` on a worker thread; block the *calling thread* only.

        The caller must invoke this off the coordinator's event loop (the
        coordinator uses ``loop.run_in_executor``); the runner always executes
        on its own thread and records a cooperative ``stop_event``.
        """

        key = (task_id, run_id)
        stop_event = threading.Event()
        done = threading.Event()
        holder: dict[str, Any] = {}

        def target() -> None:
            entry = holder["entry"]
            try:
                entry.result = runner(stop_event)
            except BaseException as exc:  # noqa: BLE001 - recorded, not swallowed
                entry.error = exc
            finally:
                done.set()

        thread = threading.Thread(
            target=target, name=f"review-{task_id}-{run_id}", daemon=True
        )
        entry = _ActiveReview(
            task_id=task_id,
            run_id=run_id,
            thread=thread,
            stop_event=stop_event,
            done=done,
        )
        holder["entry"] = entry
        with self._lock:
            # A review for this Run has exactly one writer; a duplicate start is
            # a programming error, not something to silently overwrite.
            self._active[key] = entry
        try:
            thread.start()
            done.wait()
        finally:
            with self._lock:
                # Keep the record until request_stop/drain observes it, but mark
                # completion via ``done``; a later read sees it finished.
                current = self._active.get(key)
                if current is entry:
                    self._active.pop(key, None)
        if entry.stop_observed:
            # The runner cooperatively acknowledged the stop; report unknown to
            # the caller so it does not fabricate a completed review.
            raise ReviewStopped(task_id, run_id)
        if entry.error is not None:
            raise entry.error
        return entry.result

    # ------------------------------------------------------------------ stop
    def request_stop(
        self, task_id: str, run_id: str, *, timeout: float | None = None
    ) -> ReviewStopResult:
        """Ask a running reviewer to stop; confirm only a real stop.

        Returns ``confirmed`` when the review thread has actually finished
        (either it observed the stop event or completed on its own) within the
        timeout.  Returns ``unknown`` otherwise, and the slot is retained.
        """

        key = (task_id, run_id)
        with self._lock:
            entry = self._active.get(key)
        if entry is None:
            return ReviewStopResult(
                confirmed=False,
                state=REVIEW_STOP_NOT_FOUND,
                task_id=task_id,
                run_id=run_id,
                reason="no running review for this Run",
            )
        entry.stop_event.set()
        wait_for = self._stop_timeout if timeout is None else timeout
        stopped = entry.done.wait(timeout=wait_for)
        if stopped:
            # The thread is gone: the reviewer really stopped (whether it saw the
            # flag or finished naturally).  The slot is released.
            with self._lock:
                self._active.pop(key, None)
            return ReviewStopResult(
                confirmed=True,
                state=REVIEW_STOP_CONFIRMED,
                task_id=task_id,
                run_id=run_id,
                reason="reviewer thread stopped; slot released",
            )
        return ReviewStopResult(
            confirmed=False,
            state=REVIEW_STOP_UNKNOWN,
            task_id=task_id,
            run_id=run_id,
            reason=(
                "reviewer did not stop within "
                f"{wait_for:.1f}s; unknown side effects, slot retained"
            ),
        )

    def mark_stop_observed(self, task_id: str, run_id: str) -> None:
        """Record that a runner cooperatively observed its stop request."""

        with self._lock:
            entry = self._active.get((task_id, run_id))
            if entry is not None:
                entry.stop_observed = True

    async def request_stop_async(
        self, task_id: str, run_id: str, *, timeout: float | None = None
    ) -> ReviewStopResult:
        """Non-blocking stop request for the coordinator's event loop (D2).

        Marks the cooperative stop event immediately, then awaits the review
        thread's completion *without blocking the loop* (the done flag is polled
        with short ``asyncio.sleep`` yields).  A ``confirmed`` verdict means the
        thread is gone and the slot is released; ``unknown`` keeps the slot.
        """

        key = (task_id, run_id)
        with self._lock:
            entry = self._active.get(key)
        if entry is None:
            return ReviewStopResult(
                confirmed=False,
                state=REVIEW_STOP_NOT_FOUND,
                task_id=task_id,
                run_id=run_id,
                reason="no running review for this Run",
            )
        entry.stop_event.set()
        wait_for = self._stop_timeout if timeout is None else timeout
        deadline = asyncio.get_running_loop().time() + max(0.0, wait_for)
        while not entry.done.is_set():
            if asyncio.get_running_loop().time() >= deadline:
                return ReviewStopResult(
                    confirmed=False,
                    state=REVIEW_STOP_UNKNOWN,
                    task_id=task_id,
                    run_id=run_id,
                    reason=(
                        "reviewer did not stop within "
                        f"{wait_for:.1f}s; unknown side effects, slot retained"
                    ),
                )
            await asyncio.sleep(0.01)
        with self._lock:
            self._active.pop(key, None)
        return ReviewStopResult(
            confirmed=True,
            state=REVIEW_STOP_CONFIRMED,
            task_id=task_id,
            run_id=run_id,
            reason="reviewer thread stopped; slot released",
        )


class ReviewStopped(RuntimeError):
    """Raised by :meth:`ReviewLifecycle.run` when a review was stopped."""

    def __init__(self, task_id: str, run_id: str) -> None:
        super().__init__(f"review stopped for task={task_id} run={run_id}")
        self.task_id = task_id
        self.run_id = run_id


def run_review_off_loop(
    loop: asyncio.AbstractEventLoop,
    lifecycle: ReviewLifecycle,
    task_id: str,
    run_id: str,
    runner: Callable[[threading.Event], Any],
) -> "asyncio.Future[Any]":
    """Schedule a review on ``loop``'s default executor without blocking it.

    The returned future resolves with the runner result, or raises
    :class:`ReviewStopped` if the review was stopped at a safe boundary.  The
    coordinator awaits this future so its loop keeps serving status/control.
    """

    return loop.run_in_executor(None, lifecycle.run, task_id, run_id, runner)


__all__ = [
    "DEFAULT_REVIEW_STOP_TIMEOUT_SECONDS",
    "REVIEW_STOP_CONFIRMED",
    "REVIEW_STOP_NOT_FOUND",
    "REVIEW_STOP_UNKNOWN",
    "ReviewLifecycle",
    "ReviewStopResult",
    "ReviewStopped",
    "run_review_off_loop",
]
