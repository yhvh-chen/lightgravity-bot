"""Local controlled OpenAI-compatible SSE upstream (provider-substitute).

Independent LG-032 R1 QA harness.  This is **not** DeepSeek and never touches the
network: it binds ``127.0.0.1`` on an ephemeral port and serves a scripted SSE
stream so the *real* pinned Antigravity SDK 0.1.22 agent loop, tool invocation,
loopback auth proxy and session lifecycle all run end to end while the model's
"decisions" are deterministic script.

The fake upstream is intentionally strict: it records a *redacted* view of every
request (phase, tool names, whether the objective for a given node was visible)
and can be scripted per phase.  Two scripted behaviours are supported:

* ``mode="two_phase_selection"`` — phase-1 selection: ``discover`` then claim the
  candidate whose ``key`` matches ``select_first``/``select_second``; phase-2
  execution: write the selected node's own artifact.
* ``mode="race"`` — a single node claim, used to observe one-winner semantics.

No secret, prompt or auth header is ever written to the evidence; only tool
names, phases and booleans.
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


class ScriptedFakeUpstream(http.server.BaseHTTPRequestHandler):
    """A scripted OpenAI-compatible SSE server (loopback only)."""

    records: list[dict[str, Any]] = []
    #: Which candidate key the selection session should claim: "second" -> non-first.
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
        tool_schemas = {
            t["function"]["name"]: t["function"].get("parameters", {})
            for t in (body.get("tools") or [])
            if isinstance(t, dict) and isinstance(t.get("function"), dict)
            and t["function"].get("name") in {"create_file", "edit_file", "write_to_file"}
        }
        last_tool = next((m for m in reversed(messages) if m.get("role") == "tool"), None)
        last_tool_text = str((last_tool or {}).get("content") or "")
        granted = '"state": "granted"' in last_tool_text
        discovered = '"state": "discovered"' in last_tool_text

        selection = "PHASE 1" in joined
        discovered_keys = (
            re.findall(r'"key":\s*"([^"]+)"', last_tool_text) if discovered else []
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
        elif "write_to_file" not in joined and "out/" in joined:
            target = self._execution_target(joined)
            payload = _tool_call(
                "write_to_file",
                {
                    "TargetFile": target,
                    "Overwrite": True,
                    "CodeContent": f"{target}\n",
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
                    "write_tool_schemas": tool_schemas,
                    "all_tool_names": tool_names,
                    "last_tool_text": last_tool_text[:200],
                    "discovered_keys": discovered_keys,
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
    def _execution_target(joined: str) -> str:
        match = re.search(r"(out/[a-zA-Z0-9_]+\.txt)", joined)
        rel = match.group(1) if match else "out/artifact.txt"
        ws = re.search(r"(/[^\"\\ ]+?/\.lg-worktrees/[^\"\\ ]+)", joined)
        if ws:
            return str(Path(ws.group(1)) / rel)
        return rel


class UpstreamServer:
    def __init__(self, *, select_non_first: bool = True, host: str = "127.0.0.1") -> None:
        self._orig = ScriptedFakeUpstream.select_non_first
        ScriptedFakeUpstream.records = []
        ScriptedFakeUpstream.select_non_first = select_non_first
        self._server = http.server.ThreadingHTTPServer((host, 0), ScriptedFakeUpstream)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f"http://{host}:{port}/v1"

    @property
    def records(self) -> list[dict[str, Any]]:
        return list(ScriptedFakeUpstream.records)

    def close(self) -> None:
        ScriptedFakeUpstream.select_non_first = self._orig
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)
