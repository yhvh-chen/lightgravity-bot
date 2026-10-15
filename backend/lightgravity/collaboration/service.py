"""Claim/lease application service: policy, idempotency and orchestration (LG-029).

This is the single entry point the API/coordinator should call.  It composes:

* :class:`DiscoveryService` — the authorized read projection;
* :class:`LeaseManager` — the atomic, fenced lease authority;
* :class:`ClaimPolicy` — the default-off feature switch and lease duration
  (docs/08 §6.5) plus the Task/Run budget gate.

It adds the one thing the lower layers do not own: **claim-request idempotency**.
A repeated ``request_id`` returns the first decision instead of granting a new
lease, and the request log is replayed from persisted events on construction so
the guarantee survives a restart.

Nothing in this module imports the SDK, spawns a model, or writes control state
outside the ``Store``.  The default path (``enabled=False``) returns an empty
projection and refuses every request, leaving deterministic scheduling in
charge.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from lightgravity.store import RevisionConflict, Store

from .discovery import DiscoveryLimits, DiscoveryService
from .lease import DEFAULT_LEASE_SECONDS, LeaseManager
from .models import (
    ClaimDecision,
    ClaimRequest,
    DiscoveryView,
    LeaseRenewal,
    LeaseState,
    ReclaimOutcome,
)


@dataclass(frozen=True, slots=True)
class ClaimPolicy:
    """Resolved collaboration switches and budget inputs (docs/08 §6.5).

    ``enabled`` defaults to ``False``: the decentralized path is opt-in and the
    program's deterministic scheduling remains the default behavior.
    """

    enabled: bool = False
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    collab_requests_enabled: bool = False
    budget_remaining: int | None = None
    max_parallel: int | None = None
    running: int = 0


class ClaimPolicyReader:
    """Reads the collaboration switches from ``settings/SETTINGS.md`` (read-only).

    The SETTINGS.md file is owned by LG-025; this reader never writes it.  Any
    missing field or unreadable file resolves to the **closed** state so the
    default path is deterministic scheduling.
    """

    def __init__(self, store: Store) -> None:
        self._store = store

    def read(self) -> ClaimPolicy:
        try:
            entity = self._store.read("settings", "settings").entity
        except Exception:  # noqa: BLE001 - any failure resolves to the closed state
            return ClaimPolicy()
        enabled = bool(entity.get("decentralized_claim_enabled", False))
        collab = bool(entity.get("collab_requests_enabled", False))
        seconds = entity.get("claim_lease_seconds", DEFAULT_LEASE_SECONDS)
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            seconds = DEFAULT_LEASE_SECONDS
        return ClaimPolicy(
            enabled=enabled,
            lease_seconds=seconds,
            collab_requests_enabled=collab,
        )


@dataclass(slots=True)
class _RequestLog:
    """Replayable ``request_id -> decision`` log (idempotency across restarts).

    The log is **derived from the frozen lease events** (``subtask.lease_granted``
    / ``subtask.claim_refused``) already written to the Run stream.  It never
    introduces an unfrozen event type, and because it is replayed from persisted
    JSONL it survives a restart and the same ``request_id`` cannot grant a second
    lease after a crash.
    """

    store: Store
    _entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    _loaded: set[str] = field(default_factory=set)

    def load(self, run_id: str) -> None:
        if run_id in self._loaded:
            return
        try:
            records = self.store.read_events(run_id, after_seq=0, limit=100000)
        except Exception:  # noqa: BLE001 - a missing stream simply has no history
            records = []
        for record in records:
            payload = record.event.get("payload")
            if not isinstance(payload, dict):
                continue
            request_id = payload.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                continue
            if record.type == "subtask.lease_granted":
                self._entries[request_id] = {
                    "request_id": request_id,
                    "subtask_ref": payload.get("subtask_ref"),
                    "owner": payload.get("owner"),
                    "granted": True,
                    "reason": payload.get("reason") or "granted",
                    "fence": payload.get("fence"),
                    "lease_expires_at": payload.get("lease_expires_at"),
                }
            elif record.type == "subtask.claim_refused":
                self._entries[request_id] = {
                    "request_id": request_id,
                    "subtask_ref": payload.get("subtask_ref"),
                    "owner": payload.get("owner"),
                    "granted": False,
                    "reason": payload.get("reason"),
                    "fence": payload.get("fence"),
                }
        self._loaded.add(run_id)

    def get(self, run_id: str, request_id: str) -> dict[str, Any] | None:
        self.load(run_id)
        entry = self._entries.get(request_id)
        return dict(entry) if entry is not None else None

    def record(self, run_id: str, payload: dict[str, Any]) -> None:
        """Remember a decision in memory for this process (events already persisted)."""

        request_id = payload.get("request_id")
        if isinstance(request_id, str) and request_id:
            self._entries.setdefault(request_id, dict(payload))


class CollaborationService:
    """Program authority for discovery, claims, leases and fencing."""

    def __init__(
        self,
        store: Store,
        *,
        policy: ClaimPolicy | None = None,
        actor: str = "coordinator",
        default_lease_seconds: int = DEFAULT_LEASE_SECONDS,
        clock: Any = None,
    ) -> None:
        self._store = store
        self._actor = actor
        kwargs: dict[str, Any] = {"actor": actor}
        if clock is not None:
            kwargs["clock"] = clock
        self._discovery = DiscoveryService(store, **({"clock": clock} if clock else {}))
        self._leases = LeaseManager(store, **kwargs)
        self._policy = policy or ClaimPolicy()
        self._default_lease_seconds = default_lease_seconds
        self._requests = _RequestLog(store)

    @property
    def policy(self) -> ClaimPolicy:
        return self._policy

    @property
    def enabled(self) -> bool:
        return self._policy.enabled

    def with_policy(self, policy: ClaimPolicy) -> "CollaborationService":
        """Return a view with a different resolved policy (same Store)."""

        clone = CollaborationService(
            self._store,
            policy=policy,
            actor=self._actor,
            default_lease_seconds=self._default_lease_seconds,
        )
        return clone

    # ----------------------------------------------------------------- discovery
    def discover(
        self,
        run_id: str,
        owner: str,
        *,
        limits: DiscoveryLimits | None = None,
        enabled: bool | None = None,
    ) -> DiscoveryView:
        active = self._policy.enabled if enabled is None else enabled
        resolved = limits or DiscoveryLimits(
            capabilities=(),
            max_parallel=self._policy.max_parallel,
            running=self._policy.running,
            budget_remaining=self._policy.budget_remaining,
        )
        return self._discovery.discover(run_id, owner, enabled=active, limits=resolved)

    # -------------------------------------------------------------------- claims
    def request_claim(
        self,
        run_id: str,
        request: ClaimRequest,
        *,
        limits: DiscoveryLimits | None = None,
        lease_seconds: int | None = None,
        allow_write: bool = True,
        dependencies_ready: bool | None = None,
        budget_available: bool | None = None,
        capability_ok: bool | None = None,
    ) -> ClaimDecision:
        """Decide a claim request; idempotent on ``(run_id, request_id)``.

        The request must also be discoverable under the current policy: a claim
        for a node the worker is not authorized to see is refused, so discovery
        and claiming cannot disagree.
        """

        prior = self._requests.get(run_id, request.request_id)
        if prior is not None:
            return ClaimDecision(
                granted=bool(prior.get("granted")),
                subtask_id=str(prior.get("subtask_ref") or request.subtask_id),
                owner=str(prior.get("owner") or request.owner),
                request_id=request.request_id,
                reason=str(prior.get("reason") or "idempotent_replay"),
                fence=int(prior.get("fence") or 0),
                lease_expires_at=prior.get("lease_expires_at"),
                revision=int(prior.get("revision") or 0),
                idempotent_replay=True,
            )

        view = self.discover(run_id, request.owner, limits=limits)
        visible = {candidate.subtask_id for candidate in view.candidates}
        is_discoverable = request.subtask_id in visible

        resolved_lease = (
            request.lease_seconds
            if request.lease_seconds is not None
            else (lease_seconds if lease_seconds is not None else self._policy.lease_seconds)
        )
        budget = budget_available
        if budget is None:
            budget = self._policy.budget_remaining is None or self._policy.budget_remaining > 0

        decision = self._leases.request_claim(
            ClaimRequest(
                subtask_id=request.subtask_id,
                owner=request.owner,
                request_id=request.request_id,
                lease_seconds=resolved_lease,
                capability=request.capability,
            ),
            enabled=self._policy.enabled,
            lease_seconds=resolved_lease,
            allow_write=allow_write,
            is_discoverable=is_discoverable,
            dependencies_ready=dependencies_ready,
            budget_available=budget,
            capability_ok=capability_ok,
            run_ref=run_id,
        )
        self._requests.record(
            run_id,
            {
                "request_id": request.request_id,
                "subtask_ref": decision.subtask_id,
                "owner": decision.owner,
                "granted": decision.granted,
                "reason": decision.reason,
                "fence": decision.fence,
                "lease_expires_at": decision.lease_expires_at,
                "revision": decision.revision,
                "task_ref": view.candidates[0].task_ref if view.candidates else None,
            },
        )
        return decision

    # ------------------------------------------------------------------ renewing
    def renew(
        self,
        subtask_id: str,
        owner: str,
        *,
        fence: int | None = None,
        lease_seconds: int | None = None,
    ) -> LeaseRenewal:
        resolved = lease_seconds if lease_seconds is not None else self._policy.lease_seconds
        return self._leases.renew(subtask_id, owner, fence=fence, lease_seconds=resolved)

    def release(
        self,
        subtask_id: str,
        owner: str,
        *,
        fence: int | None = None,
        reason: str = "released",
    ) -> bool:
        return self._leases.release(subtask_id, owner, fence=fence, reason=reason)

    def lease_state(self, subtask_id: str) -> LeaseState | None:
        return self._leases.lease_state(subtask_id)

    def reclaim_expired(self, subtask_id: str, *, reason: str = "lease_expired") -> ReclaimOutcome:
        return self._leases.reclaim_expired(subtask_id, reason=reason)

    def assert_current(self, subtask_id: str, owner: str, fence: int) -> dict[str, Any]:
        """Fencing gate for write-back / handoff / emit / member release."""

        return self._leases.assert_current(subtask_id, owner, fence)

    def guard_write_back(
        self,
        subtask_id: str,
        owner: str,
        fence: int,
        updates: dict[str, Any],
    ) -> Any:
        """Fenced write-back: verify the fence, then persist via the ``Store``.

        A stale fence raises :class:`~lightgravity.collaboration.errors.StaleLease`
        **before** any write, so an old holder cannot overwrite a reclaimed node.
        """

        self._leases.assert_current(subtask_id, owner, fence)
        for _ in range(16):
            current = self._store.read("subtask", subtask_id)
            try:
                return self._store.write(
                    "subtask",
                    subtask_id,
                    updates,
                    expected_revision=current.revision,
                    actor=self._actor,
                )
            except RevisionConflict:
                # A concurrent write touched the node; re-verify the fence before
                # retrying so a reclaimed lease cannot slip through.
                self._leases.assert_current(subtask_id, owner, fence)
                continue
        raise RuntimeError("fenced write-back did not converge")


__all__ = [
    "ClaimPolicy",
    "ClaimPolicyReader",
    "CollaborationService",
]
