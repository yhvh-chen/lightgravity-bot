"""Retry lineage regressions using real persisted Tasks/Runs and fake execution."""
from __future__ import annotations

import pytest

from lightgravity.contracts import AppError, EventType
from lightgravity.store import FileStore
from coordinator_helpers import FakeExecutor, make_coordinator


async def failed_delivery(store: FileStore):
    executor = FakeExecutor(state="failed")
    coordinator = make_coordinator(store, executor)
    task_id = coordinator.create_task("initial", "Game", "reuse game").task_id
    assert task_id is not None
    assert await coordinator._process_one()
    run_id = executor.requests[0].run_id
    assert store.read("run", run_id).entity["state"] == "failed"
    return coordinator, executor, task_id, run_id


async def test_terminal_failure_retains_run_and_retry_advances_attempt(store: FileStore) -> None:
    coordinator, executor, task_id, first = await failed_delivery(store)
    task = store.read("task", task_id).entity
    assert task["active_run"] is None
    assert task["last_run"] == first
    assert (await coordinator.request_control(task_id, "retry", request_id="retry")).data["confirmed"]
    await coordinator.request_control(task_id, "retry", request_id="retry")
    assert await coordinator._process_one()
    assert len(executor.requests) == 2
    second = executor.requests[-1]
    assert second.run_id != first
    assert second.task_id == task_id and second.attempt == 2
    assert second.conversation_id is None and second.continuation_mode is None
    assert store.read("task", task_id).entity["requirements_revision"] == 1
    assert len(store.list_tasks()) == 1
    assert not await coordinator._process_one()


async def test_legacy_missing_pointer_uses_attributed_history_and_current_scope(store: FileStore) -> None:
    coordinator, executor, task_id, first = await failed_delivery(store)
    task = store.read("task", task_id)
    legacy = dict(task.entity)
    legacy.pop("last_run")
    legacy["requirements_revision"] = 2
    legacy["workspace_ref"] = f"tasks/{task_id}"
    workspace = store.resolve_path(legacy["workspace_ref"], write=True)
    workspace.mkdir(parents=True)
    names = ("design.md", "index.html", "VERIFICATION.md", "README-PENGUIN-POP.md", "DELIVERY.md")
    for name in names:
        (workspace / name).write_text(f"preserved {name}")
    from lightgravity.workspaces.git import GitRunner
    from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager

    runner = GitRunner(workspace.parent / ".scratch")
    runner.ok(["init", "--template=", "-b", "main"], cwd=workspace)
    runner.ok(["add", *names], cwd=workspace)
    runner.ok(["commit", "-m", "preserved inputs"], cwd=workspace)
    store.write(
        "task", task_id, legacy, expected_revision=task.revision, actor="legacy-fixture",
        body="Reuse preserved game inputs; avoid optional polish.",
    )
    old = store.read("run", first)
    old_entity = dict(old.entity, continuation={
        "conversation_id": "stopped-native-conversation", "save_dir": "/stopped/session",
        "continuation_mode": "create_only", "config_version": 1,
    })
    store.write("run", first, old_entity, expected_revision=old.revision, actor="legacy-fixture")
    # Old failure's cleanup remains pending: this must be a fresh session,
    # never continuation into its stopped native session.
    old = store.read("run", first)
    assert old.entity["cleanup"]["status"] == "pending"
    await coordinator.request_control(task_id, "retry")
    assert await coordinator._process_one()
    request = executor.requests[-1]
    assert request.attempt == 2 and request.task_id == task_id
    assert request.conversation_id is None
    assert request.workspace_path == str(workspace)
    assert "avoid optional polish" in request.instructions
    isolated = GraphWorkspaceProvider(WorktreeManager(workspace.parent.parent)).isolate(
        task_id=task_id, run_id=request.run_id, node_key="deliver",
        subtask_id=request.subtask_id, base_workspace=request.workspace_path,
    )
    assert isolated is not None
    from pathlib import Path
    for name in names:
        assert (Path(isolated) / name).read_text() == f"preserved {name}"
    assert store.read("task", task_id).entity["requirements_revision"] == 2
    assert store.read("run", first).entity == old.entity


async def test_history_pages_and_excludes_another_tasks_run(store: FileStore) -> None:
    coordinator, executor, task_id, first = await failed_delivery(store)
    task = store.read("task", task_id)
    legacy = dict(task.entity)
    legacy.pop("last_run")
    store.write("task", task_id, legacy, expected_revision=task.revision, actor="legacy-fixture")
    for i in range(505):
        coordinator._writer.emit(task_id, EventType.ERROR_RECORDED, {"message": str(i)}, task_ref=task_id)
    # A later correctly attributed Run beyond the first history page.
    await coordinator.request_control(task_id, "retry")
    assert await coordinator._process_one()
    second = executor.requests[-1].run_id
    other = coordinator.create_task("other", "Other", "unrelated").task_id
    assert other is not None
    assert await coordinator._process_one()
    foreign = executor.requests[-1].run_id
    coordinator._writer.emit(
        task_id, EventType.RUN_CREATED, {"run_id": foreign, "attempt": 999},
        task_ref=task_id, run_ref=foreign,
    )
    task = store.read("task", task_id)
    legacy = dict(task.entity)
    legacy.pop("last_run")
    store.write("task", task_id, legacy, expected_revision=task.revision, actor="legacy-fixture")
    assert coordinator._historical_run(task_id)[0] == second
    await coordinator.request_control(task_id, "retry")
    assert await coordinator._process_one()
    assert executor.requests[-1].task_id == task_id
    assert executor.requests[-1].attempt == 3


async def test_history_cannot_admit_second_writer(store: FileStore) -> None:
    coordinator, executor, task_id, first = await failed_delivery(store)
    task = store.read("task", task_id)
    legacy = dict(task.entity)
    legacy.pop("last_run")
    store.write("task", task_id, legacy, expected_revision=task.revision, actor="legacy-fixture")
    run = store.read("run", first)
    live = dict(run.entity, state="executing")
    store.write("run", first, live, expected_revision=run.revision, actor="inconsistent-fixture")
    await coordinator.request_control(task_id, "retry")
    with pytest.raises(AppError, match="non-terminal Run"):
        await coordinator._process_one()
    assert len(executor.requests) == 1
