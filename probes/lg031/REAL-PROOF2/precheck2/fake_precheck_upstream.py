"""Precheck-local scripted loopback upstream (provider-substitute).

Independent of the R1 fake.  Emits the *pinned SDK's real* tool names so the
native workspace sandbox actually writes exact artifact content, and scripts the
two-phase candidate-pool selection (discover -> claim non-first -> separate
execution session whose write target is derived from the selected node's
objective).  Loopback only; no network, no DeepSeek, no secret.

Records a redacted view: phase, tool names, discovered candidate keys.  Never
writes prompts/headers/credentials.
"""

from __future__ import annotations

import http.server
import json
import re
import threading
from pathlib import Path
from typing import Any


def _sse(data: str) -> str:
    return f"data: {data}\n\n"


def _chunk(delta: dict[str, Any], finish: str | None = None) -> str:
    payload = {
        "id": "chunk",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "fake-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if finish is not None:
        payload["usage"] = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
    return _sse(json.dumps(payload))


def _tool_call(tool: str, args: dict[str, Any], call_id: str = "call_1") -> str:
    return _chunk(
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "index": 0,
                    "id": call_id,
                    "type": "function",
                    "function": {"name": tool, "arguments": json.dumps(args)},
                }
            ],
        },
        finish="tool_calls",
    )


def _text(text: str) -> str:
    return _chunk({"role": "assistant", "content": text}, finish="stop")


class _ScriptedUpstream(http.server.BaseHTTPRequestHandler):
    """A scripted OpenAI-compatible SSE server (loopback only)."""

    records: list[dict[str, Any]] = []
    select_non_first: bool = True
    lock = threading.Lock()

    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        messages = body.get("messages") or []
        joined = json.dumps(messages)
        tool_names = [
            t.get("function", {}).get("name")
            for t in (body.get("tools") or [])
            if isinstance(t, dict) and isinstance(t.get("function"), dict)
        ]
        last_tool = next((m for m in reversed(messages) if m.get("role") == "tool"), None)
        last_tool_text = str((last_tool or {}).get("content") or "")
        granted = '"state": "granted"' in last_tool_text
        discovered = '"state": "discovered"' in last_tool_text

        selection = "PHASE 1" in joined
        discovered_keys = (
            re.findall(r'"key":\s*"([^"]+)"', last_tool_text) if discovered else []
        )
        wrote_already = any(
            m.get("role") == "tool" and "Created file" in str(m.get("content") or "")
            for m in messages
        )
        if selection and not granted:
            if discovered:
                node_ref = self._pick_node(last_tool_text, self.select_non_first)
                payload = _tool_call(
                    "discover_and_request_claim",
                    {"node_ref": node_ref, "request_id": "req-select"},
                ) + "data: [DONE]\n\n"
                phase = "selection:claim"
            else:
                payload = _tool_call("discover_and_request_claim", {}) + "data: [DONE]\n\n"
                phase = "selection:discover"
        elif selection:
            payload = _text("selection complete") + "data: [DONE]\n\n"
            phase = "selection:finish"
        elif re.search(r"Create (the file )?out/(alpha|beta)\.txt", joined) and not wrote_already:
            target, content = self._execution_target(joined)
            payload = _tool_call(
                "write_to_file",
                {
                    "TargetFile": target,
                    "CodeContent": content,
                    "Overwrite": True,
                    "Description": "Write the selected node artifact.",
                    "toolSummary": "Artifact write",
                    "toolAction": "Writing artifact",
                },
            ) + "data: [DONE]\n\n"
            phase = "execution:write"
        else:
            payload = _text("execution complete") + "data: [DONE]\n\n"
            phase = "execution:finish"

        with self.lock:
            self.__class__.records.append(
                {
                    "phase": phase,
                    "path": self.path,
                    "tool_names": tool_names,
                    "selection_phase": selection,
                    "has_alpha": "alpha" in joined,
                    "has_beta": "beta" in joined,
                    "discovered_keys": discovered_keys,
                    "last_tool_text": last_tool_text[:400],
                    "roles": [m.get("role") for m in messages][-6:],
                    "tail": [str(m.get("content") or m.get("tool_calls") or "")[:120] for m in messages[-3:]],
                }
            )
        encoded = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    @staticmethod
    def _pick_node(tool_text: str, non_first: bool) -> str:
        try:
            start = tool_text.index("{")
            payload = json.loads(tool_text[start:])
        except Exception:  # noqa: BLE001
            payload = None
        candidates: list[dict[str, Any]] = []
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            candidates = [c for c in payload["candidates"] if isinstance(c, dict)]
        if not candidates:
            refs = re.findall(r'"node_ref":\s*"([^"]+)"', tool_text)
            keys = re.findall(r'"key":\s*"([^"]+)"', tool_text)
            candidates = [{"node_ref": r, "key": k} for r, k in zip(refs, keys)]
        if not candidates:
            return ""
        chosen = candidates[-1] if non_first and len(candidates) > 1 else candidates[0]
        return str(chosen.get("node_ref") or "")

    @staticmethod
    def _execution_target(joined: str) -> tuple[str, str]:
        """(absolute target, exact content) from the selected node's session.

        The SDK workspace sandbox requires an absolute path; the isolated
        execution worktree is discoverable from the prompt (the same
        ``.lg-worktrees/<run>/<node>`` layout the program builds).
        """

        key = "alpha" if "alpha" in joined else ("beta" if "beta" in joined else "artifact")
        match = re.search(r"/[^\"\\ ]+?/\.lg-worktrees/[^\"'\\ ]+", joined)
        if match:
            return str(Path(match.group(0)) / f"out/{key}.txt"), key
        return str(Path(".").resolve() / f"out/{key}.txt"), key


class PrecheckUpstream:
    def __init__(self, *, select_non_first: bool = True, host: str = "127.0.0.1") -> None:
        self._orig = _ScriptedUpstream.select_non_first
        _ScriptedUpstream.records = []
        _ScriptedUpstream.select_non_first = select_non_first
        self._server = http.server.ThreadingHTTPServer((host, 0), _ScriptedUpstream)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f"http://{host}:{port}/v1"

    @property
    def records(self) -> list[dict[str, Any]]:
        return list(_ScriptedUpstream.records)

    def close(self) -> None:
        _ScriptedUpstream.select_non_first = self._orig
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)
