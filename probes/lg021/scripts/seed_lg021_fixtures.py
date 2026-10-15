#!/usr/bin/env python3
"""Seed a temp data dir + workspace for the LG-021 browser QA.

Deterministic, no network, no model call.  Creates a small but real set of
durable entities so the real product UI (served over same-origin loopback HTTP
by the ``lightgravity`` CLI) has genuine backed states to render:

* several Tasks across distinct real phases (queued / failed /
  awaiting_acceptance / recovery_required / cancelled) plus an archived Task
  for the history filter;
* one Task with a very long title and a long Markdown body (tables + fenced
  code + long path) for the long-content / overflow checks;
* workspace files (deep path, long filename, long log, markdown table) under
  the authorized workspace root for the Files view;
* one durable ``task.phase_changed -> failed`` event so a real notification is
  projected (same mechanism LG-019 uses).

Usage: seed_lg021_fixtures.py DATA_DIR WORKSPACE_DIR
Prints a JSON summary (task ids by label) on stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.coordinator import Coordinator  # noqa: E402
from lightgravity.coordinator.dispatcher import (  # noqa: E402
    SingleSlotDispatcher,
    UnavailableExecutor,
)
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.store.ids import new_id  # noqa: E402

LONG_TITLE = (
    "Refactor the batch intake pipeline so that every recovered document keeps a "
    "stable source revision, an auditable extraction receipt, and a deterministic "
    "re-index path across restarts — including the very long tail of edge cases "
    "that only surface when a job is cancelled mid-extraction"
)

LONG_MARKDOWN = """# Delivery notes

This is a deliberately long Markdown body used to exercise the preview and
scroll behaviour of the Files/Chat panels.

| column a | column b | column c | column d |
|---|---|---|---|
| value-0001 | value-0002 | a much longer value that should wrap or scroll | value-0004 |
| value-1001 | value-1002 | value-1003 | value-1004 |
| value-2001 | value-2002 | value-2003 | value-2004 |

```python
def very_long_function_name_that_should_not_clip(argument_one, argument_two, argument_three):
    return {"argument_one": argument_one, "argument_two": argument_two}
```

A very long unbroken path:
/tmp/lg021-fixtures/workspace/tasks/very/deep/nested/directory/with/a/really/long/file-name-that-goes-on-and-on-and-on-and-on-and-on-and-on.md

""" + "\n".join(
    f"Line {i:04d}: filler content for scroll and wrap behaviour checks." for i in range(1, 121)
)


_TASK_BODY_TMPL = """# Task

## 目标

{objective}

## 范围

