"""LG-133 queued cancellation bookkeeping; deterministic, no SDK/model."""
from __future__ import annotations

import pytest

from lightgravity.api.team_groups import build_team_group
from lightgravity.coordinator.queue import TaskQueue
from lightgravity.store import FileStore

from coordinator_helpers import FakeExecutor, make_coordinator


@pytest.mark.parametrize('already_cancelled', [False, True])
async def test_cancel_without_run_clears_queue_and_retains_history_without_workers(
    store: FileStore, already_cancelled: bool,
) -> None:
    executor = FakeExecutor()
    coordinator = make_coordinator(store, executor)
    task_id = coordinator.create_task('queued', 'Queued task', 'do queued work').task_id
    sibling_id = coordinator.create_task('sibling', 'Other task', 'independent').task_id
    assert task_id is not None and sibling_id is not None
    task = store.read('task', task_id)
    queue = {**task.entity['queue'], 'waiting_reason': 'active_task_limit', 'custom': 'preserved'}
    store.write('task', task_id, {'queue': queue}, expected_revision=task.revision, actor='test')
    if already_cancelled:
        task = store.read('task', task_id)
        # Exact old-control failure shape, not a migration or edited QA record.
        store.write('task', task_id, {'phase': 'cancelled'}, expected_revision=task.revision, actor='test')
    sibling = store.read('task', sibling_id)
    result = await coordinator.request_control(task_id, 'cancel', request_id='cancel-queued')
    assert result.data['confirmed'] is True
    after = store.read('task', task_id)
    assert after.entity['queue'] == {**queue, 'state': 'not_queued', 'owner': None, 'lease_expires_at': None, 'waiting_reason': None}
    assert after.entity['phase'] == 'cancelled' and after.entity['status'] == 'todo'
    group = build_team_group(store, after)
    assert group['_released'] is True
    assert group['active_run'] is None and group['runs'] == [] and group['members'] == []
    assert store.read('task', sibling_id) == sibling
    assert not executor.requests and executor.cancel_calls == 0
    assert TaskQueue(store).next_queued().id == sibling_id
    replay = await coordinator.request_control(task_id, 'cancel', request_id='cancel-queued')
    assert replay == result
    assert store.read('task', task_id).revision == after.revision


async def test_cancel_after_claim_before_job_starts_never_creates_a_run(store: FileStore) -> None:
    executor = FakeExecutor()
    coordinator = make_coordinator(store, executor)
    task_id = coordinator.create_task('claim', 'Claimed task', 'do work').task_id
    assert task_id is not None
    assert await coordinator._pump_once()
    # The pump has admitted/claimed the Task, but its created asyncio job has
    # not had a turn yet. Cancel can be handled in this same event-loop gap.
    job = coordinator._running_tasks[task_id]
    assert coordinator.status(task_id)['active_run'] is None
    result = await coordinator.request_control(task_id, 'cancel', request_id='cancel-claimed')
    assert result.data['confirmed'] is True
    await job
    coordinator._reap_finished_jobs()
    group = build_team_group(store, store.read('task', task_id))
    assert group['runs'] == []
    assert group['_released'] is True
    assert not executor.requests
    assert coordinator.capacity_snapshot()['admitted_count'] == 0
    assert TaskQueue(store).next_queued() is None


async def test_no_run_cancel_does_not_drop_another_owners_live_claim(store: FileStore) -> None:
    coordinator = make_coordinator(store, FakeExecutor())
    task_id = coordinator.create_task('foreign', 'Claimed elsewhere', 'do work').task_id
    assert task_id is not None
    store.claim(task_id, 'another-coordinator', lease_seconds=300)
    before = store.read('task', task_id)
    result = await coordinator.request_control(task_id, 'cancel', request_id='cancel-foreign')
    assert result.data['state'] == 'unconfirmed' and result.data['confirmed'] is False
    assert store.read('task', task_id) == before
