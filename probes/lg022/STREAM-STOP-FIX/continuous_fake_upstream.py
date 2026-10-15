"""Continuous-chunk local fake SSE upstream for the LG-022 stream-stop probe.

The QA fake (``qa/lg022-r2/sdk-cancel-investigation/fake_upstream.py``) proves
the defect, but its stream can be considered finished by the SDK shortly after
the first chunks in some interleavings, making a mid-stream stop racy.  This
local fake keeps emitting content chunks on a timer until released, so a stop
request reliably lands while the SDK turn is genuinely streaming.

``provider-substitute``: never DeepSeek, never the network.  Bounded total
hold so a probe cannot hang.  This file is probe-only and touches no product
code.
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


def _content_chunk(n: int) -> str:
    payload = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-reviewer",
        "choices": [
            {
                "index": 0,
                "delta": {"content": f"tick-{n} "},
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
class ContinuousGate:
    opened: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    client_gone: threading.Event = field(default_factory=threading.Event)
    requests: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        gate: ContinuousGate = self.server.gate  # type: ignore[attr-defined]
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
            send(_content_chunk(0))
            gate.opened.set()
            deadline = time.monotonic() + hold_seconds
            n = 1
            while not gate.release.is_set() and time.monotonic() < deadline:
                send(_content_chunk(n))
                n += 1
                if gate.release.wait(timeout=0.2):
                    break
            if gate.release.is_set():
                send(_stop_chunk())
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # The client (SDK/agent) closed the socket: real teardown evidence.
            gate.client_gone.set()


class ContinuousFakeUpstream:
    """Threaded HTTP server that streams content chunks until released."""

    def __init__(self, *, hold_seconds: float = 20.0) -> None:
        self.gate = ContinuousGate()
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.gate = self.gate  # type: ignore[attr-defined]
        self._server.hold_seconds = hold_seconds  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="continuous-fake"
        )
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self.gate.release.set()
        try:
            self._server.shutdown()
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass
        self._server.server_close()


__all__ = ["ContinuousFakeUpstream"]
