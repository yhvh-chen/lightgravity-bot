"""Partial-write recovery and stale temp-file cleanup (fault injection)."""

from __future__ import annotations

import json

from lightgravity.store import FileStore
from lightgravity.store.atomic import TEMP_PREFIX, load_jsonl

from store_helpers import create_task


def test_recover_removes_stale_temp_files(store: FileStore) -> None:
    task_id = create_task(store)
    leftovers = [
        store.data_dir / "tasks" / task_id / f"{TEMP_PREFIX}abc",
        store.data_dir / f"{TEMP_PREFIX}root",
    ]
    for path in leftovers:
        path.write_text("partial")
    report = store.recover()
    assert sorted(report.removed_temp_files) == sorted(str(p) for p in leftovers)
    assert all(not path.exists() for path in leftovers)


def test_recover_truncates_partial_conversation_line(store: FileStore) -> None:
    task_id = create_task(store)
    path = store.data_dir / "tasks" / task_id / "conversation.jsonl"
    path.write_text(
        json.dumps({"message_id": "msg_01J000000000000000000000A", "seq": 1}) + "\n" + '{"message_id": "msg_01J00'
    )
    report = store.recover()
    assert str(path) in report.truncated_jsonl
    assert report.recorded_events == 1
    records, bad = load_jsonl(path)
    assert bad == 0
    assert [r["seq"] for r in records] == [1]
    # A subsequent append keeps sequence continuity after truncation.
    appended = store.append_message(task_id, {"message_id": "msg_01J000000000000000000000B", "role": "user"})
    assert appended.seq == 2
    # The recovery is recorded as an event on the owning task stream.
    event_types = [e.type for e in store.read_events(f"task_{task_id}")]
    assert "error.recorded" in event_types


def test_recover_truncates_partial_event_stream(store: FileStore) -> None:
    task_id = create_task(store)
    store.append_event(task_id, {"type": "task.created"})
    path = store.data_dir / "events" / task_id / "events.jsonl"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"schema": "lightgravity.bot/v1", "seq": 2')
    report = store.recover()
    assert str(path) in report.truncated_jsonl
    # Existing seq is preserved and the next append continues from it.
    assert [e.seq for e in store.read_events(task_id)] == [1, 2]
    assert store.read_events(task_id)[-1].type == "error.recorded"


def test_recover_is_noop_on_clean_store(store: FileStore) -> None:
    create_task(store)
    store.append_event(create_task(store), {"type": "task.created"})
    report = store.recover()
    assert report.removed_temp_files == []
    assert report.truncated_jsonl == []
    assert report.recorded_events == 0
    assert report.diagnostics == []


def test_recover_does_not_touch_user_data_outside_store(store: FileStore, tmp_path) -> None:
    outside = tmp_path / "precious.txt"
    outside.write_text("untouched")
    store.recover()
    assert outside.read_text() == "untouched"
