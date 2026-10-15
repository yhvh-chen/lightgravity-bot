#!/usr/bin/env python3
"""Experiment-only metering relay (loopback) between the product auth proxy and
the real DeepSeek upstream.

Topology (unchanged product code, only run parameters):

    SDK harness --HTTP--> LocalAuthProxy(injects Bearer) --HTTP--> this relay
        --HTTPS--> api.deepseek.com

The relay is the *only* place the experiment may unify declared parameters
(``max_tokens=8192`` and ``thinking={"type":"disabled"}``) and the only place
per-HTTP usage / ``finish_reason`` / response model / cache / reasoning can be
observed.  It:

* binds loopback only and forwards to a fixed authorized host;
* counts **every** upstream HTTP request, including SDK-internal retries;
* records the non-secret request parameters before and after rewriting, the
  response status, response model, ``finish_reason``s, usage and timing;
* never records or logs the ``Authorization`` header or any secret;
* forwards the exact response stream bytes to the client (no faked tool result).

It does **not** synthesize model output and does **not** suppress SDK retries.
"""
from __future__ import annotations

import http.client
import http.server
import json
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

# Fixed declared unification constants (identical for both experiment groups).
FORCED_MAX_TOKENS = 8192
FORCED_THINKING = {"type": "disabled"}
AUTHORIZED_HOSTS = frozenset({"api.deepseek.com"})
MAX_CAPTURE_BYTES = 4 * 1024 * 1024


@dataclass
class RelayCall:
    seq: int
    started_at: str
    path: str
    duration_s: float = 0.0
    request_before: dict[str, Any] = field(default_factory=dict)
    request_after: dict[str, Any] = field(default_factory=dict)
    rewrites: dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    tool_names: tuple[str, ...] = ()
    response_status: int | None = None
    response_model: str | None = None
    finish_reasons: list[str] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    reasoning_content_seen: bool = False
    response_bytes: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["tool_names"] = list(self.tool_names)
        return d


def _param_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Non-secret request parameters we care about (never messages content)."""
    tools = payload.get("tools")
    tool_names: list[str] = []
    if isinstance(tools, list):
        for tool in tools:
            fn = tool.get("function") if isinstance(tool, dict) else None
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                tool_names.append(fn["name"])
    messages = payload.get("messages")
    return {
        "model": payload.get("model"),
        "max_tokens": payload.get("max_tokens"),
        "max_completion_tokens": payload.get("max_completion_tokens"),
        "output_limit_fields": output_limit_fields(payload),
        "thinking": payload.get("thinking"),
        "temperature": payload.get("temperature"),
        "top_p": payload.get("top_p"),
        "stream": payload.get("stream"),
        "stream_options": payload.get("stream_options"),
        "response_format": payload.get("response_format"),
        "has_tools": bool(tools),
        "tool_names": tool_names,
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "message_roles": (
            [m.get("role") for m in messages if isinstance(m, dict)]
            if isinstance(messages, list) else []
        ),
    }


def output_limit_fields(payload: dict[str, Any]) -> list[str]:
    """Names among the mutually exclusive output-limit keys that are present."""

    return [k for k in ("max_tokens", "max_completion_tokens") if payload.get(k) is not None]


def unify_request(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the declared parameter unification; return (payload, rewrites).

    The corrected protocol has exactly **one** output-limit field.  The harness
    may send the ``max_completion_tokens`` alias (observed at 65535 in the first
    attempt); we remove it unconditionally and set ``max_tokens=8192`` so the
    declared output ceiling actually takes effect.
    """

    rewrites: dict[str, Any] = {}
    alias = payload.pop("max_completion_tokens", None)
    if alias is not None:
        rewrites["max_completion_tokens"] = {"from": alias, "to": None, "action": "removed"}
    if payload.get("max_tokens") != FORCED_MAX_TOKENS:
        rewrites["max_tokens"] = {"from": payload.get("max_tokens"), "to": FORCED_MAX_TOKENS}
        payload["max_tokens"] = FORCED_MAX_TOKENS
    if payload.get("thinking") != FORCED_THINKING:
        rewrites["thinking"] = {"from": payload.get("thinking"), "to": dict(FORCED_THINKING)}
        payload["thinking"] = dict(FORCED_THINKING)
    stream_opts = payload.get("stream_options")
    if not isinstance(stream_opts, dict) or not stream_opts.get("include_usage"):
        rewrites["stream_options"] = {"from": stream_opts, "to": {"include_usage": True}}
        payload["stream_options"] = {"include_usage": True}
    if len(output_limit_fields(payload)) != 1:
        raise ValueError(
            f"output limit not unified: fields={output_limit_fields(payload)} payload={payload!r}"
        )
    return payload, rewrites


