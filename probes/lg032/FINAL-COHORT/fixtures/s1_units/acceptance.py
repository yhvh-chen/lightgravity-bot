#!/usr/bin/env python3
"""Objective machine gate for sample s1_units. Hidden from the model.

Usage: python3 acceptance.py --workspace <dir>

Checks (6):
  labels.slugify        - lowercase, non-alnum runs -> single '-', trim '-'
  numeric.clamp         - clamp into [lo, hi]
  numeric.in_range      - True iff lo <= v <= hi
  no_write_verify       - the read-only verify node wrote nothing into the repo
Prints one JSON report to stdout.
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

    def _eq(actual, expected) -> None:
        if actual != expected:
            raise AssertionError(f"expected {expected!r}, got {actual!r}")

    labels = None
    try:
        labels = importlib.import_module("src.labels")
    except Exception as exc:  # noqa: BLE001
        lbl_err = f"{type(exc).__name__}: {exc}"
    else:
        lbl_err = ""

    numeric = None
    try:
        numeric = importlib.import_module("src.numeric")
    except Exception as exc:  # noqa: BLE001
        num_err = f"{type(exc).__name__}: {exc}"
    else:
        num_err = ""

    if labels is None:
        check("labels.slugify", lambda: (_ for _ in ()).throw(AssertionError(lbl_err)))
    else:
        check("labels.slugify.basic", lambda: _eq(labels.slugify("Hello World"), "hello-world"))
        check("labels.slugify.runs", lambda: _eq(labels.slugify("  A__B--C  "), "a-b-c"))

    if numeric is None:
        check("numeric.clamp", lambda: (_ for _ in ()).throw(AssertionError(num_err)))
        check("numeric.in_range", lambda: (_ for _ in ()).throw(AssertionError(num_err)))
    else:
        check("numeric.clamp", lambda: (
            _eq(numeric.clamp(5, 0, 3), 3),
            _eq(numeric.clamp(-1, 0, 3), 0),
            _eq(numeric.clamp(2, 0, 3), 2),
        ))
        check("numeric.in_range", lambda: (
            _eq(numeric.in_range(2, 0, 3), True),
            _eq(numeric.in_range(3, 0, 3), True),
            _eq(numeric.in_range(4, 0, 3), False),
        ))

    # The read-only verify node must not have created new source files.
    extra = sorted(
        str(p.relative_to(ws))
        for p in (ws / "src").glob("*.py")
        if p.name not in {"__init__.py", "labels.py", "numeric.py"}
    )
    check("no_write_from_verify", lambda: _eq(extra, []))

    passed = sum(1 for c in checks if c["passed"])
    print(json.dumps({"checks": checks, "passed": passed, "total": len(checks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
