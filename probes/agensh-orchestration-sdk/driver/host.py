#!/usr/bin/env python3
"""Experiment host: reuse the product AntigravityExecutor for one real SDK turn.

This module wires the *product* adapter (``ResourceCompiler`` +
``AntigravityExecutor`` + ``LocalAuthProxy`` + ``LocalOpenAIAgentConfig``) to
the experiment relay, on a per-turn isolated staging workspace, and returns a
fully-metered turn record.  It is an experiment host, not the product runtime.

Key rules implemented here:

* every logical turn really runs ``AntigravityExecutor.execute`` → real SDK
  agent loop → real file tools; file contents are never supplied by the driver
  and re-written on the model's behalf;
* the credential is read once into an ``InMemoryCredentialResolver`` and then
  removed from the process environment *before* any harness spawn, so harness
  children do not inherit it;
* a per-turn ``pre_tool_call_decide`` hook restricts file tools to the staging
  workspace root;
* params unification (max_tokens / thinking) happens only in the relay.

The structured ``finish`` JSON is recovered from the emitted ``finish`` tool
call (``output_string``), because ``ExecutorResult`` intentionally does not
carry the raw structured object.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

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
    ResourceCompiler,
    ToolRegistration,
    default_registry,
)
from lightgravity.store import FileStore  # noqa: E402

from hooks import make_path_guard_hook, make_tool_observer  # noqa: E402

CREDENTIAL_REF = "deepseek-api-key"
DEFAULT_MODEL = "deepseek-v4-flash"

# Secret-ish environment variable names removed from the process env before any
# harness spawn (values are never read or printed here).
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
    # Also drop any obvious AWS-style secrets without reading them.
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


class PlanSchema(pydantic.BaseModel):
    """Group-B one-shot planner plan."""

    plan: list[dict[str, Any]] = []
    interface_notes: str = ""
    findings: list[str] = []


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
        "You do not modify files. Read files with view_file if useful, then call finish with "
        "JSON matching the provided schema: "
        '{"plan": [{"worker": "w1", "objective": <text>, "files": [<relative path>]}, '
        '{"worker": "w2", ...}], "interface_notes": <text>, "findings": [<short text>]}.\n'
        "Assign disjoint files; at most one writer per file; never assign the same file to "
        "both workers. Do not write whole-file implementations for the workers."
    ),
}


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
        # No skills are attached: the calibration showed the SDK auto-exposes
        # list_skills/lookup_skill tools when skills exist, which wasted model
        # calls and truncated turns.  Both groups are identical here.
        # Tool resources: claim workers only get view-file at request time via allowed_tools.
        for tool_id, impl in (
            ("view-file", "view-file"),
            ("create-file", "create-file"),
            ("edit-file", "edit-file"),
        ):
            self._create("tool", tool_id, {"implementation": impl})
        # Hook resources.
        self._create("hook", "staging-guard", {"handler": "staging-guard", "events": ("pre_tool_call",)})
        self._create("hook", "tool-observer", {"handler": "tool-observer", "events": ("post_tool_call",)})
        # Agents.
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
                  tool_events: list[dict[str, Any]]) -> Any:
        return default_registry(
            hooks=[
                HookRegistration(
                    handler_id="staging-guard",
                    factory=lambda: make_path_guard_hook(staging_root, decisions),
                    events=("pre_tool_call",),
                    description="staging workspace path whitelist",
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
        max_model_calls: int = 4,
        max_tool_calls: int = 8,
    ) -> dict[str, Any]:
        """Run one logical SDK turn through the product executor."""

        decisions: list[dict[str, Any]] = []
        tool_events: list[dict[str, Any]] = []
        registry = self._registry(workspace, decisions, tool_events)
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
        t0 = time.monotonic()
        result = await executor.execute(request, emit)
        elapsed = time.monotonic() - t0
        turn = _turn_record(
            result=result, events=events, decisions=decisions, tool_events=tool_events,
            elapsed=elapsed, model_sent=compiled_holder.get("model"),
        )
        return turn


def _turn_record(
    *, result: Any, events: list[dict[str, Any]], decisions: list[dict[str, Any]],
    tool_events: list[dict[str, Any]], elapsed: float, model_sent: str | None,
) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []
    texts: list[str] = []
    for ev in events:
        if ev.get("type") == "adapter.tool_call":
            tool_calls.append({"name": ev.get("name"), "args": ev.get("args")})
        elif ev.get("type") == "adapter.text":
            texts.append(str(ev.get("text", "")))
    finish_payload = extract_finish_output(tool_calls)
    structured_repr = None
    for rec in result.check_records:
        if rec.name == "structured_output":
            structured_repr = rec.detail
    usage = result.usage.to_dict()
    return {
        "state": result.state,
        "summary": result.summary[:600],
        "stop_reason": result.stop_reason,
        "stop_confirmed": result.stop_confirmed,
        "failure": result.failure.to_dict() if result.failure else None,
        "usage": usage,
        "model": result.model,
        "upstream_model": result.upstream_model,
        "elapsed_seconds": round(elapsed, 3),
        "tool_calls": tool_calls,
        "tool_call_names": [t["name"] for t in tool_calls],
        "finish_payload": finish_payload,
        "finish_parse_error": None if finish_payload is not None else "no_finish_output",
        "structured_repr": structured_repr,
        "text": "".join(texts)[:2000],
        "hook_decisions": decisions,
        "tool_observations": tool_events,
        "session_ref": result.session_ref.to_dict() if result.session_ref else None,
        "model_sent": model_sent,
    }


def extract_finish_output(tool_calls: list[dict[str, Any]]) -> Any:
    """Return the parsed JSON from the last ``finish`` tool call, or ``None``."""

    for call in reversed(tool_calls):
        if call.get("name") != "finish":
            continue
        args = call.get("args") or {}
        raw = args.get("output_string")
        if raw is None:
            for key in ("output", "result", "content", "json", "response"):
                if isinstance(args.get(key), str):
                    raw = args[key]
                    break
        if raw is None:
            if isinstance(args, dict) and args:
                return args
            continue
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
    return None


__all__ = ["SdkHost", "read_and_purge_secret", "extract_finish_output",
           "ClaimSchema", "EditSchema", "PlanSchema", "CREDENTIAL_REF", "DEFAULT_MODEL"]