def _parse_sse(buf: bytes) -> tuple[dict[str, Any] | None, str | None, list[str], bool]:
    """Extract (usage, response_model, finish_reasons, reasoning_seen) from SSE."""

    usage: dict[str, Any] | None = None
    model: str | None = None
    reasons: list[str] = []
    reasoning = False
    for raw in buf.split(b"\n"):
        line = raw.strip()
        if not line.startswith(b"data:"):
            continue
        data = line[5:].strip()
        if data == b"[DONE]":
            continue
        try:
            obj = json.loads(data.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("model"), str):
            model = obj["model"]
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
        for choice in obj.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            if choice.get("finish_reason"):
                reasons.append(str(choice["finish_reason"]))
            delta = choice.get("delta") or {}
            if isinstance(delta, dict) and delta.get("reasoning_content"):
                reasoning = True
    return usage, model, reasons, reasoning


class _RelayState:
    def __init__(self, *, upstream_url: str, timeout: float) -> None:
        self.upstream_url = upstream_url
        self.timeout = timeout
        self.active = True
        self.calls: list[RelayCall] = []
        self.lock = threading.Lock()
        self._seq = 0

    def next_seq(self) -> int:
        with self.lock:
            self._seq += 1
            return self._seq

    def record(self, call: RelayCall) -> None:
        with self.lock:
            self.calls.append(call)

    def snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return [c.to_dict() for c in self.calls]

    def count(self) -> int:
        with self.lock:
            return len(self.calls)


