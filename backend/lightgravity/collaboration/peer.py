"""Controlled peer collaboration: requests, results and artifact handoff (LG-030).

This is the program authority for the frozen peer endpoints
``POST/GET /runs/{run_id}/collab_requests`` (docs/08 §4.3).  A worker may
*request* collaboration and *hand off* artifacts; only this module validates and
persists, and it never lets the request body grant permission, create a new
Task/Run, or bypass verification.

What is enforced here (LG-028 preparation §4.1-§4.4, docs/08 §4.3/§6.2/§6.3):

* **Causal binding** - every request carries ``task``/``run``/``node`` +
  ``message_id`` + ``correlation_id`` (``context.validate_binding``); a response
  links back with ``in_reply_to``.
* **Authorization** - the requester and responder must both be members of the
  *same Run*; a request that names a Subtask/Member/artifact from another
  Task/Run is refused with a definite ``cross_task``/``unknown_*`` reason.
* **Summary, not content** - only a bounded authorized summary and versioned
  artifact refs are accepted.  Instruction-like text is stored verbatim and
  flagged, never executed (``context.classify_summary``); artifact *content* is
  never read.
* **Versioned handoff** - refs are parsed/validated by
  :mod:`lightgravity.collaboration.handoff`; evidence refs must resolve for the
  owning Task/Run and digest-match, and are never re-served across Tasks.
* **Budget/capacity/timeout** - a per-Run collaboration count, a per-Task
  ``max_repair_rounds``-style budget and an adaptive timeout gate every request.
  Exhaustion returns a definite ``budget_exhausted`` result and never a wait
  loop, so a peer can never be awaited indefinitely (no infinite recursion, no
  new Run/Task).
* **Idempotency** - ``request_id`` is replayed from the persisted JSONL log, so a
  duplicate returns the first result (and a duplicate handoff is not re-applied).

The default path is unchanged: when ``collab_requests_enabled`` is false
(docs/08 §6.5), the service refuses with ``feature_disabled`` and the
deterministic scheduler is untouched.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lightgravity.contracts import AppError, ErrorCode, EventType
from lightgravity.store import EntityNotFound, Store
from lightgravity.store.atomic import append_jsonl, load_jsonl
from lightgravity.store.clock import Clock, from_iso, plus_seconds, to_iso, utcnow
from lightgravity.store.locking import LockManager

from .context import (
    COLLAB_MODES,
    REQUEST_STATES,
    AuthorizedSummary,
    CausalBinding,
    ContextError,
    classify_summary,
    validate_binding,
)
from .handoff import HandoffError, validate_handoff_refs
from .models import fence_of

#: Bounded per-Run collaboration requests when the Task budget does not set a
#: dedicated ceiling.  Prevents a worker from fanning out unlimited peers.
DEFAULT_MAX_COLLAB_REQUESTS = 8

#: Default per-request wall-clock budget.  A request that would exceed it is
#: refused up front; nothing here blocks waiting for a peer.
DEFAULT_COLLAB_TIMEOUT_SECONDS = 120

#: Maximum accepted ``timeout_seconds`` on a single request (bounded waiting).
MAX_COLLAB_TIMEOUT_SECONDS = 600

#: Fraction of the Task ``budget`` treated as the collaboration allowance when
#: no explicit key is present.  Kept conservative: collaboration is a supplement
#: to the delivery budget, not a second budget.
_BUDGET_SHARE = 0.5


class CollabRefused(AppError):
    """A peer request the program refuses, carrying a stable machine ``reason``."""

    def __init__(self, reason: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        merged: dict[str, Any] = {"reason": reason}
        if details:
            merged.update(details)
        super().__init__(ErrorCode.CLAIM_REFUSED, message, details=merged)
        self.reason = reason


class HandoffRejected(AppError):
    """A handoff carrying an unauthorized/stale artifact ref (never applied)."""

    def __init__(self, reason: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        merged: dict[str, Any] = {"reason": reason}
        if details:
            merged.update(details)
        super().__init__(ErrorCode.REFERENCE_INVALID, message, details=merged)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class CollabRequestResult:
    """Immutable, JSON-ready result of one peer request (request or handoff)."""

    request_id: str
    run_ref: str
    node_ref: str
    from_member_ref: str
    to_member_ref: str | None
    mode: str
    state: str
    reason: str
    correlation_id: str
    message_id: str
    summary: AuthorizedSummary
    handoff_refs: tuple[str, ...]
    produced_refs: tuple[str, ...]
    fence: int
    at: str
    idempotent_replay: bool = False
    budget_remaining: int | None = None
    timeout_seconds: int = DEFAULT_COLLAB_TIMEOUT_SECONDS
    attempt: int = 1
    rejected_refs: tuple[str, ...] = ()
    binding: CausalBinding | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "lightgravity.bot/v1",
            "kind": "collab_request",
            "request_id": self.request_id,
            "run_ref": self.run_ref,
            "task_ref": self.binding.task_ref if self.binding else None,
            "node_ref": self.node_ref,
            "from_member_ref": self.from_member_ref,
            "to_member_ref": self.to_member_ref,
            "mode": self.mode,
            "state": self.state,
            "reason": self.reason,
            "correlation_id": self.correlation_id,
            "message_id": self.message_id,
            "summary": self.summary.to_dict(),
            "handoff_refs": list(self.handoff_refs),
            "produced_refs": list(self.produced_refs),
            "rejected_refs": list(self.rejected_refs),
            "fence": self.fence,
            "at": self.at,
            "idempotent_replay": self.idempotent_replay,
            "budget_remaining": self.budget_remaining,
            "timeout_seconds": self.timeout_seconds,
            "attempt": self.attempt,
        }


class _CollabLog:
    """Append-only ``request_id -> result`` log with flock (idempotency SoT).

    The log is a JSONL history (rebuildable, like every other event log in the
    project) and the *only* place a peer request is recorded.  ``request_id`` is
    the idempotency key: the first result wins and is replayed verbatim, so a
    duplicate or a restart cannot apply a second handoff.
    """

    def __init__(self, data_dir: Path | str, *, clock: Clock = utcnow) -> None:
        self._path = Path(data_dir) / "collaboration" / "collab_requests.jsonl"
        self._clock = clock
        self._locks = LockManager(Path(data_dir) / "locks", default_timeout=10.0)

    @property
    def path(self) -> Path:
        return self._path

    def _lock_key(self, run_id: str) -> str:
        return f"collab:{run_id}"

    def load(self, run_id: str) -> dict[str, dict[str, Any]]:
        with self._locks.acquire(self._lock_key(run_id)):
            records, _ = load_jsonl(self._path)
        entries: dict[str, dict[str, Any]] = {}
        for record in records:
            if record.get("run_ref") != run_id:
                continue
            request_id = record.get("request_id")
            if isinstance(request_id, str) and request_id:
                entries[request_id] = record
        return entries

    def get(self, run_id: str, request_id: str) -> dict[str, Any] | None:
        return self.load(run_id).get(request_id)

    def append(self, record: dict[str, Any]) -> None:
        run_id = record.get("run_ref")
        key = self._lock_key(run_id if isinstance(run_id, str) and run_id else "unknown")
        with self._locks.acquire(key):
            append_jsonl(self._path, record)

    def count(self, run_id: str) -> int:
        return len(self.load(run_id))

    def transaction(self, run_id: str) -> "_CollabTransaction":
        """Hold the per-Run lock across a read-decide-append critical section.

        Idempotency and the per-Run budget are only sound if the *decision* and
        the append happen while no other process can interleave.  Two workers
        presenting the same ``request_id`` (or racing the last budget slot) must
        therefore serialize here, inside the same ``flock`` scope as
