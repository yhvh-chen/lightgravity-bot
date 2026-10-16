"""Controlled team account fact source (LG-050).

Single authority: one JSON document (``<data>/team/accounts.json`` by default).
Writes are atomic (same-directory temp + ``fsync`` + ``os.replace``) under a
process lock and the file is forced to mode ``0600``.  Passwords are stored as
PBKDF2-HMAC-SHA256 (per-account random salt) and never logged, echoed, returned
or written to any other file.  No database is introduced.
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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..store.atomic import atomic_write_text

#: Document schema id for the accounts fact source.
TEAM_SCHEMA = "lightgravity.team/v1"
#: Only this KDF is accepted; anything else is refused, never guessed at.
PASSWORD_ALGO = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16
_DKLEN = 32
VALID_ROLES = frozenset({"admin", "member"})
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: A fixed dummy record used to equalise timing for unknown usernames.  It is
#: generated lazily so it never depends on a secret.
_DUMMY: dict[str, Any] | None = None


class TeamAccountsError(ValueError):
    """Raised for an invalid account operation (unknown role, bad file shape)."""


@dataclass(frozen=True, slots=True)
class Account:
    """One public account record (never carries the password in cleartext)."""

    username: str
    role: str
    created_at: str
    password: dict[str, Any]


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
        self._path = Path(path)
        self._lock = threading.RLock()

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
        created_at = raw.get("created_at")
        return Account(
            username=username,
            role=str(role),
            created_at=str(created_at) if isinstance(created_at, str) else "",
            password=dict(password),
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
        return account

    # --------------------------------------------------------------- writing
    def add(self, username: str, password: str, role: str = "member") -> Account:
        """Add one account; refuse a duplicate username or invalid role."""

        username = _validate_username(username)
        if role not in VALID_ROLES:
            raise TeamAccountsError(f"role must be one of {sorted(VALID_ROLES)}")
        record = hash_password(password)
        created_at = _now_iso()
        with self._lock:
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
            }
            self._write(data)
        return Account(
            username=username, role=role, created_at=created_at, password=record
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
    "PBKDF2_ITERATIONS",
    "TEAM_SCHEMA",
    "VALID_ROLES",
    "Account",
    "TeamAccounts",
    "TeamAccountsError",
    "hash_password",
    "verify_password",
]
