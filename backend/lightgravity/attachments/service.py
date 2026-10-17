"""Private Personal attachment service (LG-119, docs/08 §19.3 R2).

Responsibilities:

* identity-scoped upload/metadata/content/download/delete under the protected
  private root;
* idempotent upload keyed by ``att_<ULID>`` and content hash;
* stored -> attached transitions for one Personal message;
* a bounded, owner-checking local text resolver used by the actual Personal
  responder.  It never calls OCR/ASR/embedding/network and never writes a
  shared source/index.

The API layer derives ``owner`` from the server session.  No method here
accepts an owner from a request body, and every path re-validates the owner
directory before reading a byte.  Cross-owner and unknown ids are reported as
``404 not_found`` (no existence leak).
"""

from __future__ import annotations

import hashlib
import os
from contextlib import ExitStack
from pathlib import Path

from ..contracts import AppError, ErrorCode
from ..store.locking import LockManager
from .models import (
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_FILE_BYTES,
    MAX_UPLOAD_BYTES,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_MEDIA_TYPES,
    AttachmentLimits,
    ModelAttachmentContext,
    PrivateAttachment,
)
from .store import AttachmentStore

_REASON_LABEL = {
    "unsupported_type": "unsupported type",
    "binary_unsupported": "binary or non-UTF-8",
    "too_large": "larger than the 64 KiB text bound",
    "unavailable": "unavailable",
    "truncated": "context limit reached",
}


def _normalize_filename(filename: str | None) -> str:
    if not isinstance(filename, str):
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "filename is required",
            details={"field": "filename"},
        )
    name = os.path.basename(filename.replace("\\", "/")).strip()
    name = "".join(ch for ch in name if ch == "\t" or ord(ch) >= 32)
    if not name:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "filename must name a file",
            details={"field": "filename"},
        )
    if len(name) > 255:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "filename is too long",
            details={"field": "filename", "max_length": 255},
        )
    return name


def _normalize_media_type(media_type: str | None) -> str:
    value = (media_type or "").strip()
    if not value:
        return "application/octet-stream"
    if "\r" in value or "\n" in value or len(value) > 127:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "media_type is not valid",
            details={"field": "media_type"},
        )
    return value


def _base_media_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _supported(attachment: PrivateAttachment) -> bool:
    if _base_media_type(attachment.media_type) in SUPPORTED_MEDIA_TYPES:
        return True
    suffix = Path(attachment.filename).suffix.lower()
    return suffix in SUPPORTED_EXTENSIONS


def _note_for(
    attachments: list[PrivateAttachment],
    statuses: dict[str, str],
    *,
    truncated: bool,
) -> str | None:
    excluded = [
        attachment
        for attachment in attachments
        if statuses.get(attachment.attachment_id)
        not in {"included", "truncated"}
    ]
    parts: list[str] = []
    if truncated:
        parts.append(
            "Attachment context was truncated to the bounded chat limit; "
            "later content was not sent to the model."
        )
    if excluded:
        listed = "; ".join(
            f"{attachment.filename} ({_REASON_LABEL.get(statuses.get(attachment.attachment_id, 'unavailable'), 'unavailable')})"
            for attachment in excluded
        )
        parts.append(f"Not read by the model: {listed}.")
    return " ".join(parts) if parts else None


