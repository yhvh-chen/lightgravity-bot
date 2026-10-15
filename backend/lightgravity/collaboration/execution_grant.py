"""Program-frozen worker execution identity and restricted tool proxy (LG-031).

This module closes the LG-029/LG-030 boundary: a *worker* must never prove who
it is with a body field, and must never hold a global management token.  Instead
the program (the graph dispatcher) **mints an opaque, process-local execution
grant** for the exact ``(run, subtask, member, fence)`` it just claimed, hands
only that opaque token to the executor, and revokes it when the execution is
stopped/confirmed.  The grant is the only thing the SDK-side tool proxy may
present, and it authorizes *only* the nodes of its own Run/Task plus the frozen
budget - it is not a capability to read/write arbitrary control state.

Two enforcement surfaces use the same grant registry:

* :func:`resolve_worker_identity` is wired into ``ApiContext.worker_identity``
  so an in-process/HTTP caller presenting ``X-LG-Execution-Grant`` is bound to
  the member the *program* recorded - never to a request body.
* :class:`RestrictedPeerTool` is a minimal SDK custom tool (a plain callable)
  that routes a peer request through the in-process :class:`PeerService`.  It
  checks the grant before ever touching the service, so a worker cannot ask for
  a node it was not authorized to see, and cannot exceed the frozen budget.

Everything here is deterministic, model-free and additive.  The default path
(no grant minted) leaves the deterministic scheduler unchanged.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

#: Default lifetime of a minted grant if the caller does not freeze one.  A
#: grant is also revoked explicitly on stop; the TTL is the fail-safe so a
#: crashed dispatcher cannot leave an unbounded credential behind.
DEFAULT_GRANT_SECONDS = 3600


@dataclass(slots=True)
class ExecutionGrant:
    """An opaque, non-transferable worker execution identity (never a secret)."""

    grant_id: str
    task_id: str
    run_id: str
    subtask_id: str
    member_ref: str
    fence: int
    authorized_node_refs: frozenset[str]
    max_collab_calls: int
    budget_remaining: int | None
    expires_at: float
    revoked: bool = False
    collab_calls: int = 0
    #: Non-secret provenance for honest reporting/tests.
    origin: str = "graph-dispatcher"

    def covers_node(self, node_ref: str) -> bool:
        return node_ref in self.authorized_node_refs

    def active(self, *, now: float | None = None) -> bool:
        if self.revoked:
            return False
        moment = time.time() if now is None else now
        return moment < self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """A redacted, non-secret view (never the token itself)."""

        return {
            "grant_id": self.grant_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "subtask_id": self.subtask_id,
            "member_ref": self.member_ref,
            "fence": self.fence,
            "authorized_node_refs": sorted(self.authorized_node_refs),
            "max_collab_calls": self.max_collab_calls,
            "budget_remaining": self.budget_remaining,
            "collab_calls": self.collab_calls,
            "origin": self.origin,
        }


class ExecutionGrantRegistry:
    """Thread-safe, process-local registry of minted execution grants.

    It is deliberately **not** persisted: a grant is runtime authority, not
    durable state.  After a restart every old grant is gone, so a stale token
    can never regain authority by replay.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_token: dict[str, ExecutionGrant] = {}
        self._by_subtask: dict[str, str] = {}

    # ----------------------------------------------------------------- minting
    def mint(
        self,
        *,
        task_id: str,
        run_id: str,
        subtask_id: str,
        member_ref: str,
        fence: int,
        authorized_node_refs: frozenset[str] | set[str] | tuple[str, ...],
        max_collab_calls: int = 0,
        budget_remaining: int | None = None,
        ttl_seconds: int = DEFAULT_GRANT_SECONDS,
        origin: str = "graph-dispatcher",
    ) -> tuple[str, ExecutionGrant]:
        """Mint a fresh grant and return ``(opaque_token, grant)``.

        Minting a new grant for a Subtask revokes any prior one (a re-claim with
        a new fence must invalidate the old holder's identity).
        """

        token = f"lgxg_{secrets.token_urlsafe(32)}"
        grant = ExecutionGrant(
            grant_id=f"grant_{secrets.token_hex(8)}",
            task_id=task_id,
            run_id=run_id,
            subtask_id=subtask_id,
            member_ref=member_ref,
            fence=fence,
            authorized_node_refs=frozenset(str(ref) for ref in authorized_node_refs),
            max_collab_calls=max_collab_calls,
            budget_remaining=budget_remaining,
            expires_at=time.time() + max(1, ttl_seconds),
            origin=origin,
        )
        with self._lock:
            prior = self._by_subtask.get(subtask_id)
            if prior is not None:
                old = self._by_token.get(prior)
                if old is not None:
                    old.revoked = True
            self._by_token[token] = grant
            self._by_subtask[subtask_id] = token
        return token, grant

    # --------------------------------------------------------------- resolving
    def resolve(self, token: str | None, *, now: float | None = None) -> ExecutionGrant | None:
        if not isinstance(token, str) or not token:
            return None
        with self._lock:
            grant = self._by_token.get(token)
            if grant is None or not grant.active(now=now):
                return None
            return grant

    def resolve_worker_identity(self, token: str | None) -> str | None:
        grant = self.resolve(token)
        return grant.member_ref if grant is not None else None

    def consume_collab_call(self, token: str) -> tuple[bool, ExecutionGrant | None]:
        """Atomically reserve one frozen collaboration call for ``token``.

        Returns ``(allowed, grant)``.  A grant with a zero/absent collaboration
        allowance refuses, so a worker cannot exceed the program's budget by
        simply calling the tool again.
        """

        with self._lock:
            grant = self._by_token.get(token)
            if grant is None or not grant.active():
                return False, None
            if grant.collab_calls >= grant.max_collab_calls:
                return False, grant
            grant.collab_calls += 1
            return True, grant

    # --------------------------------------------------------------- revoking
    def revoke_token(self, token: str | None) -> bool:
        if not isinstance(token, str) or not token:
            return False
        with self._lock:
            grant = self._by_token.pop(token, None)
            if grant is None:
                return False
            grant.revoked = True
            if self._by_subtask.get(grant.subtask_id) == token:
                self._by_subtask.pop(grant.subtask_id, None)
            return True

    def revoke_subtask(self, subtask_id: str) -> bool:
        with self._lock:
            token = self._by_subtask.get(subtask_id)
        return self.revoke_token(token)

    def revoke_run(self, run_id: str) -> int:
        with self._lock:
            tokens = [
                token
                for token, grant in self._by_token.items()
                if grant.run_id == run_id
            ]
        return sum(1 for token in tokens if self.revoke_token(token))

    def active_grants(self) -> list[ExecutionGrant]:
        with self._lock:
            return [grant for grant in self._by_token.values() if grant.active()]


