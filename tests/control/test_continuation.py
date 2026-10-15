"""LG-016 cross-Run native SDK session continuation (docs/02, docs/04 §5, docs/08 §8).

These tests pin the *safety* contract: a new Run continues the same native SDK
conversation only for a run that provably stopped through a confirmed pause with
a clean native session record; an interrupted/unclean Run is never silently
continued; the first Run records a stable ``save_dir`` and creates a session.
They are unit tests over the coordinator seam, not real SDK calls (the bounded
real pause/resume path is recorded in the LG-016 implementation report).
"""

from __future__ import annotations

import asyncio
from typing import Any

from lightgravity.adapter import CancelResult
from lightgravity.coordinator import Coordinator, RunController
from lightgravity.coordinator.continuation import (
    CONTINUATION_CONFIG_VERSION,
    plan_continuation,
)
from lightgravity.coordinator.dispatcher import DispatchContext, DispatchOutcome
from lightgravity.contracts import TaskPhase
from lightgravity.store import FileStore

from coordinator_helpers import raw_task, wait_for_phase


class SessionDispatcher:
    """Emits a real session id + native conversation so continuation is testable.

    It blocks in ``executing`` until either the dispatcher is released or a
    cancel is confirmed, mirroring :class:`ControllableDispatcher` used by the
    other LG-016 tests.  It records every :class:`DispatchContext` it receives so
    a test can assert what a resumed Run was actually told to do.
    """

    name = "session-dispatcher"

    def __init__(
        self,
        *,
        session_id: str = "sess_1",
        conversation_id: str = "conv-abcdefghijklmnopqrstuvwxyz012345",
        session_state: str = "created",
    ) -> None:
        self.session_id = session_id
        self.conversation_id = conversation_id
        #: ``state`` reported on the session_started event; ``resumed`` mimics
        #: the adapter attaching to an existing native conversation.
        self.session_state = session_state
        self.contexts: list[DispatchContext] = []
        self.started = asyncio.Event()
        self._blocker = asyncio.Event()

    async def dispatch(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: Any,
    ) -> DispatchOutcome:
        self.contexts.append(context)
        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        result = emit(
            {
                "type": "adapter.session_started",
                "session": {
                    "session_id": self.session_id,
                    "conversation_id": self.conversation_id,
                    "save_dir": context.save_dir,
                    "state": self.session_state,
                },
            }
        )
        if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
            await result
        self.started.set()
        await self._blocker.wait()
        return DispatchOutcome(state="succeeded", summary="session dispatcher")

    async def cancel(self, task_id: str, run_id: str) -> CancelResult:
        self._blocker.set()
        return CancelResult(confirmed=True, state="cancelled", reason="stop confirmed")


def _make(store: FileStore, dispatcher: SessionDispatcher) -> Coordinator:
    return Coordinator(store, dispatcher=dispatcher)


def _runs(store: FileStore, task_id: str) -> list[dict[str, Any]]:
    ensure = getattr(store, "_ensure_index", None)
    if callable(ensure):
        ensure()
    entries = getattr(store, "_entries", {}) or {}
    return [
        entry.data
        for (kind, _), entry in entries.items()
        if kind == "run" and entry.data.get("task_ref") == task_id
    ]


# --------------------------------------------------------------- pure planner
def _paused_run(**overrides: Any) -> dict[str, Any]:
    run: dict[str, Any] = {
        "state": "paused",
        "cleanup": {"status": "done"},
        "continuation": {
            "conversation_id": "conv-abcdefghijklmnopqrstuvwxyz012345",
            "save_dir": "/data/native-sessions/task_1",
            "continuation_mode": "create_only",
            "config_version": CONTINUATION_CONFIG_VERSION,
        },
    }
    run.update(overrides)
    return run


def test_plan_resume_for_clean_paused_run() -> None:
    decision = plan_continuation(
        {"phase": TaskPhase.PAUSED.value}, _paused_run(), "run_1"
    )
    assert decision.kind == "resume"
    assert decision.identity is not None
    assert decision.identity.conversation_id.startswith("conv-")
    assert decision.identity.save_dir.endswith("task_1")
    assert decision.source_run_id == "run_1"


def test_plan_recovery_required_when_cleanup_not_done() -> None:
    run = _paused_run(cleanup={"status": "pending"})
    decision = plan_continuation({"phase": TaskPhase.PAUSED.value}, run, "run_1")
    assert decision.kind == "recovery_required"
    assert decision.identity is None


