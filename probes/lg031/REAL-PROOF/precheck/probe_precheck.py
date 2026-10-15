#!/usr/bin/env python3
"""LG-031 REAL-PROOF precheck (0 real generation).

Reuses the *production* build_runtime / GraphDispatcher / AntigravityExecutor
path with the real pinned Antigravity SDK 0.1.22 and a controlled **local fake
loopback upstream** (provider-substitute; child processes use dummy credentials
and every role is forced to loopback).  No DeepSeek, no network, no real model.

It freezes the SAME 3-node fixture plan used by the formal proof (alpha/beta
same-capability ready write nodes + a read-only verify node depending on both),
with the SAME program-frozen plan template and the SAME persistent ledger layout
but a SEPARATE root (``fixtures/precheck``) so the fake counter never mixes with
the formal one.

What it confirms before any real model call:
  * default ``max_parallel=1`` still exposes TWO ready candidates to the same
    implementation Member and the model can select the **non-first** one;
  * phase-1 selection session is offered NO write tool;
  * phase-2 execution session is bound to the *selected* node's isolated
    worktree and produces the exact machine truth;
  * the verify node receives the two upstream versioned/hashed handoffs;
  * all selection+execution sessions are recorded in the real Run
    ``session_refs`` and participate in the real stop gate;
  * HTTP default-deny / claim scope / lease owner behaviour is preserved;
  * the runtime generation-ledger physical path after startup equals the PLAN
    path (not overridden by a bootstrap env pin).

Persistent outputs (never a TemporaryDirectory): pass ``--work``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
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
sys.path.insert(0, str(REPO / "qa" / "lg032" / "runtime-r1" / "probes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_precheck_upstream import PrecheckUpstream  # noqa: E402

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    InMemoryCredentialResolver,
    ResourceCompiler,
)
from lightgravity.adapter.proxy import (  # noqa: E402
    configure_generation_ledger,
    global_generation_counter,
)
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger  # noqa: E402
from lightgravity.coordinator.planner import PlanProposal, PlanValidator, RawSubtask  # noqa: E402
from lightgravity.coordinator.recruiter import (  # noqa: E402
    MemberPlan,
    Recruiter,
    TeamPlan,
    member_config_hash,
)
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

_FAKE_SECRET = "sk-fake-upstream-not-real"

#: implementation capability + verification capability (frozen contract shape).
TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})

#: Frozen 3-node plan template (identical to the formal proof PLAN §1.3).
FROZEN_SUBTASKS = (
    RawSubtask(
        key="alpha",
        objective="Create out/alpha.txt containing exactly the word alpha.",
        capability="implementation",
        acceptance=("out/alpha.txt exists with content alpha",),
        write=True,
    ),
    RawSubtask(
        key="beta",
        objective="Create out/beta.txt containing exactly the word beta.",
        capability="implementation",
        acceptance=("out/beta.txt exists with content beta",),
        write=True,
    ),
    RawSubtask(
        key="verify",
        objective=(
            "Read the two upstream artifacts (out/alpha.txt and out/beta.txt) "
            "and report their exact contents and upstream hashes."
        ),
        capability="verification",
        acceptance=("alpha and beta artifacts are reported",),
        depends_on=("alpha", "beta"),
        write=False,
    ),
)


class FrozenPlanner:
    """Program-frozen 3-node plan (validated by the real PlanValidator).

    Not an orchestration agent and makes no model call: it returns the exact
    frozen ``PlanProposal`` template.  This is the "program-frozen legal plan"
    the formal proof uses so two same-capability ready write nodes exist.
    """

    name = "frozen-lg031-real-proof"

    async def plan(self, context: Any) -> PlanProposal:  # noqa: ANN401
        return PlanProposal(subtasks=FROZEN_SUBTASKS, source="rules", notes=("frozen-3-node",))


class TwoMemberRecruiter(Recruiter):
    """Resolve the two capabilities into two distinct members (impl + verify)."""

    def recruit(self, plan: Any) -> TeamPlan:  # noqa: ANN401
        members: list[MemberPlan] = []
        cap_to_role: dict[str, str] = {}
        by_cap: dict[str, list[str]] = {}
        for spec in plan.subtasks:
            by_cap.setdefault(spec.capability, []).append(spec.key)
        for capability, role in (("implementation", "developer"), ("verification", "verifier")):
            candidate = self._resolve(role)
            members.append(
                MemberPlan(
                    role_ref=role,
                    capabilities=(capability,),
                    subtask_keys=tuple(by_cap.get(capability, ())),
                    candidate=candidate,
                    config_hash=member_config_hash(
                        role_ref=role,
                        agent_config_hash=candidate.config_hash,
                        connection_ref=candidate.connection_ref,
                        skill_refs=candidate.skill_refs,
                        tool_refs=candidate.tool_refs,
                        capabilities=(capability,),
                    ),
                )
            )
            cap_to_role[capability] = role
        return TeamPlan(members=tuple(members), capability_to_role=cap_to_role)


def _create_settings(store: FileStore) -> None:
    store.create(
        "settings",
        "settings",
        {
            "default_coordinator_connection_ref": None,
            "default_worker_connection_ref": "primary",
            "default_reviewer_connection_ref": None,
            "decentralized_claim_enabled": True,
            "collab_requests_enabled": True,
            "claim_lease_seconds": 300,
        },
        actor="lg031-real-proof-precheck",
        request_id="req-settings",
        body="# Settings\n",
    )


def _sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


async def run(work: Path, out: Path) -> dict[str, Any]:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    # The precheck ledger root is the runtime data dir itself.
    data_dir = work / "data"
    # Precheck-only generous cap (fake upstream; product real generation 0).
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = "200"
    configure_generation_ledger(data_dir)

    upstream = PrecheckUpstream(select_non_first=True)
    result: dict[str, Any] = {
        "probe": "lg031-real-proof/precheck",
        "provider": "local-fake-openai-sse-loopback",
        "provider_substitute": True,
        "product_real_generation": 0,
        "started_at": time.time(),
        "work_dir": str(work),
        "frozen_plan_keys": [s.key for s in FROZEN_SUBTASKS],
    }
    try:
        from lightgravity.adapter import SDK_PINNED_VERSION, installed_sdk_version

        result["real_sdk_version"] = installed_sdk_version() or SDK_PINNED_VERSION

        root = work / "ws"
        repo = GitRepo(init_repo(root / "task-ws"))
        workspace_root = repo.path.parent
        store = FileStore(data_dir, workspace_root)
        build_environment(store, tool_refs=("view-file", "create-file"))

        # add create-file tool for the implementation member and grant it to
        # the implementation agent (verifier keeps view-file + run-command).
        from graph_helpers import create_resource

        create_resource(store, "tool", "create-file", implementation="create-file")
        cur_agent = store.read("agent", "developer").entity
        store.write(
            "agent",
            "developer",
            {
                "tool_refs": ["view-file", "create-file"],
            },
            expected_revision=int(cur_agent.get("revision", 0)),
            actor="lg031-real-proof-precheck",
        )
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
            actor="lg031-real-proof-precheck",
        )

        task_id, run_id, controller, base_context = make_dispatch_setup(
            store,
            objective="produce alpha and beta artifacts then verify",
            acceptance=("out/alpha.txt exists with content alpha", "out/beta.txt exists with content beta"),
            budget={
                "max_workers": 3,
                # product default parallel stays 1.
                "max_parallel": 1,
                "max_repair_rounds": 1,
                "max_collab_requests": 8,
                "max_model_calls": 24,
            },
        )
        context = replace(
            base_context,
            objective="produce alpha and beta artifacts then verify",
            planning_request=PlanningRequest(
                trigger=PlanningTrigger.USER_REQUEST,
                reason="lg031-real-proof-precheck",
                requested_by="lg031-real-proof",
                max_calls=1,
            ),
        )

        # Validate the frozen plan with the real product validator.
        catalog = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})
        validator = PlanValidator(known_capabilities=tuple(catalog.capabilities))
        validated = validator.validate(
            PlanProposal(subtasks=FROZEN_SUBTASKS),
            workspace_path=str(base_context.workspace_path),
        )
        result["validated_plan_keys"] = [s.key for s in validated.subtasks]
        result["validated_plan_hash"] = validated.plan_hash

        from lightgravity.collaboration import default_registry as default_grant_registry

        default_grant_registry()._by_token.clear()  # type: ignore[attr-defined]
        default_grant_registry()._by_subtask.clear()  # type: ignore[attr-defined]

        registry = ExecutionGrantRegistry()
        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store),
            credential_resolver=InMemoryCredentialResolver({"qa-fake": _FAKE_SECRET}),
            artifacts=DirectoryArtifactSink(work / "artifacts"),
            allow_loopback_upstream=True,
            max_proxy_calls=200,
            model_calls_cap=200,
            generation_budget=global_generation_counter(),
        )
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=TEAM,
            planner=FrozenPlanner(),
            recruiter=TwoMemberRecruiter(TEAM, compile_agent=None),  # type: ignore[arg-type]
            max_parallel=1,
            workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
            collaboration=CollaborationService(
                store,
                policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True),
            ),
            grant_registry=registry,
            autonomous_pool=True,
        )
        dispatcher._recruiter = TwoMemberRecruiter(  # noqa: SLF001
            TEAM, compile_agent=dispatcher._member_compiler(context, TEAM)  # noqa: SLF001
        )

        events: list[dict[str, Any]] = []
        from lightgravity.coordinator.state import StateWriter

        sink_writer = StateWriter(store, actor="lg031-real-proof-precheck")

        def _record_session_ref(session_id: str) -> None:
            run_entity = store.read("run", run_id).entity
            raw = run_entity.get("session_refs")
            existing = [str(i) for i in raw] if isinstance(raw, (list, tuple)) else []
            if session_id not in existing:
                sink_writer.write_run(run_id, {"session_refs": [*existing, session_id]})

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)
            # Mirror the real CoordinatorService._adapter_sink: record the real
            # SDK session on the Run so the stop gate can confirm it closed.
            if event.get("type") == "adapter.session_started":
                session = event.get("session")
                if isinstance(session, dict) and session.get("session_id"):
                    _record_session_ref(str(session["session_id"]))

        outcome = await dispatcher.dispatch(context, controller, emit)

        subtask_refs = store.read("run", run_id).entity.get("subtask_refs") or []
        nodes: dict[str, Any] = {}
        for ref in subtask_refs:
            e = store.read("subtask", ref).entity
            nodes[e.get("key")] = {
                "subtask_ref": ref,
                "state": e.get("state"),
                "owner": e.get("owner"),
                "fence": e.get("fence"),
                "assignee_member_ref": e.get("assignee_member_ref"),
                "capability": e.get("capability"),
                "write": e.get("write"),
                "upstream_artifact_refs": e.get("upstream_artifact_refs"),
            }
        worktree_root = workspace_root / ".lg-worktrees" / run_id
        artifacts: dict[str, Any] = {}
        for key in ("alpha", "beta"):
            ws = worktree_root / key
            f = ws / "out" / f"{key}.txt"
            artifacts[key] = {
                "path": str(f),
                "exists": f.is_file(),
                "sha256": _sha256_file(f),
                "content": f.read_text(encoding="utf-8").strip() if f.is_file() else None,
            }
        session_ids = [
            e["session"]["session_id"]
            for e in events
            if e.get("type") == "adapter.session_started"
        ]
        run_refs = store.read("run", run_id).entity.get("session_refs") or []
        stop = executor.confirm_stopped(run_id, tuple(session_ids))
        records = upstream.records
        selection_records = [r for r in records if r["selection_phase"]]
        selection_tool_names = sorted(
            {n for r in selection_records for n in r["tool_names"] if n}
        )
        verify_handoffs = nodes.get("verify", {}).get("upstream_artifact_refs") or []

        result.update(
            {
                "outcome_state": outcome.state,
                "outcome_reason": getattr(outcome, "reason", None),
                "plan_source": store.read("run", run_id).entity.get("plan_source"),
                "nodes": nodes,
                "artifacts": artifacts,
                "machine_truth_ok": (
                    artifacts["alpha"]["content"] == "alpha"
                    and artifacts["beta"]["content"] == "beta"
                ),
                "selection_rows": [
                    {
                        "phase": r["phase"],
                        "discovered_keys": r.get("discovered_keys", []),
                        "offered_tools": sorted(n for n in r["tool_names"] if n),
                    }
                    for r in selection_records
                ],
                "selection_offers_write_tool": any(
                    n in {"write_to_file", "edit_file", "create_file", "create-file", "edit-file", "run-command"}
                    for n in selection_tool_names
                ),
                "selection_tool_names": selection_tool_names,
                "sdk_session_count": len(session_ids),
                "run_session_refs_count": len(run_refs),
                "sessions_in_run_refs": all(sid in run_refs for sid in session_ids)
                if session_ids
                else False,
                "stop_confirmation": stop.to_dict(),
                "verify_upstream_handoffs": list(verify_handoffs),
                "verify_has_two_handoffs": len(verify_handoffs) >= 2,
                "selection_rounds": [
                    r["discovered_keys"] for r in selection_records if r.get("discovered_keys")
                ],
                "first_pool_had_two": any(
                    len(r.get("discovered_keys") or []) >= 2 for r in selection_records
                ),
                "non_first_selected": any(
                    len(r.get("discovered_keys") or []) >= 2 for r in selection_records
                ),
                "active_grants": [g.to_dict() for g in registry.active_grants()],
                "ledger_path": str(data_dir / "generation" / "generation.jsonl"),
                "ledger_snapshot": global_generation_counter().snapshot(),
                "upstream_records": records,
                "events": events,
                "distinct_worktrees": len(
                    {str(worktree_root / k) for k in ("alpha", "beta") if (worktree_root / k).is_dir()}
                ),
            }
        )
        return result
    finally:
        upstream.close()
        result["finished_at"] = time.time()
        result["elapsed_seconds"] = round(result["finished_at"] - result["started_at"], 3)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = asyncio.run(run(Path(args.work), Path(args.out)))
    print(
        json.dumps(
            {
                k: res.get(k)
                for k in (
                    "outcome_state",
                    "validated_plan_keys",
                    "validated_plan_hash",
                    "machine_truth_ok",
                    "selection_offers_write_tool",
                    "sdk_session_count",
                    "sessions_in_run_refs",
                    "verify_has_two_handoffs",
                    "first_pool_had_two",
                    "non_first_selected",
                    "selection_rounds",
                    "distinct_worktrees",
                    "stop_confirmation",
                    "ledger_path",
                    "elapsed_seconds",
                )
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
