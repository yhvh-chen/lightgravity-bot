"""Protected private-attachment file storage (LG-119).

Layout (docs/08 §19.3)::

    <data>/private-attachments/<sha256("lightgravity:private-attachments:v1:" + owner)>/
        <att_<ULID>>/
            ATTACHMENT.json
            content.bin

Only this root knows the raw bytes.  The owner digest is one-way and the API
never returns a path.  Every directory is ``0700`` and every file ``0600``.
Writes are same-directory temp files + ``fsync`` + ``os.replace``; reads use
``O_NOFOLLOW`` and reject anything that is not a regular file below the
resolved owner directory, so a planted symlink cannot escape the private root.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..contracts import AppError, ErrorCode
from ..store.ids import id_matches_kind
from .models import MAX_UPLOAD_BYTES, PrivateAttachment

_ROOT_NAME = "private-attachments"
_OWNER_NAMESPACE = "lightgravity:private-attachments:v1:"
_METADATA_NAME = "ATTACHMENT.json"
_CONTENT_NAME = "content.bin"
_TEMP_PREFIX = ".lgattachment-"


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _ensure_dir(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    # mkdir mode is filtered by umask; force the documented private mode.
    os.chmod(path, mode)


def _within(candidate: str, root: str) -> bool:
    try:
        return os.path.commonpath([candidate, root]) == root
    except ValueError:
        return False


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=_TEMP_PREFIX)
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
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


def _read_regular(path: Path, *, max_bytes: int) -> bytes:
    """Read at most ``max_bytes+1`` from a non-symlink regular file."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "private attachment storage entry is not readable",
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment storage entry is not a regular file",
            )
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


