"""Event streams, idempotent messages and rebuildable index."""

from __future__ import annotations

import pytest

from lightgravity.store import (
    ConfigInvalid,
    EntityNotFound,
    FileStore,
    new_id,
)
from lightgravity.store.atomic import load_jsonl

from store_helpers import create_task, task_content


def test_event_seq_is_monotonic_and_readable(store: FileStore) -> None:
    stream = create_task(store)
    first = store.append_event(stream, {"type": "task.created", "payload": {"a": 1}})
    second = store.append_event(stream, {"type": "task.phase_changed", "payload": {"a": 2}})
    assert (first.seq, second.seq) == (1, 2)
    assert first.event_id.startswith("evt_")
    events = store.read_events(stream)
    assert [e.seq for e in events] == [1, 2]
    assert [e.type for e in events] == ["task.created", "task.phase_changed"]
    after = store.read_events(stream, after_seq=1)
    assert [e.seq for e in after] == [2]


def test_event_unknown_type_rejected(store: FileStore) -> None:
    stream = create_task(store)
    with pytest.raises(ConfigInvalid):
        store.append_event(stream, {"type": "task.invented"})


def test_event_invalid_stream_rejected(store: FileStore) -> None:
    with pytest.raises(ConfigInvalid):
        store.append_event("../bad", {"type": "task.created"})


def test_read_events_missing_stream_returns_empty(store: FileStore) -> None:
    assert store.read_events(new_id("task")) == []


def test_message_append_is_idempotent(store: FileStore) -> None:
    task_id = create_task(store)
    message_id = "msg_01J000000000000000000000A"
    first = store.append_message(task_id, {"message_id": message_id, "role": "user", "content": "hi"})
    second = store.append_message(task_id, {"message_id": message_id, "role": "user", "content": "changed"})
    assert first.seq == second.seq == 1
    stored = store.read_messages(task_id)
    assert len(stored) == 1
    assert stored[0].message["content"] == "hi"
    assert stored[0].cursor == f"v1:{task_id}:1"


def test_message_cursor_pagination(store: FileStore) -> None:
    task_id = create_task(store)
    store.append_message(task_id, {"message_id": "msg_01J000000000000000000000A", "role": "user", "content": "1"})
    store.append_message(task_id, {"message_id": "msg_01J000000000000000000000B", "role": "assistant", "content": "2"})
    store.append_message(task_id, {"message_id": "msg_01J000000000000000000000C", "role": "user", "content": "3"})
    after_first = store.read_messages(task_id, after=f"v1:{task_id}:1")
    assert [m.seq for m in after_first] == [2, 3]
    assert [m.message["content"] for m in store.read_messages(task_id, limit=1)] == ["1"]


def test_message_requires_existing_task(store: FileStore) -> None:
    with pytest.raises(EntityNotFound):
        store.append_message(new_id("task"), {"message_id": "msg_01J000000000000000000000A"})


def test_message_requires_idempotency_key(store: FileStore) -> None:
    task_id = create_task(store)
    with pytest.raises(ConfigInvalid):
        store.append_message(task_id, {"role": "user", "content": "no id"})


def test_rebuild_index_lists_tasks(store: FileStore) -> None:
    first = create_task(store, title="one")
    second = create_task(store, title="two")
    report = store.rebuild_index()
    assert report.tasks == 2
    assert report.diagnostics == []
    summaries = {summary.id: summary for summary in store.list_tasks()}
    assert set(summaries) == {first, second}
    assert summaries[first].title == "one"
    assert summaries[first].status == "todo"
    assert summaries[first].queue_state == "not_queued"


def test_index_rebuild_reflects_external_edit(store: FileStore) -> None:
    task_id = create_task(store, title="before")
    path = store.entity_path("task", task_id)
    path.write_text(path.read_text().replace("title: before", "title: after"))
    store.rebuild_index()
    assert store.list_tasks()[0].title == "after"


def test_index_reports_invalid_entity_and_duplicate_id(store: FileStore) -> None:
    task_id = create_task(store)
    # A malformed task file (illegal status/phase) must be reported, not indexed.
    bad = store.data_dir / "tasks" / new_id("task") / "TASK.md"
    bad.parent.mkdir(parents=True)
    bad.write_text(
        "---\n"
        "schema: lightgravity.bot/v1\n"
        "kind: task\n"
        f"id: {new_id('task')}\n"
        "status: done\n"
        "phase: executing\n"
        "revision: 0\n"
        "requirements_revision: 1\n"
        "queue: {state: not_queued}\n"
        "acceptance: {status: pending}\n"
        "---\n"
    )
    # Two resource files declaring the same id -> duplicate_id diagnostic.
    agents = store.data_dir / "resources" / "agents"
    agents.mkdir(parents=True)
    (agents / "alpha.md").write_text(
        "---\nschema: lightgravity.bot/v1\nkind: agent\nid: alpha\nrevision: 1\nenabled: true\n---\n"
    )
    (agents / "beta.md").write_text(
        "---\nschema: lightgravity.bot/v1\nkind: agent\nid: alpha\nrevision: 1\nenabled: true\n---\n"
    )
    report = store.rebuild_index()
    codes = {d.code for d in report.diagnostics}
    assert "illegal_status_phase" in codes
    assert "duplicate_id" in codes
    assert report.tasks == 1
    assert (task_id in {s.id for s in store.list_tasks()})


def test_index_is_derived_not_authoritative(store: FileStore) -> None:
    task_id = create_task(store)
    # Corrupt the index layer by discarding it; a rebuild restores the task.
    store._entries = None  # noqa: SLF001 - deliberately simulating a lost cache
    summaries = store.list_tasks()
    assert [s.id for s in summaries] == [task_id]
    raw = load_jsonl(store.data_dir / "tasks" / task_id / "conversation.jsonl")
    assert raw == ([], 0)
    # task_content helper is importable and usable.
    assert task_content()["status"] == "todo"
