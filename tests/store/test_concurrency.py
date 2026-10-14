"""Real cross-process concurrency evidence (docs/08 §7, §9).

Each scenario launches several OS processes via ``subprocess`` so ``flock``,
atomic replace and revision checks are exercised across processes, not just
threads.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from lightgravity.store import FileStore
from lightgravity.store.atomic import load_jsonl

from store_helpers import create_task

REPO_ROOT = Path(__file__).resolve().parents[2]

_EVENT_SCRIPT = """
import sys, pathlib
from lightgravity.store import FileStore
data = pathlib.Path(sys.argv[1]); stream = sys.argv[2]; count = int(sys.argv[3])
store = FileStore(data, data / "ws")
for i in range(count):
    store.append_event(stream, {"type": "message.appended", "actor": "proc", "payload": {"i": i}})
"""

_CLAIM_SCRIPT = """
import sys, pathlib
from lightgravity.store import FileStore, LockConflict
data = pathlib.Path(sys.argv[1]); task = sys.argv[2]; owner = sys.argv[3]
store = FileStore(data, data / "ws")
try:
    store.claim(task, owner, lease_seconds=600)
    print("CLAIMED")
except LockConflict:
    print("LOCKED")
"""

_WRITE_SCRIPT = """
import sys, pathlib
from lightgravity.store import FileStore, RevisionConflict
data = pathlib.Path(sys.argv[1]); task = sys.argv[2]; title = sys.argv[3]
store = FileStore(data, data / "ws")
try:
    store.write("task", task, {"title": title}, expected_revision=0, actor="proc")
    print("WROTE")
except RevisionConflict:
    print("CONFLICT")
"""

_MESSAGE_SCRIPT = """
import sys, pathlib
from lightgravity.store import FileStore
data = pathlib.Path(sys.argv[1]); task = sys.argv[2]; message_id = sys.argv[3]; body = sys.argv[4]
store = FileStore(data, data / "ws")
store.append_message(task, {"message_id": message_id, "role": "user", "content": body})
print("OK")
"""


def _run_parallel(script: str, argument_lists: list[list[str]], *, timeout: float = 120.0) -> list[str]:
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, *args],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for args in argument_lists
    ]
    outputs: list[str] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=timeout)
        assert process.returncode == 0, f"worker failed rc={process.returncode}: {stderr}"
        outputs.append(stdout.strip())
    return outputs


def test_concurrent_event_appends_have_no_gaps(store: FileStore, data_dir: Path) -> None:
    task_id = create_task(store)
    workers, per_worker = 4, 20
    outputs = _run_parallel(
        _EVENT_SCRIPT,
        [[str(data_dir), task_id, str(per_worker)] for _ in range(workers)],
    )
    assert outputs == [""] * workers
    events = store.read_events(task_id, limit=1000)
    assert [e.seq for e in events] == list(range(1, workers * per_worker + 1))
    records, bad = load_jsonl(store.data_dir / "events" / task_id / "events.jsonl")
    assert bad == 0
    assert len(records) == workers * per_worker


def test_concurrent_claim_has_single_winner(store: FileStore, data_dir: Path) -> None:
    task_id = create_task(store)
    owners = ["owner-1", "owner-2", "owner-3", "owner-4"]
    outputs = _run_parallel(_CLAIM_SCRIPT, [[str(data_dir), task_id, owner] for owner in owners])
    assert outputs.count("CLAIMED") == 1
    assert outputs.count("LOCKED") == len(owners) - 1
    queue = store.read("task", task_id).entity["queue"]
    assert queue["state"] == "claimed"
    assert queue["owner"] in owners


def test_concurrent_revision_write_has_single_winner(store: FileStore, data_dir: Path) -> None:
    task_id = create_task(store)
    outputs = _run_parallel(
        _WRITE_SCRIPT,
        [[str(data_dir), task_id, f"title-{index}"] for index in range(4)],
    )
    assert outputs.count("WROTE") == 1
    assert outputs.count("CONFLICT") == 3
    current = store.read("task", task_id)
    assert current.revision == 1
    assert current.entity["title"].startswith("title-")


def test_concurrent_duplicate_message_is_idempotent(store: FileStore, data_dir: Path) -> None:
    task_id = create_task(store)
    message_id = "msg_01J000000000000000000000Z"
    outputs = _run_parallel(
        _MESSAGE_SCRIPT,
        [[str(data_dir), task_id, message_id, f"body-{index}"] for index in range(4)],
    )
    assert outputs == ["OK"] * 4
    records, bad = load_jsonl(store.data_dir / "tasks" / task_id / "conversation.jsonl")
    assert bad == 0
    assert [r["message_id"] for r in records] == [message_id]