{scope}
"""


def create_task(
    store: FileStore,
    coordinator: Coordinator,
    *,
    key: str,
    title: str,
    objective: str,
    phase: str = "intake",
    status: str = "todo",
    archived: bool = False,
) -> str:
    """Create a real Task entity at a chosen phase.

    The entity is written with the store's own ``create`` path (full static
    validation, real schema) so the Board reads genuine persisted phases.  A
    matching ``task.phase_changed`` event is appended (same shape the real
    coordinator emits) so notification projection sees a durable event too.
    """
    task_id = new_id("task")
    content: dict[str, Any] = {
        "title": title,
        "objective": objective,
        "acceptance_criteria": [],
        "status": status,
        "phase": phase,
        "requirements_revision": 1,
        "project_ref": None,
        "repository_ref": None,
        "workspace_ref": None,
        "agent_ref": "coordinator",
        "depends_on": [],
        "active_run": None,
        "deliverable_revision": 0,
        "queue": {
            "state": "not_queued",
            "order": None,
            "queued_at": None,
            "owner": None,
            "lease_expires_at": None,
        },
        "acceptance": {
            "status": "pending",
            "requirements_revision": None,
            "deliverable_revision": None,
            "evidence_refs": [],
            "decided_at": None,
            "decision_ref": None,
        },
        "budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
        "archived": archived,
    }
    store.create(
        "task",
        task_id,
        content,
        actor="coordinator",
        request_id=f"lg021-{key}",
        body=_TASK_BODY_TMPL.format(objective=objective, scope="fixture scope"),
    )
    if phase != "intake":
        store.append_event(
            task_id,
            {
                "type": "task.phase_changed",
                "actor": "coordinator",
                "task_ref": task_id,
                "run_ref": f"run_lg021_{key}",
                "payload": {"from": "intake", "to": phase, "reason": f"lg021 fixture {key}"},
            },
        )
    return task_id


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: seed_lg021_fixtures.py DATA_DIR WORKSPACE_DIR", file=sys.stderr)
        return 2
    data_dir = Path(sys.argv[1])
    workspace = Path(sys.argv[2])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "inputs").mkdir(exist_ok=True)
    (workspace / "candidates").mkdir(exist_ok=True)
    (workspace / "deliverables").mkdir(exist_ok=True)
    (workspace / "evidence").mkdir(exist_ok=True)

    store = FileStore(data_dir, workspace)
    coordinator = Coordinator(store, dispatcher=SingleSlotDispatcher(UnavailableExecutor()))

    out: dict[str, str] = {}
    out["long"] = create_task(
        store,
        coordinator,
        key="long",
        title=LONG_TITLE,
        objective=LONG_MARKDOWN,
        phase="awaiting_acceptance",
        status="in-progress",
    )
    out["failed"] = create_task(
        store,
        coordinator,
        key="failed",
        title="Failing task for notification targeting",
        objective="produces a durable failed phase event",
        phase="failed",
        status="in-progress",
    )
    out["recovery"] = create_task(
        store,
        coordinator,
        key="recovery",
        title="Recovery-required task",
        objective="awaiting user recovery decision",
        phase="recovery_required",
        status="in-progress",
    )
    out["queued"] = create_task(
        store,
        coordinator,
        key="queued",
        title="Queued task",
        objective="waiting for an execution slot",
        phase="queued",
        status="todo",
    )
    out["cancelled"] = create_task(
        store,
        coordinator,
        key="cancelled",
        title="Cancelled task kept in history",
        objective="history filter fixture",
        phase="cancelled",
        status="in-progress",
    )
    out["archived"] = create_task(
        store,
        coordinator,
        key="archived",
        title="Archived task (history only)",
        objective="archived filter fixture",
        phase="completed",
        status="done",
        archived=True,
    )

    # Extra durable failed event for one more notification (targets `failed`).
    store.append_event(
        out["failed"],
        {
            "type": "task.phase_changed",
            "actor": "coordinator",
            "task_ref": out["failed"],
            "run_ref": "run_lg021_failed",
            "payload": {"from": "executing", "to": "failed", "reason": "fixture failure #2"},
        },
    )

    # Workspace files for the Files view.
    (workspace / "inputs" / "notes.md").write_text(LONG_MARKDOWN, encoding="utf-8")
    long_name = "very-long-file-name-" + ("x" * 60) + "-tail.md"
    (workspace / "inputs" / long_name).write_text(
        "# long name\n\n" + "content\n" * 50, encoding="utf-8"
    )
    deep = workspace / "candidates" / "a" / "very" / "deeply" / "nested" / "directory" / "path"
    deep.mkdir(parents=True, exist_ok=True)
    (deep / "result-with-a-long-name-that-should-wrap-or-truncate.md").write_text(
        LONG_MARKDOWN, encoding="utf-8"
    )
    (workspace / "deliverables" / "run.log").write_text(
        "\n".join(
            f"2026-10-16T00:00:{i % 60:02d}Z INFO worker step {i:05d} "
            f"path=/tmp/lg021-fixtures/workspace/tasks/{i}/artifact.md"
            for i in range(1, 401)
        ),
        encoding="utf-8",
    )
    (workspace / "evidence" / "table.md").write_text(LONG_MARKDOWN, encoding="utf-8")

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
