#!/usr/bin/env python3
"""Objective acceptance for T1 (independent modification).

Hidden from the model. Usage:
    python3 acceptance.py --workspace <dir>
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
        slugs = importlib.import_module("src.slugs")
    except Exception as exc:  # noqa: BLE001
        slugs = None
        slug_import_error = f"{type(exc).__name__}: {exc}"
    else:
        slug_import_error = ""

    def _slug_import():
        if slugs is None:
            raise RuntimeError(f"import src.slugs failed: {slug_import_error}")

    if slugs is None:
        for nm in ("slug.case", "slug.multi", "slug.trim"):
            checks.append({"name": nm, "passed": False, "detail": f"import src.slugs failed: {slug_import_error}"})
    else:
        check("slug.case", lambda: _eq(slugs.slugify("Hello World!"), "hello-world"))
        check("slug.multi", lambda: _eq(slugs.slugify("A--B"), "a-b"))
        check("slug.trim", lambda: _eq(slugs.slugify("  Foo__Bar  "), "foo-bar"))

    try:
        ranges = importlib.import_module("src.ranges")
    except Exception as exc:  # noqa: BLE001
        ranges = None
        range_import_error = f"{type(exc).__name__}: {exc}"
    else:
        range_import_error = ""

    if ranges is None:
        for nm in ("clamp.low", "clamp.high", "in_range"):
            checks.append({"name": nm, "passed": False, "detail": f"import src.ranges failed: {range_import_error}"})
    else:
        check("clamp.low", lambda: _eq(ranges.clamp(-1, 0, 2), 0))
        check("clamp.high", lambda: _eq(ranges.clamp(3, 0, 2), 2))
        check("in_range", lambda: _both(ranges.in_range(5, 1, 10) is True, ranges.in_range(0, 1, 10) is False))

    passed = sum(1 for c in checks if c["passed"])
    print(json.dumps({"checks": checks, "passed": passed, "total": len(checks)}))
    return 0


def _eq(actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def _both(a: bool, b: bool) -> None:
    if not (a and b):
        raise AssertionError(f"expected both true; got {a}, {b}")


if __name__ == "__main__":
    raise SystemExit(main())