class AttachmentStore:
    """Owner-digest scoped filesystem authority for private attachments."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def owner_digest(owner: str) -> str:
        return hashlib.sha256(
            f"{_OWNER_NAMESPACE}{owner}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def validate_id(attachment_id: str) -> str:
        if not id_matches_kind("att", attachment_id):
            # An invalid id cannot name any stored attachment; do not reveal
            # whether a similarly-spaced path exists.
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            )
        return attachment_id

    def _root_dir(self) -> Path:
        if self._root.is_symlink():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment root may not be a symlink",
            )
        _ensure_dir(self._root)
        return self._root

    def _owner_dir(self, owner: str) -> Path:
        root = self._root_dir()
        owner_dir = root / self.owner_digest(owner)
        if owner_dir.is_symlink():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment owner directory may not be a symlink",
            )
        _ensure_dir(owner_dir)
        self._assert_under(owner_dir, root)
        return owner_dir

    def _existing_owner_dir(self, owner: str) -> Path | None:
        root = self._root_dir()
        owner_dir = root / self.owner_digest(owner)
        if not owner_dir.is_dir() or owner_dir.is_symlink():
            return None
        if not _within(os.path.realpath(owner_dir), os.path.realpath(root)):
            return None
        return owner_dir

    def _attachment_dir(self, owner: str, attachment_id: str) -> Path:
        self.validate_id(attachment_id)
        owner_dir = self._owner_dir(owner)
        target = owner_dir / attachment_id
        if target.is_symlink():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment directory may not be a symlink",
            )
        _ensure_dir(target)
        self._assert_under(target, owner_dir)
        return target

    def _existing_attachment_dir(
        self, owner: str, attachment_id: str
    ) -> Path | None:
        self.validate_id(attachment_id)
        owner_dir = self._existing_owner_dir(owner)
        if owner_dir is None:
            return None
        target = owner_dir / attachment_id
        if target.is_symlink() or not target.is_dir():
            return None
        real_owner = os.path.realpath(owner_dir)
        if not _within(os.path.realpath(target), real_owner):
            return None
        return target

    @staticmethod
    def _assert_under(path: Path, root: Path) -> None:
        real_root = os.path.realpath(root)
        real_path = os.path.realpath(path)
        if not _within(real_path, real_root):
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment path escapes the protected root",
            )

    def load_metadata(self, owner: str, attachment_id: str) -> PrivateAttachment | None:
        target = self._existing_attachment_dir(owner, attachment_id)
        if target is None:
            return None
        metadata_path = target / _METADATA_NAME
        if metadata_path.is_symlink() or not metadata_path.is_file():
            return None
        try:
            raw = _read_regular(metadata_path, max_bytes=64 * 1024)
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            attachment = PrivateAttachment(
                attachment_id=str(payload["attachment_id"]),
                filename=str(payload["filename"]),
                media_type=str(payload["media_type"]),
                size=int(payload["size"]),
                sha256=str(payload["sha256"]),
                status=str(payload["status"]),
                created_at=str(payload["created_at"]),
                message_id=(
                    str(payload["message_id"])
                    if payload.get("message_id") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if attachment.attachment_id != attachment_id:
            return None
        if attachment.status not in {"stored", "attached"}:
            return None
        return attachment

    def read_content(
        self, owner: str, attachment_id: str, *, max_bytes: int = MAX_UPLOAD_BYTES
    ) -> tuple[PrivateAttachment, bytes]:
        attachment = self.load_metadata(owner, attachment_id)
        if attachment is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            )
        target = self._existing_attachment_dir(owner, attachment_id)
        if target is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            )
        content_path = target / _CONTENT_NAME
        if content_path.is_symlink():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment content may not be a symlink",
            )
        try:
            data = _read_regular(content_path, max_bytes=max_bytes)
        except FileNotFoundError:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            ) from None
        if len(data) > max_bytes:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment exceeds the read size limit",
                details={"attachment_id": attachment_id, "max_bytes": max_bytes},
            )
        if len(data) != attachment.size or hashlib.sha256(data).hexdigest() != attachment.sha256:
            # Corrupt/tampered storage is not served as if it were the record.
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment content is unavailable",
                details={"attachment_id": attachment_id},
            )
        return attachment, data

    def write(
        self,
        owner: str,
        attachment_id: str,
        *,
        filename: str,
        media_type: str,
        data: bytes,
    ) -> PrivateAttachment:
        target = self._attachment_dir(owner, attachment_id)
        digest = hashlib.sha256(data).hexdigest()
        content_path = target / _CONTENT_NAME
        metadata_path = target / _METADATA_NAME
        for path in (content_path, metadata_path):
            if path.is_symlink():
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "private attachment storage entry may not be a symlink",
                )
        _atomic_write(content_path, data)
        attachment = PrivateAttachment(
            attachment_id=attachment_id,
            filename=filename,
            media_type=media_type,
            size=len(data),
            sha256=digest,
            status="stored",
            created_at=_now_iso(),
        )
        _atomic_write(
            metadata_path,
            json.dumps(attachment.to_dict(), ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            ),
        )
        return attachment

    def update_status(
        self,
        owner: str,
        attachment: PrivateAttachment,
        *,
        status: str,
        message_id: str | None,
    ) -> PrivateAttachment:
        target = self._existing_attachment_dir(owner, attachment.attachment_id)
        if target is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment.attachment_id},
            )
        updated = PrivateAttachment(
            attachment_id=attachment.attachment_id,
            filename=attachment.filename,
            media_type=attachment.media_type,
            size=attachment.size,
            sha256=attachment.sha256,
            status=status,
            created_at=attachment.created_at,
            message_id=message_id,
        )
        metadata_path = target / _METADATA_NAME
        if metadata_path.is_symlink():
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "private attachment metadata may not be a symlink",
            )
        _atomic_write(
            metadata_path,
            json.dumps(updated.to_dict(), ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            ),
        )
        return updated

    def delete(self, owner: str, attachment: PrivateAttachment) -> None:
        target = self._existing_attachment_dir(owner, attachment.attachment_id)
        if target is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment.attachment_id},
            )
        for name in (_METADATA_NAME, _CONTENT_NAME):
            path = target / name
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
        try:
            target.rmdir()
        except OSError:
            # An unexpected extra entry is not silently deleted; the attachment
            # remains unavailable for deletion rather than half-removed.
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "private attachment directory is not empty",
                details={"attachment_id": attachment.attachment_id},
            ) from None

    def revision(self, owner: str, attachment_id: str) -> str:
        target = self._existing_attachment_dir(owner, attachment_id)
        if target is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            )
        info = (target / _CONTENT_NAME).stat()
        return f"{info.st_size}-{info.st_mtime_ns}"

    def content_path(self, owner: str, attachment_id: str) -> Path:
        target = self._existing_attachment_dir(owner, attachment_id)
        if target is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            )
        path = target / _CONTENT_NAME
        if path.is_symlink() or not path.is_file():
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            )
        return path


__all__ = ["AttachmentStore"]
