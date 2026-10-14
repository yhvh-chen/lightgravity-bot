"""ASGI Host/Origin guard for the loopback-first local service (LG-020).

The product binds loopback by default and is served as one origin (the static
frontend and the API from the same process).  This middleware makes that
explicit and testable *without editing* ``api/app.py``:

* the ``Host`` header must resolve to a loopback host, ``testserver`` (in-process
  test transport) or a host the operator explicitly allowed;
* when a browser sends ``Origin``, its host must be allowed too, so a hostile
  cross-site page cannot ride the local service.

It deliberately does **not** authenticate requests; the local access token and
the default-deny sensitive-write policy stay in ``api/access.py``.  This guard
only rejects traffic that should never reach the app at all.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from urllib.parse import urlparse

#: Hosts that always count as local (loopback binds + in-process test transport).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "[::1]", "localhost", "testserver"})

_ALLOWED_METHODS_WITHOUT_BODY = frozenset({"GET", "HEAD", "OPTIONS"})


def normalize_host(value: str | None) -> str:
    """Lower-case a ``host[:port]`` value and strip the port (IPv6 aware)."""

    if not value:
        return ""
    host = value.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    if ":" in host:
        return host.rsplit(":", 1)[0]
    return host


def _envelope(code: str, message: str) -> bytes:
    return json.dumps(
        {
            "error": {
                "code": code,
                "message": message,
                "details": {},
                "retryable": False,
                "request_id": None,
            }
        }
    ).encode("utf-8")


class HostGuardMiddleware:
    """Pure-ASGI middleware enforcing allowed Host / same-origin Origin."""

    def __init__(
        self,
        app: object,
        *,
        allowed_hosts: Iterable[str] = (),
        extra_loopback: Sequence[str] = (),
    ) -> None:
        self.app = app
        allowed = {normalize_host(host) for host in allowed_hosts if host}
        allowed |= {normalize_host(host) for host in extra_loopback if host}
        self.allowed_hosts = frozenset(LOOPBACK_HOSTS | allowed)

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)  # type: ignore[operator]
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        host = normalize_host(headers.get("host"))
        if host not in self.allowed_hosts:
            await self._reject(
                send, 400, "invalid_host", f"host {host or '<missing>'!r} is not allowed"
            )
            return
        origin = headers.get("origin")
        if origin:
            origin_host = normalize_host(urlparse(origin).hostname)
            if origin_host not in self.allowed_hosts:
                await self._reject(
                    send,
                    403,
                    "origin_not_allowed",
                    "cross-origin requests are not accepted by the local service",
                )
                return
        await self.app(scope, receive, send)  # type: ignore[operator]

    async def _reject(self, send: object, status: int, code: str, message: str) -> None:
        body = _envelope(code, message)
        await send(  # type: ignore[operator]
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})  # type: ignore[operator]


__all__ = ["LOOPBACK_HOSTS", "HostGuardMiddleware", "normalize_host"]
