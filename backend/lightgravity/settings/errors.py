"""Settings/connection error types (docs/08 §4.2, §9).

LG-025 does not add any error code: problems surface through the frozen v1
codes.  Connection/settings field problems are ``config_invalid``; dangling or
blocked references (default pointing at a missing/unverified connection, a
credential still used by a connection) are ``reference_invalid``; an
unresolvable credential for a real test is ``capability_unavailable``.
"""

from __future__ import annotations

from typing import Any

from lightgravity.contracts import AppError, ErrorCode

_DIAGNOSTIC_LIST = list[dict[str, Any]]


class SettingsError(AppError):
    """Base class for all settings/connection/credential failures."""


class SettingsConfigInvalid(SettingsError):
    """Connection/settings frontmatter or field-combination problem (422)."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: _DIAGNOSTIC_LIST | None = None,
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


class ConnectionReferenceInvalid(SettingsError):
    """A reference would become dangling / a referenced entity blocks the op."""

    def __init__(
        self,
        message: str,
        *,
        kind: str | None = None,
        ref: str | None = None,
        detail: str | None = None,
        references: dict[str, Any] | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if kind is not None:
            details["kind"] = kind
        if ref is not None:
            details["ref"] = ref
        if detail is not None:
            details["detail"] = detail
        if references is not None:
            details["references"] = references
        super().__init__(ErrorCode.REFERENCE_INVALID, message, details=details)
        self.kind = kind
        self.ref = ref
        self.references = references or {}


class CredentialUnavailable(SettingsError):
    """A real connection test needs a credential that cannot be resolved (503)."""

    def __init__(self, message: str, *, ref: str | None = None) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            message,
            details={**({"ref": ref} if ref else {})},
        )
        self.ref = ref


class SecretStoreError(SettingsError):
    """The controlled secret store cannot be read/written safely (500)."""

    def __init__(self, message: str, *, location: str | None = None) -> None:
        super().__init__(
            ErrorCode.INTERNAL_ERROR,
            message,
            details={**({"location": location} if location else {})},
        )


__all__ = [
    "SettingsError",
    "SettingsConfigInvalid",
    "ConnectionReferenceInvalid",
    "CredentialUnavailable",
    "SecretStoreError",
]
