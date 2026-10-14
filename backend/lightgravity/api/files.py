"""Root-restricted Files endpoints (LG-012 reads + LG-014 upload/download, docs/08 §4.3/§10).

Read side (LG-012, unchanged semantics): ``GET /files`` lists one directory and
``GET /files/content`` returns a file's bytes as text or base64.  Both resolve
through the Store's ``resolve_path`` choke point, so lexical ``..`` escapes and
symlinks whose realpath leaves ``LIGHTGRAVITY_WORKSPACE_ROOT`` are rejected with
the frozen ``path_outside_workspace`` code.

LG-014 additions (registered as *planned* in docs/08 v1.3.0 and implemented
here):

* ``POST /files/upload`` — bounded binary body with ``path`` and
  ``expected_revision``.  It is a **protected write**: it re-runs the injected
  API ``AccessPolicy`` as a sensitive request, so an unusable token is an honest
  ``unauthorized`` instead of an open write.  Writes are atomic (same-directory
  temp + ``fsync`` + ``os.replace``) under a per-target ``flock``; a stale
  ``expected_revision`` (including ``null`` meaning "must not exist") is a
  ``revision_conflict`` that never overwrites the newer bytes.  Symlink/lexical
  escapes and paths resolving inside the secret store are refused.
* ``GET /files/download`` — bounded download of the same content the preview
  reads.  The response carries the stat-based file ``revision`` and an optional
  ``revision`` query re-checks it, so preview and download stay on one version
  and an external edit is reported instead of silently downloaded.
* ``GET /tasks/{task_id}/artifacts`` — task-scoped inputs/candidates/deliverables/
  evidence association from the Task ``workspace_ref`` plus the acceptance
  binding fields.  No workspace or no files yields an honest empty result with a
  note, never fabricated data.  Canonical evidence artifacts (which live in the
  Store-owned Task/Run evidence root, *not* under the workspace root) are listed
  independently with their own authorized ref.
* ``GET /tasks/{task_id}/artifacts/content`` and
  ``GET /tasks/{task_id}/artifacts/download`` — preview/download of one canonical
  evidence artifact.  They accept only ``evidence:<run_id>/<name>@sha256:<hex>``
  and resolve it through the Task/Run evidence resolver, so a raw absolute path,
  another Task's artifact or a digest mismatch is refused; preview and download
  share one stat-based ``revision``.

Files/preview is read-only: no execution, no MCP, no Trigger.  HTML/scripts are
never rendered, only offered for download.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from ..contracts import AppError, ErrorCode
from ..evidence import (
    EvidenceRefError,
    canonical_evidence_ref,
    evidence_root,
    parse_evidence_ref,
    resolve_evidence_ref,
)
from ..store import EntityNotFound
from ..store.atomic import TEMP_PREFIX
from ..store.locking import LockManager
from .context import ApiContext, get_context

#: Hard cap for inline content; larger files are truncated, never loaded whole.
MAX_CONTENT_BYTES = 5_000_000
#: Hard cap for one upload body.  Larger requests are rejected before persisting.
MAX_UPLOAD_BYTES = 10_000_000
#: Hard cap for one download.  Larger files are refused rather than streamed.
MAX_DOWNLOAD_BYTES = 50_000_000
_BINARY_SNIFF_BYTES = 1024
_STREAM_CHUNK = 256 * 1024
_ARTIFACT_SCAN_LIMIT = 2000
#: Evidence run-directory names are single, separator-free components.
_SAFE_RUN_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

#: Top-level task-directory convention (docs/01 §9, docs/02 §4) -> category.
_ARTIFACT_CATEGORIES: dict[str, str] = {
    "inputs": "inputs",
    "artifacts": "candidates",
    "deliverables": "deliverables",
    "runs": "evidence",
}


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


def _revision(path: Path) -> str | None:
    """Stat-based revision: size + mtime_ns, ``None`` when the file is absent.

    Cheap enough to compute for every listing entry and consistent between the
    content preview and the download response.  It is a change detector, not a
    cryptographic digest; docs/08 registers the field, not the algorithm.
    """

    try:
        info = path.stat()
    except OSError:
        return None
    return f"{info.st_size}-{info.st_mtime_ns}"


def _describe(child: str, root_real: str) -> dict[str, Any] | None:
    real = os.path.realpath(child)
    if not _within(real, root_real):
        return None  # escaping symlink: never surfaced through the API
    try:
        info = os.stat(child)
    except OSError:
        return None
    is_symlink = os.path.islink(child)
    is_dir = os.path.isdir(child)
    media_type = None
    revision = None
    if not is_dir:
        media_type = mimetypes.guess_type(child)[0] or "application/octet-stream"
        revision = f"{info.st_size}-{info.st_mtime_ns}"
    return {
        "name": os.path.basename(child),
        "path": _relative(child, root_real),
        "type": "directory" if is_dir else "file",
        "size": None if is_dir else info.st_size,
        "modified_at": _iso(info.st_mtime),
        "symlink": is_symlink,
        "media_type": media_type,
        "revision": revision,
    }


def _reject_secret(ctx: ApiContext, target: Path, original: str) -> None:
    """Refuse any read/write whose resolved path is inside the secret store."""

    secret_root = os.path.realpath(str(ctx.secret_store.directory))
    resolved = os.path.realpath(str(target))
    if _within(resolved, secret_root):
        raise AppError(
            ErrorCode.PATH_OUTSIDE_WORKSPACE,
            "path resolves inside the secret store",
            details={"path": original, "secret_store": secret_root},
        )


def _content_disposition(filename: str) -> str:
    from urllib.parse import quote

    fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=TEMP_PREFIX)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


async def _read_bounded(request: Request, limit: int) -> tuple[bytes, bool]:
    """Collect the request body, aborting as soon as it exceeds ``limit``."""

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            return b"", True
        chunks.append(chunk)
    return b"".join(chunks), False


def _normalize_revision(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _classify(relative: str) -> str:
    head = relative.split("/", 1)[0].lower() if relative else ""
    return _ARTIFACT_CATEGORIES.get(head, "other")


def _scan_artifacts(root: Path, root_real: str) -> dict[str, list[dict[str, Any]]]:
    categories: dict[str, list[dict[str, Any]]] = {
        "inputs": [],
        "candidates": [],
        "deliverables": [],
        "evidence": [],
        "other": [],
    }
    scanned = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        files.sort()
        for name in files:
            if scanned >= _ARTIFACT_SCAN_LIMIT:
                return categories
            child = os.path.join(current, name)
            described = _describe(child, root_real)
            if described is None or described["type"] != "file":
                continue
            scanned += 1
            categories[_classify(str(described["path"]))].append(described)
    return categories


def _scan_evidence_root(
    data_dir: Path, task_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    """List canonical evidence artifacts under the Task's evidence root.

    Only the Store-owned evidence root is read, never the raw data directory, so
    this cannot become a general filesystem listing.  Each entry carries its own
    canonical ``evidence:<run_id>/<name>@sha256:<hex>`` ref (the digest is the
    recorded content hash) so the preview/download endpoints can re-authorize it.
    """

    root = evidence_root(data_dir, task_id)
    if not root.is_dir():
        return []
    root_real = os.path.realpath(str(root))
    items: list[dict[str, Any]] = []
    for run_dir in sorted(root.iterdir()):
        if run_id is not None and run_dir.name != run_id:
            continue
        if not run_dir.is_dir() or not _SAFE_RUN_NAME.match(run_dir.name):
            continue
        for child in sorted(run_dir.iterdir()):
            if len(items) >= _ARTIFACT_SCAN_LIMIT:
                return items
            described = _describe(str(child), root_real)
            if described is None or described["type"] != "file":
                continue
            digest = _sha256_of(child)
            described["run_id"] = run_dir.name
            described["artifact_name"] = child.name
            described["evidence_ref"] = canonical_evidence_ref(
                run_dir.name, child.name, digest
            )
            items.append(described)
    return items


def _sha256_of(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:  # pragma: no cover - unreadable file
        return None


def _resolve_task_evidence(
    ctx: ApiContext, task_id: str, ref: str
) -> tuple[Path, str, str]:
    """Authorize a canonical evidence ref for a specific Task.

    The ref pins the owning Run and (when present) the content digest; the
    resolver enforces Task ownership of the evidence root and rejects any ref
    that is not an ``evidence:`` reference, so a raw absolute path or a ref from
    another Task cannot be read through this endpoint.
    """

    try:
        parsed = parse_evidence_ref(ref)
    except EvidenceRefError as exc:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "evidence reference is malformed",
            details={"evidence_ref": ref, "detail": str(exc)},
        ) from None
    if parsed is None:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "only canonical 'evidence:<run_id>/<name>@sha256:<hex>' references "
            "can be resolved here; raw paths are not accepted",
            details={"evidence_ref": ref},
        )
    try:
        target = resolve_evidence_ref(
            ref, data_dir=ctx.data_dir, task_id=task_id, run_id=parsed.run_id
        )
    except EvidenceRefError as exc:
        raise AppError(
            ErrorCode.NOT_FOUND,
            "evidence reference is not readable for this task/run",
            details={"evidence_ref": ref, "detail": str(exc)},
        ) from None
    return target, parsed.run_id, parsed.name


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
        _reject_secret(ctx, target, path)
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
        _reject_secret(ctx, target, path)
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
            "revision": _revision(target),
        }
        if binary:
            payload["content"] = base64.b64encode(data).decode("ascii")
        else:
            payload["content"] = data.decode("utf-8", "replace")
        return payload

    @router.get("/files/download")
    def download_file(
        ctx: Annotated[ApiContext, Depends(get_context)],
        path: Annotated[str, Query()],
        revision: Annotated[str | None, Query()] = None,
    ) -> StreamingResponse:
        target = ctx.store.resolve_path(path, write=False)
        _reject_secret(ctx, target, path)
        if not target.is_file():
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"file {path!r} does not exist",
                details={"path": path},
            )
        info = target.stat()
        if info.st_size > MAX_DOWNLOAD_BYTES:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "file exceeds the download size limit",
                details={"path": path, "max_bytes": MAX_DOWNLOAD_BYTES},
            )
        current = _revision(target)
        expected = _normalize_revision(revision)
        if expected is not None and expected != current:
            raise AppError(
                ErrorCode.REVISION_CONFLICT,
                "file changed since the requested revision",
                details={
                    "path": path,
                    "expected_revision": expected,
                    "actual_revision": current,
                },
            )
        media_type = (
            mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        )

        def stream() -> Any:
            with target.open("rb") as handle:
                while True:
                    chunk = handle.read(_STREAM_CHUNK)
                    if not chunk:
                        break
                    yield chunk

        headers = {
            "Content-Disposition": _content_disposition(target.name),
            "ETag": f'"{current}"',
            "X-LG-Revision": current or "",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
        return StreamingResponse(stream(), media_type=media_type, headers=headers)

    @router.post("/files/upload")
    async def upload_file(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        response: Response,
        path: Annotated[str, Query()],
        expected_revision: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        # Protected write: the global middleware only marks /settings as
        # sensitive, so re-apply the injected policy here.  With no token
        # configured the default is deny (unauthorized), never an open write.
        ctx.access.authorize(request, sensitive=True)

        target = ctx.store.resolve_path(path, write=True)
        _reject_secret(ctx, target, path)
        if not path.strip() or target.is_dir():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "upload path must name a file",
                details={"path": path},
            )

        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                length = int(declared)
            except ValueError as exc:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "invalid Content-Length header",
                    details={"path": path},
                ) from exc
            if length < 0 or length > MAX_UPLOAD_BYTES:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "upload exceeds the maximum body size",
                    details={"path": path, "max_bytes": MAX_UPLOAD_BYTES},
                )

        parent = target.parent
        if not parent.is_dir():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "parent directory does not exist",
                details={"path": path},
            )

        expected = _normalize_revision(expected_revision)
        locks = LockManager(ctx.data_dir / "locks")
        with locks.acquire(f"file-upload:{target}"):
            current = _revision(target)
            if expected is None:
                if current is not None:
                    raise AppError(
                        ErrorCode.REVISION_CONFLICT,
                        "file already exists; expected_revision is required to overwrite",
                        details={
                            "path": path,
                            "expected_revision": None,
                            "actual_revision": current,
                        },
                    )
            elif current is None:
                raise AppError(
                    ErrorCode.REVISION_CONFLICT,
                    "file does not exist",
                    details={
                        "path": path,
                        "expected_revision": expected,
                        "actual_revision": None,
                    },
                )
            elif current != expected:
                raise AppError(
                    ErrorCode.REVISION_CONFLICT,
                    "file changed since the requested revision",
                    details={
                        "path": path,
                        "expected_revision": expected,
                        "actual_revision": current,
                    },
                )

            data, too_large = await _read_bounded(request, MAX_UPLOAD_BYTES)
            if too_large:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "upload exceeds the maximum body size",
                    details={"path": path, "max_bytes": MAX_UPLOAD_BYTES},
                )

            # Re-check immediately before replacement: an out-of-band edit that
            # landed while the body streamed must not be silently overwritten.
            latest = _revision(target)
            if latest != current:
                raise AppError(
                    ErrorCode.REVISION_CONFLICT,
                    "file changed while the upload was being read",
                    details={
                        "path": path,
                        "expected_revision": expected,
                        "actual_revision": latest,
                    },
                )

            _atomic_write_bytes(target, data)
            new_revision = _revision(target)

        created = current is None
        response.status_code = 201 if created else 200
        response.headers["ETag"] = f'"{new_revision}"'
        return {
            "path": _relative(target, os.path.realpath(str(ctx.workspace_root))),
            "name": target.name,
            "size": len(data),
            "revision": new_revision,
            "created": created,
        }

    @router.get("/tasks/{task_id}/artifacts")
    def task_artifacts(
        ctx: Annotated[ApiContext, Depends(get_context)],
        task_id: str,
    ) -> dict[str, Any]:
        try:
            versioned = ctx.store.read("task", task_id)
        except EntityNotFound:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"task {task_id!r} not found",
                details={"task_id": task_id},
            ) from None
        entity = versioned.entity
        acceptance = entity.get("acceptance")
        acceptance = acceptance if isinstance(acceptance, dict) else {}
        result: dict[str, Any] = {
            "task_id": task_id,
            "task_revision": versioned.revision,
            "requirements_revision": entity.get("requirements_revision"),
            "deliverable_revision": entity.get("deliverable_revision"),
            "candidate_ref": acceptance.get("candidate_ref"),
            "evidence_refs": list(acceptance.get("evidence_refs") or []),
            "check_records": list(acceptance.get("check_records") or []),
            "workspace_ref": entity.get("workspace_ref"),
            "categories": {
                "inputs": [],
                "candidates": [],
                "deliverables": [],
                "evidence": [],
                "other": [],
            },
            "note": None,
            "evidence": [],
        }
        # Canonical evidence artifacts live in the Store-owned Task/Run evidence
        # root, which is *not* under the workspace root, so they are listed
        # independently of ``workspace_ref`` and carry their own authorized ref.
        evidence_entries: list[dict[str, Any]] = []
        for entry in _scan_evidence_root(ctx.data_dir, task_id):
            evidence_entries.append(entry)
        result["evidence"] = evidence_entries
        result["categories"]["evidence"] = list(evidence_entries)
        workspace_ref = entity.get("workspace_ref")
        if not isinstance(workspace_ref, str) or not workspace_ref.strip():
            result["note"] = (
                "Task has no workspace_ref; no workspace files to associate."
                if not result["evidence"]
                else "Task has no workspace_ref; only canonical evidence artifacts are listed."
            )
            return result
        try:
            root = ctx.store.resolve_path(workspace_ref, write=False)
        except AppError as exc:
            result["note"] = f"Task workspace_ref is not accessible ({exc.code.value})."
            return result
        if not root.is_dir():
            result["note"] = "Task workspace_ref directory does not exist."
            return result
        root_real = os.path.realpath(str(root))
        result["categories"] = _scan_artifacts(root, root_real)
        # Keep both: workspace-classified evidence files plus canonical evidence-root refs.
        result["categories"]["evidence"] = [
            *result["categories"]["evidence"],
            *evidence_entries,
        ]
        return result

    @router.get("/tasks/{task_id}/artifacts/content")
    def task_artifact_content(
        ctx: Annotated[ApiContext, Depends(get_context)],
        task_id: str,
        evidence_ref: Annotated[str, Query()],
    ) -> dict[str, Any]:
        """Preview a canonical evidence artifact for its owning Task.

        The reference must be ``evidence:<run_id>/<name>@sha256:<hex>``; it is
        resolved through the Task/Run evidence resolver, so a raw absolute path,
        another Task's artifact or a digest mismatch is refused rather than read.
        """

        target, run_id, name = _resolve_task_evidence(ctx, task_id, evidence_ref)
        size = target.stat().st_size
        with target.open("rb") as handle:
            data = handle.read(MAX_CONTENT_BYTES)
        truncated = size > MAX_CONTENT_BYTES
        binary = b"\x00" in data[:_BINARY_SNIFF_BYTES]
        media_type = mimetypes.guess_type(name)[0] or (
            "application/octet-stream" if binary else "text/plain"
        )
        payload: dict[str, Any] = {
            "task_id": task_id,
            "run_id": run_id,
            "name": name,
            "evidence_ref": evidence_ref,
            "size": size,
            "truncated": truncated,
            "media_type": media_type,
            "encoding": "base64" if binary else "utf-8",
            "revision": _revision(target),
        }
        if binary:
            payload["content"] = base64.b64encode(data).decode("ascii")
        else:
            payload["content"] = data.decode("utf-8", "replace")
        return payload

    @router.get("/tasks/{task_id}/artifacts/download")
    def task_artifact_download(
        ctx: Annotated[ApiContext, Depends(get_context)],
        task_id: str,
        evidence_ref: Annotated[str, Query()],
        revision: Annotated[str | None, Query()] = None,
    ) -> StreamingResponse:
        """Download the same evidence bytes that the preview reads."""

        target, _run_id, _name = _resolve_task_evidence(ctx, task_id, evidence_ref)
        info = target.stat()
        if info.st_size > MAX_DOWNLOAD_BYTES:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "artifact exceeds the download size limit",
                details={"evidence_ref": evidence_ref, "max_bytes": MAX_DOWNLOAD_BYTES},
            )
        current = _revision(target)
        expected = _normalize_revision(revision)
        if expected is not None and expected != current:
            raise AppError(
                ErrorCode.REVISION_CONFLICT,
                "artifact changed since the requested revision",
                details={
                    "evidence_ref": evidence_ref,
                    "expected_revision": expected,
                    "actual_revision": current,
                },
            )
        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"

        def stream() -> Any:
            with target.open("rb") as handle:
                while True:
                    chunk = handle.read(_STREAM_CHUNK)
                    if not chunk:
                        break
                    yield chunk

        headers = {
            "Content-Disposition": _content_disposition(target.name),
            "ETag": f'"{current}"',
            "X-LG-Revision": current or "",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
        return StreamingResponse(stream(), media_type=media_type, headers=headers)

    return router


__all__ = [
    "build_files_router",
    "MAX_CONTENT_BYTES",
    "MAX_UPLOAD_BYTES",
    "MAX_DOWNLOAD_BYTES",
]
