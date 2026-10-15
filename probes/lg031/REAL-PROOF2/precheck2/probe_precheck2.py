#!/usr/bin/env python3
"""LG-031 REAL-PROOF2 precheck (0 real generation).

Two parts, both before any real DeepSeek call:

A. **Startup / physical-ledger wiring via the *actual* ``build_runtime``**:
   resolve ``Settings.from_env`` from an isolated ``LIGHTGRAVITY_DATA_DIR``,
   call the real ``build_runtime`` (which itself calls
   ``configure_generation_ledger(settings.data_dir)``) and assert the
   post-startup generation ledger physically writes to
   ``<settings.data_dir>/generation/generation.jsonl`` — i.e. an env pin is
   **not** silently overridden by bootstrap, and the counter is the same one
   every worker/verifier/reviewer proxy shares.

B. **Three-node candidate-pool run via the production components + local fake
   loopback upstream** (provider-substitute; no network, no DeepSeek):
   the SAME frozen 3-node plan (alpha/beta same-capability ready write nodes +
   read-only verify depending on both) executed by the real ``GraphDispatcher``
   candidate-pool two-phase lifecycle.  Confirms: two ready candidates visible
   under ``max_parallel=1``; non-first selectable; selection offers no write
   tool; execution binds the selected node's isolated worktree; 4 versioned
   handoffs to verify; all sessions in real Run ``session_refs``; real stop
   gate.  Records per-stage ledger counts (default serial).

Persistent roots: ``--work`` is **create-only** (never rmtree'd; the probe
refuses to run if the root already exists).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))
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
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import build_environment, create_resource, make_dispatch_setup  # noqa: E402

_FAKE_SECRET = "sk-fake-upstream-not-real"

TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})

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
    name = "frozen-lg031-real-proof2"

    async def plan(self, context: Any) -> PlanProposal:  # noqa: ANN401
        return PlanProposal(subtasks=FROZEN_SUBTASKS, source="rules", notes=("frozen-3-node",))


class TwoMemberRecruiter(Recruiter):
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


def _sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


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
        actor="lg031-real-proof2-precheck",
        request_id="req-settings",
        body="# Settings\n",
    )


def part_a_startup_ledger(work: Path) -> dict[str, Any]:
    """Actual build_runtime startup + physical ledger path check."""

    data_dir = work / "data"
    os.environ["LIGHTGRAVITY_DATA_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_WORKSPACE_ROOT"] = str(data_dir / "workspaces")
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = "7"

    # Drop any counter cached before our env pin.
    import lightgravity.adapter.proxy as _proxy_mod

    _proxy_mod._GLOBAL_GENERATION_COUNTER = None  # type: ignore[attr-defined]

    from lightgravity.api.bootstrap import StartupOptions, build_runtime
    from lightgravity.config import Settings

    settings = Settings.from_env()
    state = build_runtime(
        StartupOptions(
            settings=settings,
            serve_frontend=False,
            wire_real_executor=False,
            seed_minimal_agent=False,
            tester=False,
            log=lambda _m: None,
        )
    )
    counter = global_generation_counter()
    before = counter.snapshot()
    reservation = counter.reserve()
    after = counter.snapshot()
    ledger_file = settings.data_dir / "generation" / "generation.jsonl"
    return {
        "settings_data_dir": str(settings.data_dir),
        "runtime_settings_data_dir": str(state.settings.data_dir),
        "ledger_file": str(ledger_file),
        "ledger_file_exists_after_reserve": ledger_file.is_file(),
        "snapshot_before": before,
        "reserve_granted": reservation,
        "snapshot_after": after,
        "startup_ledger_is_persistent": bool(after.get("persistent")),
        # bootstrap must configure the ledger at the resolved data dir; the env
        # override must not be silently re-pinned elsewhere.
        "env_pin_matches_resolved": os.environ.get("LIGHTGRAVITY_GENERATION_LEDGER_DIR")
        == str(settings.data_dir),
        "counter_limit_from_env": after.get("limit"),
    }


async def part_b_three_node_pool(work: Path) -> dict[str, Any]:
    """Frozen 3-node candidate-pool run over the production components."""

    data_dir = work / "data"
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = "200"
    import lightgravity.adapter.proxy as _proxy_mod

    _proxy_mod._GLOBAL_GENERATION_COUNTER = None  # type: ignore[attr-defined]
    configure_generation_ledger(data_dir)

    upstream = PrecheckUpstream(select_non_first=True)
    ledger_stages: list[dict[str, Any]] = []

    def ledger_count(stage: str) -> None:
        ledger_stages.append({"stage": stage, **global_generation_counter().snapshot()})

    result: dict[str, Any] = {
        "provider": "local-fake-openai-sse-loopback",
        "provider_substitute": True,
        "product_real_generation": 0,
    }
    try:
        from lightgravity.adapter import SDK_PINNED_VERSION, installed_sdk_version

        result["real_sdk_version"] = installed_sdk_version() or SDK_PINNED_VERSION

        root = work / "ws"
        repo = GitRepo(init_repo(root / "task-ws"))
        workspace_root = repo.path.parent
        store = FileStore(data_dir, workspace_root)
        build_environment(store, tool_refs=("view-file", "create-file", "edit-file"))
        create_resource(store, "tool", "create-file", implementation="create-file")
        _create_settings(store)
        cur = int(store.read("connection", "primary").entity.get("revision", 0))
        store.write(
            "connection",
            "primary",
            {"base_url": upstream.base_url, "model": "fake-model"},
            expected_revision=cur,
            actor="lg031-real-proof2-precheck",
        )

        task_id, run_id, controller, base_context = make_dispatch_setup(
            store,
            objective="Create out/alpha.txt and out/beta.txt, then verify both.",
            acceptance=(
                "out/alpha.txt exists with content alpha",
                "out/beta.txt exists with content beta",
            ),
            workspace_ref="task-ws",
            budget={
                "max_workers": 3,
                "max_parallel": 1,
                "max_repair_rounds": 1,
                "max_collab_requests": 8,
                "max_model_calls": 12,
            },
        )
        context = replace(
            base_context,
            workspace_path=str(repo.path),
            objective="Create out/alpha.txt and out/beta.txt, then verify both.",
            planning_request=PlanningRequest(
                trigger=PlanningTrigger.USER_REQUEST,
                reason="lg031-real-proof2-precheck",
                requested_by="proof2-precheck",
                max_calls=1,
            ),
        )

        validator = PlanValidator(known_capabilities=tuple(TEAM.capabilities))
        validated = validator.validate(
            PlanProposal(subtasks=FROZEN_SUBTASKS), workspace_path=str(repo.path)
        )
        result["validated_plan_keys"] = [s.key for s in validated.subtasks]
        result["validated_plan_hash"] = validated.plan_hash

        from lightgravity.adapter import default_registry as adapter_default_registry

        registry = ExecutionGrantRegistry()
        compiler = ResourceCompiler(store, registry=adapter_default_registry())
        executor = AntigravityExecutor(
            store,
            compiler,
            credential_resolver=InMemoryCredentialResolver({"worker-default": _FAKE_SECRET}),
            artifacts=DirectoryArtifactSink(data_dir / "artifacts"),
            workspace_root=workspace_root,
            max_proxy_calls=200,
            model_calls_cap=200,
            upstream_timeout=120,
            allow_loopback_upstream=True,
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
        sink_writer = StateWriter(store, actor="lg031-real-proof2-precheck")

        def _record_session_ref(session_id: str) -> None:
            run_entity = store.read("run", run_id).entity
            raw = run_entity.get("session_refs")
            existing = [str(i) for i in raw] if isinstance(raw, (list, tuple)) else []
            if session_id not in existing:
                sink_writer.write_run(run_id, {"session_refs": [*existing, session_id]})

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)
            if event.get("type") == "adapter.session_started":
                session = event.get("session")
                if isinstance(session, dict) and session.get("session_id"):
                    _record_session_ref(str(session["session_id"]))
            if event.get("type") == "adapter.execution_started":
                ledger_count("execution_started")
            if event.get("type") == "adapter.execution_finished":
                ledger_count("execution_finished")

        ledger_count("before_dispatch")
        outcome = await dispatcher.dispatch(context, controller, emit)
        ledger_count("after_dispatch")

        subtask_refs = store.read("run", run_id).entity.get("subtask_refs") or []
        nodes: dict[str, Any] = {}
        for ref in subtask_refs:
            e = store.read("subtask", ref).entity
            nodes[e.get("key")] = {
                "subtask_ref": ref,
                "state": e.get("state"),
                "owner": e.get("owner"),
                "fence": e.get("fence"),
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
                "nodes": nodes,
                "artifacts": artifacts,
                "machine_truth_ok": (
                    artifacts["alpha"]["content"] == "alpha"
                    and artifacts["beta"]["content"] == "beta"
                ),
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
                "stop_confirmation": stop.to_dict()
                if hasattr(stop, "to_dict")
                else dict(stop),
                "verify_upstream_handoffs": list(verify_handoffs),
                "verify_has_two_handoffs": len(verify_handoffs) >= 2,
                "first_pool_had_two": any(
                    len(r.get("discovered_keys") or []) >= 2 for r in selection_records
                ),
                "active_grants": [g.to_dict() for g in registry.active_grants()],
                "ledger_path": str(data_dir / "generation" / "generation.jsonl"),
                "ledger_snapshot": global_generation_counter().snapshot(),
                "ledger_stages": ledger_stages,
                "distinct_worktrees": len(
                    {
                        str(worktree_root / k)
                        for k in ("alpha", "beta")
                        if (worktree_root / k).is_dir()
                    }
                ),
            }
        )
        return result
    finally:
        upstream.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    work = Path(args.work).resolve()
    if work.exists():
        raise SystemExit(f"refusing to reuse existing precheck root (create-only): {work}")
    work.mkdir(parents=True)

    started = time.time()
    result: dict[str, Any] = {
        "probe": "lg031-real-proof2/precheck2",
        "work_dir": str(work),
        "started_at": started,
        "frozen_plan_keys": [s.key for s in FROZEN_SUBTASKS],
    }
    result["part_a_startup_ledger"] = part_a_startup_ledger(work)
    result["part_b_three_node_pool"] = asyncio.run(part_b_three_node_pool(work))
    result["finished_at"] = time.time()
    result["elapsed_seconds"] = round(result["finished_at"] - started, 3)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    a = result["part_a_startup_ledger"]
    b = result["part_b_three_node_pool"]
    print(
        json.dumps(
            {
                "part_a_ledger_file": a["ledger_file"],
                "part_a_ledger_exists": a["ledger_file_exists_after_reserve"],
                "part_a_persistent": a["startup_ledger_is_persistent"],
                "part_a_env_pin_matches": a["env_pin_matches_resolved"],
                "part_b_outcome": b["outcome_state"],
                "plan_hash": b["validated_plan_hash"],
                "first_pool_had_two": b["first_pool_had_two"],
                "selection_offers_write_tool": b["selection_offers_write_tool"],
                "machine_truth_ok": b["machine_truth_ok"],
                "sessions_in_run_refs": b["sessions_in_run_refs"],
                "verify_has_two_handoffs": b["verify_has_two_handoffs"],
                "distinct_worktrees": b["distinct_worktrees"],
                "stop": b["stop_confirmation"],
                "ledger_snapshot": b["ledger_snapshot"],
                "elapsed_seconds": result["elapsed_seconds"],
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
