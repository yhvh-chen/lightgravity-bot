"""Collaboration-layer errors mapped onto frozen contract error codes (LG-029).

The frozen codes (docs/08 §4.2) are ``stale_lease`` (409, non-retryable) and
``claim_refused`` (409, non-retryable, carries a stable ``reason``).  They were
registered by LG-028 for the decentralized line and are ``frozen-but-unimplemented``
until this task.  Using the frozen ``AppError`` keeps the HTTP mapping and
retryability centralized instead of re-declaring them here.
"""

from __future__ import annotations

from typing import Any

from lightgravity.contracts import AppError, ErrorCode


class ClaimRefused(AppError):
    """A candidate claim request the program refuses (docs/08 §4.2).

    ``reason`` is a stable machine token, not free text, so callers and the
    ``subtask.claim_refused`` event can be classified without parsing prose.
    """

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = {"reason": reason}
        if details:
            merged.update(details)
        super().__init__(ErrorCode.CLAIM_REFUSED, message, details=merged)
        self.reason = reason


class StaleLease(AppError):
    """A write-back with a fence that is not the current lease fence (§6.3).

    Fencing rejects the write *without* persisting anything: it is not
    last-write-wins.  ``stale_lease`` is non-retryable because retrying with the
    same fence can never succeed; the caller must re-discover and re-claim.
    """

    def __init__(
        self,
        subtask_id: str,
        *,
        provided: int,
        current: int,
        reason: str = "fence_mismatch",
    ) -> None:
        super().__init__(
            ErrorCode.STALE_LEASE,
            f"fence mismatch for subtask {subtask_id}: provided={provided} current={current}",
            details={
                "reason": reason,
                "subtask_ref": subtask_id,
                "provided_fence": provided,
                "current_fence": current,
            },
        )
        self.provided_fence = provided
        self.current_fence = current


__all__ = ["ClaimRefused", "StaleLease"]
