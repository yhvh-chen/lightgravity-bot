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

State machine / termination (LG-032 cohort-ready fix)
-----------------------------------------------------
The previous revision classified a request as a *selection* phase whenever the
restricted ``discover_and_request_claim`` tool appeared in the exposed tool
list.  That is wrong: the product's phase-2 **execution** session still carries
the claim tool schema, so every execution request was mis-read as a selection,
re-issued ``discover_and_request_claim`` forever, and burned the whole
per-attempt generation cap before any artifact was written (observed: 48/48
selection requests, then the execution session hit the pre-forward ``429``).

The fake now discriminates phases exactly like the mature R1 real-SDK fake:
the product-frozen selection prompt carries the sentinel ``PHASE 1``; a
verify node is a session that exposes ``view_file`` but **no** write tool; and
everything else is an execution node.  Every phase has an explicit, *bounded*
termination condition derived from the conversation itself (not from wall
clock), so a node can never spin indefinitely:

* selection -> ``discover`` (once) -> ``claim`` (once, a legal non-first
  candidate) -> final text after a ``granted`` receipt; a refused/revoked claim
  also terminates after one refusal instead of retrying forever.
* execution -> one ``write_to_file`` per artifact the node's own objective
  names -> final text once all owned artifacts are written; bounded by the
  number of owned artifacts.
* verify    -> one ``view_file`` of the first upstream artifact -> final text.
* reviewer  -> a passing structured outcome.

No product cap is relaxed, no proxy budget is bypassed, no model permission is
changed and no authorized root is widened: the fake only decides *what the
model would have said*.
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

