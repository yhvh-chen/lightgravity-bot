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
import inspect
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, cast, runtime_checkable

from lightgravity.contracts import AppError, ErrorCode, EventType, TaskPhase, TaskStatus
from lightgravity.resources import ResourceService
from lightgravity.sources.selection import (
    SelectedContext,
    compose_prompt,
    parse_selected_sources,
    resolve_context_from_snapshot,
    resolve_selected_sources,
)
from lightgravity.store import (
    EntityNotFound,
    LockConflict,
    Store,
    Versioned,
    new_id,
)
from lightgravity.store.ids import id_matches_kind
from lightgravity.store.locking import LockManager

# LG-017: the rework orchestrator's spawner returns this structural outcome.
# Importing it directly (no cycle: verify.rework depends on coordinator.state,
# not on coordinator.service) keeps the coordinator's port honest without
# duplicating the type.
from lightgravity.verify.rework import SpawnOutcome

from .capacity import CapacityConfig, CapacityGovernor
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

    def check_before_review(self, task_id: str) -> bool: ...

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
        stop_event: Any | None = None,
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


#: Characters that may directly follow the bot mention and still count as a
#: mention (ASCII + common CJK punctuation).
_MENTION_FOLLOW_PUNCT = ",.!?;:)]}、。，！？；：）】》。"

#: An exact legal runtime Task id token: ``task_`` followed by the 26-char
#: Crockford Base32 ULID alphabet used by ``store/ids.py``.  The lookarounds
#: require a standalone token so a longer/differently-prefixed id is not
#: truncated into a valid-looking one.  Crockford excludes I, L, O and U.
_TASK_ID_TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z_])task_[0-9A-HJKMNP-TV-Z]{26}(?![0-9A-Za-z_])"
)
#: A looser "looks like a task reference" detector so a malformed token (wrong
#: length/alphabet/prefix) is reported as invalid rather than silently ignored.
_TASK_REF_LIKE_RE = re.compile(
    r"(?<![0-9A-Za-z_])task_[0-9A-Za-z]{1,}(?![0-9A-Za-z_])"
)


