"""Runtime local access token and trusted-page handshake (LG-020, docs/08 §4.1).

The token is the value the API expects in ``X-LG-Token`` for sensitive writes
(``LocalAccessPolicy``).  Rules implemented here:

* it is generated in-process with :func:`secrets.token_urlsafe` when the
  operator has not injected one through :data:`RUNTIME_TOKEN_ENV`;
* it is never written to the data directory, a log line, a URL or Markdown;
* it is handed to the browser only inside the HTML of a trusted loopback page,
  into the existing in-memory ``window.__LG_RUNTIME_TOKEN__`` global that
  ``frontend/src/api/auth.ts`` already reads.  No persistent storage is used.

The value is exposed as :class:`RuntimeToken` with a ``source`` label so status
output can report *how* it was obtained without revealing it.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

#: Optional operator-injected token (e.g. from a process manager).  Never a
#: file the app writes.
RUNTIME_TOKEN_ENV = "LIGHTGRAVITY_RUNTIME_TOKEN"

#: Number of random bytes for the generated token (>= 256 bits).
_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class RuntimeToken:
    """A resolved runtime token plus its provenance (never logged as a value)."""

    value: str
    source: str  # "environment" | "generated"

    def __repr__(self) -> str:  # pragma: no cover - defensive redaction
        return f"RuntimeToken(source={self.source!r}, value=<redacted>)"


def resolve_runtime_token(env: Mapping[str, str] | None = None) -> RuntimeToken:
    """Return the injected token, or generate one for this process."""

    source = os.environ if env is None else env
    injected = source.get(RUNTIME_TOKEN_ENV)
    if isinstance(injected, str) and injected.strip():
        return RuntimeToken(injected.strip(), "environment")
    return RuntimeToken(secrets.token_urlsafe(_TOKEN_BYTES), "generated")


def bootstrap_script(token: str) -> str:
    """Build the in-memory handshake ``<script>`` for a trusted local page."""

    payload = json.dumps(token)
    return (
        "<script>"
        f"window.__LG_RUNTIME_TOKEN__={payload};"
        "window.__LG_RUNTIME_TOKEN_READY__=true;"
        "</script>"
    )


def inject_runtime_token(html: str, token: str) -> str:
    """Insert the handshake script into ``<head>`` (fallback: ``<body>``/front)."""

    script = bootstrap_script(token)
    lowered = html.lower()
    head = lowered.find("<head")
    if head != -1:
        end = html.find(">", head)
        if end != -1:
            return html[: end + 1] + "\n" + script + html[end + 1 :]
    body = lowered.find("<body")
    if body != -1:
        end = html.find(">", body)
        if end != -1:
            return html[: end + 1] + "\n" + script + html[end + 1 :]
    return script + "\n" + html


__all__ = [
    "RUNTIME_TOKEN_ENV",
    "RuntimeToken",
    "bootstrap_script",
    "inject_runtime_token",
    "resolve_runtime_token",
]
