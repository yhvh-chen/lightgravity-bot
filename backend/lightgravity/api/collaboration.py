"""Decentralized discovery/claim/lease/协作 endpoints (LG-029, docs/08 §4.3).

Covers the LG-029-owned frozen endpoints:

* ``GET  /runs/{run_id}/discoverable``                 read-only authorized projection
* ``POST /runs/{run_id}/claim_requests``               candidate claim request
* ``POST /subtasks/{subtask_id}/lease/renew``          lease renewal (``fence``)
* ``POST /subtasks/{subtask_id}/lease/release``        holder/program release

The peer endpoints (``POST/GET /runs/{run_id}/collab_requests``) belong to
LG-030 and are deliberately **not** registered here.

Default-off: the endpoints always exist but behave inertly when
``decentralized_claim_enabled`` is false — discovery returns an empty, disabled
projection and claims are refused with ``claim_refused``/``feature_disabled`` —
so the deterministic scheduler path is unchanged (docs/08 §6.5).

Worker identity: this router does not accept an arbitrary ``owner`` from a
browser.  Until the executor-identity seam is wired by the integration owner
(see ``probes/lg029/INTEGRATION.md``), the request body carries the owner and the
router is reachable only through the frozen local access policy
(``X-LG-Token`` when the runtime injects one), exactly like the other control
endpoints.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from ..collaboration import (
    ClaimPolicy,
    ClaimPolicyReader,
    ClaimRequest,
    CollaborationService,
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


def _service(ctx: ApiContext) -> CollaborationService:
    """Build the claim/lease service with the current default-off policy."""

    policy: ClaimPolicy = ClaimPolicyReader(ctx.store).read()
    return CollaborationService(ctx.store, policy=policy)


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

    return router


__all__ = ["build_collaboration_router"]
