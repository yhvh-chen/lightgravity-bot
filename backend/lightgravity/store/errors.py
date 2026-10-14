"""Store-level error types (LG-004).

All of these subclass :class:`lightgravity.contracts.AppError` so the API layer
can serialize them with the frozen error envelope (docs/08 §4.2).  The class
names match the exception names used in docs/08 §7.

The store never invents new error codes; it only binds contract codes to
concrete, typed exceptions with useful ``details`` payloads.
"""

from __future__ import annotations

from typing import Any

from lightgravity.contracts import AppError, ErrorCode


class StoreError(AppError):
    """Base class for all store failures."""


class ConfigInvalid(StoreError):
    """Frontmatter/schema/duplicate-key/state validation failed (docs/08 §9)."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: list[dict[str, Any]] | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.CONFIG_INVALID,
            message,
            details={
                "diagnostics": diagnostics or [],
                **({"location": location} if location else {}),
            },
        )
        self.diagnostics = diagnostics or []


class EntityNotFound(StoreError):
    """Requested entity has no authoritative file."""

    def __init__(self, kind: str, entity_id: str, *, path: str | None = None) -> None:
        super().__init__(
            ErrorCode.NOT_FOUND,
            f"{kind} {entity_id!r} not found",
            details={"kind": kind, "id": entity_id, **({"path": path} if path else {})},
        )


class RevisionConflict(StoreError):
    """Optimistic-concurrency check failed; caller must re-read (docs/08 §9)."""

    def __init__(self, kind: str, entity_id: str, *, expected: int, actual: int) -> None:
        super().__init__(
            ErrorCode.REVISION_CONFLICT,
            f"revision conflict for {kind} {entity_id!r}: "
            f"expected {expected}, actual {actual}",
            details={
                "kind": kind,
                "id": entity_id,
                "expected_revision": expected,
                "actual_revision": actual,
                "etag": f'"{actual}"',
            },
        )
        self.expected = expected
        self.actual = actual


class LockConflict(StoreError):
    """Entity lock or task lease is held elsewhere; retryable (docs/08 §9)."""

    def __init__(self, resource: str, *, owner: str | None = None) -> None:
        super().__init__(
            ErrorCode.LOCK_CONFLICT,
            f"lock conflict on {resource!r}",
            details={"resource": resource, **({"owner": owner} if owner else {})},
            retryable=True,
        )
        self.resource = resource
        self.owner = owner


class PathOutsideWorkspace(StoreError):
    """Path escaped the authorized workspace root (docs/08 §10)."""

    def __init__(self, relative: str, *, root: str) -> None:
        super().__init__(
            ErrorCode.PATH_OUTSIDE_WORKSPACE,
            f"path {relative!r} is outside the authorized workspace",
            details={"path": relative, "workspace_root": root},
        )


class IllegalTransition(StoreError):
    """Illegal status/phase combination or disallowed migration (docs/08 §9)."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.ILLEGAL_TRANSITION,
            message,
            details={"diagnostics": diagnostics or []},
        )
        self.diagnostics = diagnostics or []


__all__ = [
    "StoreError",
    "ConfigInvalid",
    "EntityNotFound",
    "RevisionConflict",
    "LockConflict",
    "PathOutsideWorkspace",
    "IllegalTransition",
]