#: Process-wide registry.  This is the single seam the graph dispatcher (mint)
#: and the API context (resolve) share; tests may construct their own registry.
_DEFAULT_REGISTRY = ExecutionGrantRegistry()


def default_registry() -> ExecutionGrantRegistry:
    return _DEFAULT_REGISTRY


def reset_default_registry() -> None:
    """Test helper: drop every process-wide grant (never used in production)."""

    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = ExecutionGrantRegistry()


def resolve_worker_identity(
    request: Any,
    *,
    registry: ExecutionGrantRegistry | None = None,
    header: str = "X-LG-Execution-Grant",
) -> str | None:
    """Resolve the program-frozen member for an inbound request.

    The token is read from a request header; the body is never consulted.  A
    missing/expired/revoked token resolves to ``None`` (default-deny), so a
    local/web caller cannot impersonate a worker just by naming one.
    """

    resolved = registry or _DEFAULT_REGISTRY
    token: str | None = None
    try:
        headers = getattr(request, "headers", None)
        if headers is not None:
            token = headers.get(header)
    except Exception:  # noqa: BLE001 - a weird request object must deny, not crash
        token = None
    return resolved.resolve_worker_identity(token)


@dataclass(slots=True)
class PeerToolResult:
    """The minimal, structured reply a restricted peer tool hands back."""

    ok: bool
    reason: str
    state: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason, "state": self.state, **self.detail}


def make_restricted_peer_tool(
    *,
    registry: ExecutionGrantRegistry,
    token: str,
    peer_service_factory: Callable[[], Any],
    run_id: str,
    node_ref: str,
    from_member_ref: str,
    default_mode: str = "summarize",
) -> Callable[..., dict[str, Any]]:
    """Build an SDK custom tool bound to one frozen execution grant.

    The callable is what the SDK agent may invoke.  It performs **no** HTTP and
    takes **no** identity from arguments: the member, run and authorization come
    from the program-minted grant.  A request for a node outside the grant's
    authorized set, an exhausted collaboration budget, or a revoked grant is
    refused with a machine reason and never reaches the peer service.
    """

    def request_peer(
        to_member_ref: str | None = None,
        node_ref_override: str | None = None,
        summary: str = "",
        mode: str = default_mode,
        handoff_refs: list[str] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        grant = registry.resolve(token)
        if grant is None:
            return PeerToolResult(
                ok=False, reason="grant_revoked_or_expired", state="rejected"
            ).to_dict()
        target_node = node_ref_override or node_ref
        if not grant.covers_node(target_node):
            return PeerToolResult(
                ok=False,
                reason="node_not_authorized",
                state="rejected",
                detail={"node_ref": target_node, "run_ref": grant.run_id},
            ).to_dict()
        allowed, grant_after = registry.consume_collab_call(token)
        if not allowed:
            reason = "grant_revoked_or_expired" if grant_after is None else "budget_exhausted"
            return PeerToolResult(
                ok=False, reason=reason, state="rejected"
            ).to_dict()
        service = peer_service_factory()
        result = service.request(
            run_id,
            request_id=request_id or f"tool_{secrets.token_hex(8)}",
            from_member_ref=from_member_ref,
            to_member_ref=to_member_ref,
            mode=mode,
            summary=summary,
            node_ref=target_node,
            message_id=f"msg_tool_{secrets.token_hex(8)}",
            correlation_id=f"corr_tool_{secrets.token_hex(8)}",
            handoff_refs=handoff_refs or [],
            # The identity comes from the grant, never from tool arguments.
            authenticated_member_ref=grant.member_ref,
        )
        payload = result.to_dict()
        return PeerToolResult(
            ok=payload.get("state") in {"requested", "resolved"},
            reason=str(payload.get("reason") or payload.get("state") or "unknown"),
            state=str(payload.get("state") or "unknown"),
            detail={"result": payload},
        ).to_dict()

    request_peer.__name__ = "request_peer"
    request_peer.__doc__ = (
        "Request a controlled handoff/coordination with a peer member of this "
        "run.  Identity, run scope and budget are fixed by the program; only "
        "authorized nodes of this run can be addressed."
    )
    return request_peer


__all__ = [
    "DEFAULT_GRANT_SECONDS",
    "ExecutionGrant",
    "ExecutionGrantRegistry",
    "PeerToolResult",
    "default_registry",
    "make_restricted_peer_tool",
    "reset_default_registry",
    "resolve_worker_identity",
]
