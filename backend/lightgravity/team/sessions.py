"""In-process team session registry (LG-050).

The session table lives in memory only: a restart invalidates every session and
the frontend must log in again.  The cookie carries only an opaque random id;
username/role/expiry are resolved server-side and never trusted from the client.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

#: Cookie name for the opaque session id.
COOKIE_NAME = "lg_session"
#: Random byte count for the session id (>= 256 bits of entropy).
_SESSION_BYTES = 32


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


class SessionRegistry:
    """Thread-safe ``session_id -> Session`` table with absolute TTL expiry."""

    def __init__(
        self,
        ttl_seconds: int,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = int(ttl_seconds)
        self._clock = clock
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def create(self, username: str, role: str, session_version: int = 0) -> Session:
        session_id = secrets.token_urlsafe(_SESSION_BYTES)
        session = Session(
            session_id=session_id,
            username=username,
            role=role,
            expires_at=self._clock() + self._ttl,
            session_version=session_version,
        )
        with self._lock:
            self._sessions[session_id] = session
        return session

    def resolve(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= self._clock():
                self._sessions.pop(session_id, None)
                return None
            return session

    def revoke(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def purge_expired(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [
                key for key, session in self._sessions.items() if session.expires_at <= now
            ]
            for key in expired:
                self._sessions.pop(key, None)
        return len(expired)


__all__ = ["COOKIE_NAME", "Session", "SessionRegistry"]
