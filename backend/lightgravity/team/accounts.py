"""Controlled team account fact source (LG-050).

Single authority: one JSON document (``<data>/team/accounts.json`` by default).
Writes are atomic (same-directory temp + ``fsync`` + ``os.replace``) under a
cross-process store lock and the file is forced to mode ``0600``. Passwords
are stored as PBKDF2-HMAC-SHA256 (per-account random salt) and never logged, echoed, returned
or written to any other file.  No database is introduced.

The LG-061 first-initialisation default is ``admin``/``admin123`` (a requested
product default, not a secret): :meth:`TeamAccounts.ensure_default_admin` seeds
that one admin only when the store is empty and never rewrites an existing
account, role or password.  There is no authentication fallback: login is only
the ordinary salted-hash verification below.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..store.atomic import atomic_write_text
from ..store.locking import LockManager

#: Document schema id for the accounts fact source.
TEAM_SCHEMA = "lightgravity.team/v1"
#: Only this KDF is accepted; anything else is refused, never guessed at.
PASSWORD_ALGO = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16
_DKLEN = 32
VALID_ROLES = frozenset({"admin", "member"})
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: LG-061 requested first-initialisation default.  This is a documented product
#: default, not a stored secret: it only ever enters the store through
#: :func:`hash_password` and never overwrites an existing account.
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"

#: A fixed dummy record used to equalise timing for unknown usernames.  It is
#: generated lazily so it never depends on a secret.
_DUMMY: dict[str, Any] | None = None


class TeamAccountsError(ValueError):
    """Raised for an invalid account operation (unknown role, bad file shape)."""


class TeamAccountsConflictError(TeamAccountsError):
    """Raised when an ``expected_revision`` no longer matches the store.

    A concurrent administrator changed the account first; the caller must
    re-read and retry rather than silently overwrite the newer state.
    """


class TeamAccountsLastAdminError(TeamAccountsError):
    """Raised when an operation would leave the store with no active admin.

    ``enabled`` administrators only; a member or a disabled admin does not
    count.  The guard is evaluated under the same store lock as the write, so
    two concurrent demotions/disables cannot both observe "one left".
    """


@dataclass(frozen=True, slots=True)
class Account:
    """One public account record (never carries the password in cleartext)."""

    username: str
    role: str
    created_at: str
    password: dict[str, Any]
    #: LG-062 additive fields.  ``enabled`` defaults to ``True`` and the
    #: revisions default to ``0`` so a pre-1.15 account loads compatibly.
    enabled: bool = True
    #: Monotonic optimistic-concurrency revision (bumped on any write).
    revision: int = 0
    #: Persistent credential/auth revision.  A session records the value it was
    #: minted under; any credential or authorization change bumps it so the
    #: target's existing sessions (and their SSE streams) fail fresh-state
    #: checks instead of trusting a cached role.
    session_version: int = 0


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=_DKLEN
    )


def hash_password(
    password: str,
    *,
    iterations: int = PBKDF2_ITERATIONS,
    salt: bytes | None = None,
) -> dict[str, Any]:
    """Return the persisted password record for ``password`` (no cleartext)."""

    if not isinstance(password, str) or not password:
        raise TeamAccountsError("password must be a non-empty string")
    if iterations <= 0:
        raise TeamAccountsError("iterations must be positive")
    used_salt = salt if salt is not None else secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, used_salt, iterations)
    return {
        "algo": PASSWORD_ALGO,
        "iterations": iterations,
        "salt": _b64(used_salt),
        "hash": _b64(digest),
    }


def verify_password(password: str, record: Mapping[str, Any]) -> bool:
    """Constant-time verification; unknown algorithms/malformed records fail."""

    if not isinstance(password, str) or not password:
        return False
    if not isinstance(record, Mapping):
        return False
    if record.get("algo") != PASSWORD_ALGO:
        return False
    iterations = record.get("iterations")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations <= 0:
        return False
    salt_raw = record.get("salt")
    hash_raw = record.get("hash")
    if not isinstance(salt_raw, str) or not isinstance(hash_raw, str):
        return False
    try:
        salt = _unb64(salt_raw)
        expected = _unb64(hash_raw)
    except (ValueError, TypeError):
        return False
    if not salt or not expected:
        return False
    actual = _derive(password, salt, iterations)
    return hmac.compare_digest(actual, expected)


def _dummy_record() -> dict[str, Any]:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("lg-dummy-password-not-a-real-credential")
    return _DUMMY


def _validate_username(username: Any) -> str:
    if not isinstance(username, str) or not _USERNAME_RE.match(username):
        raise TeamAccountsError(
            "username must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
        )
    return username


class TeamAccounts:
    """File-backed account store with atomic, 0600, locked writes."""

    def __init__(self, path: Path | str) -> None:
        # Canonicalize once so relative paths and symlink aliases refer to the
        # same document and stable sibling lock, including after atomic replace.
        self._path = Path(path).resolve()
        self._lock = threading.RLock()
        self._file_locks = LockManager(self._path.parent)

    @contextmanager
    def _mutation(self) -> Iterator[None]:
        """Hold one transaction lock across read, validation and atomic replace.

        Lock the stable sidecar, never the account inode that os.replace swaps.
        The sidecar is deliberately retained after unlock to avoid split locks.
        """

        with self._lock:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self._file_locks.acquire(self._path.name):
                yield

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def from_settings(cls, settings: Any) -> "TeamAccounts":
        return cls(settings.team_accounts_path)

    # --------------------------------------------------------------- reading
    def exists(self) -> bool:
        return self._path.is_file()

    def _read_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"schema": TEAM_SCHEMA, "accounts": {}}
        try:
            text = self._path.read_text("utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file
            raise TeamAccountsError(f"cannot read accounts file: {exc}") from exc
        if not text.strip():
            return {"schema": TEAM_SCHEMA, "accounts": {}}
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise TeamAccountsError(f"accounts file is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise TeamAccountsError("accounts file must be a JSON object")
        schema = data.get("schema")
        if schema != TEAM_SCHEMA:
            raise TeamAccountsError(f"unsupported accounts schema {schema!r}")
        accounts = data.get("accounts")
        if not isinstance(accounts, dict):
            raise TeamAccountsError("accounts field must be a JSON object")
        return data

    @staticmethod
    def _read_revision(raw: Any, key: str) -> int:
        value = raw.get(key, 0) if isinstance(raw, dict) else 0
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TeamAccountsError(f"account field {key!r} must be a non-negative integer")
        return value

    def _account_from_raw(self, username: str, raw: Any) -> Account:
        if not isinstance(raw, dict):
            raise TeamAccountsError(f"account {username!r} must be an object")
        role = raw.get("role")
        if role not in VALID_ROLES:
            raise TeamAccountsError(f"account {username!r} has invalid role {role!r}")
        password = raw.get("password")
        if not isinstance(password, dict):
            raise TeamAccountsError(f"account {username!r} is missing a password record")
        algo = password.get("algo")
        if algo != PASSWORD_ALGO:
            # Unknown algorithms are refused, never downgraded or ignored.
            raise TeamAccountsError(
                f"account {username!r} uses unsupported password algo {algo!r}"
            )
        # LG-062 compatibility: an account written before 1.15 has no
        # ``enabled``/``revision``/``session_version`` fields.  Missing
        # ``enabled`` means enabled (no behaviour change for legacy accounts).
        enabled_raw = raw.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise TeamAccountsError(f"account {username!r} has non-boolean enabled")
        created_at = raw.get("created_at")
        return Account(
            username=username,
            role=str(role),
            created_at=str(created_at) if isinstance(created_at, str) else "",
            password=dict(password),
            enabled=enabled_raw,
            revision=self._read_revision(raw, "revision"),
            session_version=self._read_revision(raw, "session_version"),
        )

    def list_accounts(self) -> list[Account]:
        with self._lock:
            data = self._read_raw()
            accounts = data.get("accounts", {})
            return [
                self._account_from_raw(str(username), accounts[username])
                for username in sorted(accounts)
            ]

    def get(self, username: str) -> Account | None:
        with self._lock:
            data = self._read_raw()
            accounts = data.get("accounts", {})
            if username not in accounts:
                return None
            return self._account_from_raw(username, accounts[username])

    def authenticate(self, username: str, password: str) -> Account | None:
        """Verify credentials in (roughly) constant time.

        An unknown username still runs one PBKDF2 derivation against the fixed
        dummy record so the response timing does not reveal account existence.
        """

        account = self.get(username) if isinstance(username, str) else None
        record = account.password if account is not None else _dummy_record()
        verified = verify_password(password, record)
        if account is None or not verified:
            return None
        # A disabled account retains its identity and history but can no longer
        # obtain a session.  Run the hash check first so timing still does not
        # reveal the disabled state.
        if not account.enabled:
            return None
        return account

    @staticmethod
    def _is_active_admin(raw: Any) -> bool:
        if not isinstance(raw, dict):
            return False
        return raw.get("role") == "admin" and raw.get("enabled", True) is True

    def _active_admin_usernames(self, accounts: Mapping[str, Any]) -> list[str]:
        return [str(name) for name, raw in accounts.items() if self._is_active_admin(raw)]

    # --------------------------------------------------------------- writing
    def ensure_default_admin(
        self,
        *,
        username: str = DEFAULT_ADMIN_USERNAME,
        password: str = DEFAULT_ADMIN_PASSWORD,
    ) -> bool:
        """Seed the requested default admin only on a first/empty store.

        Returns ``True`` when a new admin was written and ``False`` when the
        store already holds at least one account.  An existing account, a
        changed password, the current role and any unknown fields are never
        modified; a restart therefore re-runs this safely without resetting
        anything.  The password is persisted only as a fresh salted hash.
        """

        username = _validate_username(username)
        record = hash_password(password)
        created_at = _now_iso()
        with self._mutation():
            data = self._read_raw()
            accounts = data.get("accounts", {})
            if not isinstance(accounts, dict):
                raise TeamAccountsError("accounts field must be a JSON object")
            if accounts:
                return False
            accounts[username] = {
                "username": username,
                "role": "admin",
                "password": record,
                "created_at": created_at,
                "enabled": True,
                "revision": 0,
                "session_version": 0,
            }
            self._write(data)
        return True

    def _change(
        self,
        username: str,
        *,
        expected_revision: int | None = None,
        role: str | None = None,
        enabled: bool | None = None,
        password: str | None = None,
    ) -> Account:
        """Apply one atomic account change under the store lock.

        Enforces, in this order: account existence, optional optimistic
        ``expected_revision``, the last-active-admin invariant, then the atomic
        write.  Role/``enabled``/password changes bump ``session_version`` so
        the target's existing sessions (and SSE streams) are invalidated.  A
        no-op change is a read-only success and does not bump revisions.
        """

        username = _validate_username(username)
        if role is not None and role not in VALID_ROLES:
            raise TeamAccountsError(f"role must be one of {sorted(VALID_ROLES)}")
        if enabled is not None and not isinstance(enabled, bool):
            raise TeamAccountsError("enabled must be a boolean")
        record = hash_password(password) if password is not None else None
        with self._mutation():
            data = self._read_raw()
            accounts = data.get("accounts", {})
            if not isinstance(accounts, dict) or username not in accounts:
                raise TeamAccountsError(f"account {username!r} does not exist")
            raw = accounts[username]
            account = self._account_from_raw(username, raw)
            if expected_revision is not None and account.revision != expected_revision:
                raise TeamAccountsConflictError(
                    f"account {username!r} changed since revision {expected_revision}"
                )
            new_role = account.role if role is None else role
            new_enabled = account.enabled if enabled is None else enabled
            credential_changed = record is not None
            authorization_changed = (
                new_role != account.role or new_enabled != account.enabled
            )
            if not credential_changed and not authorization_changed:
                return account
            if (
                account.role == "admin"
                and account.enabled
                and (new_role != "admin" or not new_enabled)
            ):
                remaining = [
                    name
                    for name in self._active_admin_usernames(accounts)
                    if name != username
                ]
                if not remaining:
                    raise TeamAccountsLastAdminError(
                        "cannot disable or demote the last active administrator"
                    )
            updated = dict(raw)
            updated["role"] = new_role
            updated["enabled"] = new_enabled
            updated["revision"] = account.revision + 1
            updated["session_version"] = account.session_version + 1
            if record is not None:
                updated["password"] = record
            accounts[username] = updated
            self._write(data)
            return self._account_from_raw(username, updated)

    def set_password(
        self,
        username: str,
        password: str,
        *,
        expected_revision: int | None = None,
    ) -> Account:
        """Replace one account's password hash, preserving everything else.

        Only the ``password`` sub-object is rewritten; role, ``created_at`` and
        any unknown account/top-level fields survive.  The auth revision is
        bumped so every existing session for the target is invalidated
        immediately on subsequent requests.  Raises
        :class:`TeamAccountsError` for an unknown or malformed account and
        :class:`TeamAccountsConflictError` for a stale ``expected_revision``.
        """

        return self._change(
            username, expected_revision=expected_revision, password=password
        )

    def set_enabled(
        self,
        username: str,
        enabled: bool,
        *,
        expected_revision: int | None = None,
    ) -> Account:
        """Enable/disable an account; refuses to disable the last active admin."""

        return self._change(
            username, expected_revision=expected_revision, enabled=enabled
        )

    def set_role(
        self,
        username: str,
        role: str,
        *,
        expected_revision: int | None = None,
    ) -> Account:
        """Change an account role; refuses to demote the last active admin."""

        return self._change(username, expected_revision=expected_revision, role=role)

    def update_account(
        self,
        username: str,
        *,
        role: str | None = None,
        enabled: bool | None = None,
        expected_revision: int | None = None,
    ) -> Account:
        """Apply role and/or enabled in one atomic write (one revision bump)."""

        return self._change(
            username, expected_revision=expected_revision, role=role, enabled=enabled
        )

    def add(self, username: str, password: str, role: str = "member") -> Account:
        """Add one account; refuse a duplicate username or invalid role."""

        username = _validate_username(username)
        if role not in VALID_ROLES:
            raise TeamAccountsError(f"role must be one of {sorted(VALID_ROLES)}")
        record = hash_password(password)
        created_at = _now_iso()
        with self._mutation():
            data = self._read_raw()
            accounts = data.setdefault("accounts", {})
            assert isinstance(accounts, dict)
            if username in accounts:
                raise TeamAccountsError(f"account {username!r} already exists")
            accounts[username] = {
                "username": username,
                "role": role,
                "password": record,
                "created_at": created_at,
                "enabled": True,
                "revision": 0,
                "session_version": 0,
            }
            self._write(data)
        return Account(
            username=username,
            role=role,
            created_at=created_at,
            password=record,
        )

    def _write(self, data: dict[str, Any]) -> None:
        # Preserve unknown top-level/account fields (docs/08 §4: unknown fields
        # survive a controlled write); only the schema is (re)asserted.
        document = dict(data)
        document["schema"] = TEAM_SCHEMA
        document.setdefault("accounts", {})
        text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self._path, text)
        try:
            os.chmod(self._path, 0o600)
            os.chmod(self._path.parent, 0o700)
        except OSError:  # pragma: no cover - best effort on exotic filesystems
            pass


__all__ = [
    "DEFAULT_ADMIN_PASSWORD",
    "DEFAULT_ADMIN_USERNAME",
    "PBKDF2_ITERATIONS",
    "TEAM_SCHEMA",
    "VALID_ROLES",
    "Account",
    "TeamAccounts",
    "TeamAccountsConflictError",
    "TeamAccountsError",
    "TeamAccountsLastAdminError",
    "hash_password",
    "verify_password",
]