class PrivateAttachmentService:
    """Owner-checking operations over :class:`AttachmentStore`."""

    def __init__(self, store: AttachmentStore, data_dir: Path) -> None:
        self._store = store
        self._locks = LockManager(Path(data_dir) / "locks")

    @property
    def store(self) -> AttachmentStore:
        return self._store

    def _lock_key(self, owner: str, attachment_id: str) -> str:
        return (
            "private-attachment:"
            f"{AttachmentStore.owner_digest(owner)}:{attachment_id}"
        )

    def upload(
        self,
        owner: str,
        attachment_id: str,
        *,
        filename: str | None,
        media_type: str | None,
        data: bytes,
    ) -> tuple[PrivateAttachment, bool]:
        """Store bytes idempotently for one owner; return ``(attachment, created)``."""

        AttachmentStore.validate_id(attachment_id)
        clean_name = _normalize_filename(filename)
        clean_media = _normalize_media_type(media_type)
        if len(data) > MAX_UPLOAD_BYTES:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "upload exceeds the maximum private attachment size",
                details={"max_bytes": MAX_UPLOAD_BYTES},
            )
        digest = hashlib.sha256(data).hexdigest()
        with self._locks.acquire(self._lock_key(owner, attachment_id)):
            existing = self._store.load_metadata(owner, attachment_id)
            if existing is not None:
                if existing.sha256 == digest and existing.size == len(data):
                    return existing, False
                raise AppError(
                    ErrorCode.REVISION_CONFLICT,
                    "attachment_id already exists with different bytes",
                    details={
                        "attachment_id": attachment_id,
                        "existing_sha256": existing.sha256,
                        "uploaded_sha256": digest,
                    },
                )
            created = self._store.write(
                owner,
                attachment_id,
                filename=clean_name,
                media_type=clean_media,
                data=data,
            )
            return created, True

    def get(self, owner: str, attachment_id: str) -> PrivateAttachment:
        attachment = self._store.load_metadata(owner, attachment_id)
        if attachment is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "private attachment not found",
                details={"attachment_id": attachment_id},
            )
        return attachment

    def content(
        self, owner: str, attachment_id: str
    ) -> tuple[PrivateAttachment, bytes, str]:
        attachment, data = self._store.read_content(owner, attachment_id)
        return (
            attachment,
            data,
            self._store.revision(owner, attachment_id),
        )

    def download_path(self, owner: str, attachment_id: str) -> tuple[PrivateAttachment, Path, str]:
        attachment = self.get(owner, attachment_id)
        path = self._store.content_path(owner, attachment_id)
        return attachment, path, self._store.revision(owner, attachment_id)

    def delete(self, owner: str, attachment_id: str) -> None:
        with self._locks.acquire(self._lock_key(owner, attachment_id)):
            attachment = self.get(owner, attachment_id)
            if attachment.status != "stored":
                raise AppError(
                    ErrorCode.ILLEGAL_TRANSITION,
                    "an attachment already used by a Personal message cannot be deleted",
                    details={
                        "attachment_id": attachment_id,
                        "status": attachment.status,
                    },
                )
            self._store.delete(owner, attachment)

    def claim_for_message(
        self, owner: str, attachment_ids: list[str], message_id: str
    ) -> list[PrivateAttachment]:
        """Atomically transition stored attachments to attached for a message."""

        ids = list(dict.fromkeys(attachment_ids))
        with ExitStack() as stack:
            for attachment_id in sorted(ids):
                stack.enter_context(self._locks.acquire(self._lock_key(owner, attachment_id)))
            claimed: list[PrivateAttachment] = []
            newly_attached: list[PrivateAttachment] = []
            try:
                for attachment_id in ids:
                    attachment = self.get(owner, attachment_id)
                    if attachment.status == "attached":
                        if attachment.message_id == message_id:
                            claimed.append(attachment)
                            continue
                        raise AppError(
                            ErrorCode.NOT_FOUND,
                            "private attachment not found",
                            details={"attachment_id": attachment_id},
                        )
                    if attachment.status != "stored":
                        raise AppError(
                            ErrorCode.NOT_FOUND,
                            "private attachment not found",
                            details={"attachment_id": attachment_id},
                        )
                    updated = self._store.update_status(
                        owner,
                        attachment,
                        status="attached",
                        message_id=message_id,
                    )
                    claimed.append(updated)
                    newly_attached.append(updated)
            except BaseException:
                for attachment in newly_attached:
                    self._store.update_status(
                        owner,
                        attachment,
                        status="stored",
                        message_id=None,
                    )
                raise
            return claimed

    def release_claims(
        self, owner: str, attachment_ids: list[str], message_id: str
    ) -> None:
        """Revert attached state when the Personal message was not persisted."""

        for attachment_id in dict.fromkeys(attachment_ids):
            with self._locks.acquire(self._lock_key(owner, attachment_id)):
                attachment = self._store.load_metadata(owner, attachment_id)
                if (
                    attachment is not None
                    and attachment.status == "attached"
                    and attachment.message_id == message_id
                ):
                    self._store.update_status(
                        owner,
                        attachment,
                        status="stored",
                        message_id=None,
                    )

    def resolve_text_for_model(
        self,
        owner: str,
        attachment_ids: list[str],
        limits: AttachmentLimits | None = None,
        *,
        message_id: str | None = None,
    ) -> ModelAttachmentContext:
        """Read bounded local text for the current owner only.

        Owner validation is repeated for every id.  If a referenced attachment
        is unknown, belongs to someone else, or is attached to a different
        message, this raises ``404 not_found`` before any responder call.
        Binary/unsupported/oversize files are excluded with an honest status,
        never presented as text the model read.
        """

        effective = limits or AttachmentLimits()
        ids = list(dict.fromkeys(attachment_ids))
        if len(ids) > effective.max_attachments:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                f"at most {effective.max_attachments} private attachments are allowed per message",
                details={
                    "field": "attachments",
                    "max_attachments": effective.max_attachments,
                },
            )
        attachments: list[PrivateAttachment] = []
        statuses: dict[str, str] = {}
        chars: dict[str, int] = {}
        filenames: dict[str, str] = {}
        chunks: list[str] = []
        total = 0
        truncated = False

        for attachment_id in ids:
            attachment = self._store.load_metadata(owner, attachment_id)
            if attachment is None:
                raise AppError(
                    ErrorCode.NOT_FOUND,
                    "private attachment not found",
                    details={"attachment_id": attachment_id},
                )
            if attachment.status == "attached":
                if message_id is None or attachment.message_id != message_id:
                    raise AppError(
                        ErrorCode.NOT_FOUND,
                        "private attachment not found",
                        details={"attachment_id": attachment_id},
                    )
            elif attachment.status != "stored":
                raise AppError(
                    ErrorCode.NOT_FOUND,
                    "private attachment not found",
                    details={"attachment_id": attachment_id},
                )
            attachments.append(attachment)
            filenames[attachment_id] = attachment.filename
            if not _supported(attachment):
                statuses[attachment_id] = "unsupported_type"
                chars[attachment_id] = 0
                continue
            if attachment.size > effective.max_file_bytes:
                statuses[attachment_id] = "too_large"
                chars[attachment_id] = 0
                continue
            try:
                _record, data = self._store.read_content(
                    owner,
                    attachment_id,
                    max_bytes=effective.max_file_bytes,
                )
            except AppError:
                statuses[attachment_id] = "unavailable"
                chars[attachment_id] = 0
                continue
            if b"\x00" in data:
                statuses[attachment_id] = "binary_unsupported"
                chars[attachment_id] = 0
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                statuses[attachment_id] = "binary_unsupported"
                chars[attachment_id] = 0
                continue
            remaining = max(effective.max_chars - total, 0)
            if remaining <= 0:
                statuses[attachment_id] = "truncated"
                chars[attachment_id] = 0
                truncated = True
                continue
            if len(text) > remaining:
                text = text[:remaining]
                statuses[attachment_id] = "truncated"
                truncated = True
            else:
                statuses[attachment_id] = "included"
            chars[attachment_id] = len(text)
            total += len(text)
            chunks.append(
                f"--- attachment: {attachment.filename} ({attachment.media_type}) ---\n"
                f"{text}\n"
                "--- end attachment ---"
            )

        note = _note_for(attachments, statuses, truncated=truncated)
        return ModelAttachmentContext(
            text="\n\n".join(chunks),
            statuses=statuses,
            context_chars=chars,
            filenames=filenames,
            truncated=truncated,
            note=note,
        )

    @staticmethod
    def max_attachments_per_message() -> int:
        return MAX_ATTACHMENTS_PER_MESSAGE

    @staticmethod
    def max_upload_bytes() -> int:
        return MAX_UPLOAD_BYTES

    @staticmethod
    def max_context_chars() -> int:
        return MAX_CONTEXT_CHARS


__all__ = ["PrivateAttachmentService"]
