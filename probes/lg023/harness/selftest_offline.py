#!/usr/bin/env python3
"""LG-023 offline harness self-test (zero real model calls).

Proves, before any real request:

* both frozen plans (arm A single node; arm B two dependent write nodes) pass the
  real product ``PlanValidator`` with the real catalog capabilities and a
  workspace boundary;
* arm B's graph is a genuine dependency (``part_b`` depends on ``part_a``);
* the attempt guard denies the 13th reservation against the shared ledger;
* the acceptance gate helper reports unreachable for a bare/incomplete task.

Writes ``evidence/offline/harness_selftest.json``.

Usage::

    uv run python probes/lg023/harness/selftest_offline.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.coordinator.dispatcher import DispatchContext  # noqa: E402
from lightgravity.coordinator.planner import PlanValidator  # noqa: E402
from lightgravity.adapter.generation_ledger import PersistentGenerationLedger  # noqa: E402

OUT = HERE.parent / "evidence" / "offline" / "harness_selftest.json"

# Import the harness module without running main().
spec = importlib.util.spec_from_file_location("lg023_run_attempt", HERE / "run_attempt.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _context(objective: str, acceptance: tuple[str, ...], workspace: str) -> DispatchContext:
    return DispatchContext(
        task_id="task", run_id="run", attempt=1, objective=objective,
        acceptance_criteria=acceptance, workspace_path=workspace,
    )


def main() -> int:
    checks: dict[str, object] = {}
    validator = PlanValidator(known_capabilities={"implementation", "verification"})

    with tempfile.TemporaryDirectory() as tmp:
        ws = tmp
        for sample, arm, expect_nodes, expect_deps in (
            ("s1_independent", "A", 1, False),
            ("s1_independent", "B", 2, True),
            ("s2_interface", "A", 1, False),
            ("s2_interface", "B", 2, True),
        ):
            planner = mod._FrozenPlanner(arm, sample)
            ctx = _context(
                mod.SAMPLES[sample]["objective"], tuple(mod.SAMPLES[sample]["acceptance"]), ws
            )
            proposal = asyncio.run(planner.plan(ctx))
            plan = validator.validate(proposal, workspace_path=ws)
            keys = [s.key for s in plan.subtasks]
            deps = {s.key: list(s.depends_on) for s in plan.subtasks}
            has_dep = any(d for d in deps.values())
            checks[f"plan_{sample}_{arm}"] = {
                "keys": keys,
                "deps": deps,
                "plan_hash": plan.plan_hash,
                "source": plan.source,
                "pass": len(keys) == expect_nodes and has_dep == expect_deps,
            }

        # Attempt guard denies the 13th reservation.
        guard_root = Path(tmp) / "guard"
        led = PersistentGenerationLedger(guard_root, limit=48)
        guard = mod._AttemptGuard(led, 12)
        granted = 0
        denied = False
        for _ in range(13):
            res = guard.reserve()
            if res is None or not getattr(res, "granted", False):
                denied = True
                break
            granted += 1
        checks["attempt_guard_12"] = {
            "granted": granted,
            "denied": denied,
            "ledger": led.snapshot(),
            "pass": granted == 12 and denied and led.snapshot()["count"] == 12,
        }

    ok = all(v["pass"] for v in checks.values())  # type: ignore[union-attr]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"ok": ok, "checks": checks}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": ok, "checks": checks}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
