"""Team authentication service: accounts + sessions + login throttling (LG-050).

This is the single server-side authority for a team identity.  Request bodies
and headers (including ``X-LG-Token``) never contribute to identity; only a
valid session id from the HttpOnly cookie does.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .accounts import Account, TeamAccounts
from .sessions import COOKIE_NAME, SessionRegistry

#: Failures allowed per identity key within the rolling window before a 429.
MAX_LOGIN_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class TeamIdentity:
    """A resolved, server-side team identity (never built from request fields)."""

    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class TeamAuthService:
    """Authenticate credentials and own the server-side session lifecycle."""

    def __init__(
        self,
        accounts: TeamAccounts,
        *,
        session_ttl_seconds: int = 28800,
        cookie_secure: bool = False,
        clock: Callable[[], float] = time.time,
        session_store_path: Path | str | None = None,
    ) -> None:
        self._accounts = accounts
        # LG-210: a configured store keeps only token hashes in the controlled
        # team data root, so a process restart no longer forces a new login.
        self._sessions = SessionRegistry(
            session_ttl_seconds, clock=clock, store_path=session_store_path
        )
        self._clock = clock
        self._cookie_secure = cookie_secure
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.RLock()

    @property
    def accounts(self) -> TeamAccounts:
        return self._accounts

    @property
    def cookie_secure(self) -> bool:
        return self._cookie_secure

    @property
    def ttl_seconds(self) -> int:
        return self._sessions.ttl_seconds

    # ------------------------------------------------------------ credentials
    def authenticate(self, username: str, password: str) -> TeamIdentity | None:
        account = self._accounts.authenticate(username, password)
        if account is None:
            return None
        return TeamIdentity(username=account.username, role=account.role)

    # --------------------------------------------------------------- sessions
    def create_session(self, identity: TeamIdentity) -> str:
        # Bind the session to the account's current credential revision.  If a
        # password reset/change, disable or role change bumps it, this session
        # fails the fresh-state check on its very next request.
        account = self._accounts.get(identity.username)
        session_version = account.session_version if account is not None else 0
        session = self._sessions.create(
            identity.username, identity.role, session_version
        )
        return session.session_id

    def resolve(self, session_id: str | None) -> TeamIdentity | None:
        session = self._sessions.resolve(session_id)
        if session is None:
            return None
        # Always resolve the *current* account state: never trust the role or
        # enabled flag cached in the session.  A missing, disabled, or
        # revision-changed account drops the session immediately.
        account = self._accounts.get(session.username)
        if account is None or not account.enabled:
            self._sessions.revoke(session_id)
            return None
        if account.session_version != session.session_version:
            self._sessions.revoke(session_id)
            return None
        return TeamIdentity(username=account.username, role=account.role)

    def revoke(self, session_id: str | None) -> bool:
        return self._sessions.revoke(session_id)

    def purge_expired(self) -> int:
        return self._sessions.purge_expired()

    # ------------------------------------------------------------- throttling
    def _key(self, username: str, client: str | None) -> str:
        return f"{client or 'unknown'}|{username}"

    def _recent(self, key: str, now: float) -> list[float]:
        stamps = self._failures.get(key, [])
        return [stamp for stamp in stamps if now - stamp < LOGIN_WINDOW_SECONDS]

    def login_allowed(self, username: str, client: str | None = None) -> bool:
        now = self._clock()
        with self._lock:
            recent = self._recent(self._key(username, client), now)
            if recent:
                self._failures[self._key(username, client)] = recent
            else:
                self._failures.pop(self._key(username, client), None)
            return len(recent) < MAX_LOGIN_FAILURES

    def record_failure(self, username: str, client: str | None = None) -> None:
        now = self._clock()
        key = self._key(username, client)
        with self._lock:
            recent = self._recent(key, now)
            recent.append(now)
            self._failures[key] = recent

    def record_success(self, username: str, client: str | None = None) -> None:
        with self._lock:
            self._failures.pop(self._key(username, client), None)

    def failure_count(self, username: str, client: str | None = None) -> int:
        now = self._clock()
        with self._lock:
            return len(self._recent(self._key(username, client), now))


__all__ = [
    "COOKIE_NAME",
    "LOGIN_WINDOW_SECONDS",
    "MAX_LOGIN_FAILURES",
    "TeamAuthService",
    "TeamIdentity",
]
