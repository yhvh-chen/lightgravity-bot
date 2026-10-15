#!/usr/bin/env python3
"""LG-032 phase A independent probe — true multi-process atomic claim race.

Independent QA probe. Spawns N real OS processes that each construct their own
``CollaborationService`` over the SAME real ``FileStore`` (real ``flock``,
atomic replace) and race to claim ONE ready Subtask at a synchronized barrier.
The frozen guarantee (LG-028 §2.6) is: exactly one process is granted; every
other gets a definite refusal (``held_by_other``), and the persisted fence
advanced exactly once.

Provider-substitute: no SDK / no network / no model. Offline mechanism evidence.

Expects a pre-created run/subtask under ``--work`` (see ``--setup``), or creates
it itself when ``--setup`` is passed.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "collaboration"))


def _worker(data_dir: str, ws: str, run_id: str, subtask: str, wid: str, barrier, out) -> None:
    # Import inside the child so the parent's cwd/sys.path are not required.
    sys.path.insert(0, str(REPO / "backend"))
    sys.path.insert(0, str(REPO / "tests" / "collaboration"))
    from lightgravity.collaboration import ClaimPolicy, ClaimRequest, CollaborationService
    from lightgravity.store import FileStore

    store = FileStore(Path(data_dir), Path(ws))
    service = CollaborationService(
        store, policy=ClaimPolicy(enabled=True, lease_seconds=300)
    )
    barrier.wait()
    try:
        decision = service.request_claim(
            run_id, ClaimRequest(subtask_id=subtask, owner=wid, request_id=f"req-{wid}")
        )
        out.put(
            {
                "worker": wid,
                "granted": decision.granted,
                "reason": decision.reason,
                "fence": decision.fence,
            }
        )
    except Exception as exc:  # noqa: BLE001 - surface any error honestly
        out.put({"worker": wid, "error": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--processes", type=int, default=6)
    args = ap.parse_args()
    work = Path(args.work)
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite existing out: {out}", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)

    # Build the fixture in the parent process (real FileStore).
    sys.path.insert(0, str(REPO / "backend"))
    sys.path.insert(0, str(REPO / "tests" / "collaboration"))
    from collab_helpers import create_run, create_subtask, create_task, link_subtasks, set_switches
    from lightgravity.store import FileStore

    data_dir = work / "data"
    ws = work / "ws"
    store = FileStore(data_dir, ws)
    set_switches(store, enabled=True, lease_seconds=300)
    task = create_task(store)
    run = create_run(store, task)
    sub = create_subtask(store, run, key="race", capability="implementation", write=False)
    link_subtasks(store, run, [sub])

    n = args.processes
    barrier = mp.Barrier(n)
    q: mp.Queue = mp.Queue()
    procs = [
        mp.Process(
            target=_worker,
            args=(str(data_dir), str(ws), run, sub, f"worker-{i}", barrier, q),
        )
        for i in range(n)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
    results = [q.get(timeout=5) for _ in range(n)]

    entity = store.read("subtask", sub).entity
    granted = [r for r in results if r.get("granted")]
    result = {
        "processes": n,
        "results": sorted(results, key=lambda r: r.get("worker", "")),
        "granted_count": len(granted),
        "final_owner": entity.get("owner"),
        "final_fence": entity.get("fence"),
        "final_state": entity.get("state"),
        "provider_substitute": "no SDK, no network, no model",
    }
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    # Exit non-zero if the invariant is violated.
    if len(granted) != 1 or entity.get("fence") != 1:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
