"""LG-022 reverify R2 — offline independent proof of the PERSISTENT generation ledger.

Proves, with NO real DeepSeek request and NO product code modification:

  C1  reserve() persists BEFORE forwarding (append-only history + atomic snapshot).
  C2  limit reached => reserve() denied (granted=False), no forward.
  C3  one ledger shared across two GenerationCounter instances (worker/reviewer
      role proxies) does not double-grant past the limit.
  C4  a FRESH interpreter (real subprocess) reading the SAME ledger sees the same
      count -- i.e. restart does NOT reset to 0.
  C5  concurrent reservation from many threads/processes never exceeds the limit
      (exactly `limit` grants, count == limit).
  C6  a CORRUPT ledger is never treated as 0: snapshot reports corrupt/unknown and
      reserve() is refused (fail-closed).

Run:  .venv/bin/python qa/lg022-r2/harness/ledger_proof.py <workdir> <out_json>
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter.generation_ledger import (  # noqa: E402
    PersistentGenerationLedger,
)
from lightgravity.adapter.proxy import GenerationCounter  # noqa: E402

RESULTS: dict[str, object] = {}


def _worker_proc(root: str, limit: int, grants: int) -> None:
    """Child process body: reserve grants times, report how many succeeded."""
    led = PersistentGenerationLedger(root, limit=limit)
    ok = 0
    for _ in range(grants):
        if led.reserve().granted:
            ok += 1
    sys.stdout.write(str(ok))


def _fresh_reader(root: str) -> None:
    """Child process body: read the ledger count only."""
    led = PersistentGenerationLedger(root, limit=None)
    try:
        sys.stdout.write(json.dumps({"count": led.count()}))
    except Exception as exc:  # noqa: BLE001
        sys.stdout.write(json.dumps({"error": type(exc).__name__}))


def child_count_expr(root: str) -> str:
    return json.dumps({"count": PersistentGenerationLedger(root, limit=None).count()})


def main() -> int:
    work = Path(sys.argv[1])
    out = Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- C1/C2/C3
    root1 = work / "c1"
    led1 = PersistentGenerationLedger(root1, limit=3)
    c1 = {"grants": [], "history_exists_after_first": None}
    r = led1.reserve()
    c1["grants"].append(r.granted)
    c1["history_exists_after_first"] = (root1 / "generation" / "generation.jsonl").exists()
    c1["count_after_first"] = led1.count()
    # C2: exhaust
    for _ in range(2):
        c1["grants"].append(led1.reserve().granted)
    denied = led1.reserve()
    c1["denied_at_limit"] = {"granted": denied.granted, "reason": denied.reason}
    c1["count_final"] = led1.count()
    RESULTS["C1_reserve_before_forward"] = c1

    # C3: two counters (worker + reviewer role) on the same ledger share the cap
    root3 = work / "c3"
    led3 = PersistentGenerationLedger(root3, limit=4)
    counter_worker = GenerationCounter(4, ledger=led3)
    led3b = PersistentGenerationLedger(root3, limit=4)
    counter_reviewer = GenerationCounter(4, ledger=led3b)
    seq = []
    for i in range(6):
        c = counter_worker if i % 2 == 0 else counter_reviewer
        seq.append(c.reserve())
    RESULTS["C3_shared_across_roles"] = {
        "sequence": seq,
        "grants": sum(1 for x in seq if x),
        "worker_count": counter_worker.count,
        "reviewer_count": counter_reviewer.count,
        "expect_grants": 4,
        "ok": sum(1 for x in seq if x) == 4 and counter_worker.count == counter_reviewer.count == 4,
    }

    # ------------------------------------------------------------------- C4
    # Real restart: reserve 2 in THIS process, then a fresh subprocess reads it.
    root4 = work / "c4"
    led4 = PersistentGenerationLedger(root4, limit=10)
    led4.reserve()
    led4.reserve()
    before = led4.count()
    code4 = (
        "import sys,json;sys.path.insert(0,%r);"
        "from lightgravity.adapter.generation_ledger import PersistentGenerationLedger as L;"
        "print(json.dumps({'count': L(%r, limit=None).count()}))"
        % (str(REPO / "backend"), str(root4))
    )
    proc = subprocess.run([sys.executable, "-c", code4], capture_output=True, text=True, timeout=60)
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    fresh = json.loads(lines[-1]) if proc.returncode == 0 and lines else {"error": (proc.stderr or "no output")[-200:]}
    RESULTS["C4_restart_persistent"] = {
        "count_before_restart": before,
        "fresh_interpreter_count": fresh.get("count"),
        "persisted_across_restart": fresh.get("count") == before and before == 2,
        "child_returncode": proc.returncode,
    }
    # also: a fresh ledger object in this process reads the same
    RESULTS["C4_restart_persistent"]["reopen_same_process_count"] = PersistentGenerationLedger(root4, limit=10).count()

    # ------------------------------------------------------------------- C5
    # Concurrency: 6 subprocesses each try 5 grants against limit=10.
    root5 = work / "c5"
    PersistentGenerationLedger(root5, limit=10)  # initialize dir
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_worker_proc, args=(str(root5), 10, 5)) for _ in range(6)]
    # capture child stdout via a pipe is awkward with spawn; use files instead
    RESULTS.pop("C5_concurrency", None)
    # simpler deterministic approach: multiprocessing via subprocess with shared file
    scripts = []
    for i in range(6):
        code = (
            "import sys;sys.path.insert(0,%r);"
            "from lightgravity.adapter.generation_ledger import PersistentGenerationLedger as L;"
            "led=L(%r,limit=10);print(sum(1 for _ in range(5) if led.reserve().granted))"
            % (str(REPO / "backend"), str(root5))
        )
        scripts.append(code)
    import concurrent.futures as cf
    def run_one(code: str) -> int:
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        try:
            return int(p.stdout.strip().splitlines()[-1])
        except Exception:
            return -1
    # launch all at once
    ps = [subprocess.Popen([sys.executable, "-c", c], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for c in scripts]
    grants_total = 0
    child_counts = []
    for p in ps:
        stdout, _ = p.communicate(timeout=60)
        try:
            grants_total += int(stdout.strip().splitlines()[-1])
        except Exception:
            grants_total += -1
    final5 = PersistentGenerationLedger(root5, limit=10)
    RESULTS["C5_concurrency"] = {
        "children": 6, "each_tries": 5, "limit": 10,
        "total_granted": grants_total,
        "ledger_count": final5.count(),
        "ok": grants_total == 10 and final5.count() == 10,
    }

    # ------------------------------------------------------------------- C6
    # Corrupt history: a line that is not valid JSON must NOT be read as 0.
    root6 = work / "c6"
    led6 = PersistentGenerationLedger(root6, limit=5)
    led6.reserve()
    history = root6 / "generation" / "generation.jsonl"
    with history.open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
    snap = led6.snapshot()
    denied6 = led6.reserve()
    counter_corrupt = GenerationCounter(5, ledger=led6)
    RESULTS["C6_corrupt_fail_closed"] = {
        "snapshot": snap,
        "reserve_granted": denied6.granted,
        "reserve_reason": denied6.reason,
        "reserve_corrupt_flag": denied6.corrupt,
        "counter_count": counter_corrupt.count,
        "not_treated_as_zero": snap.get("count") is None and counter_corrupt.count != 0 and not denied6.granted,
    }
    # corrupt snapshot file too
    root6b = work / "c6b"
    led6b = PersistentGenerationLedger(root6b, limit=5)
    led6b.reserve()
    (root6b / "generation" / "generation.count.json").write_text("{bad", encoding="utf-8")
    snap6b = led6b.snapshot()
    RESULTS["C6b_corrupt_snapshot"] = {
        "snapshot": snap6b,
        "reserve_granted": led6b.reserve().granted,
        "not_treated_as_zero": snap6b.get("count") is None and not led6b.reserve().granted,
    }

    # ------------------------------------------------------------------ verdict
    ok_flags = {
        "C1": c1["grants"] == [True, True, True] and c1["history_exists_after_first"] and c1["count_final"] == 3,
        "C2": c1["denied_at_limit"]["granted"] is False,
        "C3": RESULTS["C3_shared_across_roles"]["ok"],  # type: ignore[index]
        "C4": RESULTS["C4_restart_persistent"]["persisted_across_restart"],  # type: ignore[index]
        "C5": RESULTS["C5_concurrency"]["ok"],  # type: ignore[index]
        "C6": RESULTS["C6_corrupt_fail_closed"]["not_treated_as_zero"],  # type: ignore[index]
    }
    RESULTS["verdict"] = {
        "checks": ok_flags,
        "all_pass": all(ok_flags.values()),
        "real_model_calls": 0,
        "evidence_kind": "offline-persistent-ledger-proof",
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(RESULTS, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(RESULTS["verdict"], indent=2))
    return 0 if RESULTS["verdict"]["all_pass"] else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
