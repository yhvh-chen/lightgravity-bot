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
from typing import Any, Protocol, cast, runtime_checkable

from lightgravity.contracts import AppError, ErrorCode, EventType, TaskPhase, TaskStatus
from lightgravity.resources import ResourceService
from lightgravity.store import (
    EntityNotFound,
    LockConflict,
    Store,
    Versioned,
    new_id,
)
from lightgravity.store.locking import LockManager

# LG-017: the rework orchestrator's spawner returns this structural outcome.
# Importing it directly (no cycle: verify.rework depends on coordinator.state,
# not on coordinator.service) keeps the coordinator's port honest without
# duplicating the type.
from lightgravity.verify.rework import SpawnOutcome

from .classification import Classification, MessageIntent, classify_message
from .resource_commands import (
    PROPOSAL_AUTHOR_ROLES,
    parse_resource_proposal,
    proposal_author_role,
)
from .dispatcher import (
    DispatchContext,
    Dispatcher,
    DispatchOutcome,
    RunController,
    SingleSlotDispatcher,
    UnavailableExecutor,
)
from .continuation import (
    MODE_CREATE_ONLY,
    MODE_RESUME,
    CONTINUATION_CONFIG_VERSION,
    continuation_record,
    plan_continuation,
)
from .control import ControlService
from .logs import GlobalConversationLog, IdempotencyLog
from .queue import TaskQueue
from .recovery import ProcessProbe, RecoveryReport, RecoveryScanner
from .state import ACTIVE_TASK_PHASES, TERMINAL_RUN_STATES, StateWriter

_ALLOWED_MESSAGE_ROLES = frozenset({"user", "assistant", "system", "tool"})