the log
        itself - never last-write-wins.
        """

        return _CollabTransaction(self, run_id)


class _CollabTransaction:
    """Context manager giving a locked snapshot of one Run's requests."""

    def __init__(self, log: "_CollabLog", run_id: str) -> None:
        self._log = log
        self._run_id = run_id
        self._context: Any = None
        self.entries: dict[str, dict[str, Any]] = {}

    def __enter__(self) -> "_CollabTransaction":
        self._context = self._log._locks.acquire(self._log._lock_key(self._run_id))  # noqa: SLF001
        self._context.__enter__()
        records, _ = load_jsonl(self._log.path)
        for record in records:
            if record.get("run_ref") != self._run_id:
                continue
            request_id = record.get("request_id")
            if isinstance(request_id, str) and request_id:
                self.entries.setdefault(request_id, record)
        return self

    def __exit__(self, *exc: object) -> None:
        self._context.__exit__(*exc)

    def get(self, request_id: str) -> dict[str, Any] | None:
        entry = self.entries.get(request_id)
        return dict(entry) if entry is not None else None

    def count(self) -> int:
        return len(self.entries)

    def append(self, record: dict[str, Any]) -> None:
        request_id = record.get("request_id")
        if isinstance(request_id, str) and request_id:
            self.entries[request_id] = record
        append_jsonl(self._log.path, record)


