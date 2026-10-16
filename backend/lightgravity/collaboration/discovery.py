"""Authorized discovery projection for a worker (LG-029, docs/08 §4.3/§6.2/§6.3).

``GET /runs/{run_id}/discoverable`` is a *read-only filtered projection*: a
worker only sees Subtasks it could legitimately request.  Discovery is therefore
where the negative guarantees are enforced, not only the claim endpoint:

* disabled feature → empty projection (default-off path, §6.5);
* a Subtask of another Task/Run is never returned (no cross-Task leakage);
* capability mismatch → excluded;
* unmet dependencies → excluded (``not_ready``);
* exhausted Task/Run budget or concurrency ceiling → excluded;
* terminal Subtasks → excluded;
* ``write=true`` nodes currently held by another owner → excluded so the single
  same-workspace writer rule is not advertised as available.

The scope of the projection comes from the authoritative Run entity's
``subtask_refs`` (written by the graph dispatcher, docs/08 §6.2), never from a
caller-supplied list, so a worker cannot widen what it may see.  Everything here
reads the Store and returns plain data; it never writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from lightgravity.store import EntityNotFound, Store
from lightgravity.store.clock import Clock, from_iso, utcnow

from .models import (
    CLAIMABLE_SUBTASK_STATES,
    TERMINAL_SUBTASK_STATES,
    DiscoverableCandidate,
    DiscoveryView,
    fence_of,
)


@dataclass(frozen=True, slots=True)
class DiscoveryLimits:
    """Program-side limits a discovery query must respect (§6.2, §6.3).

    ``max_parallel`` and ``budget_remaining`` mirror the Task budget; a value of
    ``None`` means "not constrained at this layer" so a caller cannot invent a
    constraint by omission.
    """

    capabilities: tuple[str, ...] = ()
    max_parallel: int | None = None
    running: int = 0
    budget_remaining: int | None = None
    write_held_keys: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def unbounded(cls) -> "DiscoveryLimits":
        return cls()


class DiscoveryService:
    """Builds the discoverable projection for one worker identity."""

    def __init__(self, store: Store, *, clock: Clock = utcnow) -> None:
        self._store = store
        self._clock = clock

    # ------------------------------------------------------------------ helpers
    def _expired(self, value: Any) -> bool:
        if not isinstance(value, str) or not value:
            return True
        try:
            return from_iso(value) <= self._clock()
        except ValueError:
            return True

    def _run_subtask_refs(self, run_id: str) -> tuple[str, ...] | None:
        run = self._safe_read("run", run_id)
        if run is None:
            return None
        refs = run.get("subtask_refs")
        if not isinstance(refs, list):
            return ()
        return tuple(ref for ref in refs if isinstance(ref, str))

    def _dependencies_ready(
        self, entity: dict[str, Any], by_id: dict[str, dict[str, Any]]
    ) -> bool:
        for dep in entity.get("depends_on") or []:
            if not isinstance(dep, str):
                return False
            dep_entity = by_id.get(dep)
            if dep_entity is None:
                return False
            if str(dep_entity.get("state")) != "passed":
                return False
        return True

    def _blocked_by(
        self, entity: dict[str, Any], by_id: dict[str, dict[str, Any]]
    ) -> tuple[str, ...]:
        blocked: list[str] = []
        for dep in entity.get("depends_on") or []:
            if not isinstance(dep, str):
                continue
            dep_entity = by_id.get(dep)
            if dep_entity is not None and str(dep_entity.get("state")) in {
                "failed",
                "blocked",
                "cancelled",
            }:
                blocked.append(dep)
        existing = entity.get("blocked_by")
        if isinstance(existing, list):
            blocked.extend(item for item in existing if isinstance(item, str))
        return tuple(dict.fromkeys(blocked))

    # ------------------------------------------------------------------- public
    def discover(
        self,
        run_id: str,
        owner: str,
        *,
        enabled: bool = True,
        limits: DiscoveryLimits | None = None,
    ) -> DiscoveryView:
        """Return the authorized candidate projection for ``owner`` on ``run_id``.

        ``enabled=False`` returns an empty, explicitly disabled view: the
        default-off path has no discovery side effects (§6.5).
        """

        resolved_limits = limits or DiscoveryLimits.unbounded()
        if not enabled:
            return DiscoveryView(run_ref=run_id, owner=owner, candidates=(), enabled=False)

        excluded: dict[str, int] = {}

        def exclude(reason: str) -> None:
            excluded[reason] = excluded.get(reason, 0) + 1

        run = self._safe_read("run", run_id)
        if run is None:
            return DiscoveryView(
                run_ref=run_id,
                owner=owner,
                candidates=(),
                considered=0,
                excluded={"run_unknown": 1},
            )

        refs = self._run_subtask_refs(run_id) or ()
        entities = self._read_subtasks(refs)
        by_id = {
            str(entity.get("id")): entity
            for entity in entities
            if isinstance(entity.get("id"), str)
        }
        considered = len(entities)

        capabilities = set(resolved_limits.capabilities)
        admitted: list[DiscoverableCandidate] = []
        for entity in entities:
            state = str(entity.get("state", ""))
            if state in TERMINAL_SUBTASK_STATES:
                exclude("terminal")
                continue
            if state not in CLAIMABLE_SUBTASK_STATES and not (
                state == "running" and self._expired(entity.get("lease_expires_at"))
            ):
                exclude("state_not_claimable")
                continue

            capability = entity.get("capability")
            if capabilities and not (isinstance(capability, str) and capability in capabilities):
                exclude("capability_mismatch")
                continue

            if not self._dependencies_ready(entity, by_id):
                exclude("dependencies_unmet")
                continue

            if resolved_limits.budget_remaining is not None and resolved_limits.budget_remaining <= 0:
                exclude("budget_exhausted")
                continue

            write = bool(entity.get("write"))
            key = entity.get("key")
            write_key = key if isinstance(key, str) else str(entity.get("id"))
            if write and write_key in resolved_limits.write_held_keys:
                exclude("write_serialization")
                continue

            if (
                resolved_limits.max_parallel is not None
                and resolved_limits.running >= resolved_limits.max_parallel
            ):
                exclude("concurrency_limited")
                continue

            owner_value = entity.get("owner")
            admitted.append(
                DiscoverableCandidate(
                    subtask_id=str(entity.get("id")),
                    run_ref=run_id,
                    task_ref=str(run.get("task_ref")) if run.get("task_ref") else "",
                    key=key if isinstance(key, str) else None,
                    objective=entity.get("objective") if isinstance(entity.get("objective"), str) else None,
                    capability=capability if isinstance(capability, str) else None,
                    write=write,
                    state=state,
                    depends_on=tuple(
                        dep for dep in (entity.get("depends_on") or []) if isinstance(dep, str)
                    ),
                    blocked_by=self._blocked_by(entity, by_id),
                    owner=owner_value if isinstance(owner_value, str) else None,
                    lease_expires_at=(
                        entity.get("lease_expires_at")
                        if isinstance(entity.get("lease_expires_at"), str)
                        else None
                    ),
                    fence=fence_of(entity),
                    assignee_member_ref=(
                        entity.get("assignee_member_ref")
                        if isinstance(entity.get("assignee_member_ref"), str)
                        else None
                    ),
                )
            )

        admitted.sort(key=lambda candidate: (candidate.key or candidate.subtask_id))
        return DiscoveryView(
            run_ref=run_id,
            owner=owner,
            candidates=tuple(admitted),
            considered=considered,
            excluded=excluded,
        )

    def _read_subtasks(self, refs: Sequence[str]) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for ref in refs:
            entity = self._safe_read("subtask", ref)
            if entity is not None:
                entities.append(entity)
        return entities

    def _safe_read(self, kind: str, entity_id: str) -> dict[str, Any] | None:
        try:
            return self._store.read(kind, entity_id).entity
        except EntityNotFound:
            return None
        except Exception:  # noqa: BLE001 - an invalid entity is simply not discoverable
            return None


__all__ = ["DiscoveryLimits", "DiscoveryService"]
