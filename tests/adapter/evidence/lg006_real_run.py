#!/usr/bin/env python3
"""LG-006 real-model evidence run (bounded).

Runs the *product* executor (``AntigravityExecutor`` + ``LocalAuthProxy``)
against the real DeepSeek upstream, through the pinned Antigravity SDK, using a
temporary authorized workspace.  Real model calls are hard-bounded by
``--max-calls``.  The raw credential is read from ``DEEPSEEK_API_KEY`` and is
never written to the evidence file.

Run:
    DEEPSEEK_API_KEY=... uv run python tests/adapter/evidence/lg006_real_run.py

The file is not a pytest test; it is an evidence harness.  It writes
``lg006-real-evidence.json`` next to itself.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "backend"))
sys.path.insert(0, str(_REPO / "tests" / "adapter"))

import helpers  # noqa: E402  (path bootstrap above)

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    EnvCredentialResolver,
    ExecuteRequest,
    ExecutionRef,
    ResourceCompiler,
    SDK_PINNED_VERSION,
    mask_values,
)
from lightgravity.store import FileStore  # noqa: E402

EVIDENCE_PATH = Path(__file__).resolve().parent / "lg006-real-evidence.json"
UPSTREAM = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-flash"
CREDENTIAL_REF = "deepseek-api-key"


def _find_localharness_pids() -> list[int]:
    pids: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "localharness" in cmdline:
            pids.append(int(entry.name))
    return sorted(pids)


def _shrink(value: Any, *, limit: int = 1200) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...[truncated]"
    if isinstance(value, dict):
        return {key: _shrink(item, limit=limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_shrink(item, limit=limit) for item in value]
    return value


class _Evidence:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def scenario(
        self,
        name: str,
        *,
        request: ExecuteRequest,
        result: Any,
        events: list[dict[str, Any]],
        proxy_calls: list[dict[str, Any]],
        wall_seconds: float,
        error: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "wall_seconds": round(wall_seconds, 2),
            "request": {
                "task_id": request.task_id,
                "run_id": request.run_id,
                "subtask_id": request.subtask_id,
                "objective": request.objective,
                "acceptance_criteria": list(request.acceptance_criteria),
                "workspace_path": request.workspace_path,
                "budget": dict(request.budget),
                "timeout_seconds": request.timeout_seconds,
                "agent_ref": request.agent_ref,
            },
            "result": result.to_dict() if result is not None else None,
            "events": _shrink(events),
            "proxy_calls": proxy_calls,
            "error": error,
        }
        return mask_values(payload, [self.secret])


def _build_environment(root: Path) -> tuple[FileStore, Path, Path]:
    data = root / "data"
    workspace_root = data / "workspaces"
    store = FileStore(data, workspace_root)
    helpers.build_basic_environment(
        store,
        base_url=UPSTREAM,
        credential_ref=CREDENTIAL_REF,
    )
    helpers.create_resource(store, "tool", "create-file", implementation="create-file")
    store.write(
        "connection",
        "primary",
        {
            "backend": "openai-compat",
            "model": MODEL,
            "credential_ref": CREDENTIAL_REF,
            "base_url": UPSTREAM,
        },
        expected_revision=0,
        actor="lg006-evidence",
    )
    helpers.build_agent(
        store,
        skills_source="inline",
        tool_refs=["view-file", "create-file", "edit-file"],
    )
    workspace = workspace_root / "lg006-ws"
    workspace.mkdir(parents=True, exist_ok=True)
    return store, workspace_root, workspace


def _verdict_schema() -> Any:
    import pydantic

    class _Verdict(pydantic.BaseModel):
        summary: str
        risk_level: int

    return _Verdict


async def _run_scenario(
    executor: AntigravityExecutor,
    evidence: _Evidence,
    name: str,
    request: ExecuteRequest,
    *,
    cancel_after: float | None = None,
) -> tuple[Any, dict[str, Any]]:
    events: list[dict[str, Any]] = []
    execution_id: dict[str, str] = {}

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if event.get("type") == "adapter.execution_started":
            ref = event.get("execution") or {}
            if isinstance(ref.get("execution_id"), str):
                execution_id["value"] = ref["execution_id"]

    started = time.monotonic()
    error: str | None = None
    result: Any = None
    proxy_calls: list[dict[str, Any]] = []
    try:
        if cancel_after is None:
            result = await executor.execute(request, emit)
        else:
            task = asyncio.create_task(executor.execute(request, emit))
            deadline = time.monotonic() + 30
            while "value" not in execution_id and time.monotonic() < deadline:
                await asyncio.sleep(0.02)
            # Cancel only once the turn is actually streaming, so the stop is a
            # genuine mid-flight cancellation rather than a lost race.
            while time.monotonic() < deadline and not any(
                event.get("type") in ("adapter.text", "adapter.tool_call") for event in events
            ):
                await asyncio.sleep(0.02)
            await asyncio.sleep(cancel_after)
            cancel_result = await executor.cancel(
                ExecutionRef(execution_id=execution_id.get("value", ""))
            )
            result = await task
            events.append({"type": "adapter.cancel_result", **cancel_result.to_dict()})
    except Exception as exc:  # noqa: BLE001 - evidence must record real failures
        error = f"{type(exc).__name__}: {exc}"

    finished = [event for event in events if event.get("type") == "adapter.execution_finished"]
    if finished:
        proxy_calls = finished[-1].get("upstream_calls") or []
    record = evidence.scenario(
        name,
        request=request,
        result=result,
        events=events,
        proxy_calls=proxy_calls,
        wall_seconds=time.monotonic() - started,
        error=error,
    )
    return result, record


async def amain(args: argparse.Namespace) -> int:
    secret = os.environ.get("DEEPSEEK_API_KEY") or ""
    report: dict[str, Any] = {
        "task": "LG-006",
        "kind": "real-model-evidence",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine()}",
        "sdk_version": SDK_PINNED_VERSION,
        "model_requested": MODEL,
        "upstream": UPSTREAM,
        "credential": {
            "source": "env:DEEPSEEK_API_KEY" if secret else "missing",
            "present": bool(secret),
        },
        "max_real_model_calls": args.max_calls,
        "discovery_calls_outside_harness": 3,
        "total_real_model_calls": 0,
        "scenarios": [],
        "process_check": {},
        "limitations": [],
    }

    if not secret:
        report["limitations"].append(
            "DEEPSEEK_API_KEY was not present; the real chain could not run "
            "(no stub was substituted)."
        )
        EVIDENCE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    root = Path(tempfile.mkdtemp(prefix="lg006-evidence-"))
    before = _find_localharness_pids()
    report["process_check"]["localharness_pids_before"] = before
    evidence = _Evidence(secret)
    try:
        store, _workspace_root, workspace = _build_environment(root)
        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store, registry=helpers.make_registry()),
            credential_resolver=EnvCredentialResolver(),
            artifacts=DirectoryArtifactSink(root / "artifacts"),
            workspace_root=store.workspace_root,
            max_proxy_calls=args.max_calls,
            model_calls_cap=args.max_calls,
        )
        schema = _verdict_schema()

        scenarios: list[tuple[str, ExecuteRequest, float | None]] = [
            (
                "file_write_diff_structured",
                ExecuteRequest(
                    task_id="task_lg006",
                    run_id="run_lg006_file",
                    subtask_id="sub_lg006_file",
                    agent_ref="developer",
                    workspace_path=str(workspace),
                    objective=(
                        "Create a file named lg006_evidence.txt in the workspace "
                        "whose entire content is exactly the line: hello-lg006. "
                        "Then call finish with summary 'file written' and risk_level 1."
                    ),
                    acceptance_criteria=("file contains hello-lg006",),
                    budget={"max_model_calls": 4, "max_tool_calls": 6},
                    timeout_seconds=120,
                    response_schema=schema,
                ),
                None,
            ),
            (
                "budget_exhausted",
                ExecuteRequest(
                    task_id="task_lg006",
                    run_id="run_lg006_budget",
                    subtask_id="sub_lg006_budget",
                    agent_ref="developer",
                    workspace_path=str(workspace),
                    objective=(
                        "Create three separate files one at a time: budget_a.txt, "
                        "budget_b.txt, budget_c.txt."
                    ),
                    budget={"max_model_calls": 1, "max_tool_calls": 3},
                    timeout_seconds=120,
                ),
                None,
            ),
            (
                "cancel_confirmed",
                ExecuteRequest(
                    task_id="task_lg006",
                    run_id="run_lg006_cancel",
                    subtask_id="sub_lg006_cancel",
                    agent_ref="developer",
                    workspace_path=str(workspace),
                    objective=(
                        "Write a very long numbered list from 1 to 300, one number "
                        "per line, as your reply."
                    ),
                    budget={"max_model_calls": 4, "max_tool_calls": 4},
                    timeout_seconds=60,
                ),
                3.0,
            ),
        ]

        for name, request, cancel_after in scenarios:
            if executor.model_calls_made >= args.max_calls:
                report["scenarios"].append(
                    {"name": name, "skipped": "real-model call cap reached"}
                )
                continue
            _result, record = await _run_scenario(
                executor, evidence, name, request, cancel_after=cancel_after
            )
            report["scenarios"].append(record)

        # Session recovery: two turns sharing save_dir + conversation id.
        if executor.model_calls_made + 2 <= args.max_calls:
            save_dir = root / "sessions" / "resume"
            save_dir.mkdir(parents=True, exist_ok=True)
            code = "zebra-lg006-4271"
            first = ExecuteRequest(
                task_id="task_lg006",
                run_id="run_lg006_resume_a",
                subtask_id="sub_lg006_resume_a",
                agent_ref="developer",
                workspace_path=str(workspace),
                save_dir=str(save_dir),
                objective=f"Remember this code for later: {code}. Reply with OK.",
                budget={"max_model_calls": 4, "max_tool_calls": 2},
                timeout_seconds=120,
            )
            first_result, first_record = await _run_scenario(
                executor, evidence, "resume_seed", first
            )
            report["scenarios"].append(first_record)
            conversation_id = None
            if first_result is not None and first_result.session_ref is not None:
                conversation_id = first_result.session_ref.conversation_id
            if conversation_id:
                second = ExecuteRequest(
                    task_id="task_lg006",
                    run_id="run_lg006_resume_b",
                    subtask_id="sub_lg006_resume_b",
                    agent_ref="developer",
                    workspace_path=str(workspace),
                    save_dir=str(save_dir),
                    conversation_id=conversation_id,
                    objective="What code did I ask you to remember? Reply with the code.",
                    budget={"max_model_calls": 4, "max_tool_calls": 2},
                    timeout_seconds=120,
                )
                second_result, second_record = await _run_scenario(
                    executor, evidence, "resume_recall", second
                )
                recalled_text = "".join(
                    str(event.get("text", ""))
                    for event in second_record.get("events", [])
                    if event.get("type") == "adapter.text"
                )
                second_record["recalled_secret"] = code in recalled_text
                report["scenarios"].append(second_record)
            else:
                report["scenarios"].append(
                    {"name": "resume_recall", "skipped": "no conversation_id from seed"}
                )

        report["total_real_model_calls"] = executor.model_calls_made
        report["grand_total_real_model_calls"] = (
            executor.model_calls_made + report["discovery_calls_outside_harness"]
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    after = _find_localharness_pids()
    report["process_check"]["localharness_pids_after"] = after
    report["process_check"]["leaked"] = sorted(set(after) - set(before))
    report["limitations"] = [
        "Execution evidence only; independent version QA remains LG-010/LG-022.",
        "Only the openai-compat (DeepSeek) backend was exercised; Gemini/Vertex "
        "remain unverified and are not default executable connections.",
        "search_web stays unavailable; MCP/Triggers/internal delegation stay off.",
        "Sandbox isolation was not escape-tested; only the SDK-reported status is recorded.",
    ]

    serialized = json.dumps(report)
    if secret in serialized:
        raise SystemExit("refusing to write evidence: secret value appeared in report")
    EVIDENCE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "evidence": str(EVIDENCE_PATH),
                "scenarios": [item.get("name") for item in report["scenarios"]],
                "total_real_model_calls": report["total_real_model_calls"],
                "leaked_processes": report["process_check"]["leaked"],
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int, default=9)
    args = parser.parse_args()
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
