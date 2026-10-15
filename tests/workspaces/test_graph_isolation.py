"""Graph dispatcher + real worktree isolation wiring (LG-018).

Proves the *product runtime* wiring, not just the worktree manager in
isolation: with a real git workspace and a
:class:`~lightgravity.workspaces.GraphWorkspaceProvider` injected into
:class:`~lightgravity.coordinator.GraphDispatcher`, two independent ``write``
nodes:

* receive **distinct**, real worktree ``workspace_path`` values in the actual
  ``ExecuteRequest`` the executor sees;
* run genuinely in parallel (peak concurrency 2);
* cannot see each other's files, and leave the user's original workspace
  untouched;

and without the provider the same graph is conservatively serialized (single
writer), never faked in parallel.  The executor here is an in-process fake (unit
evidence); the real SDK/DeepSeek path is LG-022.  The git worktrees are real.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

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
from lightgravity.workspaces.manager import WORKTREE_DIRNAME

from conftest import GitRepo, init_repo
from graph_helpers import FakeGraphExecutor, build_environment, make_dispatch_setup

TWO_WRITE = RoleCatalog({"implementation": ["developer"]})


class TwoWritePlanner:
    """Two independent write nodes, no dependencies between them."""

    name = "two-write"

    async def plan(self, context: DispatchContext) -> PlanProposal:
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="write-a",
                    objective="write A",
                    capability="implementation",
                    acceptance=("A is written",),
                    write=True,
                ),
                RawSubtask(
                    key="write-b",
                    objective="write B",
                    capability="implementation",
                    acceptance=("B is written",),
                    write=True,
                ),
            ),
            source="test",
        )


def _make_store(workspace_root: Path, data_dir: Path) -> FileStore:
    return FileStore(data_dir, workspace_root)


async def _run_with_provider(
    repo: GitRepo, data_dir: Path, *, with_provider: bool
):
    # make_dispatch_setup resolves workspace_ref "task-ws" under the store's
    # workspace root, so the authorized Task workspace must be the real git
    # repo itself for a worktree to be isolated from it.
    workspace_root = repo.path.parent
    store = _make_store(workspace_root, data_dir)
    build_environment(store)
    _task_id, _run_id, controller, base_context = make_dispatch_setup(store)
    assert Path(base_context.workspace_path).resolve() == repo.path.resolve()
    # A tiny delay makes genuine overlap observable: without it the fake
    # executor completes synchronously and could not demonstrate parallelism.
    executor = FakeGraphExecutor(delay=0.05)
    provider = (
        GraphWorkspaceProvider(WorktreeManager(workspace_root)) if with_provider else None
    )
    dispatcher = GraphDispatcher(
        store,
        executor,
        catalog=TWO_WRITE,
        planner=TwoWritePlanner(),  # type: ignore[arg-type]
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
    outcome = await dispatcher.dispatch(context, controller, lambda e: None)
    return outcome, executor, workspace_root, store


@pytest.mark.asyncio
async def test_two_write_nodes_get_isolated_worktrees_and_run_parallel(
    task_repo: GitRepo, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    outcome, executor, workspace_root, store = await _run_with_provider(
        task_repo, data_dir, with_provider=True
    )

    assert outcome.state == "succeeded"
    assert len(executor.requests) == 2
    workspaces = {r.workspace_path for r in executor.requests}
    assert len(workspaces) == 2, "each write node must get its own workspace"
    for ws in workspaces:
        assert Path(ws).is_dir()
        assert Path(ws).is_relative_to(workspace_root / WORKTREE_DIRNAME)

    # Real parallelism, not just distinct paths.
    assert executor.peak_concurrent == 2

    # The user's original workspace was never written into.
    assert task_repo.status_porcelain() == ""
    assert not (task_repo.path / "from_a.txt").exists()
    assert not (task_repo.path / "from_b.txt").exists()


@pytest.mark.asyncio
async def test_without_provider_writes_are_serialized(
    task_repo: GitRepo, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    outcome, executor, workspace_root, store = await _run_with_provider(
        task_repo, data_dir, with_provider=False
    )
    assert outcome.state == "succeeded"
    # No isolation: every write node shares the one workspace and cannot overlap.
    assert {r.workspace_path for r in executor.requests} == {str(task_repo.path)}
    assert executor.peak_concurrent == 1
