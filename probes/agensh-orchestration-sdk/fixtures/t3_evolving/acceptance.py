#!/usr/bin/env python3
"""Objective acceptance for T3 (evolving requirements).

Hidden from the model. Usage:
    python3 acceptance.py --workspace <dir> --stage 1|2
Stage 1 = original requirements (5 checks); stage 2 = original + new (9 checks).
Prints a JSON report to stdout.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--stage", type=int, choices=(1, 2), default=2)
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    sys.path.insert(0, str(ws))

    checks: list[dict[str, object]] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            checks.append({"name": name, "passed": True, "detail": ""})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": name, "passed": False, "detail": f"{type(exc).__name__}: {exc}"})

    try:
        stats = importlib.import_module("src.stats")
        err = ""
    except Exception as exc:  # noqa: BLE001
        stats = None
        err = f"{type(exc).__name__}: {exc}"

    stage1 = [
        ("mean.basic", lambda s: _eq(s.mean([1, 2, 3, 4]), 2.5)),
        ("mean.empty", lambda s: _raises_value_error(lambda: s.mean([]))),
        ("median.odd", lambda s: _eq(s.median([3, 1, 2]), 2)),
        ("median.even", lambda s: _eq(s.median([1, 2, 3, 4]), 2.5)),
        ("median.empty", lambda s: _raises_value_error(lambda: s.median([]))),
    ]
    stage2_new = [
        ("mode.basic", lambda s: _eq(s.mode([1, 1, 2, 3]), 1)),
        ("mode.tie.min", lambda s: _eq(s.mode([2, 2, 1, 1]), 1)),
        ("stdev.basic", lambda s: _eq(round(s.stdev([2, 4, 4, 4, 5, 5, 7, 9]), 4), 2.0)),
        ("stdev.empty", lambda s: _raises_value_error(lambda: s.stdev([]))),
    ]

    plan = stage1 + (stage2_new if args.stage == 2 else [])
    if stats is None:
        for nm, _fn in plan:
            checks.append({"name": nm, "passed": False, "detail": f"import src.stats failed: {err}"})
    else:
        for nm, fn in plan:
            check(nm, lambda fn=fn, s=stats: fn(s))

    passed = sum(1 for c in checks if c["passed"])
    print(json.dumps({"checks": checks, "passed": passed, "total": len(checks)}))
    return 0


def _eq(actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def _raises_value_error(fn) -> None:
    try:
        fn()
    except ValueError:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"expected ValueError, got {type(exc).__name__}: {exc}") from exc
    raise AssertionError("expected ValueError, nothing raised")


if __name__ == "__main__":
    raise SystemExit(main())
