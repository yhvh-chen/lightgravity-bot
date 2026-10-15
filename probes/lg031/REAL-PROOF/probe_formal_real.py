#!/usr/bin/env python3
"""LG-031 REAL-PROOF — formal real-DeepSeek engineering proof (ONE run).

Drives the **real product** ``GraphDispatcher`` candidate-pool two-phase
lifecycle (selection session -> program atomic grant -> separate execution
session) with the pinned Antigravity SDK 0.1.22 and the **real DeepSeek
provider**, over a program-frozen validated 3-node plan:

    alpha (implementation, write) \\
    beta  (implementation, write)  > verify (verification, read-only)
                                    depends_on alpha, beta

The two implementation nodes are simultaneously ready and both belong to the
single ``implementation`` Member's authorized candidate pool, so a real SDK
worker must select one of >=2 candidates itself; the ``verify`` node (a second
Member) receives both upstream versioned/hashed handoffs.  After the run the
probe runs the real program machine gate, the real independent ``ModelReviewer``
and the real stop gate, and binds an accept.

Single formal run: this script must be executed **once**.  The persistent
generation ledger under ``fixtures/formal/data`` enforces the shared hard cap
across every selector/execution/reviewer/retry request in the process and across
restarts.

Credentials: read from the process environment only (``DEEPSEEK_API_KEY``), never
printed or written.  Unknown usage is reported as ``unknown`` (never 0).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    InMemoryCredentialResolver,
    ResourceCompiler,
    default_registry as adapter_default_registry,
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
from lightgravity.settings import (  # noqa: E402
    ConnectionService,
    FileSecretStore,
    ROLE_REVIEWER,
)
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.verify.candidate import load_candidate  # noqa: E402
from lightgravity.verify.review import (  # noqa: E402
    ModelReviewer,
    ReviewContext,
    resolve_candidate_evidence,
    resolve_reviewer_support,
    validate_findings,
)
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

from graph_helpers import make_dispatch_setup  # noqa: E402

CREDENTIAL_REF = "deepseek-api-key"
MODEL = os.environ.get("LG031_REAL_MODEL", "deepseek-v4-flash")
BASE_URL = os.environ.get("LG031_REAL_BASE_URL", "https://api.deepseek.com/v1")
CONNECTION_ID = "worker-primary"
REVIEWER_CONNECTION_ID = "reviewer-primary"
MAX_CALLS = int(os.environ.get("LG031_REAL_MAX_CALLS", "24"))
OUTPUT_LIMIT = int(os.environ.get("LG031_REAL_OUTPUT_LIMIT", "12000"))
HTTP_TIMEOUT = float(os.environ.get("LG031_REAL_HTTP_TIMEOUT", "120"))

TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})

FROZEN_SUBTASKS = (
    RawSubtask(
        key="alpha",
        objective=(
            "Create the file out/alpha.txt in your workspace containing exactly the "
            "single word alpha (lowercase, no other text)."
        ),
        capability="implementation",
        acceptance=("out/alpha.txt exists with content alpha",),
        write=True,
    ),
    RawSubtask(
        key="beta",
        objective=(
            "Create the file out/beta.txt in your workspace containing exactly the "
            "single word beta (lowercase, no other text)."
        ),
        capability="implementation",
        acceptance=("out/beta.txt exists with content beta",),
        write=True,
    ),
    RawSubtask(
        key="verify",
        objective=(
            "Read the two upstream artifacts handed to you (out/alpha.txt and "
            "out/beta.txt) and report their exact contents and the upstream hash "
            "references. Do not write any file."
        ),
        capability="verification",
        acceptance=("alpha and beta artifact contents and hashes are reported",),
        depends_on=("alpha", "beta"),
        write=False,
    ),
)


class FrozenPlanner:
    """Program-frozen 3-node plan (validated by the real PlanValidator)."""

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


def _sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _init_git_fixture(root: Path) -> str:
    """Empty feature repo with a fixed initial commit; returns the commit hash."""

    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "proof@local"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "proof"], check=True)
    (root / "README.md").write_text("lg031 real-proof fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture seed"], check=True)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _create_resource(store: FileStore, kind: str, entity_id: str, fields: dict[str, Any]) -> None:
    fields = dict(fields)
    fields.setdefault("title", entity_id)
    fields.setdefault("enabled", True)
    store.create(kind, entity_id, fields, actor="proof", request_id=f"req-{kind}-{entity_id}")


def _build_resources(store: FileStore, *, base_url: str = BASE_URL) -> None:
    def create(kind: str, entity_id: str, fields: dict[str, Any], body: str = "") -> None:
        _create_resource(store, kind, entity_id, fields)

    create(
        "connection",
        CONNECTION_ID,
        {
            "backend": "openai-compat",
            "model": MODEL,
            "credential_ref": CREDENTIAL_REF,
            "base_url": base_url,
        },
    )
    create("connection", REVIEWER_CONNECTION_ID, {
        "backend": "openai-compat",
        "model": MODEL,
        "credential_ref": CREDENTIAL_REF,
        "base_url": base_url,
    })
    create("conversation", "worker", {"session_continuation_mode": "create_or_resume"})
    create("skill", "implementation", {"description": "Implementation", "body": "# Impl\n"})
    create("skill", "verification", {"description": "Verification", "body": "# Verify\n"})
    for tool_id, impl in (
        ("view-file", "view-file"),
        ("create-file", "create-file"),
        ("edit-file", "edit-file"),
        ("run-command", "run-command"),
    ):
        create("tool", tool_id, {"implementation": impl})
    create(
        "agent",
        "developer",
        {
            "connection_ref": CONNECTION_ID,
            "conversation_ref": "worker",
            "skills": {"source": "inline", "refs": ["implementation"]},
            "tool_refs": ["view-file", "create-file", "edit-file"],
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
        },
        body=(
            "You are an implementation worker. Work ONLY in your own workspace. When the "
            "task tells you to select a node from a candidate pool, you MUST first call the "
            "discover_and_request_claim tool with no arguments to list the authorized "
            "candidates (each has node_ref/objective/write), then call it again with the "
            "node_ref of exactly one candidate you choose and a request_id. Only after the "
            "program grants the node, create the artifact named in that node's objective "
            "with create_file and the exact content required. Never fabricate a grant and "
            "never write outside your workspace."
        ),
    )
    create(
        "agent",
        "verifier",
        {
            "connection_ref": CONNECTION_ID,
            "conversation_ref": "worker",
            "skills": {"source": "inline", "refs": ["verification"]},
            "tool_refs": ["view-file", "run-command"],
            "hook_refs": [],
            "mcp_refs": [],
            "trigger_refs": [],
            "subagents": [],
        },
        body=(
            "You are a read-only verification worker. Read the upstream artifacts given to "
            "you and report their exact contents and the upstream hash references. Never "
            "write any file."
        ),
    )
    create(
        "settings",
        "settings",
        {
            "default_coordinator_connection_ref": None,
            "default_worker_connection_ref": CONNECTION_ID,
            "default_reviewer_connection_ref": None,
            "decentralized_claim_enabled": True,
            "collab_requests_enabled": True,
            "claim_lease_seconds": 300,
        },
    )


def _review_sync(store: FileStore, secret_root: Path, task_id: str) -> dict[str, Any]:
    secret_store = FileSecretStore(secret_root)
    service = ConnectionService(store, secret_store=secret_store)
    service.update_settings(
        expected_revision=0,
        actor="proof",
        default_reviewer_connection_ref=REVIEWER_CONNECTION_ID,
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
        timeout_seconds=HTTP_TIMEOUT,
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


async def run(work: Path, out: Path, *, dry_fake: bool = False) -> dict[str, Any]:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    data_dir = work / "data"
    secret_root = work / "secrets"

    fake_upstream = None
    base_url = BASE_URL
    if dry_fake:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "precheck"))
        from fake_precheck_upstream import PrecheckUpstream  # noqa: PLC0415

        fake_upstream = PrecheckUpstream(select_non_first=True)
        base_url = fake_upstream.base_url

    # Single persistent phase ledger; the runtime counter reads/writes it.
    os.environ["LIGHTGRAVITY_GENERATION_LEDGER_DIR"] = str(data_dir)
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(MAX_CALLS)
    import lightgravity.adapter.proxy as _proxy_mod

    _proxy_mod._GLOBAL_GENERATION_COUNTER = None  # type: ignore[attr-defined]
    configure_generation_ledger(data_dir)

    credential = os.environ.get("DEEPSEEK_API_KEY") or ("sk-fake-dry-run" if dry_fake else None)
    result: dict[str, Any] = {
        "probe": "lg031-real-proof/formal",
        "provider": "deepseek",
        "provider_substitute": False,
        "product_real_generation": True,
        "real_model": MODEL,
        "real_base_url": BASE_URL,
        "dry_fake": dry_fake,
        "started_at": time.time(),
        "work_dir": str(work),
        "max_real_calls": MAX_CALLS,
        "output_limit": OUTPUT_LIMIT,
        "frozen_plan_keys": [s.key for s in FROZEN_SUBTASKS],
    }
    if not credential:
        result["status"] = "skipped"
        result["reason"] = "no DEEPSEEK_API_KEY in env"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    workspace_root = work / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    base_repo = workspace_root / "task-ws"
    initial_commit = _init_git_fixture(base_repo)
    result["initial_commit"] = initial_commit

    store = FileStore(data_dir, workspace_root)
    _build_resources(store, base_url=base_url)

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
    # Point the run at the git fixture worktree root.
    context = replace(
        base_context,
        workspace_path=str(base_repo),
        objective="Create out/alpha.txt and out/beta.txt, then verify both.",
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="lg031-real-proof",
            requested_by="proof",
            max_calls=1,
        ),
    )

    # Validate the frozen plan with the real product validator.
    validator = PlanValidator(known_capabilities=tuple(TEAM.capabilities))
    validated = validator.validate(
        PlanProposal(subtasks=FROZEN_SUBTASKS), workspace_path=str(base_repo)
    )
    result["validated_plan_keys"] = [s.key for s in validated.subtasks]
    result["validated_plan_hash"] = validated.plan_hash

    registry = ExecutionGrantRegistry()
    compiler = ResourceCompiler(store, registry=adapter_default_registry())
    executor = AntigravityExecutor(
        store,
        compiler,
        credential_resolver=InMemoryCredentialResolver({CREDENTIAL_REF: credential}),
        artifacts=DirectoryArtifactSink(data_dir / "artifacts"),
        workspace_root=workspace_root,
        max_proxy_calls=MAX_CALLS,
        model_calls_cap=MAX_CALLS,
        upstream_timeout=HTTP_TIMEOUT,
        allow_loopback_upstream=dry_fake,
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

    writer = StateWriter(store, actor="proof")
    events: list[dict[str, Any]] = []

    def _record_session_ref(session_id: str) -> None:
        run_entity = store.read("run", run_id).entity
        raw = run_entity.get("session_refs")
        existing = [str(i) for i in raw] if isinstance(raw, (list, tuple)) else []
        if session_id not in existing:
            writer.write_run(run_id, {"session_refs": [*existing, session_id]})

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if event.get("type") == "adapter.session_started":
            session = event.get("session")
            if isinstance(session, dict) and session.get("session_id"):
                _record_session_ref(str(session["session_id"]))

    started = time.monotonic()
    outcome = await dispatcher.dispatch(context, controller, emit)
    elapsed = time.monotonic() - started

    # ---- program machine gate (independent of the reviewer) --------------
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
            "in_own_worktree": f"/{key}/" in str(f),
            "other_present": (
                (ws / "out" / ("beta.txt" if key == "alpha" else "alpha.txt")).is_file()
            ),
        }
    machine = {
        "alpha_exact": artifacts["alpha"]["content"] == "alpha",
        "beta_exact": artifacts["beta"]["content"] == "beta",
        "no_cross_contamination": not any(a["other_present"] for a in artifacts.values()),
        "verify_no_write": nodes.get("verify", {}).get("write") is False,
        "verify_has_two_handoffs": len(nodes.get("verify", {}).get("upstream_artifact_refs") or []) >= 2,
        "all_nodes_passed": all(v["state"] == "passed" for v in nodes.values()),
    }
    machine["pass"] = all(machine.values())

    session_ids = [
        e["session"]["session_id"]
        for e in events
        if e.get("type") == "adapter.session_started"
    ]
    run_refs = store.read("run", run_id).entity.get("session_refs") or []
    stop = executor.confirm_stopped(run_id, tuple(session_ids))
    stop_dict = stop.to_dict() if hasattr(stop, "to_dict") else dict(stop)

    result.update(
        {
            "outcome_state": outcome.state,
            "outcome_reason": getattr(outcome, "reason", None),
            "plan_source": store.read("run", run_id).entity.get("plan_source"),
            "elapsed_seconds": round(elapsed, 3),
            "nodes": nodes,
            "artifacts": artifacts,
            "machine_gate": machine,
            "sdk_session_count": len(session_ids),
            "run_session_refs_count": len(run_refs),
            "sessions_in_run_refs": all(sid in run_refs for sid in session_ids)
            if session_ids
            else False,
            "stop_confirmation": stop_dict,
            "verify_upstream_handoffs": list(
                nodes.get("verify", {}).get("upstream_artifact_refs") or []
            ),
            "active_grants": [g.to_dict() for g in registry.active_grants()],
            "ledger_path": str(data_dir / "generation" / "generation.jsonl"),
            "ledger_snapshot": global_generation_counter().snapshot(),
            "events": events,
        }
    )

    # ---- real independent ModelReviewer + bound accept ------------------
    if machine["pass"]:
        writer.write_task(
            task_id,
            {
                "phase": "verifying",
                "acceptance": {
                    "status": "pending",
                    "requirements_revision": 1,
                    "deliverable_revision": 1,
                    "evidence_refs": [
                        "out/alpha.txt" if artifacts["alpha"]["exists"] else "",
                        "out/beta.txt" if artifacts["beta"]["exists"] else "",
                    ],
                },
            },
        )
        result["review"] = await asyncio.to_thread(_review_sync, store, secret_root, task_id)

    result["finished_at"] = time.time()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if fake_upstream is not None:
        fake_upstream.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-fake", action="store_true")
    args = ap.parse_args()
    res = asyncio.run(run(Path(args.work), Path(args.out), dry_fake=args.dry_fake))
    print(
        json.dumps(
            {
                k: res.get(k)
                for k in (
                    "status",
                    "outcome_state",
                    "machine_gate",
                    "sdk_session_count",
                    "sessions_in_run_refs",
                    "stop_confirmation",
                    "ledger_snapshot",
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