@dataclass(slots=True)
class _RunFacts:
    """The authoritative Run/Subtask facts a request is authorized against."""

    task_ref: str
    run_ref: str
    subtask_refs: set[str] = field(default_factory=set)
    member_refs: set[str] = field(default_factory=set)
    subtask_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)


class PeerService:
    """Program authority for controlled peer requests and artifact handoff."""

    def __init__(
        self,
        store: Store,
        *,
        data_dir: Path | str,
        policy: Any = None,
        actor: str = "coordinator",
        clock: Clock = utcnow,
        max_requests: int = DEFAULT_MAX_COLLAB_REQUESTS,
        default_timeout_seconds: int = DEFAULT_COLLAB_TIMEOUT_SECONDS,
    ) -> None:
        self._store = store
        self._data_dir = Path(data_dir)
        self._policy = policy
        self._actor = actor
        self._clock = clock
        self._max_requests = max_requests
        self._default_timeout = default_timeout_seconds
        self._log = _CollabLog(self._data_dir, clock=clock)

    # ------------------------------------------------------------------ policy
    @property
    def enabled(self) -> bool:
        return bool(getattr(self._policy, "collab_requests_enabled", False))

    # ------------------------------------------------------------------- facts
    def _run_facts(self, run_id: str) -> _RunFacts | None:
        try:
            run = self._store.read("run", run_id).entity
        except EntityNotFound:
            return None
        except Exception:  # noqa: BLE001 - unreadable Run is not authorizable
            return None
        task_ref = run.get("task_ref")
        if not isinstance(task_ref, str) or not task_ref:
            return None
        facts = _RunFacts(task_ref=task_ref, run_ref=run_id)
        refs = run.get("subtask_refs")
        if isinstance(refs, list):
            facts.subtask_refs = {ref for ref in refs if isinstance(ref, str)}
        team_refs = run.get("team_refs")
        if isinstance(team_refs, list):
            facts.member_refs = {ref for ref in team_refs if isinstance(ref, str)}
        for ref in facts.subtask_refs:
            try:
                entity = self._store.read("subtask", ref).entity
            except Exception:  # noqa: BLE001 - skip unreadable nodes
                continue
            facts.subtask_by_id[ref] = entity
        return facts

    def _task_budget(self, task_ref: str) -> dict[str, Any]:
        try:
            entity = self._store.read("task", task_ref).entity
        except Exception:  # noqa: BLE001 - missing Task budgets use defaults
            return {}
        budget = entity.get("budget")
        return budget if isinstance(budget, dict) else {}

    def _budget_ceiling(self, task_ref: str) -> int | None:
        """Resolve the Task's collaboration request allowance.

        ``budget.max_collab_requests`` wins when present; otherwise a
        conservative share of ``max_repair_rounds``/``max_workers`` is used so
        collaboration cannot exceed the delivery budget.  ``None`` means the
        system default applies.
        """

        budget = self._task_budget(task_ref)
        explicit = budget.get("max_collab_requests")
        if isinstance(explicit, int) and not isinstance(explicit, bool) and explicit >= 0:
            return explicit
        for key in ("max_workers", "max_parallel", "max_repair_rounds"):
            value = budget.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return max(1, int(value * (1 + _BUDGET_SHARE)))
        return None

    # ------------------------------------------------------------------ public
    def request(
        self,
        run_id: str,
        *,
        request_id: str,
        from_member_ref: str,
        to_member_ref: str | None,
        mode: str,
        summary: str,
        node_ref: str,
        message_id: str,
        correlation_id: str,
        handoff_refs: list[str] | tuple[str, ...] = (),
        fence: int | None = None,
        timeout_seconds: int | None = None,
        in_reply_to: str | None = None,
    ) -> CollabRequestResult:
        """Decide one peer request and persist it; idempotent on ``request_id``.

        Every refusal is a *definite* result, never a wait: feature off, unknown
        Run/node/peer, cross-Task, capability/permission, budget, capacity and
        timeout all return a terminal ``state`` with a machine ``reason``.
        """

        if not self.enabled:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="feature_disabled",
                state="rejected",
            )

        # Everything below runs inside one per-Run critical section so that
        # idempotency (``request_id``) and the per-Run budget cannot be raced by
        # another process; the decision and the append are atomic together.
        with self._log.transaction(run_id) as txn:
            return self._decide(
                run_id=run_id,
                request_id=request_id,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                summary=summary,
                node_ref=node_ref,
                message_id=message_id,
                correlation_id=correlation_id,
                handoff_refs=handoff_refs,
                fence=fence,
                timeout_seconds=timeout_seconds,
                in_reply_to=in_reply_to,
                txn=txn,
            )

    def _decide(
        self,
        *,
        run_id: str,
        request_id: str,
        from_member_ref: str,
        to_member_ref: str | None,
        mode: str,
        summary: str,
        node_ref: str,
        message_id: str,
        correlation_id: str,
        handoff_refs: list[str] | tuple[str, ...],
        fence: int | None,
        timeout_seconds: int | None,
        in_reply_to: str | None,
        txn: "_CollabTransaction",
    ) -> CollabRequestResult:
        """The decision body, executed while holding the per-Run lock."""

        # Idempotency: a duplicate request_id replays the first result verbatim.
        prior = txn.get(request_id)
        if prior is not None:
            return _replay(prior)

        facts = self._run_facts(run_id)
        if facts is None:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="unknown_run",
                state="rejected",
                txn=txn,
            )

        binding: CausalBinding | None = None
        try:
            binding = validate_binding(
                task_ref=facts.task_ref,
                run_ref=run_id,
                node_ref=node_ref,
                message_id=message_id,
                correlation_id=correlation_id,
                in_reply_to=in_reply_to,
            )
        except ContextError as exc:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason=f"invalid_binding:{exc}",
                state="rejected",
                txn=txn,
            )

        if mode not in COLLAB_MODES:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="invalid_mode",
                state="rejected",
                binding=binding,
                txn=txn,
            )

        # The requester must be part of this Run (never an arbitrary browser id).
        if from_member_ref not in facts.member_refs:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="requester_not_in_run",
                state="rejected",
                binding=binding,
                txn=txn,
            )

        # The node must belong to this Run (cross-Task leakage guard).
        entity = facts.subtask_by_id.get(node_ref)
        if node_ref not in facts.subtask_refs or entity is None:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="unknown_node",
                state="rejected",
                binding=binding,
                txn=txn,
            )

        # Fencing: a request from an old holder must not act on a reclaimed node.
        current_fence = fence_of(entity)
        if fence is not None and fence != current_fence:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="stale_lease",
                state="rejected",
                binding=binding,
                fence=current_fence,
                txn=txn,
            )

        # Responder (when named) must be in the same Run.
        if to_member_ref is not None and to_member_ref not in facts.member_refs:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="responder_not_in_run",
                state="rejected",
                binding=binding,
                txn=txn,
            )

        # Summary is data: validate, then classify; never executed.
        try:
            authorized = classify_summary(summary)
        except ContextError as exc:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason=f"summary_rejected:{exc}",
                state="rejected",
                binding=binding,
                txn=txn,
            )

        # Versioned/hashed handoff refs, authorized for this Task/Run only.
        try:
            validated_refs = validate_handoff_refs(
                tuple(handoff_refs),
                data_dir=self._data_dir,
                task_id=facts.task_ref,
                run_id=run_id,
                workspace_root=getattr(self._store, "workspace_root", None),
                known_subtask_refs=facts.subtask_refs,
            )
        except HandoffError as exc:
            result = self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason=f"handoff_rejected:{exc}",
                state="rejected",
                binding=binding,
                rejected_refs=tuple(handoff_refs),
                txn=txn,
            )
            self._emit_rejected(run_id, result)
            return result

        # Budget / capacity / timeout gates (all definite, no waiting).
        ceiling = self._budget_ceiling(facts.task_ref)
        used = txn.count()
        if ceiling is not None and used >= ceiling:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="budget_exhausted",
                state="rejected",
                binding=binding,
                budget_remaining=0,
                txn=txn,
            )

        timeout = self._resolve_timeout(timeout_seconds)
        if timeout is None:
            return self._refuse(
                run_id=run_id,
                request_id=request_id,
                node_ref=node_ref,
                from_member_ref=from_member_ref,
                to_member_ref=to_member_ref,
                mode=mode,
                message_id=message_id,
                correlation_id=correlation_id,
                summary_text=summary,
                reason="timeout_exceeds_capacity",
                state="rejected",
                binding=binding,
                txn=txn,
            )

        attempt = used + 1
        produced = tuple(ref.raw for ref in validated_refs)
        now = to_iso(self._clock())
        result = CollabRequestResult(
            request_id=request_id,
            run_ref=run_id,
            node_ref=node_ref,
            from_member_ref=from_member_ref,
            to_member_ref=to_member_ref,
            mode=mode,
            state="requested",
            reason="accepted",
            correlation_id=correlation_id,
            message_id=message_id,
            summary=authorized,
            handoff_refs=tuple(handoff_refs),
            produced_refs=produced,
            fence=current_fence,
            at=now,
            budget_remaining=(ceiling - attempt if ceiling is not None else None),
            timeout_seconds=timeout,
            attempt=attempt,
            binding=binding,
        )
        txn.append(result.to_dict())
        self._emit(
            run_id,
            EventType.COLLAB_REQUESTED,
            {
                "subtask_ref": node_ref,
                "owner": from_member_ref,
                "to_member_ref": to_member_ref,
                "fence": current_fence,
                "reason": "accepted",
                "mode": mode,
                "correlation_id": correlation_id,
                "message_id": message_id,
                "attempt": attempt,
                "instruction_like": authorized.instruction_like,
            },
            task_ref=facts.task_ref,
        )
        if produced:
            self._emit(
                run_id,
                EventType.HANDOFF_PRODUCED,
                {
                    "subtask_ref": node_ref,
                    "owner": from_member_ref,
                    "fence": current_fence,
                    "reason": "handoff",
                    "refs": list(produced),
                },
                task_ref=facts.task_ref,
            )
        return result

    def resolve(
        self,
        run_id: str,
        *,
        request_id: str,
        state: str = "resolved",
        reason: str = "resolved",
    ) -> CollabRequestResult:
        """Record the terminal outcome of a previously accepted request.

        Only an already-accepted request can be resolved; a duplicate resolve is
        idempotent (the first terminal state wins).  A response carries no new
        authority and cannot grant permission.
        """

        prior = self._log.get(run_id, request_id)
        if prior is None:
            raise CollabRefused(
                "unknown_request",
                f"collab request {request_id!r} does not exist",
                details={"request_id": request_id, "run_ref": run_id},
            )
        existing = _replay(prior)
        if existing.state != "requested":
            return existing
        if state not in REQUEST_STATES:
            raise CollabRefused(
                "invalid_state",
                f"unknown collab result state {state!r}",
                details={"request_id": request_id, "state": state},
            )
        record = dict(prior)
        record["state"] = state
        record["reason"] = reason
        record["resolved_at"] = to_iso(self._clock())
        self._log.append(record)
        self._emit(
            run_id,
            EventType.COLLAB_RESOLVED,
            {
                "subtask_ref": existing.node_ref,
                "owner": existing.from_member_ref,
                "fence": existing.fence,
                "reason": reason,
                "state": state,
                "request_id": request_id,
            },
            task_ref=existing.binding.task_ref if existing.binding else None,
        )
        return _replay(record)

    def list_requests(
        self,
        run_id: str,
        *,
        after: str | None = None,
        limit: int = 100,
    ) -> list[CollabRequestResult]:
        """Read-only projection of a Run's requests, ordered by first write."""

        records: list[dict[str, Any]] = []
        with self._log._locks.acquire(self._log._lock_key(run_id)):  # noqa: SLF001
            all_records, _ = load_jsonl(self._log.path)
        for record in all_records:
            if record.get("run_ref") == run_id:
                records.append(record)        # Later state records for the same request_id supersede earlier ones.
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for record in records:
            request_id = record.get("request_id")
            if not isinstance(request_id, str):
                continue
            if request_id not in latest:
                order.append(request_id)
            latest[request_id] = record
        results = [_replay(latest[rid]) for rid in order]
        start = 0
        if after:
            for index, result in enumerate(results):
                if result.request_id == after:
                    start = index + 1
                    break
        return results[start : start + limit]

    # ----------------------------------------------------------------- helpers
    def _resolve_timeout(self, value: int | None) -> int | None:
        timeout = value if value is not None else self._default_timeout
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            return None
        if timeout > MAX_COLLAB_TIMEOUT_SECONDS:
            return None
        return timeout

    def _refuse(
        self,
        *,
        run_id: str,
        request_id: str,
        node_ref: str,
        from_member_ref: str,
        to_member_ref: str | None,
        mode: str,
        message_id: str,
        correlation_id: str,
        summary_text: str,
        reason: str,
        state: str,
        binding: CausalBinding | None = None,
        fence: int = 0,
        rejected_refs: tuple[str, ...] = (),
        budget_remaining: int | None = None,
        txn: "_CollabTransaction | None" = None,
    ) -> CollabRequestResult:
        try:
            summary = classify_summary(summary_text)
        except ContextError:
            # Preserve the raw text as inert data for audit; it is never executed.
            summary = AuthorizedSummary(
                text=summary_text if isinstance(summary_text, str) else "",
                instruction_like=True,
                markers=("oversized_or_empty",),
            )
        result = CollabRequestResult(
            request_id=request_id,
            run_ref=run_id,
            node_ref=node_ref,
            from_member_ref=from_member_ref,
            to_member_ref=to_member_ref,
            mode=mode,
            state=state,
            reason=reason,
            correlation_id=correlation_id,
            message_id=message_id,
            summary=summary,
            handoff_refs=rejected_refs,
            produced_refs=(),
            rejected_refs=rejected_refs,
            fence=fence,
            at=to_iso(self._clock()),
            budget_remaining=budget_remaining,
            binding=binding,
        )
        # Only persist refusals that are structurally attributable to a real Run;
        # an unknown Run has nothing to attach the record to.  When we are inside
        # the per-Run transaction we append through it so the write stays in the
        # same critical section as the idempotency read.
        if reason != "unknown_run" and _safe_request_id(request_id):
            if txn is not None:
                txn.append(result.to_dict())
            else:
                self._log.append(result.to_dict())
        return result

    def _emit_rejected(self, run_id: str, result: CollabRequestResult) -> None:
        self._emit(
            run_id,
            EventType.HANDOFF_REJECTED,
            {
                "subtask_ref": result.node_ref,
                "owner": result.from_member_ref,
                "fence": result.fence,
                "reason": result.reason,
                "rejected_refs": list(result.rejected_refs),
            },
            task_ref=result.binding.task_ref if result.binding else None,
        )

    def _emit(
        self,
        run_id: str,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        task_ref: str | None,
    ) -> None:
        try:
            self._store.append_event(
                run_id,
                {
                    "type": event_type.value,
                    "actor": self._actor,
                    "task_ref": task_ref,
                    "run_ref": run_id,
                    "payload": payload,
                },
            )
        except Exception:  # noqa: BLE001 - event emission is best-effort audit
            pass


