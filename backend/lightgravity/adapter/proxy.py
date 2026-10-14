"""Product-side loopback authentication proxy (docs/08 §8.1).

The pinned Antigravity ``LocalOpenAIAgentConfig`` speaks the OpenAI
``/v1/chat/completions`` protocol but its endpoint config carries only
``base_url`` - there is no ``api_key`` field.  Hosted providers such as DeepSeek
require a bearer token, so this component fronts the *fixed, authorized*
upstream and injects the credential from memory.

Guarantees:

* Binds loopback only (``127.0.0.1``/``::1``), on an ephemeral port.
* Serves exactly one URL prefix containing a per-session random token, so a
  different local session/process cannot reuse the proxy to spend the
  credential.
* Forwards only ``/v1/<token>/chat/completions`` to the upstream host on the
  authorization allowlist; every other path is rejected.
* Never logs, echoes or records the ``Authorization`` header or the secret
  value; the only recorded call metadata is model/path/stream/tool names.
* Has an explicit start/stop lifecycle.  :meth:`LocalAuthProxy.stop` returns a
  *confirmation* and only reports success once the serving thread and socket are
  gone.

This is product code; it does not import or depend on the LG-003 probe.
"""

from __future__ import annotations

import http.server
import json
import re
import secrets
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

from .credentials import Secret
from .errors import CapabilityUnavailable

#: Hosts the proxy may bind.  Loopback only - never 0.0.0.0.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

#: Upstream hosts the product may forward credentials to (fixed allowlist).
AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com"})

#: The single authorized first-version upstream (DeepSeek chat completions).
DEEPSEEK_UPSTREAM_URL = "https://api.deepseek.com/v1/chat/completions"

#: Request bodies must stay under this bound (model prompts, base64 images).
MAX_REQUEST_BYTES = 16 * 1024 * 1024

#: Only the OpenAI chat-completions path is proxied.
_CHAT_SUFFIX = "/chat/completions"

_MODEL_RE = re.compile(rb'"model"\s*:\s*"([^"]+)"')


def _extract_model(payload: bytes) -> str | None:
    match = _MODEL_RE.search(payload)
    if match is None:
        return None
    try:
        return match.group(1).decode("utf-8")
    except UnicodeDecodeError:
        return None


def upstream_chat_completions(base_url: str) -> str:
    """Return the fixed upstream chat-completions URL for a connection base."""

    root = base_url.rstrip("/")
    if root.endswith(_CHAT_SUFFIX):
        return root
    return root + _CHAT_SUFFIX


@dataclass(frozen=True, slots=True)
class ProxyCallRecord:
    """Sanitized metadata about one proxied upstream call (never headers)."""

    call: int
    path: str
    model: str | None
    stream: bool | None
    message_count: int
    has_tools: bool
    tool_names: tuple[str, ...]
    has_response_format: bool
    forwarded: bool
    status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "call": self.call,
            "path": self.path,
            "model": self.model,
            "stream": self.stream,
            "message_count": self.message_count,
            "has_tools": self.has_tools,
            "tool_names": list(self.tool_names),
            "has_response_format": self.has_response_format,
            "forwarded": self.forwarded,
            "status": self.status,
        }


class _ProxyState:
    """Mutable state shared by the serving thread and the HTTP handler."""

    def __init__(
        self,
        *,
        credential: Secret,
        upstream_url: str,
        session_token: str,
        max_calls: int,
        timeout: float,
    ) -> None:
        self.credential = credential
        self.upstream_url = upstream_url
        self.session_token = session_token
        self.max_calls = max_calls
        self.timeout = timeout
        self.active = True
        self.calls = 0
        self.records: list[ProxyCallRecord] = []
        self.upstream_model: str | None = None
        self.lock = threading.Lock()

    def begin_call(self) -> int | None:
        with self.lock:
            if not self.active or self.calls >= self.max_calls:
                return None
            self.calls += 1
            return self.calls

    def record(self, record: ProxyCallRecord) -> None:
        with self.lock:
            self.records.append(record)

    def snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return [record.to_dict() for record in self.records]