class _RelayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AgenshMeterRelay/1"
    state: _RelayState

    def log_message(self, *args: object) -> None:  # noqa: D102 - silence stdlib logs
        return

    def _read_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length < 0 or length > 16 * 1024 * 1024:
            return None
        return self.rfile.read(length) if length else b""

    def _json_error(self, status: int, message: str) -> None:
        body = json.dumps({"error": {"message": message}}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_POST(self) -> None:  # noqa: N802
        state = self.state
        path = self.path.split("?", 1)[0]
        if not path.endswith("/chat/completions"):
            self._json_error(404, "not_found")
            return
        seq = state.next_seq()
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        t0 = time.monotonic()
        call = RelayCall(seq=seq, started_at=started, path=path)
        state.record(call)
        body = self._read_body()
        if body is None:
            call.error = "bad_body"
            call.duration_s = round(time.monotonic() - t0, 3)
            self._json_error(413, "bad_body")
            return
        try:
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload not an object")
        except (UnicodeDecodeError, ValueError) as exc:
            call.error = f"bad_json: {exc}"
            call.duration_s = round(time.monotonic() - t0, 3)
            self._json_error(400, "bad_json")
            return

        call.request_before = _param_view(payload)
        call.message_count = int(call.request_before.get("message_count") or 0)
        call.tool_names = tuple(call.request_before.get("tool_names") or [])

        # --- declared unification (record exactly what changed) -------------
        payload, rewrites = unify_request(payload)
        call.rewrites = rewrites
        call.request_after = _param_view(payload)

        out_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._forward(out_body, call, t0)

    def _forward(self, body: bytes, call: RelayCall, t0: float) -> None:
        state = self.state
        parsed = urlparse(state.upstream_url)
        headers = {
            "Content-Type": "application/json",
            "Accept": self.headers.get("Accept") or "text/event-stream",
        }
        auth = self.headers.get("Authorization")
        if auth:  # forwarded verbatim, never recorded
            headers["Authorization"] = auth
        conn: http.client.HTTPSConnection | None = None
        try:
            if parsed.scheme == "https":
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection(
                    parsed.hostname, parsed.port or 443, timeout=state.timeout, context=ctx
                )
            else:
                conn = http.client.HTTPConnection(
                    parsed.hostname, parsed.port or 80, timeout=state.timeout
                )
            conn.request("POST", parsed.path or "/v1/chat/completions", body=body, headers=headers)
            upstream = conn.getresponse()
            status = upstream.status
            call.response_status = status
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
                call.response_bytes += len(chunk)
                if len(captured) < MAX_CAPTURE_BYTES:
                    captured.extend(chunk[: MAX_CAPTURE_BYTES - len(captured)])
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    call.error = "client_closed"
                    break
            usage, model, reasons, reasoning = _parse_sse(bytes(captured))
            call.usage = usage
            call.response_model = model
            call.finish_reasons = reasons
            call.reasoning_content_seen = reasoning
        except Exception as exc:  # noqa: BLE001 - never crash the relay thread
            call.error = f"{type(exc).__name__}: {exc}"
            if call.response_status is None:
                try:
                    self._json_error(502, "relay_upstream_error")
                except Exception:  # noqa: BLE001
                    pass
        finally:
            call.duration_s = round(time.monotonic() - t0, 3)
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass


class MeteringRelay:
    """Loopback metering relay with a fixed authorized upstream."""

    def __init__(
        self,
        *,
        upstream_url: str = "https://api.deepseek.com/v1/chat/completions",
        host: str = "127.0.0.1",
        port: int = 0,
        timeout: float = 120.0,
    ) -> None:
        parsed = urlparse(upstream_url)
        if parsed.scheme != "https" or parsed.hostname not in AUTHORIZED_HOSTS:
            raise ValueError(f"refusing to relay to unauthorized upstream {upstream_url!r}")
        if host != "127.0.0.1":
            raise ValueError("metering relay must bind 127.0.0.1")
        self._host = host
        self._requested_port = port
        self._state = _RelayState(upstream_url=upstream_url, timeout=timeout)
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int | None = None
        self._started = False
        self._stopped = False

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise RuntimeError("relay not started")
        return f"http://{self._host}:{self._port}/v1"

    @property
    def call_count(self) -> int:
        return self._state.count()

    def call_records(self) -> list[dict[str, Any]]:
        return self._state.snapshot()

    def start(self) -> None:
        if self._started and not self._stopped:
            return
        handler = type("_BoundRelay", (_RelayHandler,), {"state": self._state})
        server = http.server.ThreadingHTTPServer((self._host, self._requested_port), handler)
        server.daemon_threads = True
        self._server = server
        self._port = int(server.server_address[1])
        self._thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05},
            name="agensh-meter-relay", daemon=True,
        )
        self._thread.start()
        self._started = True

    def stop(self, *, timeout: float = 10.0) -> bool:
        if self._stopped:
            return True
        self._state.active = False
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:  # noqa: BLE001
                pass
        if self._thread is not None:
            self._thread.join(timeout)
        self._stopped = self._thread is None or not self._thread.is_alive()
        return self._stopped

    def total_reported_tokens(self) -> int:
        total = 0
        for call in self.call_records():
            usage = call.get("usage") or {}
            try:
                total += int(usage.get("total_tokens") or 0)
            except (TypeError, ValueError):
                continue
        return total

    def __enter__(self) -> "MeteringRelay":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


__all__ = ["MeteringRelay", "RelayCall", "FORCED_MAX_TOKENS", "FORCED_THINKING",
           "unify_request", "output_limit_fields", "_param_view", "_parse_sse"]
