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

#: Independent receipt branches frozen by docs/08 §20.6.  They are a
#: projection of the actual text/index state, never a second status store.
TEXT_BRANCH_STATES = ("pending", "extracting", "ready", "unavailable", "failed")
KEYWORD_BRANCH_STATES = ("pending", "indexing", "searchable", "no_text", "failed")
SEMANTIC_BRANCH_STATES = (
    "pending",
    "indexing",
    "searchable",
    "disabled",
    "unsupported",
    "failed",
)
INTAKE_MODES = ("sync", "deferred")


def pending_text_branch() -> dict[str, Any]:
    return {"status": "pending", "reason": None, "error_code": None}


def pending_keyword_branch() -> dict[str, Any]:
    return {"status": "pending", "reason": None, "error_code": None}


def pending_semantic_branch() -> dict[str, Any]:
    return {
        "status": "pending",
        "reason": None,
        "error_code": None,
        "model": None,
        "kinds": [],
        "failed_kinds": [],
    }


def normalize_text_branch(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    status = data.get("status")
    branch = pending_text_branch()
    branch["status"] = status if status in TEXT_BRANCH_STATES else "pending"
    branch["reason"] = data.get("reason") if isinstance(data.get("reason"), str) else None
    branch["error_code"] = (
        data.get("error_code") if isinstance(data.get("error_code"), str) else None
    )
    # 1.20 additive ASR provenance. These keys are only present when the
    # persisted branch actually carried them; old/non-audio branches keep the
    # frozen 1.19 three-field shape.
    if "language" in data:
        branch["language"] = data.get("language") if isinstance(data.get("language"), str) else None
    if "machine" in data:
        branch["machine"] = dict(data["machine"]) if isinstance(data.get("machine"), dict) else None
    if "timestamps" in data:
        branch["timestamps"] = data.get("timestamps") if isinstance(data.get("timestamps"), list) else None
    # LG-224 additive PDF extraction provenance: a client can tell a native
    # text-layer read from an OCR fallback.  Only present when persisted, so
    # legacy/non-PDF branches keep the frozen three-field shape.
    if "extractor" in data:
        branch["extractor"] = data.get("extractor") if isinstance(data.get("extractor"), str) else None
    return branch


def normalize_keyword_branch(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    status = data.get("status")
    branch = pending_keyword_branch()
    branch["status"] = status if status in KEYWORD_BRANCH_STATES else "pending"
    branch["reason"] = data.get("reason") if isinstance(data.get("reason"), str) else None
    branch["error_code"] = (
        data.get("error_code") if isinstance(data.get("error_code"), str) else None
    )
    return branch


def normalize_semantic_branch(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    status = data.get("status")
    branch = pending_semantic_branch()
    branch["status"] = status if status in SEMANTIC_BRANCH_STATES else "pending"
    branch["reason"] = data.get("reason") if isinstance(data.get("reason"), str) else None
    branch["error_code"] = (
        data.get("error_code") if isinstance(data.get("error_code"), str) else None
    )
    branch["model"] = data.get("model") if isinstance(data.get("model"), str) else None
    kinds = data.get("kinds")
    branch["kinds"] = [
        kind for kind in kinds if kind in ("text", "image", "audio")
    ] if isinstance(kinds, list) else []
    failed = data.get("failed_kinds")
    branch["failed_kinds"] = [
        kind for kind in failed if kind in ("text", "image", "audio")
    ] if isinstance(failed, list) else []
    return branch


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
    #: Exact producing job; legacy/version-only receipt lines have no association.
    job_id: str | None = None
    #: Additive receipt-v2 branches (docs/08 §20.6).  Old receipt lines read as
    #: ``pending`` so an upgrade never fabricates a branch result.
    text: dict[str, Any] = field(default_factory=pending_text_branch)
    keyword: dict[str, Any] = field(default_factory=pending_keyword_branch)
    semantic: dict[str, Any] = field(default_factory=pending_semantic_branch)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "job_id": self.job_id,
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
            "text": dict(self.text),
            "keyword": dict(self.keyword),
            "semantic": dict(self.semantic),
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
    def intake_mode(self) -> str:
        """``sync`` for old jobs (the frozen default) or ``deferred``."""

        value = self.entity.get("intake_mode")
        return value if value in INTAKE_MODES else "sync"

    @property
    def attempt(self) -> int:
        value = self.entity.get("attempt")
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else 1

    @property
    def budget(self) -> dict[str, Any]:
        value = self.entity.get("budget")
        return value if isinstance(value, dict) else {}

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
    "TEXT_BRANCH_STATES",
    "KEYWORD_BRANCH_STATES",
    "SEMANTIC_BRANCH_STATES",
    "INTAKE_MODES",
    "pending_text_branch",
    "pending_keyword_branch",
    "pending_semantic_branch",
    "normalize_text_branch",
    "normalize_keyword_branch",
    "normalize_semantic_branch",
    "Scope",
    "Origin",
    "ReceiptEntry",
    "SourceRecord",
    "IntakeJobRecord",
    "ReceiveResult",
]
