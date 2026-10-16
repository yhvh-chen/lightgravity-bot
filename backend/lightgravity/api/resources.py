"""Resource and Team read endpoints plus controlled resource writes (LG-015).

``GET /resources/{kind}`` and ``GET /resources/{kind}/{id}`` expose the seven
Resources navigation categories plus agent templates.  Reads go through the
LG-004 ``Store`` (Markdown is the single authority) and the LG-015
``ResourceService``, which keeps declared/parsed/dependency/runtime availability
separate and never fakes a live health check.

``PATCH /resources/{kind}/{id}`` is the *controlled* modification path for
non-connection resources: an allow-listed field patch is re-parsed with the
adapter schema, every reference is resolved, and the change is written through
``Store.write`` with ``expected_revision`` (atomic + optimistic concurrency).
Connections are rejected here and must be edited through the Settings endpoints,
which own the same Connection entity.  Sensitive writes re-use the frozen
``AccessPolicy``/runtime token rather than opening an unauthenticated path.

``GET /team/available`` and ``GET /team/members`` back the Team view: available
agent templates with compiled availability, and Member instances (current plus
released history).  These are additive read endpoints; the frozen docs/08 §4.3
table does not yet list them, so integration must register them.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..contracts import AppError, ErrorCode
from ..resources import ResourceService
from .context import ApiContext, get_context


class ResourceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    #: Allow-listed top-level frontmatter fields for this kind.
    patch: dict[str, Any] = Field(default_factory=dict)
    #: Optional replacement Markdown body (never executed).
    body: str | None = None


def _service(ctx: ApiContext) -> ResourceService:
    return ResourceService(
        ctx.store,
        data_dir=ctx.data_dir,
        connections=ctx.connections,
    )


def build_resource_router() -> APIRouter:
    router = APIRouter(tags=["resources"])

    @router.get("/resources/{kind}")
    def list_resources(
        kind: str,
        ctx: Annotated[ApiContext, Depends(get_context)],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        cursor: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        return _service(ctx).list_resources(kind, limit=limit, cursor=cursor)

    @router.get("/resources/{kind}/{resource_id}")
    def get_resource(
        kind: str,
        resource_id: str,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        detail = _service(ctx).detail(kind, resource_id)
        response.headers["ETag"] = str(detail["etag"])
        return detail

    @router.patch("/resources/{kind}/{resource_id}")
    def update_resource(
        kind: str,
        resource_id: str,
        payload: ResourceUpdateRequest,
        request: Request,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        # The global dependency already applied the non-sensitive policy; a
        # resource write is a control change, so require the injected local
        # token as well.  This re-uses the LG-012 AccessPolicy; it does not
        # bypass the default-deny behaviour.
        ctx.access.authorize(request, sensitive=True)
        if kind == "connection":
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "connections are edited through the Settings endpoints; there is one "
                "Connection authority and no second model list",
                details={
                    "kind": kind,
                    "id": resource_id,
                    "use": f"/api/v1/settings/connections/{resource_id}",
                },
            )
        detail = _service(ctx).update(
            kind,
            resource_id,
            patch=payload.patch,
            expected_revision=payload.expected_revision,
            actor="api",
            body=payload.body,
        )
        response.headers["ETag"] = str(detail["etag"])
        return detail

    @router.get("/team/available")
    def list_available_agents(
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        return {"items": _service(ctx).available_agents(), "next_cursor": None}

    @router.get("/team/members")
    def list_members(
        ctx: Annotated[ApiContext, Depends(get_context)],
        task_ref: Annotated[str | None, Query()] = None,
        run_ref: Annotated[str | None, Query()] = None,
        include_released: Annotated[bool, Query()] = True,
    ) -> dict[str, Any]:
        items = _service(ctx).members(
            task_ref=task_ref,
            run_ref=run_ref,
            include_released=include_released,
        )
        return {"items": items, "next_cursor": None}

    return router


__all__ = ["build_resource_router", "ResourceUpdateRequest"]
