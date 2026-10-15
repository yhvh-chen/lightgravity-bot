#!/usr/bin/env python3
"""Objective acceptance for T2 (cross-module interface dependency).

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

    def _import(name: str):
        return importlib.import_module(name)

    rect = {"kind": "rect", "width": 3, "height": 4}
    circle = {"kind": "circle", "radius": 2}

    try:
        geometry = _import("src.geometry")
        geo_err = ""
    except Exception as exc:  # noqa: BLE001
        geometry = None
        geo_err = f"{type(exc).__name__}: {exc}"

    if geometry is None:
        for nm in ("geo.rect.area", "geo.circle.area", "geo.rect.perimeter", "geo.bad.kind"):
            checks.append({"name": nm, "passed": False, "detail": f"import src.geometry failed: {geo_err}"})
    else:
        check("geo.rect.area", lambda: _eq(geometry.area(rect), 12))
        check("geo.circle.area", lambda: _eq(round(geometry.area(circle), 2), 12.57))
        check("geo.rect.perimeter", lambda: _eq(geometry.perimeter(rect), 14))
        check("geo.bad.kind", lambda: _raises_value_error(lambda: geometry.area({"kind": "tri"})))

    try:
        report = _import("src.report")
        rep_err = ""
    except Exception as exc:  # noqa: BLE001
        report = None
        rep_err = f"{type(exc).__name__}: {exc}"

    if report is None:
        for nm in ("report.rect", "report.circle"):
            checks.append({"name": nm, "passed": False, "detail": f"import src.report failed: {rep_err}"})
    else:
        check("report.rect", lambda: _describe_eq(report, rect, "rect: area=12.00 perimeter=14.00"))
        check("report.circle", lambda: _describe_eq(report, circle, "circle: area=12.57 perimeter=12.57"))

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


def _describe_eq(report, shape, expected: str) -> None:
    actual = report.describe(shape)
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


if __name__ == "__main__":
    raise SystemExit(main())
