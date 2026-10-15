"""Plain value types for LG-029 discovery, claims, leases and fencing.

These are internal dataclasses (mirroring the LG-004/LG-025 convention of not
adding private types to the shared frozen ``contracts`` module).  The API layer
serializes them to the docs/08 §4.3 wire shapes.

Design invariants kept here so both the service and its tests share one source:

* A worker only ever *requests* a claim; the program decides.  Nothing in this
  module mutates control state.
* ``fence`` is a monotonic integer; the current fence is the authority for every
  later write-back, lease renewal, artifact handoff and member release (§6.3).
* A lease expiry never means "the execution stopped".  :class:`LeaseState`
  exposes ``expired`` separately from ``stopped`` so the caller cannot conflate
  them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Terminal Subtask states that must never be claimed again (§6.3).
TERMINAL_SUBTASK_STATES: frozenset[str] = frozenset(
    {"passed", "failed", "cancelled"}
)

#: Subtask states a decentralized claim may move into ``running`` from.
CLAIMABLE_SUBTASK_STATES: frozenset[str] = frozenset({"pending", "ready", "repairing"})

#: Stable refusal reasons surfaced on ``claim_refused`` / ``subtask.claim_refused``.
REFUSAL_REASONS = (
    "not_discoverable",
    "capability_mismatch",
    "dependencies_unmet",
    "budget_exhausted",
    "terminal",
    "held_by_other",
    "write_serialization",
    "feature_disabled",
    "run_inactive",
    "unknown_subtask",
)


@dataclass(frozen=True, slots=True)
class DiscoverableCandidate:
    """One Subtask a given worker is authorized to *see* and request (§4.3).

    The projection deliberately carries only what a worker needs to decide
    whether to request a claim: it never carries another Task's data, an
    unauthorized capability, or control fields the worker must not set.
    """

    subtask_id: str
    run_ref: str
    task_ref: str
    key: str | None
    objective: str | None
    capability: str | None
    write: bool
    state: str
    depends_on: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    owner: str | None = None
    lease_expires_at: str | None = None
    fence: int = 0
    assignee_member_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_ref": self.subtask_id,
            "subtask_id": self.subtask_id,
            "run_ref": self.run_ref,
            "task_ref": self.task_ref,
            "key": self.key,
            "objective": self.objective,
            "capability": self.capability,
            "write": self.write,
            "state": self.state,
            "depends_on": list(self.depends_on),
            "blocked_by": list(self.blocked_by),
            "owner": self.owner,
            "lease_expires_at": self.lease_expires_at,
            "fence": self.fence,
            "assignee_member_ref": self.assignee_member_ref,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryView:
    """Result of a discovery query: the authorized projection plus diagnostics."""

    run_ref: str
    owner: str
    candidates: tuple[DiscoverableCandidate, ...]
    considered: int = 0
    excluded: dict[str, int] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_ref": self.run_ref,
            "owner": self.owner,
            "enabled": self.enabled,
            "considered": self.considered,
            "excluded": dict(self.excluded),
            "items": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class ClaimRequest:
    """A worker's *request* to claim a Subtask (never an authorization)."""

    subtask_id: str
    owner: str
    request_id: str
    lease_seconds: int | None = None
    capability: str | None = None


@dataclass(frozen=True, slots=True)
class ClaimDecision:
    """Program decision for one :class:`ClaimRequest`."""

    granted: bool
    subtask_id: str
    owner: str
    request_id: str
    reason: str = ""
    fence: int = 0
    lease_expires_at: str | None = None
    revision: int = 0
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "granted": self.granted,
            "subtask_ref": self.subtask_id,
            "subtask_id": self.subtask_id,
            "owner": self.owner,
            "request_id": self.request_id,
            "reason": self.reason,
            "fence": self.fence,
            "lease_expires_at": self.lease_expires_at,
            "revision": self.revision,
            "idempotent_replay": self.idempotent_replay,
        }


@dataclass(frozen=True, slots=True)
class LeaseRenewal:
    subtask_id: str
    owner: str
    renewed: bool
    fence: int
    lease_expires_at: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_ref": self.subtask_id,
            "owner": self.owner,
            "renewed": self.renewed,
            "fence": self.fence,
            "lease_expires_at": self.lease_expires_at,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class LeaseState:
    """Read-only view used to reason about expiry *without* implying a stop.

    ``expired`` is a lease fact.  ``stopped`` is deliberately a separate field
    that this task always reports as ``False`` unless a caller has independently
    confirmed a process stop; a lease expiring never sets it.
    """

    subtask_id: str
    state: str
    owner: str | None
    lease_expires_at: str | None
    fence: int
    expired: bool
    stopped: bool = False
    has_side_effects: bool = False


@dataclass(frozen=True, slots=True)
class ReclaimOutcome:
    """Program-side stale-lease reclaim, which never auto-replays side effects."""

    subtask_id: str
    reclaimed: bool
    previous_owner: str | None
    fence: int
    recovery_required: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_ref": self.subtask_id,
            "reclaimed": self.reclaimed,
            "previous_owner": self.previous_owner,
            "fence": self.fence,
            "recovery_required": self.recovery_required,
            "reason": self.reason,
        }


def fence_of(entity: dict[str, Any]) -> int:
    """Read the additive ``fence`` field, treating legacy/absent as ``0`` (§6.3)."""

    value = entity.get("fence")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


__all__ = [
    "CLAIMABLE_SUBTASK_STATES",
    "TERMINAL_SUBTASK_STATES",
    "REFUSAL_REASONS",
    "ClaimDecision",
    "ClaimRequest",
    "DiscoverableCandidate",
    "DiscoveryView",
    "LeaseRenewal",
    "LeaseState",
    "ReclaimOutcome",
    "fence_of",
]
