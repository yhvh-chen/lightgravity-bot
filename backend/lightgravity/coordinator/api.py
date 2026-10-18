"""Independent FastAPI router for coordinator-owned endpoints (LG-007).

This module is intentionally **not** wired into ``lightgravity/api/app.py``;
LG-012 will mount :func:`build_router` under ``/api/v1``.  It only exposes the
endpoints docs/08 §4.3 assigns to LG-007:

* ``POST /tasks``              (idempotent on ``request_id``)
* ``POST /tasks/{task_id}/messages`` (idempotent on ``message_id``)
* ``GET  /tasks/{task_id}/messages`` (cursor)

Control actions live behind the LG-009/LG-016 action contract and are reached
through :meth:`Coordinator.request_control`; the router does not invent a new
wire shape for them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..contracts import AppError, ErrorCode
from .service import Coordinator


def _team_identity(request: Request) -> Any | None:
    """Resolve the server-side team identity for a request, if team mode is on."""

    context = getattr(request.app.state, "context", None)
    service = getattr(context, "team", None) if context is not None else None
    if service is None:
        return None
    from ..team import COOKIE_NAME

    return service.resolve(request.cookies.get(COOKIE_NAME))


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    title: str
    objective: str
    scope: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    workspace_ref: str | None = None


class AppendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    content: str
    role: str = "user"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str | None = None
    task_ref: str | None = None
    #: Additive structured resource-change proposal (docs/08 §5.2 / LG-015).
    #: Validated and applied by the coordinator through ``ResourceService``.
    resource_proposal: dict[str, Any] | None = None
    #: Additive optional selected-material refs (docs/08 §6.6.1 / docs/10).
    #: Opaque ``{source_id, source_version?, content_hash?}``; ≤3 entries.
    selected_sources: list[dict[str, Any]] | None = None
    #: Additive LG-144 receipt-only message refs (docs/08 §20.3).  Only
    #: ``source_id`` is read; the server replaces it with a normalized snapshot.
    source_refs: list[dict[str, Any]] | None = None


def _source_refs_service(request: Request) -> Any:
    """Resolve the app source service used for message ``source_refs``.

    The provider is installed by ``create_app`` and shares the store the
    sources router/worker read.  Without it the additive field is unavailable
    rather than silently dropped.
    """

    provider = getattr(request.app.state, "source_service_provider", None)
    if provider is not None:
        return provider()
    return getattr(request.app.state, "source_service", None)


def build_router(coordinator: Coordinator) -> APIRouter:
    """Build the coordinator router bound to ``coordinator``."""

    router = APIRouter(tags=["coordinator"])

    @router.post("/tasks")
    async def create_task(payload: CreateTaskRequest) -> dict[str, Any]:
        result = coordinator.create_task(
            request_id=payload.request_id,
            title=payload.title,
            objective=payload.objective,
            scope=payload.scope,
            acceptance_criteria=tuple(payload.acceptance_criteria),
            workspace_ref=payload.workspace_ref,
        )
        return result.to_dict()

    @router.post("/tasks/{task_id}/messages")
    async def append_message(
        task_id: str, payload: AppendMessageRequest, request: Request
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "message_id": payload.message_id,
            "role": payload.role,
            "content": payload.content,
            "attachments": payload.attachments,
        }
        if payload.correlation_id:
            message["correlation_id"] = payload.correlation_id
        if payload.task_ref:
            message["task_ref"] = payload.task_ref
        # LG-050: author is server-injected from the resolved team session; the
        # request body cannot self-report it (role alone is not identity).
        identity = _team_identity(request)
        if identity is not None:
            message["author"] = {
                "kind": "user",
                "username": identity.username,
                "role": identity.role,
            }
        if payload.resource_proposal is not None:
            # A resource proposal is a control change: require the same
            # injected authorization as the direct controlled PATCH, so the
            # conversation path cannot become an unauthenticated back door.
            # In team mode it is additionally admin-only.
            policy = getattr(request.app.state, "access_policy", None)
            if policy is not None:
                policy.authorize(request, sensitive=True, admin=True)
            message["resource_proposal"] = payload.resource_proposal
        if payload.selected_sources is not None:
            message["selected_sources"] = payload.selected_sources
        if payload.source_refs is not None:
            service = _source_refs_service(request)
            if service is None:
                raise AppError(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "message source_refs are not available on this server",
                    details={"field": "source_refs", "capability": "material_intake_v2"},
                )
            # Validate against the authoritative file SoT and persist only the
            # server-normalized snapshot.  The client's version/hash/scope are
            # never trusted, and ``source_refs`` is never model context.
            normalized = service.resolve_message_source_refs(
                task_ref=task_id, refs=payload.source_refs
            )
            if normalized:
                message["source_refs"] = normalized
        result = await coordinator.submit_task_message(task_id, message)
        return result.to_dict()

    @router.get("/tasks/{task_id}/messages")
    async def read_messages(
        task_id: str,
        after: str | None = Query(default=None),
        limit: int = Query(default=200, ge=0, le=1000),
    ) -> dict[str, Any]:
        items = coordinator.read_task_messages(task_id, after=after, limit=limit)
        next_cursor = f"v1:{task_id}:{items[-1]['seq']}" if items else None
        return {"items": items, "next_cursor": next_cursor}

    return router


__all__ = ["build_router", "CreateTaskRequest", "AppendMessageRequest"]
