#!/usr/bin/env python3
"""LG-032 R1 gate 3 — session refs / stop gate / shared budget / recovery.

Independent QA probe.  Real pinned SDK 0.1.22 + local fake loopback upstream;
real ``GraphDispatcher`` candidate-pool two-phase lifecycle; real persistent
generation ledger; real ``StoreResourceStopper`` stop gate; real
``Coordinator._adapter_sink`` as the emit sink so ``run.session_refs`` is written
exactly as the product path records it.

It checks, for the pool (two-phase) path:

* every real SDK session the adapter started is attributed to the Run, and the
  stop gate confirms only when the adapter proves every session closed;
* a deliberately *unstoppped* selection session keeps the gate held (retaining
  refs), rather than silently passing;
* the selection + execution (+ a reviewer proxy) share ONE physical persistent
  ledger under the controlled data root; the count does not reset across
  sessions/Runs; corruption reads as unknown (never 0).

Persistent outputs only; no TemporaryDirectory for the SoT.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))
sys.path.insert(0, str(REPO / "tests" / "collaboration"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_upstream import UpstreamServer  # noqa: E402

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    InMemoryCredentialResolver,
    ResourceCompiler,
)
from lightgravity.adapter.generation_ledger import PersistentGenerationLedger  # noqa: E402
from lightgravity.adapter.proxy import GenerationCounter  # noqa: E402
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import Coordinator, GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.dispatcher import UnavailableExecutor  # noqa: E402
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.verify.stopgate import StoreResourceStopper  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402
from probe_gate1_two_phase import (  # noqa: E402
    TEAM,
    FourNodePlanner,
    TwoMemberRecruiter,
    _add_agent,
    _add_create_file_tool,
    _create_settings,
)

_FAKE_SECRET = "sk-fake-upstream-not-real"


class _SingleConfirm:
    """A stop-confirmer that always returns one captured report (QA scenario)."""

    def __init__(self, report: dict[str, Any]) -> None:
        self._report = report

    def confirm_stopped(self, run_id: str, session_refs: tuple[str, ...]) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            confirmed=bool(self._report.get("confirmed")),
            to_dict=lambda: dict(self._report),
        )


def _member_setup() -> None:
    pass


async def _run_pool(
    *,
    work: Path,
    upstream: UpstreamServer,
    ledger_limit: int | None,
    sink_session_refs: bool,
    corrupt_ledger: bool,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    data = data_dir or (work / "data")
    root = work / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(data, workspace_root)
    fresh_data = not (data / "resources" / "connections" / "primary.md").exists()
    if fresh_data:
        build_environment(store, tool_refs=("view-file", "create-file"))
        _add_create_file_tool(store)
        _add_agent(store, "dev-a")
        _add_agent(store, "dev-b")
        _create_settings(store)
    cur = int(store.read("connection", "primary").entity.get("revision", 0))
    store.write(
        "connection",
        "primary",
        {
            "backend": "openai-compat",
            "model": "fake-model",
            "credential_ref": "qa-fake",
            "base_url": upstream.base_url,
        },
        expected_revision=cur,
        actor="qa-r1",
    )

    task_id, run_id, controller, base_context = make_dispatch_setup(
        store,
        budget={
            "max_workers": 4,
            "max_parallel": 2,
            "max_repair_rounds": 1,
            "max_collab_requests": 8,
            "max_model_calls": 24,
        },
    )
    context = replace(
        base_context,
        objective="produce four artifacts",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="qa-r1-gate3",
            requested_by="qa-r1",
            max_calls=1,
        ),
    )

    # The REAL coordinator sink records run.session_refs exactly as the product
    # path does; it is a plain callable, so the graph can use it as ``emit``.
    coordinator = Coordinator(store, dispatcher=UnavailableExecutor(), data_dir=data)
    sink = coordinator._adapter_sink(task_id, run_id)  # noqa: SLF001

    # One physical persistent ledger under the controlled data root, shared by
    # every worker session (and a reviewer proxy) in the process.
    ledger = PersistentGenerationLedger(data, limit=ledger_limit)
    if corrupt_ledger:
        (data / "generation" / "generation.jsonl").write_text(
            "{not-json\n", encoding="utf-8"
        )
    counter = GenerationCounter(limit=ledger_limit, ledger=ledger)

    registry = ExecutionGrantRegistry()
    executor = AntigravityExecutor(
        store,
        ResourceCompiler(store),
        credential_resolver=InMemoryCredentialResolver({"qa-fake": _FAKE_SECRET}),
        artifacts=DirectoryArtifactSink(work / "artifacts"),
        allow_loopback_upstream=True,
        model_calls_cap=24,
        generation_budget=counter,
    )
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=TEAM,
        planner=FourNodePlanner(),
        max_parallel=2,
        workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
        collaboration=CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        ),
        grant_registry=registry,
        autonomous_pool=True,
    )
    dispatcher._recruiter = TwoMemberRecruiter(  # noqa: SLF001
        TEAM, compile_agent=dispatcher._member_compiler(context, TEAM)  # noqa: SLF001
    )

    events: list[dict[str, Any]] = []

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if sink_session_refs:
            sink(event)

    outcome = await dispatcher.dispatch(context, controller, emit)

    # Apply the outcome exactly as the product coordinator does so the Run reaches
    # a terminal state before the verifier stop gate runs.
    coordinator._apply_outcome(task_id, run_id, outcome)  # noqa: SLF001

    run_entity = store.read("run", run_id).entity
    session_refs = list(run_entity.get("session_refs") or [])
    adapter_sessions = [
        e["session"]["session_id"]
        for e in events
        if e.get("type") == "adapter.session_started"
    ]
    # Real stop gate (adapter-confirmed).  ``executor.confirm_stopped`` proves
    # each session closed; the store stopper requires the Run not active, no
    # unconfirmed sessions, and the slot released.
    stopper = StoreResourceStopper(store, session_confirmer=executor)
    stop_report = stopper.stop(task_id, run_id)
    raw_confirm = executor.confirm_stopped(run_id, tuple(adapter_sessions)).to_dict()

    # Held-gate scenario: a selection session that started but never closed is
    # present in the Run's stop-gate list.  The real adapter confirmer reports it
    # unknown, so the store stopper must keep the gate unconfirmed and RETAIN the
    # refs (no fabricated pass).  We inject the unresolved ref directly on the
    # Run, exactly as a never-closed selector would leave it.
    bogus = "sess_unclosed_selector_never_stopped"
    controller.update_run({"session_refs": [*session_refs, bogus]})
    held_stopper = StoreResourceStopper(store, session_confirmer=executor)
    held_report = held_stopper.stop(task_id, run_id)
    held = held_report.to_dict()
    held["retained_refs"] = list(
        store.read("run", run_id).entity.get("session_refs") or []
    )
    held["unresolved_ref_retained"] = bogus in held["retained_refs"]

    count_after = counter.count
    ledger_snapshot = ledger.snapshot()
    return {
        "outcome_state": outcome.state,
        "run_id": run_id,
        "task_id": task_id,
        "session_refs_on_run": session_refs,
        "adapter_session_count": len(adapter_sessions),
        "adapter_sessions": adapter_sessions,
        "sessions_missing_from_run": sorted(set(adapter_sessions) - set(session_refs)),
        "selection_sessions_in_run": len(session_refs),
        "stop_gate": stop_report.to_dict(),
        "adapter_confirm_stopped": raw_confirm,
        "held_gate": held,
        "run_state_after_outcome": run_entity.get("state"),
        "generation_count": count_after,
        "generation_limit": ledger_limit,
        "ledger_snapshot": ledger_snapshot,
        "ledger_path": str(data / "generation" / "generation.jsonl"),
    }


async def run(work: Path, out: Path) -> dict[str, Any]:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    upstream = UpstreamServer(select_non_first=True)
    result: dict[str, Any] = {
        "probe": "lg032-r1/gate3-resources",
        "provider": "local-fake-openai-sse-loopback",
        "provider_substitute": True,
        "product_real_generation": 0,
        "started_at": time.time(),
        "scenarios": {},
    }
    try:
        # Scenario A: full path with sink + shared ledger (limit generous).
        result["scenarios"]["A_shared_ledger"] = await _run_pool(
            work=work / "A",
            upstream=upstream,
            ledger_limit=100,
            sink_session_refs=True,
            corrupt_ledger=False,
        )
        # Scenario B: a SECOND, independent run that shares the SAME physical
        # persistent ledger (its own task/run), so the count must NOT reset.
        result["scenarios"]["B_second_run_no_reset"] = await _run_pool(
            work=work / "B",
            data_dir=work / "A" / "data",  # same controlled data root/ledger
            upstream=upstream,
            ledger_limit=100,
            sink_session_refs=True,
            corrupt_ledger=False,
        )
        # Scenario C: corrupt ledger -> unknown, never 0.
        result["scenarios"]["C_corrupt_ledger"] = await _run_pool(
            work=work / "C",
            upstream=upstream,
            ledger_limit=100,
            sink_session_refs=True,
            corrupt_ledger=True,
        )
    finally:
        upstream.close()
        result["finished_at"] = time.time()
        result["elapsed_seconds"] = round(result["finished_at"] - result["started_at"], 3)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = asyncio.run(run(Path(a.work), Path(a.out)))
    print(
        json.dumps(
            {
                k: {
                    "outcome": v["outcome_state"],
                    "adapter_sessions": v["adapter_session_count"],
                    "sessions_missing_from_run": v["sessions_missing_from_run"],
                    "stop_confirmed": v["stop_gate"]["confirmed"],
                    "gen_count": v["generation_count"],
                    "corrupt": v["ledger_snapshot"].get("corrupt"),
                }
                for k, v in res["scenarios"].items()
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
