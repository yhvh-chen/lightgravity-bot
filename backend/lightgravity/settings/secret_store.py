"""Controlled secret store for first-version credentials (docs/07 §4, docs/08 §8.1).

Chosen first-version store: a dedicated, permission-restricted directory of
``<ref>.secret`` files plus an opaque ``metadata.json`` version map.  It lives
in ``LIGHTGRAVITY_SECRET_STORE`` (default ``./secrets``, gitignored, outside the
task/source tree in production).  This is a deliberately local, single-user
store; it does **not** claim encryption at rest - the protection is filesystem
permissions (directory ``0700``, files ``0600``) and the loopback-only API.

Guarantees:

* A value is only ever read through :meth:`FileSecretStore.get`, which returns a
  :class:`~lightgravity.adapter.credentials.Secret`; ``repr``/``str`` are
  redacted, so accidental logging cannot leak it.
* ``metadata.json`` stores only an opaque ``cred_<hex>`` version token per ref,
  never the value.  The token is what binds a test result to a credential
  version (docs/07 §5) without exposing key material.
* Writes are atomic (temp file with ``0600`` + ``os.replace``), guarded by an
  ``flock`` so concurrent writers cannot interleave.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from lightgravity.adapter.credentials import CredentialResolver, EnvCredentialResolver, Secret

from .errors import SecretStoreError, SettingsConfigInvalid
from .models import CredentialStatus

_REF_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_METADATA_FILE = "metadata.json"
_LOCK_FILE = ".lock"
_SECRET_SUFFIX = ".secret"

#: Directory/file modes enforced by the store (owner-only).
MODE_DIR = 0o700
MODE_FILE = 0o600

SOURCE_SECRET_STORE = "secret_store"
SOURCE_ENVIRONMENT = "environment"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FileSecretStore:
    """Owner-only, atomic, versioned credential store."""

    def __init__(self, directory: Path | str) -> None:
        self._dir = Path(directory)

    # ------------------------------------------------------------------ paths
    @property
    def directory(self) -> Path:
        return self._dir

    def _ensure_dir(self) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self._dir, MODE_DIR)
        except OSError as exc:
            raise SecretStoreError(
                f"cannot prepare secret store directory: {exc}", location=str(self._dir)
            ) from exc

    def _validate_ref(self, ref: str) -> str:
        if not isinstance(ref, str) or not _REF_RE.match(ref):
            raise SettingsConfigInvalid(
                f"credential_ref {ref!r} is not a valid resource slug",
                diagnostics=[
                    {"code": "credential_ref_invalid", "location": "credential_ref", "ref": ref}
                ],
            )
        return ref

    def _secret_path(self, ref: str) -> Path:
        return self._dir / f"{ref}{_SECRET_SUFFIX}"

    def _metadata_path(self) -> Path:
        return self._dir / _METADATA_FILE

    # ----------------------------------------------------------------- locks
    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._ensure_dir()
        lock_path = self._dir / _LOCK_FILE
        try:
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, MODE_FILE)
        except OSError as exc:
            raise SecretStoreError(
                f"cannot open secret store lock: {exc}", location=str(lock_path)
            ) from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    # ------------------------------------------------------------------ io
    def _atomic_write(self, path: Path, data: bytes) -> None:
        tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, MODE_FILE)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            os.chmod(path, MODE_FILE)
        except OSError as exc:
            raise SecretStoreError(
                f"cannot write secret store entry: {exc}", location=str(path)
            ) from exc
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def _read_metadata(self) -> dict[str, dict[str, str]]:
        path = self._metadata_path()
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            # A corrupt version map must not make stored secrets unusable; the
            # values remain resolvable, only their version token is unknown.
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, dict):
                version = value.get("version")
                updated = value.get("updated_at")
                result[key] = {
                    "version": version if isinstance(version, str) else "",
                    "updated_at": updated if isinstance(updated, str) else "",
                }
        return result

    def _write_metadata(self, metadata: Mapping[str, Mapping[str, str]]) -> None:
        payload = json.dumps(
            {key: dict(value) for key, value in metadata.items()}, sort_keys=True, indent=2
        )
        self._atomic_write(self._metadata_path(), (payload + "\n").encode("utf-8"))

    # ------------------------------------------------------------- public API
    def get(self, ref: str) -> Secret | None:
        """Return the secret for ``ref``, or ``None`` when unset."""

        if not isinstance(ref, str) or not _REF_RE.match(ref):
            return None
        path = self._secret_path(ref)
        if not path.is_file():
            return None
        try:
            value = path.read_text("utf-8")
        except OSError as exc:
            raise SecretStoreError(
                f"cannot read secret store entry: {exc}", location=str(path)
            ) from exc
        if not value.strip():
            return None
        return Secret(value)

    def put(self, ref: str, value: str) -> str:
        """Store ``value`` under ``ref`` and return a fresh opaque version token."""

        self._validate_ref(ref)
        if not isinstance(value, str) or not value.strip():
            raise SettingsConfigInvalid(
                "credential value must be a non-empty string; empty input never "
                "removes an existing secret",
                diagnostics=[
                    {"code": "credential_value_empty", "location": "credential.value"}
                ],
            )
        with self._locked():
            self._atomic_write(self._secret_path(ref), value.encode("utf-8"))
            version = f"cred_{uuid.uuid4().hex[:12]}"
            metadata = self._read_metadata()
            metadata[ref] = {"version": version, "updated_at": _now_iso()}
            self._write_metadata(metadata)
            return version

    def delete(self, ref: str) -> bool:
        """Remove ``ref``; return whether an entry existed."""

        self._validate_ref(ref)
        with self._locked():
            path = self._secret_path(ref)
            existed = path.is_file()
            if path.exists():
                try:
                    path.unlink()
                except OSError as exc:
                    raise SecretStoreError(
                        f"cannot remove secret store entry: {exc}", location=str(path)
                    ) from exc
            metadata = self._read_metadata()
            if ref in metadata:
                del metadata[ref]
                self._write_metadata(metadata)
            return existed

    def version(self, ref: str) -> str | None:
        """Return the opaque version token for ``ref`` (never the value)."""

        if not isinstance(ref, str) or not _REF_RE.match(ref):
            return None
        return self._read_metadata().get(ref, {}).get("version") or None

    def status(self, ref: str) -> CredentialStatus:
        secret = self.get(ref)
        if secret is None:
            return CredentialStatus(ref=ref, configured=False)
        return CredentialStatus(
            ref=ref,
            configured=True,
            source=SOURCE_SECRET_STORE,
            version=self.version(ref),
        )

    def list_refs(self) -> list[str]:
        self._ensure_dir()
        refs: set[str] = set(self._read_metadata().keys())
        for path in self._dir.glob(f"*{_SECRET_SUFFIX}"):
            refs.add(path.name[: -len(_SECRET_SUFFIX)])
        return sorted(ref for ref in refs if _REF_RE.match(ref))

    def check_permissions(self) -> list[str]:
        """Return human-readable permission issues (empty when owner-only)."""

        issues: list[str] = []
        if not self._dir.exists():
            return issues
        dir_mode = self._dir.stat().st_mode & 0o777
        if dir_mode != MODE_DIR:
            issues.append(f"secret store directory mode is {oct(dir_mode)}, expected 0o700")
        for path in sorted(self._dir.iterdir()):
            if not path.is_file():
                continue
            mode = path.stat().st_mode & 0o777
            if mode & 0o077:
                issues.append(f"{path.name} mode is {oct(mode)}, expected owner-only")
        return issues


class SecretStoreCredentialResolver:
    """Adapter ``CredentialResolver`` backed by the store, then the environment.

    Used by ``AntigravityExecutor`` (LG-006): the real value never leaves
    memory and the source is recorded for diagnostics without the value.
    """

    def __init__(
        self,
        store: FileSecretStore,
        *,
        env_resolver: CredentialResolver | None = None,
    ) -> None:
        self._store = store
        self._env = env_resolver if env_resolver is not None else EnvCredentialResolver()

    def resolve(self, credential_ref: str) -> Secret | None:
        secret = self._store.get(credential_ref)
        if secret is not None:
            return secret
        return self._env.resolve(credential_ref)

    def source(self, credential_ref: str) -> CredentialStatus:
        stored = self._store.status(credential_ref)
        if stored.configured:
            return stored
        env_secret = self._env.resolve(credential_ref)
        if env_secret is not None:
            return CredentialStatus(
                ref=credential_ref, configured=True, source=SOURCE_ENVIRONMENT, version=None
            )
        return CredentialStatus(ref=credential_ref, configured=False)


__all__ = [
    "FileSecretStore",
    "SecretStoreCredentialResolver",
    "MODE_DIR",
    "MODE_FILE",
    "SOURCE_SECRET_STORE",
    "SOURCE_ENVIRONMENT",
]