class _ReworkRunController:
    """RunController delegate that keeps a rework Task in ``executing``.

    A rework Run enters through the frozen ``repairing -> executing`` transition.
    The dispatcher still calls ``set_task_phase('planning'/'recruiting')`` while
    it plans and recruits; those would be illegal backward transitions from
    ``executing``.  This delegate forwards every Run write and member/event call
    but drops Task-phase writes that would move the Task *back* from
    ``executing`` (the Run's own state and the final ``executing -> verifying``
    write still happen normally).
    """

    def __init__(self, inner: RunController) -> None:
        self._inner = inner

    def set_task_phase(
        self,
        phase: str,
        *,
        status: str | None = None,
        extra: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> Any:
        normalized = str(phase)
        if normalized in {"planning", "recruiting", "executing"}:
            # The Task already sits in ``executing`` for a rework Run; keep it
            # there instead of writing an illegal backward transition.
            return None
        return self._inner.set_task_phase(
            normalized, status=status, extra=extra, reason=reason
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _spawn_outcome_from_dict(data: dict[str, Any]) -> "SpawnOutcome":
    """Rebuild a recorded rework-spawn outcome from its persisted dict."""

    run_id = data.get("run_id")
    return SpawnOutcome(
        queued=bool(data.get("queued", False)),
        run_id=run_id if isinstance(run_id, str) and run_id else None,
        detail=str(data.get("detail", "")),
    )


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


@runtime_checkable
class CandidateVerifier(Protocol):
    """Structural port for the LG-009 verification service.

    Declared here (instead of importing ``VerificationService``) so the
    coordinator and verify packages do not form an import cycle.  The
    coordinator calls :meth:`verify_and_prepare` automatically once a
    successful Run reaches ``verifying`` (docs/08 §6.1/§9).
    """

    def verify_and_prepare(
        self,
        task_id: str,
        *,
        request_id: str | None = None,
        expected_revision: int | None = None,
    ) -> Any: ...


@runtime_checkable
class ReworkReviewer(Protocol):
    """Structural port for the LG-017 review + bounded rework orchestrator.

    Declared here (not imported) so the coordinator and verify packages do not
    form an import cycle; ``ReworkOrchestrator`` satisfies it.  The coordinator
    calls :meth:`process` after machine verification and only opens human
    acceptance when the review passes.
    """

    def process(
        self,
        task_id: str,
        *,
        request_id: str | None = None,
        note: str | None = None,
    ) -> Any: ...


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
        verification: CandidateVerifier | None = None,
        rework: ReworkReviewer | None = None,
        resource_service: ResourceService | None = None,
        process_probe: ProcessProbe | None = None,
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
        self._verification = verification
        self._rework = rework
        self._resource_service = resource_service
        self._resource_dir = resolved_data_dir
        self._control = ControlService(
            self._store, self._writer, self._queue, self._dispatcher, owner=self._owner
        )
        self._recovery = RecoveryScanner(
            self._store,
            self._writer,
            probe=process_probe,
            artifact_root=resolved_data_dir,
        )
        self._loop_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._last_recovery: RecoveryReport | None = None
        #: LG-017 bounded rework queue: (task_id, findings) drained by the
        #: worker loop.  Kept in memory because the Task frontmatter already
        #: records ``review_findings``; a restart re-derives rework from the
        #: ``repairing`` phase via the normal recovery scan instead of replaying
        #: in-memory state.
        self._pending_rework: list[tuple[str, tuple[dict[str, Any], ...]]] = []
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
    def resources(self) -> ResourceService:
        """Controlled resource writer shared with the API layer (lazy default)."""

        if self._resource_service is None:
            self._resource_service = ResourceService(
                self._store, data_dir=self._resource_dir
            )
        return self._resource_service

    @property
    def active_run_id(self) -> str | None:
        return self._active_run_id

    def set_verification(self, verification: CandidateVerifier | None) -> None:
        """Attach/replace the verification port (used by ``create_app`` so an
        injected coordinator shares the app's verification service)."""

        self._verification = verification

    def set_rework(self, rework: ReworkReviewer | None) -> None:
        """Attach/replace the LG-017 independent-review/rework orchestrator.

        ``create_app`` may inject a ``ReworkOrchestrator``; when it does not, the
        coordinator builds one lazily over the same Store with a deterministic
        :class:`~lightgravity.verify.review.ProgramReviewer` and itself as the
        ``RunSpawner``.  That makes independent review + bounded rework the
        product's real default runtime path, not just a declared interface.
        """

        self._rework = rework

    @property
    def rework(self) -> ReworkReviewer | None:
        return self._rework

    def _resolved_rework(self) -> ReworkReviewer | None:
        """Return the effective rework orchestrator, building the default once.

        The default is a ``ReworkOrchestrator`` over this coordinator's Store
        whose ``RunSpawner`` is this coordinator, with the deterministic
        program reviewer (no model call).  It is built lazily so importing the
        coordinator never constructs it and so an injected orchestrator always
        wins.
        """

        if self._rework is not None:
            return self._rework
        # Local import keeps coordinator import graph free of verify at module
        # load time while still wiring a real default at runtime.
        from lightgravity.verify.review import ProgramReviewer
        from lightgravity.verify.rework import ReworkOrchestrator

        self._rework = ReworkOrchestrator(
            self._store,
            reviewer=ProgramReviewer(),
            writer=self._writer,
            spawner=self,
            actor=self._owner,
        )
        return self._rework

    def start(self) -> None:
        """Start the background queue worker (idempotent).

        Before the worker loop accepts work, one restart scan runs so a Run
        interrupted by a previous process never silently occupies the slot or
        gets replayed.  The scan's findings are exposed via
        :meth:`recovery_report`.
        """

        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stopping = False
        self.run_recovery_scan()
        self._loop_task = asyncio.create_task(self._run_loop())

    def run_recovery_scan(self) -> RecoveryReport:
        """Inspect persisted state after a restart and record the conclusions."""

        report = self._recovery.scan()
        self._last_recovery = report
        return report

    @property
    def recovery_report(self) -> RecoveryReport | None:
        return self._last_recovery

    @property
    def control(self) -> ControlService:
        return self._control

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
        if message.get("resource_proposal") is not None:
            # A controlled resource-change proposal is validated and applied
            # synchronously: it must not queue behind a code Run, and a model/
            # worker reply can never write control state (docs/05 §6.2).
            result = self._route_resource_proposal(task_id, message)
            self._idempotency.record(key, result.to_dict())
            return result
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

    # ------------------------------------------------- controlled resources
    def _route_resource_proposal(
        self, task_id: str, message: dict[str, Any]
    ) -> CoordinatorResult:
        """Validate and apply one message-attached resource proposal.

        The message was already persisted (so the request is auditable and
        idempotent on ``message_id``); this method records the *actual* outcome
        back into the same Task conversation.  It never enqueues work, never
        waits for a code Run and never lets a non-user author change a resource.
        """

        submitted_id = str(message.get("message_id"))
        role = proposal_author_role(message)
        if role not in PROPOSAL_AUTHOR_ROLES:
            return self._record_resource_result(
                task_id,
                submitted_id,
                status="unauthorized_source",
                reply=(
                    "Resource changes are only accepted from an authenticated user "
                    f"Task message; a {role!r} message cannot modify control "
                    "resources. No change was written."
                ),
                data={"role": role},
            )

        try:
            proposal = parse_resource_proposal(message.get("resource_proposal"))
        except AppError as exc:
            return self._record_resource_result(
                task_id,
                submitted_id,
                status="invalid_proposal",
                reply=f"资源修改提议不合法：{exc.message}",
                data={"error_code": exc.code.value, "details": exc.details},
            )

        # A valid Task must exist; append_message already enforces this, but read
        # it explicitly so the reply can name the preserved Task scope.
        task = self._store.read("task", task_id)
        task_title = str(task.entity.get("title") or task_id)
        try:
            detail = self.resources.update(
                proposal.kind,
                proposal.resource_id,
                patch=proposal.patch,
                expected_revision=proposal.expected_revision,
                actor=f"coordinator:{self._owner}",
                body=proposal.body,
            )
        except AppError as exc:
            status = (
                "conflict"
                if exc.code == ErrorCode.REVISION_CONFLICT
                else "rejected"
            )
            detail_payload: dict[str, Any] = {
                "kind": proposal.kind,
                "id": proposal.resource_id,
                "expected_revision": proposal.expected_revision,
                "error_code": exc.code.value,
            }
            if exc.code == ErrorCode.REVISION_CONFLICT:
                detail_payload.update(exc.details)
                reply = (
                    f"{proposal.ref} 修改冲突：期望 revision "
                    f"{proposal.expected_revision}，实际 "
                    f"{exc.details.get('actual_revision')}。未写入；请重读后再提交。"
                )
            else:
                reply = f"{proposal.ref} 修改被拒绝（{exc.code.value}）：{exc.message}"
            return self._record_resource_result(
                task_id,
                submitted_id,
                status=status,
                reply=reply,
                data=detail_payload,
            )

        return self._record_resource_result(
            task_id,
            submitted_id,
            status="applied",
            reply=(
                f"已按程序校验写入 {proposal.kind}:{proposal.resource_id}，"
                f"revision -> {detail['revision']}。模板修改只影响后续招募；"
                f"正在运行的成员保持其固定配置（Task {task_title} 上下文保留）。"
            ),
            data={
                "kind": proposal.kind,
                "id": proposal.resource_id,
                "revision": detail["revision"],
                "etag": detail.get("etag"),
                "task_ref": task_id,
            },
        )

    def _record_resource_result(
        self,
        task_id: str,
        submitted_id: str,
        *,
        status: str,
        reply: str,
        data: dict[str, Any],
    ) -> CoordinatorResult:
        """Persist the actual resource-proposal result into the Task log."""

        # Deterministic reply id: appending is idempotent, so a retried
        # proposal never duplicates the recorded outcome.
        self._store.append_message(
            task_id,
            {
                "message_id": f"resource-result:{submitted_id}",
                "role": "assistant",
                "content": reply,
                "in_reply_to": submitted_id,
                "correlation_id": submitted_id,
                "resource_result": {"status": status, **data},
            },
        )
        return CoordinatorResult(
            kind="resource_change",
            reply=reply,
            task_id=task_id,
            data={"status": status, **data, "recorded_in_conversation": True},
        )

    # --------------------------------------------------------------- control
    async def request_control(
        self,
        task_id: str,
        action: str,
        *,
        request_id: str | None = None,
    ) -> CoordinatorResult:
        """Apply a control action, awaiting real stop confirmation.

        ``pause``/``cancel`` return ``confirmed=False`` until the dispatcher
        reports a real stop; ``resume``/``retry``/``reopen``/``enqueue`` only
        requeue and never create a second writer.  Idempotency is keyed by
        ``request_id`` so a duplicate control request returns the first
        outcome without re-invoking the adapter.
        """

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
        if action in {"pause", "cancel"}:
            outcome = await self._control.stop(task_id, action)
        elif action in {"resume", "retry", "reopen", "enqueue"}:
            outcome = self._control.requeue(task_id, action)
        else:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unsupported control action {action!r}",
                details={"action": action},
            )
        reply = self._control_reply(outcome)
        data: dict[str, Any] = {
            "action": outcome.action,
            "state": outcome.state,
            "confirmed": outcome.confirmed,
        }
        if outcome.run_id:
            data["run_id"] = outcome.run_id
        if outcome.phase:
            data["phase"] = outcome.phase
        if outcome.reason:
            data["reason"] = outcome.reason
        if outcome.cleanup:
            data["cleanup"] = outcome.cleanup
        return CoordinatorResult(
            kind="control",
            reply=reply,
            task_id=task_id,
            run_id=outcome.run_id,
            data=data,
        )

    @staticmethod
    def _control_reply(outcome: object) -> str:
        action = getattr(outcome, "action", "control")
        task_id = getattr(outcome, "task_id", "")
        state = getattr(outcome, "state", "")
        reason = getattr(outcome, "reason", None)
        if state == "confirmed":
            if action in {"pause", "cancel"}:
                return f"Task {task_id} 的 {action} 已确认停止。"
            return f"Task {task_id} 已接受 {action}，重新进入队列。"
        if state == "unconfirmed":
            return f"Task {task_id} 的 {action} 尚未确认停止，保持取消/暂停中间态。"
        return f"Task {task_id} 的 {action} 未生效：{reason or '当前阶段不允许'}。"

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
        # LG-017 rework Runs are dispatched directly (the frozen contract allows
        # ``repairing -> executing``, not ``repairing -> queued``), so they are
        # drained here *before* the normal queue.  A rework Run still opens a
        # fresh Run, re-recruits and re-verifies through the same dispatcher.
        if self._pending_rework:
            return await self._process_rework()
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
            await self._dispatch_run(task, run_id, claimed_event=True)
            return True
        finally:
            # Only release the claim we still hold.  A control requeue (resume)
            # that ran while this worker was finishing may have moved the Task
            # back to ``queued``; releasing then would clobber the queued state
            # and the resumed Run would never be picked up.  ``release`` itself
            # is idempotent for ``not_queued``.
            try:
                if self._queue_state(task_id) == "claimed":
                    self._store.release(task_id, self._owner)
            except LockConflict:
                pass

    async def _dispatch_run(
        self,
        task: Versioned,
        run_id: str,
        *,
        claimed_event: bool,
        rework: bool = False,
    ) -> None:
        """Dispatch one opened Run through the configured dispatcher.

        Shared by the normal queue path and the LG-017 rework path so both open a
        real Run, recruit a team and run verification identically.  For a rework
        Run the Task is already in ``executing`` (the only frozen transition out
        of ``repairing``), so the controller suppresses the dispatcher's
        planning/recruiting Task-phase writes (the Run's own state still moves
        normally) instead of hitting an illegal backward transition.
        """

        task_id = task.entity_id
        if claimed_event:
            self._writer.emit(
                task_id,
                EventType.QUEUE_CLAIMED,
                {"owner": self._owner, "run_id": run_id},
                task_ref=task_id,
                run_ref=run_id,
            )
        context = self._build_context(task, run_id)
        controller = RunController(self._writer, task_id, run_id)
        if rework:
            controller = _ReworkRunController(controller)  # type: ignore[assignment]
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

    async def _process_rework(self) -> bool:
        """Open and dispatch one queued LG-017 rework Run.

        The Task is already in ``repairing`` (set by the orchestrator).  The
        only frozen transition out of ``repairing`` is ``executing``; the new
        Run is opened and dispatched there, re-recruiting a team and re-running
        verification.  A Task that is no longer spawnable is dropped with an
        honest error event instead of being retried forever.
        """

        task_id, findings = self._pending_rework[0]
        try:
            task = self._store.read("task", task_id)
        except EntityNotFound:
            self._pending_rework.pop(0)
            return False
        phase = str(task.entity.get("phase", ""))
        if phase != TaskPhase.REPAIRING.value:
            self._pending_rework.pop(0)
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "rework",
                    "code": "not_ready",
                    "message": f"rework dropped: task phase is {phase!r}, not repairing",
                },
            )
            return True
        try:
            self._writer.write_task(task_id, {"review_findings": [dict(f) for f in findings]})
            # ``_open_run(rework=True)`` performs the single frozen
            # ``repairing -> executing`` transition and opens the fresh Run; the
            # Run then owns planning/recruiting/executing internally.
            task = self._store.read("task", task_id)
            run_id = self._open_run(task, rework=True)
        except Exception as exc:  # noqa: BLE001 - report, never fabricate a Run
            self._pending_rework.pop(0)
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "rework",
                    "code": "not_ready",
                    "message": f"could not open rework Run: {type(exc).__name__}: {exc}",
                },
            )
            return True
        self._pending_rework.pop(0)
        await self._dispatch_run(task, run_id, claimed_event=False, rework=True)
        return True

    def _queue_state(self, task_id: str) -> str:
        try:
            queue = self._store.read("task", task_id).entity.get("queue")
        except EntityNotFound:
            return "not_queued"
        if isinstance(queue, dict):
            return str(queue.get("state", "not_queued"))
        return "not_queued"

    def _open_run(self, task: Versioned, *, rework: bool = False) -> str:
        # A Task that a restart scan (or an operator) put into recovery_required
        # must not have a Run opened as a silent replay: its side effects are
        # unknown.  A human decides via resume/retry/cancel first.
        if str(task.entity.get("phase", "")) == TaskPhase.RECOVERY_REQUIRED.value:
            raise AppError(
                ErrorCode.ILLEGAL_TRANSITION,
                "task requires a human recovery decision; not opening a replay Run",
                details={"task_id": task.entity_id},
            )
        active = task.entity.get("active_run")
        source_run: dict[str, Any] | None = None
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
            source_run = existing
        else:
            # ``active_run`` was cleared by a requeue; the stopped Run is still
            # discoverable via ``last_run`` so a confirmed pause can be
            # continued natively instead of replayed from scratch.
            last = task.entity.get("last_run")
            if isinstance(last, str) and last:
                try:
                    source_run = self._store.read("run", last).entity
                except EntityNotFound:
                    source_run = None
                else:
                    active = last

        # Decide the native SDK session continuation from the Task's previous
        # Run *before* opening the new one (docs/02, docs/04 §5, docs/08 §8):
        # only a provably clean pause continues the same conversation; an
        # interrupted/unclean Run must not be silently replayed.
        decision = plan_continuation(
            task.entity,
            source_run,
            active if isinstance(active, str) and active else None,
        )
        continuation: dict[str, Any] | None = None
        if decision.is_resume and decision.identity is not None:
            identity = decision.identity
            continuation = {
                "conversation_id": identity.conversation_id,
                "save_dir": identity.save_dir,
                "continuation_mode": MODE_RESUME,
                "source_run_id": decision.source_run_id,
                "config_version": CONTINUATION_CONFIG_VERSION,
                "decision": "resume",
                "reason": decision.reason,
            }
        elif decision.is_recovery_required:
            # A new Run must not be opened as a silent replay.  Record the
            # decision and let the human recovery path handle the Task.
            self._writer.emit(
                task.entity_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "continuation",
                    "code": "recovery_required",
                    "message": decision.reason,
                    "source_run_id": decision.source_run_id,
                },
                task_ref=task.entity_id,
                run_ref=decision.source_run_id,
            )
            raise AppError(
                ErrorCode.ILLEGAL_TRANSITION,
                decision.reason,
                details={"task_id": task.entity_id, "source_run_id": decision.source_run_id},
            )

        run_id = new_id("run")
        # Attempt counts the Run's position in the Task's delivery history.  A
        # rework Run (opened after a review rejected the prior candidate) is a
        # new business attempt, so it must not reuse attempt 1 as though nothing
        # had been delivered (docs/08 §6.2).  Prior Run attempt comes from the
        # retained ``last_run``/``active_run`` source, never a fabricated count.
        prior_attempt = 0
        if isinstance(source_run, dict):
            raw_attempt = source_run.get("attempt")
            if isinstance(raw_attempt, int) and not isinstance(raw_attempt, bool):
                prior_attempt = raw_attempt
        attempt = prior_attempt + 1 if prior_attempt > 0 else 1
        # Carry the independent review findings (if any) onto the new Run so the
        # repair context can target them; empty for a normal first/retry Run.
        review_findings = task.entity.get("review_findings")
        findings_list = (
            [dict(f) for f in review_findings if isinstance(f, dict)]
            if isinstance(review_findings, list)
            else []
        )
        run_content: dict[str, Any] = {
            "task_ref": task.entity_id,
            "attempt": attempt,
            "state": "planning",
            "plan_ref": "PLAN.md",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "continuation": continuation,
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        }
        if findings_list:
            run_content["review_findings"] = findings_list
        cast(_BodyStore, self._store).create(
            "run",
            run_id,
            run_content,
            actor=self._owner,
            request_id=f"run:{run_id}",
            body=f"# Run {run_id}\n\nTask: {task.entity_id}\n",
        )
        self._writer.emit(
            task.entity_id,
            EventType.RUN_CREATED,
            {
                "run_id": run_id,
                "attempt": attempt,
                "continuation": decision.kind,
                "source_run_id": decision.source_run_id,
            },
            task_ref=task.entity_id,
            run_ref=run_id,
        )
        self._writer.transition_task(
            task.entity_id,
            TaskPhase.EXECUTING if rework else TaskPhase.PLANNING,
            run_ref=run_id,
            extra={"active_run": run_id},
            reason="lg017 rework Run opened" if rework else None,
        )
        return run_id

    def _build_context(self, task: Versioned, run_id: str) -> DispatchContext:
        entity = task.entity
        criteria = entity.get("acceptance_criteria") or []
        if not isinstance(criteria, list):
            criteria = []
        # Carry the planned native continuation (non-secret conversation id +
        # save_dir) into the ExecuteRequest so the adapter resumes the same SDK
        # conversation instead of replaying the objective from scratch.
        conversation_id, save_dir, continuation_mode = self._continuation_for(run_id)
        if save_dir is None:
            # Every Task gets one stable native session store so the SDK writes
            # its trajectory where a later resume can find it.  This is
            # non-secret and outside the Task Markdown dir (docs/02 §SDK session
            # 原生格式用于恢复).
            save_dir = self._native_session_dir(task.entity_id)
        return DispatchContext(
            task_id=task.entity_id,
            run_id=run_id,
            attempt=self._run_attempt(run_id),
            objective=str(entity.get("objective") or entity.get("title") or ""),
            acceptance_criteria=tuple(str(item) for item in criteria),
            instructions=self._instructions_for(task, run_id),
            workspace_path=self._workspace_path(entity),
            allowed_tools=self._allowed_tools,
            agent_ref=self._agent_ref,
            connection_ref=self._connection_ref,
            budget=self._budget or self._task_budget(entity),
            timeout_seconds=self._timeout_seconds,
            save_dir=save_dir,
            conversation_id=conversation_id,
            continuation_mode=continuation_mode,
            prior_run=self._prior_run_for(run_id),
        )

    def _run_attempt(self, run_id: str) -> int:
        """Read the Run's authoritative attempt (default 1 when unrecorded)."""

        try:
            raw = self._store.read("run", run_id).entity.get("attempt")
        except EntityNotFound:
            return 1
        if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
            return raw
        return 1

    def _instructions_for(self, task: Versioned, run_id: str) -> str:
        """The Task body plus any independent-review rework targets (LG-017).

        A repair Run gets the review findings appended so the new team knows
        what the independent reviewer rejected, without erasing the original
        Task body.  A normal Run gets the body unchanged.
        """

        body = task.body.strip()
        try:
            findings = self._store.read("run", run_id).entity.get("review_findings")
        except EntityNotFound:
            findings = None
        if not isinstance(findings, list) or not findings:
            return body
        lines = [body, "", "## Independent review rework targets (LG-017)"]
        for item in findings:
            if not isinstance(item, dict):
                continue
            target = str(item.get("rework_target") or "deliverable")
            summary = str(item.get("summary") or "").strip()
            ref = str(item.get("evidence_ref") or "")
            lines.append(f"- [{target}] {summary} (evidence: {ref})")
        return "\n".join(lines)

    def _prior_run_for(self, run_id: str) -> dict[str, Any] | None:
        """Return the source Run entity a resumed Run continues, else ``None``.

        Only a Run whose ``continuation.decision == 'resume'`` has a source; a
        fresh Run never inherits another Run's native node sessions.
        """

        try:
            run = self._store.read("run", run_id).entity
        except EntityNotFound:
            return None
        raw = run.get("continuation")
        if not isinstance(raw, dict) or raw.get("decision") != "resume":
            return None
        source = raw.get("source_run_id")
        if not isinstance(source, str) or not source:
            return None
        try:
            return self._store.read("run", source).entity
        except EntityNotFound:
            return None

    def _continuation_for(self, run_id: str) -> tuple[str | None, str | None, str | None]:
        """Return ``(conversation_id, save_dir, continuation_mode)`` to resume.

        Only a ``decision == 'resume'`` continuation is applied; a fresh Run
        gets ``(None, None, None)`` so the adapter creates a new native session
        and never silently replays into a stale conversation.
        """

        try:
            run = self._store.read("run", run_id).entity
        except EntityNotFound:
            return None, None, None
        raw = run.get("continuation")
        if not isinstance(raw, dict) or raw.get("decision") != "resume":
            return None, None, None
        conversation_id = raw.get("conversation_id")
        save_dir = raw.get("save_dir")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return None, None, None
        if not isinstance(save_dir, str) or not save_dir.strip():
            return None, None, None
        mode = raw.get("continuation_mode")
        if mode not in {MODE_RESUME, "create_or_resume", MODE_CREATE_ONLY}:
            mode = MODE_RESUME
        return conversation_id, save_dir, str(mode)

    def _workspace_path(self, entity: dict[str, Any]) -> str:
        ref = entity.get("workspace_ref")
        if not isinstance(ref, str) or not ref.strip():
            return ""
        try:
            resolved = self._store.resolve_path(ref, write=True)
        except Exception:  # noqa: BLE001 - unresolved workspace is reported as empty
            return ""
        return str(resolved)

    def _native_session_dir(self, task_id: str) -> str:
        """Stable, non-secret native session storage directory for a Task.

        The directory is created lazily by the SDK when it writes the first
        trajectory; the coordinator only returns the path.  A resumed Run of the
        same Task points at the same directory so the SDK's native
        ``conversation_id`` lookup finds the previous session.
        """

        return str(self._resource_dir / "native-sessions" / task_id)

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
        # Persist the adapter's *final* native session identity.  The SDK only
        # assigns the native ``conversation_id`` after the turn completes, so the
        # ``session_started`` event alone cannot carry it; the ``ExecutorResult``
        # session ref is authoritative (proven by probes/lg016 native evidence).
        self._record_result_session(run_id, outcome.result)
        # The default GraphDispatcher path aggregates node results, so the Run's
        # authoritative native identity lives in the per-node ``node_sessions``
        # the graph persisted.  Derive the Run-level continuation from them so a
        # later confirmed-pause resume still has a non-secret source even when no
        # single ``outcome.result`` exists (LG-016 graph session wiring).
        self._record_run_continuation_from_nodes(run_id)
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
        # A control requeue (resume/retry/reopen) may have opened a new Run for
        # this Task while this (older) dispatch was still finishing.  Applying
        # the old outcome then would clobber the freshly queued/planned Run and
        # silently erase the pause.  If the Task already points at a different
        # active Run, this outcome is stale: keep the Run's stop record and let
        # the live Run own the Task phase.
        current_active = self._store.read("task", task_id).entity.get("active_run")
        if current_active != run_id:
            self._writer.write_run(run_id, {"cleanup": {"status": "done"}})
            return
        run_state = DispatchOutcome(state=state).run_state
        task_phase = DispatchOutcome(state=state).task_phase
        if current_phase == TaskPhase.CANCELLING.value and run_state != "cancelled":
            # A cancel was accepted while the dispatcher was still returning.
            run_state = "cancelled"
            task_phase = TaskPhase.CANCELLED
        elif current_phase in {TaskPhase.PAUSING.value, TaskPhase.PAUSED.value}:
            # A pause was accepted/confirmed while the dispatcher was still
            # returning.  Keep the paused Run instead of letting a late
            # success overwrite it and silently resume execution.
            run_state = "paused"
            task_phase = TaskPhase.PAUSED
            self._writer.transition_run(
                run_id, run_state, task_ref=task_id, reason="pause accepted"
            )
            self._writer.transition_task(task_id, task_phase, run_ref=run_id)
            return
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
        if run_state in TERMINAL_RUN_STATES or run_state == "recovery_required":
            # recovery_required frees the execution slot and drops the active_run
            # pointer so the Task is cleanly parked for a human decision (it is
            # not a silent replay Run); ``_open_run`` still refuses to reopen it.
            if run_state == "recovery_required":
                self._writer.write_run(run_id, {"cleanup": {"status": "done"}})
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
        if run_state == "verifying":
            self._auto_verify(task_id, run_id)

    def _auto_verify(self, task_id: str, run_id: str) -> None:
        """Run independent review, then machine verification, after delivery.

        Order (LG-017): the independent reviewer inspects the candidate's *real
        evidence* first.  Only a passing review proceeds to
        :meth:`VerificationService.verify_and_prepare`, which moves the candidate
        ``verifying -> awaiting_acceptance`` through the real stop/release gate.

        * review ``rework`` with budget left -> a fresh repair Run is queued
          (re-recruit + re-verify); the old candidate/evidence are kept;
        * review ``rework`` with budget spent -> ``waiting_user`` and a
          ``budget_exhausted`` event, never a fake acceptance;
        * review ``unavailable`` (no usable independent reviewer) -> the
          candidate stays pending for a human, never a fake pass;
        * a review failure is recorded and leaves the Task in ``verifying``.

        When no rework orchestrator is wired the coordinator falls back to the
        LG-009 behaviour (machine checks only), so the default runtime never
        breaks.
        """

        verifier = self._verification
        rework = self._resolved_rework()
        if rework is not None:
            try:
                outcome = rework.process(task_id, request_id=f"auto-review:{run_id}")
            except Exception as exc:  # noqa: BLE001 - never let review crash the loop
                self._writer.emit(
                    task_id,
                    EventType.ERROR_RECORDED,
                    {
                        "mode": "review",
                        "code": "internal_error",
                        "message": f"independent review failed: {type(exc).__name__}: {exc}",
                    },
                    task_ref=task_id,
                    run_ref=run_id,
                )
                return
            state = str(getattr(outcome, "state", ""))
            if state != "awaiting_acceptance":
                # rework / unavailable / exhausted: do not open acceptance here.
                return

        if verifier is None:
            return
        try:
            verifier.verify_and_prepare(task_id, request_id=f"auto-verify:{run_id}")
        except Exception as exc:  # noqa: BLE001 - never let verification crash the loop
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {
                    "mode": "verify",
                    "code": "internal_error",
                    "message": f"automatic verification failed: {type(exc).__name__}: {exc}",
                },
                task_ref=task_id,
                run_ref=run_id,
            )

    def spawn_repair_run(
        self,
        task_id: str,
        *,
        prior_run_id: str,
        findings: tuple[dict[str, Any], ...],
        request_id: str,
    ) -> "SpawnOutcome":
        """LG-017 :class:`~lightgravity.verify.rework.RunSpawner` implementation.

        Queues a fresh rework Run for a Task already moved to ``repairing`` by
        the orchestrator.  The worker loop opens exactly one new Run on the next
        pass (``active_run`` was cleared, the prior Run is retained as
        ``last_run`` with its diff/evidence untouched), and that new Run goes
        through the full plan/recruit/dispatch/verify path again — i.e. it
        re-recruits and re-verifies rather than reusing the rejected team.

        The outcome is recorded under a rework-scoped ``request_id`` so a
        replayed reject (same request id) returns the *same* rework result
        instead of re-deriving it against moved-on state.  A spawn that cannot
        proceed returns ``SpawnOutcome(queued=False, ...)`` (never a fabricated
        Run id).
        """

        key = f"rework-spawn:{task_id}:{request_id}"
        existing = self._idempotency.lookup(key)
        if existing is not None:
            return _spawn_outcome_from_dict(existing)

        outcome = self._spawn_repair_run_once(
            task_id, prior_run_id=prior_run_id, findings=findings, request_id=request_id
        )
        self._idempotency.execute(key, lambda: outcome.to_dict())
        return outcome

    def lookup_spawn_outcome(self, task_id: str, request_id: str) -> "SpawnOutcome | None":
        """Return a previously recorded rework-spawn outcome, if any.

        Used by the API replay path so a duplicate reject returns the first
        response verbatim (including its ``rework`` field) without writing a
        second Run.
        """

        key = f"rework-spawn:{task_id}:{request_id}"
        existing = self._idempotency.lookup(key)
        if existing is None:
            return None
        return _spawn_outcome_from_dict(existing)

    def _spawn_repair_run_once(
        self,
        task_id: str,
        *,
        prior_run_id: str,
        findings: tuple[dict[str, Any], ...],
        request_id: str,
    ) -> "SpawnOutcome":
        current = self._store.read("task", task_id)
        phase = str(current.entity.get("phase", ""))
        if phase != TaskPhase.REPAIRING.value:
            return SpawnOutcome(
                queued=False, detail=f"task phase {phase!r} is not spawnable"
            )
        if isinstance(current.entity.get("active_run"), str) and current.entity.get("active_run"):
            return SpawnOutcome(queued=False, detail="task still has a non-terminal Run")
        # Persist the review findings so the new Run's context can read what to
        # repair; the old candidate/evidence stay on disk.
        self._writer.write_task(
            task_id,
            {"review_findings": [dict(f) for f in findings]},
        )
        # Enqueue into the bounded rework queue.  The worker loop transitions
        # ``repairing -> executing`` and opens exactly one fresh Run (re-recruit
        # + re-verify).  Duplicate requests for the same Task are collapsed so a
        # replayed reject cannot open a second concurrent rework Run.
        if any(existing_task == task_id for existing_task, _ in self._pending_rework):
            return SpawnOutcome(
                queued=True, detail="rework already queued for this task"
            )
        self._pending_rework.append((task_id, tuple(dict(f) for f in findings)))
        self._writer.emit(
            task_id,
            EventType.QUEUE_ENQUEUED,
            {
                "state": "rework_queued",
                "request_id": request_id,
                "prior_run_id": prior_run_id,
                "reason": "lg017-rework",
                "findings": len(findings),
            },
            task_ref=task_id,
            run_ref=prior_run_id,
        )
        # The worker loop opens exactly one new Run on its next pass and drives
        # the full plan/recruit/dispatch/verify path again (re-recruit +
        # re-verify).  No Run id exists yet, so none is fabricated.
        return SpawnOutcome(queued=True, detail="repair Run queued for the worker loop")

    def _adapter_sink(self, task_id: str, run_id: str) -> Callable[[dict[str, Any]], None]:
        """Persist only contract-relevant adapter events.

        Streaming text/tool events are intentionally not persisted by LG-007;
        they are execution detail for the Run view (LG-016).  Errors are
        recorded so failures are never silent.
        """

        def sink(event: dict[str, Any]) -> None:
            event_type = event.get("type")
            if event_type == "adapter.session_started":
                # Record the real SDK session on the Run so the stop gate can
                # confirm every session is closed before awaiting acceptance
                # (docs/08 §6.2/§9).  Idempotent by session_id; never fabricates
                # a session when the adapter reported none.
                session = event.get("session")
                if isinstance(session, dict) and session.get("session_id"):
                    self._record_session_ref(run_id, str(session["session_id"]))
                # Persist the non-secret native conversation identity so a later
                # confirmed-pause resume can continue the same SDK session
                # (docs/02 SDK 资源; docs/04 §5).  Only IDs/dirs are stored.
                self._record_continuation(run_id, session)
            elif event_type == "adapter.error":
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

    def _record_result_session(self, run_id: str, result: Any) -> None:
        """Persist the final adapter ``SessionRef`` (native conversation id + dir).

        Called once per Run after the turn, when the native conversation id is
        finally known.  Records the opaque session id for the stop gate and the
        non-secret conversation identity for continuation; a missing id is never
        fabricated.
        """

        session_ref = getattr(result, "session_ref", None)
        if session_ref is None:
            return
        session = session_ref.to_dict() if hasattr(session_ref, "to_dict") else None
        if not isinstance(session, dict):
            return
        session_id = session.get("session_id")
        if session_id:
            self._record_session_ref(run_id, str(session_id))
        self._record_continuation(run_id, session)

    def _record_run_continuation_from_nodes(self, run_id: str) -> None:
        """Derive the Run-level ``continuation`` from persisted node sessions.

        Only the GraphDispatcher populates ``node_sessions``.  When there is no
        single ``outcome.result`` (the graph aggregates node results), the Run's
        continuation source is the first node session that carries a native
        conversation id.  The run-level record is a *fallback* used to open a
        later Run; the authoritative per-node coordinates stay in
        ``node_sessions``.  Nothing is written when no node reported a native id.
        """

        try:
            run = self._store.read("run", run_id).entity
        except EntityNotFound:
            return
        node_sessions = run.get("node_sessions")
        if not isinstance(node_sessions, dict) or not node_sessions:
            return
        primary: dict[str, Any] | None = None
        for entry in node_sessions.values():
            if not isinstance(entry, dict):
                continue
            conversation_id = entry.get("conversation_id")
            save_dir = entry.get("save_dir")
            if (
                isinstance(conversation_id, str)
                and conversation_id.strip()
                and isinstance(save_dir, str)
                and save_dir.strip()
                and str(entry.get("state")) != "closed"
            ):
                primary = entry
                break
        if primary is None:
            return
        existing = run.get("continuation")
        planned_source = existing.get("source_run_id") if isinstance(existing, dict) else None
        resumed = str(primary.get("state")) == "resumed"
        record = continuation_record(
            conversation_id=str(primary["conversation_id"]),
            save_dir=str(primary["save_dir"]),
            continuation_mode=(MODE_RESUME if resumed else MODE_CREATE_ONLY),
            source_run_id=(
                str(planned_source)
                if isinstance(planned_source, str) and planned_source
                else None
            ),
            resumed=resumed,
        )
        if record is None:
            return
        record["decision"] = "resume" if resumed else "fresh"
        # Never downgrade an already-planned native resume to a fresh decision
        # on a chained resume; the Run-level record is only a fallback and must
        # not lose the continuation intent proven at open time.
        if isinstance(existing, dict) and existing.get("decision") == "resume":
            record["decision"] = "resume"
        record["primary_node_key"] = str(primary.get("key", ""))
        self._writer.write_run(run_id, {"continuation": record})

    def _record_session_ref(self, run_id: str, session_id: str) -> None:
        """Add ``session_id`` to the Run's ``session_refs`` once (idempotent)."""

        try:
            run = self._store.read("run", run_id)
        except EntityNotFound:
            return
        raw = run.entity.get("session_refs")
        existing = [str(item) for item in raw] if isinstance(raw, (list, tuple)) else []
        if session_id in existing:
            return
        self._writer.write_run(run_id, {"session_refs": [*existing, session_id]})

    def _record_continuation(
        self, run_id: str, session: Any
    ) -> None:
        """Persist ``conversation_id``/``save_dir`` for a later native resume.

        The values are non-secret native SDK identifiers (docs/02: 记录会话标识、
        后端、配置版本与存储引用).  The adapter labels a session ``resumed`` when
        it attached to an existing conversation; we keep that label so a Run's
        ``continuation.decision`` reflects whether it continued an earlier
        native session.  Nothing is written when the adapter reported no native
        conversation id — a fabricated identity would let a later Run attach to
        the wrong conversation.
        """

        if not isinstance(session, dict):
            return
        conversation_id = session.get("conversation_id")
        save_dir = session.get("save_dir")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return
        if not isinstance(save_dir, str) or not save_dir.strip():
            return
        try:
            run = self._store.read("run", run_id).entity
        except EntityNotFound:
            return
        raw = run.get("continuation")
        planned_source = raw.get("source_run_id") if isinstance(raw, dict) else None
        resumed = str(session.get("state")) == "resumed"
        record = continuation_record(
            conversation_id=conversation_id,
            save_dir=save_dir,
            continuation_mode=(
                MODE_RESUME if resumed else MODE_CREATE_ONLY
            ),
            source_run_id=(
                str(planned_source)
                if isinstance(planned_source, str) and planned_source
                else None
            ),
            resumed=resumed,
        )
        if record is None:
            return
        record["decision"] = "resume" if resumed else "fresh"
        self._writer.write_run(run_id, {"continuation": record})

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
