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

from .service import Coordinator


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
        if payload.resource_proposal is not None:
            # A resource proposal is a control change: require the same
            # injected authorization as the direct controlled PATCH, so the
            # conversation path cannot become an unauthenticated back door.
            policy = getattr(request.app.state, "access_policy", None)
            if policy is not None:
                policy.authorize(request, sensitive=True)
            message["resource_proposal"] = payload.resource_proposal
        if payload.selected_sources is not None:
            message["selected_sources"] = payload.selected_sources
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
