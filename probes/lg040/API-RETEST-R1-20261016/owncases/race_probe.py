"""LG-040 API-RETEST — focused claim-race probe (classification evidence).

Runs the SAME semantics as
``tests/collaboration/test_claims.py::test_two_owner_race_on_real_store_only_one_wins``
against the real ``FileStore`` + real ``CollaborationService`` for N iterations,
and records the outcome distribution.  Purpose: determine whether the product
claim path has a genuine concurrency defect (double-grant / zero-grant under
contention) or whether the full-suite single failure was a timing/assumption
flake.

Read-only w.r.t. the product.  All data under a temp dir.  No network/model.

Run:  PYTHONPATH=<worktree>/backend python race_probe.py [iterations]
"""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "collaboration"))

from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
)
from lightgravity.store import FileStore  # noqa: E402

from collab_helpers import (  # noqa: E402
    FakeClock,
    create_run,
    create_subtask,
    create_task,
    link_subtasks,
    set_switches,
)


def one_iteration(iteration: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"lg040-race-{iteration}-"))
    data_dir = tmp / "data"
    workspace_root = tmp / "ws"
    workspace_root.mkdir(parents=True, exist_ok=True)
    clock = FakeClock()

    setup = FileStore(data_dir, workspace_root)
    task_id = create_task(setup)
    run_id = create_run(setup, task_id)
    sub = create_subtask(setup, run_id, key="a")
    link_subtasks(setup, run_id, [sub])
    set_switches(setup, enabled=True, lease_seconds=60)

    barrier = threading.Barrier(2)
    results: list[object] = []
    errors: list[BaseException] = []

    from lightgravity.collaboration import ClaimRequest

    def worker(owner: str) -> None:
        store = FileStore(data_dir, workspace_root)
        service = CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=60), clock=clock
        )
        barrier.wait()
        try:
            results.append(
                service.request_claim(
                    run_id,
                    ClaimRequest(
                        subtask_id=sub,
                        owner=owner,
                        request_id=f"req-{owner}",
                    ),
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("worker-a",)),
        threading.Thread(target=worker, args=("worker-b",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    granted = [d for d in results if getattr(d, "granted", False)]
    refused = [d for d in results if not getattr(d, "granted", True)]
    entity = setup.read("subtask", sub).entity
    outcome = {
        "iteration": iteration,
        "errors": [type(e).__name__ for e in errors],
        "results": len(results),
        "granted": len(granted),
        "refused": len(refused),
        "refuse_reasons": [getattr(d, "reason", None) for d in refused],
        "final_owner": entity.get("owner"),
        "final_fence": entity.get("fence"),
        "pass": (
            errors == []
            and len(results) == 2
            and len(granted) == 1
            and len(refused) == 1
            and getattr(refused[0], "reason", None) == "held_by_other"
            and entity.get("fence") == 1
        ),
    }
    return outcome


def main() -> int:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    label = sys.argv[2] if len(sys.argv) > 2 else "fix"
    outcomes = [one_iteration(i) for i in range(iterations)]
    fails = [o for o in outcomes if not o["pass"]]
    double = [o for o in outcomes if o["granted"] != 1]
    print(f"iterations={iterations} pass={iterations - len(fails)} fail={len(fails)}")
    print(f"double_grant_or_zero={len(double)}")
    for o in fails[:10]:
        print("FAIL:", o)
    import json
    from collections import Counter

    reasons = Counter(tuple(o["refuse_reasons"]) for o in outcomes)
    print("reason_distribution:", dict(reasons))

    out = Path(__file__).resolve().parents[1] / "raw" / f"race_probe_results_{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"iterations": iterations, "failures": fails, "all": outcomes}, indent=2) + "\n")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