def _read_request_metadata(
    body: bytes,
) -> tuple[str | None, bool | None, int, bool, tuple[str, ...], bool]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, None, 0, False, (), False
    if not isinstance(payload, dict):
        return None, None, 0, False, (), False
    model = payload.get("model")
    model_name = model if isinstance(model, str) else None
    stream = payload.get("stream")
    stream_flag = stream if isinstance(stream, bool) else None
    messages = payload.get("messages")
    message_count = len(messages) if isinstance(messages, list) else 0
    raw_tools = payload.get("tools")
    tools = raw_tools if isinstance(raw_tools, list) else []
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, dict):
            fn = tool.get("function")
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                names.append(fn["name"])
    has_response_format = isinstance(payload.get("response_format"), dict)
    return model_name, stream_flag, message_count, bool(tools), tuple(names), has_response_format


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Loopback-only request handler with an injected credential."""

    protocol_version = "HTTP/1.1"
    server_version = "LightGravityAuthProxy/1"
    state: _ProxyState

    # Never emit request/header logs (they would include Authorization).
    def log_message(self, *args: object) -> None:  # noqa: D102 - stdlib hook
        return

    def version_string(self) -> str:  # noqa: D102 - stdlib hook
        return self.server_version

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # The local client went away; there is nobody to answer.
            pass
        self.close_connection = True

    def _read_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length < 0 or length > MAX_REQUEST_BYTES:
            return None
        return self.rfile.read(length) if length else b""

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        state = self.state
        path = self.path.split("?", 1)[0]
        expected = f"/{state.session_token}/v1{_CHAT_SUFFIX}"
        if path != expected:
            self._json(404, {"error": {"message": "not_found"}})
            return

        call = state.begin_call()
        if call is None:
            self._json(
                429,
                {"error": {"message": "local auth proxy call budget exhausted"}},
            )
            return

        body = self._read_body()
        if body is None:
            self._json(413, {"error": {"message": "request too large or malformed"}})
            return

        model, stream, message_count, has_tools, tool_names, has_response_format = (
            _read_request_metadata(body)
        )
        record = ProxyCallRecord(
            call=call,
            path=path,
            model=model,
            stream=stream,
            message_count=message_count,
            has_tools=has_tools,
            tool_names=tool_names,
            has_response_format=has_response_format,
            forwarded=True,
        )
        self._forward(body, state, record)

    def _forward(self, body: bytes, state: _ProxyState, record: ProxyCallRecord) -> None:
        request = urllib.request.Request(
            state.upstream_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": self.headers.get("Accept") or "text/event-stream",
                # The only place the secret is materialized, in memory.
                "Authorization": "Bearer " + state.credential.reveal(),
            },
        )
        try:
            upstream = urllib.request.urlopen(request, timeout=state.timeout)
        except urllib.error.HTTPError as exc:
            # Drain the upstream body to release the connection; never echo it.
            _ = exc.read(65536)
            state.record(replace(record, status=exc.code))
            self._json(exc.code, {"error": {"message": "upstream error"}})
            return
        except Exception as exc:  # noqa: BLE001 - translate to a bounded failure
            state.record(replace(record, status=502))
            self._json(502, {"error": {"message": f"upstream {type(exc).__name__}"}})
            return

        try:
            with upstream:
                status = upstream.status
                content_type = upstream.headers.get("Content-Type", "text/event-stream")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                captured = bytearray()
                while True:
                    chunk = upstream.read(4096)
                    if not chunk:
                        break
                    if len(captured) < 8192:
                        captured.extend(chunk[: 8192 - len(captured)])
                        observed = _extract_model(bytes(captured))
                        if observed is not None and state.upstream_model is None:
                            with state.lock:
                                state.upstream_model = observed
                    self.wfile.write(chunk)
                    self.wfile.flush()
                self.wfile.flush()
                observed = _extract_model(bytes(captured))
                if observed is not None:
                    with state.lock:
                        state.upstream_model = observed
                state.record(replace(record, status=status))
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Local client aborted (commonly an executor cancellation); the
            # upstream call still happened and is counted, but no response can
            # be delivered.
            self.close_connection = True
            state.record(replace(record, status=499))
        except Exception:  # noqa: BLE001 - never let the proxy thread crash
            self.close_connection = True
            state.record(replace(record, status=502))


class LocalAuthProxy:
    """Single-session loopback authentication proxy with a fixed upstream."""

    def __init__(
        self,
        *,
        credential: Secret,
        upstream_url: str = DEEPSEEK_UPSTREAM_URL,
        session_token: str | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        max_calls: int = 64,
        timeout: float = 120.0,
        allow_loopback_upstream: bool = False,
    ) -> None:
        if host not in LOOPBACK_HOSTS or host == "localhost":
            raise CapabilityUnavailable(
                f"local auth proxy must bind a loopback address, not {host!r}",
                capability="local_auth_proxy",
            )
        parsed = urlparse(upstream_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise CapabilityUnavailable(
                "local auth proxy requires an absolute upstream URL",
                capability="local_auth_proxy",
            )
        allowed = set(AUTHORIZED_UPSTREAM_HOSTS)
        if allow_loopback_upstream:
            allowed |= {"127.0.0.1", "localhost", "::1"}
        if parsed.hostname not in allowed:
            raise CapabilityUnavailable(
                f"upstream host {parsed.hostname!r} is not authorized",
                capability="local_auth_proxy",
            )
        if max_calls <= 0:
            raise CapabilityUnavailable(
                "local auth proxy requires max_calls > 0",
                capability="local_auth_proxy",
            )
        self._host = host
        self._requested_port = port
        self._state = _ProxyState(
            credential=credential,
            upstream_url=upstream_url,
            session_token=session_token or secrets.token_urlsafe(24),
            max_calls=max_calls,
            timeout=timeout,
        )
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int | None = None
        self._lock = threading.Lock()
        self._started = False
        self._stopped = False

    # ------------------------------------------------------------------ props
    @property
    def session_token(self) -> str:
        return self._state.session_token

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def upstream_url(self) -> str:
        return self._state.upstream_url

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(self._started and not self._stopped and thread is not None and thread.is_alive())

    @property
    def base_url(self) -> str:
        """The SDK ``base_url``; includes the per-session token prefix."""

        if self._port is None:
            raise CapabilityUnavailable(
                "local auth proxy has not been started", capability="local_auth_proxy"
            )
        host = f"[{self._host}]" if ":" in self._host else self._host
        return f"http://{host}:{self._port}/{self._state.session_token}/v1"

    @property
    def call_count(self) -> int:
        return self._state.calls

    @property
    def upstream_model(self) -> str | None:
        """The model id the upstream reported (parsed from the first SSE frames)."""

        return self._state.upstream_model

    def call_records(self) -> list[dict[str, Any]]:
        return self._state.snapshot()

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Bind the ephemeral loopback port and start serving."""

        with self._lock:
            if self._started and not self._stopped:
                return
            if self._stopped:
                raise CapabilityUnavailable(
                    "local auth proxy is already stopped", capability="local_auth_proxy"
                )
            handler = type("_BoundProxyHandler", (_ProxyHandler,), {"state": self._state})
            try:
                server = http.server.ThreadingHTTPServer((self._host, self._requested_port), handler)
            except OSError as exc:
                raise CapabilityUnavailable(
                    f"local auth proxy could not bind {self._host}:{self._requested_port}",
                    capability="local_auth_proxy",
                ) from exc
            server.daemon_threads = True
            self._server = server
            self._port = int(server.server_address[1])
            thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name="lg-local-auth-proxy",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            self._started = True

    def stop(self, *, timeout: float = 10.0) -> bool:
        """Stop serving and return ``True`` only when the socket/thread are gone."""

        with self._lock:
            if self._stopped:
                return True
            self._state.active = False
            server = self._server
            thread = self._thread
        if server is not None:
            try:
                server.shutdown()
            except Exception:  # noqa: BLE001 - shutdown must be best-effort
                pass
            try:
                server.server_close()
            except Exception:  # noqa: BLE001
                pass
        if thread is not None:
            thread.join(timeout)
        confirmed = thread is None or not thread.is_alive()
        with self._lock:
            self._stopped = confirmed
        return confirmed

    def __enter__(self) -> "LocalAuthProxy":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def __repr__(self) -> str:
        # Never include the credential or upstream Authorization material.
        return (
            f"LocalAuthProxy(host={self._host!r}, port={self._port!r}, "
            f"running={self.is_running}, calls={self._state.calls})"
        )


__all__ = [
    "LOOPBACK_HOSTS",
    "AUTHORIZED_UPSTREAM_HOSTS",
    "DEEPSEEK_UPSTREAM_URL",
    "MAX_REQUEST_BYTES",
    "ProxyCallRecord",
    "LocalAuthProxy",
    "upstream_chat_completions",
]