def _parse_task_id_tokens(content: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split pasted Task ID tokens into ``(legal, invalid)`` stable tuples.

    ``legal`` holds exact ``task_<ULID>`` tokens in first-seen order; anything
    task-like that is not an exact legal id is returned in ``invalid``.  This
    lets the global query distinguish "no id" / "malformed id" / "multiple"
    without ever guessing an arbitrary target.
    """

    text = content or ""
    legal: list[str] = []
    for match in _TASK_ID_TOKEN_RE.findall(text):
        if match not in legal:
            legal.append(match)
    legal_set = set(legal)
    invalid: list[str] = []
    for match in _TASK_REF_LIKE_RE.findall(text):
        if match not in legal_set and match not in invalid:
            invalid.append(match)
    return tuple(legal), tuple(invalid)


def _is_bot_mention(content: str, mention: str) -> bool:
    """Whether ``content`` starts with the configured bot mention.

    Leading whitespace is ignored and the mention must be followed by end of
    string, whitespace or punctuation so ``@bottom`` is not a bot call.
    """

    if not mention:
        return False
    stripped = content.lstrip()
    if not stripped.startswith(mention):
        return False
    rest = stripped[len(mention) :]
    if not rest:
        return True
    return rest[0].isspace() or rest[0] in _MENTION_FOLLOW_PUNCT


def _responder_accepts_attachment_context(responder: Callable[..., Any]) -> bool:
    """Whether a responder can receive the separate attachment-context argument."""

    try:
        parameters = inspect.signature(responder).parameters.values()
    except (TypeError, ValueError):  # builtins/partials: keep the safe 2-arg call
        return False
    positional = 0
    for parameter in parameters:
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            return True
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional += 1
    return positional >= 3


def _reject_private_attachment_refs(
    attachments: Any, *, surface: str
) -> None:
    """Private ``attachment_id`` refs are Personal-only (docs/08 §19.3).

    Task/Team messages keep the existing ``{path, media_type?}`` shape.  A
    private id must never be rewritten into a shared path or task attachment.
    """

    if not isinstance(attachments, list):
        return
    if any(isinstance(item, dict) and "attachment_id" in item for item in attachments):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "attachment_id is only accepted by the Personal conversation; "
            "Task/Team messages use path references",
            details={"field": "attachments", "surface": surface},
        )


def _default_responder(content: str, classification: Classification) -> str:
    if classification.intent == MessageIntent.BOUNDED_READ:
        return (
            "This is a bounded read-only request. No Task or Run will be created, "
            "and write or command access is not granted."
        )
    return "I am LightGravity Bot. Describe your delivery goal, or provide a Task ID to check its status."



def _delivery_title(content: str, mention: str) -> str:
    """Use the first request sentence as a compact title, without a model call."""
    text = content.strip()
    if _is_bot_mention(text, mention):
        text = text[len(mention):].lstrip()
    text = " ".join(text.lstrip(":,;：，；").split())
    # A dot inside a filename/URL is not a sentence boundary.
    first = re.split(r"(?<=[.!?])(?:\s+|$)|(?<=[。！？])", text, maxsplit=1)[0]
    first = first.rstrip(".!?。！？").strip()
    if not first:
        return "New task"
    if len(first) <= 60:
        return first
    clipped = first[:59].rstrip()
    # Prefer a nearby word boundary; long tokens still get a bounded title.
    if " " in clipped and len(clipped.rsplit(" ", 1)[0]) >= 40:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped + "…"

def _task_body(objective: str, scope: str | None, acceptance: tuple[str, ...]) -> str:
    lines = ["# Task", "", "## Objective", "", objective.strip(), ""]
    if scope and scope.strip():
        lines += ["## Scope", "", scope.strip(), ""]
    if acceptance:
        lines += ["## Acceptance criteria", ""]
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
            "waiting_reason": None,
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
        source_service: Any | None = None,
        team_mode: bool = False,
        bot_mention: str = "@bot",
        capacity: CapacityConfig | CapacityGovernor | None = None,
    ) -> None:
        self._store = store
        self._owner = owner or f"coordinator:{os.getpid()}"
        self._writer = StateWriter(store, actor=self._owner)
        self._queue = TaskQueue(store, self._writer)
        self._dispatcher = dispatcher or SingleSlotDispatcher(UnavailableExecutor())
        # LG-126: one global governor shared by every Task's graph dispatch and
        # the independent reviewer.  In-memory only; restart starts empty and
        # the recovery scan runs before any admission.
        self._capacity = (
            capacity
            if isinstance(capacity, CapacityGovernor)
            else CapacityGovernor(capacity or CapacityConfig.from_env())
        )
        attach_capacity = getattr(self._dispatcher, "set_capacity_governor", None)
        if callable(attach_capacity):
            attach_capacity(self._capacity)
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
        #: LG-119: whether the injected Personal responder can receive the
        #: separate bounded attachment-context argument.  Existing 2-arg test
        #: lambdas keep working; the real bootstrap dialogue responder accepts it.
        self._responder_accepts_attachment_context = (
            _responder_accepts_attachment_context(self._responder)
        )
        #: LG-054: whether a real direct-answer responder was injected.  When
        #: ``False`` the private Personal channel honestly reports
        #: ``unavailable`` instead of dressing the deterministic fallback up as
        #: a model answer.  The legacy global/Task flows keep the existing
        #: fallback behaviour unchanged.
        self._responder_configured = responder is not None
        self._verification = verification
        self._rework = rework
        self._resource_service = resource_service
        #: Optional LG-043 selected-material service.  When ``None`` the
        #: selected-material fields are still accepted at the wire boundary but
        #: resolution reports an honest ``capability_unavailable`` instead of
        #: pretending to read sources.
        self._source_service = source_service
        #: LG-050 additive team-mode behaviour.  When ``False`` (default) the
        #: coordinator is byte-for-byte the single-user behaviour: global
        #: messages always route and no author is injected.
        self._team_mode = team_mode
        self._bot_mention = bot_mention or "@bot"
        #: Serialises bot turns per global conversation so concurrent requests
        #: (and duplicate ``message_id`` retries) cannot double-run a model.
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        #: Late-bound provider used by the API assembly to share the same
        #: per-app ``app.state.source_service`` the sources router builds.
        self._source_service_provider: Callable[[], Any | None] | None = None
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
        #: Per-Task dispatch jobs (one Task can have at most one non-terminal
        #: Run, but different Tasks execute concurrently inside the governor).
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        #: Reviewer/verification jobs keyed by Run; the reviewer slot is acquired
        #: before the review starts and released only after its real teardown.
        self._verification_tasks: dict[str, asyncio.Task[None]] = {}
        #: LG-022 R1: independent-reviewer lifecycle so a review runs off the
        #: coordinator event loop and can be stopped with confirmation.  Shared
        #: with the control service so pause/cancel can stop a running reviewer.
        from lightgravity.verify.review_lifecycle import ReviewLifecycle

        self._review_lifecycle = ReviewLifecycle()
        #: Runs whose candidate passed review and still need the machine verify
        #: step; drained by the worker loop so the loop stays responsive during
        #: a long independent review (LG-022 D2).
        self._pending_auto_verify: list[tuple[str, str]] = []
        self._control.set_review_lifecycle(self._review_lifecycle)
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

    @property
    def capacity(self) -> CapacityGovernor:
        """The process-global capacity governor (diagnostics/tests)."""

        return self._capacity

    def capacity_snapshot(self) -> dict[str, Any]:
        """Read-only capacity facts for diagnostics; never admits or writes."""

        return self._capacity.snapshot().to_dict()

    def configure_capacity(self, config: CapacityConfig) -> None:
        """Wire startup-resolved config before the worker loop starts."""

        self._capacity = CapacityGovernor(config)
        attach_capacity = getattr(self._dispatcher, "set_capacity_governor", None)
        if callable(attach_capacity):
            attach_capacity(self._capacity)

    @property
    def responder_configured(self) -> bool:
        """Whether a real (model-backed) direct-answer responder is wired."""

        return self._responder_configured

    def _invoke_responder(
        self,
        content: str,
        classification: Classification,
        *,
        attachment_context: str | None = None,
        attachment_note: str | None = None,
    ) -> str:
        """Call the responder with bounded attachment context kept separate.

        The context is never merged into persisted user content.  If the
        injected responder cannot accept it, the reply explicitly says the
        attachment text was not delivered instead of silently claiming it was
        read.
        """

        if (
            attachment_context is not None
            and self._responder_accepts_attachment_context
        ):
            reply = cast(Callable[..., str], self._responder)(
                content, classification, attachment_context
            )
        else:
            reply = self._responder(content, classification)
            if attachment_context is not None:
                attachment_note = (
                    "The configured responder could not receive the attachment "
                    "text; it was not read by the model."
                    if not attachment_note
                    else attachment_note
                    + " The configured responder could not receive the "
                    "attachment text."
                )
        if attachment_note:
            reply = f"{attachment_note}\n\n{reply}" if reply else attachment_note
        return reply

    @property
    def review_lifecycle(self) -> Any:
        """The independent-reviewer lifecycle (LG-022 R1)."""

        from lightgravity.verify.review_lifecycle import ReviewLifecycle

        if not isinstance(self._review_lifecycle, ReviewLifecycle):  # pragma: no cover
            self._review_lifecycle = ReviewLifecycle()
        return self._review_lifecycle

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
        whose ``RunSpawner`` is this coordinator, with an explicit
        :class:`~lightgravity.verify.review.UnavailableReviewer`.

        Honest default (LG-017 R1): a *program-only* machine check is the
        LG-009 gate, **not** an independent review.  Rather than rename it
        ``ProgramReviewer`` and call it independent QA, the unreviewed runtime
        reports ``unavailable`` so acceptance never opens without a real
        reviewer.  A real (model-backed) reviewer is injected by the runtime
        assembly when a reviewer connection is configured; an injected
        orchestrator always wins.  The deterministic ``ProgramReviewer`` is
        still available as an explicit machine-gate reviewer for callers that
        want it wired deliberately.
        """

        if self._rework is not None:
            return self._rework
        # Local import keeps coordinator import graph free of verify at module
        # load time while still wiring a real default at runtime.
        from lightgravity.verify.review import UnavailableReviewer
        from lightgravity.verify.rework import ReworkOrchestrator

        self._rework = ReworkOrchestrator(
            self._store,
            reviewer=UnavailableReviewer(),
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
        jobs = [*self._running_tasks.values(), *self._verification_tasks.values()]
        for job in jobs:
            if not job.done():
                job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        self._running_tasks.clear()
        self._verification_tasks.clear()

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
        default_delivery: bool = False,
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
                default_delivery=default_delivery,
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
        selected_trigger: Mapping[str, Any] | None = None,
        default_delivery: bool = False,
    ) -> dict[str, Any]:
        task_id = new_id("task")
        acceptance = tuple(acceptance_criteria)
        resolved_workspace_ref = workspace_ref
        if default_delivery:
            if not acceptance:
                from .planner import default_acceptance_criteria

                acceptance = default_acceptance_criteria(objective)
            if resolved_workspace_ref is None or not str(resolved_workspace_ref).strip():
                resolved_workspace_ref = self._ensure_default_workspace(task_id)
        content = _task_content(
            title=title,
            objective=objective,
            acceptance=acceptance,
            project_ref=project_ref,
            workspace_ref=resolved_workspace_ref,
            agent_ref=agent_ref or "coordinator",
        )
        if default_delivery:
            # Explicit program policy authorizes only registered, read-only checks.
            content["checks"] = ["evidence-present", "artifacts-in-workspace"]
            content["machine_check_policy"] = "default_delivery_v1"
        cast(_BodyStore, self._store).create(
            "task",
            task_id,
            content,
            actor=self._owner,
            request_id=request_id,
            body=_task_body(objective, scope, acceptance),
        )
        self._writer.emit(
            task_id,
            EventType.TASK_CREATED,
            {"title": title, "request_id": request_id},
            task_ref=task_id,
        )
        # Program-frozen Run trigger association (LG-043 followup): the message
        # that caused this Task to be queued owns the selected-material context
        # for the Run it will spawn.  Stored as internal Task metadata (existing
        # controlled SoT, no public field), transferred to the Run at open time.
        if selected_trigger is not None:
            self._writer.write_task(task_id, {"selected_trigger": dict(selected_trigger)})
        queue_state = "not_queued"
        if enqueue:
            queue_state = self._queue.enqueue(task_id)
        return {
            "kind": "task",
            "reply": f"Created Task {task_id} ({queue_state}).",
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

        In team mode a global message that does not mention the bot is recorded
        only (no model call, no Task).  Bot turns are serialised per
        conversation so a concurrent duplicate retry cannot run twice.
        """

        if not self._team_mode:
            return await self._submit_global_unlocked(
                conversation_id, message, request_id=request_id
            )
        lock = self._conversation_lock(conversation_id)
        async with lock:
            return await self._submit_global_unlocked(
                conversation_id, message, request_id=request_id
            )

    def _conversation_lock(self, conversation_id: str) -> asyncio.Lock:
        lock = self._conversation_locks.get(conversation_id)
        if lock is None:
            lock = asyncio.Lock()
            self._conversation_locks[conversation_id] = lock
        return lock

    async def _submit_global_unlocked(
        self,
        conversation_id: str,
        message: dict[str, Any],
        *,
        request_id: str | None = None,
        attachment_context: str | None = None,
        attachment_note: str | None = None,
        personal_private: bool = False,
    ) -> CoordinatorResult:
        message_id = self._require_message_id(message)
        key = f"message:{message_id}"
        existing = self._idempotency.lookup(key)
        if existing is not None:
            return self._result_from(existing)
        if not personal_private:
            _reject_private_attachment_refs(
                message.get("attachments"), surface="global/team"
            )
        content = str(message.get("content", ""))
        record_only = self._team_mode and not _is_bot_mention(content, self._bot_mention)
        # Ordinary Team messages never consume model context. Keep selected refs
        # as message data without resolving them or persisting a trusted snapshot.
        selected = None if record_only else self._resolve_selected(None, message)
        if selected is not None:
            message = dict(message)
            message["selected_context"] = selected.snapshot()
        record = self._global.append(conversation_id, message)
        if record_only:
            # Ordinary team message: persist only.  No classifier, no responder,
            # no model call, no Task creation.
            result = CoordinatorResult(
                kind="recorded",
                reply="",
                conversation_id=conversation_id,
                data={"intent": "recorded", "creates_task": False},
            )
            self._idempotency.record(key, result.to_dict())
            return result
        routed = message
        if self._team_mode:
            stripped = content.lstrip()[len(self._bot_mention):].lstrip()
            routed = dict(message)
            routed["content"] = stripped
        classification = self._classifier(str(routed.get("content", "")))
        result = await self._route_global(
            conversation_id=conversation_id,
            message=routed,
            record_seq=record.seq,
            classification=classification,
            task_ref=self._message_task_ref(message),
            request_id=request_id or message_id,
            selected=selected,
            attachment_context=attachment_context,
            attachment_note=attachment_note,
            personal_private=personal_private,
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
        selected: SelectedContext | None = None,
        attachment_context: str | None = None,
        attachment_note: str | None = None,
        personal_private: bool = False,
    ) -> CoordinatorResult:
        content = str(message.get("content", ""))
        if classification.next_action in {"direct", "bounded_read"}:
            reply = self._invoke_responder(
                compose_prompt(content, selected),
                classification,
                attachment_context=attachment_context,
                attachment_note=attachment_note,
            )
            data: dict[str, Any] = {
                "intent": classification.intent.value,
                "bounded_tools": list(classification.bounded_tools),
                "creates_task": False,
            }
            if selected is not None:
                data.update(selected.bindings_data())
            # LG-047 QA-R1: persist the real assistant reply (and its additive
            # selected-source bindings) into the same conversation log the user
            # message was written to, so reopening the history shows the reply
            # and its Sources backlinks.  Deterministic id + idempotent append:
            # a retried message never writes a second assistant row.
            self._persist_assistant_reply(
                conversation_id=conversation_id,
                task_id=None,
                in_reply_to=str(message.get("message_id") or request_id),
                reply=reply,
                selected=selected,
                extra={"bounded_tools": list(classification.bounded_tools)},
            )
            return CoordinatorResult(
                kind=classification.next_action,
                reply=reply,
                conversation_id=conversation_id,
                data=data,
            )
        if personal_private:
            reply = (
                "Messages with private attachments stay in Personal chat and do "
                "not create a shared Task. Remove the attachment or use the "
                "shared Team/material flow to create delivery work. Nothing was "
                "created here."
            )
            if attachment_note:
                reply = f"{attachment_note}\n\n{reply}"
            self._persist_assistant_reply(
                conversation_id=conversation_id,
                task_id=None,
                in_reply_to=str(message.get("message_id") or request_id),
                reply=reply,
                selected=None,
                extra={
                    "intent": classification.intent.value,
                    "private": True,
                    "creates_task": False,
                },
            )
            return CoordinatorResult(
                kind="recorded",
                reply=reply,
                conversation_id=conversation_id,
                data={
                    "intent": classification.intent.value,
                    "creates_task": False,
                    "private": True,
                },
            )
        if classification.next_action == "create_task":
            title = _delivery_title(content, self._bot_mention)

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
                    # An ordinary Chat delivery request has neither explicit
                    # acceptance criteria nor a workspace.  The program supplies
                    # both (a real authorized workspace under the configured
                    # root + a derived acceptance criterion) so the default rule
                    # plan validates. New task uses the same default policy.
                    default_delivery=True,
                    selected_trigger=self._trigger_binding(
                        str(message.get("message_id") or request_id), selected
                    ),
                )

            created = self._idempotency.execute(f"message-task:{request_id}", producer)
            created = dict(created)
            created["conversation_id"] = conversation_id
            created["data"] = {"intent": classification.intent.value, "creates_task": True}
            # Keep the creation receipt in the originating conversation, just
            # like direct replies. The Task reservation precedes this append;
            # a retry after interruption reuses the Task and deterministic row.
            self._persist_assistant_reply(
                conversation_id=conversation_id,
                task_id=None,
                in_reply_to=str(message.get("message_id") or request_id),
                reply=str(created["reply"]),
                selected=selected,
                extra={**created["data"], "task_id": created["task_id"],
                       "queue_state": created["queue_state"]},
            )
            return self._result_from(created)
        if classification.next_action == "query":
            # LG-066: a global/Team status query is resolved *only* from an
            # explicit legal Task ID pasted in the message (no contract field,
            # no "nearest active Task" guess).  It reads persisted state and
            # never creates a Task, Run or worker.
            return self._route_global_status_query(
                conversation_id=conversation_id,
                message=message,
                request_id=request_id,
                task_ref=task_ref,
                intent=classification.intent.value,
            )
        target, candidates = self._resolve_target(task_ref)
        if target is None:
            return CoordinatorResult(
                kind="clarify",
                reply="Specify a Task for this control request. No action was taken.",
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
                reply=f"Resume requested for Task {target} ({state}).",
                task_id=target,
                conversation_id=conversation_id,
                queue_state=state,
            )
        return CoordinatorResult(
            kind=classification.next_action,
            reply="Saved to the global conversation. Use the Task conversation for delivery actions.",
            conversation_id=conversation_id,
            data={"intent": classification.intent.value, "record_seq": record_seq},
        )

    # -------------------------------------------------------- personal entry
    async def submit_personal_message(
        self,
        conversation_id: str,
        message: dict[str, Any],
        *,
        owner: str,
        request_id: str | None = None,
        attachment_context: str | None = None,
        attachment_note: str | None = None,
    ) -> CoordinatorResult:
        """Persist and answer one message in a person's private conversation.

        LG-054: the private Personal channel is derived from the authenticated
        server identity by the API layer (never a request field) and is
        **chat-only**.  In team mode it never creates a Task/Run, never
        attaches shared sources, never routes through the shared global/Task
        logs or events, and never asks the responder to start delivery work;
        delivery requests return explicit switch-to-Team guidance instead.  In
        single-user mode there is no privacy boundary to protect, so the legacy
        global behaviour (including delivery Task creation) is preserved
        exactly and the shared global conversation id is reused.
        """

        if not self._team_mode:
            # Single-user Personal is the legacy global conversation.  Only a
            # message carrying private attachment context is forced to stay a
            # private chat turn; ordinary legacy messages keep the exact
            # task-creation behaviour.  The private context is still carried on
            # a separate responder argument, never merged into user content.
            private_turn = (
                attachment_context is not None or attachment_note is not None
            )
            return await self._submit_global_unlocked(
                conversation_id,
                message,
                request_id=request_id,
                attachment_context=attachment_context,
                attachment_note=attachment_note,
                personal_private=private_turn,
            )
        lock = self._conversation_lock(conversation_id)
        async with lock:
            return await self._submit_personal_unlocked(
                conversation_id,
                message,
                owner=owner,
                request_id=request_id,
                attachment_context=attachment_context,
                attachment_note=attachment_note,
            )

    async def _submit_personal_unlocked(
        self,
        conversation_id: str,
        message: dict[str, Any],
        *,
        owner: str,
        request_id: str | None = None,
        attachment_context: str | None = None,
        attachment_note: str | None = None,
    ) -> CoordinatorResult:
        message_id = self._require_message_id(message)
        # Namespace the idempotency key by owner + channel so two users can
        # never collide on a client-supplied message id (LG-054).
        key = f"personal:{owner}:message:{message_id}"
        existing = self._idempotency.lookup(key)
        if existing is not None:
            return self._result_from(existing)
        record = self._global.append(conversation_id, message)
        classification = self._classifier(str(message.get("content", "")))
        result = await self._route_personal(
            conversation_id=conversation_id,
            message=message,
            owner=owner,
            classification=classification,
            record_seq=record.seq,
            request_id=request_id or message_id,
            attachment_context=attachment_context,
            attachment_note=attachment_note,
        )
        self._idempotency.record(key, result.to_dict())
        return result

    async def _route_personal(
        self,
        *,
        conversation_id: str,
        message: dict[str, Any],
        owner: str,
        classification: Classification,
        record_seq: int,
        request_id: str,
        attachment_context: str | None = None,
        attachment_note: str | None = None,
    ) -> CoordinatorResult:
        """Answer a private message without any shared side effect (LG-054)."""

        content = str(message.get("content", ""))
        in_reply_to = str(message.get("message_id") or request_id)
        if classification.next_action in {"direct", "bounded_read"}:
            if not self._responder_configured:
                reply = (
                    "Personal chat is unavailable because no model is configured. "
                    "Configure a model in Settings, or use Team for shared task "
                    "delivery. Nothing was created."
                )
                self._persist_assistant_reply(
                    conversation_id=conversation_id,
                    task_id=None,
                    in_reply_to=in_reply_to,
                    reply=reply,
                    selected=None,
                    extra={"intent": "unavailable", "private": True},
                )
                return CoordinatorResult(
                    kind="unavailable",
                    reply=reply,
                    conversation_id=conversation_id,
                    data={
                        "intent": classification.intent.value,
                        "creates_task": False,
                        "private": True,
                        "unavailable": True,
                    },
                )
            reply = self._invoke_responder(
                content,
                classification,
                attachment_context=attachment_context,
                attachment_note=attachment_note,
            )
            extra: dict[str, Any] = {
                "intent": classification.intent.value,
                "private": True,
            }
            if attachment_context is not None:
                extra["attachment_context_included"] = True
            if attachment_note:
                extra["attachment_context_note"] = True
            self._persist_assistant_reply(
                conversation_id=conversation_id,
                task_id=None,
                in_reply_to=in_reply_to,
                reply=reply,
                selected=None,
                extra=extra,
            )
            return CoordinatorResult(
                kind=classification.next_action,
                reply=reply,
                conversation_id=conversation_id,
                data={
                    "intent": classification.intent.value,
                    "bounded_tools": list(classification.bounded_tools),
                    "creates_task": False,
                    "private": True,
                    "attachment_context_included": attachment_context is not None,
                },
            )
        # Chat-only: never create a shared Task/Run, never invoke the team task
        # coordinator, never write to shared logs/events.
        reply = (
            "Personal chat is chat-only and private to you. To create a task, run "
            "delivery, upload materials, or use shared sources, switch to Team. "
            "Nothing was created here."
        )
        if attachment_note:
            reply = f"{attachment_note}\n\n{reply}"
        self._persist_assistant_reply(
            conversation_id=conversation_id,
            task_id=None,
            in_reply_to=in_reply_to,
            reply=reply,
            selected=None,
            extra={
                "intent": classification.intent.value,
                "private": True,
                "requires_team": True,
            },
        )
        return CoordinatorResult(
            kind="switch_to_team",
            reply=reply,
            conversation_id=conversation_id,
            data={
                "intent": classification.intent.value,
                "creates_task": False,
                "private": True,
                "requires_team": True,
                "switch_to_team": True,
                "record_seq": record_seq,
            },
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
        _reject_private_attachment_refs(
            message.get("attachments"), surface="task"
        )
        # LG-043: resolve optional selected sources before persisting/dispatching.
        # Classification below still uses only the original user content.
        selected = self._resolve_selected(task_id, message)
        if selected is not None:
            message = dict(message)
            message["selected_context"] = selected.snapshot()
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
            # A retry rebinds the Run trigger only when it actually opens a fresh
            # queued Run.  If the Task is already queued/executing, a later
            # message must NOT overwrite the pending Run's trigger: that Run
            # still uses its own trigger's exact saved selection (docs/10 §5/§6).
            # Bind *before* enqueue so the claim/dispatch loop can never open the
            # Run between the state transition and the binding write.
            phase = str(self._store.read("task", task_id).entity.get("phase", ""))
            already_queued = phase in {
                TaskPhase.QUEUED.value,
                TaskPhase.PLANNING.value,
                TaskPhase.RECRUITING.value,
                TaskPhase.EXECUTING.value,
            }
            if not already_queued:
                self._bind_selected_trigger(task_id, message_id, selected)
            state = self._queue.enqueue(task_id)
            result = CoordinatorResult(
                kind="retry",
                reply=f"Resume requested for Task {task_id} ({state}).",
                task_id=task_id,
                queue_state=state,
            )
        elif classification.next_action in {"direct", "bounded_read"}:
            data: dict[str, Any] = {
                "intent": classification.intent.value,
                "creates_run": False,
            }
            if selected is not None:
                data.update(selected.bindings_data())
            reply = self._responder(compose_prompt(content, selected), classification)
            # LG-047 QA-R1: persist the Task-conversation assistant reply with
            # its additive selected-source bindings so reopening the Task chat
            # shows the answer and Sources (frontend normalizes ``message.data``).
            self._persist_assistant_reply(
                conversation_id=None,
                task_id=task_id,
                in_reply_to=message_id,
                reply=reply,
                selected=selected,
                extra={"intent": classification.intent.value},
            )
            result = CoordinatorResult(
                kind=classification.next_action,
                reply=reply,
                task_id=task_id,
                data=data,
            )
        else:
            result = CoordinatorResult(
                kind=classification.next_action,
                reply="Saved to the Task conversation. No new Run was created.",
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
        if self._team_mode:
            # Defense in depth: even if the API admin gate were bypassed, a
            # member-authored proposal is refused here.  The ``author`` field is
            # only ever injected server-side from the resolved session.
            author = message.get("author")
            author_role = author.get("role") if isinstance(author, dict) else None
            if author_role != "admin":
                return self._record_resource_result(
                    task_id,
                    submitted_id,
                    status="unauthorized_source",
                    reply=(
                        "Team-mode resource changes require an administrator "
                        "session; no change was written."
                    ),
                    data={"required_role": "admin"},
                )

        try:
            proposal = parse_resource_proposal(message.get("resource_proposal"))
        except AppError as exc:
            return self._record_resource_result(
                task_id,
                submitted_id,
                status="invalid_proposal",
                reply=f"Invalid resource change proposal: {exc.message}",
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
                    f"{proposal.ref} conflict: expected revision "
                    f"{proposal.expected_revision}, actual "
                    f"{exc.details.get('actual_revision')}. No changes saved; reload and retry."
                )
            else:
                reply = f"{proposal.ref} change rejected ({exc.code.value}): {exc.message}"
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
                f"Saved validated {proposal.kind}:{proposal.resource_id}, "
                f"revision -> {detail['revision']}. Template changes apply to future recruits; "
                f"active members retain their pinned configuration (Task {task_title} context preserved)."
            ),
            data={
                "kind": proposal.kind,
                "id": proposal.resource_id,
                "revision": detail["revision"],
                "etag": detail.get("etag"),
                "task_ref": task_id,
            },
        )

    def _persist_assistant_reply(
        self,
        *,
        conversation_id: str | None,
        task_id: str | None,
        in_reply_to: str,
        reply: str,
        selected: SelectedContext | None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist one assistant reply into the existing conversation SoT.

        The assistant reply is written with the *same* store the
        triggering user message used (global conversation log or the Task
        message log), so reopening the history shows the answer.  The additive
        selected-source bindings are stored under the message's ``data`` field
        that the frontend already normalizes (docs/10 §4) — no new DB, no second
        source of truth, no raw secret/path (bindings only carry the stable
        locator string).  The id is deterministic on the triggering message, so
        an idempotent retry never appends a duplicate assistant row.
        """

        payload: dict[str, Any] = {
            "message_id": f"assistant:{in_reply_to}",
            "role": "assistant",
            "content": reply,
            "in_reply_to": in_reply_to,
            "correlation_id": in_reply_to,
        }
        if self._team_mode:
            payload["author"] = {
                "kind": "bot",
                "username": "bot",
                "role": "assistant",
            }
        data: dict[str, Any] = dict(extra or {})
        if selected is not None:
            data.update(selected.bindings_data())
            # Keep the bounded resolved snapshot on the reply too, so a reload
            # can replay the exact bytes/refs bound to this answer (docs/10 §6)
            # and the assistant row carries the same authorization as its
            # triggering message.  Additive; never a raw path/secret.
            payload["selected_context"] = selected.snapshot()
        if data:
            payload["data"] = data
        if conversation_id is not None:
            self._global.append(conversation_id, payload)
        elif task_id is not None:
            self._store.append_message(task_id, payload)

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
        self._sync_task_admission(task_id)
        if outcome.confirmed and action in {"pause", "cancel"} and outcome.run_id:
            self._cancel_verification_job(outcome.run_id)
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
                return f"Task {task_id}: {action} stop confirmed."
            return f"Task {task_id}: {action} accepted and queued."
        if state == "unconfirmed":
            return f"Task {task_id}: stop for {action} is unconfirmed; cancellation or pause remains pending."
        return f"Task {task_id}: {action} was not applied: {reason or 'not allowed in the current phase'}."

    # ------------------------------------------------- global status query
    def _route_global_status_query(
        self,
        *,
        conversation_id: str,
        message: dict[str, Any],
        request_id: str,
        task_ref: str | None,
        intent: str,
    ) -> CoordinatorResult:
        """Resolve one global/Team status query from an explicit Task ID.

        LG-066: the global route has no ``task_ref`` request field, so the Task
        is identified only by an exact legal ``task_<ULID>`` token pasted in
        the message content (or an internally supplied valid ``task_ref``).
        Missing/malformed/unresolvable/ambiguous targets return an honest
        ``clarify`` instead of guessing the single active Task.  A successful
        query returns the persisted snapshot and never creates a Task/Run, so
        it stays immediate while a worker is busy.  The reply is written to
        the shared global conversation so every logged-in member can see it.
        """

        content = str(message.get("content", ""))
        in_reply_to = str(message.get("message_id") or request_id)

        explicit = task_ref if task_ref and id_matches_kind("task", task_ref) else None
        if explicit is not None:
            legal: tuple[str, ...] = (explicit,)
            invalid: tuple[str, ...] = ()
        else:
            legal, invalid = _parse_task_id_tokens(content)

        if invalid:
            return self._persist_global_query_clarify(
                conversation_id=conversation_id,
                in_reply_to=in_reply_to,
                reply=(
                    "Invalid Task ID: "
                    + ", ".join(invalid)
                    + " (expected task_ followed by 26 Crockford Base32 characters). "
                    "Check the ID and retry. No task was created or started."
                ),
                data={"intent": intent, "invalid_task_ids": list(invalid)},
            )
        if len(legal) > 1:
            return self._persist_global_query_clarify(
                conversation_id=conversation_id,
                in_reply_to=in_reply_to,
                reply=(
                    "Multiple Task IDs found ("
                    + ", ".join(legal)
                    + "). Send one Task ID to select a target. "
                    "No task was created or started."
                ),
                data={"intent": intent, "ambiguous": True, "task_ids": list(legal)},
            )
        if not legal:
            return self._persist_global_query_clarify(
                conversation_id=conversation_id,
                in_reply_to=in_reply_to,
                reply=(
                    "Provide a Task ID (task_…) for this query. "
                    "No task was created or started."
                ),
                data={"intent": intent, "missing_task_id": True},
            )

        task_id = legal[0]
        try:
            snapshot = self._global_status_snapshot(task_id)
        except EntityNotFound:
            return self._persist_global_query_clarify(
                conversation_id=conversation_id,
                in_reply_to=in_reply_to,
                reply=(
                    f"Shared Task {task_id} was not found. Check that it belongs to this workspace. "
                    "No task was created or started."
                ),
                data={"intent": intent, "unknown_task_id": task_id},
            )

        reply = self._global_status_reply(snapshot)
        self._persist_assistant_reply(
            conversation_id=conversation_id,
            task_id=None,
            in_reply_to=in_reply_to,
            reply=reply,
            selected=None,
            extra={"intent": intent, "task_id": task_id, "query": True},
        )
        return CoordinatorResult(
            kind="query",
            reply=reply,
            task_id=task_id,
            conversation_id=conversation_id,
            data=snapshot,
        )

    def _persist_global_query_clarify(
        self,
        *,
        conversation_id: str,
        in_reply_to: str,
        reply: str,
        data: dict[str, Any],
    ) -> CoordinatorResult:
        """Persist an honest query clarification and never create work."""

        self._persist_assistant_reply(
            conversation_id=conversation_id,
            task_id=None,
            in_reply_to=in_reply_to,
            reply=reply,
            selected=None,
            extra={
                "intent": str(data.get("intent", "status_query")),
                "query_clarify": True,
            },
        )
        return CoordinatorResult(
            kind="clarify",
            reply=reply,
            conversation_id=conversation_id,
            data=data,
        )

    def _global_status_snapshot(self, task_id: str) -> dict[str, Any]:
        """Persisted status plus artifact facts for a global query reply.

        ``status()`` supplies phase/queue/active Run; the Task's persisted
        acceptance record supplies the current candidate and canonical evidence
        refs.  This reads the store only -- no worker, Run or model call.
        """

        snapshot = self.status(task_id)
        task = self._store.read("task", task_id)
        acceptance = task.entity.get("acceptance")
        acceptance = acceptance if isinstance(acceptance, dict) else {}
        refs = acceptance.get("evidence_refs")
        snapshot["acceptance_status"] = acceptance.get("status")
        snapshot["candidate_ref"] = acceptance.get("candidate_ref")
        snapshot["artifact_refs"] = [
            ref for ref in (refs or []) if isinstance(ref, str)
        ]
        snapshot["creates_task"] = False
        snapshot["creates_run"] = False
        return snapshot

    @staticmethod
    def _global_status_reply(snapshot: Mapping[str, Any]) -> str:
        queue = snapshot.get("queue")
        queue = queue if isinstance(queue, Mapping) else {}
        parts = [
            f"Task {snapshot['task_id']}: status={snapshot['status']} "
            f"phase={snapshot['phase']} queue={queue.get('state')} "
            f"run={snapshot['run_state']}."
        ]
        candidate = snapshot.get("candidate_ref")
        if isinstance(candidate, str) and candidate:
            parts.append(f"candidate={candidate}")
        refs = snapshot.get("artifact_refs")
        if isinstance(refs, list) and refs:
            parts.append(f"artifacts={len(refs)}")
        parts.append("Read-only query. No Task or Run was created or started.")
        return " ".join(parts)

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
                "waiting_reason": queue.get("waiting_reason"),
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
        """Bounded multi-Task pump.

        The loop admits up to the global active-Task cap and starts each Task's
        dispatch as an independent job.  It never holds the loop across a worker
        execution, so status queries, control actions and other Tasks stay
        responsive.  A third Task remains honestly queued with
        ``waiting_reason=active_task_limit``.
        """

        while not self._stopping:
            try:
                processed = await self._pump_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop must survive a bad task
                processed = False
            if not processed:
                try:
                    await asyncio.sleep(self._poll_interval)
                except asyncio.CancelledError:
                    raise

    async def _pump_once(self) -> bool:
        self._reap_finished_jobs()
        # Verification/reviewer jobs are gated by the shared reviewer sub-cap;
        # a reviewer waits for a real worker session release instead of blocking
        # the pump behind a single worker.
        if self._pending_auto_verify:
            self._schedule_pending_verifications()
            return True
        if self._pending_rework:
            if self._schedule_pending_rework():
                return True
        processed = False
        while self._capacity.has_active_slot():
            summary = self._queue.next_queued()
            if summary is None:
                break
            task_id = summary.id
            if task_id in self._running_tasks:
                break
            if not self._capacity.admit_task(task_id):
                break
            try:
                self._store.claim(task_id, self._owner, lease_seconds=self._lease_seconds)
            except LockConflict:
                self._capacity.release_task(task_id)
                break
            except Exception:  # noqa: BLE001 - one bad Task must not stop the pump
                self._capacity.release_task(task_id)
                break
            self._running_tasks[task_id] = asyncio.create_task(
                self._run_claimed_task(task_id)
            )
            processed = True
        if not self._capacity.has_active_slot():
            self._mark_queued_capacity_waiting()
        return processed

    def _reap_finished_jobs(self) -> None:
        for task_id, job in list(self._running_tasks.items()):
            if not job.done():
                continue
            self._running_tasks.pop(task_id, None)
            try:
                job.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001 - the loop must survive
                self._safe_error(
                    task_id, "worker", "internal_error", f"{type(exc).__name__}: {exc}"
                )
            self._sync_task_admission(task_id)
        for run_id, job in list(self._verification_tasks.items()):
            if not job.done():
                continue
            self._verification_tasks.pop(run_id, None)
            try:
                job.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001 - keep serving other Runs
                try:
                    task_id = str(self._store.read("run", run_id).entity.get("task_ref", ""))
                except EntityNotFound:
                    task_id = ""
                if task_id:
                    self._safe_error(
                        task_id, "verify", "internal_error", f"{type(exc).__name__}: {exc}",
                        run_id=run_id,
                    )

    async def _run_claimed_task(self, task_id: str) -> None:
        """Open and dispatch one already-admitted, claimed Task."""

        try:
            task = self._store.read("task", task_id)
            queue = task.entity.get("queue")
            # The pump creates this job before it gets its first event-loop
            # turn. A queued cancel can win that gap without any Run existing;
            # the late job must not open an orphan Run after confirmed cancel.
            if (
                task.entity.get("phase") != TaskPhase.QUEUED.value
                or not isinstance(queue, dict)
                or queue.get("state") != "claimed"
                or queue.get("owner") != self._owner
            ):
                return
            run_id = self._open_run(task)
            await self._dispatch_run(task, run_id, claimed_event=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - report, never fabricate a Run
            self._safe_error(
                task_id, "worker", "internal_error", f"{type(exc).__name__}: {exc}"
            )
        finally:
            try:
                if self._queue_state(task_id) == "claimed":
                    self._store.release(task_id, self._owner)
            except LockConflict:
                pass
            self._sync_task_admission(task_id)

    def _sync_task_admission(self, task_id: str) -> None:
        """Release the in-memory active-Task slot only after real stop/park.

        The Store phase is authoritative: terminal/paused/recovery/waiting
        phases no longer hold execution resources.  A stale/absent Task is also
        released (it cannot own a live slot forever).
        """

        if not self._capacity.is_admitted(task_id):
            return
        try:
            phase = str(self._store.read("task", task_id).entity.get("phase", ""))
        except EntityNotFound:
            self._capacity.release_task(task_id)
            return
        if phase not in ACTIVE_TASK_PHASES:
            self._capacity.release_task(task_id)

    def _mark_queued_capacity_waiting(self) -> None:
        for summary in self._store.list_tasks():
            if summary.phase != TaskPhase.QUEUED.value or summary.queue_state != "queued":
                continue
            try:
                self._queue.set_waiting_reason(summary.id, "active_task_limit")
            except (AppError, EntityNotFound, LockConflict):
                continue

    def _schedule_pending_verifications(self) -> None:
        while self._pending_auto_verify:
            task_id, run_id = self._pending_auto_verify.pop(0)
            if run_id in self._verification_tasks:
                continue
            try:
                task = self._store.read("task", task_id).entity
            except EntityNotFound:
                continue
            if (
                str(task.get("phase")) != TaskPhase.VERIFYING.value
                or task.get("active_run") != run_id
            ):
                continue
            self._verification_tasks[run_id] = asyncio.create_task(
                self._auto_verify_with_capacity(task_id, run_id)
            )

    async def _auto_verify_with_capacity(self, task_id: str, run_id: str) -> None:
        """Acquire a reviewer/global session slot before the independent review.

        Worker and reviewer share ``max_global_sessions``; the reviewer sub-cap
        gates only the review phase.  Waiting writes the additive
        ``run.waiting_reason=reviewer_limit`` and does not fake acceptance.
        """

        lease = self._capacity.try_acquire_session(
            task_id, kind="reviewer", run_id=run_id
        )
        try:
            if lease is None:
                self._set_run_waiting_reason(run_id, "reviewer_limit")
                lease = await self._capacity.acquire_session(
                    task_id, kind="reviewer", run_id=run_id
                )
            self._set_run_waiting_reason(run_id, None)
            # A cancel/pause may have stopped the Run while this job waited for
            # a reviewer slot.  Never review a stale candidate.
            try:
                task = self._store.read("task", task_id).entity
            except EntityNotFound:
                return
            if (
                str(task.get("phase")) != TaskPhase.VERIFYING.value
                or task.get("active_run") != run_id
            ):
                return
            await self._auto_verify_async(task_id, run_id)
        finally:
            self._capacity.release_session(lease)
            self._verification_tasks.pop(run_id, None)
            self._sync_task_admission(task_id)

    def _cancel_verification_job(self, run_id: str) -> None:
        """Drop a verifier that is still waiting after a confirmed stop.

        Cancel/pause already proved the reviewer/worker stopped through the
        lifecycle/dispatcher.  The waiting verification job would only observe a
        stale phase; cancelling it releases no slot that is not already gone in
        its own ``finally``.
        """

        job = self._verification_tasks.get(run_id)
        if job is not None and not job.done():
            job.cancel()

    def _set_run_waiting_reason(self, run_id: str, reason: str | None) -> None:
        try:
            current = self._store.read("run", run_id).entity
        except EntityNotFound:
            return
        if current.get("waiting_reason") == reason:
            return
        try:
            self._writer.write_run(run_id, {"waiting_reason": reason})
        except (AppError, LockConflict):
            return

    def _safe_error(
        self,
        task_id: str,
        mode: str,
        code: str,
        message: str,
        *,
        run_id: str | None = None,
    ) -> None:
        try:
            self._writer.emit(
                task_id,
                EventType.ERROR_RECORDED,
                {"mode": mode, "code": code, "message": message},
                task_ref=task_id,
                run_ref=run_id,
            )
        except Exception:  # noqa: BLE001 - diagnostics must never crash the pump
            return

    def _schedule_pending_rework(self) -> bool:
        if not self._pending_rework:
            return False
        task_id, findings = self._pending_rework.pop(0)
        if task_id in self._running_tasks:
            self._pending_rework.insert(0, (task_id, findings))
            return False
        if not self._capacity.admit_task(task_id):
            self._pending_rework.insert(0, (task_id, findings))
            return False
        self._running_tasks[task_id] = asyncio.create_task(
            self._run_rework_job(task_id, findings)
        )
        return True

    async def _run_rework_job(
        self, task_id: str, findings: tuple[dict[str, Any], ...]
    ) -> None:
        try:
            await self._dispatch_rework_item(task_id, findings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - report, never fabricate a Run
            self._safe_error(
                task_id, "rework", "internal_error", f"{type(exc).__name__}: {exc}"
            )
        finally:
            self._sync_task_admission(task_id)

    async def _process_one(self) -> bool:
        """Process one unit synchronously (legacy/direct-driver compatibility).

        The resident ``_run_loop`` uses the concurrent ``_pump_once``; this
        method remains a deterministic one-shot for existing callers.  It still
        honours the global active-Task and reviewer caps.
        """

        if self._pending_auto_verify:
            task_id, run_id = self._pending_auto_verify[0]
            self._pending_auto_verify.pop(0)
            await self._auto_verify_with_capacity(task_id, run_id)
            return True
        if self._pending_rework:
            return await self._process_rework()
        summary = self._queue.next_queued()
        if summary is None:
            return False
        task_id = summary.id
        if not self._capacity.admit_task(task_id):
            self._queue.set_waiting_reason(task_id, "active_task_limit")
            return False
        try:
            self._store.claim(task_id, self._owner, lease_seconds=self._lease_seconds)
        except LockConflict:
            self._capacity.release_task(task_id)
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
            self._sync_task_admission(task_id)

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
        """Open and dispatch one queued LG-017 rework Run (one-shot driver)."""

        if not self._pending_rework:
            return False
        task_id, findings = self._pending_rework.pop(0)
        if not self._capacity.admit_task(task_id):
            self._pending_rework.insert(0, (task_id, findings))
            return False
        try:
            processed = await self._dispatch_rework_item(task_id, findings)
        finally:
            self._sync_task_admission(task_id)
        return processed

    async def _dispatch_rework_item(
        self, task_id: str, findings: tuple[dict[str, Any], ...]
    ) -> bool:
        """Dispatch one already-dequeued rework item (legacy and pump paths)."""

        try:
            task = self._store.read("task", task_id)
        except EntityNotFound:
            return False
        phase = str(task.entity.get("phase", ""))
        if phase != TaskPhase.REPAIRING.value:
            self._safe_error(
                task_id,
                "rework",
                "not_ready",
                f"rework dropped: task phase is {phase!r}, not repairing",
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
            self._safe_error(
                task_id,
                "rework",
                "not_ready",
                f"could not open rework Run: {type(exc).__name__}: {exc}",
            )
            return True
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

    def _historical_run(self, task_id: str) -> tuple[str, dict[str, Any]] | None:
        """Recover a legacy missing last_run from attributed creation events.

        Task events locate candidates; the Run entity remains authoritative for
        ownership, state and attempt. Never infer history from directory names,
        another Task's events, or an event's claimed attempt counter.
        """
        after_seq = 0
        latest: tuple[str, dict[str, Any]] | None = None
        while True:
            events = self._store.read_events(task_id, after_seq=after_seq, limit=500)
            if not events:
                return latest
            for record in events:
                event = record.event
                payload = event.get("payload")
                if record.type != EventType.RUN_CREATED or event.get("task_ref") != task_id:
                    continue
                run_id = event.get("run_ref")
                if (
                    not isinstance(run_id, str) or not run_id
                    or not isinstance(payload, dict) or payload.get("run_id") != run_id
                ):
                    continue
                try:
                    run = self._store.read("run", run_id).entity
                except EntityNotFound:
                    continue
                if run.get("task_ref") == task_id:
                    latest = (run_id, run)
            next_seq = events[-1].seq
            if next_seq <= after_seq:
                return latest
            after_seq = next_seq

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

        if source_run is None:
            historical = self._historical_run(task.entity_id)
            if historical is not None:
                active, source_run = historical
        if source_run is not None:
            if source_run.get("task_ref") != task.entity_id:
                raise AppError(ErrorCode.ILLEGAL_TRANSITION, "previous Run belongs to another Task")
            if str(source_run.get("state")) not in TERMINAL_RUN_STATES | {"paused"}:
                raise AppError(
                    ErrorCode.ILLEGAL_TRANSITION,
                    "Task history contains a non-terminal Run; not opening a second writer",
                )

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
        # Freeze the Run's selected-material binding to its exact trigger message
        # (internal metadata; no public field).  ``None`` means the trigger had
        # no selection, so this Run must not inherit another message's context.
        trigger = task.entity.get("selected_trigger")
        if isinstance(trigger, dict):
            run_content["selected_trigger"] = dict(trigger)
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

    def _selected_resolver(self, task_ref: str | None) -> Any:
        """Return a Task-scoped selection resolver, or raise honestly when unwired.

        Raised errors happen **before** any product model dispatch.
        """

        service = self._source_service
        if service is None and self._source_service_provider is not None:
            try:
                service = self._source_service_provider()
            except Exception:  # noqa: BLE001 - a wiring gap is capability_unavailable
                service = None
        if service is None:
            raise AppError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "selected sources are not available: no source service is wired",
                details={"capability": "selected_sources"},
            )
        build = getattr(service, "selected_source_resolver", None)
        if build is None:  # pragma: no cover - defensive wiring gap
            raise AppError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "selected sources are not available",
                details={"capability": "selected_sources"},
            )
        return build(task_ref)

    def set_source_service_provider(
        self, provider: Callable[[], Any | None] | None
    ) -> None:
        """Late-bind the per-app source service (LG-043 API assembly)."""

        self._source_service_provider = provider

    def _resolve_selected(
        self, task_ref: str | None, message: dict[str, Any]
    ) -> SelectedContext | None:
        """Resolve a message's optional ``selected_sources`` before any model call.

        Returns ``None`` for legacy messages that omit the field, so the
        no-selection path stays byte-for-byte unchanged.  A malformed ref,
        stale/revoked/cross-Task source or unwired service raises the frozen
        error **before** any product model dispatch.
        """

        refs = parse_selected_sources(message.get("selected_sources"))
        if not refs:
            return None
        resolver = self._selected_resolver(task_ref)
        return resolve_selected_sources(resolver, refs)

    @staticmethod
    def _trigger_binding(
        message_id: str, selected: SelectedContext | None
    ) -> dict[str, Any]:
        """Program-frozen Run trigger binding (internal metadata only).

        Records the exact message that triggered the queued work and the
        resolved selected-context snapshot at that moment.  ``snapshot`` is
        ``None`` when the trigger carried no selection (legacy/no-selection), so
        the Run it spawns never inherits a different message's selection.
        """

        return {
            "message_id": message_id,
            "snapshot": selected.snapshot() if selected is not None else None,
        }

    def _bind_selected_trigger(
        self, task_id: str, message_id: str, selected: SelectedContext | None
    ) -> None:
        """Bind the Task's queued Run to its exact trigger message.

        Called only when a message actually opens a fresh queued Run, and it
        replaces any earlier binding (including one whose ``snapshot`` is
        ``None``), so a Run never silently reuses an older selection
        (docs/10 §5/§6).
        """

        try:
            self._writer.write_task(
                task_id, {"selected_trigger": self._trigger_binding(message_id, selected)}
            )
        except EntityNotFound:  # pragma: no cover - task exists at call sites
            return

    def _run_selected_snapshot(self, run_id: str) -> dict[str, Any] | None:
        """The selected snapshot bound to *this Run's* trigger message.

        Reads the internal ``selected_trigger`` metadata written when the Run
        was opened (from the Task's frozen trigger association).  Never scans
        the conversation for a "latest" snapshot: a Run must use the selection
        of its own trigger, not a later message's.
        """

        try:
            run = self._store.read("run", run_id).entity
        except EntityNotFound:
            return None
        trigger = run.get("selected_trigger")
        if not isinstance(trigger, dict):
            return None
        snapshot = trigger.get("snapshot")
        return snapshot if isinstance(snapshot, dict) else None

    def _worker_selected_context(self, task_id: str, run_id: str) -> SelectedContext | None:
        """Revalidate the Run-bound selected snapshot before worker dispatch.

        Uses the *saved* bytes/refs from the Run's trigger message and re-reads
        current source state; a changed/revoked source is reported as
        ``source_stale``/``not_found`` rather than silently replayed with
        different content (docs/10 §5/§6).
        """

        snapshot = self._run_selected_snapshot(run_id)
        if snapshot is None:
            return None
        resolver = self._selected_resolver(task_id)
        return resolve_context_from_snapshot(resolver, snapshot)

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
        # LG-043: revalidate the persisted selected snapshot *before* worker
        # dispatch and pass the same exact body the chat reply used.  A source
        # that changed/revoked since resolution raises here (source_stale /
        # not_found) instead of dispatching stale authorization.
        selected = self._worker_selected_context(task.entity_id, run_id)
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
            selected_body=selected.body if selected else None,
            selected_bindings=(
                tuple(b.to_dict() for b in selected.bindings) if selected else ()
            ),
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

    def _ensure_default_workspace(self, task_id: str) -> str:
        """Provision and return the default authorized workspace ref for a Task.

        Used for default delivery tasks, including New task, with no workspace.
        The ref is a Task-scoped directory *inside* the configured authorized
        workspace root (``Store.resolve_path`` enforces containment), so it is a
        real boundary the worker may write within; it never escapes the root and
        creates no new root.  The directory is created because the executor
        requires an existing directory.
        """

        ref = f"tasks/{task_id}"
        try:
            resolved = self._store.resolve_path(ref, write=True)
            resolved.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - fail honestly without persisting a false workspace
            raise AppError(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "Default task workspace could not be created",
                details={"task_id": task_id},
            ) from exc
        return ref

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
        run_extra: dict[str, Any] = {"waiting_reason": None}
        if run_state in {"failed", "cancelled"}:
            run_extra["ended_at"] = _now_iso()
        # LG-022 D3: only a real failure/cancellation may carry ``fail_reason``.
        # A succeeded Run whose summary is just "all N subtask(s) passed" must
        # not be presented as failed to the Board/UI.
        if run_state in {"failed", "cancelled"} and (outcome.failure_message or outcome.summary):
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
            # Keep genuine attempt/session lineage after clearing the live
            # pointer; Retry must advance this Task's delivery history.
            self._writer.write_task(task_id, {"last_run": run_id, "active_run": None})
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
            # LG-022 D2: do not run the (potentially long) independent review
            # inline on this event loop.  Queue it so the worker loop can drain
            # it while continuing to serve status/control.
            self._pending_auto_verify.append((task_id, run_id))

    def _auto_verify(self, task_id: str, run_id: str) -> None:
        """Run machine checks, independent review, then the stop gate after delivery.

        The machine gate records real outcomes before the independent reviewer
        inspects the candidate. Only passing checks and review proceed to
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
        if verifier is not None and not verifier.check_before_review(task_id):
            return
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

    async def _auto_verify_async(self, task_id: str, run_id: str) -> None:
        """Non-blocking independent review + machine verify (LG-022 R1 / D2).

        Same order/semantics as :meth:`_auto_verify`, but the (long) synchronous
        review runs on the reviewer lifecycle's worker thread via the loop's
        default executor, so the coordinator event loop keeps serving status and
        control while the review is in flight.  A stop request (pause/cancel)
        sets the lifecycle stop event; the runner observes it at a safe boundary
        and raises :class:`ReviewStopped`, which we report honestly without
        fabricating a review outcome.
        """

        from lightgravity.verify.review_lifecycle import (
            ReviewStopped,
            run_review_off_loop,
        )

        verifier = self._verification
        rework = self._resolved_rework()
        lifecycle = self.review_lifecycle
        if verifier is not None and not verifier.check_before_review(task_id):
            return
        if rework is not None:
            loop = asyncio.get_running_loop()

            def runner(stop_event: Any) -> Any:
                return rework.process(
                    task_id,
                    request_id=f"auto-review:{run_id}",
                    stop_event=stop_event,
                )

            try:
                outcome = await run_review_off_loop(
                    loop, lifecycle, task_id, run_id, runner
                )
            except ReviewStopped:
                # Honest stop: the reviewer was asked to stop and did.  Do not
                # spend a round or open acceptance; the Run/phase is owned by
                # the control path that requested the stop.
                self._writer.emit(
                    task_id,
                    EventType.ERROR_RECORDED,
                    {
                        "mode": "review",
                        "code": "review_stopped",
                        "message": "independent review stopped by control request",
                    },
                    task_ref=task_id,
                    run_ref=run_id,
                )
                return
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
            self._record_reviewer_stop(run_id, outcome)
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

    def _record_reviewer_stop(self, run_id: str, outcome: Any) -> None:
        """Persist the reviewer's real resource stop fact on the Run (LG-022 R2).

        The reviewer is a separate SDK agent + loopback proxy from the worker.
        When the real reviewer turn ran, its teardown fact proves the reviewer
        resource stopped; the stop gate reads it so releasing a candidate never
        relies on the worker stop alone.  No fact (program reviewer / no real
        turn) writes nothing -- never a fabricated stop.
        """

        fact = getattr(outcome, "reviewer_stop_fact", None)
        if not isinstance(fact, dict) or not fact:
            return
        try:
            task_ref = str(self._store.read("run", run_id).entity.get("task_ref", ""))
        except EntityNotFound:  # pragma: no cover - run vanished mid-review
            return
        status = "done" if fact.get("confirmed") else "pending"
        self._writer.write_run(run_id, {"reviewer_cleanup": {"status": status, **fact}})
        self._writer.emit(
            task_ref,
            EventType.CLEANUP_UPDATED,
            {"scope": "reviewer", "status": status, **fact},
            task_ref=task_ref,
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
