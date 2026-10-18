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

import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..attachments import (
    MAX_ATTACHMENTS_PER_MESSAGE,
    attachment_service_for,
)
from ..contracts import AppError, ErrorCode
from ..store import EntityNotFound
from ..store.ids import id_matches_kind, is_slug
from ..team import COOKIE_NAME
from .context import ApiContext, get_context

#: Reserved, stable conversation id for the singleton global entry.  A
#: well-formed Crockford-base32 ``conv_<ULID>`` (all zeros) that is stable
#: across restarts, so global history has one durable location.
GLOBAL_CONVERSATION_ID = "conv_00000000000000000000000000"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def personal_conversation_id(username: str) -> str:
    """Derive the stable, per-user private conversation id (LG-054).

    The id is a well-formed ``conv_<26 Crockford chars>`` produced from a
    one-way hash of the authenticated server identity, so:

    * it is stable across restarts (history persists in one file);
    * it can only be derived from the owner's session cookie, never a request
      body/query field, so no other member (including an admin) can address it;
    * it never exposes the raw username in a file path.
    """

    digest = hashlib.sha256(
        f"lightgravity:personal-conversation:v1:{username}".encode("utf-8")
    ).digest()
    return "conv_" + "".join(_CROCKFORD[byte % 32] for byte in digest[:26])


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
    #: Additive LG-144 receipt-only message refs (docs/08 §20.3).  Only
    #: ``source_id`` is read; the server replaces it with a normalized snapshot.
    source_refs: list[dict[str, Any]] | None = None


class PersonalMessageRequest(BaseModel):
    """Private Personal-chat message (LG-054, additive ``/conversations/personal``).

    ``extra="forbid"`` means a client-supplied ``owner``/``author``/``task_ref``
    is a 422: ownership is always the server-resolved session identity.  The
    source/attachment fields are accepted only so the handler can return a
    clear Team guidance instead of silently dropping them.
    """

    model_config = ConfigDict(extra="forbid")

    message_id: str
    content: str
    role: str = "user"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str | None = None
    request_id: str | None = None
    selected_sources: list[dict[str, Any]] | None = None
    workspace_ref: str | None = None
    agent_ref: str | None = None
    #: Accepted only so Personal can return the explicit Team guidance instead
    #: of silently dropping a shared-intake field (docs/08 §20.12).
    source_refs: list[dict[str, Any]] | None = None


def _session_cookie(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)


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


def _personal_owner(ctx: ApiContext, request: Request) -> tuple[str, str]:
    """Resolve the (owner, private-conversation-id) pair from server identity.

    Team mode: identity comes only from the HttpOnly session cookie.  Single
    mode: there is no privacy boundary and the legacy global conversation id is
    reused so old history/behaviour is preserved.
    """

    if ctx.team is None:
        return "single", GLOBAL_CONVERSATION_ID
    identity = ctx.team.resolve(_session_cookie(request))
    if identity is None:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "a valid team session is required for the personal conversation",
            details={"endpoint": "/conversations/personal/messages"},
        )
    return identity.username, personal_conversation_id(identity.username)


def _source_refs_service(request: Request) -> Any:
    """Resolve the app source service used for message ``source_refs``."""

    provider = getattr(request.app.state, "source_service_provider", None)
    if provider is not None:
        return provider()
    return getattr(request.app.state, "source_service", None)


def _normalize_source_refs(
    request: Request, refs: list[dict[str, Any]], *, task_ref: str | None
) -> list[dict[str, Any]]:
    """Validate and normalize receipt-only refs; never model context."""

    service = _source_refs_service(request)
    if service is None:
        raise AppError(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "message source_refs are not available on this server",
            details={"field": "source_refs", "capability": "material_intake_v2"},
        )
    return service.resolve_message_source_refs(task_ref=task_ref, refs=refs)


def _reject_shared_inputs(payload: PersonalMessageRequest) -> None:
    """Personal is chat-only: shared materials/sources are a Team concern."""

    hint = {
        "hint": "switch_to_team",
        "message": "Shared materials and task delivery are available in Team.",
    }
    if payload.selected_sources:
        raise AppError(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "Personal chat does not accept selected sources; "
            "shared materials and task delivery are available in Team.",
            details={"field": "selected_sources", **hint},
        )
    if payload.source_refs is not None:
        raise AppError(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "Personal chat does not accept shared source references; "
            "switch to Team to attach material receipts.",
            details={"field": "source_refs", **hint},
        )
    if payload.workspace_ref or payload.agent_ref:
        raise AppError(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "Personal chat does not accept workspace/agent references; "
            "shared materials and task delivery are available in Team.",
            details={"field": "workspace_ref", **hint},
        )


