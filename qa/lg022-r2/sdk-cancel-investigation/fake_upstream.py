"""Controlled local OpenAI-compatible streaming fake upstream (QA probe only).

Provides a valid SSE stream that can be held open in a controlled, *bounded*
way (staged release + hard total timeout), so an SDK probe can observe whether
a real ``google-antigravity`` cancel truly reaches the transport.  This is a
``provider-substitute``: it is NOT DeepSeek and never touches the network.

Design constraints (per the investigation brief):
  * valid SSE protocol (``data: {...}`` chunks + ``data: [DONE]``);
  * staged, controllable release (``release`` event) so the stream can be held
    mid-turn while cancel is exercised;
  * a hard total timeout so a probe can never hang past its per-run budget
    (the server thread auto-ends the stream at ``hold_seconds``); this avoids
    the prior mistake of treating the SDK's 120s request timeout as a 5s cancel
    failure;
  * records whether the client (SDK) went away before release -> ``client_gone``.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
from dataclasses import dataclass, field


def _role_chunk() -> str:
    payload = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-reviewer",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": "partial-"},
                "finish_reason": None,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _content_chunk() -> str:
    payload = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-reviewer",
        "choices": [
            {
                "index": 0,
                "delta": {"content": "still-streaming"},
                "finish_reason": None,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _stop_chunk() -> str:
    payload = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-reviewer",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }
    return f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n"


@dataclass
class Gate:
    """Test-owned control for the fake upstream."""

    opened: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    client_gone: threading.Event = field(default_factory=threading.Event)
    #: Monotonic-ish timestamp when the stream was first held.
    held_at: float = 0.0
    requests: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        gate: Gate = self.server.gate  # type: ignore[attr-defined]
        hold_seconds: float = self.server.hold_seconds  # type: ignore[attr-defined]
        with gate.lock:
            gate.requests += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def send(data: str) -> None:
            raw = data.encode("utf-8")
            self.wfile.write(f"{len(raw):X}\r\n".encode("ascii") + raw + b"\r\n")
            self.wfile.flush()

        try:
            send(_role_chunk())
            send(_content_chunk())
            gate.held_at = time.monotonic()
            gate.opened.set()
            # Staged hold: end at release OR at the hard total timeout.  Never
            # hold indefinitely -> the probe stays within its own budget and we
            # never mistake an SDK request timeout for a cancel failure.
            released = gate.release.wait(timeout=hold_seconds)
            if not released:
                # Probe did not release and the SDK did not finish: the client
                # is still attached.  Close cleanly so the SDK sees a short
                # (non-hanging) stream ending at the server's bounded timeout.
                gate.client_gone.set()  # server-side close, not client-gone
                try:
                    send(_stop_chunk())
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                return
            send(_stop_chunk())
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # The client (SDK/agent) closed the socket before we finished ->
            # evidence that the turn was torn down (cancel/disconnect worked).
            gate.client_gone.set()


class FakeUpstream:
    """Threaded HTTP server hosting the controlled SSE fake."""

    def __init__(self, *, hold_seconds: float = 20.0) -> None:
        self.gate = Gate()
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.gate = self.gate  # type: ignore[attr-defined]
        self._server.hold_seconds = hold_seconds  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="fake-upstream"
        )
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self.gate.release.set()
        try:
            self._server.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self._server.server_close()
        self._thread.join(timeout=5)


__all__ = ["FakeUpstream", "Gate"]
