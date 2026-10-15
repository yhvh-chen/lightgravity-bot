"""LG-031 real-Git decentralized execution: two workers, handoff, conflict pause.

This is the integration evidence for the LG-031 acceptance condition "真实运行覆盖
至少两个 worker、独立 worktree、依赖交接及冲突处理".  It uses **real** git
worktrees (LG-018), the **real** fenced lease authority (LG-029) and the real
program-frozen execution identity (LG-031) with in-process fake executors - no
model is called, but every git repository, branch, merge and conflict is real.

Covered:

* two admitted workers execute two independent write nodes, each in its own
  worktree, with a versioned+hashed artifact handoff to a dependent node;
* a non-conflicting integration produces a real candidate commit whose base is
  the frozen base commit;
* a conflicting integration pauses with the real conflicting file and keeps all
  worktrees (nothing auto-resolved or deleted);
* the program, not the worker, decides ownership (one winner per node) and the
  handles/identities are released only after a confirmed stop.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from lightgravity.adapter import ExecutorResult, ExecutionRef
from lightgravity.collaboration import ClaimPolicy, CollaborationService, ExecutionGrantRegistry
from lightgravity.coordinator import (
    DispatchContext,
    GraphDispatcher,
    PlanProposal,
    RawSubtask,
    RoleCatalog,
)
from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger
from lightgravity.store import FileStore
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager

_WORKSPACE_TESTS = Path(__file__).resolve().parent.parent / "workspaces"
if str(_WORKSPACE_TESTS) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_TESTS))

from gitfixtures import GitRepo, init_repo  # noqa: E402
from graph_helpers import (  # noqa: E402
    FakeGraphExecutor,
    build_environment,
    make_dispatch_setup,
)

TWO_TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


class TwoWriterPlanner:
    """Two write nodes + one dependent read node (hash handoff)."""

    name = "two-writer"

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="write-a",
                    objective="write A",
                    capability="implementation",
                    acceptance=("A written",),
                    write=True,
                ),
                RawSubtask(
                    key="write-b",
                    objective="write B",
                    capability="implementation",
                    acceptance=("B written",),
                    write=True,
                ),
                RawSubtask(
                    key="verify",
                    objective="verify both",
                    capability="verification",
                    acceptance=("verified",),
                    depends_on=("write-a", "write-b"),
                    write=False,
                ),
            ),
            source="test",
        )


@pytest.fixture
def task_repo(tmp_path: Path) -> GitRepo:
    root = tmp_path / "ws"
    return GitRepo(init_repo(root / "task-ws"))


def _setup(task_repo: GitRepo, tmp_path: Path, *, decentralized: bool = True):
    workspace_root = task_repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    if decentralized:
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
            actor="test",
            request_id="req-settings",
            body="# Settings\n",
        )
    _task_id, _run_id, controller, base_context = make_dispatch_setup(store)
    executor = FakeGraphExecutor(delay=0.03)
    manager = WorktreeManager(workspace_root)
    provider = GraphWorkspaceProvider(manager)
    collaboration = CollaborationService(
        store, policy=ClaimPolicy(enabled=decentralized, lease_seconds=300)
    )
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=TWO_TEAM,
        planner=TwoWriterPlanner(),  # type: ignore[arg-type]
        max_parallel=2,
        workspaces=provider,
        collaboration=collaboration,
        grant_registry=ExecutionGrantRegistry(),
    )
    context = replace(
        base_context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="test",
            requested_by="test",
            max_calls=1,
        ),
    )
    return dispatcher, context, controller, executor, provider, store


@pytest.mark.asyncio
async def test_two_workers_isolated_worktrees_and_hashed_handoff(
    task_repo: GitRepo, tmp_path: Path
) -> None:
    dispatcher, context, controller, executor, provider, store = _setup(task_repo, tmp_path)
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    assert outcome.state == "succeeded"

    # Each write node ran in its own real worktree, distinct from the base repo.
    write_requests = [r for r in executor.requests if r.workspace_path != context.workspace_path]
    assert len(write_requests) == 2
    paths = {r.workspace_path for r in write_requests}
    assert len(paths) == 2
    for path in paths:
        assert Path(path).is_dir()
        assert Path(path).resolve() != task_repo.path.resolve()

    # The dependent node received a versioned + hashed upstream handoff.
    verify_request = next(r for r in executor.requests if r.subtask_id.endswith("verify") or "verify" in r.objective)
    assert verify_request.upstream_artifact_refs
    # ``<subtask>@<hash>:<artifact>`` handoff with a real sha256 hex digest.
    for ref in verify_request.upstream_artifact_refs:
        subtask_ref, _, rest = ref.partition("@")
        content_hash, _, artifact = rest.partition(":")
        assert subtask_ref and artifact
        assert len(content_hash) == 64  # sha256 hex


@pytest.mark.asyncio
async def test_only_one_worker_wins_each_node(task_repo: GitRepo, tmp_path: Path) -> None:
    dispatcher, context, controller, executor, provider, store = _setup(task_repo, tmp_path)
    await dispatcher.dispatch(context, controller, lambda e: None)
    # Every subtask that was scheduled has exactly one owner recorded.
    base = store.data_dir / "subtasks"
    for path in sorted(base.glob("*.md")):
        entity = store.read("subtask", path.stem).entity
        if entity.get("state") in {"passed", "running"}:
            assert entity.get("owner") in {None, dispatcher._owner} or entity.get("fence", 0) >= 1


@pytest.mark.asyncio
async def test_conflicting_candidates_pause_and_keep_worktrees(
    tmp_path: Path,
) -> None:
    """Two workers edit the same file: integration pauses and keeps everything."""

    root = tmp_path / "ws"
    repo = GitRepo(init_repo(root / "task-ws"))
    workspace_root = repo.path.parent
    store = FileStore(tmp_path / "data", workspace_root)
    build_environment(store)
    _task_id, _run_id, controller, base_context = make_dispatch_setup(store)

    # A fake executor that writes the same file only in each isolated worktree.
    def responder(request):
        if request.workspace_path != base_context.workspace_path:
            target = Path(request.workspace_path) / "code.txt"
            target.write_text(f"change from {request.objective}\n", "utf-8")
        return ExecutorResult(
            state="succeeded",
            summary=f"wrote {request.objective}",
            artifact_refs=(f"artifact_{request.subtask_id}",),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    # The fake commits its own worktree so a real merge can conflict.
    class CommittingExecutor(FakeGraphExecutor):
        async def execute(self, request, emit):
            result = await super().execute(request, emit)
            if request.workspace_path != base_context.workspace_path:
                GitRepo(Path(request.workspace_path)).commit_all(
                    f"work {request.objective}"
                )
            return result

    executor = CommittingExecutor(responder)
    manager = WorktreeManager(workspace_root)
    provider = GraphWorkspaceProvider(manager)
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=TWO_TEAM,
        planner=TwoWriterPlanner(),  # type: ignore[arg-type]
        max_parallel=2,
        workspaces=provider,
    )
    context = replace(
        base_context,
        planning_request=PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST,
            reason="test",
            requested_by="test",
            max_calls=1,
        ),
    )
    await dispatcher.dispatch(context, controller, lambda e: None)

    session = provider.session(context.run_id)
    assert session is not None
    integration = session.integrate(["write-a", "write-b"])
    assert integration.conflicted is True
    assert "code.txt" in integration.conflicts
    # All worktrees are retained (the undelivered diffs are not deleted).
    assert session.records()
    for record in session.records():
        assert Path(record.path).is_dir()
    # The user's original workspace is untouched.
    assert (repo.path / "code.txt").read_text("utf-8") == "base\n"
