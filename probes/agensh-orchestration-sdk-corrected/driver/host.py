#!/usr/bin/env python3
"""Corrected experiment host: reuse the product AntigravityExecutor for one real
SDK turn, with lossless structured output and positive per-turn stop evidence.

Corrections vs the first attempt
--------------------------------
* **Lossless finish**: the product executor truncates emitted tool-argument
  strings to 2000 chars (``executor._bounded``), so the emitted ``finish``
  event must never be the control source.  A ``pre_tool_call`` hook captures the
  full, untruncated tool call as handed over by the SDK itself; the driver reads
  the structured output from there (native SDK message), with the SDK native
  session DB as an offline cross-check.  The emitted, bounded payload is kept
  *only* as a diagnostic and compared against the full one.
* **Strict plan schema**: ``PlanItem``/``PlanSchema`` use a pydantic submodel
  with ``extra="forbid"``, ``worker: Literal["w1","w2"]``, non-empty short
  ``objective`` and at most one file per assignment.  Aliases such as
  ``assignee``/``assigned_files`` are rejected by the model *and* the SDK.
* **Lease-aware guard**: writes are limited to the held lease path; a reviewer
  has no write permission.  Unknown file arguments fail closed.
* **Positive stop evidence**: the loopback proxy is wrapped (via the public
  ``proxy_factory`` hook) so ``proxy.stop()`` return value / post-stop running
  state are recorded; the ``auth_proxy_stopped`` check record, the harness PID
  set before/after and the port state are all captured per turn.  A turn without
  positive stop evidence is marked ``unknown`` and must not release its lease or
  pass the gate.

No product source file is modified; the only observation shims live here.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Literal

# --- product import bootstrap (worktree backend) --------------------------
_HERE = Path(__file__).resolve()
_PROBE_ROOT = _HERE.parents[1]
_REPO_ROOT = _HERE.parents[3]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pydantic  # noqa: E402

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    ExecuteRequest,
    HookRegistration,
    InMemoryCredentialResolver,
    LocalAuthProxy,
    ResourceCompiler,
    ToolRegistration,
    default_registry,
)
from lightgravity.store import FileStore  # noqa: E402

from hooks import make_path_guard_hook, make_tool_observer  # noqa: E402

CREDENTIAL_REF = "deepseek-api-key"
DEFAULT_MODEL = "deepseek-v4-flash"

_SECRET_ENV_NAMES = (
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
)


def read_and_purge_secret(name: str = "DEEPSEEK_API_KEY") -> str:
    """Read a credential into memory and remove it (and peers) from ``os.environ``."""

    value = os.environ.get(name, "")
    for var in _SECRET_ENV_NAMES:
        os.environ.pop(var, None)
    for var in list(os.environ):
        if var.startswith("AWS_") and ("SECRET" in var or "TOKEN" in var):
            os.environ.pop(var, None)
    return value


# --- response schemas -----------------------------------------------------
class ClaimSchema(pydantic.BaseModel):
    """Phase-1 proposal: optional single-file claim + short peer message."""

    claim: str | None = None
    message: str = ""
    findings: list[str] = []


class EditSchema(pydantic.BaseModel):
    """Phase-2 result: what the worker did (files are written by SDK tools)."""

    summary: str = ""
    findings: list[str] = []


class PlanItem(pydantic.BaseModel):
    """One worker assignment in a strict planner plan."""

    model_config = pydantic.ConfigDict(extra="forbid")

    worker: Literal["w1", "w2"]
    objective: str = pydantic.Field(min_length=1, max_length=400)
    files: list[str] = pydantic.Field(default_factory=list, max_length=1)


class PlanSchema(pydantic.BaseModel):
    """Group-B one-shot planner plan (strict submodel; extra keys rejected)."""

    model_config = pydantic.ConfigDict(extra="forbid")

    plan: list[PlanItem] = pydantic.Field(min_length=1, max_length=4)
    interface_notes: str = pydantic.Field(default="", max_length=600)
    findings: list[str] = pydantic.Field(default_factory=list, max_length=3)


_AGENT_BODIES = {
    "claim-worker": (
        "You are a worker in a controlled two-worker file-editing collaboration. "
        "You may read files with the view_file tool. You must not write any file. "
        "Finish by calling finish with JSON matching the provided schema: "
        '{"claim": <relative path or null>, "message": <short text>, "findings": [<short text>]}.\n'
        "Rules: at most one claim; claim only a writable file that no peer already claimed; "
        "hold the current file sha256 only as information (never invent content). "
        "Keep message <= 240 chars and each finding <= 160 chars.\n"
        "Do not modify or suggest modifying TASK/RUN/subtask/events/acceptance. "
        "Never read or write anything outside your workspace."
    ),
    "edit-worker": (
        "You are a worker in a controlled two-worker file-editing collaboration. "
        "You may read files with view_file, and write files with the create/edit file tools. "
        "If and only if you hold a writable lease for a file, implement the objective by "
        "actually writing that file with the file tools; otherwise only review. "
        "Never write a file you do not hold a lease for. "
        "Finish by calling finish with JSON matching the provided schema: "
        '{"summary": <short text>, "findings": [<short text>]}.\n'
        "Do not modify or suggest modifying TASK/RUN/subtask/events/acceptance. "
        "Never read or write anything outside your workspace."
    ),
    "planner": (
        "You are an orchestration planner for a controlled two-worker collaboration. "
        "You do not modify files (you have read-only tools). Read files with view_file if "
        "useful, then call finish with JSON matching the exactly-provided schema:\n"
        '{"plan": [{"worker": "w1"|"w2", "objective": <non-empty short text>, '
        '"files": [<relative path or empty>]}, ...], "interface_notes": <short text>, '
        '"findings": [<short text>]}\n'
        "Absolute rules (the program enforces all of them):\n"
        "- exactly the two workers w1 and w2 appear, each exactly once;\n"
        "- every writable file listed in the user message is assigned to exactly one worker;\n"
        "- each assignment carries AT MOST ONE file;\n"
        "- a worker assigned no file must use an empty list [] and is the reviewer;\n"
        "- a file is never assigned to both workers; no additional JSON keys are allowed;\n"
        "- objective must be a short, non-empty instruction; do not write whole-file "
        "implementations for the workers.\n"
    ),
}


# --- lossless finish extraction ------------------------------------------
def parse_finish_args(args: Any) -> tuple[Any, str | None]:
    """Parse a ``finish`` tool-call args dict into the structured object.

    Returns ``(payload, error)`` where error is ``None`` on success.
    """

    if not isinstance(args, dict):
        return None, "invalid_args"
    raw = args.get("output_string")
    if raw is None:
        for key in ("output", "result", "content", "json", "response"):
            if isinstance(args.get(key), str):
                raw = args[key]
                break
        if raw is None:
            return (args, None) if args else (None, "empty_args")
    if isinstance(raw, (dict, list)):
        return raw, None
    if not isinstance(raw, str):
        return None, "invalid_args"
    try:
        return json.loads(raw), None
    except (TypeError, ValueError):
        return None, "invalid_json"


def extract_finish_from_calls(captured_calls: list[dict[str, Any]]) -> tuple[Any, str | None, dict | None]:
    """Return ``(payload, error, source_call)`` from captured full tool calls."""

    for call in reversed(captured_calls or []):
        if str(call.get("name")) != "finish":
            continue
        payload, err = parse_finish_args(call.get("args") or {})
        return payload, err, call
    return None, "no_finish_call", None


def extract_finish_output(tool_calls: list[dict[str, Any]]) -> Any:
    """Legacy helper: parsed JSON from the last emitted ``finish`` tool call."""

    for call in reversed(tool_calls or []):
        if call.get("name") != "finish":
            continue
        payload, err = parse_finish_args(call.get("args") or {})
        return payload if err is None else None
    return None


# --- stop observation -----------------------------------------------------
class ObservedProxy:
    """Transparent wrapper around ``LocalAuthProxy`` that records stop results.

    Injected through the product executor's public ``proxy_factory`` hook, so no
    product source is changed.
    """

    def __init__(self, inner: LocalAuthProxy) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "stop_events", [])
        object.__setattr__(self, "call_records_snapshot", [])

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_inner"), name)

    def stop(self, *args: Any, **kwargs: Any) -> bool:
        inner = object.__getattribute__(self, "_inner")
        returned = inner.stop(*args, **kwargs)
        try:
            running = bool(inner.is_running)
        except Exception:  # noqa: BLE001
            running = None
        try:
            recs = inner.call_records()
        except Exception:  # noqa: BLE001
            recs = []
        self.stop_events.append({"returned": bool(returned), "is_running_after": running})
        object.__setattr__(self, "call_records_snapshot", recs)
        return returned


def _make_observed_proxy_factory(sink: list[ObservedProxy]) -> Any:
    def factory(credential: Any, upstream: str, max_calls: int) -> ObservedProxy:
        proxy = ObservedProxy(
            LocalAuthProxy(
                credential=credential,
                upstream_url=upstream,
                max_calls=max_calls,
                timeout=90.0,
                allow_loopback_upstream=True,
            )
        )
        sink.append(proxy)
        return proxy

    return factory


# --- experiment-only close observer --------------------------------------
# The wrapper is installed once; it appends into whatever sink is current for the
# running turn (turns are sequential, so a single module-level pointer is safe).
_CURRENT_CLOSE_SINK: list[list[dict[str, Any]]] = []


def _install_close_observer(sink: list[dict[str, Any]]) -> bool:
    """Wrap ``_ExecutionHandle.ensure_closed`` in-memory to record its result."""

    _CURRENT_CLOSE_SINK.clear()
    _CURRENT_CLOSE_SINK.append(sink)
    try:
        from lightgravity.adapter import executor as _exec_mod
        handle_cls = _exec_mod._ExecutionHandle  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return False
    if getattr(handle_cls, "_agensh_close_observer", False):
        return True
    original = handle_cls.ensure_closed

    async def wrapped(self: Any) -> bool:
        result = await original(self)
        try:
            if _CURRENT_CLOSE_SINK:
                _CURRENT_CLOSE_SINK[-1].append({"ensure_closed_returned": bool(result)})
        except Exception:  # noqa: BLE001
            pass
        return result

    handle_cls.ensure_closed = wrapped  # type: ignore[assignment]
    handle_cls._agensh_close_observer = True  # type: ignore[attr-defined]
    return True


def _localharness_pids() -> list[int]:
    """PIDs whose *executable* is the SDK ``localharness`` binary.

    Matching on ``/proc/<pid>/cmdline`` is unsafe: an unrelated process (e.g. a
    shell running a command that merely mentions the word) would be counted.
    We resolve ``/proc/<pid>/exe`` and compare the basename instead.
    """

    pids: list[int] = []
    proc = Path("/proc")
    if not proc.exists():
        return pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            exe = os.readlink(entry / "exe")
        except OSError:
            continue
        if os.path.basename(exe) == "localharness":
            try:
                pids.append(int(entry.name))
            except ValueError:
                continue
    return sorted(pids)


def _port_open(port: int | None) -> bool | None:
    if not port:
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex(("127.0.0.1", int(port))) == 0
    except OSError:
        return None


class SdkHost:
    """Per-experiment product-adapter host bound to one relay."""

    def __init__(self, data_dir: Path, relay_base_url: str, workspace_root: Path | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.workspace_root = Path(workspace_root) if workspace_root else (self.data_dir / "workspaces")
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.store = FileStore(self.data_dir, self.workspace_root)
        self.relay_base_url = relay_base_url
        self._build_resources()
        self.artifacts = DirectoryArtifactSink(self.data_dir / "artifacts")

    # ------------------------------------------------------------- resources
    def _create(self, kind: str, entity_id: str, fields: dict[str, Any], body: str = "") -> None:
        fields.setdefault("title", entity_id)
        fields.setdefault("enabled", True)
        self.store.create(kind, entity_id, fields, actor="agensh-sdk", request_id=f"req-{kind}-{entity_id}")

    def _build_resources(self) -> None:
        self._create(
            "connection", "primary",
            {
                "backend": "openai-compat",
                "model": DEFAULT_MODEL,
                "credential_ref": CREDENTIAL_REF,
                "base_url": self.relay_base_url,
            },
        )
        self._create("conversation", "task-worker",
                     {"session_continuation_mode": "create_or_resume", "agent_behavior": "autonomous"})
        for tool_id, impl in (
            ("view-file", "view-file"),
            ("create-file", "create-file"),
            ("edit-file", "edit-file"),
        ):
            self._create("tool", tool_id, {"implementation": impl})
        self._create("hook", "staging-guard", {"handler": "staging-guard", "events": ("pre_tool_call",)})
        self._create("hook", "tool-observer", {"handler": "tool-observer", "events": ("post_tool_call",)})
        self._create(
            "agent", "claim-worker",
            {
                "connection_ref": "primary",
                "conversation_ref": "task-worker",
                "skills": {"source": "inline", "refs": []},
                "tool_refs": ["view-file"],
                "hook_refs": ["staging-guard"],
                "mcp_refs": [], "trigger_refs": [], "subagents": [],
            },
            body=_AGENT_BODIES["claim-worker"],
        )
        self._create(
            "agent", "edit-worker",
            {
                "connection_ref": "primary",
                "conversation_ref": "task-worker",
                "skills": {"source": "inline", "refs": []},
                "tool_refs": ["view-file", "create-file", "edit-file"],
                "hook_refs": ["staging-guard", "tool-observer"],
                "mcp_refs": [], "trigger_refs": [], "subagents": [],
            },
            body=_AGENT_BODIES["edit-worker"],
        )
        self._create(
            "agent", "planner",
            {
                "connection_ref": "primary",
                "conversation_ref": "task-worker",
                "skills": {"source": "inline", "refs": []},
                "tool_refs": ["view-file"],
                "hook_refs": ["staging-guard"],
                "mcp_refs": [], "trigger_refs": [], "subagents": [],
            },
            body=_AGENT_BODIES["planner"],
        )

    # ---------------------------------------------------------------- registry
    def _registry(self, staging_root: Path, decisions: list[dict[str, Any]],
                  tool_events: list[dict[str, Any]], captured_calls: list[dict[str, Any]],
                  write_lease_paths: set[str]) -> Any:
        return default_registry(
            hooks=[
                HookRegistration(
                    handler_id="staging-guard",
                    factory=lambda: make_path_guard_hook(
                        staging_root, decisions,
                        write_lease_paths=frozenset(write_lease_paths),
                        captured_calls=captured_calls,
                    ),
                    events=("pre_tool_call",),
                    description="staging workspace + lease path guard",
                ),
                HookRegistration(
                    handler_id="tool-observer",
                    factory=lambda: make_tool_observer(tool_events),
                    events=("post_tool_call",),
                    description="tool result observer",
                ),
            ],
            tools=[
                ToolRegistration(handler_id="view-file", permission="file.read", sdk_tool="view_file"),
                ToolRegistration(handler_id="create-file", permission="file.write", sdk_tool="create_file"),
                ToolRegistration(handler_id="edit-file", permission="file.write", sdk_tool="edit_file"),
            ],
        )

    # ------------------------------------------------------------------ turn
    async def run_turn(
        self,
        *,
        credential: str,
        agent_ref: str,
        workspace: Path,
        objective: str,
        response_schema: Any,
        allowed_tools: tuple[str, ...],
        timeout_seconds: float,
        save_dir: Path | None = None,
        conversation_id: str | None = None,
        max_model_calls: int = 6,
        max_tool_calls: int = 8,
        write_lease: str | None = None,
    ) -> dict[str, Any]:
        """Run one logical SDK turn through the product executor."""

        workspace = Path(workspace).resolve()
        decisions: list[dict[str, Any]] = []
        tool_events: list[dict[str, Any]] = []
        captured_calls: list[dict[str, Any]] = []
        write_lease_paths: set[str] = set()
        if write_lease:
            write_lease_paths.add((workspace / write_lease).resolve().as_posix())
        registry = self._registry(workspace, decisions, tool_events, captured_calls, write_lease_paths)

        observed_proxies: list[ObservedProxy] = []
        close_sink: list[dict[str, Any]] = []
        close_observed = _install_close_observer(close_sink)

        compiled_holder: dict[str, Any] = {}
        executor = AntigravityExecutor(
            self.store,
            ResourceCompiler(self.store, registry=registry),
            credential_resolver=InMemoryCredentialResolver({CREDENTIAL_REF: credential}),
            artifacts=self.artifacts,
            workspace_root=self.workspace_root,
            max_proxy_calls=max_model_calls,
            model_calls_cap=None,
            upstream_timeout=90.0,
            allow_loopback_upstream=True,
            proxy_factory=_make_observed_proxy_factory(observed_proxies),
        )
        events: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)
            if event.get("type") == "adapter.session_requested":
                compiled_holder["model"] = event.get("model")

        request = ExecuteRequest(
            task_id="agensh-sdk",
            run_id=workspace.name,
            subtask_id=f"{agent_ref}-{int(time.time() * 1000)}",
            agent_ref=agent_ref,
            workspace_path=str(workspace),
            objective=objective,
            allowed_tools=allowed_tools,
            budget={"max_model_calls": max_model_calls, "max_tool_calls": max_tool_calls},
            timeout_seconds=timeout_seconds,
            save_dir=str(save_dir) if save_dir else None,
            conversation_id=conversation_id,
            response_schema=response_schema,
        )
        harness_before = _localharness_pids()
        t0 = time.monotonic()
        result = await executor.execute(request, emit)
        elapsed = time.monotonic() - t0
        harness_after = _localharness_pids()

        observed = observed_proxies[-1] if observed_proxies else None
        port = getattr(observed, "port", None) if observed is not None else None
        port_open_after = _port_open(port)
        stop_events = list(getattr(observed, "stop_events", [])) if observed is not None else []

        return _turn_record(
            result=result, events=events, decisions=decisions, tool_events=tool_events,
            captured_calls=captured_calls, elapsed=elapsed,
            model_sent=compiled_holder.get("model"),
            stop_events=stop_events, port=port, port_open_after=port_open_after,
            harness_before=harness_before, harness_after=harness_after,
            close_sink=close_sink, close_observed=close_observed,
            save_dir=save_dir, workspace=workspace, write_lease=write_lease,
        )


def _turn_record(
    *, result: Any, events: list[dict[str, Any]], decisions: list[dict[str, Any]],
    tool_events: list[dict[str, Any]], captured_calls: list[dict[str, Any]],
    elapsed: float, model_sent: str | None, stop_events: list[dict[str, Any]],
    port: int | None, port_open_after: bool | None, harness_before: list[int],
    harness_after: list[int], close_sink: list[dict[str, Any]], close_observed: bool,
    save_dir: Path | None, workspace: Path, write_lease: str | None,
) -> dict[str, Any]:
    emitted_calls: list[dict[str, Any]] = []
    texts: list[str] = []
    for ev in events:
        if ev.get("type") == "adapter.tool_call":
            emitted_calls.append({"name": ev.get("name"), "args": ev.get("args")})
        elif ev.get("type") == "adapter.text":
            texts.append(str(ev.get("text", "")))

    payload, finish_err, source_call = extract_finish_from_calls(captured_calls)
    finish_source = "hook" if payload is not None or finish_err != "no_finish_call" else None
    finish_chars = None if payload is None else len(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    finish_sha = (None if payload is None else
                  hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest())

    # Offline cross-check only: read the full payload back from the native DB.
    db_payload = None
    if save_dir is not None:
        try:
            from sessiondb import extract_best_finish_payload
            dbs = sorted(Path(save_dir).glob("*.db"))
            if dbs:
                db_payload = extract_best_finish_payload(dbs[0])
        except Exception:  # noqa: BLE001
            db_payload = None

    emitted_payload = extract_finish_output(emitted_calls)
    emitted_chars = None if emitted_payload is None else len(
        json.dumps(emitted_payload, ensure_ascii=False, sort_keys=True))

    check_records = [
        {"name": getattr(rec, "name", None), "status": getattr(rec, "status", None),
         "detail": str(getattr(rec, "detail", ""))}
        for rec in (getattr(result, "check_records", ()) or ())
    ]
    auth_proxy_check = next((r for r in check_records if r["name"] == "auth_proxy_stopped"), None)

    stop_positive = bool(
        (stop_events and stop_events[-1].get("returned") is True
         and stop_events[-1].get("is_running_after") is False)
        or (auth_proxy_check and auth_proxy_check.get("status") == "passed")
        or getattr(result, "stop_confirmed", None) is True
    )
    harness_gone = set(harness_after).issubset(set(harness_before))
    stop_evidence = {
        "proxy_stop_events": stop_events,
        "proxy_port": port,
        "port_open_after": port_open_after,
        "auth_proxy_stopped_check": auth_proxy_check,
        "stop_confirmed_field": getattr(result, "stop_confirmed", None),
        "agent_close_observed": close_observed,
        "agent_close_returns": [c.get("ensure_closed_returned") for c in close_sink],
        "harness_pids_before": harness_before,
        "harness_pids_after": harness_after,
        "harness_gone_after": harness_gone,
        "workspace": str(workspace),
        "write_lease": write_lease,
        "positive": stop_positive and harness_gone and port_open_after in (False, None),
        "status": ("confirmed" if (stop_positive and harness_gone and port_open_after in (False, None))
                   else "unknown"),
    }

    return {
        "state": result.state,
        "summary": result.summary[:600],
        "stop_reason": str(result.stop_reason),
        "stop_confirmed": result.stop_confirmed,
        "failure": result.failure.to_dict() if result.failure else None,
        "usage": result.usage.to_dict(),
        "model": result.model,
        "upstream_model": result.upstream_model,
        "elapsed_seconds": round(elapsed, 3),
        "tool_calls": emitted_calls,
        "tool_call_names": [t["name"] for t in emitted_calls],
        "captured_calls": captured_calls,
        "captured_call_names": [c["name"] for c in captured_calls],
        "finish_payload": payload,
        "finish_source": finish_source,
        "finish_parse_error": finish_err,
        "finish_payload_chars": finish_chars,
        "finish_payload_sha256": finish_sha,
        "emitted_finish_payload": emitted_payload,
        "emitted_finish_chars": emitted_chars,
        "emitted_truncated": bool(
            emitted_payload is not None and payload is not None
            and json.dumps(emitted_payload, ensure_ascii=False, sort_keys=True)
            != json.dumps(payload, ensure_ascii=False, sort_keys=True)
        ),
        "session_db_finish_chars": (None if db_payload is None else
                                    len(json.dumps(db_payload, ensure_ascii=False, sort_keys=True))),
        "session_db_matches_hook": bool(
            payload is not None and db_payload is not None
            and json.dumps(payload, ensure_ascii=False, sort_keys=True)
            == json.dumps(db_payload, ensure_ascii=False, sort_keys=True)
        ),
        "structured_repr": next((r["detail"] for r in check_records if r["name"] == "structured_output"), None),
        "check_records": check_records,
        "text": "".join(texts)[:2000],
        "hook_decisions": decisions,
        "tool_observations": tool_events,
        "stop_evidence": stop_evidence,
        "session_ref": result.session_ref.to_dict() if result.session_ref else None,
        "model_sent": model_sent,
    }


__all__ = [
    "SdkHost", "read_and_purge_secret", "extract_finish_output",
    "extract_finish_from_calls", "parse_finish_args", "ObservedProxy",
    "ClaimSchema", "EditSchema", "PlanSchema", "PlanItem", "CREDENTIAL_REF",
    "DEFAULT_MODEL",
]