def test_plan_recovery_required_for_interrupted_phase() -> None:
    decision = plan_continuation(
        {"phase": TaskPhase.RECOVERY_REQUIRED.value}, _paused_run(), "run_1"
    )
    assert decision.kind == "recovery_required"


def test_plan_fresh_for_failed_run_without_identity() -> None:
    run = {"state": "failed", "cleanup": {"status": "pending"}}
    decision = plan_continuation(
        {"phase": TaskPhase.FAILED.value}, run, "run_1"
    )
    assert decision.kind == "fresh"


def test_plan_fresh_when_paused_but_no_native_identity() -> None:
    run = {"state": "paused", "cleanup": {"status": "done"}}
    decision = plan_continuation({"phase": TaskPhase.PAUSED.value}, run, "run_1")
    # A clean pause with no native session continues the Task, but creates a new
    # session rather than pretending to resume.
    assert decision.kind == "fresh"


def test_plan_fresh_without_source_run() -> None:
    decision = plan_continuation({"phase": TaskPhase.QUEUED.value}, None, None)
    assert decision.kind == "fresh"


# ------------------------------------------------------------------ e2e seam
async def test_first_run_records_stable_save_dir_and_creates_session(
    store: FileStore,
) -> None:
    dispatcher = SessionDispatcher(session_state="created")
    coordinator = _make(store, dispatcher)
    coordinator.start()
    task_id = coordinator.create_task("req-1", "T", "do").task_id
    assert task_id is not None
    await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
    await wait_for_phase(coordinator, task_id, {"executing"})
    try:
        context = dispatcher.contexts[0]
        # The coordinator supplies one stable native session store for the Task.
        assert context.save_dir is not None
        assert context.save_dir.endswith(f"native-sessions/{task_id}")
        assert context.conversation_id is None
        assert context.continuation_mode is None
        active = store.read("task", task_id).entity["active_run"]
        run = store.read("run", active).entity
        record = run["continuation"]
        assert record["conversation_id"].startswith("conv-")
        assert record["save_dir"] == context.save_dir
        assert record["decision"] == "fresh"
        assert record["config_version"] == CONTINUATION_CONFIG_VERSION
    finally:
        dispatcher._blocker.set()
        await coordinator.stop()


async def test_pause_then_resume_carries_native_conversation(store: FileStore) -> None:
    """A confirmed pause + resume continues the same native conversation.

    The second Run must be told ``continuation_mode == 'resume'`` with the first
    Run's conversation id and the *same* save_dir — i.e. the objective is not
    replayed into a brand-new session.
    """

    dispatcher = SessionDispatcher(session_id="sess_a", session_state="created")
    coordinator = _make(store, dispatcher)
    coordinator.start()
    task_id = coordinator.create_task("req-2", "T", "do").task_id
    assert task_id is not None
    await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
    await wait_for_phase(coordinator, task_id, {"executing"})
    try:
        pause = await coordinator.request_control(
            task_id, "pause", request_id="req-pause"
        )
        assert pause.data["confirmed"] is True
        first_run = store.read("task", task_id).entity["active_run"]
        first_record = store.read("run", first_run).entity["continuation"]
        assert first_record["decision"] == "fresh"

        # The blocker stays set (the pause already released it), so the resumed
        # Run proceeds and the loop opens a new Run; it emits its own
        # session_started event.  We only reset the started flag to observe it.
        dispatcher.started.clear()
        dispatcher.session_id = "sess_b"
        dispatcher.session_state = "resumed"
        dispatcher.conversation_id = first_record["conversation_id"]

        resume = await coordinator.request_control(
            task_id, "resume", request_id="req-resume"
        )
        assert resume.data["confirmed"] is True
        await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
        # The dispatcher returns immediately (the blocker is already set), so the
        # Run proceeds through executing/verifying; the context is what matters.
        for _ in range(100):
            if len(dispatcher.contexts) >= 2:
                break
            await asyncio.sleep(0.02)

        assert len(dispatcher.contexts) >= 2
        resumed_ctx = dispatcher.contexts[-1]
        assert resumed_ctx.conversation_id == first_record["conversation_id"]
        assert resumed_ctx.save_dir == first_record["save_dir"]
        assert resumed_ctx.continuation_mode == "resume"

        second_run = store.read("task", task_id).entity["active_run"]
        assert second_run != first_run
        second_record = store.read("run", second_run).entity["continuation"]
        assert second_record["decision"] == "resume"
        assert second_record["source_run_id"] == first_run
    finally:
        dispatcher._blocker.set()
        await coordinator.stop()


