"""Error codes, HTTP mapping and the app-level exception (docs/08 §4.2, §9)."""

from __future__ import annotations

from typing import Any

from .dto import ErrorBody, ErrorEnvelope
from .enums import ErrorCode

#: HTTP status for each frozen error code.
ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.PATH_OUTSIDE_WORKSPACE: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.REVISION_CONFLICT: 409,
    ErrorCode.LOCK_CONFLICT: 409,
    ErrorCode.NOT_READY: 409,
    ErrorCode.ILLEGAL_TRANSITION: 409,
    ErrorCode.CANCELLATION_UNCONFIRMED: 409,
    ErrorCode.ACCEPTANCE_STALE: 409,
    ErrorCode.CONFIG_INVALID: 422,
    ErrorCode.REFERENCE_INVALID: 422,
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.BUDGET_EXHAUSTED: 429,
    ErrorCode.CAPABILITY_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}

#: Whether a client may reasonably retry after a short backoff (docs/08 §4.2).
ERROR_RETRYABLE: dict[ErrorCode, bool] = {
    ErrorCode.INVALID_REQUEST: False,
    ErrorCode.UNAUTHORIZED: False,
    ErrorCode.PATH_OUTSIDE_WORKSPACE: False,
    ErrorCode.NOT_FOUND: False,
    ErrorCode.REVISION_CONFLICT: False,
    ErrorCode.LOCK_CONFLICT: True,
    ErrorCode.NOT_READY: False,
    ErrorCode.ILLEGAL_TRANSITION: False,
    ErrorCode.CANCELLATION_UNCONFIRMED: True,
    ErrorCode.ACCEPTANCE_STALE: False,
    ErrorCode.CONFIG_INVALID: False,
    ErrorCode.REFERENCE_INVALID: False,
    ErrorCode.VALIDATION_FAILED: False,
    ErrorCode.BUDGET_EXHAUSTED: False,
    ErrorCode.CAPABILITY_UNAVAILABLE: True,
    ErrorCode.INTERNAL_ERROR: False,
}


class AppError(Exception):
    """Domain error carrying a frozen error code.

    The API layer converts this into the standard error envelope; business
    packages raise it instead of returning ad-hoc JSON.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = (
            ERROR_RETRYABLE[code] if retryable is None else retryable
        )
        self.request_id = request_id

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS[self.code]

    def to_envelope(self, *, request_id: str | None = None) -> ErrorEnvelope:
        return error_envelope(
            self.code,
            self.message,
            details=self.details,
            retryable=self.retryable,
            request_id=self.request_id if request_id is None else request_id,
        )


def error_envelope(
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    retryable: bool | None = None,
    request_id: str | None = None,
) -> ErrorEnvelope:
    """Build the standard error envelope for a code."""

    return ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or {},
            retryable=ERROR_RETRYABLE[code] if retryable is None else retryable,
            request_id=request_id,
        )
    )


__all__ = ["AppError", "ERROR_HTTP_STATUS", "ERROR_RETRYABLE", "error_envelope"]
