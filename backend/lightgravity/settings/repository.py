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
        data=dict(data),
    )


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
    def validate_backend(
        self, backend: str, *, model: str | None, base_url: str | None
    ) -> None:
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
        if not registration.verified:
            raise SettingsConfigInvalid(
                f"backend {backend!r} is not verified in this environment; it cannot be "
                "saved as an executable connection",
                diagnostics=[
                    {
                        "code": "backend_unverified",
                        "location": f"{CONNECTION_KIND}.backend",
                        "detail": {"backend": backend},
                    }
                ],
            )
        if registration.endpoint_field == "base_url" and not base_url:
            raise SettingsConfigInvalid(
                "openai-compatible connection requires base_url",
                diagnostics=[
                    {"code": "endpoint_missing", "location": f"{CONNECTION_KIND}.base_url"}
                ],
            )
        if registration.requires_credential and not model:
            raise SettingsConfigInvalid(
                "connection requires an explicit model; refusing to guess a model id",
                diagnostics=[
                    {"code": "model_missing", "location": f"{CONNECTION_KIND}.model"}
                ],
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
        actor: str,
        request_id: str,
    ) -> Connection:
        self.validate_backend(backend, model=model, base_url=base_url)
        content: dict[str, Any] = {
            "title": title or connection_id,
            "enabled": enabled,
            "backend": backend,
            "model": model,
            "base_url": base_url,
            "credential_ref": credential_ref,
        }
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
        actor: str,
        request_id: str,
    ) -> GlobalSettings:
        content = {
            "default_coordinator_connection_ref": default_coordinator_connection_ref,
            "default_worker_connection_ref": default_worker_connection_ref,
            "default_reviewer_connection_ref": default_reviewer_connection_ref,
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
