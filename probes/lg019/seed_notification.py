#!/usr/bin/env python3
"""Seed a temp data dir with a bare Task and one durable failed-phase event.

Used by the LG-019 Firefox BiDi shell smoke so the real product UI has a real
durable notification to project. No model call, no Run, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.coordinator import Coordinator  # noqa: E402
from lightgravity.coordinator.dispatcher import (  # noqa: E402
    SingleSlotDispatcher,
    UnavailableExecutor,
)
from lightgravity.store import FileStore  # noqa: E402


def main() -> int:
    data_dir = Path(sys.argv[1])
    workspace = Path(sys.argv[2])
    workspace.mkdir(parents=True, exist_ok=True)
    store = FileStore(data_dir, workspace)
    coordinator = Coordinator(store, dispatcher=SingleSlotDispatcher(UnavailableExecutor()))
    result = coordinator.create_task(
        request_id="lg019-browser-seed",
        title="LG019 browser notification",
        objective="durable notification fixture",
        enqueue=False,
    )
    task_id = result.task_id
    store.append_event(
        task_id,
        {
            "type": "task.phase_changed",
            "actor": "coordinator",
            "task_ref": task_id,
            "run_ref": "run_01J0000000000000000000001",
            "payload": {"from": "executing", "to": "failed", "reason": "smoke fixture failure"},
        },
    )
    print(task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
