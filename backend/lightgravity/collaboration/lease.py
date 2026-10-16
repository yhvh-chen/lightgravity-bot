"""Program-authorized lease acquisition, renewal, release and fencing (LG-029).

This is the *authority* layer for the decentralized path: workers request, this
module decides and persists.  It never lets a model or worker write control
state directly (docs/08 §6.3, §8).

Concurrency model
-----------------
Every mutation is a read-modify-write through :meth:`Store.write`, which takes
the per-entity ``flock`` and rejects a stale ``expected_revision``.  Two workers
racing for the same Subtask therefore cannot both win: the loser gets a
``RevisionConflict``, re-reads, observes the other active owner and is refused
with :class:`ClaimRefused` (``held_by_other``).  The decision and the write
happen inside that loop, so exclusivity is a property of the program, not of
test timing.

Fencing
-------
``fence`` is the additive, monotonic counter of docs/08 §6.3.  *Every* grant or
reclaim increments it.  A later write-back that does not present the current
fence is rejected with :class:`~lightgravity.collaboration.errors.StaleLease`
and **nothing is persisted** - this is fencing, not last-write-wins.  Legacy
entities without a ``fence`` are read as ``0`` and produce a diagnostic rather
than being blocked.

Expiry is not a stop
--------------------
:meth:`LeaseManager.reclaim_expired` only makes an expired lease *re-grantable*.
If the node has side effects (``write=true``) it is routed to
``recovery_required`` and never auto-replayed; ``stopped`` is never inferred
from an expiry.
"""

from __future__ import annotations

from typing import Any

from lightgravity.contracts import EventType
from lightgravity.store import (
    EntityNotFound,
    RevisionConflict,
    Store,
    Versioned,
)
from lightgravity.store.clock import Clock, from_iso, plus_seconds, to_iso, utcnow

from .errors import ClaimRefused, StaleLease
from .models import (
    CLAIMABLE_SUBTASK_STATES,
    TERMINAL_SUBTASK_STATES,
    ClaimDecision,
    ClaimRequest,
    LeaseRenewal,
    LeaseState,
    ReclaimOutcome,
    fence_of,
)

#: Bounded retries on optimistic-concurrency conflicts before giving up.  A
#: conflict here means "another worker touched this node"; re-reading and
#: re-deciding is correct, but an unbounded loop would let two live workers
#: spin forever.
_MAX_RETRIES = 16

#: Default lease duration if a caller does not supply one (docs/08 §6.5 default
#: suggestion; the service-level setting is the authority when wired).
DEFAULT_LEASE_SECONDS = 300


