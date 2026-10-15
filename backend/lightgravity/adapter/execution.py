"""Stable executor boundary types (docs/08 §8).

``ExecuteRequest`` is constructed by the coordinator (LG-007); ``ExecutorResult``
carries the actual outcome, artifacts, diff, checks, session and usage.  The
adapter returns these values and only *emits* events - it never writes control
state (task/run/member files), which stays with the coordinator/``Store``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .capabilities import AdapterCapabilities

#: The frozen outcome classification (docs/08 §8).
ExecutorState = str  # succeeded | failed | blocked | cancelled | budget_exhausted | timeout

#: A normalized adapter event; the coordinator maps ``type`` to a contract
#: ``EventType`` and persists it.  Never contains credential material.
NormalizedEvent = dict[str, Any]

#: ``emit`` accepts a sync or async sink.
EventSink = Callable[[NormalizedEvent], "Awaitable[None] | None"]


@dataclass(frozen=True, slots=True)
class ExecuteRequest:
    """One subtask execution attempt.

    The core fields are the frozen docs/08 §8 set.  ``agent_ref`` is an
    additive adapter-level field: it points at the LG-005 ``agent`` resource
    whose compiled, permission-bounded plan (connection, skills, tool ceiling,
    budget) the executor runs.  It is required until LG-007 wires an explicit
    agent reference through the contract.
    """

    task_id: str
    run_id: str
    subtask_id: str
    attempt: int = 1
    objective: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    instructions: str = ""
    upstream_artifact_refs: tuple[str, ...] = ()
    workspace_path: str = ""
    allowed_tools: tuple[str, ...] | None = None
    skill_refs: tuple[str, ...] = ()
    connection_ref: str | None = None
    timeout_seconds: float | None = None
    budget: Mapping[str, int] = field(default_factory=dict)
    # Adapter extension (see class docstring).
    agent_ref: str | None = None
    save_dir: str | None = None
    conversation_id: str | None = None
    #: Additive runtime continuation override (native SDK SessionContinuationMode
    #: value: ``resume``/``create_or_resume``/``create_only``).  The coordinator
    #: sets it to ``resume`` only for a provably safe continuation of a previous
    #: paused Run; ``None`` keeps the compiled session profile's behavior.
    continuation_mode: str | None = None
    response_schema: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "subtask_id": self.subtask_id,
            "attempt": self.attempt,
            "objective": self.objective,
            "acceptance_criteria": list(self.acceptance_criteria),
            "instructions": self.instructions,
            "upstream_artifact_refs": list(self.upstream_artifact_refs),
            "workspace_path": self.workspace_path,
            "allowed_tools": list(self.allowed_tools) if self.allowed_tools is not None else None,
            "skill_refs": list(self.skill_refs),
            "connection_ref": self.connection_ref,
            "timeout_seconds": self.timeout_seconds,
            "budget": dict(self.budget),
            "agent_ref": self.agent_ref,
            "save_dir": self.save_dir,
            "conversation_id": self.conversation_id,
            "continuation_mode": self.continuation_mode,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRef:
    execution_id: str
    task_id: str | None = None
    run_id: str | None = None
    subtask_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "subtask_id": self.subtask_id,
        }


@dataclass(frozen=True, slots=True)
class SessionRef:
    session_id: str
    conversation_id: str | None = None
    state: str = "created"  # created | resumed | create_or_resumed | closed
    save_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "state": self.state,
            "save_dir": self.save_dir,
        }


@dataclass(frozen=True, slots=True)
class Usage:
    """Actually-obtained usage; unavailable counters are listed in ``unknown``."""

    prompt_tokens: int | None = None
    candidates_tokens: int | None = None
    total_tokens: int | None = None
    thought_tokens: int | None = None
    cached_tokens: int | None = None
    unknown: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "candidates_tokens": self.candidates_tokens,
            "total_tokens": self.total_tokens,
            "thought_tokens": self.thought_tokens,
            "cached_tokens": self.cached_tokens,
            "unknown": list(self.unknown),
        }


@dataclass(frozen=True, slots=True)
class FailureInfo:
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class CheckRecord:
    """A machine check performed around/inside the run."""

    name: str
    status: str  # passed | failed | unknown
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ExecutorResult:
    """The structured outcome returned to the coordinator."""

    state: ExecutorState
    summary: str
    artifact_refs: tuple[str, ...] = ()
    diff_ref: str | None = None
    check_records: tuple[CheckRecord, ...] = ()
    session_ref: SessionRef | None = None
    failure: FailureInfo | None = None
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None
    stop_confirmed: bool | None = None
    execution_ref: ExecutionRef | None = None
    model: str | None = None
    upstream_model: str | None = None
    #: The unified diff text (also persisted through the artifact sink when set);
    #: an additive adapter field so callers can verify without a second read.
    diff: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "summary": self.summary,
            "artifact_refs": list(self.artifact_refs),
            "diff_ref": self.diff_ref,
            "check_records": [record.to_dict() for record in self.check_records],
            "session_ref": self.session_ref.to_dict() if self.session_ref else None,
            "failure": self.failure.to_dict() if self.failure else None,
            "usage": self.usage.to_dict(),
            "stop_reason": self.stop_reason,
            "stop_confirmed": self.stop_confirmed,
            "execution_ref": self.execution_ref.to_dict() if self.execution_ref else None,
            "model": self.model,
            "upstream_model": self.upstream_model,
            "diff": self.diff,
        }


@dataclass(frozen=True, slots=True)
class CancelResult:
    """Cancel outcome; ``confirmed`` is the only signal that a stop happened."""

    confirmed: bool
    state: str  # cancelled | unconfirmed | requested | not_found | completed
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"confirmed": self.confirmed, "state": self.state, "reason": self.reason}


@runtime_checkable
class ExecutorAdapter(Protocol):
    """docs/08 §8 ``ExecutorAdapter``."""

    name: str
    version: str

    def capabilities(self) -> AdapterCapabilities: ...

    async def execute(self, request: ExecuteRequest, emit: EventSink) -> ExecutorResult: ...

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult: ...

    async def close(self, session_ref: SessionRef) -> None: ...


__all__ = [
    "ExecutorState",
    "NormalizedEvent",
    "EventSink",
    "ExecuteRequest",
    "ExecutionRef",
    "SessionRef",
    "Usage",
    "FailureInfo",
    "CheckRecord",
    "ExecutorResult",
    "CancelResult",
    "ExecutorAdapter",
]
