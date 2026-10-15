"""Stable dispatcher seam for LG-008 (LG-007, docs/01 §4, docs/08 §8).

The coordinator owns the queue, the single execution slot and Task/Run
transitions.  Everything between "a Run was created" and "the executor
returned" is delegated to a :class:`Dispatcher`.  LG-007 ships
:class:`SingleSlotDispatcher`, a minimal one-Run dispatcher that calls the
injected :class:`~lightgravity.adapter.ExecutorAdapter`.  LG-008 will provide a
graph dispatcher (planner/recruiter/scheduler) behind the same protocol without
touching queue or lifecycle code.

A dispatcher only mutates control state through :class:`RunController`, which
writes through the ``Store``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from lightgravity.adapter import (
    AdapterCapabilities,
    CancelResult,
    ExecuteRequest,
    ExecutionRef,
    ExecutorAdapter,
    ExecutorResult,
    FailureInfo,
    SessionRef,
    adapter_capabilities,
)
from lightgravity.adapter.execution import EventSink
from lightgravity.contracts import TaskPhase

from .state import RunController

#: Adapter outcome states mapped to Task/Run phases by the coordinator.
OUTCOME_TO_RUN_STATE: dict[str, str] = {
    "succeeded": "verifying",
    "failed": "failed",
    "blocked": "failed",
    "cancelled": "cancelled",
    "budget_exhausted": "failed",
    "timeout": "failed",
    # A resume that cannot prove a completed write node is reusable fails closed
    # to an explicit recovery decision instead of replaying side effects (LG-016).
    "recovery_required": "recovery_required",
}

OUTCOME_TO_TASK_PHASE: dict[str, str] = {
    "succeeded": TaskPhase.VERIFYING,
    "failed": TaskPhase.FAILED,
    "blocked": TaskPhase.FAILED,
    "cancelled": TaskPhase.CANCELLED,
    "budget_exhausted": TaskPhase.FAILED,
    "timeout": TaskPhase.FAILED,
    "recovery_required": TaskPhase.RECOVERY_REQUIRED,
}


@dataclass(frozen=True, slots=True)
class DispatchContext:
    """Everything a dispatcher needs to build and run a Subtask/attempt."""

    task_id: str
    run_id: str
    attempt: int
    objective: str
    acceptance_criteria: tuple[str, ...] = ()
    instructions: str = ""
    workspace_path: str = ""
    allowed_tools: tuple[str, ...] | None = None
    skill_refs: tuple[str, ...] = ()
    agent_ref: str | None = None
    connection_ref: str | None = None
    budget: Mapping[str, int] = field(default_factory=dict)
    timeout_seconds: float | None = None
    save_dir: str | None = None
    conversation_id: str | None = None
    continuation_mode: str | None = None
    #: The previous stopped Run entity (non-secret) when this Run continues a
    #: confirmed pause.  GraphDispatcher reads ``node_sessions`` from it to give
    #: each node *its own* native conversation instead of a single run-level one
    #: (LG-016).  ``None`` for a fresh Run.
    prior_run: Mapping[str, Any] | None = None

    def to_execute_request(self) -> ExecuteRequest:
        """Build the frozen adapter request from this context."""

        return ExecuteRequest(
            task_id=self.task_id,
            run_id=self.run_id,
            subtask_id=f"subtask_{self.run_id}",
            attempt=self.attempt,
            objective=self.objective,
            acceptance_criteria=self.acceptance_criteria,
            instructions=self.instructions,
            workspace_path=self.workspace_path,
            allowed_tools=self.allowed_tools,
            skill_refs=self.skill_refs,
            connection_ref=self.connection_ref,
            timeout_seconds=self.timeout_seconds,
            budget=dict(self.budget),
            agent_ref=self.agent_ref,
            save_dir=self.save_dir,
            conversation_id=self.conversation_id,
            continuation_mode=self.continuation_mode,
        )


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """Normalized dispatcher result the coordinator applies to the Run."""

    state: str
    summary: str = ""
    result: ExecutorResult | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    model: str | None = None
    stop_confirmed: bool | None = None

    @property
    def run_state(self) -> str:
        return OUTCOME_TO_RUN_STATE.get(self.state, "failed")

    @property
    def task_phase(self) -> str:
        return OUTCOME_TO_TASK_PHASE.get(self.state, TaskPhase.FAILED)

    @property
    def is_terminal(self) -> bool:
        return self.run_state in {"failed", "cancelled"}


@runtime_checkable
class Dispatcher(Protocol):
    """LG-008's extension point.

    Implementations must not write TASK.md/RUN.md directly; use the supplied
    :class:`RunController`.
    """

    name: str

    async def dispatch(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: EventSink,
    ) -> DispatchOutcome: ...

    async def cancel(self, task_id: str, run_id: str) -> CancelResult: ...


class SingleSlotDispatcher:
    """Minimal one-Run dispatcher over an :class:`ExecutorAdapter`.

    It performs the legal ``planning → recruiting → executing`` Task walk for
    the single-agent first-version path and delegates the actual execution to
    the adapter.  It keeps no control state and does not verify results.

    In-flight executions are tracked as asyncio tasks so a control message can
    stop them without waiting for the code task to finish; ``cancel`` only
    reports ``confirmed=True`` after the execution task actually stopped.
    """

    name = "single-slot"

    def __init__(self, executor: ExecutorAdapter, *, cancel_timeout: float = 15.0) -> None:
        self._executor = executor
        self._cancel_timeout = cancel_timeout
        self._active: dict[str, ExecutionRef] = {}
        self._inflight: dict[str, "asyncio.Task[ExecutorResult]"] = {}
        self._explicit_cancel: set[str] = set()

    @property
    def executor(self) -> ExecutorAdapter:
        return self._executor

    async def dispatch(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: EventSink,
    ) -> DispatchOutcome:
        controller.set_task_phase(TaskPhase.RECRUITING, reason="single-slot dispatch")
        controller.set_run_state("recruiting")
        controller.set_task_phase(TaskPhase.EXECUTING, reason="single-slot dispatch")
        controller.set_run_state("executing")

        request = context.to_execute_request()
        run_id = context.run_id
        task: "asyncio.Task[ExecutorResult]" = asyncio.ensure_future(
            self._executor.execute(request, emit)
        )
        self._inflight[run_id] = task
        try:
            result = await task
        except asyncio.CancelledError:
            if run_id not in self._explicit_cancel:
                raise
            result = ExecutorResult(
                state="cancelled",
                summary="execution cancelled by coordinator control",
                stop_confirmed=True,
                execution_ref=ExecutionRef(
                    execution_id=f"exec_cancelled_{run_id}",
                    task_id=context.task_id,
                    run_id=run_id,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - convert a crash into a classified failure
            return DispatchOutcome(
                state="failed",
                summary=f"{type(exc).__name__}: {exc}",
                failure_code="internal_error",
                failure_message=str(exc),
            )
        finally:
            self._inflight.pop(run_id, None)
            self._explicit_cancel.discard(run_id)
        if result.execution_ref is not None:
            self._active[run_id] = result.execution_ref
        failure = result.failure
        return DispatchOutcome(
            state=result.state,
            summary=result.summary,
            result=result,
            failure_code=failure.code if failure else None,
            failure_message=failure.message if failure else None,
            model=result.model,
            stop_confirmed=result.stop_confirmed,
        )

    async def cancel(self, task_id: str, run_id: str) -> CancelResult:
        inflight = self._inflight.get(run_id)
        if inflight is None:
            ref = self._active.pop(run_id, None)
            if ref is None:
                return CancelResult(
                    confirmed=False,
                    state="not_found",
                    reason=f"no active execution for run {run_id!r}",
                )
            result = await self._executor.cancel(ref)
            if result.confirmed:
                self._active.pop(run_id, None)
            return result

        self._explicit_cancel.add(run_id)
        inflight.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(inflight), timeout=self._cancel_timeout)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            return CancelResult(
                confirmed=False,
                state="unconfirmed",
                reason="execution did not stop within the cancel timeout",
            )
        except Exception as exc:  # noqa: BLE001 - report, never fake a stop
            return CancelResult(
                confirmed=False,
                state="unconfirmed",
                reason=f"cancel path raised {type(exc).__name__}",
            )
        return CancelResult(confirmed=True, state="cancelled", reason="execution task stopped")


class UnavailableExecutor:
    """Placeholder adapter used before LG-010 wires the real executor.

    It never pretends to run: every attempt returns ``blocked`` with
    ``capability_unavailable`` so the coordinator writes a real failure instead
    of a fabricated success.
    """

    name = "unavailable"
    version = "0.0.0"

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(
        self, request: ExecuteRequest, emit: EventSink
    ) -> ExecutorResult:
        return ExecutorResult(
            state="blocked",
            summary="executor not wired (LG-010)",
            failure=FailureInfo(
                "capability_unavailable",
                "no executor adapter is configured in this coordinator",
            ),
            execution_ref=ExecutionRef(
                execution_id=f"exec_unavailable_{request.run_id}",
                task_id=request.task_id,
                run_id=request.run_id,
            ),
        )

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        return CancelResult(confirmed=True, state="cancelled", reason="no active execution")

    async def close(self, session_ref: SessionRef) -> None:
        return None


__all__ = [
    "OUTCOME_TO_RUN_STATE",
    "OUTCOME_TO_TASK_PHASE",
    "DispatchContext",
    "DispatchOutcome",
    "Dispatcher",
    "SingleSlotDispatcher",
    "UnavailableExecutor",
]
