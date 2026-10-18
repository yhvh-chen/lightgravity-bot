"""Team session registry with an optional hash-only persistent store (LG-210).

A session id is an opaque random token that only ever travels to the client in
the HttpOnly cookie.  When a ``store_path`` is configured the registry keeps
the authoritative table in one controlled JSON document under the team data
root and writes **only** a SHA-256 hash of each token.  The plaintext bearer
value is never written to disk, logged or returned by any endpoint beyond the
cookie itself.

The persisted store is a single fact source for live sessions:

* writes take the existing same-directory cross-process ``flock`` and use the
  shared atomic replace helper, so two processes cannot lose each other's
  create/revoke updates;
* every resolve re-reads the store, so a logout or revocation in another
  process is visible to the next request and to the existing SSE re-check;
* an unreadable/malformed store fails closed (no session resolves, a fresh
  login starts a new store) instead of being treated as a wildcard;
* account ``session_version``/enabled state is still revalidated by
  :class:`~lightgravity.team.service.TeamAuthService` on every resolve.

Without ``store_path`` the registry keeps the original in-process table, which
unit tests and embedders can still use without touching a data root.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..store.atomic import atomic_write_text
from ..store.locking import LockManager

#: Cookie name for the opaque session id.
COOKIE_NAME = "lg_session"
#: Random byte count for the session id (>= 256 bits of entropy).
_SESSION_BYTES = 32
#: Persisted document schema id.
SESSION_SCHEMA = "lightgravity.team.sessions/v1"
_VALID_ROLES = frozenset({"admin", "member"})


class SessionStoreError(RuntimeError):
    """The persisted session store is missing, unreadable or malformed."""


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    username: str
    role: str
    expires_at: float
    #: LG-062: the account ``session_version`` this session was minted under.
    #: The service compares it against the store on every resolve so a
    #: password/role/enabled change invalidates older sessions immediately.
    session_version: int = 0


def _token_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _is_hash_key(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _decode_store(text: str) -> dict[str, dict[str, Any]]:
    """Validate a persisted document; any malformed part rejects the whole store."""

    if not text.strip():
        raise SessionStoreError("session store is empty")
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise SessionStoreError(f"session store is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise SessionStoreError("session store must be a JSON object")
    if document.get("schema") != SESSION_SCHEMA:
        raise SessionStoreError("unsupported session store schema")
    raw_sessions = document.get("sessions")
    if not isinstance(raw_sessions, dict):
        raise SessionStoreError("session store 'sessions' field must be an object")

    sessions: dict[str, dict[str, Any]] = {}
    for key, raw in raw_sessions.items():
        if not _is_hash_key(key) or not isinstance(raw, dict):
            raise SessionStoreError("session store contains an invalid record")
        username = raw.get("username")
        role = raw.get("role")
        expires_at = raw.get("expires_at")
        session_version = raw.get("session_version", 0)
        if not isinstance(username, str) or not username:
            raise SessionStoreError("session record has an invalid username")
        if role not in _VALID_ROLES:
            raise SessionStoreError("session record has an invalid role")
        if (
            isinstance(expires_at, bool)
            or not isinstance(expires_at, (int, float))
            or not math.isfinite(expires_at)
        ):
            raise SessionStoreError("session record has an invalid expiry")
        if (
            isinstance(session_version, bool)
            or not isinstance(session_version, int)
            or session_version < 0
        ):
            raise SessionStoreError("session record has an invalid session_version")
        sessions[key] = {
            "username": username,
            "role": role,
            "expires_at": float(expires_at),
            "session_version": session_version,
        }
    return sessions


def _encode_store(sessions: dict[str, dict[str, Any]]) -> str:
    document = {"schema": SESSION_SCHEMA, "sessions": sessions}
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


class SessionRegistry:
    """Thread/process-safe ``session_id -> Session`` table with absolute TTL.

    ``store_path=None`` keeps the original memory-only behaviour.  A configured
    path holds hashes only (never the token) and is protected by a sibling
    cross-process lock plus atomic replacement.
    """

    def __init__(
        self,
        ttl_seconds: int,
        *,
        clock: Callable[[], float] = time.time,
        store_path: Path | str | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = int(ttl_seconds)
        self._clock = clock
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self._path: Path | None = None
        self._file_locks: LockManager | None = None
        if store_path is not None:
            raw = Path(store_path)
            # Resolve the parent but keep the final component: an existing
            # symlink at the store name is detected and rejected on read
            # instead of silently following a link outside the controlled root.
            self._path = raw.parent.resolve() / raw.name
            self._file_locks = LockManager(self._path.parent)

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    @property
    def path(self) -> Path | None:
        return self._path

    # ------------------------------------------------------------ persistence
    @contextmanager
    def _mutation(self) -> Iterator[None]:
        """Serialize one read/modify/atomic-replace transaction."""

        assert self._path is not None and self._file_locks is not None
        with self._lock:
            try:
                self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            except OSError as exc:
                raise SessionStoreError("cannot create session store directory") from exc
            # Lock the stable sidecar, never the store inode os.replace swaps.
            with self._file_locks.acquire(self._path.name):
                yield

    def _load_persisted(self) -> dict[str, dict[str, Any]]:
        assert self._path is not None
        if self._path.is_symlink():
            raise SessionStoreError("session store must not be a symlink")
        try:
            if not self._path.exists():
                return {}
            if not self._path.is_file():
                raise SessionStoreError("session store is not a regular file")
            text = self._path.read_text("utf-8")
        except OSError as exc:
            raise SessionStoreError("cannot read session store") from exc
        except UnicodeError as exc:
            raise SessionStoreError("session store is not UTF-8") from exc
        return _decode_store(text)

    def _write_persisted(self, sessions: dict[str, dict[str, Any]]) -> None:
        assert self._path is not None
        try:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Atomic replace does not follow a symlink at the destination; it
            # replaces the link itself, so a malicious link is never written
            # through to its target.
            atomic_write_text(self._path, _encode_store(sessions))
            self._path.chmod(0o600)
            self._path.parent.chmod(0o700)
        except OSError as exc:
            raise SessionStoreError("cannot write session store") from exc

    @staticmethod
    def _prune(
        sessions: dict[str, dict[str, Any]], now: float
    ) -> dict[str, dict[str, Any]]:
        return {
            key: record
            for key, record in sessions.items()
            if record["expires_at"] > now
        }

    @staticmethod
    def _from_record(session_id: str, record: dict[str, Any]) -> Session:
        return Session(
            session_id=session_id,
            username=str(record["username"]),
            role=str(record["role"]),
            expires_at=float(record["expires_at"]),
            session_version=int(record["session_version"]),
        )

    # --------------------------------------------------------------- lifecycle
    def create(self, username: str, role: str, session_version: int = 0) -> Session:
        session_id = secrets.token_urlsafe(_SESSION_BYTES)
        expires_at = self._clock() + self._ttl
        session = Session(
            session_id=session_id,
            username=username,
            role=role,
            expires_at=expires_at,
            session_version=session_version,
        )
        if self._path is None:
            with self._lock:
                self._sessions[session_id] = session
            return session

        key = _token_hash(session_id)
        with self._mutation():
            try:
                records = self._load_persisted()
            except SessionStoreError:
                # A corrupt store can never satisfy an old cookie.  A fresh
                # successful login is the reauthentication path and starts a
                # clean table, rather than accepting or widening anything.
                records = {}
            records = self._prune(records, self._clock())
            records[key] = {
                "username": username,
                "role": role,
                "expires_at": expires_at,
                "session_version": session_version,
            }
            self._write_persisted(records)
        return session

    def resolve(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        now = self._clock()
        if self._path is None:
            with self._lock:
                session = self._sessions.get(session_id)
                if session is None:
                    return None
                if session.expires_at <= now:
                    self._sessions.pop(session_id, None)
                    return None
                return session

        key = _token_hash(session_id)
        with self._mutation():
            try:
                records = self._load_persisted()
            except SessionStoreError:
                # Fail closed: a corrupt/unreadable store requires a new login.
                return None
            record = records.get(key)
            if record is None:
                return None
            if record["expires_at"] <= now:
                records.pop(key, None)
                self._write_persisted(records)
                return None
            return self._from_record(session_id, record)

    def revoke(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        if self._path is None:
            with self._lock:
                return self._sessions.pop(session_id, None) is not None

        key = _token_hash(session_id)
        with self._mutation():
            try:
                records = self._load_persisted()
            except SessionStoreError:
                # Nothing can be accepted from a corrupt store; do not rewrite
                # it here.  Logout stays idempotent and the next login resets.
                return False
            if records.pop(key, None) is None:
                return False
            self._write_persisted(records)
            return True

    def purge_expired(self) -> int:
        now = self._clock()
        if self._path is None:
            with self._lock:
                expired = [
                    key
                    for key, session in self._sessions.items()
                    if session.expires_at <= now
                ]
                for key in expired:
                    self._sessions.pop(key, None)
                return len(expired)

        with self._mutation():
            try:
                records = self._load_persisted()
            except SessionStoreError:
                return 0
            remaining = self._prune(records, now)
            removed = len(records) - len(remaining)
            if removed:
                self._write_persisted(remaining)
            return removed


__all__ = [
    "COOKIE_NAME",
    "SESSION_SCHEMA",
    "Session",
    "SessionRegistry",
    "SessionStoreError",
]
