#!/usr/bin/env python3
"""Offline fixture validation: initial must fail, reference must pass.

No model calls. Usage:
    python3 driver/validate_fixtures.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"


def run_acceptance(fixture: str, workspace: Path, stage: int | None) -> dict:
    cmd = [sys.executable, str(FIX / fixture / "acceptance.py"), "--workspace", str(workspace)]
    if stage is not None:
        cmd += ["--stage", str(stage)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"acceptance crashed for {fixture}: {proc.stderr[-500:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def make_workspace(fixture: str, source: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=f"fix-{fixture}-"))
    src = FIX / fixture / source
    for item in src.iterdir():
        if item.is_dir():
            shutil.copytree(item, tmp / item.name)
        else:
            shutil.copy2(item, tmp / item.name)
    # ensure empty __init__ exists for reference trees
    (tmp / "src").mkdir(parents=True, exist_ok=True)
    (tmp / "src" / "__init__.py").touch(exist_ok=True)
    return tmp


STAGES = {"t1_independent": [None], "t2_interface": [None], "t3_evolving": [1, 2]}


def main() -> int:
    failures = 0
    for fixture, stages in STAGES.items():
        for stage in stages:
            init_ws = make_workspace(fixture, "initial")
            init = run_acceptance(fixture, init_ws, stage)
            print(f"{fixture} stage={stage} initial: {init['passed']}/{init['total']} passed"
                  f" (expected 0) -> {'OK' if init['passed'] == 0 else 'FAIL'}")
            if init["passed"] != 0:
                failures += 1
            ref_name = "reference"
            if fixture == "t3_evolving" and stage == 1:
                # final reference also passes stage 1
                ref_name = "reference"
            ref_ws = make_workspace(fixture, ref_name)
            ref = run_acceptance(fixture, ref_ws, stage)
            print(f"{fixture} stage={stage} reference: {ref['passed']}/{ref['total']} passed"
                  f" (expected all) -> {'OK' if ref['passed'] == ref['total'] else 'FAIL'}")
            if ref["passed"] != ref["total"]:
                failures += 1
            shutil.rmtree(init_ws, ignore_errors=True)
            shutil.rmtree(ref_ws, ignore_errors=True)

    # extra: round1-only reference passes stage1, fails stage2
    ws = make_workspace("t3_evolving", "reference_round1")
    s1 = run_acceptance("t3_evolving", ws, 1)
    s2 = run_acceptance("t3_evolving", ws, 2)
    ok = s1["passed"] == s1["total"] and s2["passed"] < s2["total"]
    print(f"t3_evolving round1-only: stage1={s1['passed']}/{s1['total']} stage2={s2['passed']}/{s2['total']}"
          f" (expect stage1 all, stage2 partial) -> {'OK' if ok else 'FAIL'}")
    if not ok:
        failures += 1
    shutil.rmtree(ws, ignore_errors=True)

    print(f"\nfixture validation: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
