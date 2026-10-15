#!/usr/bin/env python3
"""LG-032 R1 gate 4 — default-off fallback + switch behaviour.

With the new switches off (default), the product must take the ORIGINAL
deterministic path: ``plan_source=rules``, no discovery/claim endpoints active,
no pool grants, no custom claim tools, SDK subagents still off.  Turning the
switch on must not be required for the first-version flows.

Real FileStore; no SDK/model/network.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))

from lightgravity.adapter import ExecutionRef, ExecutorResult  # noqa: E402
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.planner import PlanProposal, RawSubtask  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402

from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

TEAM = RoleCatalog({"implementation": ["developer"]})


class _OneNodePlanner:
    name = "fallback"

    async def plan(self, context):  # noqa: ANN001
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="only",
                    objective="Write out/only.txt",
                    capability="implementation",
                    acceptance=("out/only.txt exists",),
                    write=False,
                ),
            ),
            source="rules",
        )


class _RecordingExecutor:
    name = "rec"
    version = "0"

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def capabilities(self):  # noqa: ANN201
        from lightgravity.adapter import adapter_capabilities

        return adapter_capabilities()

    async def execute(self, request, emit):  # noqa: ANN001, ANN201
        self.requests.append(request)
        return ExecutorResult(
            state="succeeded",
            summary="ok",
            artifact_refs=(),
            execution_ref=ExecutionRef(
                execution_id="e", task_id=request.task_id, run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    def confirm_stopped(self, run_id, session_refs):  # noqa: ANN001, ANN201
        from lightgravity.adapter import StopConfirmation

        return StopConfirmation(run_id=run_id, confirmed=True, sessions_total=0)

    async def cancel(self, ref):  # noqa: ANN001, ANN201
        from lightgravity.adapter import CancelResult

        return CancelResult(confirmed=True, state="cancelled", reason="noop")


async def run(work: Path, out: Path) -> dict[str, Any]:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    ws = work / "ws"
    ws.mkdir(parents=True)
    store = FileStore(work / "data", ws)
    build_environment(store)
    # Settings present but both switches OFF (the default).
    store.create(
        "settings",
        "settings",
        {
            "default_coordinator_connection_ref": None,
            "default_worker_connection_ref": None,
            "default_reviewer_connection_ref": None,
            "decentralized_claim_enabled": False,
            "collab_requests_enabled": False,
            "claim_lease_seconds": 300,
        },
        actor="qa-r1",
        request_id="req-settings",
        body="# Settings\n",
    )
    _task, run_id, controller, context = make_dispatch_setup(
        store=store, budget={"max_workers": 2, "max_parallel": 1}
    )
    from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger

    context = replace(
        context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="qa-r1-gate4",
            requested_by="qa-r1",
            max_calls=1,
        ),
    )
    ex = _RecordingExecutor()
    dispatcher = GraphDispatcher(
        store,
        ex,
        catalog=TEAM,
        planner=_OneNodePlanner(),
        max_parallel=1,
        collaboration=None,
        grant_registry=None,
        autonomous_pool=True,  # pool requested, but the switch is off
    )
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    run_entity = store.read("run", run_id).entity
    sub_refs = run_entity.get("subtask_refs") or []
    tool_names = []
    for req in ex.requests:
        tool_names.extend(getattr(t, "__name__", "?") for t in req.custom_tools)
    result = {
        "probe": "lg032-r1/gate4-default-off",
        "product_real_generation": 0,
        "outcome_state": outcome.state,
        "plan_source": run_entity.get("plan_source"),
        "custom_tools_seen": sorted(set(tool_names)),
        "has_discover_and_request_claim": any(
            "discover_and_request_claim" in t for t in tool_names
        ),
        "node_states": {
            store.read("subtask", r).entity.get("key"): store.read("subtask", r).entity.get("state")
            for r in sub_refs
        },
        "fences": {
            store.read("subtask", r).entity.get("key"): store.read("subtask", r).entity.get("fence")
            for r in sub_refs
        },
        "custom_tools_empty": tool_names == [],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = asyncio.run(run(Path(a.work), Path(a.out)))
    print(json.dumps({k: res[k] for k in (
        "outcome_state", "plan_source", "custom_tools_empty",
        "has_discover_and_request_claim", "node_states", "fences",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