def _private_attachment_ids(payload: PersonalMessageRequest) -> list[str]:
    """Validate the Personal-only ``[{attachment_id}]`` shape.

    A client-supplied path/filename/size/hash is never trusted.  ``path`` is a
    hard validation error so a private attachment cannot be rewritten into a
    shared Task/Team reference; extra metadata is ignored because the server
    reloads the canonical record by owner + id.
    """

    ids: list[str] = []
    for item in payload.attachments:
        if not isinstance(item, dict):
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "Personal attachments must be {attachment_id} objects",
                details={"field": "attachments"},
            )
        if "path" in item:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "Personal attachments use attachment_id, not path",
                details={"field": "attachments", "hint": "use_private_attachment_id"},
            )
        attachment_id = item.get("attachment_id")
        if not isinstance(attachment_id, str) or not id_matches_kind(
            "att", attachment_id
        ):
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"field": "attachments"},
            )
        ids.append(attachment_id)
    if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            f"at most {MAX_ATTACHMENTS_PER_MESSAGE} private attachments are allowed per message",
            details={
                "field": "attachments",
                "max_attachments": MAX_ATTACHMENTS_PER_MESSAGE,
            },
        )
    if len(set(ids)) != len(ids):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "duplicate private attachment ids are not allowed",
            details={"field": "attachments"},
        )
    return ids


def _reject_private_attachment_refs(payload: GlobalMessageRequest) -> None:
    """The shared global/Team conversation never accepts private ids."""

    if any(
        isinstance(item, dict) and "attachment_id" in item
        for item in payload.attachments
    ):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "attachment_id is only accepted by the Personal conversation; "
            "Task/Team messages use path references",
            details={"field": "attachments", "surface": "global/team"},
        )


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
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        _authorize_source(ctx, payload.workspace_ref, payload.agent_ref)
        _reject_private_attachment_refs(payload)
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
        if payload.source_refs is not None:
            # Global/Team messages accept only global sources; a Task-scoped
            # source is rejected rather than widened to the shared scope.
            normalized = _normalize_source_refs(request, payload.source_refs, task_ref=None)
            if normalized:
                message["source_refs"] = normalized
        # LG-050: the author is server-injected from the resolved session, never
        # from the request.  ``GlobalMessageRequest`` forbids an ``author`` field
        # (extra="forbid"), so a client-supplied author is a 422 before this runs.
        if ctx.team is not None:
            identity = ctx.team.resolve(_session_cookie(request))
            if identity is not None:
                message["author"] = {
                    "kind": "user",
                    "username": identity.username,
                    "role": identity.role,
                }
        result = await ctx.coordinator.submit_global_message(
            GLOBAL_CONVERSATION_ID,
            message,
            request_id=payload.request_id,
        )
        response = result.to_dict()
        if response.get("kind") == "recorded":
            response["reply"] = None
        return response

    # ------------------------------------------------ private Personal chat
    @router.get("/conversations/personal/messages")
    def read_personal_messages(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        after: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=0, le=1000)] = 200,
    ) -> dict[str, Any]:
        _owner, conversation_id = _personal_owner(ctx, request)
        items = ctx.coordinator.read_global_messages(
            conversation_id, after=after, limit=limit
        )
        next_cursor = (
            f"v1:{conversation_id}:{items[-1]['seq']}" if items else None
        )
        return {"items": items, "next_cursor": next_cursor}

    @router.post("/conversations/personal/messages")
    async def append_personal_message(
        payload: PersonalMessageRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        owner, conversation_id = _personal_owner(ctx, request)
        _reject_shared_inputs(payload)
        attachment_ids = _private_attachment_ids(payload)
        service = attachment_service_for(ctx.data_dir)
        attachment_context = None
        claimed = []
        message: dict[str, Any] = {
            "message_id": payload.message_id,
            "role": payload.role,
            "content": payload.content,
            "attachments": [],
            "private": True,
        }
        if attachment_ids:
            # Claim first (stored -> attached) so two concurrent messages cannot
            # bind the same private bytes.  A failure before submit is rolled
            # back; the persisted snapshot is canonical server metadata.
            claimed = service.claim_for_message(
                owner, attachment_ids, payload.message_id
            )
            try:
                resolved = service.resolve_text_for_model(
                    owner,
                    attachment_ids,
                    message_id=payload.message_id,
                )
            except BaseException:
                service.release_claims(owner, attachment_ids, payload.message_id)
                raise
            message["attachments"] = [
                resolved.snapshot_for(attachment) for attachment in claimed
            ]
            attachment_context = resolved.text
            attachment_note = resolved.note
        else:
            attachment_note = None
        if payload.correlation_id:
            message["correlation_id"] = payload.correlation_id
        if ctx.team is not None:
            identity = ctx.team.resolve(_session_cookie(request))
            if identity is not None:
                message["author"] = {
                    "kind": "user",
                    "username": identity.username,
                    "role": identity.role,
                }
        try:
            result = await ctx.coordinator.submit_personal_message(
                conversation_id,
                message,
                owner=owner,
                request_id=payload.request_id,
                attachment_context=attachment_context,
                attachment_note=attachment_note,
            )
        except BaseException:
            if attachment_ids:
                service.release_claims(owner, attachment_ids, payload.message_id)
            raise
        response = result.to_dict()
        if response.get("kind") == "recorded":
            response["reply"] = None
        return response

    return router


__all__ = [
    "GLOBAL_CONVERSATION_ID",
    "GlobalMessageRequest",
    "PersonalMessageRequest",
    "build_conversations_router",
    "personal_conversation_id",
]
