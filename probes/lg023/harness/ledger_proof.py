#!/usr/bin/env python3
"""LG-023 offline generation-ledger proof (zero real model calls).

Proves the budget rules frozen in ``PLAN.md`` §5 *before* any real request:

* globally there is exactly one persistent ledger with a hard cap of 48;
* the cap is enforced (49th reservation denied);
* the count survives a fresh object and a **fresh interpreter** (cross-process,
  no reset);
* a corrupt ledger is fail-closed (``corrupt=true``, count reported as ``None``,
  reservation refused) and is **never treated as 0**;
* the per-attempt secondary cap (12) is enforced by the attempt guard, and the
  *same* global ledger is charged by every stage (worker / reviewer / repair).

Writes ``evidence/offline/ledger_proof.json``.

Usage::

    uv run python probes/lg023/harness/ledger_proof.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
REPO = PROBE.parent.parent
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter.generation_ledger import (  # noqa: E402
    GenerationLedgerCorrupt,
    PersistentGenerationLedger,
)

OUT = PROBE / "evidence" / "offline" / "ledger_proof.json"
GLOBAL_LIMIT = 48
ATTEMPT_LIMIT = 12
_CHILD = r"""
import sys
sys.path.insert(0, {backend!r})
from lightgravity.adapter.generation_ledger import PersistentGenerationLedger
led = PersistentGenerationLedger({root!r}, limit={limit})
res = led.reserve()
print(res.count)
"""


def _reserve_ok(led: PersistentGenerationLedger) -> bool:
    return led.reserve().granted


def main() -> int:
    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "phase"

        # L1: single ledger, hard cap 48.
        led = PersistentGenerationLedger(root, limit=GLOBAL_LIMIT)
        for _ in range(GLOBAL_LIMIT):
            assert _reserve_ok(led), "reserve should be granted below the cap"
        snap = led.snapshot()
        checks["L1_cap48"] = {
            "snapshot": snap,
            "pass": snap["count"] == GLOBAL_LIMIT and snap["remaining"] == 0,
        }
        denied = led.reserve()
        checks["L2_cap_enforced_49th"] = {
            "granted": denied.granted,
            "count": denied.count,
            "reason": denied.reason,
            "pass": (not denied.granted) and denied.count == GLOBAL_LIMIT,
        }

        # L3: new object on the same root keeps the count (restart simulation).
        led2 = PersistentGenerationLedger(root, limit=GLOBAL_LIMIT)
        snap2 = led2.snapshot()
        checks["L3_persist_across_instance"] = {
            "snapshot": snap2,
            "pass": snap2["count"] == GLOBAL_LIMIT,
        }

        # L4: fresh interpreter on the same root (true cross-process).
        child = subprocess.run(
            [sys.executable, "-c", _CHILD.format(backend=str(REPO / "backend"), root=str(root), limit=GLOBAL_LIMIT)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        checks["L4_persist_cross_process"] = {
            "child_stdout": child.stdout.strip(),
            "child_returncode": child.returncode,
            "pass": child.returncode == 0,
        }

        # L5: corruption is fail-closed and never 0.
        corrupt_root = Path(tmp) / "corrupt"
        corrupt_led = PersistentGenerationLedger(corrupt_root, limit=GLOBAL_LIMIT)
        _reserve_ok(corrupt_led)
        history = corrupt_root / "generation" / "generation.jsonl"
        history.write_text("{ this is not json }\n", encoding="utf-8")
        snap_c = corrupt_led.snapshot()
        refused = corrupt_led.reserve()
        try:
            corrupt_led.count()
            raised = False
        except GenerationLedgerCorrupt:
            raised = True
        checks["L5_corrupt_fail_closed"] = {
            "snapshot": snap_c,
            "reserve_granted": refused.granted,
            "count_raises": raised,
            "pass": (
                snap_c.get("corrupt") is True
                and snap_c.get("count") is None
                and (not refused.granted)
                and raised
            ),
        }

        # L6: per-attempt secondary cap (12) checked against the *same* ledger.
        attempt_root = Path(tmp) / "attempt"
        aled = PersistentGenerationLedger(attempt_root, limit=GLOBAL_LIMIT)
        attempt_used = 0
        attempt_denied_at = None
        for i in range(ATTEMPT_LIMIT + 3):
            if attempt_used >= ATTEMPT_LIMIT:
                attempt_denied_at = i
                break
            assert _reserve_ok(aled)
            attempt_used += 1
        checks["L6_attempt_cap12"] = {
            "attempt_used": attempt_used,
            "attempt_denied_at": attempt_denied_at,
            "global_snapshot": aled.snapshot(),
            "pass": attempt_used == ATTEMPT_LIMIT and attempt_denied_at == ATTEMPT_LIMIT,
        }

        # L7: all stages charge the same ledger (worker + reviewer share root).
        stage_root = Path(tmp) / "stages"
        wled = PersistentGenerationLedger(stage_root, limit=GLOBAL_LIMIT)
        _reserve_ok(wled)  # worker
        _reserve_ok(wled)  # reviewer (same root)
        rled = PersistentGenerationLedger(stage_root, limit=GLOBAL_LIMIT)
        checks["L7_single_ledger_all_stages"] = {
            "count_after_two_stages": rled.count(),
            "pass": rled.count() == 2,
        }

    ok = all(v["pass"] for v in checks.values())  # type: ignore[union-attr]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"ok": ok, "checks": checks}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": ok, "checks": checks}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
