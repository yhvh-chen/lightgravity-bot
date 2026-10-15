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

Worker identity: this router does not accept an arbitrary ``owner`` from a
browser as an *authorization*.  Until the executor-identity seam is wired by the
integration owner (see ``probes/lg030/INTEGRATION.md``), the request body carries
the member identity and the peer service additionally requires that identity to
be a member of the same Run; the router itself is reachable only through the
frozen local access policy (``X-LG-Token`` when the runtime injects one), exactly
like the other control endpoints.  Server-side authentication of the caller is
LG-031's execution-identity injection, not something this body field can grant.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from ..collaboration import (
    ClaimPolicy,
    ClaimPolicyReader,
    ClaimRequest,
    CollaborationService,
    PeerService,
)
from .context import ApiContext, get_context


class ClaimRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    request_id: str
    subtask_ref: str
    lease_seconds: int | None = Field(default=None, gt=0)
    capability: str | None = None


class LeaseRenewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    lease_seconds: int | None = Field(default=None, gt=0)
    fence: int | None = Field(default=None, ge=0)


class LeaseReleaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
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


def build_collaboration_router() -> APIRouter:
    router = APIRouter(tags=["collaboration"])

    @router.get("/runs/{run_id}/discoverable")
    def discover(
        run_id: str,
        owner: str,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        view = _service(ctx).discover(run_id, owner)
        return view.to_dict()

    @router.post("/runs/{run_id}/claim_requests")
    def claim(
        run_id: str,
        payload: ClaimRequestBody,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        decision = _service(ctx).request_claim(
            run_id,
            ClaimRequest(
                subtask_id=payload.subtask_ref,
                owner=payload.owner,
                request_id=payload.request_id,
                lease_seconds=payload.lease_seconds,
                capability=payload.capability,
            ),
        )
        if decision.granted:
            response.headers["ETag"] = f'"{decision.revision}"'
        return decision.to_dict()

    @router.post("/subtasks/{subtask_id}/lease/renew")
    def renew(
        subtask_id: str,
        payload: LeaseRenewBody,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        renewal = _service(ctx).renew(
            subtask_id,
            payload.owner,
            fence=payload.fence,
            lease_seconds=payload.lease_seconds,
        )
        return renewal.to_dict()

    @router.post("/subtasks/{subtask_id}/lease/release")
    def release(
        subtask_id: str,
        payload: LeaseReleaseBody,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        released = _service(ctx).release(
            subtask_id,
            payload.owner,
            fence=payload.fence,
            reason=payload.reason or "released",
        )
        return {"subtask_ref": subtask_id, "owner": payload.owner, "released": released}

    @router.post("/runs/{run_id}/collab_requests")
    def request_collab(
        run_id: str,
        payload: CollabRequestBody,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
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


__all__ = ["build_collaboration_router"]
