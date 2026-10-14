#!/usr/bin/env python3
"""LG-006 dedicated cancel evidence (bounded, one real model call).

Cancels a genuinely streaming turn and records the confirmation, outcome and
proxy stop.  Kept separate from the main harness so the main run is not replayed
(real-model call budget is a hard bound).

Run:
    DEEPSEEK_API_KEY=... uv run python tests/adapter/evidence/lg006_cancel_run.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_EVIDENCE_DIR = Path(__file__).resolve().parent
_REPO = _EVIDENCE_DIR.parents[2]
sys.path.insert(0, str(_REPO / "backend"))
sys.path.insert(0, str(_REPO / "tests" / "adapter"))

import helpers  # noqa: E402

from lg006_real_run import (  # noqa: E402
    MODEL,
    UPSTREAM,
    _build_environment,
    _find_localharness_pids,
)
from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    EnvCredentialResolver,
    ExecuteRequest,
    ExecutionRef,
    ResourceCompiler,
    mask_values,
)
from lightgravity.adapter.proxy import LocalAuthProxy  # noqa: E402

CANCEL_EVIDENCE_PATH = _EVIDENCE_DIR / "lg006-cancel-evidence.json"


async def amain() -> int:
    secret = os.environ.get("DEEPSEEK_API_KEY") or ""
    report: dict[str, Any] = {
        "task": "LG-006",
        "kind": "real-model-cancel-evidence",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_requested": MODEL,
        "upstream": UPSTREAM,
        "credential_present": bool(secret),
        "real_model_calls": 0,
    }
    if not secret:
        report["error"] = "DEEPSEEK_API_KEY missing; cancel was not attempted"
        CANCEL_EVIDENCE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 2

    root = Path(tempfile.mkdtemp(prefix="lg006-cancel-"))
    before = _find_localharness_pids()
    try:
        store, _workspace_root, workspace = _build_environment(root)
        captures: list[LocalAuthProxy] = []

        def proxy_factory(credential: Any, upstream: str, max_calls: int) -> LocalAuthProxy:
            proxy = LocalAuthProxy(
                credential=credential, upstream_url=upstream, max_calls=max_calls
            )
            captures.append(proxy)
            return proxy

        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store, registry=helpers.make_registry()),
            credential_resolver=EnvCredentialResolver(),
            artifacts=DirectoryArtifactSink(root / "artifacts"),
            workspace_root=store.workspace_root,
            max_proxy_calls=1,
            model_calls_cap=1,
            proxy_factory=proxy_factory,
        )
        events: list[dict[str, Any]] = []
        execution_id: dict[str, str] = {}

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)
            ref = event.get("execution") or {}
            if event.get("type") == "adapter.execution_started" and isinstance(
                ref.get("execution_id"), str
            ):
                execution_id["value"] = ref["execution_id"]

        request = ExecuteRequest(
            task_id="task_lg006",
            run_id="run_lg006_cancel_dedicated",
            subtask_id="sub_lg006_cancel_dedicated",
            agent_ref="developer",
            workspace_path=str(workspace),
            objective=(
                "Write a very long numbered list from 1 to 300, one number per "
                "line, as your reply."
            ),
            budget={"max_model_calls": 1, "max_tool_calls": 2},
            timeout_seconds=60,
        )
        task = asyncio.create_task(executor.execute(request, emit))
        deadline = time.monotonic() + 30
        while "value" not in execution_id and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        while time.monotonic() < deadline and not any(
            event.get("type") in ("adapter.text", "adapter.tool_call") for event in events
        ):
            await asyncio.sleep(0.02)
        cancel_result = await executor.cancel(
            ExecutionRef(execution_id=execution_id.get("value", ""))
        )
        result = await task
        events.append({"type": "adapter.cancel_result", **cancel_result.to_dict()})

        report["execution_id"] = execution_id.get("value")
        report["result"] = result.to_dict()
        report["cancel_result"] = cancel_result.to_dict()
        report["events"] = [
            {key: value for key, value in event.items() if key != "result"}
            for event in events
        ]
        report["real_model_calls"] = executor.model_calls_made
        report["proxy_calls"] = captures[0].call_records() if captures else []
        report["proxy_stop_confirmed"] = (
            captures[0].stop() if captures else True
        )
    except Exception as exc:  # noqa: BLE001 - evidence records real failures
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(root, ignore_errors=True)

    after = _find_localharness_pids()
    report["process_check"] = {
        "before": before,
        "after": after,
        "leaked": sorted(set(after) - set(before)),
    }
    serialized = json.dumps(mask_values(report, [secret]))
    if secret in serialized:
        raise SystemExit("refusing to write evidence: secret value appeared in report")
    CANCEL_EVIDENCE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "evidence": str(CANCEL_EVIDENCE_PATH),
                "state": (report.get("result") or {}).get("state"),
                "cancel": report.get("cancel_result"),
                "calls": report.get("real_model_calls"),
                "leaked": report["process_check"]["leaked"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
