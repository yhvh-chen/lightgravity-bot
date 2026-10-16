"""LG-040 RACE-TEST-FIX — contention probe for the two-owner claim race.

Runs the exact semantics of
``tests/collaboration/test_claims.py::test_two_owner_race_on_real_store_only_one_wins``
against the real ``FileStore`` + real ``CollaborationService`` for N iterations
and records the loser's refusal-reason distribution.

Purpose: show that under real contention the loser is legitimately refused with
EITHER ``held_by_other`` (discovery snapshot taken before the winner's commit)
OR ``not_discoverable`` (snapshot taken after the winner's commit, so the now
``running`` subtask is excluded as not claimable).  Both are fail-closed,
single-winner refusals; only the test's original exact-reason assertion was
brittle.

Read-only w.r.t. the product.  All data under a temp dir.  No network/model.

Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<worktree>/backend python race_reason_probe.py [iterations]
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "collaboration"))

from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    ClaimRequest,
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

VALID_FAIL_CLOSED = {"held_by_other", "not_discoverable"}


def one_iteration(iteration: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"lg040-racefix-{iteration}-"))
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
                    ClaimRequest(subtask_id=sub, owner=owner, request_id=f"req-{owner}"),
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
    reason = getattr(refused[0], "reason", None) if len(refused) == 1 else None
    return {
        "iteration": iteration,
        "errors": [type(e).__name__ for e in errors],
        "results": len(results),
        "granted": len(granted),
        "refused": len(refused),
        "refuse_reason": reason,
        "final_owner": entity.get("owner"),
        "final_fence": entity.get("fence"),
        # Strong invariants preserved regardless of which fail-closed reason won.
        "strong_invariants_ok": (
            errors == []
            and len(results) == 2
            and len(granted) == 1
            and len(refused) == 1
            and reason in VALID_FAIL_CLOSED
            and entity.get("owner") == getattr(granted[0], "owner", None)
            and entity.get("fence") == 1
        ),
        # The brittle assumption the old test made.
        "old_exact_reason_ok": reason == "held_by_other",
    }


def main() -> int:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    label = sys.argv[2] if len(sys.argv) > 2 else "fix"
    outcomes = [one_iteration(i) for i in range(iterations)]

    strong_fail = [o for o in outcomes if not o["strong_invariants_ok"]]
    old_fail = [o for o in outcomes if not o["old_exact_reason_ok"]]
    double = [o for o in outcomes if o["granted"] != 1]
    reason_dist = Counter(o["refuse_reason"] for o in outcomes)

    print(f"iterations={iterations}")
    print(f"strong_invariant_fail={len(strong_fail)} (must be 0)")
    print(f"old_exact_reason_fail={len(old_fail)} (expected >0 sometimes)")
    print(f"double_or_zero_grant={len(double)} (must be 0)")
    print(f"loser_reason_distribution={dict(reason_dist)}")
    for o in old_fail[:5]:
        print("OLD-ASSERTION-FLAKE:", o)

    out = Path(__file__).resolve().parents[1] / "raw" / f"race_reason_probe_{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "iterations": iterations,
                "strong_invariant_failures": strong_fail,
                "old_exact_reason_failures": old_fail,
                "loser_reason_distribution": dict(reason_dist),
                "all": outcomes,
            },
            indent=2,
        )
        + "\n"
    )
    return 1 if strong_fail else 0


if __name__ == "__main__":
    sys.exit(main())
