"""Private Personal attachment HTTP routes (LG-119, docs/08 §19.3).

The route factory is complete and idempotent to mount::

    app.include_router(build_attachments_router(), prefix=API_PREFIX)

``api/app.py`` mounting and the optional ``private_attachments`` health
capability are owned by the serial integration owner.  Tests mount this same
factory through ``create_app`` fixtures so the real routes, dependencies and
context are exercised.

Identity is always the server-resolved session (team username) or ``single`` in
single-user mode.  A query/body owner field is never accepted; the metadata
response exposes no path and no owner.
"""

from __future__ import annotations

import base64
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from ..contracts import AppError, ErrorCode
from ..store.ids import id_matches_kind
from ..team import COOKIE_NAME
from .service import PrivateAttachmentService
from .store import AttachmentStore
from ..api.context import ApiContext, get_context

#: Preview and streaming bounds mirror the Files preview/download behaviour.
_CONTENT_PREVIEW_BYTES = 5_000_000
_BINARY_SNIFF_BYTES = 1024
_STREAM_CHUNK = 256 * 1024


def _service(ctx: ApiContext) -> PrivateAttachmentService:
    root = ctx.data_dir / "private-attachments"
    return PrivateAttachmentService(AttachmentStore(root), ctx.data_dir)


def _owner(ctx: ApiContext, request: Request) -> str:
    """Resolve owner from the server session; never from a request field."""

    if ctx.team is None:
        return "single"
    identity = ctx.team.resolve(request.cookies.get(COOKIE_NAME))
    if identity is None:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "a valid team session is required for private attachments",
            details={"endpoint": request.url.path},
        )
    return identity.username


def _content_disposition(filename: str) -> str:
    from urllib.parse import quote

    fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


async def _read_bounded(request: Request, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "upload exceeds the maximum private attachment size",
                details={"max_bytes": limit},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _attachment_view(attachment: Any) -> dict[str, Any]:
    return {"attachment": attachment.to_dict()}


def build_attachments_router() -> APIRouter:
    router = APIRouter(tags=["attachments"])

    @router.post("/attachments/private")
    async def upload_private_attachment(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        response: Response,
        attachment_id: Annotated[str | None, Query()] = None,
        filename: Annotated[str | None, Query()] = None,
        media_type: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        # Same-origin/loopback protected write plus current identity.  In team
        # mode the session cookie satisfies the write protection; there is no
        # admin bypass because the owner is always the session username.
        ctx.access.authorize(request, sensitive=True)
        owner = _owner(ctx, request)
        if not attachment_id or not attachment_id.strip():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "attachment_id is required",
                details={"field": "attachment_id"},
            )
        if not id_matches_kind("att", attachment_id):
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "attachment_id must be a well-formed att_<ULID>",
                details={"field": "attachment_id"},
            )
        if not filename or not filename.strip():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "filename is required",
                details={"field": "filename"},
            )
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                length = int(declared)
            except ValueError as exc:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "invalid Content-Length header",
                ) from exc
            if length < 0 or length > PrivateAttachmentService.max_upload_bytes():
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "upload exceeds the maximum private attachment size",
                    details={"max_bytes": PrivateAttachmentService.max_upload_bytes()},
                )
        data = await _read_bounded(
            request, PrivateAttachmentService.max_upload_bytes()
        )
        attachment, created = _service(ctx).upload(
            owner,
            attachment_id,
            filename=filename,
            media_type=media_type,
            data=data,
        )
        response.status_code = 201 if created else 200
        return _attachment_view(attachment)

    @router.get("/attachments/private/{attachment_id}")
    def read_private_attachment(
        attachment_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        owner = _owner(ctx, request)
        return _attachment_view(_service(ctx).get(owner, attachment_id))

    @router.get("/attachments/private/{attachment_id}/content")
    def private_attachment_content(
        attachment_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        owner = _owner(ctx, request)
        attachment, data, revision = _service(ctx).content(owner, attachment_id)
        if len(data) > _CONTENT_PREVIEW_BYTES:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "attachment exceeds the inline content limit; download it instead",
                details={"max_bytes": _CONTENT_PREVIEW_BYTES},
            )
        binary = b"\x00" in data[:_BINARY_SNIFF_BYTES]
        payload: dict[str, Any] = {
            "attachment_id": attachment.attachment_id,
            "filename": attachment.filename,
            "media_type": attachment.media_type,
            "size": attachment.size,
            "encoding": "base64" if binary else "utf-8",
            "revision": revision,
        }
        payload["content"] = (
            base64.b64encode(data).decode("ascii")
            if binary
            else data.decode("utf-8", "replace")
        )
        return payload

    @router.get("/attachments/private/{attachment_id}/download")
    def download_private_attachment(
        attachment_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        revision: Annotated[str | None, Query()] = None,
    ) -> StreamingResponse:
        owner = _owner(ctx, request)
        attachment, path, current = _service(ctx).download_path(owner, attachment_id)
        expected = (revision or "").strip() or None
        if expected is not None and expected != current:
            raise AppError(
                ErrorCode.REVISION_CONFLICT,
                "private attachment changed since the requested revision",
                details={
                    "attachment_id": attachment_id,
                    "expected_revision": expected,
                    "actual_revision": current,
                },
            )

        def stream() -> Any:
            # O_NOFOLLOW closes the tiny check/open race for a swapped symlink.
            fd = os.open(
                str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            with os.fdopen(fd, "rb") as handle:
                while True:
                    chunk = handle.read(_STREAM_CHUNK)
                    if not chunk:
                        break
                    yield chunk

        headers = {
            "Content-Disposition": _content_disposition(attachment.filename),
            "ETag": f'"{current}"',
            "X-LG-Revision": current,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
        return StreamingResponse(
            stream(), media_type=attachment.media_type, headers=headers
        )

    @router.delete("/attachments/private/{attachment_id}", status_code=204)
    def delete_private_attachment(
        attachment_id: str,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> Response:
        owner = _owner(ctx, request)
        _service(ctx).delete(owner, attachment_id)
        return Response(status_code=204)

    return router


__all__ = ["build_attachments_router"]
