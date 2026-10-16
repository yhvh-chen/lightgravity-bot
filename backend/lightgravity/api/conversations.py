"""Singleton global-conversation messages (docs/08 §4.3/§5.2, LG-012).

The global entry is the **only** conversation exposed over HTTP in this version;
Task conversation messages keep their own LG-007 routes under
``/tasks/{task_id}/messages``.  Messages are persisted through the coordinator's
``GlobalConversationLog`` (``bot-data/conversations/<id>/messages.jsonl``), so
the existing idempotency and layout are reused unchanged — this module is a thin
HTTP mapping, not a new conversation platform.

The path segment is the literal ``global``; it maps to one reserved, stable
conversation id that is a well-formed ``conv_<ULID>`` so the LG-004 log and the
runtime id grammar accept it without a special case.

``workspace_ref``/``agent_ref`` are **source-restricted**: they are validated
against server-authorized sources (a workspace inside the authorized root, and a
known agent resource) and never treated as instructions.  Unknown/escaping refs
are rejected, so a browser cannot point the global entry at an arbitrary
execution identity or directory.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from ..contracts import AppError, ErrorCode
from ..store import EntityNotFound
from ..store.ids import is_slug
from .context import ApiContext, get_context

#: Reserved, stable conversation id for the singleton global entry.  A
#: well-formed Crockford-base32 ``conv_<ULID>`` (all zeros) that is stable
#: across restarts, so global history has one durable location.
GLOBAL_CONVERSATION_ID = "conv_00000000000000000000000000"


class GlobalMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    content: str
    role: str = "user"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str | None = None
    request_id: str | None = None
    workspace_ref: str | None = None
    agent_ref: str | None = None
    #: Additive optional selected-material refs (docs/08 §6.6.1 / docs/10).
    selected_sources: list[dict[str, Any]] | None = None


def _authorize_source(
    ctx: ApiContext, workspace_ref: str | None, agent_ref: str | None
) -> None:
    """Reject source refs that do not resolve to an authorized source."""

    if workspace_ref is not None:
        if not isinstance(workspace_ref, str) or not workspace_ref.strip():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "workspace_ref must be a non-empty string",
                details={"field": "workspace_ref"},
            )
        # Raises PathOutsideWorkspace (403) for escapes/absolute paths.
        ctx.store.resolve_path(workspace_ref, write=False)
    if agent_ref is not None:
        if not is_slug(agent_ref):
            raise AppError(
                ErrorCode.REFERENCE_INVALID,
                f"invalid agent_ref {agent_ref!r}",
                details={"field": "agent_ref", "agent_ref": agent_ref},
            )
        try:
            ctx.store.read("agent", agent_ref)
        except EntityNotFound as exc:
            raise AppError(
                ErrorCode.REFERENCE_INVALID,
                f"agent_ref {agent_ref!r} does not resolve to a known agent",
                details={"field": "agent_ref", "agent_ref": agent_ref},
            ) from exc


def build_conversations_router() -> APIRouter:
    router = APIRouter(tags=["conversations"])

    @router.get("/conversations/global/messages")
    def read_global_messages(
        ctx: Annotated[ApiContext, Depends(get_context)],
        after: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=0, le=1000)] = 200,
    ) -> dict[str, Any]:
        items = ctx.coordinator.read_global_messages(
            GLOBAL_CONVERSATION_ID, after=after, limit=limit
        )
        next_cursor = (
            f"v1:{GLOBAL_CONVERSATION_ID}:{items[-1]['seq']}" if items else None
        )
        return {"items": items, "next_cursor": next_cursor}

    @router.post("/conversations/global/messages")
    async def append_global_message(
        payload: GlobalMessageRequest,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        _authorize_source(ctx, payload.workspace_ref, payload.agent_ref)
        message: dict[str, Any] = {
            "message_id": payload.message_id,
            "role": payload.role,
            "content": payload.content,
            "attachments": payload.attachments,
        }
        if payload.correlation_id:
            message["correlation_id"] = payload.correlation_id
        if payload.selected_sources is not None:
            message["selected_sources"] = payload.selected_sources
        result = await ctx.coordinator.submit_global_message(
            GLOBAL_CONVERSATION_ID,
            message,
            request_id=payload.request_id,
        )
        return result.to_dict()

    return router


__all__ = ["GLOBAL_CONVERSATION_ID", "GlobalMessageRequest", "build_conversations_router"]
