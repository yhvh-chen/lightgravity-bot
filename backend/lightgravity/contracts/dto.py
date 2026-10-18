"""Error envelope DTOs and health/version DTOs (docs/08 §4.2).

These are the frozen wire shapes for LG-002's real ``/health`` and ``/version``
endpoints plus the shared error envelope used by all API tasks.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import ErrorCode


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class Author(BaseModel):
    """Server-injected message author (LG-050, docs/08 additive).

    Persisted on team-mode conversation messages and returned inside each
    message item.  It is produced by the server from the session; a client can
    never supply it (the request model forbids the field).
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    username: str | None = None
    role: str | None = None


class HealthResponse(BaseModel):
    """Process liveness, version and capability overview (docs/08 §4.3).

    ``capabilities`` reports only what is *actually* wired at skeleton stage.
    Unimplemented features stay ``False`` rather than being advertised.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    package_version: str
    contract_version: str
    schema_version: str
    capabilities: dict[str, bool] = Field(default_factory=dict)
    # LG-249 additive, non-secret: the exact configured Team routing mention.
    # Populated only in team mode; single-user/older backends omit or return
    # null. Clients must never substitute a hard-coded @bot fallback.
    team_bot_mention: str | None = None


class VersionResponse(BaseModel):
    """Contract/schema/build information (docs/08 §4.3)."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str
    schema_version: str
    package_version: str
    python_version: str
    platform: str


__all__ = [
    "Author",
    "ErrorBody",
    "ErrorEnvelope",
    "HealthResponse",
    "VersionResponse",
]
