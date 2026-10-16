"""Private LG-025 value types.

These are deliberately *not* added to ``lightgravity.contracts`` (docs/08 §11:
the contracts module is owned by the integration executor and frozen).  They
are the settings-layer view of the same Connection/SETTINGS.md files defined in
docs/07 §3 and docs/08 §6.5; LG-012/LG-026 can publish wire DTOs later without
changing any frozen field meaning.

Secret rule: none of these types ever carries a secret *value*.  They carry a
``credential_ref`` plus an opaque ``credential_version`` token, and public
serialization only reports configured/source, never the value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Connection roles used when pinning a resolved default.
ROLE_COORDINATOR = "coordinator"
ROLE_WORKER = "worker"
#: LG-017 additive role: the independent reviewer runs on its own default
#: connection/credential so its context is separate from the implementer.  It is
#: a settings role only; it adds no ``state``/``phase``/``acceptance`` enum value.
ROLE_REVIEWER = "reviewer"
ROLE_EXPLICIT = "explicit"

#: The default settings roles a connection can be pinned to (LG-017 adds reviewer).
DEFAULT_ROLES = (ROLE_COORDINATOR, ROLE_WORKER, ROLE_REVIEWER)

#: The only first-version backend that may be an executable default (docs/08 §8.1).
DEFAULT_EXECUTABLE_BACKEND = "openai-compat"

#: First-version preferred model id (docs/07 §3).  It is recorded and sent as-is;
#: the upstream may normalize the reported model name (LG-006).
PREFERRED_MODEL = "deepseek-v4-flash"

#: Default upstream for an OpenAI-compatible DeepSeek connection.
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


@dataclass(frozen=True, slots=True)
class Connection:
    """A ``kind: connection`` resource, minus any secret material."""

    id: str
    title: str
    enabled: bool
    revision: int
    content_hash: str
    backend: str
    model: str | None
    base_url: str | None
    credential_ref: str | None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Non-secret public view (credential status added by the service)."""

        return {
            "id": self.id,
            "title": self.title,
            "enabled": self.enabled,
            "revision": self.revision,
            "content_hash": self.content_hash,
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url,
            "credential_ref": self.credential_ref,
        }


@dataclass(frozen=True, slots=True)
class GlobalSettings:
    """``kind: settings`` — default connection references only (docs/07 §3)."""

    revision: int
    content_hash: str
    default_coordinator_connection_ref: str | None
    default_worker_connection_ref: str | None
    #: LG-017 additive: independent-reviewer default connection.  ``None`` means
    #: no real reviewer is configured, so the runtime reports ``unavailable``
    #: instead of reviewing with the implementer's own connection.
    default_reviewer_connection_ref: str | None = None
    #: LG-031 additive: decentralized collaboration switches (docs/08 §6.5).  All
    #: default to the closed/deterministic path; a missing or invalid value is
    #: read as the default and never opens the decentralized path implicitly.
    decentralized_claim_enabled: bool = False
    collab_requests_enabled: bool = False
    claim_lease_seconds: int = 300
    exists: bool = True
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "exists": self.exists,
            "content_hash": self.content_hash,
            "default_coordinator_connection_ref": self.default_coordinator_connection_ref,
            "default_worker_connection_ref": self.default_worker_connection_ref,
            "default_reviewer_connection_ref": self.default_reviewer_connection_ref,
            "decentralized_claim_enabled": self.decentralized_claim_enabled,
            "collab_requests_enabled": self.collab_requests_enabled,
            "claim_lease_seconds": self.claim_lease_seconds,
        }


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    """Whether a ``credential_ref`` resolves, and from where (never the value)."""

    ref: str
    configured: bool
    source: str | None = None  # "secret_store" | "environment" | None
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "configured": self.configured,
            "source": self.source,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ConnectionReferences:
    """Everything that points at a connection id (docs/07 §3, §6)."""

    connection_id: str
    default_roles: tuple[str, ...] = ()
    agent_refs: tuple[str, ...] = ()

    @property
    def referenced(self) -> bool:
        return bool(self.default_roles or self.agent_refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "default_roles": list(self.default_roles),
            "agent_refs": list(self.agent_refs),
        }


@dataclass(frozen=True, slots=True)
class PinnedConnection:
    """A resolved connection fixed for one session/member (docs/07 §3).

    Changing SETTINGS.md or the connection later does not mutate this record;
    :meth:`still_current` detects drift so a coordinator can decide whether to
    re-pin.  ``credential_version`` is an opaque token, not the secret.
    """

    connection_id: str
    role: str
    revision: int
    content_hash: str
    backend: str
    model: str | None
    base_url: str | None
    credential_ref: str | None
    credential_version: str | None
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "role": self.role,
            "revision": self.revision,
            "content_hash": self.content_hash,
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url,
            "credential_ref": self.credential_ref,
            "credential_version": self.credential_version,
            "config_hash": self.config_hash,
        }

    def still_current(self, connection: "Connection", credential_version: str | None) -> bool:
        return (
            connection.revision == self.revision
            and connection.content_hash == self.content_hash
            and (credential_version or None) == (self.credential_version or None)
        )


@dataclass(frozen=True, slots=True)
class TestLayerResult:
    """One layer of a connection test (docs/07 §5)."""

    name: str
    status: str  # passed | failed | skipped | declared
    detail: str = ""
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    """A layered test record bound to connection revision + credential version.

    ``overall`` is intentionally not a single boolean: the static config, the
    real network/model result and the SDK capability *declaration* are reported
    separately so a network success can never be presented as "SDK capability
    verified" (docs/07 §5, docs/08 §8.1).
    """

    test_id: str
    connection_id: str
    connection_revision: int
    credential_ref: str | None
    credential_version: str | None
    backend: str
    model: str | None
    base_url_host: str | None
    started_at: str
    finished_at: str
    layers: tuple[TestLayerResult, ...]
    overall: str  # verified | partial | failed | not_run
    note: str = ""

    def layer(self, name: str) -> TestLayerResult | None:
        for item in self.layers:
            if item.name == name:
                return item
        return None

    def is_stale(
        self, connection_revision: int, credential_version: str | None
    ) -> bool:
        return self.connection_revision != connection_revision or (
            (self.credential_version or None) != (credential_version or None)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "connection_id": self.connection_id,
            "connection_revision": self.connection_revision,
            "credential_ref": self.credential_ref,
            "credential_version": self.credential_version,
            "backend": self.backend,
            "model": self.model,
            "base_url_host": self.base_url_host,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "layers": [layer.to_dict() for layer in self.layers],
            "overall": self.overall,
            "note": self.note,
        }


__all__ = [
    "ROLE_COORDINATOR",
    "ROLE_WORKER",
    "ROLE_EXPLICIT",
    "DEFAULT_EXECUTABLE_BACKEND",
    "PREFERRED_MODEL",
    "DEFAULT_BASE_URL",
    "Connection",
    "GlobalSettings",
    "CredentialStatus",
    "ConnectionReferences",
    "PinnedConnection",
    "TestLayerResult",
    "ConnectionTestResult",
]
