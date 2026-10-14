"""Dependency graph, subtask leases and artifact handoff (LG-008).

This module owns the *scheduling* primitives that a dispatcher composes:

* :class:`DependencyGraph` validates a Subtask graph (unique keys, existing
  dependencies, no cycles) and answers readiness/blocking questions in a
  deterministic topological order.
* :class:`SubtaskClaimer` performs the atomic, idempotent ``ready -> running``
  claim with an owner and lease expiry, persisted in the Subtask frontmatter and
  guarded by ``Store`` optimistic concurrency.  It is the Subtask-level analogue
  of the frozen Task lease (docs/08 §7) and never allows two owners to run the
  same node.
* :class:`ArtifactHandoff` carries upstream artifact refs together with the
  producing Subtask id, revision and content hash so a dependency release never
  transmits a bare completion signal.

Nothing here writes TASK.md/RUN.md directly; state goes through
:class:`~lightgravity.coordinator.state.StateWriter` (and thus the ``Store``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from lightgravity.contracts import AppError, ErrorCode, EventType
from lightgravity.store import EntityNotFound, Versioned
from lightgravity.store.clock import Clock, from_iso, plus_seconds, to_iso, utcnow

from .state import StateWriter


class GraphError(AppError):
    """A Subtask graph that failed program validation."""

    def __init__(self, message: str, *, problems: Sequence[str] = ()) -> None:
        super().__init__(
            ErrorCode.CONFIG_INVALID,
            message,
            details={"problems": list(problems)},
        )
        self.problems = tuple(problems)


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One node of the validated Subtask graph (keys, not runtime ids)."""

    key: str
    depends_on: tuple[str, ...] = ()
    write: bool = False


class DependencyGraph:
    """Validated DAG of Subtask keys with deterministic topological order."""

    def __init__(self, nodes: Sequence[GraphNode]) -> None:
        problems: list[str] = []
        self._nodes: dict[str, GraphNode] = {}
        for index, node in enumerate(nodes):
            if not node.key:
                problems.append(f"node #{index} has an empty key")
                continue
            if node.key in self._nodes:
                problems.append(f"duplicate subtask key {node.key!r}")
                continue
            self._nodes[node.key] = node
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep == node.key:
                    problems.append(f"subtask {node.key!r} depends on itself")
                elif dep not in self._nodes:
                    problems.append(f"subtask {node.key!r} depends on unknown {dep!r}")
        if problems:
            raise GraphError("subtask graph is invalid", problems=problems)

        self._index = {node_key: i for i, node_key in enumerate(self._nodes)}

        order: list[str] = []
        remaining = {key: set(node.depends_on) for key, node in self._nodes.items()}
        while remaining:
            ready = [key for key, deps in remaining.items() if not deps]
            if not ready:
                cycle = sorted(remaining)
                raise GraphError(
                    "subtask graph contains a cycle",
                    problems=[f"cycle among {cycle!r}"],
                )
            # Preserve declaration order among simultaneously-ready nodes.
            ready.sort(key=lambda key: self._declaration_index(key))
            for key in ready:
                order.append(key)
                remaining.pop(key)
            for deps in remaining.values():
                deps.difference_update(ready)
        self._order: tuple[str, ...] = tuple(order)

    def _declaration_index(self, key: str) -> int:
        return self._index.get(key, 0)

    @property
    def nodes(self) -> Mapping[str, GraphNode]:
        return dict(self._nodes)

    def node(self, key: str) -> GraphNode:
        return self._nodes[key]

    def topological_order(self) -> tuple[str, ...]:
        return self._order

    def ready(self, completed: Iterable[str], blocked: Iterable[str]) -> tuple[str, ...]:
        """Keys whose dependencies all completed and that are not yet done/blocked."""

        done = set(completed) | set(blocked)
        ready: list[str] = []
        for key in self._order:
            if key in done:
                continue
            if all(dep in completed for dep in self._nodes[key].depends_on):
                ready.append(key)
        return tuple(ready)

    def unresolved(self, completed: Iterable[str], blocked: Iterable[str]) -> tuple[str, ...]:
        """Keys with no terminal outcome yet."""

        done = set(completed) | set(blocked)
        return tuple(key for key in self._order if key not in done)

    def blocked_by(self, key: str, failed: Iterable[str]) -> tuple[str, ...]:
        """Direct dependencies of ``key`` that already failed (for reasons)."""

        failed_set = set(failed)
        return tuple(dep for dep in self._nodes[key].depends_on if dep in failed_set)


@dataclass(frozen=True, slots=True)
class ClaimOutcome:
    """Result of an atomic Subtask claim."""

    acquired: bool
    subtask_id: str
    state: str  # acquired | already_owned | held_by_other | expired_reclaimed | terminal
    owner: str
    lease_expires_at: str | None = None
    reason: str = ""

    @property
    def effective_state(self) -> str:
        return "acquired" if self.state == "expired_reclaimed" else self.state


_TERMINAL_SUBTASK_STATES = frozenset({"passed", "failed", "cancelled"})


