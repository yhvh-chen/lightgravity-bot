"""Local distribution runtime helpers (LG-020).

This package is *new* startup glue and deliberately owns no business logic:

* :mod:`~lightgravity.runtime.token` — the per-process runtime access token and
  the trusted local-page HTML injection (memory only, never persisted/URL/log).
* :mod:`~lightgravity.runtime.hostguard` — ASGI Host/Origin guard so the
  loopback-first service only answers trusted same-origin requests.
* :mod:`~lightgravity.runtime.frontend` — single-service static frontend
  serving with SPA fallback and token injection (or a minimal honest bootstrap
  page when the build is absent).
* :mod:`~lightgravity.runtime.pidfile` — runtime pid record plus real
  stop/cleanup of the started process.

None of these modules import the frozen ``lightgravity.api.app`` factory; the
assembly lives in :mod:`lightgravity.api.bootstrap`.
"""

from .frontend import mount_frontend
from .hostguard import HostGuardMiddleware
from .pidfile import (
    ProcessRecord,
    StopResult,
    process_alive,
    read_record,
    remove_record,
    stop_process_file,
    write_record,
)
from .token import RuntimeToken, inject_runtime_token, resolve_runtime_token

__all__ = [
    "HostGuardMiddleware",
    "ProcessRecord",
    "RuntimeToken",
    "StopResult",
    "inject_runtime_token",
    "mount_frontend",
    "process_alive",
    "read_record",
    "remove_record",
    "resolve_runtime_token",
    "stop_process_file",
    "write_record",
]