def _safe_request_id(request_id: str) -> bool:
    return isinstance(request_id, str) and 0 < len(request_id) <= 200


def _replay(record: dict[str, Any]) -> CollabRequestResult:
    """Rebuild a :class:`CollabRequestResult` from a persisted JSONL record."""

    summary_raw = record.get("summary")
    if isinstance(summary_raw, dict):
        summary = AuthorizedSummary(
            text=str(summary_raw.get("text", "")),
            instruction_like=bool(summary_raw.get("instruction_like", False)),
            markers=tuple(summary_raw.get("markers") or ()),
        )
    else:  # legacy/defensive: treat a bare string as inert text
        summary = AuthorizedSummary(text=str(summary_raw or ""))

    binding_raw = record.get("binding")
    binding: CausalBinding | None = None
    if isinstance(binding_raw, dict):
        binding = CausalBinding(
            task_ref=str(binding_raw.get("task_ref", "")),
            run_ref=str(binding_raw.get("run_ref", "")),
            node_ref=str(binding_raw.get("node_ref", "")),
            message_id=str(binding_raw.get("message_id", "")),
            correlation_id=str(binding_raw.get("correlation_id", "")),
            in_reply_to=binding_raw.get("in_reply_to"),
        )

    return CollabRequestResult(
        request_id=str(record.get("request_id", "")),
        run_ref=str(record.get("run_ref", "")),
        node_ref=str(record.get("node_ref", "")),
        from_member_ref=str(record.get("from_member_ref", "")),
        to_member_ref=record.get("to_member_ref"),
        mode=str(record.get("mode", "")),
        state=str(record.get("state", "")),
        reason=str(record.get("reason", "")),
        correlation_id=str(record.get("correlation_id", "")),
        message_id=str(record.get("message_id", "")),
        summary=summary,
        handoff_refs=tuple(record.get("handoff_refs") or ()),
        produced_refs=tuple(record.get("produced_refs") or ()),
        rejected_refs=tuple(record.get("rejected_refs") or ()),
        fence=int(record.get("fence") or 0),
        at=str(record.get("at", "")),
        idempotent_replay=True,
        budget_remaining=record.get("budget_remaining"),
        timeout_seconds=int(record.get("timeout_seconds") or DEFAULT_COLLAB_TIMEOUT_SECONDS),
        attempt=int(record.get("attempt") or 1),
        binding=binding,
    )


def summarize_request_digest(payload: dict[str, Any]) -> str:
    """Stable digest of a request payload for diagnostics/idempotency audits."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "CollabRefused",
    "CollabRequestResult",
    "DEFAULT_COLLAB_TIMEOUT_SECONDS",
    "DEFAULT_MAX_COLLAB_REQUESTS",
    "HandoffRejected",
    "MAX_COLLAB_TIMEOUT_SECONDS",
    "PeerService",
    "summarize_request_digest",
]
