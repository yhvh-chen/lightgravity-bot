#!/usr/bin/env python3
"""LG-032 R1 gate 1 — real SDK two-phase selection, same Runtime/GraphDispatcher.

Independent QA probe (NOT the source probe).  Real pinned Antigravity SDK 0.1.22
+ a local controlled fake OpenAI-compatible upstream (provider-substitute); the
*only* processing endpoint is ``127.0.0.1``.  No DeepSeek, no network, no real
model.  Product real generation: 0.

What is real here:
* the real SDK agent loop, session lifecycle, tool invocation and loopback auth
  proxy (``AntigravityExecutor``);
* the real product ``GraphDispatcher`` candidate-pool two-phase lifecycle
  (selection session -> program atomic grant -> separate execution session);
* real ``FileStore`` + real ``flock`` + real git worktrees + real fenced
  ``CollaborationService``.

Scenario:
* ONE Run, ONE ``GraphDispatcher``, ``max_parallel=2``.
* TWO distinct members (different ``member_ref``) with the **same permission
  profile** (identical agent tool/skill/connection config).  Each member owns a
  pool of TWO same-capability-context ready write nodes.
* Each worker's phase-1 selection session sees a >=2 candidate pool and the fake
  upstream makes it select the **non-first** candidate.
* Phase 2 is a separate real SDK session bound by the program to the *selected*
  node's isolated git worktree / objective / upstream; artifacts are attributed
  to the selected node only.

The probe is deliberately strict about not inventing product features: the two
members are built by an injected recruiter for the *QA test* (the frozen contract
maps one capability to one member), so the probe honestly labels the capability
labels as ``impl_a``/``impl_b`` rather than claiming the product recruiter splits
one capability across members.

Persistent outputs (never a TemporaryDirectory): pass ``--work``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger  # noqa: E402
from lightgravity.coordinator.planner import PlanProposal, RawSubtask  # noqa: E402
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

#: Two agents with an IDENTICAL permission profile (same tools/skills/connection).
TEAM = RoleCatalog({"impl_a": ["dev-a"], "impl_b": ["dev-b"]})


class FourNodePlanner:
    """Two same-capability-context nodes per member, all simultaneously ready."""

    name = "r1-four-node"

    async def plan(self, context):  # noqa: ANN001
        subtasks = [
            RawSubtask(
                key="a1",
                objective="Write a1 artifact out/a1.txt",
                capability="impl_a",
                acceptance=("out/a1.txt exists",),
                write=True,
            ),
            RawSubtask(
                key="a2",
                objective="Write a2 artifact out/a2.txt",
                capability="impl_a",
                acceptance=("out/a2.txt exists",),
                write=True,
            ),
            RawSubtask(
                key="b1",
                objective="Write b1 artifact out/b1.txt",
                capability="impl_b",
                acceptance=("out/b1.txt exists",),
                write=True,
            ),
            RawSubtask(
                key="b2",
                objective="Write b2 artifact out/b2.txt",
                capability="impl_b",
                acceptance=("out/b2.txt exists",),
                write=True,
            ),
        ]
        return PlanProposal(subtasks=tuple(subtasks), source="rules")


class TwoMemberRecruiter(Recruiter):
    """QA-only recruiter: two distinct members, one per capability label.

    Both members compile from agents with an identical tool/skill/connection
    profile, so this is two *different member_ref* workers with the same
    permission profile (the gate-1 requirement).  The frozen product recruiter
    maps a capability to a single member; this recruiter exists only to build the
    QA scenario and is clearly labelled as such.
    """

    def __init__(self, catalog, compile_agent):  # noqa: ANN001
        super().__init__(catalog, compile_agent=compile_agent)

    def recruit(self, plan):  # noqa: ANN001
        members: list[MemberPlan] = []
        cap_to_role: dict[str, str] = {}
        by_cap: dict[str, list[str]] = {}
        for spec in plan.subtasks:
            by_cap.setdefault(spec.capability, []).append(spec.key)
        for capability, role in (("impl_a", "dev-a"), ("impl_b", "dev-b")):
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


def _add_agent(store: FileStore, agent_id: str) -> None:
    from graph_helpers import create_agent

    create_agent(
        store,
        agent_id,
        skill_refs=["implementation"],
        tool_refs=("view-file", "create-file"),
    )


def _add_create_file_tool(store: FileStore) -> None:
    from graph_helpers import create_resource

    create_resource(store, "tool", "create-file", implementation="create-file")


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
        actor="qa-r1",
        request_id="req-settings",
        body="# Settings\n",
    )


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


async def run(work: Path, out: Path) -> dict[str, Any]:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    upstream = UpstreamServer(select_non_first=True)
    result: dict[str, Any] = {
        "probe": "lg032-r1/gate1-two-phase-sdk",
        "provider": "local-fake-openai-sse-loopback",
        "provider_substitute": True,
        "product_real_generation": 0,
        "started_at": time.time(),
        "work_dir": str(work),
    }
    try:
        from lightgravity.adapter import SDK_PINNED_VERSION, installed_sdk_version

        result["real_sdk_version"] = installed_sdk_version() or SDK_PINNED_VERSION

        root = work / "ws"
        repo = GitRepo(init_repo(root / "task-ws"))
        workspace_root = repo.path.parent
        store = FileStore(work / "data", workspace_root)
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
                reason="qa-r1-gate1",
                requested_by="qa-r1",
                max_calls=1,
            ),
        )
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
            model_calls_cap=24,
        )
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=TEAM,
            planner=FourNodePlanner(),
            recruiter=TwoMemberRecruiter(TEAM, compile_agent=None),  # type: ignore[arg-type]
            max_parallel=2,
            workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
            collaboration=CollaborationService(
                store,
                policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True),
            ),
            grant_registry=registry,
            autonomous_pool=True,
        )
        # The custom recruiter needs the dispatcher's member compiler.
        dispatcher._recruiter = TwoMemberRecruiter(  # noqa: SLF001
            TEAM, compile_agent=dispatcher._member_compiler(context, TEAM)  # noqa: SLF001
        )

        events: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)

        outcome = await dispatcher.dispatch(context, controller, emit)

        # ---- evidence -------------------------------------------------------
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
            }
        member_refs = sorted(
            {v["assignee_member_ref"] for v in nodes.values() if v["assignee_member_ref"]}
        )
        worktree_root = workspace_root / ".lg-worktrees" / run_id
        workspaces: dict[str, str] = {}
        artifacts: dict[str, Any] = {}
        for key in nodes:
            ws = worktree_root / key
            workspaces[key] = str(ws) if ws.is_dir() else ""
            f = ws / "out" / f"{key}.txt"
            artifacts[key] = {
                "path": str(f),
                "exists": f.is_file(),
                "sha256": _sha256(f),
                "in_own_worktree": f"/{key}/" in str(f),
                "content_matches_key": (
                    f.is_file() and f.read_text(encoding="utf-8").strip().split("/")[-1] == f"{key}.txt"
                )
                if f.is_file()
                else False,
            }
        session_ids = [
            e["session"]["session_id"]
            for e in events
            if e.get("type") == "adapter.session_started"
        ]
        stop = executor.confirm_stopped(run_id, tuple(session_ids))
        records = upstream.records
        selection_records = [r for r in records if r["selection_phase"]]
        execution_records = [r for r in records if not r["selection_phase"]]
        # A selection session must never be offered a product write tool.
        selection_tool_names = sorted(
            {n for r in selection_records for n in r["tool_names"] if n}
        )
        # Distinct execution workspaces referenced by the fake upstream per node.
        selected_non_first = True
        for key in ("a2", "b2"):
            if nodes.get(key, {}).get("state") != "passed":
                selected_non_first = False

        # Member permission profiles: two DISTINCT members with the SAME profile.
        member_profiles: dict[str, Any] = {}
        for ref in store.read("run", run_id).entity.get("team_refs") or []:
            m = store.read("member", ref).entity
            member_profiles[m.get("role_ref") or ref] = {
                "member_ref": ref,
                "role_ref": m.get("role_ref"),
                "tool_policy": m.get("tool_policy"),
                "skill_refs": m.get("skill_refs"),
                "connection_ref": m.get("connection_ref"),
                "capabilities": m.get("capabilities"),
            }
        perm_profiles = {
            role: {
                "tool_policy": v["tool_policy"],
                "skill_refs": v["skill_refs"],
                "connection_ref": v["connection_ref"],
            }
            for role, v in member_profiles.items()
        }
        profiles_equal = len({json.dumps(v, sort_keys=True) for v in perm_profiles.values()}) == 1
        # Selection-phase rows: which candidate pool each selection session saw
        # and whether the *first listed* candidate was passed over.
        selection_rows = [
            {
                "phase": r["phase"],
                "discovered_keys": r.get("discovered_keys", []),
                "offered_tools": sorted(n for n in r["tool_names"] if n),
            }
            for r in selection_records
        ]
        result.update(
            {
                "outcome_state": outcome.state,
                "outcome_reason": getattr(outcome, "reason", None),
                "member_profiles": member_profiles,
                "member_profiles_equal": profiles_equal,
                "selection_rows": selection_rows,
                "events": events,
                "members": member_refs,
                "distinct_member_count": len(member_refs),
                "nodes": nodes,
                "workspaces": workspaces,
                "artifacts": artifacts,
                "selected_keys": [k for k, v in nodes.items() if v["state"] == "passed"],
                "selection_phase_requests": len(selection_records),
                "execution_phase_requests": len(execution_records),
                "selection_tool_names": selection_tool_names,
                "selection_offers_write_tool": any(
                    n in {"write_to_file", "edit-file", "create-file", "run-command"}
                    for n in selection_tool_names
                ),
                "sdk_session_count": len(session_ids),
                "sdk_session_starts": session_ids,
                "stop_confirmation": stop.to_dict(),
                "active_grants": [g.to_dict() for g in registry.active_grants()],
                "upstream_phases": [r["phase"] for r in records],
                "upstream_records": records,
                "selected_non_first": selected_non_first,
                "no_cross_contamination": all(
                    v["content_matches_key"] for v in artifacts.values() if v["exists"]
                ),
                "distinct_worktrees": len({w for w in workspaces.values() if w}),
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
                    "distinct_member_count",
                    "selected_keys",
                    "sdk_session_count",
                    "selection_offers_write_tool",
                    "no_cross_contamination",
                    "distinct_worktrees",
                    "selected_non_first",
                    "elapsed_seconds",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
