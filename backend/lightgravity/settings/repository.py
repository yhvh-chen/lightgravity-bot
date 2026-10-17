"""Store-backed repository for Connection and SETTINGS.md (docs/07 §3, docs/08 §6.5).

Connections and the global defaults share one authority: the LG-004 ``Store``.
Connections live at ``resources/connections/<id>.md``; defaults live at
``settings/SETTINGS.md`` (``kind: settings``, id ``settings``).  There is no
second provider/model state database.

The repository only maps stored frontmatter to the private value types and
validates the first-version backend rules; policy (default legality, reference
blocking, cross-file compensation, credential handling) lives in the service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lightgravity.adapter.provider_matrix import (
    capabilities_for_connection,
    capabilities_for_registration,
    validate_provider_fields,
)
from lightgravity.adapter.registry import ImplementationRegistry, default_registry
from lightgravity.store import ConfigInvalid, EntityNotFound, Versioned
from lightgravity.store import Store

from .errors import SettingsConfigInvalid
from .models import (
    DEFAULT_EXECUTABLE_BACKEND,
    Connection,
    GlobalSettings,
)

SETTINGS_KIND = "settings"
SETTINGS_ID = "settings"
CONNECTION_KIND = "connection"
SETTINGS_RELATIVE = ("settings", "SETTINGS.md")
_CONNECTIONS_SUBDIR = ("resources", "connections")
_AGENTS_SUBDIR = ("resources", "agents")

_UNSET: Any = object()


def _require_str(data: dict[str, Any], field: str, kind: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise SettingsConfigInvalid(
            f"{kind}.{field} is required and must be a non-empty string",
            diagnostics=[{"code": f"{field}_missing", "location": f"{kind}.{field}"}],
        )
    return value


def _optional_str(data: dict[str, Any], field: str) -> str | None:
    value = data.get(field)
    return value if isinstance(value, str) and value else None


def _connection_from_versioned(versioned: Versioned) -> Connection:
    data = versioned.entity
    backend = _require_str(data, "backend", CONNECTION_KIND)
    return Connection(
        id=versioned.entity_id,
        title=str(data.get("title") or versioned.entity_id),
        enabled=bool(data.get("enabled", True)),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        backend=backend,
        model=_optional_str(data, "model"),
        base_url=_optional_str(data, "base_url"),
        credential_ref=_optional_str(data, "credential_ref"),
        auth_mode=_optional_str(data, "auth_mode"),
        project=_optional_str(data, "project"),
        location=_optional_str(data, "location"),
        model_path=_optional_str(data, "model_path"),
        litert_backend=_optional_str(data, "litert_backend"),
        data=dict(data),
    )


def _optional_bool(data: dict[str, Any], field: str, *, default: bool = False) -> bool:
    value = data.get(field)
    return value if isinstance(value, bool) else default


def _optional_positive_int(data: dict[str, Any], field: str, *, default: int) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return default
    return value


def _settings_from_versioned(versioned: Versioned) -> GlobalSettings:
    data = versioned.entity
    return GlobalSettings(
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        default_coordinator_connection_ref=_optional_str(
            data, "default_coordinator_connection_ref"
        ),
        default_worker_connection_ref=_optional_str(data, "default_worker_connection_ref"),
        default_reviewer_connection_ref=_optional_str(
            data, "default_reviewer_connection_ref"
        ),
        decentralized_claim_enabled=_optional_bool(data, "decentralized_claim_enabled"),
        collab_requests_enabled=_optional_bool(data, "collab_requests_enabled"),
        claim_lease_seconds=_optional_positive_int(data, "claim_lease_seconds", default=300),
        exists=True,
        data=dict(data),
    )


def _empty_settings() -> GlobalSettings:
    return GlobalSettings(
        revision=0,
        content_hash="",
        default_coordinator_connection_ref=None,
        default_worker_connection_ref=None,
        default_reviewer_connection_ref=None,
        exists=False,
        data={},
    )


class ConnectionRepository:
    """Read/write connections and SETTINGS.md through the ``Store`` protocol."""

    def __init__(
        self,
        store: Store,
        *,
        registry: ImplementationRegistry | None = None,
    ) -> None:
        self._store = store
        self._registry = registry or default_registry()

    @property
    def store(self) -> Store:
        return self._store

    @property
    def registry(self) -> ImplementationRegistry:
        return self._registry

    # ------------------------------------------------------------- connections
    def capabilities(self, backend: str) -> dict[str, bool | None] | None:
        registration = self._registry.backend(backend)
        if registration is None:
            return None
        return capabilities_for_registration(registration)

    def connection_capabilities(
        self, connection: Connection
    ) -> dict[str, bool | None] | None:
        """Capability facts for this record, including its endpoint host policy."""

        registration = self._registry.backend(connection.backend)
        if registration is None:
            return None
        return capabilities_for_connection(
            registration,
            backend=connection.backend,
            base_url=connection.base_url,
        )

    def validate_backend(
        self,
        backend: str,
        *,
        model: str | None,
        base_url: str | None,
        auth_mode: str | None = None,
        project: str | None = None,
        location: str | None = None,
        model_path: str | None = None,
        litert_backend: str | None = None,
        credential_ref: str | None = None,
    ) -> None:
        """Validate the complete non-secret provider configuration.

        Saving only requires the backend to be *configurable*; it never requires
        executable/vendor-verified status.  Unknown-but-old backends are not
        rewritten by reads, but a save/update through this validator must use a
        registered backend.
        """

        registration = self._registry.backend(backend)
        if registration is None:
            raise SettingsConfigInvalid(
                f"connection backend {backend!r} is not registered for this version",
                diagnostics=[
                    {
                        "code": "backend_unsupported",
                        "location": f"{CONNECTION_KIND}.backend",
                        "detail": {"backend": backend},
                    }
                ],
            )
        if not registration.configurable:
            raise SettingsConfigInvalid(
                f"backend {backend!r} is not configurable in this environment",
                diagnostics=[
                    {
                        "code": "backend_unconfigurable",
                        "location": f"{CONNECTION_KIND}.backend",
                        "detail": {"backend": backend},
                    }
                ],
            )
        _, diagnostics = validate_provider_fields(
            backend=backend,
            auth_mode=auth_mode,
            model=model,
            base_url=base_url,
            project=project,
            location=location,
            model_path=model_path,
            litert_backend=litert_backend,
            credential_ref=credential_ref,
        )
        if diagnostics:
            raise SettingsConfigInvalid(
                f"connection {backend!r} configuration is invalid",
                diagnostics=diagnostics,
                location=f"{CONNECTION_KIND}.backend",
            )

    def read_connection(self, connection_id: str) -> Connection:
        versioned = self._store.read(CONNECTION_KIND, connection_id)
        return _connection_from_versioned(versioned)

    def get_connection_or_none(self, connection_id: str) -> Connection | None:
        try:
            return self.read_connection(connection_id)
        except EntityNotFound:
            return None

    def list_connections(self) -> list[Connection]:
        root = self._connections_dir()
        if root is None or not root.is_dir():
            return []
        connections: list[Connection] = []
        for path in sorted(root.glob("*.md")):
            try:
                connections.append(self.read_connection(path.stem))
            except ConfigInvalid:
                # An invalid file is a diagnostics concern, not a reason to
                # hide the valid connections; it is reported by the store index.
                continue
        return connections

    def create_connection(
        self,
        connection_id: str,
        *,
        title: str | None = None,
        backend: str = DEFAULT_EXECUTABLE_BACKEND,
        model: str | None = None,
        base_url: str | None = None,
        credential_ref: str | None = None,
        enabled: bool = True,
        auth_mode: Any = _UNSET,
        project: Any = _UNSET,
        location: Any = _UNSET,
        model_path: Any = _UNSET,
        litert_backend: Any = _UNSET,
        actor: str,
        request_id: str,
    ) -> Connection:
        self.validate_backend(
            backend,
            model=model,
            base_url=base_url,
            auth_mode=None if auth_mode is _UNSET else auth_mode,
            project=None if project is _UNSET else project,
            location=None if location is _UNSET else location,
            model_path=None if model_path is _UNSET else model_path,
            litert_backend=None if litert_backend is _UNSET else litert_backend,
            credential_ref=credential_ref,
        )
        content: dict[str, Any] = {
            "title": title or connection_id,
            "enabled": enabled,
            "backend": backend,
            "model": model,
            "base_url": base_url,
            "credential_ref": credential_ref,
        }
        for key, value in (
            ("auth_mode", auth_mode),
            ("project", project),
            ("location", location),
            ("model_path", model_path),
            ("litert_backend", litert_backend),
        ):
            if value is not _UNSET:
                content[key] = value
        versioned = self._store.create(
            CONNECTION_KIND,
            connection_id,
            content,
            actor=actor,
            request_id=request_id,
        )
        return _connection_from_versioned(versioned)

    def write_connection(
        self,
        connection_id: str,
        updates: dict[str, Any],
        *,
        expected_revision: int,
        actor: str,
    ) -> Connection:
        versioned = self._store.write(
            CONNECTION_KIND,
            connection_id,
            updates,
            expected_revision=expected_revision,
            actor=actor,
        )
        return _connection_from_versioned(versioned)

    def delete_connection(
        self,
        connection_id: str,
        *,
        expected_revision: int,
        actor: str,
        guard: Any = None,
    ) -> None:
        """Delete one Connection under the store's entity lock.

        ``guard`` runs after the revision check while the lock is still held, so
        reference/default checks and the unlink share one controlled boundary.
        No secret-store value is read or removed here.
        """

        delete = getattr(self._store, "delete", None)
        if not callable(delete):
            raise SettingsConfigInvalid(
                "the configured store does not support controlled deletion",
                diagnostics=[{"code": "delete_unsupported", "location": CONNECTION_KIND}],
            )
        delete(
            CONNECTION_KIND,
            connection_id,
            expected_revision=expected_revision,
            actor=actor,
            guard=guard,
        )

    # ---------------------------------------------------------------- settings
    def read_settings(self) -> GlobalSettings:
        try:
            versioned = self._store.read(SETTINGS_KIND, SETTINGS_ID)
        except EntityNotFound:
            return _empty_settings()
        return _settings_from_versioned(versioned)

    def create_settings(
        self,
        *,
        default_coordinator_connection_ref: str | None,
        default_worker_connection_ref: str | None,
        default_reviewer_connection_ref: str | None = None,
        decentralized_claim_enabled: bool = False,
        collab_requests_enabled: bool = False,
        claim_lease_seconds: int = 300,
        actor: str,
        request_id: str,
    ) -> GlobalSettings:
        content = {
            "default_coordinator_connection_ref": default_coordinator_connection_ref,
            "default_worker_connection_ref": default_worker_connection_ref,
            "default_reviewer_connection_ref": default_reviewer_connection_ref,
            "decentralized_claim_enabled": decentralized_claim_enabled,
            "collab_requests_enabled": collab_requests_enabled,
            "claim_lease_seconds": claim_lease_seconds,
        }
        versioned = self._store.create(
            SETTINGS_KIND, SETTINGS_ID, content, actor=actor, request_id=request_id
        )
        return _settings_from_versioned(versioned)

    def write_settings(
        self,
        updates: dict[str, Any],
        *,
        expected_revision: int,
        actor: str,
    ) -> GlobalSettings:
        versioned = self._store.write(
            SETTINGS_KIND,
            SETTINGS_ID,
            updates,
            expected_revision=expected_revision,
            actor=actor,
        )
        return _settings_from_versioned(versioned)

    # ------------------------------------------------------------------- scan
    def _data_dir(self) -> Path | None:
        data_dir = getattr(self._store, "data_dir", None)
        return Path(data_dir) if data_dir is not None else None

    def _connections_dir(self) -> Path | None:
        data_dir = self._data_dir()
        if data_dir is None:
            return None
        return data_dir.joinpath(*_CONNECTIONS_SUBDIR)

    def agent_connection_refs(self) -> dict[str, str]:
        """Map ``agent_id -> connection_ref`` for reference/impact checks."""

        data_dir = self._data_dir()
        if data_dir is None:
            return {}
        root = data_dir.joinpath(*_AGENTS_SUBDIR)
        if not root.is_dir():
            return {}
        found: dict[str, str] = {}
        for path in sorted(root.glob("*.md")):
            try:
                versioned = self._store.read("agent", path.stem)
            except ConfigInvalid:
                continue
            ref = versioned.entity.get("connection_ref")
            if isinstance(ref, str) and ref:
                found[path.stem] = ref
        return found


__all__ = [
    "ConnectionRepository",
    "SETTINGS_KIND",
    "SETTINGS_ID",
    "SETTINGS_RELATIVE",
    "CONNECTION_KIND",
]
