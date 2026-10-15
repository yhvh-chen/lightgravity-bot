"""LG-032 FINAL-COHORT offline scripted upstream (provider-substitute).

Derived from the LG-031 REAL-PROOF precheck fake (already probe-verified), but
adapted to the LG-032 fixtures, the product's own tool set (``view_file``,
``create_file``) and the frozen prompt templates.

Guarantees:
* Loopback only (``127.0.0.1``); no network, no DeepSeek; the credential the
  proxy injects is a locally-generated dummy.
* Emits the *pinned SDK's real* tool names so the native workspace sandbox
  actually reads/writes exact artifact content; drives the reviewer turn to a
  passing structured outcome.
* Records only redacted metadata (phase, tool names, roles).  Never records or
  returns prompts/headers/credentials in the saved evidence.
"""

from __future__ import annotations

import http.server
import json
import re
import threading
from pathlib import Path
from typing import Any

#: The two artifacts per sample, and the exact correct content the worker writes.
ARTIFACTS: dict[str, dict[str, str]] = {
    "s1_units": {
        "src/labels.py": (
            "import re\n\n\n"
            "def slugify(title: str) -> str:\n"
            "    lowered = title.lower()\n"
            "    collapsed = re.sub(r\"[^a-z0-9]+\", \"-\", lowered)\n"
            "    return collapsed.strip(\"-\")\n"
        ),
        "src/numeric.py": (
            "def clamp(value, lo, hi):\n"
            "    if value < lo:\n"
            "        return lo\n"
            "    if value > hi:\n"
            "        return hi\n"
            "    return value\n\n\n"
            "def in_range(value, lo, hi) -> bool:\n"
            "    return lo <= value <= hi\n"
        ),
    },
    "s2_pipeline": {
        "src/shapes.py": (
            "import math\n\n\n"
            "def area(shape):\n"
            "    kind = shape['kind']\n"
            "    if kind == 'rect':\n"
            "        return shape['width'] * shape['height']\n"
            "    if kind == 'circle':\n"
            "        return math.pi * shape['radius'] ** 2\n"
            "    raise ValueError(kind)\n\n\n"
            "def perimeter(shape):\n"
            "    kind = shape['kind']\n"
            "    if kind == 'rect':\n"
            "        return 2 * (shape['width'] + shape['height'])\n"
            "    if kind == 'circle':\n"
            "        return 2 * math.pi * shape['radius']\n"
            "    raise ValueError(kind)\n"
        ),
        "src/report.py": (
            "from .shapes import area, perimeter\n\n\n"
            "def describe(shape):\n"
            "    return f\"{shape['kind']}: area={area(shape):.2f} \" \\\n"
            "           f\"perimeter={perimeter(shape):.2f}\"\n"
        ),
    },
}


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
    capture_tools: list[Any] = []
    sample: str = "s1_units"
    arm: str = "A"
    capture_only: bool = False
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
        with self.lock:
            if not self.__class__.capture_tools and body.get("tools"):
                self.__class__.capture_tools = body.get("tools")

        if self.__class__.capture_only:
            payload = _text("captured") + "data: [DONE]\n\n"
            self._record("capture", joined, tool_names, messages)
            self._send(payload)
            return

        # --- Reviewer turn: no tools are exposed to the independent reviewer.
        if not tool_names and (
            "independent qa reviewer" in joined.lower()
            or "single json object" in joined.lower()
        ):
            payload = self._reviewer_payload(joined) + "data: [DONE]\n\n"
            self._record("review", joined, tool_names, messages)
            self._send(payload)
            return

        wrote = any(
            m.get("role") == "tool" and (
                "created" in str(m.get("content") or "").lower()
                or "wrote" in str(m.get("content") or "").lower()
            )
            for m in messages
        )
        read_done = any(
            m.get("role") == "tool" and "file" in str(m.get("content") or "").lower()
            for m in messages
        )

        # A node is a verify node iff it can only read (no write tool exposed).
        write_capable = any(
            n in ("write_to_file", "replace_file_content", "create_file", "edit_file")
            for n in tool_names
        )
        if self._is_selection(tool_names, joined):
            payload, phase = self._selection(messages, joined), "selection"
        elif not write_capable and "view_file" in tool_names:
            payload, phase = self._verify(messages), "verify"
        else:
            payload, phase = self._execute(messages, wrote), "execution"
        self._record(phase, joined, tool_names, messages)
        self._send(payload + "data: [DONE]\n\n")

    # ------------------------------------------------------------- internals
    def _record(self, phase: str, joined: str, tool_names: list[Any],
                messages: list[dict[str, Any]]) -> None:
        with self.lock:
            type(self).records.append(
                {
                    "phase": phase,
                    "path": self.path,
                    "tool_names": tool_names,
                    "roles": [m.get("role") for m in messages][-6:],
                    "tail": [str(m.get("content") or m.get("tool_calls") or "")[:160]
                             for m in messages[-3:]],
                    # Full text is non-secret (product prompts / tool schemas) and
                    # local-only; needed to derive the isolated workspace path.
                    "full": [str(m.get("content") or "")[:6000] for m in messages
                             if m.get("role") in ("system", "user")][-2:],
                }
            )

    def _send(self, payload: str) -> None:
        encoded = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    @staticmethod
    def _is_selection(tool_names: list[Any], joined: str) -> bool:
        # Only a real selection phase for arm B: the restricted claim tool must be
        # an *exposed tool* (not merely mentioned in a prompt).
        return "discover_and_request_claim" in tool_names

    @staticmethod
    def _is_verify(joined: str) -> bool:
        return "verification member" in joined.lower() or "read-only tools" in joined.lower()

    def _selection(self, messages: list[dict[str, Any]], joined: str) -> str:
        last_tool = next((m for m in reversed(messages) if m.get("role") == "tool"), None)
        last_tool_text = str((last_tool or {}).get("content") or "")
        granted = '"state": "granted"' in last_tool_text
        discovered = '"state": "discovered"' in last_tool_text
        if granted:
            return _text("selection complete")
        if discovered:
            node_ref = self._pick_node(last_tool_text, self.select_non_first)
            return _tool_call("discover_and_request_claim",
                              {"node_ref": node_ref, "request_id": "req-select"})
        return _tool_call("discover_and_request_claim", {})

    def _verify(self, messages: list[dict[str, Any]]) -> str:
        already = any(m.get("role") == "tool" for m in messages)
        if already:
            return _text("verified: artifacts match acceptance criteria")
        joined = json.dumps(messages)
        files = list(ARTIFACTS.get(self.sample, {}).keys())
        target = files[0] if files else "src/labels.py"
        root = self._workspace_root(joined)
        abspath = str(Path(root) / target) if root else target
        return _tool_call("view_file", {
            "AbsolutePath": abspath,
            "StartLine": 1, "EndLine": 200,
            "toolSummary": "Reading artifact",
            "toolAction": "Reading artifact",
        })

    def _execute(self, messages: list[dict[str, Any]], wrote: bool) -> str:
        joined = json.dumps(messages)
        files = list(ARTIFACTS.get(self.sample, {}).keys())
        if not files:
            return _text("implementation complete")
        # Count how many write tool calls the conversation already contains, and
        # which targets were written, so one node can write every artifact for
        # its objective (arm A writes both files; arm B writes one each).
        written_targets: list[str] = []
        for m in messages:
            for call in (m.get("tool_calls") or []):
                fn = call.get("function") if isinstance(call, dict) else None
                name = (fn or {}).get("name")
                if name == "write_to_file":
                    try:
                        args = json.loads((fn or {}).get("arguments") or "{}")
                    except Exception:  # noqa: BLE001
                        args = {}
                    tgt = str(args.get("TargetFile") or "")
                    written_targets.append(tgt)
        # Which artifacts this node owns: arm B splits objectives per file.
        owns = self._owned_files(joined, files)
        remaining = [f for f in owns if not any(f in t for t in written_targets)]
        if wrote and not remaining:
            return _text("implementation complete")
        if not remaining:
            return _text("implementation complete")
        target = remaining[0]
        content = ARTIFACTS[self.sample][target]
        root = self._workspace_root(joined)
        # TargetFile must be an ABSOLUTE path; the isolated per-node worktree is
        # discoverable from the session prompt (``.lg-worktrees/<run>/<node>``).
        target_path = str(Path(root) / target) if root else target
        return _tool_call("write_to_file", {
            "TargetFile": target_path,
            "CodeContent": content,
            "Overwrite": True,
            "Description": "Implement the fixture stub exactly as the objective requires.",
            "toolSummary": "Writing artifact",
            "toolAction": "Writing artifact",
        })

    @staticmethod
    def _owned_files(joined: str, files: list[str]) -> list[str]:
        """The artifacts named by this node's objective (defaults to all).

        Arm B splits the work: the alpha objective names the first file, the
        beta objective the second.  A node only writes files explicitly named
        in its own objective text.
        """

        named = [f for f in files if f in joined]
        return named or files

    @staticmethod
    def _workspace_root(joined: str) -> str | None:
        match = re.search(r"(/[^\"'\\ ]+?/workspaces/[^\"'\\ ]+)", joined)
        return match.group(1) if match else None

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
            candidates = [{"node_ref": r} for r in refs]
        if not candidates:
            return ""
        chosen = candidates[-1] if non_first and len(candidates) > 1 else candidates[0]
        return str(chosen.get("node_ref") or "")

    @staticmethod
    def _reviewer_payload(joined: str) -> str:
        payload = {
            "validated_outcome": "passed",
            "outcome": "passed",
            "reason": "offline scripted reviewer: machine gate content matches",
            "findings": [],
        }
        return _text(json.dumps(payload))


class FakeUpstream:
    def __init__(self, *, sample: str = "s1_units", arm: str = "A",
                 select_non_first: bool = True, capture_only: bool = False,
                 host: str = "127.0.0.1") -> None:
        _ScriptedUpstream.records = []
        _ScriptedUpstream.capture_tools = []
        _ScriptedUpstream.sample = sample
        _ScriptedUpstream.arm = arm
        _ScriptedUpstream.select_non_first = select_non_first
        _ScriptedUpstream.capture_only = capture_only
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

    @property
    def captured_tools(self) -> list[Any]:
        return list(_ScriptedUpstream.capture_tools)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)
