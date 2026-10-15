#!/usr/bin/env python3
"""Objective machine gate for sample s2_pipeline. Hidden from the model.

Usage: python3 acceptance.py --workspace <dir>

Cross-module interface: report.describe must import area/perimeter from .shapes.
Checks (6):
  shapes.rect.area / shapes.circle.area / shapes.bad.kind
  shapes.rect.perimeter
  report.rect / report.circle (depends on the shapes interface)
  no_write_from_verify
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

    def _raises_value_error(fn) -> None:
        try:
            fn()
        except ValueError:
            return
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"expected ValueError, got {type(exc).__name__}: {exc}") from exc
        raise AssertionError("expected ValueError, nothing raised")

    rect = {"kind": "rect", "width": 3, "height": 4}
    circle = {"kind": "circle", "radius": 2}

    try:
        shapes = importlib.import_module("src.shapes")
        shp_err = ""
    except Exception as exc:  # noqa: BLE001
        shapes = None
        shp_err = f"{type(exc).__name__}: {exc}"

    if shapes is None:
        for nm in ("shapes.rect.area", "shapes.circle.area", "shapes.rect.perimeter",
                   "shapes.bad.kind"):
            check(nm, lambda: (_ for _ in ()).throw(AssertionError(shp_err)))
    else:
        check("shapes.rect.area", lambda: _eq(shapes.area(rect), 12))
        check("shapes.circle.area", lambda: _eq(round(shapes.area(circle), 2), 12.57))
        check("shapes.rect.perimeter", lambda: _eq(shapes.perimeter(rect), 14))
        check("shapes.bad.kind", lambda: _raises_value_error(lambda: shapes.area({"kind": "tri"})))

    try:
        report = importlib.import_module("src.report")
        rep_err = ""
    except Exception as exc:  # noqa: BLE001
        report = None
        rep_err = f"{type(exc).__name__}: {exc}"

    if report is None:
        for nm in ("report.rect", "report.circle"):
            check(nm, lambda: (_ for _ in ()).throw(AssertionError(rep_err)))
    else:
        check("report.rect", lambda: _eq(report.describe(rect), "rect: area=12.00 perimeter=14.00"))
        check("report.circle", lambda: _eq(report.describe(circle), "circle: area=12.57 perimeter=12.57"))

    extra = sorted(
        str(p.relative_to(ws))
        for p in (ws / "src").glob("*.py")
        if p.name not in {"__init__.py", "shapes.py", "report.py"}
    )
    check("no_write_from_verify", lambda: _eq(extra, []))

    passed = sum(1 for c in checks if c["passed"])
    print(json.dumps({"checks": checks, "passed": passed, "total": len(checks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
