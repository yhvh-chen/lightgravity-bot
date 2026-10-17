"""Connection/SETTINGS service: policy, credential lifecycle and pinning (LG-025).

This is the integration layer over :class:`ConnectionRepository` (Store) and
:class:`FileSecretStore`.  It owns the first-version rules from docs/07:

* default references only ever point at an existing, enabled, verified
  connection - no dangling or unverified executable default;
* disabling a connection that is a default requires clearing that default in the
  same operation, with compensation if the later write fails;
* a credential still referenced by a connection cannot be deleted;
* a resolved connection can be *pinned* to a revision + credential version so a
  later default/connection edit never hot-swaps active members;
* the public view never contains a secret value, only whether/where a ref
  resolves, and secrets are only read through ``Secret`` (redacted repr).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from lightgravity.adapter.credentials import CredentialResolver, EnvCredentialResolver, Secret
from lightgravity.adapter.provider_matrix import (
    credential_recipient_identity,
    effective_auth_mode,
)
from lightgravity.adapter.registry import ImplementationRegistry
from lightgravity.store import Store
from lightgravity.store.locking import connection_reference_lock

from .embedding import EmbeddingSettingsService
from .errors import ConnectionReferenceInvalid, SecretStoreError, SettingsConfigInvalid
from .models import (
    DEFAULT_BASE_URL,
    DEFAULT_EXECUTABLE_BACKEND,
    PREFERRED_MODEL,
    ROLE_COORDINATOR,
    ROLE_EXPLICIT,
    ROLE_REVIEWER,
    ROLE_WORKER,
    Connection,
    ConnectionReferences,
    CredentialStatus,
    GlobalSettings,
    PinnedConnection,
)
from .repository import ConnectionRepository
from .secret_store import FileSecretStore, SecretStoreCredentialResolver

_UNSET: Any = object()

VALID_CREDENTIAL_ACTIONS = ("keep", "set", "remove")


class _Compensation:
    """Ordered undo log for cross-file writes (docs/07 §6, docs/08 §9)."""

    def __init__(self) -> None:
        self._undo: list[tuple[str, Callable[[], Any]]] = []

    def add(self, label: str, undo: Callable[[], Any]) -> None:
        self._undo.append((label, undo))

    def rollback(self) -> list[str]:
        errors: list[str] = []
        for label, undo in reversed(self._undo):
            try:
                undo()
            except Exception as exc:  # noqa: BLE001 - report, never hide the original
                errors.append(f"{label}: {exc}")
        return errors


class ConnectionService:
    """Application service for connections, defaults and credentials."""

    def __init__(
        self,
        store: Store,
        *,
        secret_store: FileSecretStore,
        registry: ImplementationRegistry | None = None,
        env_resolver: CredentialResolver | None = None,
        allowed_model_roots: Sequence[Path | str] | None = None,
        test_diagnostics: Any | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._repo = ConnectionRepository(store, registry=registry)
        self._secrets = secret_store
        self._resolver = SecretStoreCredentialResolver(
            secret_store, env_resolver=env_resolver or EnvCredentialResolver()
        )
        root = getattr(store, "workspace_root", None)
        self._allowed_model_roots = tuple(
            Path(item)
            for item in (
                allowed_model_roots
                if allowed_model_roots is not None
                else ([root] if root is not None else [])
            )
        )
        # Read-only access to the existing saved-test diagnostics.  This never
        # writes a second Connection state; draft results are never recorded by
        # the tester and are filtered again defensively here.
        self._test_diagnostics = test_diagnostics
        self._embedding = EmbeddingSettingsService(
            self._repo, secret_store=self._secrets, env=env
        )

    # --------------------------------------------------------------- exposure
    @property
    def repository(self) -> ConnectionRepository:
        return self._repo

    @property
    def secret_store(self) -> FileSecretStore:
        return self._secrets

    @property
    def credential_resolver(self) -> CredentialResolver:
        """The resolver LG-006 should use for ``credential_ref`` lookups."""

        return self._resolver

    @property
    def embedding(self) -> EmbeddingSettingsService:
        """Independent Embedding purpose; never a chat/worker default."""

        return self._embedding

    # ------------------------------------------------------------- connections
    def list_connections(self) -> list[dict[str, Any]]:
        return [self._public_connection(item) for item in self._repo.list_connections()]

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        return self._public_connection(self._repo.read_connection(connection_id))

    def create_connection(
        self,
        connection_id: str,
        *,
        title: str | None = None,
        backend: str = DEFAULT_EXECUTABLE_BACKEND,
        model: str | None = None,
        base_url: str | None = None,
        credential_ref: str | None = None,
        credential_value: str | None = None,
        enabled: bool = True,
        auth_mode: Any = _UNSET,
        project: Any = _UNSET,
        location: Any = _UNSET,
        model_path: Any = _UNSET,
        litert_backend: Any = _UNSET,
        actor: str,
        request_id: str,
    ) -> dict[str, Any]:
        if backend == DEFAULT_EXECUTABLE_BACKEND:
            model = model or PREFERRED_MODEL
            base_url = base_url or DEFAULT_BASE_URL
        optional = {
            "auth_mode": auth_mode,
            "project": project,
            "location": location,
            "model_path": model_path,
            "litert_backend": litert_backend,
        }
        # Omitted optional fields stay absent on a new record (legacy-compatible
        # shape); explicitly supplied values, including null, are persisted.
        persisted_fields = {
            key: value for key, value in optional.items() if value is not _UNSET
        }
        validation_fields = {
            key: (None if value is _UNSET else value)
            for key, value in optional.items()
        }
        self._validate_connection_fields(
            backend=backend,
            model=model,
            base_url=base_url,
            credential_ref=credential_ref,
            **validation_fields,
        )
        compensation = _Compensation()
        try:
            if credential_ref and credential_value:
                previous = self._secrets.get(credential_ref)
                restore_ref: str = credential_ref

                def _undo_credential(
                    ref: str = restore_ref, prev: Secret | None = previous
                ) -> None:
                    self._restore_credential(ref, previous=prev)

                compensation.add("credential", _undo_credential)
                self._secrets.put(restore_ref, credential_value)
            connection = self._repo.create_connection(
                connection_id,
                title=title,
                backend=backend,
                model=model,
                base_url=base_url,
                credential_ref=credential_ref,
                enabled=enabled,
                **persisted_fields,
                actor=actor,
                request_id=request_id,
            )
        except Exception:
            errors = compensation.rollback()
            if errors:
                raise SecretStoreError(
                    "connection create failed and credential compensation failed: "
                    + "; ".join(errors)
                ) from None
            raise
        return self._public_connection(connection)

    def update_connection(
        self,
        connection_id: str,
        *,
        expected_revision: int,
        actor: str,
        title: str | None = None,
        enabled: bool | None = None,
        backend: Any = _UNSET,
        model: Any = _UNSET,
        base_url: Any = _UNSET,
        credential_ref: Any = _UNSET,
        credential_action: str = "keep",
        credential_value: str | None = None,
        clear_defaults: bool = False,
        auth_mode: Any = _UNSET,
        project: Any = _UNSET,
        location: Any = _UNSET,
        model_path: Any = _UNSET,
        litert_backend: Any = _UNSET,
    ) -> dict[str, Any]:
        if credential_action not in VALID_CREDENTIAL_ACTIONS:
            raise SettingsConfigInvalid(
                f"credential_action must be one of {', '.join(VALID_CREDENTIAL_ACTIONS)}",
                diagnostics=[
                    {"code": "credential_action_invalid", "location": "credential_action"}
                ],
            )
        current = self._repo.read_connection(connection_id)
        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if enabled is not None:
            updates["enabled"] = enabled
        if backend is not _UNSET:
            if not isinstance(backend, str) or not backend:
                raise SettingsConfigInvalid(
                    "backend must be a non-empty string when supplied",
                    diagnostics=[{"code": "backend_invalid", "location": "backend"}],
                )
            updates["backend"] = backend
        for key, value in (
            ("model", model),
            ("base_url", base_url),
            ("credential_ref", credential_ref),
            ("auth_mode", auth_mode),
            ("project", project),
            ("location", location),
            ("model_path", model_path),
            ("litert_backend", litert_backend),
        ):
            if value is not _UNSET:
                updates[key] = value

        if credential_action == "remove":
            updates["credential_ref"] = None
        elif credential_action == "keep" and credential_value:
            # A non-empty value is an explicit set; an empty/absent value keeps.
            credential_action = "set"
        if credential_action == "set":
            if not credential_value or not credential_value.strip():
                raise SettingsConfigInvalid(
                    "setting a credential requires a non-empty value; empty input "
                    "never removes the existing secret",
                    diagnostics=[
                        {"code": "credential_value_empty", "location": "credential.value"}
                    ],
                )
            target_ref = updates.get("credential_ref", current.credential_ref)
            if not isinstance(target_ref, str) or not target_ref:
                raise SettingsConfigInvalid(
                    "setting a credential requires a credential_ref",
                    diagnostics=[
                        {"code": "credential_ref_missing", "location": "credential_ref"}
                    ],
                )
            updates["credential_ref"] = target_ref

        final = {
            "backend": updates.get("backend", current.backend),
            "model": updates.get("model", current.model),
            "base_url": updates.get("base_url", current.base_url),
            "credential_ref": updates.get("credential_ref", current.credential_ref),
            "auth_mode": updates.get("auth_mode", current.auth_mode),
            "project": updates.get("project", current.project),
            "location": updates.get("location", current.location),
            "model_path": updates.get("model_path", current.model_path),
            "litert_backend": updates.get("litert_backend", current.litert_backend),
        }
        self._validate_connection_fields(**final)

        # Do not silently carry a stored key to a different provider/auth mode or
        # endpoint recipient.  The old secret file is never deleted here; it is
        # merely detached so no later test/execution can send it to a new target.
        old_identity = credential_recipient_identity(
            backend=current.backend,
            auth_mode=current.auth_mode,
            base_url=current.base_url,
            project=current.project,
            location=current.location,
            credential_ref=current.credential_ref,
        )
        new_identity = credential_recipient_identity(
            backend=final["backend"],
            auth_mode=final["auth_mode"],
            base_url=final["base_url"],
            project=final["project"],
            location=final["location"],
            credential_ref=final["credential_ref"],
        )
        if (
            old_identity != new_identity
            and credential_action == "keep"
            and not credential_value
            and final["credential_ref"]
        ):
            updates["credential_ref"] = None
            final["credential_ref"] = None
        self._validate_connection_fields(**final)

        refs = self.references_to(connection_id)
        disabling = enabled is False and current.enabled
        if disabling and refs.default_roles and not clear_defaults:
            raise ConnectionReferenceInvalid(
                f"connection {connection_id!r} is a default connection; disable it "
                "together with clearing the default reference",
                kind="connection",
                ref=connection_id,
                detail="disable_default_referenced",
                references=refs.to_dict(),
            )

        compensation = _Compensation()
        try:
            if credential_action == "set":
                credential_target: str = str(updates["credential_ref"])
                previous = self._secrets.get(credential_target)

                def _undo_credential(
                    ref: str = credential_target, prev: Secret | None = previous
                ) -> None:
                    self._restore_credential(ref, previous=prev)

                compensation.add("credential", _undo_credential)
                self._secrets.put(credential_target, str(credential_value))
            if disabling and refs.default_roles and clear_defaults:
                old_settings = self._repo.read_settings()
                cleared = dict(old_settings.data)
                for role in refs.default_roles:
                    key = (
                        "default_worker_connection_ref"
                        if role == ROLE_WORKER
                        else "default_coordinator_connection_ref"
                    )
                    cleared[key] = None
                written = self._write_settings_content(
                    cleared, expected_revision=old_settings.revision, actor=actor
                )

                def _undo_settings(
                    old: GlobalSettings = old_settings, rev: int = written.revision
                ) -> None:
                    self._repo.write_settings(
                        {
                            "default_coordinator_connection_ref": (
                                old.default_coordinator_connection_ref
                            ),
                            "default_worker_connection_ref": (
                                old.default_worker_connection_ref
                            ),
                        },
                        expected_revision=rev,
                        actor=actor,
                    )

                compensation.add("settings", _undo_settings)
            connection = self._repo.write_connection(
                connection_id, updates, expected_revision=expected_revision, actor=actor
            )
        except Exception:
            errors = compensation.rollback()
            if errors:
                raise SecretStoreError(
                    "connection update failed and rollback was incomplete: "
                    + "; ".join(errors)
                ) from None
            raise
        return self._public_connection(connection)

    def delete_connection(
        self,
        connection_id: str,
        *,
        expected_revision: int,
        actor: str,
    ) -> dict[str, Any]:
        """Delete a Connection without touching its (possibly shared) secret.

        The shared reference lock serializes this guard/unlink with controlled
        Settings and Agent binding writers, before taking the entity lock.
        References are never rewritten; a referenced connection is refused.
        """
        with connection_reference_lock(self._repo.store):
            self._repo.delete_connection(
                connection_id,
                expected_revision=expected_revision,
                actor=actor,
                guard=lambda: self._guard_connection_delete(connection_id),
            )
            return {"deleted": True, "id": connection_id}

    def _guard_connection_delete(self, connection_id: str) -> None:
        refs = self.references_to(connection_id)
        if refs.referenced:
            raise ConnectionReferenceInvalid(
                f"connection {connection_id!r} is still referenced and cannot be deleted",
                kind="connection",
                ref=connection_id,
                detail="connection_still_referenced",
                references=refs.to_dict(),
            )

    def references_to(self, connection_id: str) -> ConnectionReferences:
        settings = self._repo.read_settings()
        roles: list[str] = []
        if settings.default_coordinator_connection_ref == connection_id:
            roles.append(ROLE_COORDINATOR)
        if settings.default_worker_connection_ref == connection_id:
            roles.append(ROLE_WORKER)
        if settings.default_reviewer_connection_ref == connection_id:
            roles.append(ROLE_REVIEWER)
        agents = tuple(
            sorted(
                agent_id
                for agent_id, ref in self._repo.agent_connection_refs().items()
                if ref == connection_id
            )
        )
        return ConnectionReferences(
            connection_id=connection_id, default_roles=tuple(roles), agent_refs=agents
        )

    # -------------------------------------------------------------- settings
    def get_settings(self) -> dict[str, Any]:
        settings = self._repo.read_settings()
        return {
            **settings.to_dict(),
            "defaults": {
                ROLE_COORDINATOR: self._describe_default(
                    settings.default_coordinator_connection_ref
                ),
                ROLE_WORKER: self._describe_default(settings.default_worker_connection_ref),
                ROLE_REVIEWER: self._describe_default(
                    settings.default_reviewer_connection_ref
                ),
            },
            # LG-117 additive read-only view; secrets are never included.
            "embedding": self._embedding.view(settings),
        }

    def update_settings(
        self,
        *,
        expected_revision: int | None,
        actor: str,
        default_coordinator_connection_ref: Any = _UNSET,
        default_worker_connection_ref: Any = _UNSET,
        default_reviewer_connection_ref: Any = _UNSET,
        decentralized_claim_enabled: Any = _UNSET,
        collab_requests_enabled: Any = _UNSET,
        claim_lease_seconds: Any = _UNSET,
    ) -> dict[str, Any]:
        with connection_reference_lock(self._repo.store):
            current = self._repo.read_settings()
            coordinator = (
                current.default_coordinator_connection_ref
                if default_coordinator_connection_ref is _UNSET
                else default_coordinator_connection_ref
            )
            worker = (
                current.default_worker_connection_ref
                if default_worker_connection_ref is _UNSET
                else default_worker_connection_ref
            )
            reviewer = (
                current.default_reviewer_connection_ref
                if default_reviewer_connection_ref is _UNSET
                else default_reviewer_connection_ref
            )
            claim_enabled = (
                current.decentralized_claim_enabled
                if decentralized_claim_enabled is _UNSET
                else decentralized_claim_enabled
            )
            collab_enabled = (
                current.collab_requests_enabled
                if collab_requests_enabled is _UNSET
                else collab_requests_enabled
            )
            lease_seconds = (
                current.claim_lease_seconds
                if claim_lease_seconds is _UNSET
                else claim_lease_seconds
            )
            self._validate_default_ref(coordinator, role=ROLE_COORDINATOR)
            self._validate_default_ref(worker, role=ROLE_WORKER)
            self._validate_default_ref(reviewer, role=ROLE_REVIEWER)
            self._validate_claim_switches(
                decentralized_claim_enabled=claim_enabled,
                collab_requests_enabled=collab_enabled,
                claim_lease_seconds=lease_seconds,
            )
            content = {
                "default_coordinator_connection_ref": coordinator,
                "default_worker_connection_ref": worker,
                "default_reviewer_connection_ref": reviewer,
                "decentralized_claim_enabled": claim_enabled,
                "collab_requests_enabled": collab_enabled,
                "claim_lease_seconds": lease_seconds,
            }
            if current.exists:
                if expected_revision is None:
                    raise SettingsConfigInvalid(
                        "expected_revision is required to update existing settings",
                        diagnostics=[
                            {"code": "expected_revision_missing", "location": "expected_revision"}
                        ],
                    )
                written = self._repo.write_settings(
                    content, expected_revision=expected_revision, actor=actor
                )
            else:
                if expected_revision not in (None, 0):
                    raise SettingsConfigInvalid(
                        "settings do not exist yet; expected_revision must be 0",
                        diagnostics=[
                            {"code": "expected_revision_invalid", "location": "expected_revision"}
                        ],
                    )
                written = self._repo.create_settings(
                    default_coordinator_connection_ref=coordinator,
                    default_worker_connection_ref=worker,
                    default_reviewer_connection_ref=reviewer,
                    decentralized_claim_enabled=claim_enabled,
                    collab_requests_enabled=collab_enabled,
                    claim_lease_seconds=lease_seconds,
                    actor=actor,
                    request_id="settings-init",
                )
            return {
                **written.to_dict(),
                "defaults": {
                    ROLE_COORDINATOR: self._describe_default(coordinator),
                    ROLE_WORKER: self._describe_default(worker),
                    ROLE_REVIEWER: self._describe_default(reviewer),
                },
            }

    def _validate_claim_switches(
        self,
        *,
        decentralized_claim_enabled: Any,
        collab_requests_enabled: Any,
        claim_lease_seconds: Any,
    ) -> None:
        """Validate the additive decentralized switches (docs/08 §6.5).

        They are non-secret booleans/positives that only ever *open* the opt-in
        path, so an invalid value is a config error rather than a silent enable.
        """

        for field, value in (
            ("decentralized_claim_enabled", decentralized_claim_enabled),
            ("collab_requests_enabled", collab_requests_enabled),
        ):
            if not isinstance(value, bool):
                raise SettingsConfigInvalid(
                    f"{field} must be a boolean",
                    diagnostics=[{"code": "switch_invalid", "location": field}],
                )
        if (
            isinstance(claim_lease_seconds, bool)
            or not isinstance(claim_lease_seconds, int)
            or claim_lease_seconds <= 0
        ):
            raise SettingsConfigInvalid(
                "claim_lease_seconds must be a positive integer",
                diagnostics=[
                    {"code": "lease_seconds_invalid", "location": "claim_lease_seconds"}
                ],
            )

    def _write_settings_content(
        self, content: dict[str, Any], *, expected_revision: int, actor: str
    ) -> GlobalSettings:
        updates = {
            "default_coordinator_connection_ref": content.get(
                "default_coordinator_connection_ref"
            ),
            "default_worker_connection_ref": content.get("default_worker_connection_ref"),
            "default_reviewer_connection_ref": content.get(
                "default_reviewer_connection_ref"
            ),
            # Preserve the additive decentralized switches (LG-031) so a
            # connection-default write does not silently reset the opt-in state.
            "decentralized_claim_enabled": bool(
                content.get("decentralized_claim_enabled", False)
            ),
            "collab_requests_enabled": bool(content.get("collab_requests_enabled", False)),
            "claim_lease_seconds": content.get("claim_lease_seconds", 300) or 300,
        }
        return self._repo.write_settings(
            updates, expected_revision=expected_revision, actor=actor
        )

    def _validate_default_ref(self, ref: Any, *, role: str) -> None:
        if ref is None:
            return
        if not isinstance(ref, str) or not ref:
            raise SettingsConfigInvalid(
                "default connection reference must be null or a non-empty id",
                diagnostics=[
                    {
                        "code": "default_ref_invalid",
                        "location": f"{role}_default",
                    }
                ],
            )
        connection = self._repo.get_connection_or_none(ref)
        if connection is None:
            raise ConnectionReferenceInvalid(
                f"default {role} connection {ref!r} does not exist",
                kind="connection",
                ref=ref,
                detail=f"{role}_default_missing",
            )
        if not connection.enabled:
            raise ConnectionReferenceInvalid(
                f"default {role} connection {ref!r} is disabled",
                kind="connection",
                ref=ref,
                detail=f"{role}_default_disabled",
            )
        capabilities = self._repo.connection_capabilities(connection)
        if not capabilities or capabilities.get("executable") is not True:
            raise ConnectionReferenceInvalid(
                f"default {role} connection {ref!r} is configurable/testable but "
                f"not executable in this build ({connection.backend!r} at "
                f"{connection.base_url or 'fixed vendor endpoint'!r})",
                kind="connection",
                ref=ref,
                detail=f"{role}_default_unverified",
            )

    def _describe_default(self, ref: str | None) -> dict[str, Any] | None:
        if ref is None:
            return None
        connection = self._repo.get_connection_or_none(ref)
        if connection is None:
            return {"ref": ref, "resolved": False}
        summary = connection.to_dict()
        summary["resolved"] = True
        summary["credential"] = self.credential_status(connection.credential_ref).to_dict()
        summary["capabilities"] = self._repo.connection_capabilities(connection)
        summary["last_test"] = self._last_test_summary(connection.id)
        return summary

    # ------------------------------------------------------------ credentials
    def credential_status(self, ref: str | None) -> CredentialStatus:
        if not ref:
            return CredentialStatus(ref="", configured=False)
        return self._resolver.source(ref)

    def set_credential(self, ref: str, value: str) -> CredentialStatus:
        self._secrets.put(ref, value)
        return self.credential_status(ref)

    def remove_credential(self, ref: str) -> CredentialStatus:
        referencing = [
            connection.id
            for connection in self._repo.list_connections()
            if connection.credential_ref == ref
        ]
        if referencing:
            raise ConnectionReferenceInvalid(
                f"credential_ref {ref!r} is still referenced by connections and cannot "
                "be removed",
                kind="credential",
                ref=ref,
                detail="credential_still_referenced",
                references={"connections": sorted(referencing)},
            )
        self._secrets.delete(ref)
        return self.credential_status(ref)

    def _restore_credential(self, ref: str, *, previous: Secret | None = None) -> None:
        """Undo helper: restore ``previous`` or remove a freshly-written secret."""

        if previous is None:
            self._secrets.delete(ref)
        else:
            self._secrets.put(ref, previous.reveal())

    # ----------------------------------------------------------------- pinning
    def pin_connection(
        self, connection_id: str, *, role: str = ROLE_EXPLICIT
    ) -> PinnedConnection:
        connection = self._repo.read_connection(connection_id)
        credential = self.credential_status(connection.credential_ref)
        return self._pin(connection, role=role, credential=credential)

    def resolve_default(self, role: str) -> PinnedConnection | None:
        settings = self._repo.read_settings()
        if role == ROLE_COORDINATOR:
            ref = settings.default_coordinator_connection_ref
        elif role == ROLE_WORKER:
            ref = settings.default_worker_connection_ref
        elif role == ROLE_REVIEWER:
            ref = settings.default_reviewer_connection_ref
        else:
            raise SettingsConfigInvalid(
                f"unknown default role {role!r}", diagnostics=[{"code": "role_invalid"}]
            )
        if ref is None:
            return None
        return self.pin_connection(ref, role=role)

    def pinned_is_current(self, pinned: PinnedConnection) -> bool:
        connection = self._repo.get_connection_or_none(pinned.connection_id)
        if connection is None:
            return False
        credential = self.credential_status(connection.credential_ref)
        return pinned.still_current(connection, credential.version)

    def _pin(
        self, connection: Connection, *, role: str, credential: CredentialStatus
    ) -> PinnedConnection:
        payload = json.dumps(
            {
                "connection": connection.content_hash,
                "backend": connection.backend,
                "model": connection.model,
                "base_url": connection.base_url,
                "credential_ref": connection.credential_ref,
                "auth_mode": connection.auth_mode,
                "project": connection.project,
                "location": connection.location,
                "model_path": connection.model_path,
                "litert_backend": connection.litert_backend,
                "credential_version": credential.version,
            },
            sort_keys=True,
        ).encode("utf-8")
        config_hash = hashlib.sha256(payload).hexdigest()
        return PinnedConnection(
            connection_id=connection.id,
            role=role,
            revision=connection.revision,
            content_hash=connection.content_hash,
            backend=connection.backend,
            model=connection.model,
            base_url=connection.base_url,
            credential_ref=connection.credential_ref,
            credential_version=credential.version,
            config_hash=config_hash,
        )

    # ------------------------------------------------------------------ views
    def _public_connection(self, connection: Connection) -> dict[str, Any]:
        payload = connection.to_dict()
        payload["credential"] = self.credential_status(connection.credential_ref).to_dict()
        refs = self.references_to(connection.id)
        payload["references"] = refs.to_dict()
        payload["capabilities"] = self._repo.connection_capabilities(connection)
        payload["last_test"] = self._last_test_summary(connection.id)
        return payload

    def _last_test_summary(self, connection_id: str) -> dict[str, Any] | None:
        """Read the latest saved-test safe summary; never a draft result.

        The diagnostic log is the only authority.  No second Connection state is
        persisted or derived beyond this read-only projection.
        """

        if self._test_diagnostics is None:
            return None
        try:
            latest = self._test_diagnostics.latest(connection_id)
        except Exception:  # noqa: BLE001 - a broken diagnostic must not hide the connection
            return None
        if not isinstance(latest, dict) or latest.get("draft") is True:
            return None
        overall = latest.get("overall")
        finished_at = latest.get("finished_at")
        if not isinstance(overall, str) or not isinstance(finished_at, str):
            return None
        summary: dict[str, Any] = {
            "overall": overall,
            "finished_at": finished_at,
        }
        test_id = latest.get("test_id")
        if isinstance(test_id, str) and test_id:
            summary["test_id"] = test_id
        revision = latest.get("connection_revision")
        summary["connection_revision"] = (
            revision if isinstance(revision, int) and not isinstance(revision, bool) else None
        )
        credential_version = latest.get("credential_version")
        summary["credential_version"] = (
            credential_version if isinstance(credential_version, str) else None
        )
        return summary

    # --------------------------------------------------------- provider policy
    def validate_connection_spec(
        self,
        *,
        backend: str,
        model: str | None,
        base_url: str | None = None,
        auth_mode: str | None = None,
        project: str | None = None,
        location: str | None = None,
        model_path: str | None = None,
        litert_backend: str | None = None,
        credential_ref: str | None = None,
    ) -> str:
        """Validate a complete provider spec (saved or draft); return auth mode.

        The draft endpoint uses this exact path, so an unsaved provider is held
        to the same matrix as a saved one.  No secret value is accepted here.
        """

        self._validate_connection_fields(
            backend=backend,
            model=model,
            base_url=base_url,
            credential_ref=credential_ref,
            auth_mode=auth_mode,
            project=project,
            location=location,
            model_path=model_path,
            litert_backend=litert_backend,
        )
        return effective_auth_mode(
            backend,
            auth_mode,
            project=project,
            location=location,
            credential_ref=credential_ref,
        )

    def _validate_connection_fields(
        self,
        *,
        backend: str,
        model: str | None,
        base_url: str | None,
        credential_ref: str | None,
        auth_mode: str | None = None,
        project: str | None = None,
        location: str | None = None,
        model_path: str | None = None,
        litert_backend: str | None = None,
    ) -> None:
        self._repo.validate_backend(
            backend,
            model=model,
            base_url=base_url,
            auth_mode=auth_mode,
            project=project,
            location=location,
            model_path=model_path,
            litert_backend=litert_backend,
            credential_ref=credential_ref,
        )
        if backend == "litert":
            self._validate_model_path(model_path)

    def _validate_model_path(self, model_path: str | None) -> None:
        """Keep LiteRT model paths inside configured roots without reading them.

        The existing Store path policy is the lexical/symlink containment choke
        point.  This validation only resolves/stats the path; it never reads file
        contents and never installs/downloads anything.
        """

        if not model_path:
            return
        if not self._allowed_model_roots:
            raise SettingsConfigInvalid(
                "no configured LiteRT model root is available",
                diagnostics=[
                    {"code": "model_root_unavailable", "location": "connection.model_path"}
                ],
            )
        candidate = Path(model_path)
        allowed = False
        for root in self._allowed_model_roots:
            root_abs = Path(str(root)).expanduser().absolute()
            try:
                resolved = (
                    Path(model_path).expanduser().absolute()
                    if candidate.is_absolute()
                    else (root_abs / candidate).absolute()
                )
                resolved = resolved.resolve(strict=False)
                real_root = root_abs.resolve(strict=False)
                resolved.relative_to(real_root)
            except (OSError, ValueError):
                continue
            allowed = True
            break
        if not allowed:
            raise SettingsConfigInvalid(
                "LiteRT model_path must resolve inside an allowed model root",
                diagnostics=[
                    {"code": "model_path_outside_roots", "location": "connection.model_path"}
                ],
            )


__all__ = ["ConnectionService"]
