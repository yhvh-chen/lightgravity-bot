"""Markdown source-of-truth store (LG-004).

Public surface:

* :class:`FileStore` — authoritative entity reads/writes, JSONL events and
  messages, task leases, rebuildable index and partial-write recovery.
* :class:`Store` — structural protocol frozen by docs/08 §7.
* Typed errors and record dataclasses.

API wiring (``backend/lightgravity/api``) is owned by LG-012 and is intentionally
not touched here; LG-012 should depend on the ``Store`` protocol only.
"""

from .errors import (
    ConfigInvalid,
    EntityNotFound,
    IllegalTransition,
    LockConflict,
    PathOutsideWorkspace,
    RevisionConflict,
    StoreError,
)
from .ids import new_id, new_ulid
from .models import (
    ClaimResult,
    Diagnostic,
    EventRecord,
    IndexReport,
    MessageRecord,
    RecoveryReport,
    TaskSummary,
    Versioned,
)
from .paths import resolve_workspace_path
from .protocol import Store
from .store import FileStore

__all__ = [
    "FileStore",
    "Store",
    "StoreError",
    "ConfigInvalid",
    "EntityNotFound",
    "IllegalTransition",
    "LockConflict",
    "PathOutsideWorkspace",
    "RevisionConflict",
    "Versioned",
    "EventRecord",
    "MessageRecord",
    "ClaimResult",
    "TaskSummary",
    "IndexReport",
    "RecoveryReport",
    "Diagnostic",
    "new_id",
    "new_ulid",
    "resolve_workspace_path",
]
