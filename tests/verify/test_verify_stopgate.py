"""Stop gate tests (LG-009): confirm stopped + release, never fake a release."""

from __future__ import annotations

from lightgravity.store import FileStore
from lightgravity.verify import StoreResourceStopper

from verify_helpers import make_verifying_task


def test_stop_gate_confirms_and_releases_team(store: FileStore) -> None:
    task_id, run_id, members, _subtasks = make_verifying_task(store, member_state="ready")
    report = StoreResourceStopper(store).stop(task_id, run_id)

    assert report.confirmed is True
    assert report.run_stopped is True
    assert report.sessions_stopped is True
    assert report.slot_released is True
    assert report.members_released == tuple(members)
    assert store.read("member", members[0]).entity["state"] == "released"
    assert store.read("task", task_id).entity["queue"]["state"] == "not_queued"


def test_stop_gate_does_not_fake_release_while_executing(store: FileStore) -> None:
    task_id, run_id, members, _subtasks = make_verifying_task(
        store, run_state="executing", member_state="running"
    )
    report = StoreResourceStopper(store).stop(task_id, run_id)

    assert report.confirmed is False
    assert report.run_stopped is False
    assert report.members_released == ()
    assert store.read("member", members[0]).entity["state"] == "running"
    assert store.read("run", run_id).entity["state"] == "executing"
    assert any("active state" in problem for problem in report.problems)


def test_stop_gate_requires_session_closure(store: FileStore) -> None:
    task_id, run_id, _members, _subtasks = make_verifying_task(
        store, session_refs=("sess_1",), cleanup="running"
    )
    report = StoreResourceStopper(store).stop(task_id, run_id)

    assert report.confirmed is False
    assert report.sessions_stopped is False
    assert any("not confirmed closed" in problem for problem in report.problems)


def test_stop_gate_releases_claimed_execution_slot(store: FileStore) -> None:
    task_id, run_id, _members, _subtasks = make_verifying_task(
        store, queue_state="claimed", queue_owner="coordinator:1"
    )
    report = StoreResourceStopper(store).stop(task_id, run_id)

    assert report.slot_released is True
    assert report.confirmed is True
    queue = store.read("task", task_id).entity["queue"]
    assert queue["state"] == "not_queued"
    assert queue["owner"] is None