#: Write tools the pinned SDK may expose (any one proves an execution node).
_WRITE_TOOLS = frozenset(
    {"write_to_file", "replace_file_content", "create_file", "edit_file"}
)
#: The product-frozen sentinel that marks a phase-1 selection session.
_SELECTION_SENTINEL = "PHASE 1"
#: Hard cap on fake-driven tool calls per node session (bounded termination).
_MAX_TOOL_CALLS = 6


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

        phase = self._classify(tool_names, joined)
        # Hard per-node bound: a node session may issue at most ``_MAX_TOOL_CALLS``
        # tool calls before the fake ends the turn with a final text.  This makes
        # an unparseable receipt a bounded, honest stop instead of an unbounded
        # loop that would burn the product's pre-forward generation cap (the
        # exact failure mode this revision fixes).
        if len(self._assistant_tool_calls(messages)) >= _MAX_TOOL_CALLS:
            payload = _text(f"{phase} complete (bounded tool-call budget reached)")
            self._record(phase, joined, tool_names, messages)
            self._send(payload + "data: [DONE]\n\n")
            return
        if phase == "selection":
            payload = self._selection(messages)
        elif phase == "verify":
            payload = self._verify(messages)
        else:
            payload = self._execute(messages)
        self._record(phase, joined, tool_names, messages)
        self._send(payload + "data: [DONE]\n\n")

    # ------------------------------------------------------------- internals
    @staticmethod
    def _classify(tool_names: list[Any], joined: str) -> str:
        """Which product phase this request is, by product-frozen signals only.

        * selection carries the frozen ``PHASE 1`` sentinel;
        * verify exposes ``view_file`` and **no** write tool;
        * everything else is an execution node.
        """

        if _SELECTION_SENTINEL in joined:
            return "selection"
        write_capable = any(name in _WRITE_TOOLS for name in tool_names)
        if not write_capable and "view_file" in tool_names:
            return "verify"
        return "execution"

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

    # --------------------------------------------------------- tool receipts
    @staticmethod
    def _assistant_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """All tool calls the (fake) assistant already issued in this session."""

        calls: list[dict[str, Any]] = []
        for m in messages:
            if m.get("role") != "assistant":
                continue
            for call in m.get("tool_calls") or []:
                if isinstance(call, dict):
                    calls.append(call)
        return calls

    @staticmethod
    def _called_tools(messages: list[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        for call in _ScriptedUpstream._assistant_tool_calls(messages):
            fn = call.get("function")
            if isinstance(fn, dict) and fn.get("name"):
                names.append(str(fn["name"]))
        return names

    @staticmethod
    def _tool_result_texts(messages: list[dict[str, Any]]) -> list[str]:
        """The raw text of every ``role: tool`` result in the conversation."""

        return [str(m.get("content") or "") for m in messages if m.get("role") == "tool"]

    @staticmethod
    def _last_receipt_state(messages: list[dict[str, Any]]) -> str | None:
        """The ``state`` of the most recent claim receipt, if any.

        The pinned SDK renders the claim tool's dict result inside a
        ``role: tool`` message as ``... ```json\\n{"ok":..., "state": "..."}``` ``.
        Parse that JSON rather than substring-matching a key format.
        """

        for text in reversed(_ScriptedUpstream._tool_result_texts(messages)):
            for block in re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL):
                try:
                    payload = json.loads(block)
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(payload, dict) and "state" in payload:
                    return str(payload.get("state"))
        return None

    # ------------------------------------------------------- phase handlers
    def _selection(self, messages: list[dict[str, Any]]) -> str:
        """Bounded selection: discover -> claim -> finish (never spins)."""

        state = self._last_receipt_state(messages)
        if state == "granted":
            return _text("selection complete")
        if state in {"rejected", "refused"}:
            # A refused claim must terminate the node, not re-loop: the program
            # will honestly record a no-claim slot outcome.
            return _text("selection refused; no authorized candidate claimed")
        if state == "discovered":
            node_ref = self._pick_node_from_messages(messages, self.select_non_first)
            if not node_ref:
                return _text("no candidate available")
            return _tool_call(
                "discover_and_request_claim",
                {"node_ref": node_ref, "request_id": "req-select"},
            )
        return _tool_call("discover_and_request_claim", {})

    def _verify(self, messages: list[dict[str, Any]]) -> str:
        if "view_file" in self._called_tools(messages):
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

    def _execute(self, messages: list[dict[str, Any]]) -> str:
        joined = json.dumps(messages)
        files = list(ARTIFACTS.get(self.sample, {}).keys())
        if not files:
            return _text("implementation complete")
        # Which artifacts this node owns: arm B splits objectives per file, so a
        # node writes only files explicitly named in its own objective.
        owns = self._owned_files(joined, files)
        written_targets: dict[str, int] = {}
        for call in self._assistant_tool_calls(messages):
            fn = call.get("function")
            if not isinstance(fn, dict) or fn.get("name") not in _WRITE_TOOLS:
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            tgt = str(args.get("TargetFile") or args.get("AbsolutePath") or "")
            for owned in owns:
                if owned in tgt:
                    written_targets[owned] = written_targets.get(owned, 0) + 1
        remaining = [f for f in owns if written_targets.get(f, 0) == 0]
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

    # ------------------------------------------------------------- selection
    def _pick_node_from_messages(self, messages: list[dict[str, Any]], non_first: bool) -> str:
        """The non-first (or first) legal candidate from the discovery receipt."""

        for text in reversed(self._tool_result_texts(messages)):
            for block in re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL):
                try:
                    payload = json.loads(block)
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(payload, dict):
                    continue
                candidates = payload.get("candidates")
                if not isinstance(candidates, list) or not candidates:
                    continue
                chosen = candidates[-1] if non_first and len(candidates) > 1 else candidates[0]
                if isinstance(chosen, dict):
                    return str(chosen.get("node_ref") or "")
        # Fallback: pull the candidate refs out of the raw discovery text.
        refs = re.findall(r'"node_ref":\s*"([^"]+)"', "\n".join(self._tool_result_texts(messages)))
        if not refs:
            return ""
        return refs[-1] if non_first and len(refs) > 1 else refs[0]

    @staticmethod
    def _owned_files(joined: str, files: list[str]) -> list[str]:
        """The artifacts this node is asked to write.

        A node owns the files it is explicitly told to *overwrite*.  Arm B
        splits the work: the alpha objective says ``overwrite src/shapes.py`` and
        the beta objective says ``overwrite src/report.py`` -- even though beta
        also *mentions* ``src/shapes.py`` in a dependency clause ("depends on
        part A's src/shapes.py"), which must NOT make beta write it.  Arm A's
        combined objective says ``OVERWRITE them`` with no per-file
        ``overwrite <path>`` phrase, so it falls back to every artifact named.
        """

        explicit: list[str] = []
        for match in re.finditer(r"overwrite\s+([^\s,;\"']+\.py)", joined, re.IGNORECASE):
            target = match.group(1)
            for f in files:
                if f in target and f not in explicit:
                    explicit.append(f)
        if explicit:
            return explicit
        named = [f for f in files if f in joined]
        return named or files

    @staticmethod
    def _workspace_root(joined: str) -> str | None:
        # Prefer the isolated per-node worktree (execution/verify); fall back to
        # any authorized workspace path (selection scratch).  The product always
        # discloses the active workspace in the SDK ``user_information`` block.
        match = re.search(r"(/[^\"'\\ \n]+?/workspaces/[^\"'\\ \n]+)", joined)
        return match.group(1) if match else None

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
