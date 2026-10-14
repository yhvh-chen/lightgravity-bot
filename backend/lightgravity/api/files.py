"""Read-only, root-restricted Files endpoints (LG-012, docs/08 §4.3/§10).

``GET /files`` lists one directory and ``GET /files/content`` returns a file's
bytes as text or base64.  Both resolve through the Store's
``resolve_path`` choke point, so lexical ``..`` escapes and symlinks whose
realpath leaves ``LIGHTGRAVITY_WORKSPACE_ROOT`` are rejected with the frozen
``path_outside_workspace`` code.  Listing also
re-checks every child realpath.  Files/preview is read-only: no execution,
no MCP, no Trigger.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ..contracts import AppError, ErrorCode
from .context import ApiContext, get_context

#: Hard cap for inline content; larger files are truncated, never loaded whole.
MAX_CONTENT_BYTES = 5_000_000
_BINARY_SNIFF_BYTES = 1024


def _relative(path: os.PathLike[str] | str, root: os.PathLike[str] | str) -> str | None:
    try:
        return os.path.relpath(os.fspath(path), os.fspath(root)).replace(os.sep, "/")
    except ValueError:
        return None


def _within(candidate: str, root_real: str) -> bool:
    try:
        return os.path.commonpath([candidate, root_real]) == root_real
    except ValueError:
        return False


def _iso(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _describe(child: str, root_real: str) -> dict[str, Any] | None:
    real = os.path.realpath(child)
    if not _within(real, root_real):
        return None  # escaping symlink: never surfaced through the API
    try:
        info = os.lstat(child)
    except OSError:
        return None
    is_symlink = os.path.islink(child)
    is_dir = os.path.isdir(child)
    media_type = None
    if not is_dir:
        media_type = mimetypes.guess_type(child)[0] or "application/octet-stream"
    return {
        "name": os.path.basename(child),
        "path": _relative(child, root_real),
        "type": "directory" if is_dir else "file",
        "size": None if is_dir else info.st_size,
        "modified_at": _iso(info.st_mtime),
        "symlink": is_symlink,
        "media_type": media_type,
    }


def build_files_router() -> APIRouter:
    router = APIRouter(tags=["files"])

    @router.get("/files")
    def list_files(
        ctx: Annotated[ApiContext, Depends(get_context)],
        path: Annotated[str, Query()] = "",
        limit: Annotated[int, Query(ge=1, le=2000)] = 500,
        cursor: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        target = ctx.store.resolve_path(path, write=False)
        if not target.is_dir():
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"directory {path!r} does not exist",
                details={"path": path},
            )
        root_real = os.path.realpath(str(ctx.workspace_root))
        children = sorted(os.fspath(child) for child in target.iterdir())
        if cursor:
            children = [child for child in children if os.path.basename(child) > cursor]
        page = children[:limit]
        items = [
            described
            for child in page
            if (described := _describe(child, root_real)) is not None
        ]
        next_cursor = (
            os.path.basename(page[-1]) if len(children) > limit and page else None
        )
        return {
            "path": _relative(target, root_real) or "",
            "items": items,
            "next_cursor": next_cursor,
        }

    @router.get("/files/content")
    def file_content(
        ctx: Annotated[ApiContext, Depends(get_context)],
        path: Annotated[str, Query()],
    ) -> dict[str, Any]:
        target = ctx.store.resolve_path(path, write=False)
        if not target.is_file():
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"file {path!r} does not exist",
                details={"path": path},
            )
        size = target.stat().st_size
        with target.open("rb") as handle:
            data = handle.read(MAX_CONTENT_BYTES)
        truncated = size > MAX_CONTENT_BYTES
        binary = b"\x00" in data[:_BINARY_SNIFF_BYTES]
        media_type = mimetypes.guess_type(str(target))[0] or (
            "application/octet-stream" if binary else "text/plain"
        )
        payload: dict[str, Any] = {
            "path": path,
            "name": target.name,
            "size": size,
            "truncated": truncated,
            "media_type": media_type,
            "encoding": "base64" if binary else "utf-8",
        }
        if binary:
            payload["content"] = base64.b64encode(data).decode("ascii")
        else:
            payload["content"] = data.decode("utf-8", "replace")
        return payload

    return router


__all__ = ["build_files_router", "MAX_CONTENT_BYTES"]
