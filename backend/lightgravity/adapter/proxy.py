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
import os
import re
import secrets
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .credentials import Secret
from .errors import CapabilityUnavailable

if TYPE_CHECKING:  # pragma: no cover - typing only (avoids import cycle)
    from .generation_ledger import PersistentGenerationLedger

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


class GenerationCounter:
    """Process-global hard cap on upstream chat-completion requests (LG-022 R1).

    LG-022 QA could not state a real limit on product model calls because the
    per-proxy budgets reset for every session/reviewer/retry.  This counter is
    shared by every :class:`LocalAuthProxy` in the process and is consulted
    *before* a request is forwarded, so a genuinely global hard cap covers all
    worker sessions, reviewer turns and SDK retries.  A denied reservation is
    reported to the caller as the same 429 budget-exhausted response as the
    per-proxy cap.

    ``reserve`` is thread-safe.  ``None`` as ``limit`` means "count only, no
    cap" (used when an operator wants observability without a limit).

    LG-022 R2: when a :class:`~lightgravity.adapter.generation_ledger.PersistentGenerationLedger`
    is attached, the count lives in the controlled data root and is reserved
    atomically **before** forwarding, so it survives a process/service restart
    and is shared across worker/reviewer/session.  Corruption is never treated
    as ``0``: a corrupt ledger denies the reservation and reports it.
    """

    def __init__(
        self,
        limit: int | None = None,
        *,
        ledger: "PersistentGenerationLedger | None" = None,
    ) -> None:
        if limit is not None and limit < 0:
            raise ValueError("generation limit must be >= 0 or None")
        self._limit = limit
        self._lock = threading.Lock()
        self._count = 0
        self._ledger = ledger

    @property
    def limit(self) -> int | None:
        return self._limit

    @property
    def count(self) -> int:
        if self._ledger is not None:
            try:
                return self._ledger.count()
            except Exception:  # noqa: BLE001 - a corrupt ledger is reported as unknown
                return -1
        with self._lock:
            return self._count

    def reserve(self) -> bool:
        """Reserve one global generation slot; ``False`` if denied.

        A denial covers the cap being reached, the cross-process lock being
        unavailable, and a corrupt ledger; all of them must refuse the forward
        rather than spend the credential.
        """

        if self._ledger is not None:
            return self._ledger.reserve().granted
        with self._lock:
            if self._limit is not None and self._count >= self._limit:
                return False
            self._count += 1
            return True

    def snapshot(self) -> dict[str, Any]:
        if self._ledger is not None:
            snap = self._ledger.snapshot()
            snap.setdefault("limit", self._limit)
            snap.setdefault("persistent", True)
            return snap
        with self._lock:
            return {
                "count": self._count,
                "limit": self._limit,
                "remaining": (
                    None if self._limit is None else max(0, self._limit - self._count)
                ),
                "persistent": False,
            }


def _default_generation_counter() -> GenerationCounter:
    """Return the process-wide counter lazily (no import-time env coupling).

    LG-022 R2: build the persistent ledger from the controlled data root so the
    count survives restarts; a missing data root keeps the in-memory counter so
    the meter still works (it is simply not durable in that deployment).
    """

    global _GLOBAL_GENERATION_COUNTER
    if _GLOBAL_GENERATION_COUNTER is None:
        from .generation_ledger import PersistentGenerationLedger, ledger_root_from_env

        limit = _limit_from_env()
        root = ledger_root_from_env()
        ledger = PersistentGenerationLedger(root, limit=limit) if root is not None else None
        _GLOBAL_GENERATION_COUNTER = GenerationCounter(limit, ledger=ledger)
    return _GLOBAL_GENERATION_COUNTER


def _limit_from_env() -> int | None:
    raw = os.environ.get("LIGHTGRAVITY_MAX_GENERATION_CALLS")
    if raw is None or raw.strip() == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def global_generation_counter() -> GenerationCounter:
    """Return the shared process-global generation counter (LG-022 R1).

    QA/status surfaces can read ``count``/``limit``/``remaining`` to obtain a
    real, cross-session generation count instead of an unknown.
    """

    return _default_generation_counter()


def configure_generation_ledger(
    root: Any, limit: int | None = None
) -> GenerationCounter:
    """Attach a persistent ledger rooted at the controlled data dir (LG-022 R2).

    Called once at startup with the resolved ``settings.data_dir`` so the count
    is durable even when ``LIGHTGRAVITY_DATA_DIR`` is not exported.  Idempotent:
    re-configuring the same root rebuilds the counter from the same ledger.
    """

    global _GLOBAL_GENERATION_COUNTER
    from .generation_ledger import PersistentGenerationLedger

    resolved_limit = _limit_from_env() if limit is None else limit
    ledger = PersistentGenerationLedger(root, limit=resolved_limit)
    _GLOBAL_GENERATION_COUNTER = GenerationCounter(resolved_limit, ledger=ledger)
    return _GLOBAL_GENERATION_COUNTER


#: Process-global counter shared by all proxies unless one is injected.
_GLOBAL_GENERATION_COUNTER: GenerationCounter | None = None


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
        generator_budget: "GenerationCounter | None" = None,
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
        #: LG-022 R1: optional process-global generation counter.  When set, every
        #: chat completion is counted *before* it is forwarded, across all
        #: proxies (worker sessions, reviewer turns, retries), so an external QA
        #: can enforce/observe a real global hard cap instead of per-proxy
        #: unknowns.  ``None`` keeps the legacy per-proxy behaviour.
        self.generator_budget = generator_budget

    def begin_call(self) -> int | None:
        with self.lock:
            if not self.active or self.calls >= self.max_calls:
                return None
            # Reserve a global generation slot *before* forwarding.  A denied
            # global slot is a hard stop and consumes no local call either.
            if self.generator_budget is not None and not self.generator_budget.reserve():
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
        generation_budget: GenerationCounter | None = None,
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
        # LG-022 R1: share the process-global generation counter by default so
        # worker sessions, reviewer turns and retries all consume one real hard
        # cap.  A caller may inject its own counter (tests) or ``None`` to keep
        # only the per-proxy counter.
        resolved_budget = (
            generation_budget
            if generation_budget is not None
            else _default_generation_counter()
        )
        self._state = _ProxyState(
            credential=credential,
            upstream_url=upstream_url,
            session_token=session_token or secrets.token_urlsafe(24),
            max_calls=max_calls,
            timeout=timeout,
            generator_budget=resolved_budget,
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
    "GenerationCounter",
    "configure_generation_ledger",
    "ProxyCallRecord",
    "LocalAuthProxy",
    "global_generation_counter",
    "upstream_chat_completions",
]
