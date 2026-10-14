"""Resident coordinator service (LG-007).

Owns the message entry points, the Task queue, the single execution slot and
the Task/Run lifecycle.  The executor is reached through the stable
:class:`~lightgravity.coordinator.dispatcher.Dispatcher` seam (LG-008).

Design guarantees relevant to the acceptance conditions:

* Messages are persisted before any side effect and deduplicated by
  ``message_id`` (Task log) / ``request_id`` (control and task creation).
* Status queries and control calls never wait behind a running code task: the
  worker runs in a background asyncio task, not in the HTTP request.
* Browser disconnect does not cancel the worker; nothing in the request path
  owns the worker task.
* At most one Task holds the execution slot, and a Task can have at most one
  non-terminal Run (``active_run``).
* All control state is written through the ``Store``.
* Direct answers and bounded read-only requests never create a Task/Run and
  never receive write-capable tools.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, cast

from lightgravity.contracts import AppError, ErrorCode, EventType, TaskPhase, TaskStatus
from lightgravity.store import (
    EntityNotFound,
    LockConflict,
    Store,
    Versioned,
    new_id,
)
from lightgravity.store.locking import LockManager

from .classification import Classification, MessageIntent, classify_message
from .dispatcher import (
    DispatchContext,
    Dispatcher,
    DispatchOutcome,
    RunController,
    SingleSlotDispatcher,
    UnavailableExecutor,
)
from .logs import GlobalConversationLog, IdempotencyLog
from .queue import TaskQueue
from .state import ACTIVE_TASK_PHASES, TERMINAL_RUN_STATES, StateWriter

_ALLOWED_MESSAGE_ROLES = frozenset({"user", "assistant", "system", "tool"})


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class CoordinatorResult:
    """Normalized result of routing one message or control call."""

    kind: str
    reply: str = ""
    task_id: str | None = None
    run_id: str | None = None
    conversation_id: str | None = None
    queue_state: str | None = None
    candidates: tuple[dict[str, Any], ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "reply": self.reply,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "queue_state": self.queue_state,
            "candidates": list(self.candidates),
            "data": self.data,
        }


def _default_responder(content: str, classification: Classification) -> str:
    if classification.intent == MessageIntent.BOUNDED_READ:
        return (
            "已识别为有界只读请求：将在只读工具上限内处理，不创建 Task/Run，"
            "也不会获得写入或命令权限。"
        )
    return "我是 LightGravity Bot 常驻助手。请描述要交付的目标，或指定 Task 查询状态。"


def _task_body(objective: str, scope: str | None, acceptance: tuple[str, ...]) -> str:
    lines = ["# Task", "", "## 目标", "", objective.strip(), ""]
    if scope and scope.strip():
        lines += ["## 范围", "", scope.strip(), ""]
    if acceptance:
        lines += ["## 验收条件", ""]
        lines += [f"- {item}" for item in acceptance]
        lines += [""]
    return "\n".join(lines)


def _task_content(
    *,
    title: str,
    objective: str,
    acceptance: tuple[str, ...],
    project_ref: str | None,
    workspace_ref: str | None,
    agent_ref: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "objective": objective,
        "acceptance_criteria": list(acceptance),
        "status": TaskStatus.TODO.value,
        "phase": TaskPhase.INTAKE.value,
        "requirements_revision": 1,
        "project_ref": project_ref,
        "repository_ref": None,
        "workspace_ref": workspace_ref,
        "agent_ref": agent_ref,
        "depends_on": [],
        "active_run": None,
        "deliverable_revision": 0,
        "queue": {
            "state": "not_queued",
            "order": None,
            "queued_at": None,
            "owner": None,
            "lease_expires_at": None,
        },
        "acceptance": {
            "status": "pending",
            "requirements_revision": None,
            "deliverable_revision": None,
            "evidence_refs": [],
            "decided_at": None,
            "decision_ref": None,
        },
        "budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
        "archived": False,
    }


class _BodyStore(Protocol):
    """The concrete store accepts a Markdown body; the frozen Store protocol does
    not model it.  Cast at the two write sites that need TASK.md/RUN.md prose."""

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


class Coordinator:
    """First-version resident coordinator (single execution slot)."""

    def __init__(
        self,
        store: Store,
        *,
        dispatcher: Dispatcher | None = None,
        owner: str | None = None,
        lease_seconds: int = 300,
        poll_interval: float = 0.05,
        agent_ref: str | None = None,
        connection_ref: str | None = None,
        allowed_tools: tuple[str, ...] | None = None,
        timeout_seconds: float | None = None,
        budget: Mapping[str, int] | None = None,
        data_dir: Any = None,
        classifier: Callable[[str], Classification] | None = None,
        responder: Callable[[str, Classification], str] | None = None,
    ) -> None:
        self._store = store
        self._owner = owner or f"coordinator:{os.getpid()}"
        self._writer = StateWriter(store, actor=self._owner)
        self._queue = TaskQueue(store, self._writer)
        self._dispatcher = dispatcher or SingleSlotDispatcher(UnavailableExecutor())
        resolved_data_dir = data_dir if data_dir is not None else getattr(store, "data_dir", None)
        if resolved_data_dir is None:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "coordinator requires a store exposing data_dir (or an explicit data_dir)",
            )
        self._locks = LockManager(resolved_data_dir / "locks")
        self._global = GlobalConversationLog(resolved_data_dir, self._locks)
        self._idempotency = IdempotencyLog(resolved_data_dir, self._locks)
        self._lease_seconds = lease_seconds
        self._poll_interval = poll_interval
        self._agent_ref = agent_ref
        self._connection_ref = connection_ref
        self._allowed_tools = allowed_tools
        self._timeout_seconds = timeout_seconds
        self._budget: dict[str, int] = dict(budget or {})
        self._classifier = classifier or classify_message
        self._responder = responder or _default_responder
        self._loop_task: asyncio.Task[None] | None = None
        self._stopping = False
        #: Set while a dispatcher call is in flight (exposed for tests/monitoring).
        self._active_run_id: str | None = None

    # ------------------------------------------------------------- lifecycle
    @property
    def owner(self) -> str:
        return self._owner

    @property
    def store(self) -> Store:
        return self._store

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    @property
    def active_run_id(self) -> str | None:
        return self._active_run_id

    def start(self) -> None:
        """Start the background queue worker (idempotent)."""

        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stopping = False
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the background worker without touching persisted state."""

        self._stopping = True
        task = self._loop_task
        self._loop_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown is best effort
                pass

    # ----------------------------------------------------------- task create
    def create_task(
        self,
        request_id: str,
        title: str,
        objective: str,
        *,
        scope: str | None = None,
        acceptance_criteria: tuple[str, ...] = (),
        project_ref: str | None = None,
        workspace_ref: str | None = None,
        agent_ref: str | None = None,
        enqueue: bool = True,
    ) -> CoordinatorResult:
        """Create (and optionally queue) a Task.  Idempotent on ``request_id``."""

        def producer() -> dict[str, Any]:
            return self._create_task_locked(
                request_id=request_id,
                title=title,
                objective=objective,
                scope=scope,
                acceptance_criteria=acceptance_criteria,
                project_ref=project_ref,
                workspace_ref=workspace_ref,
                agent_ref=agent_ref,
                enqueue=enqueue,
            )

        return self._result_from(self._idempotency.execute(f"request:{request_id}", producer))

    def _create_task_locked(
        self,
        *,
        request_id: str,
        title: str,
        objective: str,
        scope: str | None,
        acceptance_criteria: tuple[str, ...],
        project_ref: str | None,
        workspace_ref: str | None,
        agent_ref: str | None,
        enqueue: bool,
    ) -> dict[str, Any]:
        task_id = new_id("task")
        content = _task_content(
            title=title,
            objective=objective,
            acceptance=acceptance_criteria,
            project_ref=project_ref,
            workspace_ref=workspace_ref,
            agent_ref=agent_ref or "coordinator",
        )
        cast(_BodyStore, self._store).create(
            "task",
            task_id,
            content,
            actor=self._owner,
            request_id=request_id,
            body=_task_body(objective, scope, acceptance_criteria),
        )
        self._writer.emit(
            task_id,
            EventType.TASK_CREATED,
            {"title": title, "request_id": request_id},
            task_ref=task_id,
        )
        queue_state = "not_queued"
        if enqueue:
            queue_state = self._queue.enqueue(task_id)
        return {
            "kind": "task",
            "reply": f"已创建 Task {task_id}（{queue_state}）。",
            "task_id": task_id,
            "queue_state": queue_state,
        }

    # ---------------------------------------------------------- global entry
    async def submit_global_message(
        self,
        conversation_id: str,
        message: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> CoordinatorResult:
        """Persist and route a message in the global conversation.

        The message is written before any side effect.  Repeated ``message_id``
        returns the first recorded result; control side effects carry their own
        ``request_id`` idempotency as a second guard.
        """

        message_id = self._require_message_id(message)
        key = f"message:{message_id}"
        existing = self._idempotency.lookup(key)
        if existing is not None:
            return self._result_from(existing)
        record = self._global.append(conversation_id, message)
        classification = self._classifier(str(message.get("content", "")))
        result = await self._route_global(
            conversation_id=conversation_id,
            message=message,
            record_seq=record.seq,
            classification=classification,
            task_ref=self._message_task_ref(message),
            request_id=request_id or message_id,
        )
        self._idempotency.record(key, result.to_dict())
        return result

    async def _route_global(
        self,
        *,
        conversation_id: str,
        message: dict[str, Any],
        record_seq: int,
        classification: Classification,
        task_ref: str | None,
        request_id: str,
    ) -> CoordinatorResult:
        content = str(message.get("content", ""))
        if classification.next_action in {"direct", "bounded_read"}:
            reply = self._responder(content, classification)
            return CoordinatorResult(
                kind=classification.next_action,
                reply=reply,
                conversation_id=conversation_id,
                data={
                    "intent": classification.intent.value,
                    "bounded_tools": list(classification.bounded_tools),
                    "creates_task": False,
                },
            )
        if classification.next_action == "create_task":
            title = content.strip().splitlines()[0][:120] or "New task"

            def producer() -> dict[str, Any]:
                return self._create_task_locked(
                    request_id=f"message:{request_id}",
                    title=title,
                    objective=content,
                    scope=None,
                    acceptance_criteria=(),
                    project_ref=None,
                    workspace_ref=None,
                    agent_ref=None,
                    enqueue=True,
                )

            created = self._idempotency.execute(f"message-task:{request_id}", producer)
            created = dict(created)
            created["conversation_id"] = conversation_id
            created["data"] = {"intent": classification.intent.value, "creates_task": True}
            return self._result_from(created)
        target, candidates = self._resolve_target(task_ref)
        if target is None:
            return CoordinatorResult(
                kind="clarify",
                reply="全局对话没有唯一目标，请指定 Task；未执行控制操作。",
                conversation_id=conversation_id,
                candidates=tuple(candidates),
                data={"intent": classification.intent.value, "ambiguous": True},
            )
        if classification.next_action == "control":
            action = "cancel" if any(
                token in content.lower() for token in ("取消", "停止", "cancel", "stop", "abort")
            ) else "pause"
            controlled = await self.request_control(target, action, request_id=request_id)
            controlled.data.setdefault("intent", classification.intent.value)
            return controlled
        if classification.next_action == "retry":
            state = self._queue.enqueue(target)
            return CoordinatorResult(
                kind="retry",
                reply=f"Task {target} 已请求继续（{state}）。",
                task_id=target,
                conversation_id=conversation_id,
                queue_state=state,
            )
        return CoordinatorResult(
            kind=classification.next_action,
            reply="已记录到全局对话；对交付任务的操作请在该 Task 对话中进行。",
            conversation_id=conversation_id,
            data={"intent": classification.intent.value, "record_seq": record_seq},
        )

    # ------------------------------------------------------------ task entry
    async def submit_task_message(
        self, task_id: str, message: dict[str, Any]
    ) -> CoordinatorResult:
        """Persist and route a message in a Task conversation."""

        message_id = self._require_message_id(message)
        key = f"message:{message_id}"
        existing = self._idempotency.lookup(key)
        if existing is not None:
            return self._result_from(existing)
        # Persist first; this is itself idempotent on message_id.
        self._store.append_message(task_id, message)
        content = str(message.get("content", ""))
        classification = self._classifier(content)
        if classification.next_action == "query":
            result = CoordinatorResult(
                kind="query",
                reply=self._status_reply(task_id),
                task_id=task_id,
                data=self.status(task_id),
            )
        elif classification.next_action == "control":
            action = "cancel" if any(
                token in content.lower() for token in ("取消", "停止", "cancel", "stop", "abort")
            ) else "pause"
            result = await self.request_control(task_id, action, request_id=message_id)
        elif classification.next_action == "retry":
            state = self._queue.enqueue(task_id)
            result = CoordinatorResult(
                kind="retry",
                reply=f"Task {task_id} 已请求继续（{state}）。",
                task_id=task_id,
                queue_state=state,
            )
        elif classification.next_action in {"direct", "bounded_read"}:
            result = CoordinatorResult(
                kind=classification.next_action,
                reply=self._responder(content, classification),
                task_id=task_id,
                data={"intent": classification.intent.value, "creates_run": False},
            )
        else:
            result = CoordinatorResult(
                kind=classification.next_action,
                reply="已保存到 Task 对话，未新建 Run。",
                task_id=task_id,
                data={"intent": classification.intent.value},
            )
        self._idempotency.record(key, result.to_dict())
        return result

    # --------------------------------------------------------------- control
    async def request_control(
        self,
        task_id: str,
        action: str,
        *,
        request_id: str | None = None,
    ) -> CoordinatorResult:
        """Apply a pause/cancel request, awaiting real stop confirmation."""

        key = f"request:{request_id}" if request_id else None
        if key is not None:
            existing = self._idempotency.lookup(key)
            if existing is not None:
                return self._result_from(existing)
        result = await self._apply_control(task_id, action)
        if key is not None:
            self._idempotency.record(key, result.to_dict())
        return result

    async def _apply_control(self, task_id: str, action: str) -> CoordinatorResult:
        task = self._store.read("task", task_id)
        phase = str(task.entity.get("phase", ""))
        active_run = task.entity.get("active_run")
        if action not in {"pause", "cancel"}:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unsupported control action {action!r}",
                details={"action": action},
            )
        if not isinstance(active_run, str) or not active_run:
            result = self._cancel_without_run(task_id, phase, action)
            return result

        if action == "cancel":
            if phase not in {TaskPhase.CANCELLING.value, TaskPhase.AWAITING_ACCEPTANCE.value}:
                self._writer.transition_task(task_id, TaskPhase.CANCELLING, run_ref=active_run)
        else:
            if phase == TaskPhase.EXECUTING.value:
                self._writer.transition_task(task_id, TaskPhase.PAUSING, run_ref=active_run)
            elif phase == TaskPhase.WAITING_USER.value:
                self._writer.transition_task(task_id, TaskPhase.PAUSED, run_ref=active_run)
            else:
                return CoordinatorResult(
                    kind="control",
                    reply=f"Task {task_id} 当前阶段 {phase} 不支持暂停。",
                    task_id=task_id,
                    run_id=active_run,
                    data={"action": action, "state": "not_pausable", "phase": phase},
                )

        cancel_result = await self._dispatcher.cancel(task_id, active_run)
        confirmed = bool(cancel_result.confirmed)
        if action == "cancel":
            if confirmed:
                self._writer.transition_run(
                    active_run, "cancelled", task_ref=task_id, reason=cancel_result.reason
                )
                self._writer.transition_task(task_id, TaskPhase.CANCELLED, run_ref=active_run)
                self._writer.set_active_run(task_id, None)
                state = "confirmed"
            else:
                state = "unconfirmed"
        else:
            if confirmed:
                self._writer.transition_run(
                    active_run, "paused", task_ref=task_id, reason=cancel_result.reason
                )
                self._writer.transition_task(task_id, TaskPhase.PAUSED, run_ref=active_run)
                state = "confirmed"
            else:
                state = "unconfirmed"
        reply = (
            f"Task {task_id} 的 {action} 已确认停止。"
            if confirmed
            else f"Task {task_id} 的 {action} 尚未确认停止，保持取消/暂停中间态。"
        )
        return CoordinatorResult(
            kind="control",
            reply=reply,
            task_id=task_id,
            run_id=active_run,
            data={"action": action, "state": state, "confirmed": confirmed},
        )

    def _cancel_without_run(self, task_id: str, phase: str, action: str) -> CoordinatorResult:
        if action != "cancel":
            return CoordinatorResult(
                kind="control",
                reply=f"Task {task_id} 当前没有活跃 Run，忽略 pause。",
                task_id=task_id,
                data={"action": action, "state": "no_active_run"},
            )
        if phase in {TaskPhase.CANCELLED.value, TaskPhase.COMPLETED.value}:
            return CoordinatorResult(
                kind="control",
                reply=f"Task {task_id} 已是 {phase}。",
                task_id=task_id,
                data={"action": action, "state": "no_active_run", "phase": phase},
            )
        self._writer.transition_task(task_id, TaskPhase.CANCELLED)
        return CoordinatorResult(
            kind="control",
            reply=f"Task {task_id} 已取消（未启动执行）。",
            task_id=task_id,
            data={"action": action, "state": "confirmed", "confirmed": True},
        )

    # ---------------------------------------------------------------- status
    def status(self, task_id: str) -> dict[str, Any]:
        """Immediate snapshot from persisted state (never waits for a Run)."""

        task = self._store.read("task", task_id)
        queue_raw = task.entity.get("queue")
        queue: dict[str, Any] = queue_raw if isinstance(queue_raw, dict) else {}
        active_run = task.entity.get("active_run")
        run_state: str | None = None
        if isinstance(active_run, str) and active_run:
            try:
                run_state = str(self._store.read("run", active_run).entity.get("state"))
            except EntityNotFound:
                run_state = "missing"
        return {
            "task_id": task_id,
            "status": task.entity.get("status"),
            "phase": task.entity.get("phase"),
            "revision": task.revision,
            "queue": {
                "state": queue.get("state"),
                "order": queue.get("order"),
                "owner": queue.get("owner"),
            },
            "active_run": active_run,
            "run_state": run_state,
            "archived": task.entity.get("archived", False),
        }

    def _status_reply(self, task_id: str) -> str:
        snapshot = self.status(task_id)
        return (
            f"Task {task_id}: status={snapshot['status']} phase={snapshot['phase']} "
            f"queue={snapshot['queue']['state']} run={snapshot['run_state']}."
        )

    def list_tasks(self) -> list[dict[str, Any]]:
        return [
            {
                "task_id": summary.id,
                "title": summary.title,
                "status": summary.status,
                "phase": summary.phase,
                "queue_state": summary.queue_state,
                "owner": summary.owner,
            }
            for summary in self._store.list_tasks()
        ]

    def read_task_messages(
        self, task_id: str, *, after: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        return [
            {"message_id": record.message_id, "seq": record.seq, "message": record.message}
            for record in self._store.read_messages(task_id, after=after, limit=limit)
        ]

    def read_global_messages(
        self, conversation_id: str, *, after: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        return [
            {"message_id": record.message_id, "seq": record.seq, "message": record.message}
            for record in self._global.read(conversation_id, after=after, limit=limit)
        ]

    # ------------------------------------------------------------- worker loop
    async def _run_loop(self) -> None:
        while not self._stopping:
            try:
                processed = await self._process_one()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive a bad task
                processed = False
            if not processed:
                try:
                    await asyncio.sleep(self._poll_interval)
                except asyncio.CancelledError:
                    raise

    async def _process_one(self) -> bool:
        summary = self._queue.next_queued()
        if summary is None:
            return False
        task_id = summary.id
        try:
            claim = self._store.claim(task_id, self._owner, lease_seconds=self._lease_seconds)
        except LockConflict:
            return False
        try:
            task = self._store.read("task", task_id)
            run_id = self._open_run(task)
            self._writer.emit(
                task_id,
                EventType.QUEUE_CLAIMED,
                {"owner": self._owner, "run_id": run_id},
                task_ref=task_id,
                run_ref=run_id,
            )
            context = self._build_context(task, run_id)
            controller = RunController(self._writer, task_id, run_id)
            self._active_run_id = run_id
            try:
                outcome = await self._dispatcher.dispatch(
                    context, controller, self._adapter_sink(task_id, run_id)
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - convert a dispatcher crash to a failure
                outcome = DispatchOutcome(
                    state="failed",
                    summary=f"{type(exc).__name__}: {exc}",
                    failure_code="internal_error",
                    failure_message=str(exc),
                )
            finally:
                self._active_run_id = None
            self._apply_outcome(task_id, run_id, outcome)
            return True
        finally:
            try:
                self._store.release(task_id, self._owner)
            except LockConflict:
                pass

    def _open_run(self, task: Versioned) -> str:
        active = task.entity.get("active_run")
        if isinstance(active, str) and active:
            try:
                existing = self._store.read("run", active).entity
            except EntityNotFound:
                existing = {}
            if str(existing.get("state")) not in TERMINAL_RUN_STATES:
                raise AppError(
                    ErrorCode.ILLEGAL_TRANSITION,
                    f"task {task.entity_id!r} already has a non-terminal Run {active!r}",
                    details={"task_id": task.entity_id, "active_run": active},
                )
        run_id = new_id("run")
        cast(_BodyStore, self._store).create(
            "run",
            run_id,
            {
                "task_ref": task.entity_id,
                "attempt": 1,
                "state": "planning",
                "plan_ref": "PLAN.md",
                "team_refs": [],
                "subtask_refs": [],
                "session_refs": [],
                "cleanup": {"status": "pending"},
                "ended_at": None,
                "fail_reason": None,
            },
            actor=self._owner,
            request_id=f"run:{run_id}",
            body=f"# Run {run_id}\n\nTask: {task.entity_id}\n",
        )
        self._writer.emit(
            task.entity_id,
            EventType.RUN_CREATED,
            {"run_id": run_id, "attempt": 1},
            task_ref=task.entity_id,
            run_ref=run_id,
        )
        self._writer.transition_task(
            task.entity_id,
            TaskPhase.PLANNING,
            run_ref=run_id,
            extra={"active_run": run_id},
        )
        return run_id

    def _build_context(self, task: Versioned, run_id: str) -> DispatchContext:
        entity = task.entity
        criteria = entity.get("acceptance_criteria") or []
        if not isinstance(criteria, list):
            criteria = []
        return DispatchContext(
            task_id=task.entity_id,
            run_id=run_id,
            attempt=1,
            objective=str(entity.get("objective") or entity.get("title") or ""),
            acceptance_criteria=tuple(str(item) for item in criteria),
            instructions=task.body.strip(),
            workspace_path=self._workspace_path(entity),
            allowed_tools=self._allowed_tools,
            agent_ref=self._agent_ref,
            connection_ref=self._connection_ref,
            budget=self._budget or self._task_budget(entity),
            timeout_seconds=self._timeout_seconds,
            conversation_id=None,
        )

    def _workspace_path(self, entity: dict[str, Any]) -> str:
        ref = entity.get("workspace_ref")
        if not isinstance(ref, str) or not ref.strip():
            return ""
        try:
            resolved = self._store.resolve_path(ref, write=True)
        except Exception:  # noqa: BLE001 - unresolved workspace is reported as empty
            return ""
        return str(resolved)

    @staticmethod
    def _task_budget(entity: dict[str, Any]) -> dict[str, int]:
        raw = entity.get("budget")
        if not isinstance(raw, dict):
            return {}
        result: dict[str, int] = {}
        for key, value in raw.items():
            if isinstance(value, int) and not isinstance(value, bool):
                result[str(key)] = value
        return result

    def _apply_outcome(self, task_id: str, run_id: str, outcome: DispatchOutcome) -> None:
        state = outcome.state
        stop_confirmed = outcome.stop_confirmed
        if state == "cancelled" and stop_confirmed is False:
            # Never write cancelled without confirmation (docs/08 §9).
            state = "failed"
            outcome = DispatchOutcome(
                state="failed",
                summary=f"cancellation unconfirmed: {outcome.summary}",
                failure_code="cancellation_unconfirmed",
                failure_message=outcome.failure_message or "cancel not confirmed",
                stop_confirmed=False,
            )
        current_phase = str(self._store.read("task", task_id).entity.get("phase", ""))
        run_state = DispatchOutcome(state=state).run_state
        task_phase = DispatchOutcome(state=state).task_phase
        if current_phase == TaskPhase.CANCELLING.value and run_state != "cancelled":
            # A cancel was accepted while the dispatcher was still returning.
            run_state = "cancelled"
            task_phase = TaskPhase.CANCELLED
        run_extra: dict[str, Any] = {}
        if run_state in {"failed", "cancelled"}:
            run_extra["ended_at"] = _now_iso()
        if outcome.failure_message or outcome.summary:
            run_extra["fail_reason"] = outcome.failure_message or outcome.summary
        self._writer.transition_run(
            run_id,
            run_state,
            task_ref=task_id,
            extra=run_extra or None,
            reason=outcome.failure_message,
        )
        self._writer.transition_task(task_id, task_phase, run_ref=run_id)
        if run_state in TERMINAL_RUN_STATES:
            self._writer.set_active_run(task_id, None)
        if outcome.failure_message:
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "worker",
                    "code": outcome.failure_code,
                    "message": outcome.failure_message,
                },
                task_ref=task_id,
                run_ref=run_id,
            )

    def _adapter_sink(self, task_id: str, run_id: str) -> Callable[[dict[str, Any]], None]:
        """Persist only contract-relevant adapter events.

        Streaming text/tool events are intentionally not persisted by LG-007;
        they are execution detail for the Run view (LG-016).  Errors are
        recorded so failures are never silent.
        """

        def sink(event: dict[str, Any]) -> None:
            event_type = event.get("type")
            if event_type == "adapter.error":
                self._writer.emit(
                    task_id,
                    EventType.ERROR_RECORDED,
                    {
                        "source": "adapter",
                        "error": str(event.get("error", ""))[:200],
                        "message": str(event.get("message", ""))[:500],
                    },
                    task_ref=task_id,
                    run_ref=run_id,
                )

        return sink

    # ------------------------------------------------------------- ambiguity
    def _active_tasks(self) -> list[dict[str, Any]]:
        active: list[dict[str, Any]] = []
        for summary in self._store.list_tasks():
            if summary.phase not in ACTIVE_TASK_PHASES:
                continue
            active.append(
                {
                    "task_id": summary.id,
                    "title": summary.title,
                    "phase": summary.phase,
                    "active_run": summary.owner,
                }
            )
        return active

    def _resolve_target(
        self, task_ref: str | None
    ) -> tuple[str | None, list[dict[str, Any]]]:
        if task_ref:
            return task_ref, []
        active = self._active_tasks()
        if len(active) == 1:
            return str(active[0]["task_id"]), []
        if len(active) == 0:
            return None, []
        return None, active

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _require_message_id(message: dict[str, Any]) -> str:
        message_id = message.get("message_id") if isinstance(message, dict) else None
        if not isinstance(message_id, str) or not message_id:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "message_id is required",
                details={"field": "message_id"},
            )
        role = message.get("role", "user")
        if role not in _ALLOWED_MESSAGE_ROLES:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unsupported message role {role!r}",
                details={"field": "role"},
            )
        return message_id

    @staticmethod
    def _message_task_ref(message: dict[str, Any]) -> str | None:
        ref = message.get("task_ref")
        return ref if isinstance(ref, str) and ref else None

    @staticmethod
    def _result_from(payload: dict[str, Any]) -> CoordinatorResult:
        candidates = payload.get("candidates") or ()
        return CoordinatorResult(
            kind=str(payload.get("kind", "unknown")),
            reply=str(payload.get("reply", "")),
            task_id=payload.get("task_id"),
            run_id=payload.get("run_id"),
            conversation_id=payload.get("conversation_id"),
            queue_state=payload.get("queue_state"),
            candidates=tuple(candidates),
            data=payload.get("data") or {},
        )


__all__ = ["Coordinator", "CoordinatorResult"]