class SubtaskClaimer:
    """Idempotent, lease-guarded Subtask claim writer."""

    def __init__(
        self,
        writer: StateWriter,
        *,
        task_id: str,
        run_id: str,
        clock: Clock = utcnow,
    ) -> None:
        self._writer = writer
        self._task_id = task_id
        self._run_id = run_id
        self._clock = clock

    def _expired(self, value: object, now: datetime) -> bool:
        if not isinstance(value, str) or not value:
            return True
        try:
            return from_iso(value) <= now
        except ValueError:
            return True

    def claim(
        self, subtask_id: str, owner: str, *, lease_seconds: int
    ) -> ClaimOutcome:
        if lease_seconds <= 0:
            raise GraphError("lease_seconds must be > 0")
        current = self._writer.read_subtask(subtask_id)
        entity = current.entity
        state = str(entity.get("state", ""))
        current_owner = entity.get("owner")
        expiry = entity.get("lease_expires_at")
        now = self._clock()

        if state in _TERMINAL_SUBTASK_STATES:
            return ClaimOutcome(
                acquired=False,
                subtask_id=subtask_id,
                state="terminal",
                owner=owner,
                reason=f"subtask is already {state}",
            )
        if state == "running" and isinstance(current_owner, str) and current_owner:
            if current_owner != owner and not self._expired(expiry, now):
                return ClaimOutcome(
                    acquired=False,
                    subtask_id=subtask_id,
                    state="held_by_other",
                    owner=str(current_owner),
                    lease_expires_at=expiry if isinstance(expiry, str) else None,
                    reason=f"subtask lease held by {current_owner!r}",
                )
            renewed = self._write_lease(subtask_id, current, owner, lease_seconds, state="running")
            return ClaimOutcome(
                acquired=True,
                subtask_id=subtask_id,
                state="already_owned" if current_owner == owner else "expired_reclaimed",
                owner=owner,
                lease_expires_at=renewed,
            )
        expiry_iso = self._write_lease(subtask_id, current, owner, lease_seconds, state="running")
        return ClaimOutcome(
            acquired=True,
            subtask_id=subtask_id,
            state="acquired",
            owner=owner,
            lease_expires_at=expiry_iso,
        )

    def renew(self, subtask_id: str, owner: str, *, lease_seconds: int) -> bool:
        try:
            current = self._writer.read_subtask(subtask_id)
        except EntityNotFound:
            return False
        entity = current.entity
        if str(entity.get("state")) != "running" or entity.get("owner") != owner:
            return False
        if self._expired(entity.get("lease_expires_at"), self._clock()):
            return False
        self._write_lease(subtask_id, current, owner, lease_seconds, state="running")
        return True

    def release(self, subtask_id: str, owner: str) -> None:
        try:
            current = self._writer.read_subtask(subtask_id)
        except EntityNotFound:
            return
        if current.entity.get("owner") not in (None, owner):
            return
        self._writer.write_subtask(
            subtask_id,
            {"owner": None, "lease_expires_at": None},
        )

    def _write_lease(
        self,
        subtask_id: str,
        current: Versioned,
        owner: str,
        lease_seconds: int,
        *,
        state: str,
    ) -> str:
        expiry = to_iso(plus_seconds(self._clock(), lease_seconds))
        self._writer.write_subtask(
            subtask_id,
            {
                "state": state,
                "owner": owner,
                "lease_expires_at": expiry,
            },
        )
        self._writer.emit(
            self._task_id,
            EventType.SUBTASK_STATE_CHANGED,
            {
                "subtask_ref": subtask_id,
                "from": current.entity.get("state"),
                "to": state,
                "owner": owner,
                "lease_expires_at": expiry,
            },
            task_ref=self._task_id,
            run_ref=self._run_id,
        )
        return expiry


@dataclass(frozen=True, slots=True)
class ArtifactHandoff:
    """Upstream artifacts tied to the producing Subtask revision/content hash."""

    subtask_ref: str
    revision: int
    content_hash: str
    artifacts: tuple[str, ...] = ()

    def encoded_refs(self) -> tuple[str, ...]:
        """Encode as ``<subtask>@<hash>:<artifact>`` strings.

        The bare ``upstream_artifact_refs`` list is contract-shaped (a list of
        strings); embedding the hash keeps the version/hash handoff visible to
        the downstream executor without a second untracked fact source.
        """

        return tuple(f"{self.subtask_ref}@{self.content_hash}:{art}" for art in self.artifacts)

    def to_dict(self) -> dict[str, object]:
        return {
            "subtask_ref": self.subtask_ref,
            "revision": self.revision,
            "content_hash": self.content_hash,
            "artifacts": list(self.artifacts),
        }


def encode_handoffs(handoffs: Sequence[ArtifactHandoff]) -> tuple[str, ...]:
    """Flatten several handoffs into the frozen ``upstream_artifact_refs`` list."""

    refs: list[str] = []
    for handoff in handoffs:
        refs.extend(handoff.encoded_refs())
    return tuple(refs)


def parse_handoff_ref(value: str) -> tuple[str, str, str]:
    """Split ``<subtask>@<hash>:<artifact>`` back into its three parts."""

    subtask_ref, _, rest = value.partition("@")
    content_hash, _, artifact = rest.partition(":")
    return subtask_ref, content_hash, artifact


__all__ = [
    "ArtifactHandoff",
    "ClaimOutcome",
    "DependencyGraph",
    "GraphError",
    "GraphNode",
    "SubtaskClaimer",
    "encode_handoffs",
    "parse_handoff_ref",
]
