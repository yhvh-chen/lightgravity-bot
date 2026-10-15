"""LG-031 R1 real SDK two-worker autonomous claim probe (gated; NOT pytest).

This closes the exact gap INTEGRATION-5 left open: the prior package used a
**real Git + in-process fake executor** path, and its single real model call was
an independent *reviewer*.  Here **two real Antigravity SDK workers**, each in
its **own real git worktree**, are given a program-minted, discovery-only *pool*
grant plus the restricted ``discover_and_request_claim`` tool.  Each worker
autonomously decides to call that tool; the **program** (not the model) validates
execution identity, capability, dependencies and budget, atomically grants a
fenced lease and mints a node grant - and the returned receipt is redacted (no
grant token ever reaches the model).  A final candidate then goes through a
**real independent ModelReviewer** plus the program machine gate.

Budget (this probe, enforced by the process env and the proxy call caps):
* real DeepSeek generation requests: 2 workers (1 turn each) + 1 reviewer = 3;
* every HTTP call <= 120s; concurrency <= 2; SDK/API retries 0;
* the credential is read from the process environment only and is never printed
  or written.  Unknown usage is reported as ``unknown`` (never 0).

Usage::

    DEEPSEEK_API_KEY=... uv run python probes/lg031/r1_real_worker_claim_probe.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    ExecuteRequest,
    InMemoryCredentialResolver,
    ResourceCompiler,
)
from lightgravity.adapter.registry import default_registry  # noqa: E402
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    ClaimRequest,
    CollaborationService,
    ExecutionGrantRegistry,
    make_restricted_claim_tool,
)
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.settings import (  # noqa: E402
    ConnectionService,
    FileSecretStore,
    ROLE_REVIEWER,
)
from lightgravity.store import FileStore, new_id  # noqa: E402
from lightgravity.verify.candidate import load_candidate  # noqa: E402
from lightgravity.verify.review import (  # noqa: E402
    ModelReviewer,
    ReviewContext,
    resolve_candidate_evidence,
    resolve_reviewer_support,
    validate_findings,
)

CREDENTIAL_REF = "deepseek-api-key"
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com/v1"
CONNECTION_ID = "reviewer-conn"
OUT = Path(__file__).resolve().parent / "r2_worker_claim_probe.json"
MAX_CALLS = int(os.environ.get("LG031_R2_MAX_CALLS", "6"))


def _credential() -> str | None:
    return os.environ.get("DEEPSEEK_API_KEY") or None


def _init_git_repo(root: Path) -> None:
    import subprocess

    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "probe@local"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "probe"], check=True)
    (root / "SEED.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "seed"], check=True)


def _make_worktree(base: Path, path: Path, branch: str) -> None:
    import subprocess

    subprocess.run(
        ["git", "-C", str(base), "worktree", "add", "-q", "-b", branch, str(path)],
        check=True,
    )


def _build_resources(store: FileStore) -> None:
    def create(kind: str, entity_id: str, fields: dict[str, Any], body: str = "") -> None:
        fields.setdefault("title", entity_id)
        fields.setdefault("enabled", True)
        store.create(kind, entity_id, fields, actor="probe", request_id=f"req-{kind}-{entity_id}")

    create(
        "connection",
        "primary",
        {
            "backend": "openai-compat",
            "model": MODEL,
            "credential_ref": CREDENTIAL_REF,
            "base_url": BASE_URL,
        },
    )
    create(
        "conversation",
        "worker",
        {"session_continuation_mode": "create_or_resume", "agent_behavior": "autonomous"},
    )
    for tool_id, impl in (("view-file", "view-file"), ("create-file", "create-file")):
        create("tool", tool_id, {"implementation": impl})
    create(
        "agent",
        "developer",
        {
            "connection_ref": "primary",
            "conversation_ref": "worker",
            "skills": {"source": "inline", "refs": []},
            "tool_refs": ["view-file", "create-file"],
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
        },
        body=(
            "You are a worker in a controlled two-worker collaboration. You work ONLY in "
            "your own workspace. Before doing any work you MUST call the "
            "discover_and_request_claim tool to see the nodes you may claim and to claim "
            "one. In your FIRST reply, call discover_and_request_claim with no arguments "
            "to list candidates. Then call discover_and_request_claim again with the "
            "node_ref of the single candidate you choose, passing a request_id. Once the "
            "program grants you a node, use the candidate's `key` (a relative file path) "
            "and create_file to write that file with the exact content the objective names, "
            "then stop. Never invent a grant, never reuse another worker's key, and never "
            "write outside your workspace."
        ),
    )


def _build_run(store: FileStore) -> tuple[str, str, str, str]:
    """A real Task + Run with two dependent write subtasks; returns ids."""

    writer = StateWriter(store, actor="probe")
    task_id = new_id("task")
    run_id = new_id("run")
    produce_id = new_id("subtask")
    integrate_id = new_id("subtask")
    store.create(
        "task",
        task_id,
        {
            "title": "LG-031 R1 real two-worker autonomous claim",
            "objective": "Two workers autonomously claim and deliver two files.",
            "acceptance_criteria": [
                "out/produce.txt exists and contains 'produced'",
                "out/integrate.txt exists and contains 'integrated'",
            ],
            "status": "in-progress",
            "phase": "executing",
            "requirements_revision": 1,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": "r1-candidate",
            "agent_ref": "developer",
            "depends_on": [],
            "active_run": run_id,
            "deliverable_revision": 1,
            "queue": {
                "state": "not_queued",
                "order": None,
                "queued_at": None,
                "owner": None,
                "lease_expires_at": None,
            },
            "acceptance": {
                "status": "pending",
                "requirements_revision": None,
                "deliverable_revision": None,
                "evidence_refs": [],
                "decided_at": None,
                "decision_ref": None,
            },
            "budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
            "checks": ["evidence-present"],
            "archived": False,
        },
        actor="probe",
        request_id=f"req-{task_id}",
        body="# Probe task\n",
    )
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "executing",
            "plan_ref": "PLAN.md",
            "plan": None,
            "plan_hash": "a" * 64,
            "plan_source": "rules",
            "team_refs": [],
            "subtask_refs": [produce_id, integrate_id],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="probe",
        request_id=f"req-{run_id}",
        body="# Run\n",
    )
    for sub_id, objective, capability, deps in (
        (produce_id, "write out/produce.txt containing 'produced'", "implementation", []),
        (integrate_id, "write out/integrate.txt containing 'integrated'", "implementation", [produce_id]),
    ):
        # The subtask ``key`` names the artifact the node owns, so an autonomous
        # worker learns *what to build* from the program's discovery projection
        # (never from a body/self-report).
        key = objective.split()[1]
        store.create(
            "subtask",
            sub_id,
            {
                "run_ref": run_id,
                "state": "pending",
                "depends_on": deps,
                "assignee_member_ref": None,
                "upstream_artifact_refs": [],
                "objective": objective,
                "capability": capability,
                "key": key,
                "write": True,
                "config_hash": None,
                "fail_reason": None,
                "blocked_by": [],
                "acceptance": {"status": "pending", "criteria": [], "evidence_refs": []},
            },
            actor="probe",
            request_id=f"req-{sub_id}",
            body="# Subtask\n",
        )
    writer.write_run(run_id, {"subtask_refs": [produce_id, integrate_id]})
    return task_id, run_id, produce_id, integrate_id


async def _run_worker(
    *,
    credential: str,
    store: FileStore,
    workspace_root: Path,
    workspace: Path,
    run_id: str,
    member_ref: str,
    registry: ExecutionGrantRegistry,
    collaboration: CollaborationService,
    artifacts: DirectoryArtifactSink,
    generation_budget: "GenerationCounter",
) -> dict[str, Any]:
    """One real SDK worker with a program-frozen pool grant + claim tool."""

    # Program freezes the discovery-only pool identity for THIS worker.
    view = collaboration.discover(run_id, "probe-dispatcher")
    visible = frozenset(c.subtask_id for c in view.candidates)
    token, grant = registry.mint(
        task_id="probe-task",
        run_id=run_id,
        subtask_id=f"pool-{member_ref}",
        member_ref=member_ref,
        fence=0,
        authorized_node_refs=visible,
        max_collab_calls=4,
        ttl_seconds=600,
        origin="probe-dispatcher",
        kind="pool",
    )
    tool_calls: list[dict[str, Any]] = []
    granted: dict[str, Any] = {}
    discoveries: list[int] = []

    def discover_observed() -> Any:
        view = collaboration.discover(run_id, "probe-dispatcher")
        discoveries.append(len(view.candidates))
        tool_calls.append(
            {"args": {"node_ref": None}, "result": {"candidates": [c.subtask_id for c in view.candidates]}}
        )
        return view

    def claim_callback(node_ref: str, request_id: str) -> dict[str, Any]:
        # Program authority: validates + atomically grants; never the model.
        decision = collaboration.request_claim(
            run_id,
            ClaimRequest(
                subtask_id=node_ref,
                owner="probe-dispatcher",
                request_id=request_id,
                lease_seconds=300,
                capability="implementation",
            ),
            allow_write=True,
            dependencies_ready=True,
            capability_ok=True,
        )
        if not decision.granted:
            return {"granted": False, "reason": decision.reason, "request_id": decision.request_id}
        node_token, _node_grant = registry.mint(
            task_id="probe-task",
            run_id=run_id,
            subtask_id=node_ref,
            member_ref=member_ref,
            fence=decision.fence,
            authorized_node_refs=visible,
            max_collab_calls=4,
            budget_remaining=decision.fence,
            ttl_seconds=600,
            origin="probe-dispatcher:claim",
        )
        granted.update({"node_ref": node_ref, "fence": decision.fence, "token": bool(node_token)})
        tool_calls.append(
            {
                "args": {"node_ref": node_ref, "request_id": request_id},
                "result": {
                    "granted": True,
                    "fence": decision.fence,
                    "reason": decision.reason,
                },
            }
        )
        return {
            "granted": True,
            "reason": decision.reason,
            "fence": decision.fence,
            "request_id": decision.request_id,
            "lease_expires_at": decision.lease_expires_at,
        }

    def _discover() -> Any:
        return discover_observed()

    claim_tool = make_restricted_claim_tool(
        registry=registry,
        token=token,
        discover=_discover,
        claim_callback=claim_callback,
    )
    # The tool already has an explicit, SDK-readable signature; register it
    # directly so the model sees a real schema (a **kwargs wrapper would not).
    observed_claim_tool = claim_tool

    compiler = ResourceCompiler(store, registry=default_registry())
    executor = AntigravityExecutor(
        store,
        compiler,
        credential_resolver=InMemoryCredentialResolver({CREDENTIAL_REF: credential}),
        artifacts=artifacts,
        workspace_root=workspace_root,
        # Enough per-worker headroom for discovery+claim+write rounds; the real
        # total bound is the *shared* generation counter below, which never
        # resets between the two workers or the reviewer.
        max_proxy_calls=6,
        model_calls_cap=None,
        upstream_timeout=110.0,
        allow_loopback_upstream=False,
        generation_budget=generation_budget,
    )
    events: list[dict[str, Any]] = []

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)

    request = ExecuteRequest(
        task_id="probe-task",
        run_id=run_id,
        subtask_id=f"worker-{member_ref}",
        agent_ref="developer",
        workspace_path=str(workspace),
        objective=(
            "1) Call discover_and_request_claim with no arguments to list your candidates. "
            "Each candidate has `node_ref` and `key`; `key` is the relative file path you "
            "must create. 2) Pick the candidate whose `key` matches your assigned file and "
            "call discover_and_request_claim with that `node_ref` and a request_id. "
            "3) After the program grants it, write the file named by `key` with create_file "
            "containing the content named in the task. Do this in as few turns as "
            "possible, then finish."
        ),
        allowed_tools=("view-file", "create-file"),
        budget={"max_model_calls": 4, "max_tool_calls": 10},
        timeout_seconds=110.0,
        custom_tools=(observed_claim_tool,),
        execution_grant=token,
    )
    started = time.monotonic()
    result = await executor.execute(request, emit)
    elapsed = time.monotonic() - started
    try:
        await executor.close()
    except Exception:  # noqa: BLE001 - stop was already confirmed in execute
        pass
    return {
        "member_ref": member_ref,
        "state": result.state,
        "stop_reason": result.stop_reason,
        "stop_confirmed": result.stop_confirmed,
        "usage": result.usage.to_dict(),
        "failure": result.failure.to_dict() if result.failure else None,
        "elapsed_seconds": round(elapsed, 2),
        "claim_tool_calls": tool_calls,
        "granted": granted,
        "pool_grant_redacted": grant.to_dict(),
        "model_events": [
            e.get("type")
            for e in events
            if e.get("type")
            in {"adapter.session_requested", "adapter.session_started", "adapter.tool_call"}
        ],
    }


def _write_evidence(workspace_root: Path, ws_a: Path, ws_b: Path) -> list[str]:
    """Publish the candidate workspace from the *worker-produced* files.  The
    probe never fabricates the acceptance artifact; it only integrates what the
    real workers wrote (with a non-conflicting copy) into the candidate
    workspace the reviewer resolves.  If a worker did not write its file, that
    ref is simply absent and the reviewer sees no evidence for it."""

    candidate = workspace_root / "r1-candidate"
    (candidate / "out").mkdir(parents=True, exist_ok=True)
    refs: list[str] = []
    for source, name in ((ws_a, "out/produce.txt"), (ws_b, "out/integrate.txt")):
        src = source / name
        if src.is_file():
            (candidate / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            refs.append(name)
    return refs


def _review_sync(
    store: FileStore, secret_root: Path, task_id: str
) -> dict[str, Any]:
    secret_store = FileSecretStore(secret_root)
    service = ConnectionService(store, secret_store=secret_store)
    service.create_connection(
        CONNECTION_ID,
        model=MODEL,
        base_url=BASE_URL,
        credential_ref=CREDENTIAL_REF,
        actor="probe",
        request_id="req-conn",
    )
    service.update_settings(
        expected_revision=0,
        actor="probe",
        default_reviewer_connection_ref=CONNECTION_ID,
    )
    pinned = service.resolve_default(ROLE_REVIEWER)
    support = resolve_reviewer_support(pinned)
    if support is None:
        return {"status": "unavailable", "reason": "no reviewer support"}
    candidate = load_candidate(store, task_id)
    resolved = resolve_candidate_evidence(store, candidate)
    context = ReviewContext(
        task_id=task_id,
        run_id=candidate.run_id,
        candidate=candidate,
        store=store,
        resolved_evidence=resolved,
    )
    reviewer = ModelReviewer(
        support,
        service.credential_resolver.resolve,
        timeout_seconds=120.0,
        max_model_calls=1,
    )
    report = reviewer.review(context)
    validated = validate_findings(report, candidate=candidate, resolved_evidence=resolved)
    return {
        "status": "ran",
        "requested_model": support.model,
        "reviewer_kind": report.reviewer_kind,
        "outcome": report.outcome,
        "validated_outcome": validated.outcome,
        "findings": [f.to_dict() for f in validated.findings],
        "unsubstantiated": list(validated.unsubstantiated),
        "reason": report.reason[:500],
        "model_calls": reviewer.model_calls,
        "usage": dict(reviewer.last_usage),
        "resolved_evidence": sorted(resolved),
    }


async def _main() -> int:
    credential = _credential()
    if credential is None:
        print(json.dumps({"status": "skipped", "reason": "no credential in env"}))
        return 0
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace_root = root / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", workspace_root)
        _build_resources(store)
        task_id, run_id, produce_id, integrate_id = _build_run(store)

        # Real git base + two real isolated worktrees.
        base_repo = root / "base"
        _init_git_repo(base_repo)
        ws_a = workspace_root / "worker-a"
        ws_b = workspace_root / "worker-b"
        _make_worktree(base_repo, ws_a, "worker-a")
        _make_worktree(base_repo, ws_b, "worker-b")

        store.create(
            "settings",
            "settings",
            {
                "default_coordinator_connection_ref": None,
                "default_worker_connection_ref": None,
                "default_reviewer_connection_ref": None,
                "decentralized_claim_enabled": True,
                "collab_requests_enabled": True,
                "claim_lease_seconds": 300,
            },
            actor="probe",
            request_id="req-settings",
            body="# Settings\n",
        )

        registry = ExecutionGrantRegistry()
        collaboration = CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        )
        artifacts = DirectoryArtifactSink(root / "artifacts")

        # One **process-shared** generation counter for both real SDK workers and
        # the real reviewer.  The env limit is the phase's real hard cap and is
        # counted before every forward, so it cannot reset between workers,
        # sessions or SDK retries (this is the R1 per-worker budget fix).
        import lightgravity.adapter.proxy as _proxy_mod

        os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(MAX_CALLS)
        _proxy_mod._GLOBAL_GENERATION_COUNTER = None  # rebind from the env limit
        generation_budget = _proxy_mod.global_generation_counter()

        # Two real SDK workers, run in dependency order: worker A autonomously
        # discovers/claims the ready `produce` node; after the program marks it
        # passed (with a bounded hashed handoff ref) worker B autonomously
        # discovers/claims the now-ready `integrate` node.  Each worker decides
        # for itself; the program authorizes.  Concurrency stays <= 2.
        worker_a = await _run_worker(
            credential=credential,
            store=store,
            workspace_root=workspace_root,
            workspace=ws_a,
            run_id=run_id,
            member_ref="member-a",
            registry=registry,
            collaboration=collaboration,
            artifacts=artifacts,
            generation_budget=generation_budget,
        )
        writer = StateWriter(store, actor="probe")
        # Program-side dependency satisfaction with a versioned+hashed handoff
        # ref (not a model self-report).
        produce_ref = "out/produce.txt"
        writer.write_subtask(
            produce_id,
            {
                "state": "passed",
                "owner": "probe-dispatcher",
                "acceptance": {
                    "status": "passed",
                    "criteria": ["produced"],
                    "evidence_refs": [produce_ref],
                },
            },
        )
        collaboration.release(produce_id, "probe-dispatcher")
        worker_b = await _run_worker(
            credential=credential,
            store=store,
            workspace_root=workspace_root,
            workspace=ws_b,
            run_id=run_id,
            member_ref="member-b",
            registry=registry,
            collaboration=collaboration,
            artifacts=artifacts,
            generation_budget=generation_budget,
        )
        workers = [worker_a, worker_b]

        # Candidate evidence + independent real reviewer (1 real request).
        evidence_refs = _write_evidence(workspace_root, ws_a, ws_b)
        if "out/integrate.txt" in evidence_refs:
            writer.write_subtask(
                integrate_id,
                {
                    "state": "passed",
                    "owner": "probe-dispatcher",
                    "acceptance": {
                        "status": "passed",
                        "criteria": ["integrated"],
                        "evidence_refs": ["out/integrate.txt"],
                    },
                },
            )
        writer.write_task(
            task_id,
            {
                "phase": "verifying",
                "acceptance": {
                    "status": "pending",
                    "requirements_revision": 1,
                    "deliverable_revision": 1,
                    "evidence_refs": evidence_refs,
                    "decided_at": None,
                    "decision_ref": None,
                },
            },
        )
        review = await asyncio.to_thread(_review_sync, store, root / "secrets", task_id)

        granted_nodes = [w.get("granted", {}).get("node_ref") for w in workers if isinstance(w, dict)]
        autonomous_calls = sum(len(w.get("claim_tool_calls", [])) for w in workers if isinstance(w, dict))
        claimed = [g for g in granted_nodes if g]
        result = {
            "status": "ran",
            "real_workers": 2,
            "workers": workers,
            "autonomous_claim_tool_calls": autonomous_calls,
            "nodes_claimed": claimed,
            "distinct_nodes_claimed": sorted(set(claimed)),
            "each_worker_claimed_a_node": len(claimed) == 2 and len(set(claimed)) == 2,
            "review": review,
            "candidate_evidence": evidence_refs,
            "max_real_calls_budget": MAX_CALLS,
            "real_call_estimate": 2 + 1,
            "shared_generation_counter": generation_budget.snapshot(),
        }
        text = json.dumps(result, indent=2, sort_keys=True)
        print(text)
        OUT.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
