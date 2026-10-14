"""Adapter-layer errors bound to the frozen contract error codes (docs/08 §4.2, §9).

The adapter does not invent new codes: resource/schema problems surface as
``config_invalid``, dangling or wrong-kind references as ``reference_invalid``
and versioned/runtime capability gaps as ``capability_unavailable``.  ``Store``
errors (``ConfigInvalid``, ``EntityNotFound`` ...) propagate unchanged from the
read boundary.
"""

from __future__ import annotations

from typing import Any

from lightgravity.contracts import AppError, ErrorCode

_DIAGNOSTIC_LIST = list[dict[str, Any]]


class AdapterError(AppError):
    """Base class for all adapter compile/build failures."""


class AdapterConfigInvalid(AdapterError):
    """Frontmatter/schema/field-combination problem (docs/08 §9)."""

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


class ReferenceInvalid(AdapterError):
    """A resource reference is missing, of the wrong kind or unregistered."""

    def __init__(
        self,
        message: str,
        *,
        kind: str | None = None,
        ref: str | None = None,
        detail: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if kind is not None:
            details["kind"] = kind
        if ref is not None:
            details["ref"] = ref
        if detail is not None:
            details["detail"] = detail
        super().__init__(ErrorCode.REFERENCE_INVALID, message, details=details)
        self.kind = kind
        self.ref = ref


class CapabilityUnavailable(AdapterError):
    """A real SDK/runtime capability is unavailable (503, retryable)."""

    def __init__(
        self,
        message: str,
        *,
        capability: str | None = None,
        missing: list[str] | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            message,
            details={
                **({"capability": capability} if capability else {}),
                "missing": missing or [],
            },
        )
        self.capability = capability


__all__ = [
    "AdapterError",
    "AdapterConfigInvalid",
    "ReferenceInvalid",
    "CapabilityUnavailable",
]
