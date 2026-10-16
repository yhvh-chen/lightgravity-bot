"""Cross-process file locking (LG-004, docs/08 §7).

Uses ``fcntl.flock`` on a dedicated lock file per logical resource.  ``flock``
locks are attached to the open file description, so two handles in the same
process contend just like two processes do.  This gives a single primitive for
both multi-thread and multi-process mutual exclusion on the development host
(the first-release runtime is a single host, docs/08 §2.1).
"""

from __future__ import annotations

import errno
import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import LockConflict


def _sanitize(key: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in key)[:180]


class LockManager:
    """Create short-lived advisory locks under a directory."""

    def __init__(self, lock_dir: Path, *, default_timeout: float = 10.0) -> None:
        self._lock_dir = lock_dir
        self._timeout = default_timeout

    def lock_path(self, key: str) -> Path:
        return self._lock_dir / f"{_sanitize(key)}.lock"

    @contextmanager
    def acquire(self, key: str, *, timeout: float | None = None) -> Iterator[None]:
        """Hold an exclusive lock for ``key``; raise LockConflict on timeout."""

        limit = self._timeout if timeout is None else timeout
        path = self.lock_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + limit
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        raise LockConflict(key) from exc
                    time.sleep(0.005)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


__all__ = ["LockManager"]
