#!/usr/bin/env python3
"""LG-032 phase A independent probe — program-side node pre-selection guard.

Independent QA probe. Exercises the REAL product method
``GraphDispatcher._claim_for_worker`` (the callback the worker-facing
``discover_and_request_claim`` tool calls) against a real FileStore with TWO
simultaneously-ready, same-capability Subtasks. It shows that the program
refuses a claim for any node other than the one it scheduled for that worker,
even though the node is genuinely discoverable.

Provider-substitute: no SDK / no network / no model. Offline mechanism evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from types import SimpleNamespace
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "collaboration"))

from lightgravity.adapter import (  # noqa: E402
    AdapterCapabilities,
    CancelResult,
    ExecutorResult,
    SessionRef,
    adapter_capabilities,
)
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import DispatchContext, GraphDispatcher  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402

from collab_helpers import (  # noqa: E402
    create_run,
    create_subtask,
    create_task,
    link_subtasks,
    set_switches,
)


class _NullExecutor:
    name = "null"
    version = "0"
    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()
    async def execute(self, request, emit):  # pragma: no cover - never called
        raise AssertionError("executor must not run in this probe")
    async def cancel(self, ref):  # pragma: no cover
        return CancelResult(confirmed=True, state="cancelled", reason="probe")
    async def close(self, ref) -> None:  # pragma: no cover
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    work = Path(args.work)
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite existing out: {out}", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)

    store = FileStore(work / "data", work / "ws")
    set_switches(store, enabled=True, lease_seconds=300)
    task = create_task(store)
    run = create_run(store, task)
    a = create_subtask(store, run, key="a", capability="implementation", write=False)
    b = create_subtask(store, run, key="b", capability="implementation", write=False)
    link_subtasks(store, run, [a, b])

    collab = CollaborationService(
        store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
    )
    registry = ExecutionGrantRegistry()
    dispatcher = GraphDispatcher(
        store,
        _NullExecutor(),
        collaboration=collab,
        grant_registry=registry,
        autonomous_claim=True,
    )
    # The worker is executing node A (program-scheduled). Build the minimal node
    # + context the real handler receives.
    node = SimpleNamespace(subtask_id=a, key="a", member_id="member-a", spec=SimpleNamespace(capability="implementation"))
    context = SimpleNamespace(run_id=run, task_id=task, budget={"max_collab_requests": 4})

    # The program's own discovery projection (what a worker could see) lists BOTH
    # nodes right now -- the projection is genuinely multi-candidate.
    view = collab.discover(run, "member-a")
    discoverable = [c.subtask_id for c in view.candidates]

    own = dispatcher._claim_for_worker(node, context, a, "req-own")
    other_authorized = dispatcher._claim_for_worker(node, context, b, "req-other")

    result = {
        "discoverable_at_execution": discoverable,
        "scheduled_node": a,
        "other_discoverable_node": b,
        "claim_scheduled": own,
        "claim_other_discoverable": other_authorized,
        "note": (
            "The node the worker was NOT scheduled for is discoverable and "
            "authorized by the projection, yet the program refuses its claim."
        ),
        "provider_substitute": "no SDK, no network, no model",
    }
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