class LeaseManager:
    """Atomic Subtask lease authority with fencing."""

    def __init__(
        self,
        store: Store,
        *,
        actor: str = "coordinator",
        clock: Clock = utcnow,
    ) -> None:
        self._store = store
        self._actor = actor
        self._clock = clock

    # ------------------------------------------------------------------ reading
    def _read(self, subtask_id: str) -> Versioned | None:
        try:
            return self._store.read("subtask", subtask_id)
        except EntityNotFound:
            return None

    def _expired(self, value: Any) -> bool:
        if not isinstance(value, str) or not value:
            return True
        try:
            return from_iso(value) <= self._clock()
        except ValueError:
            return True

    def lease_state(self, subtask_id: str) -> LeaseState | None:
        """Read the current lease facts without changing anything."""

        current = self._read(subtask_id)
        if current is None:
            return None
        entity = current.entity
        lease_expires = entity.get("lease_expires_at")
        owner = entity.get("owner")
        state = str(entity.get("state", ""))
        expired = state == "running" and self._expired(lease_expires)
        return LeaseState(
            subtask_id=subtask_id,
            state=state,
            owner=owner if isinstance(owner, str) else None,
            lease_expires_at=lease_expires if isinstance(lease_expires, str) else None,
            fence=fence_of(entity),
            expired=expired,
            # A lease expiry never proves the executor stopped.  Only an
            # independently confirmed process stop may set this true.
            stopped=False,
            has_side_effects=bool(entity.get("write")),
        )

    # ------------------------------------------------------------------ claiming
    def request_claim(
        self,
        request: ClaimRequest,
        *,
        enabled: bool = True,
        lease_seconds: int | None = None,
        allow_write: bool = True,
        is_discoverable: bool | None = None,
        dependencies_ready: bool | None = None,
        budget_available: bool = True,
        capability_ok: bool | None = None,
        run_ref: str | None = None,
    ) -> ClaimDecision:
        """Decide a claim request and, when granted, persist the lease atomically.

        All the negative gates are evaluated here (not only in discovery) so a
        worker that bypasses discovery still cannot claim: capability, dependency,
        budget, discoverability, terminal state, active other owner and the
        single-writer rule.  ``idempotent_replay`` is set when the same
        ``request_id`` is presented again for a lease this owner already holds.
        """

        if not enabled:
            self._refuse_event(request, "feature_disabled", run_ref=run_ref)
            raise ClaimRefused(
                "feature_disabled",
                "decentralized claim is disabled",
                details={"subtask_ref": request.subtask_id},
            )
        if request.lease_seconds is not None and request.lease_seconds <= 0:
            raise ClaimRefused(
                "invalid_lease_seconds",
                "lease_seconds must be > 0",
                details={"subtask_ref": request.subtask_id},
            )
        duration = self._resolve_seconds(request.lease_seconds if request.lease_seconds else lease_seconds)

        for _ in range(_MAX_RETRIES):
            current = self._read(request.subtask_id)
            if current is None:
                self._refuse_event(request, "unknown_subtask", run_ref=run_ref)
                raise ClaimRefused(
                    "unknown_subtask",
                    f"subtask {request.subtask_id!r} does not exist",
                    details={"subtask_ref": request.subtask_id},
                )

            entity = current.entity
            state = str(entity.get("state", ""))
            owner = entity.get("owner")
            fence = fence_of(entity)

            if state in TERMINAL_SUBTASK_STATES:
                return self._refused(request, "terminal", fence=fence, run_ref=run_ref)

            if is_discoverable is False:
                return self._refused(request, "not_discoverable", fence=fence, run_ref=run_ref)
            if capability_ok is False:
                return self._refused(request, "capability_mismatch", fence=fence, run_ref=run_ref)
            if dependencies_ready is False:
                return self._refused(request, "dependencies_unmet", fence=fence, run_ref=run_ref)
            if not budget_available:
                return self._refused(request, "budget_exhausted", fence=fence, run_ref=run_ref)
            if bool(entity.get("write")) and not allow_write:
                return self._refused(request, "write_serialization", fence=fence, run_ref=run_ref)

            if (
                state == "running"
                and isinstance(owner, str)
                and owner
                and owner != request.owner
                and not self._expired(entity.get("lease_expires_at"))
            ):
                return self._refused(request, "held_by_other", fence=fence, run_ref=run_ref)

            if state == "running" and owner == request.owner and not self._expired(
                entity.get("lease_expires_at")
            ):
                # Same owner re-requesting a live lease: idempotent, no new fence.
                return ClaimDecision(
                    granted=True,
                    subtask_id=request.subtask_id,
                    owner=request.owner,
                    request_id=request.request_id,
                    reason="already_owned",
                    fence=fence,
                    lease_expires_at=(
                        entity.get("lease_expires_at")
                        if isinstance(entity.get("lease_expires_at"), str)
                        else None
                    ),
                    revision=current.revision,
                    idempotent_replay=True,
                )

            if state not in CLAIMABLE_SUBTASK_STATES and not (
                state == "running" and self._expired(entity.get("lease_expires_at"))
            ):
                return self._refused(request, "state_not_claimable", fence=fence, run_ref=run_ref)

            new_fence = fence + 1
            expiry = to_iso(plus_seconds(self._clock(), duration))
            try:
                versioned = self._store.write(
                    "subtask",
                    request.subtask_id,
                    {
                        "state": "running",
                        "owner": request.owner,
                        "lease_expires_at": expiry,
                        "fence": new_fence,
                        "blocked_by": [],
                    },
                    expected_revision=current.revision,
                    actor=self._actor,
                )
            except RevisionConflict:
                # Another worker modified the node between read and write.
                # Re-read and re-decide; exclusivity is preserved because the
                # winner's owner/expiry are now visible.
                continue

            self._emit(
                entity,
                EventType.SUBTASK_LEASE_GRANTED,
                {
                    "subtask_ref": request.subtask_id,
                    "owner": request.owner,
                    "fence": new_fence,
                    "previous_fence": fence,
                    "lease_expires_at": expiry,
                    "request_id": request.request_id,
                    "reason": "granted",
                },
                run_ref=run_ref,
            )
            return ClaimDecision(
                granted=True,
                subtask_id=request.subtask_id,
                owner=request.owner,
                request_id=request.request_id,
                reason="granted",
                fence=new_fence,
                lease_expires_at=expiry,
                revision=versioned.revision,
            )

        return self._refused(request, "held_by_other", run_ref=run_ref)

    def _refused(
        self,
        request: ClaimRequest,
        reason: str,
        *,
        fence: int = 0,
        run_ref: str | None = None,
    ) -> ClaimDecision:
        self._refuse_event(request, reason, fence=fence, run_ref=run_ref)
        return ClaimDecision(
            granted=False,
            subtask_id=request.subtask_id,
            owner=request.owner,
            request_id=request.request_id,
            reason=reason,
            fence=fence,
        )

    # ------------------------------------------------------------------ renewing
    def renew(
        self,
        subtask_id: str,
        owner: str,
        *,
        fence: int | None = None,
        lease_seconds: int | None = None,
    ) -> LeaseRenewal:
        """Renew a live lease held by ``owner``; never resurrect an expired one."""

        duration = self._resolve_seconds(lease_seconds)
        for _ in range(_MAX_RETRIES):
            current = self._read(subtask_id)
            if current is None:
                return LeaseRenewal(subtask_id, owner, False, 0, reason="unknown_subtask")
            entity = current.entity
            state = str(entity.get("state", ""))
            current_owner = entity.get("owner")
            current_fence = fence_of(entity)
            if state != "running" or current_owner != owner:
                return LeaseRenewal(
                    subtask_id, owner, False, current_fence, reason="not_owner"
                )
            if fence is not None and fence != current_fence:
                raise StaleLease(
                    subtask_id, provided=fence, current=current_fence, reason="renew_fence_mismatch"
                )
            if self._expired(entity.get("lease_expires_at")):
                # Renewal must not resurrect an expired lease: the node may be
                # re-granted to someone else, and the old holder must not regain
                # authority by simply asking again.
                return LeaseRenewal(
                    subtask_id, owner, False, current_fence, reason="lease_expired"
                )
            expiry = to_iso(plus_seconds(self._clock(), duration))
            try:
                self._store.write(
                    "subtask",
                    subtask_id,
                    {"lease_expires_at": expiry, "fence": current_fence},
                    expected_revision=current.revision,
                    actor=self._actor,
                )
            except RevisionConflict:
                continue
            self._emit(
                entity,
                EventType.SUBTASK_LEASE_RENEWED,
                {
                    "subtask_ref": subtask_id,
                    "owner": owner,
                    "fence": current_fence,
                    "lease_expires_at": expiry,
                },
            )
            return LeaseRenewal(
                subtask_id, owner, True, current_fence, lease_expires_at=expiry, reason="renewed"
            )
        return LeaseRenewal(subtask_id, owner, False, 0, reason="contention")

    # ----------------------------------------------------------------- releasing
    def release(
        self,
        subtask_id: str,
        owner: str,
        *,
        fence: int | None = None,
        reason: str = "released",
    ) -> bool:
        """Release a lease held by ``owner`` (or by the program when ``owner`` owns it).

        The fence is *not* incremented on release: the node returns to a
        claimable state and the next grant increments it, matching §6.3 ("each
        successful grant/reclaim +1").  A stale fence is rejected.
        """

        for _ in range(_MAX_RETRIES):
            current = self._read(subtask_id)
            if current is None:
                return False
            entity = current.entity
            current_owner = entity.get("owner")
            current_fence = fence_of(entity)
            if current_owner is not None and current_owner != owner:
                raise ClaimRefused(
                    "not_owner",
                    f"subtask {subtask_id!r} is held by {current_owner!r}",
                    details={"subtask_ref": subtask_id, "holder": current_owner},
                )
            if fence is not None and fence != current_fence:
                raise StaleLease(subtask_id, provided=fence, current=current_fence)
            if current_owner is None and entity.get("lease_expires_at") is None:
                return True  # already released
            try:
                self._store.write(
                    "subtask",
                    subtask_id,
                    {"owner": None, "lease_expires_at": None},
                    expected_revision=current.revision,
                    actor=self._actor,
                )
            except RevisionConflict:
                continue
            self._emit(
                entity,
                EventType.SUBTASK_LEASE_REVOKED,
                {"subtask_ref": subtask_id, "owner": owner, "fence": current_fence, "reason": reason},
            )
            return True
        return False

    # ------------------------------------------------------------------ reclaiming
    def reclaim_expired(
        self,
        subtask_id: str,
        *,
        reason: str = "lease_expired",
    ) -> ReclaimOutcome:
        """Make an expired lease re-grantable, without auto-replaying side effects.

        For a node with side effects (``write=true``) the Subtask is marked
        ``recovery_required`` via its ``fail_reason``/``blocked_by`` and reported
        as such; the caller must not re-run it automatically.  For a read-only
        node the lease is cleared and the next grant increments the fence.
        """

        for _ in range(_MAX_RETRIES):
            current = self._read(subtask_id)
            if current is None:
                return ReclaimOutcome(subtask_id, False, None, 0, reason="unknown_subtask")
            entity = current.entity
            state = str(entity.get("state", ""))
            owner = entity.get("owner")
            fence = fence_of(entity)
            if state != "running" or not self._expired(entity.get("lease_expires_at")):
                return ReclaimOutcome(
                    subtask_id, False, owner if isinstance(owner, str) else None, fence, reason="not_expired"
                )

            has_side_effects = bool(entity.get("write"))
            new_fence = fence + 1
            updates: dict[str, Any] = {
                "owner": None,
                "lease_expires_at": None,
                "fence": new_fence,
            }
            if has_side_effects:
                updates["state"] = "waiting_user"
                updates["fail_reason"] = "recovery_required: unconfirmed side effects after lease expiry"
                updates["blocked_by"] = []
            try:
                self._store.write(
                    "subtask",
                    subtask_id,
                    updates,
                    expected_revision=current.revision,
                    actor=self._actor,
                )
            except RevisionConflict:
                continue

            self._emit(
                entity,
                EventType.SUBTASK_LEASE_EXPIRED,
                {
                    "subtask_ref": subtask_id,
                    "owner": owner,
                    "fence": new_fence,
                    "previous_fence": fence,
                    "reason": reason,
                    "recovery_required": has_side_effects,
                },
            )
            return ReclaimOutcome(
                subtask_id=subtask_id,
                reclaimed=True,
                previous_owner=owner if isinstance(owner, str) else None,
                fence=new_fence,
                recovery_required=has_side_effects,
                reason=reason,
            )
        return ReclaimOutcome(subtask_id, False, None, 0, reason="contention")

    # ------------------------------------------------------------------ fencing
    def assert_current(self, subtask_id: str, owner: str, fence: int) -> dict[str, Any]:
        """Guard a write-back/handoff/emit/member-release with the current fence.

        Returns the current entity when the fence matches; raises
        :class:`StaleLease` (persisting nothing) when it does not.  This is the
        single gate every post-claim side effect must pass through.
        """

        current = self._read(subtask_id)
        if current is None:
            raise ClaimRefused(
                "unknown_subtask",
                f"subtask {subtask_id!r} does not exist",
                details={"subtask_ref": subtask_id},
            )
        entity = current.entity
        current_fence = fence_of(entity)
        if current_fence != fence:
            raise StaleLease(subtask_id, provided=fence, current=current_fence)
        current_owner = entity.get("owner")
        if current_owner is not None and current_owner != owner:
            raise StaleLease(
                subtask_id,
                provided=fence,
                current=current_fence,
                reason="owner_mismatch",
            )
        return entity

    # ------------------------------------------------------------------- helpers
    def _resolve_seconds(self, value: int | None) -> int:
        seconds = value if value is not None else DEFAULT_LEASE_SECONDS
        if seconds <= 0:
            raise ClaimRefused(
                "invalid_lease_seconds",
                "lease_seconds must be > 0",
            )
        return seconds

    def _refuse_event(
        self,
        request: ClaimRequest,
        reason: str,
        *,
        fence: int = 0,
        run_ref: str | None = None,
    ) -> None:
        self._store.append_event(
            self._refusal_stream(request.subtask_id, run_ref),
            {
                "type": EventType.SUBTASK_CLAIM_REFUSED.value,
                "actor": self._actor,
                "task_ref": None,
                "run_ref": run_ref,
                "payload": {
                    "subtask_ref": request.subtask_id,
                    "owner": request.owner,
                    "reason": reason,
                    "fence": fence,
                    "request_id": request.request_id,
                },
            },
        )

    def _emit(
        self,
        entity: dict[str, Any],
        event_type: EventType,
        payload: dict[str, Any],
        *,
        run_ref: str | None = None,
    ) -> None:
        task_ref = entity.get("task_ref")
        resolved_run = run_ref if run_ref else entity.get("run_ref")
        stream = resolved_run if isinstance(resolved_run, str) and resolved_run else (
            task_ref if isinstance(task_ref, str) and task_ref else f"subtask:{entity.get('id')}"
        )
        self._store.append_event(
            stream,
            {
                "type": event_type.value,
                "actor": self._actor,
                "task_ref": task_ref if isinstance(task_ref, str) else None,
                "run_ref": resolved_run if isinstance(resolved_run, str) else None,
                "payload": payload,
            },
        )

    def _refusal_stream(self, subtask_id: str, run_ref: str | None) -> str:
        """Stable stream for refusal events.

        Prefers the Run stream (so claim-request idempotency can be replayed from
        one authoritative stream) and falls back to the Subtask stream only when
        the Run is unknown.
        """

        if isinstance(run_ref, str) and run_ref:
            return run_ref
        return subtask_id if subtask_id else "claim-refusals"


__all__ = ["DEFAULT_LEASE_SECONDS", "LeaseManager"]
