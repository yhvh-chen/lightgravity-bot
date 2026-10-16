"""Shared, frozen contract types (LG-001 / docs/08-interface-contract.md).

Owned by the integration executor. Other tasks import from here and must not
copy these definitions (docs/08 §11).
"""

from .constants import API_PREFIX, CONTRACT_VERSION, SCHEMA_NAMESPACE
from .dto import Author, ErrorBody, ErrorEnvelope, HealthResponse, VersionResponse
from .enums import (
    AcceptanceStatus,
    ActionName,
    ActionState,
    ErrorCode,
    EventType,
    MemberState,
    QueueState,
    RunCleanupStatus,
    RunState,
    SubtaskAcceptanceStatus,
    SubtaskState,
    TaskPhase,
    TaskStatus,
)
from .errors import (
    AppError,
    ERROR_HTTP_STATUS,
    ERROR_RETRYABLE,
    error_envelope,
)

__all__ = [
    "API_PREFIX",
    "CONTRACT_VERSION",
    "SCHEMA_NAMESPACE",
    "AcceptanceStatus",
    "ActionName",
    "ActionState",
    "ErrorCode",
    "EventType",
    "MemberState",
    "QueueState",
    "RunCleanupStatus",
    "RunState",
    "SubtaskAcceptanceStatus",
    "SubtaskState",
    "TaskPhase",
    "TaskStatus",
    "AppError",
    "Author",
    "ERROR_HTTP_STATUS",
    "ERROR_RETRYABLE",
    "error_envelope",
    "ErrorBody",
    "ErrorEnvelope",
    "HealthResponse",
    "VersionResponse",
]