async def test_interrupted_run_is_not_auto_continued(store: FileStore) -> None:
    """A Run interrupted with unknown side effects must not be silently resumed.

    ``_open_run`` refuses to open a replay Run and raises, and the Task keeps its
    ``recovery_required`` phase instead of quietly re-executing the objective.
    """

    from lightgravity.coordinator.state import StateWriter
    from lightgravity.store import new_id

    task_id = raw_task(store, status="in-progress", phase="recovery_required")
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "executing",
            "plan_ref": "PLAN.md",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "continuation": {
                "conversation_id": "conv-abcdefghijklmnopqrstuvwxyz012345",
                "save_dir": "/data/native-sessions/x",
                "continuation_mode": "create_only",
                "config_version": CONTINUATION_CONFIG_VERSION,
            },
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="test",
        request_id=f"run:{run_id}",
        body="# Run\n",
    )
    StateWriter(store, actor="test").set_active_run(task_id, run_id)

    dispatcher = SessionDispatcher()
    coordinator = _make(store, dispatcher)
    task = store.read("task", task_id)
    try:
        try:
            coordinator._open_run(task)
        except Exception as exc:  # noqa: BLE001 - the refusal is the assertion
            assert "recovery" in str(exc).lower()
        else:  # pragma: no cover - must not happen
            raise AssertionError("interrupted Run was auto-continued")
        assert store.read("task", task_id).entity["phase"] == (
            TaskPhase.RECOVERY_REQUIRED.value
        )
        # No new Run was created as a silent replay.
        assert len(_runs(store, task_id)) == 1
    finally:
        await coordinator.stop()


class LateConversationDispatcher(SessionDispatcher):
    """Mimics the real SDK: the conversation id is only known after the turn.

    ``adapter.session_started`` reports ``conversation_id=None`` (the SDK assigns
    it during the exchange); the final ``ExecutorResult.session_ref`` carries the
    real native identity, exactly as proven by the bounded real-SDK probe.  The
    coordinator must persist that final identity so a later pause→resume can
    continue it.
    """

    async def dispatch(self, context, controller, emit):
        outcome = await super().dispatch(context, controller, emit)
        from lightgravity.adapter import ExecutionRef, ExecutorResult, SessionRef

        ref = SessionRef(
            session_id=f"{self.session_id}_final",
            conversation_id=self.conversation_id,
            state=self.session_state,
            save_dir=context.save_dir,
        )
        result = ExecutorResult(
            state="succeeded",
            summary="late conversation id",
            session_ref=ref,
            execution_ref=ExecutionRef(
                execution_id=f"exec_{context.run_id}",
                task_id=context.task_id,
                run_id=context.run_id,
            ),
        )
        return DispatchOutcome(
            state=outcome.state, summary=outcome.summary, result=result
        )


async def test_final_result_session_ref_is_persisted_for_continuation(
    store: FileStore,
) -> None:
    """The SDK-late native conversation id from the result is persisted.

    The ``session_started`` event cannot carry the conversation id (it is only
    assigned after the exchange), so the coordinator must read the final
    ``ExecutorResult.session_ref``.  Otherwise a later resume would have no
    native identity to continue.
    """

    dispatcher = LateConversationDispatcher(
        session_id="sess_late", session_state="created"
    )
    # The session_started event reports no conversation id.
    dispatcher.conversation_id = None  # type: ignore[assignment]
    coordinator = _make(store, dispatcher)
    coordinator.start()
    task_id = coordinator.create_task("req-late", "T", "do").task_id
    assert task_id is not None
    await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
    try:
        # Restore the real id the SDK reports only in the final result, and
        # release the turn so _apply_outcome records the result session.
        dispatcher.conversation_id = "conv-late-abcdefghijklmnopqrstuvwxyz"
        dispatcher._blocker.set()
        for _ in range(200):
            run = store.read("run", store.read("task", task_id).entity["active_run"]).entity
            if run.get("continuation"):
                break
            await asyncio.sleep(0.02)
        record = run["continuation"]
        assert record["conversation_id"] == "conv-late-abcdefghijklmnopqrstuvwxyz"
        assert record["save_dir"] == dispatcher.contexts[0].save_dir
        assert "sess_late_final" in list(run["session_refs"])
    finally:
        await coordinator.stop()
