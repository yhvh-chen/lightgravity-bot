#!/usr/bin/env python3
"""LG031-BOUNDARY-QA — product-default-layout real-SDK two-phase probe.

Reuses the mature real-SDK loopback harness from
``probes/lg031/RUNTIME-AUTH-INTEGRATION/probe_two_phase_sdk.py`` (real pinned
Antigravity SDK 0.1.22 + local fake OpenAI SSE upstream; product real
generation = 0), but sets the **product default** ``DispatchContext.save_dir``
to ``<data_dir>/native-sessions/<task>`` -- which lies OUTSIDE the executor
authorized ``workspace_root = <data_dir>/workspaces``.  This is exactly the
layout in ``probes/lg031-workspace-boundary/DEFECT-REPRO.md`` where the pre-fix
selection scratch (under save_dir) was rejected by the real executor.

What it proves (all with the real SDK agent loop + real executor + real
GraphDispatcher candidate pool + real git worktrees):

  A. The selector's phase-1 session workspace is INSIDE the authorized root (the
     real executor accepts it), and is NOT under ``save_dir``.
  B. Before selection the phase-1 session is given NO write tools
     (``allowed_tools=()``), so it cannot write a product artifact prior to
     program authorization; the restricted claim tool is the only tool.
  C. After the real worker selects a NON-FIRST candidate and the program
     authorizes it, the phase-2 execution session is bound to the *selected*
     node's isolated worktree -- the artifact lands on that node, not another.
  D. Every SDK session is recorded (session refs) and the adapter's real stop
     confirmer confirms the run's sessions stopped.

Exit 0 iff A-D hold.  Provider is the local fake (not DeepSeek); no network POST
leaves loopback.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

QA_DIR = Path(__file__).resolve().parent
REPO = QA_DIR.parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))
sys.path.insert(0, str(REPO / "tests" / "adapter"))
sys.path.insert(0, str(REPO / "tests" / "collaboration"))
sys.path.insert(0, str(REPO / "probes" / "lg031" / "RUNTIME-AUTH-INTEGRATION"))

# Import the frozen harness symbols (module import is guard-protected).
import probe_two_phase_sdk as harness  # noqa: E402

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
    default_registry as default_grant_registry,
)
from lightgravity.coordinator import GraphDispatcher  # noqa: E402
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

TEAM = harness.TEAM
_FAKE_SECRET = harness._FAKE_SECRET


async def run(out_path: Path) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="lg031-qa-boundary-probe-"))
    upstream = harness._UpstreamServer(select_key="beta")
    result: dict[str, Any] = {
        "probe": "lg031-workspace-boundary/qa/product-default-two-phase-sdk",
        "provider": "local-fake-openai-sse",
        "provider_substitute": True,
        "product_real_generation": 0,
        "save_dir_layout": "product-default: <data_dir>/native-sessions/<task> (OUTSIDE workspace_root)",
    }
    try:
        from lightgravity.adapter import SDK_PINNED_VERSION, installed_sdk_version

        result["real_sdk_version"] = installed_sdk_version() or SDK_PINNED_VERSION

        root = tmp / "ws"
        repo = GitRepo(init_repo(root / "task-ws"))
        workspace_root = repo.path.parent
        store = FileStore(tmp / "data", workspace_root)
        build_environment(store, tool_refs=("view-file", "create-file"))
        harness._add_create_file_tool(store)
        harness._create_settings(store)

        current = store.read("connection", "primary").entity.get("revision", 0)
        store.write(
            "connection",
            "primary",
            {
                "backend": "openai-compat",
                "model": "fake-model",
                "credential_ref": "worker-default",
                "base_url": upstream.base_url,
            },
            expected_revision=int(current),
            actor="probe",
        )

        _task_id, run_id, controller, base_context = make_dispatch_setup(
            store,
            budget={
                "max_workers": 3,
                "max_parallel": 1,
                "max_repair_rounds": 1,
                "max_collab_requests": 4,
                "max_model_calls": 6,
            },
        )
        # PRODUCT-DEFAULT save_dir: OUTSIDE workspace_root.
        save_dir = tmp / "data" / "native-sessions" / _task_id
        context = replace(
            base_context,
            objective="produce both artifacts",
            save_dir=str(save_dir),
            planning_request=PlanningRequest(
                trigger=PlanningTrigger.USER_REQUEST,
                reason="probe",
                requested_by="probe",
                max_calls=1,
            ),
        )

        registry = ExecutionGrantRegistry()
        default_grant_registry()._by_token.clear()  # type: ignore[attr-defined]
        default_grant_registry()._by_subtask.clear()  # type: ignore[attr-defined]

        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store),
            credential_resolver=InMemoryCredentialResolver({"worker-default": _FAKE_SECRET}),
            artifacts=DirectoryArtifactSink(tmp / "artifacts"),
            allow_loopback_upstream=True,
            model_calls_cap=12,
            generation_budget=None,
        )
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=TEAM,
            planner=harness.TwoCandidatePlanner(),
            max_parallel=1,
            workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
            collaboration=CollaborationService(
                store,
                policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True),
            ),
            grant_registry=registry,
            autonomous_pool=True,
        )

        # A. The scratch must be inside the root and NOT under save_dir, and the
        # real executor must accept it (no "escapes the authorized root").
        scratch = Path(dispatcher._selection_workspace(context, "slot_qa_0")).resolve()  # noqa: SLF001
        root_real = workspace_root.resolve()
        save_real = save_dir.resolve()
        result["selection_scratch"] = str(scratch)
        result["scratch_inside_root"] = scratch == root_real or root_real in scratch.parents
        result["scratch_not_under_save_dir"] = not (
            scratch == save_real or save_real in scratch.parents
        )
        try:
            result["executor_accepts_scratch"] = executor._resolve_workspace(str(scratch)) == scratch  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            result["executor_accepts_scratch"] = False
            result["executor_accepts_scratch_error"] = str(exc)

        events: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            events.append(event)

        outcome = await dispatcher.dispatch(context, controller, emit)

        # C/D. selected node binding, refs, stopgate.
        subtasks = store.read("run", run_id).entity.get("subtask_refs") or []
        nodes: dict[str, Any] = {}
        for ref in subtasks:
            entity = store.read("subtask", ref).entity
            nodes[entity.get("key")] = {
                "state": entity.get("state"),
                "owner": entity.get("owner"),
                "fence": entity.get("fence"),
                "acceptance": entity.get("acceptance"),
            }
        worktree_root = workspace_root / ".lg-worktrees" / run_id
        workspaces = {
            key: (str(worktree_root / key) if (worktree_root / key).is_dir() else "")
            for key in nodes
        }
        artifacts: dict[str, Any] = {}
        for key, ws in workspaces.items():
            f = Path(ws) / "out" / f"{key}.txt"
            artifacts[key] = {
                "path": str(f),
                "exists": f.is_file(),
                "content": f.read_text() if f.is_file() else None,
            }
        session_ids = [
            e["session"]["session_id"]
            for e in events
            if e.get("type") == "adapter.session_started"
        ]
        stop_confirmation = executor.confirm_stopped(run_id, tuple(session_ids))

        # B. Before selection: verify the phase-1 request carried no write tools.
        # The dispatcher builds selection requests with allowed_tools=() and only
        # the restricted claim tool; assert on the recorded upstream tool names.
        selection_records = [
            r for r in harness._FakeUpstream.records if r["phase"].startswith("selection")
        ]
        execution_records = [
            r for r in harness._FakeUpstream.records if r["phase"].startswith("execution")
        ]
        selection_tool_names = sorted(
            {t for r in selection_records for t in r.get("tool_names", [])}
        )
        result.update(
            {
                "outcome_state": outcome.state,
                "nodes": nodes,
                "workspaces": workspaces,
                "artifacts": {k: {kk: vv for kk, vv in v.items() if kk != "content"} for k, v in artifacts.items()},
                "selected_keys": [k for k, m in nodes.items() if m["state"] == "passed"],
                "sdk_session_ids": session_ids,
                "sdk_session_count": len(session_ids),
                "stop_confirmation": stop_confirmation.to_dict(),
                "selection_phase_requests": len(selection_records),
                "execution_phase_requests": len(execution_records),
                "selection_tool_names": selection_tool_names,
                "beta_selected_non_first": bool(
                    nodes.get("beta", {}).get("state") == "passed"
                    and artifacts.get("beta", {}).get("exists")
                    and artifacts.get("alpha", {}).get("exists")
                ),
                "writer_collision_into_wrong_node": not (
                    artifacts.get("beta", {}).get("exists")
                    and artifacts.get("alpha", {}).get("exists")
                    and "beta" in (artifacts.get("beta", {}).get("content") or "")
                    and "alpha" in (artifacts.get("alpha", {}).get("content") or "")
                    and "/beta/" in artifacts.get("beta", {}).get("path", "")
                    and "/alpha/" in artifacts.get("alpha", {}).get("path", "")
                ),
                # Gate B: before selection the phase-1 session must carry NO
                # write tool.  The SDK also injects its own read-only skill
                # introspection tools (list_skills/lookup_skill/lookup_skills);
                # the product write tools (view-file/create-file) and the SDK
                # write tool ``write_to_file`` must be ABSENT.
                "selection_phase_has_no_product_write_tool": not (
                    {"write_to_file", "create-file", "create_file", "view-file", "view_file"}
                    & set(selection_tool_names)
                ),
                "selection_only_restricted_plus_readonly_skill_tools": set(
                    selection_tool_names
                )
                <= {
                    "discover_and_request_claim",
                    "list_skills",
                    "lookup_skill",
                    "lookup_skills",
                },
            }
        )
        return result
    finally:
        upstream.close()
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
        result["finished_at"] = __import__("time").time()


def _verdict(r: dict[str, Any]) -> tuple[bool, list[str]]:
    gates: list[tuple[str, bool]] = [
        ("A_scratch_inside_root", bool(r.get("scratch_inside_root"))),
        ("A_scratch_not_under_save_dir", bool(r.get("scratch_not_under_save_dir"))),
        ("A_executor_accepts_scratch", bool(r.get("executor_accepts_scratch"))),
        ("B_selection_phase_no_write_tool", bool(r.get("selection_phase_has_no_product_write_tool"))),
        (
            "B_selection_only_restricted_plus_readonly_skill_tools",
            bool(r.get("selection_only_restricted_plus_readonly_skill_tools")),
        ),
        ("C_beta_selected_non_first", bool(r.get("beta_selected_non_first"))),
        ("C_no_writer_collision", r.get("writer_collision_into_wrong_node") is False),
        ("D_session_refs_recorded", bool(r.get("sdk_session_count"))),
        ("D_stop_confirmed", bool((r.get("stop_confirmation") or {}).get("confirmed"))),
    ]
    failed = [name for name, ok in gates if not ok]
    return not failed, failed


def main() -> int:
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else QA_DIR / "evidence" / "product-default-two-phase-sdk.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(run(out))
    ok, failed = _verdict(result)
    result["ok"] = ok
    result["failed_gates"] = failed
    out.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps({k: result[k] for k in (
        "real_sdk_version", "product_real_generation", "save_dir_layout",
        "scratch_inside_root", "scratch_not_under_save_dir", "executor_accepts_scratch",
        "selection_tool_names", "selection_phase_has_no_product_write_tool",
        "outcome_state", "selected_keys", "beta_selected_non_first",
        "writer_collision_into_wrong_node", "sdk_session_count", "stop_confirmation",
        "ok", "failed_gates",
    ) if k in result}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
