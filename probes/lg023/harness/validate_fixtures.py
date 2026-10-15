#!/usr/bin/env python3
"""LG-023 offline fixture validation (zero model calls).

For each fixture:
* ``initial/`` must FAIL acceptance (masked stub);
* ``reference/`` must PASS acceptance (6/6).

Writes a JSON report to ``evidence/offline/fixture_validation.json`` and prints it.

Usage::

    uv run python probes/lg023/harness/validate_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
FIXTURES = PROBE / "fixtures"
OUT = PROBE / "evidence" / "offline" / "fixture_validation.json"

SAMPLES = ("s1_independent", "s2_interface")


def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(root)).encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def _run_acceptance(workspace: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("DEEPSEEK_API_KEY",)}
    proc = subprocess.run(
        [sys.executable, str(FIXTURES / _current_sample / "acceptance.py"), "--workspace", str(workspace)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    out = proc.stdout.strip().splitlines()
    try:
        report = json.loads(out[-1]) if out else {"passed": -1, "total": -1}
    except json.JSONDecodeError:
        report = {"passed": -1, "total": -1, "raw": proc.stdout, "stderr": proc.stderr}
    report["exit_code"] = proc.returncode
    return report


_current_sample = ""


def main() -> int:
    global _current_sample
    results: dict[str, object] = {}
    ok = True
    for sample in SAMPLES:
        _current_sample = sample
        fix = FIXTURES / sample
        entry: dict[str, object] = {"initial_hash": _tree_hash(fix / "initial")}
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            shutil.copytree(fix / "initial", ws, dirs_exist_ok=True)
            init_report = _run_acceptance(ws)
        entry["initial"] = init_report
        entry["initial_fails"] = init_report.get("passed", -1) < init_report.get("total", -1)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            shutil.copytree(fix / "initial", ws, dirs_exist_ok=True)
            shutil.copytree(fix / "reference", ws, dirs_exist_ok=True)
            ref_report = _run_acceptance(ws)
        entry["reference"] = ref_report
        entry["reference_passes"] = ref_report.get("passed") == ref_report.get("total") == 6
        if not (entry["initial_fails"] and entry["reference_passes"]):
            ok = False
        results[sample] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ok": ok, "samples": results}
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
