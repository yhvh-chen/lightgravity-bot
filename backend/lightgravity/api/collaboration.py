"""Decentralized discovery/claim/lease/协作 endpoints (LG-029 + LG-030, docs/08 §4.3).

Covers the frozen endpoints owned by this collaboration line:

* ``GET  /runs/{run_id}/discoverable``                 read-only authorized projection (LG-029)
* ``POST /runs/{run_id}/claim_requests``               candidate claim request (LG-029)
* ``POST /subtasks/{subtask_id}/lease/renew``          lease renewal (``fence``) (LG-029)
* ``POST /subtasks/{subtask_id}/lease/release``        holder/program release (LG-029)
* ``POST /runs/{run_id}/collab_requests``              controlled peer request (LG-030)
* ``GET  /runs/{run_id}/collab_requests``              peer request/result projection (LG-030)

Default-off: the endpoints always exist but behave inertly when the respective
switch is false — discovery returns an empty, disabled projection and claims are
refused with ``claim_refused``/``feature_disabled``; peer requests are rejected
with ``feature_disabled`` — so the deterministic scheduler path is unchanged
(docs/08 §6.5).

Execution identity (LG-029 F2 fix): the discovery/claim/renew/release endpoints
take **no** authorization from the request body.  They resolve the
program-frozen execution grant through :attr:`ApiContext.worker_grant` (the same
opaque, process-local grant the graph dispatcher mints via
``ExecutionGrantRegistry``), and derive from it, exclusively:

* **who** the caller is (``member_ref`` → the program-recorded lease owner);
* **which Run/Task** it is scoped to (``run_id`` must equal the path);
* **which nodes** it may discover/claim (``authorized_node_refs``);
* **which fence** it may renew/release (``fence``).

A body ``owner``/``capability``/``write``/``scope`` can therefore never grant or
widen access: when the body names a different principal the request is refused
with ``claim_refused``/``identity_mismatch`` (nothing persisted), and when no
grant resolver is wired the endpoints default-deny with
``claim_refused``/``unauthenticated``.  This keeps a browser or local caller from
acting as an arbitrary run member or stealing a peer's lease.

The peer (LG-030) endpoints keep their existing seam: the body's
``from_member_ref`` must equal the program-authenticated identity from
:attr:`ApiContext.worker_identity` and is never itself trusted.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..collaboration import (
    ClaimPolicy,
    ClaimPolicyReader,
    ClaimRequest,
    CollaborationService,
    PeerService,
    default_registry as default_grant_registry,
)
from ..collaboration.errors import ClaimRefused
from ..collaboration.execution_grant import ExecutionGrant
from .context import ApiContext, get_context

#: Header an executor presents with its program-minted execution grant.
GRANT_HEADER = "X-LG-Execution-Grant"


def resolve_request_grant(request: Request) -> ExecutionGrant | None:
    """Resolve the program-frozen grant a request presents (header-only).

    The opaque token is read from :data:`GRANT_HEADER` and looked up in the
    process-wide registry the graph dispatcher mints into; the request body is
    never consulted.  A missing/expired/revoked token resolves to ``None``
    (default-deny), so a caller cannot authenticate by naming a member in a
    payload.  This is the concrete resolver bootstrap wires into
    :attr:`ApiContext.worker_grant`.
    """

    token: str | None = None
    try:
        headers = getattr(request, "headers", None)
        if headers is not None:
            token = headers.get(GRANT_HEADER)
    except Exception:  # noqa: BLE001 - a weird request object must deny, not crash
        return None
    if not isinstance(token, str) or not token:
        return None
    return default_grant_registry().resolve(token)


class ClaimRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Compatibility field.  It is **not** authentication: when present it must
    #: equal the program-authenticated principal, otherwise the request is
    #: refused without persisting anything.
    owner: str | None = None
    request_id: str
    subtask_ref: str
    lease_seconds: int | None = Field(default=None, gt=0)
    #: Advisory only.  Capability is program-bound by the grant/discovery; this
    #: field can never grant a capability the program did not authorize.
    capability: str | None = None


class LeaseRenewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str | None = None
    lease_seconds: int | None = Field(default=None, gt=0)
    fence: int | None = Field(default=None, ge=0)


class LeaseReleaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str | None = None
    fence: int | None = Field(default=None, ge=0)
    reason: str | None = None


class CollabRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    from_member_ref: str
    to_member_ref: str | None = None
    node_ref: str
    mode: str = "summarize"
    summary: str
    message_id: str
    correlation_id: str
    in_reply_to: str | None = None
    handoff_refs: list[str] = Field(default_factory=list)
    fence: int | None = Field(default=None, ge=0)
    timeout_seconds: int | None = Field(default=None, gt=0)


def _service(ctx: ApiContext) -> CollaborationService:
    """Build the claim/lease service with the current default-off policy."""

    policy: ClaimPolicy = ClaimPolicyReader(ctx.store).read()
    return CollaborationService(ctx.store, policy=policy)


def _peer_service(ctx: ApiContext) -> PeerService:
    """Build the peer service with the current default-off policy."""

    policy: ClaimPolicy = ClaimPolicyReader(ctx.store).read()
    return PeerService(ctx.store, data_dir=ctx.data_dir, policy=policy)


def _refuse(reason: str, message: str, **details: Any) -> ClaimRefused:
    return ClaimRefused(reason, message, details=details or None)


def _require_grant(ctx: ApiContext, request: Request) -> ExecutionGrant:
    """Resolve the program-frozen grant or default-deny (no business writes).

    A missing/expired/revoked grant, or a runtime without a grant resolver,
    refuses with ``unauthenticated`` so a caller can never fall back to a
    body-supplied ``owner``.
    """

    resolver = ctx.worker_grant
    if resolver is None:
        raise _refuse(
            "unauthenticated",
            "no program execution-identity resolver is configured",
        )
    try:
        grant = resolver(request)
    except Exception:  # noqa: BLE001 - a failing resolver must deny, not crash
        grant = None
    if grant is None or not grant.active():
        raise _refuse(
            "unauthenticated",
            "no active program execution grant was presented",
        )
    return grant


def _grant_owner(grant: ExecutionGrant) -> str:
    """The program-frozen lease owner (never a request-body value).

    The grant's ``member_ref`` is the program-authenticated principal; using it
    as the lease owner means an authenticated worker can only ever act as
    itself.  (A future graph-side owner override would be carried on the grant,
    not taken from the body.)
    """

    return grant.member_ref


def _check_body_owner(payload_owner: str | None, grant: ExecutionGrant) -> None:
    """Reject a body that names a principal other than the authenticated one.

    The body ``owner`` is compatibility-only; a mismatch is a definite refusal
    and never an alternate identity.
    """

    if payload_owner is None:
        return
    if payload_owner != grant.member_ref:
        raise _refuse(
            "identity_mismatch",
            "request owner does not match the program-authenticated principal",
            authenticated=grant.member_ref,
        )


def _check_run_scope(grant: ExecutionGrant, run_id: str) -> None:
    if grant.run_id != run_id:
        raise _refuse(
            "identity_mismatch",
            "execution grant is scoped to a different run",
            grant_run=grant.run_id,
            requested_run=run_id,
        )


def _check_node_scope(grant: ExecutionGrant, subtask_id: str) -> None:
    """A grant may only act on its own node or one it was authorized to see."""

    if subtask_id == grant.subtask_id:
        return
    if subtask_id in grant.authorized_node_refs:
        return
    raise _refuse(
        "not_discoverable",
        "execution grant does not authorize this node",
        subtask_ref=subtask_id,
    )


def _check_fence(grant: ExecutionGrant, fence: int | None) -> int:
    """Bind the caller to the program-recorded fence; a body cannot lower it."""

    if fence is None:
        return grant.fence
    if fence != grant.fence:
        # Imported lazily to avoid a hard import cycle at module load.
        from ..collaboration.errors import StaleLease

        raise StaleLease(
            grant.subtask_id,
            provided=fence,
            current=grant.fence,
            reason="fence_mismatch",
        )
    return fence


def build_collaboration_router() -> APIRouter:
    router = APIRouter(tags=["collaboration"])

    @router.get("/runs/{run_id}/discoverable")
    def discover(
        run_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        owner: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        grant = _require_grant(ctx, request)
        _check_run_scope(grant, run_id)
        _check_body_owner(owner, grant)
        view = _service(ctx).discover(run_id, _grant_owner(grant))
        payload = view.to_dict()
        # Restrict the authorized projection to exactly the nodes the grant
        # covers, so a caller cannot discover beyond its program-frozen scope.
        allowed = set(grant.authorized_node_refs) | {grant.subtask_id}
        payload["items"] = [
            item for item in payload.get("items", []) if item.get("subtask_ref") in allowed
        ]
        return payload

    @router.post("/runs/{run_id}/claim_requests")
    def claim(
        run_id: str,
        payload: ClaimRequestBody,
        response: Response,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        grant = _require_grant(ctx, request)
        _check_run_scope(grant, run_id)
        _check_body_owner(payload.owner, grant)
        _check_node_scope(grant, payload.subtask_ref)
        decision = _service(ctx).request_claim(
            run_id,
            ClaimRequest(
                subtask_id=payload.subtask_ref,
                owner=_grant_owner(grant),
                request_id=payload.request_id,
                lease_seconds=payload.lease_seconds,
                # Capability is program-bound; the body value is never an
                # authorization input (discovery already filters by the grant).
                capability=None,
            ),
        )
        if decision.granted:
            response.headers["ETag"] = f'"{decision.revision}"'
        return decision.to_dict()

    @router.post("/subtasks/{subtask_id}/lease/renew")
    def renew(
        subtask_id: str,
        payload: LeaseRenewBody,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        grant = _require_grant(ctx, request)
        _check_node_scope(grant, subtask_id)
        _check_body_owner(payload.owner, grant)
        fence = _check_fence(grant, payload.fence)
        renewal = _service(ctx).renew(
            subtask_id,
            _grant_owner(grant),
            fence=fence,
            lease_seconds=payload.lease_seconds,
        )
        return renewal.to_dict()

    @router.post("/subtasks/{subtask_id}/lease/release")
    def release(
        subtask_id: str,
        payload: LeaseReleaseBody,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        grant = _require_grant(ctx, request)
        _check_node_scope(grant, subtask_id)
        _check_body_owner(payload.owner, grant)
        fence = _check_fence(grant, payload.fence)
        released = _service(ctx).release(
            subtask_id,
            _grant_owner(grant),
            fence=fence,
            reason=payload.reason or "released",
        )
        return {
            "subtask_ref": subtask_id,
            "owner": _grant_owner(grant),
            "released": released,
        }

    @router.post("/runs/{run_id}/collab_requests")
    def request_collab(
        run_id: str,
        payload: CollabRequestBody,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        # Program-authenticated identity only.  The body's ``from_member_ref`` is
        # not authentication; when no execution-identity seam is wired the
        # resolver returns ``None`` and the service refuses (default-deny).
        authenticated = (
            ctx.worker_identity(request) if ctx.worker_identity is not None else None
        )
        result = _peer_service(ctx).request(
            run_id,
            request_id=payload.request_id,
            from_member_ref=payload.from_member_ref,
            to_member_ref=payload.to_member_ref,
            mode=payload.mode,
            summary=payload.summary,
            node_ref=payload.node_ref,
            message_id=payload.message_id,
            correlation_id=payload.correlation_id,
            in_reply_to=payload.in_reply_to,
            handoff_refs=payload.handoff_refs,
            fence=payload.fence,
            timeout_seconds=payload.timeout_seconds,
            authenticated_member_ref=authenticated,
        )
        return result.to_dict()

    @router.get("/runs/{run_id}/collab_requests")
    def list_collab(
        run_id: str,
        ctx: Annotated[ApiContext, Depends(get_context)],
        after: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        results = _peer_service(ctx).list_requests(run_id, after=after, limit=limit)
        return {
            "run_ref": run_id,
            "enabled": _peer_service(ctx).enabled,
            "items": [result.to_dict() for result in results],
        }

    return router


__all__ = ["GRANT_HEADER", "build_collaboration_router", "resolve_request_grant"]
