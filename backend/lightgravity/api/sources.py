"""Source-intake HTTP endpoints (LG-034, docs/08 §4.3/§6.6).

Implements the endpoints frozen for this task:

* ``POST /sources``                 — register+persist an original (idempotent
  by ``request_id``; no Task/Run/team is created)
* ``GET  /sources``                 — authorized, scope-filtered list
* ``GET  /sources/{source_id}``     — detail (never echoes an escaping path)
* ``GET  /sources/{source_id}/receipt`` — per-file receipt built from the same
  file state the Files/Chat views read
* ``GET  /intake/jobs/{job_id}``    — intake job status (logical view over the
  file SoT, not a second state store)
* ``POST /intake/jobs/{job_id}/actions`` — ``cancel``/``retry`` (cancel needs a
  confirmed stop; interrupted jobs are not auto-replayed)
* ``POST /inbox/messages``          — controlled inbox entry; global material
  does **not** force a Task

The router factory only depends on :class:`ApiContext`, so wiring is a single
``app.include_router(build_sources_router(), prefix=API_PREFIX)`` line in the
integration owner's ``api/app.py`` (see ``probes/lg034/INTEGRATION.md``).  What
``POST /sources`` accepts is always *data*: the request body cannot grant
execution permissions, and every path/ref is program-checked.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..contracts import AppError, ErrorCode
from ..store.errors import ConfigInvalid, EntityNotFound
from .context import ApiContext, get_context

#: Request-id contract shared with Task messages (docs/08 §4.1).
_MAX_BASE64 = 16_000_000


class SourceScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_ref: str | None = None
    project_ref: str | None = None
    inbox_ref: str | None = None


class SourceOriginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = "upload"
    external_ref: str | None = None
    fetched: bool = False


class SourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    filename: str
    #: Exactly one of ``path`` (workspace-relative, authorized) or
    #: ``content_base64`` (inline, bounded) must be provided.
    path: str | None = None
    content_base64: str | None = None
    media_type: str | None = None
    title: str | None = None
    title_origin: str = "user"
    scope: SourceScopeRequest = Field(default_factory=SourceScopeRequest)
    origin: SourceOriginRequest = Field(default_factory=SourceOriginRequest)
    payload_hash: str | None = None


class JobActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    confirmed: bool = False
    note: str | None = None


class InboxMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    content: str = ""
    inbox_ref: str | None = None
    attachment_base64: str | None = None
    attachment_filename: str | None = None
    media_type: str | None = None


class SourceActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    #: Optional intake job to cancel/reprocess; required for ``cancel``.
    job_id: str | None = None
    confirmed: bool = False
    note: str | None = None
    #: Optional optimistic-concurrency guard for state-changing actions.
    expected_revision: int | None = None


class FormalEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    edited_by: str = "user"
    expected_revision: int | None = None


def _service(request: Request, ctx: ApiContext) -> Any:
    """Return the per-app source service, built from the live Store context.

    The service is cached on ``app.state`` (one file-backed engine per process)
    while Task-attribution authorization still reads the app's injectable Store.
    """

    cached = getattr(request.app.state, "source_service", None)
    if cached is not None:
        return cached

    from ..sources import build_source_service

    def _resolve(relative: str, write: bool) -> Any:
        return ctx.store.resolve_path(relative, write=write)

    service = build_source_service(
        data_dir=ctx.data_dir,
        task_store=ctx.store,
        resolve_path=_resolve,
        events=ctx.store,
    )
    request.app.state.source_service = service
    return service


def _receive(ctx: ApiContext, service: Any, payload: SourceCreateRequest) -> Any:
    has_path = bool(payload.path)
    has_inline = payload.content_base64 is not None
    if has_path == has_inline:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "provide exactly one of 'path' or 'content_base64'",
            details={"path": payload.path is not None, "content_base64": has_inline},
        )
    if payload.content_base64 is not None and len(payload.content_base64) > _MAX_BASE64:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "content_base64 exceeds the maximum accepted size",
            details={"max_base64_chars": _MAX_BASE64},
        )
    scope = payload.scope
    origin = payload.origin
    if has_path:
        return service.receive_from_path(
            request_id=payload.request_id,
            path=payload.path or "",
            filename=payload.filename,
            task_ref=scope.task_ref,
            project_ref=scope.project_ref,
            inbox_ref=scope.inbox_ref,
            title=payload.title,
            title_origin=payload.title_origin,
            media_type=payload.media_type,
            origin_kind=origin.kind,
            external_ref=origin.external_ref,
            fetched=origin.fetched,
            payload_hash=payload.payload_hash,
        )
    return service.receive_inline(
        request_id=payload.request_id,
        filename=payload.filename,
        content_base64=payload.content_base64 or "",
        task_ref=scope.task_ref,
        project_ref=scope.project_ref,
        inbox_ref=scope.inbox_ref,
        title=payload.title,
        title_origin=payload.title_origin,
        media_type=payload.media_type,
        origin_kind=origin.kind,
        external_ref=origin.external_ref,
        fetched=origin.fetched,
        payload_hash=payload.payload_hash,
    )


def _result_view(service: Any, result: Any) -> dict[str, Any]:
    """Shape a receive result using the same projections the read routes use."""

    return {
        "source": service._source_view(result.source),
        "job": service._job_view(result.job),
        "deduplicated": result.deduplicated,
        "created": result.created,
        "receipts": [entry.to_dict() for entry in result.receipts],
    }


def build_sources_router() -> APIRouter:
    router = APIRouter(tags=["sources"])

    @router.post("/sources")
    def create_source(
        payload: SourceCreateRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        response: Response,
    ) -> dict[str, Any]:
        result = _receive(ctx, _service(request, ctx), payload)
        response.status_code = 201 if result.created else 200
        response.headers["ETag"] = result.source.etag
        return _result_view(_service(request, ctx), result)

    @router.get("/sources")
    def list_sources(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        task_ref: Annotated[str | None, Query()] = None,
        project_ref: Annotated[str | None, Query()] = None,
        inbox_ref: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        cursor: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        return _service(request, ctx).list_sources(
            task_ref=task_ref,
            project_ref=project_ref,
            inbox_ref=inbox_ref,
            limit=limit,
            cursor=cursor,
        )

    @router.get("/sources/{source_id}")
    def get_source(
        source_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        try:
            return _service(request, ctx).get_source(source_id)
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} not found",
                details={"source_id": source_id},
            ) from None

    @router.get("/sources/{source_id}/receipt")
    def get_receipt(
        source_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        try:
            return _service(request, ctx).receipt(source_id)
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} not found",
                details={"source_id": source_id},
            ) from None

    @router.get("/intake/jobs/{job_id}")
    def get_job(
        job_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        try:
            return _service(request, ctx).get_job(job_id)
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"intake job {job_id!r} not found",
                details={"job_id": job_id},
            ) from None

    @router.post("/intake/jobs/{job_id}/actions")
    def job_action(
        job_id: str,
        payload: JobActionRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        service = _service(request, ctx)
        try:
            if payload.action == "cancel":
                job = service.intake.cancel(job_id, confirmed=payload.confirmed, reason=payload.note)
                return {"job_id": job_id, "action": "cancel", "status": job.status, "confirmed": True}
            if payload.action == "retry":
                job = service.intake.retry(job_id)
                return {"job_id": job_id, "action": "retry", "status": job.status, "confirmed": True}
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"intake job {job_id!r} not found",
                details={"job_id": job_id},
            ) from None
        except ConfigInvalid as exc:
            raise AppError(ErrorCode.VALIDATION_FAILED, exc.message, details=exc.details) from exc
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            f"unsupported action {payload.action!r}; supported: cancel, retry",
            details={"action": payload.action},
        )

    @router.get("/sources/{source_id}/content")
    def get_source_content(
        source_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        kind: Annotated[str, Query(pattern="^(auto|formal|machine)$")] = "auto",
    ) -> dict[str, Any]:
        try:
            return _service(request, ctx).content_view(source_id, kind=kind)
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} not found",
                details={"source_id": source_id},
            ) from None

    @router.get("/sources/{source_id}/download")
    def download_source(
        source_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        kind: Annotated[str, Query(pattern="^(original|formal|machine)$")] = "original",
    ) -> Response:
        try:
            view = _service(request, ctx).download_view(source_id, kind=kind)
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} not found",
                details={"source_id": source_id},
            ) from None
        # ``stat_revision`` is a size-mtime token, explicitly NOT a crypto hash.
        return Response(
            content=view["bytes"],
            media_type=view["media_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{view["filename"]}"',
                "ETag": f'"{view["stat_revision"]}"',
                "X-LG-Stat-Revision": view["stat_revision"],
                "X-LG-Kind": view["kind"],
            },
        )

    @router.post("/sources/{source_id}/actions")
    def source_action(
        source_id: str,
        payload: SourceActionRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        try:
            return _service(request, ctx).source_actions(
                source_id,
                action=payload.action,
                confirmed=payload.confirmed,
                job_id=payload.job_id,
                expected_revision=payload.expected_revision,
            )
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} not found",
                details={"source_id": source_id},
            ) from None

    @router.post("/sources/{source_id}/formal")
    def edit_source_formal(
        source_id: str,
        payload: FormalEditRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        try:
            return _service(request, ctx).edit_formal(
                source_id,
                content=payload.content,
                edited_by=payload.edited_by,
                expected_revision=payload.expected_revision,
            )
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} not found",
                details={"source_id": source_id},
            ) from None

    @router.post("/inbox/messages")
    def inbox_message(
        payload: InboxMessageRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        response: Response,
    ) -> dict[str, Any]:
        service = _service(request, ctx)
        inbox_ref = payload.inbox_ref or service.create_inbox()
        if payload.inbox_ref is None:
            response.status_code = 201
        message = service.append_inbox_message(
            inbox_id=inbox_ref,
            message_id=payload.message_id,
            content=payload.content,
            attachment_base64=payload.attachment_base64,
            attachment_filename=payload.attachment_filename,
            media_type=payload.media_type,
        )
        # Explicitly report that no delivery Task/Run was created (docs/08 §6.6).
        return {
            "inbox_ref": inbox_ref,
            "message": message,
            "task_created": False,
            "run_created": False,
        }

    return router


__all__ = ["build_sources_router", "MAX_INLINE_BYTES"]


# Re-exported for callers that import the bound constant without the service.
from ..sources.service import MAX_INLINE_BYTES  # noqa: E402
