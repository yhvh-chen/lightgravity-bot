"""Private Personal attachment value objects and bounded text limits (LG-119).

The private attachment scope is **Personal chat only**.  It is deliberately
separate from the shared source/material scope: nothing here registers a
``source``, writes a shared index, or calls OCR/ASR/embedding/network code.

These models are internal to the backend.  The wire view never exposes the
owner digest or a filesystem path (docs/08 §19.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: One upload body may be at most 10,000,000 bytes (docs/08 §19.3).
MAX_UPLOAD_BYTES = 10_000_000

#: A Personal message may reference at most three private attachments.
MAX_ATTACHMENTS_PER_MESSAGE = 3

#: Bounded model context (R2): 64 KiB raw per file, 12,000 Unicode chars total.
MAX_CONTEXT_FILE_BYTES = 64 * 1024
MAX_CONTEXT_CHARS = 12_000

#: Supported local text media types / extension fallback.  This is an explicit
#: allow-list: unknown binaries are never presented as model-readable text.
SUPPORTED_MEDIA_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/yaml",
        "application/x-yaml",
    }
)
SUPPORTED_EXTENSIONS = frozenset(
    {".txt", ".md", ".markdown", ".csv", ".json", ".yaml", ".yml", ".log"}
)

CONTEXT_STATUSES = frozenset(
    {
        "included",
        "truncated",
        "unsupported_type",
        "binary_unsupported",
        "too_large",
        "unavailable",
    }
)


@dataclass(frozen=True, slots=True)
class PrivateAttachment:
    """Canonical persisted metadata for one owner-scoped attachment."""

    attachment_id: str
    filename: str
    media_type: str
    size: int
    sha256: str
    status: str
    created_at: str
    message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "attachment_id": self.attachment_id,
            "filename": self.filename,
            "media_type": self.media_type,
            "size": self.size,
            "sha256": self.sha256,
            "status": self.status,
            "created_at": self.created_at,
        }
        if self.message_id is not None:
            payload["message_id"] = self.message_id
        return payload

    def snapshot(
        self, *, context_status: str, context_chars: int
    ) -> dict[str, Any]:
        """Canonical persisted message snapshot (no path/owner)."""

        payload = self.to_dict()
        payload["context_status"] = context_status
        payload["context_chars"] = context_chars
        return payload


@dataclass(frozen=True, slots=True)
class AttachmentLimits:
    """Per-message resolver bounds; injectable for focused tests."""

    max_attachments: int = MAX_ATTACHMENTS_PER_MESSAGE
    max_file_bytes: int = MAX_CONTEXT_FILE_BYTES
    max_chars: int = MAX_CONTEXT_CHARS


@dataclass(frozen=True, slots=True)
class ModelAttachmentContext:
    """Bounded text context plus honest per-attachment inclusion facts."""

    text: str
    statuses: dict[str, str] = field(default_factory=dict)
    context_chars: dict[str, int] = field(default_factory=dict)
    filenames: dict[str, str] = field(default_factory=dict)
    truncated: bool = False
    note: str | None = None

    @property
    def included(self) -> bool:
        return any(status in {"included", "truncated"} for status in self.statuses.values())

    def snapshot_for(self, attachment: PrivateAttachment) -> dict[str, Any]:
        status = self.statuses.get(attachment.attachment_id, "unavailable")
        return attachment.snapshot(
            context_status=status,
            context_chars=self.context_chars.get(attachment.attachment_id, 0),
        )


__all__ = [
    "AttachmentLimits",
    "CONTEXT_STATUSES",
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "MAX_CONTEXT_CHARS",
    "MAX_CONTEXT_FILE_BYTES",
    "MAX_UPLOAD_BYTES",
    "ModelAttachmentContext",
    "PrivateAttachment",
    "SUPPORTED_EXTENSIONS",
    "SUPPORTED_MEDIA_TYPES",
]
