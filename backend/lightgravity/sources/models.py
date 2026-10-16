"""Typed views of the ``source`` / ``intake_job`` entities (docs/08 §6.6).

These dataclasses are internal, non-wire records.  Their fields mirror the
frozen frontmatter exactly so callers (API, LG-035 extraction, LG-036 index)
read one vocabulary instead of poking at raw mappings.  Unknown frontmatter
fields are preserved in the stored document and surfaced separately, never
interpreted here (docs/08 §5.2, §6.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Display statuses for ``source`` (docs/08 §6.6).  These are **not** Task
#: phases and never enter the §6.1 ``phase`` enum.
SOURCE_STATUSES = (
    "received",
    "processing",
    "extracted",
    "attributed",
    "indexed",
    "archived",
    "partial",
    "failed",
)

#: Display statuses for ``intake_job`` (docs/08 §6.6).
JOB_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
    "recovery_required",
)

#: Display stages for ``intake_job.stage`` (docs/08 §6.6).
JOB_STAGES = (
    "received",
    "extracting",
    "attributing",
    "formalizing",
    "indexing",
    "done",
)

#: ``source.index.lexical`` values frozen by docs/08 §6.6.
LEXICAL_STATES = ("not_indexed", "indexed", "stale", "failed")
#: ``source.index.vector`` values frozen by docs/08 §6.6; LG-034 never enables it.
VECTOR_STATES = ("disabled", "not_indexed", "indexed", "stale", "failed")

TITLE_ORIGINS = ("user", "derived")
ORIGIN_KINDS = ("upload", "link", "external")


@dataclass(frozen=True, slots=True)
class Scope:
    """Attribution scope of a source (docs/08 §6.6).

    At most one target is set.  ``inbox_ref`` marks the controlled inbox for
    material with unknown/global attribution; it never implies a Task.
    """

    task_ref: str | None = None
    project_ref: str | None = None
    inbox_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "project_ref": self.project_ref,
            "inbox_ref": self.inbox_ref,
        }

    @classmethod
    def from_dict(cls, value: Any) -> Scope:
        data = value if isinstance(value, dict) else {}
        return cls(
            task_ref=_as_optional_str(data.get("task_ref")),
            project_ref=_as_optional_str(data.get("project_ref")),
            inbox_ref=_as_optional_str(data.get("inbox_ref")),
        )

    @property
    def is_global(self) -> bool:
        return self.task_ref is None and self.project_ref is None


@dataclass(frozen=True, slots=True)
class Origin:
    """Where the material came from (docs/08 §6.6).

    ``fetched=False`` for a recorded link means "recorded only, not fetched" —
    callers must not present it as ingested (docs/09 §3).
    """

    kind: str = "upload"
    external_ref: str | None = None
    fetched: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "external_ref": self.external_ref,
            "fetched": self.fetched,
        }

    @classmethod
    def from_dict(cls, value: Any) -> Origin:
        data = value if isinstance(value, dict) else {}
        kind = data.get("kind")
        return cls(
            kind=kind if isinstance(kind, str) and kind in ORIGIN_KINDS else "upload",
            external_ref=_as_optional_str(data.get("external_ref")),
            fetched=bool(data.get("fetched", False)),
        )


@dataclass(frozen=True, slots=True)
class ReceiptEntry:
    """One per-file receipt line (docs/08 §4.3 ``GET /sources/{id}/receipt``).

    The receipt reads the **same** file state that Files/Chat read; it is a
    projection, never a second status store.  A failed entry never carries
    fabricated body text (docs/09 §6).
    """

    source_id: str
    filename: str
    status: str
    stage: str
    detail: str | None
    searchable: bool
    original_path: str | None
    formal_path: str | None
    content_hash: str | None
    source_version: int
    at: str
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "filename": self.filename,
            "status": self.status,
            "stage": self.stage,
            "detail": self.detail,
            "searchable": self.searchable,
            "original_path": self.original_path,
            "formal_path": self.formal_path,
            "content_hash": self.content_hash,
            "source_version": self.source_version,
            "at": self.at,
            "error_code": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """A ``source`` entity read from its authoritative frontmatter."""

    source_id: str
    revision: int
    entity: dict[str, Any]
    content_hash: str
    body: str
    path: str

    @property
    def title(self) -> str:
        return str(self.entity.get("title") or "")

    @property
    def status(self) -> str:
        return str(self.entity.get("status") or "received")

    @property
    def source_version(self) -> int:
        value = self.entity.get("source_version")
        return value if isinstance(value, int) and not isinstance(value, bool) else 1

    @property
    def scope(self) -> Scope:
        return Scope.from_dict(self.entity.get("scope"))

    @property
    def origin(self) -> Origin:
        return Origin.from_dict(self.entity.get("origin"))

    @property
    def content_digest(self) -> str | None:
        value = self.entity.get("content_hash")
        return value if isinstance(value, str) and value else None

    @property
    def archived(self) -> bool:
        """Reversible organizational archive flag (docs/08 §6.6).

        This is **not** the invalidating ``revoke`` state (which sets
        ``status=archived``).  An archived source keeps its origin, scope,
        permissions, retrievability and openability; only ``revoke``/``delete``
        make it unavailable.  Absent means ``False``.
        """

        return bool(self.entity.get("archived", False))

    @property
    def etag(self) -> str:
        return f'"{self.revision}"'


@dataclass(frozen=True, slots=True)
class IntakeJobRecord:
    """An ``intake_job`` entity read from its authoritative frontmatter."""

    job_id: str
    revision: int
    entity: dict[str, Any]
    content_hash: str
    body: str
    path: str

    @property
    def source_ref(self) -> str | None:
        value = self.entity.get("source_ref")
        return value if isinstance(value, str) else None

    @property
    def status(self) -> str:
        return str(self.entity.get("status") or "queued")

    @property
    def stage(self) -> str:
        return str(self.entity.get("stage") or "received")

    @property
    def request_id(self) -> str | None:
        value = self.entity.get("request_id")
        return value if isinstance(value, str) else None

    @property
    def payload_hash(self) -> str | None:
        value = self.entity.get("payload_hash")
        return value if isinstance(value, str) and value else None

    @property
    def cancel(self) -> dict[str, Any]:
        value = self.entity.get("cancel")
        return value if isinstance(value, dict) else {"requested": False, "confirmed": False}

    @property
    def etag(self) -> str:
        return f'"{self.revision}"'


@dataclass(frozen=True, slots=True)
class ReceiveResult:
    """Outcome of one ``POST /sources`` intake request."""

    source: SourceRecord
    job: IntakeJobRecord
    deduplicated: bool
    created: bool
    receipts: list[ReceiptEntry] = field(default_factory=list)


def _as_optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


__all__ = [
    "SOURCE_STATUSES",
    "JOB_STATUSES",
    "JOB_STAGES",
    "LEXICAL_STATES",
    "VECTOR_STATES",
    "TITLE_ORIGINS",
    "ORIGIN_KINDS",
    "Scope",
    "Origin",
    "ReceiptEntry",
    "SourceRecord",
    "IntakeJobRecord",
    "ReceiveResult",
]
