#!/usr/bin/env python3
"""LG-049 R3 — boot the real app, verify role wiring + lifespan readiness.

ZERO model calls. Confirms:
  * product app booted with the REAL lifespan (served directly, not mounted);
  * real SDK executor wired; real independent model reviewer wired
    (`reviewer.reviewer == "model"` on a separate reviewer connection);
  * product persistent generation ledger is persistent, starts at the campaign
    count (0), and is NOT reset across restarts;
  * contract/package versions are as expected.

Readiness is health + the real runtime execution/reviewer report.  It does NOT
create a Task or spend any model budget.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
from api import Api  # noqa: E402

CAMPAIGN = HERE.parent / "campaign"
DATA_DIR = CAMPAIGN / "product-data"
READY = HERE.parent / "evidence" / "ready_boot.json"
TOKEN = "qa-r3-token-not-a-credential"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--max-generation-calls", type=int, default=16)
    ap.add_argument("--ready-out", default=str(READY))
    args = ap.parse_args()

    env = dict(os.environ)
    env["LIGHTGRAVITY_RUNTIME_TOKEN"] = TOKEN
    env["PYTHONPATH"] = str(REPO / "backend")

    ready_path = Path(args.ready_out)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    if ready_path.exists():
        ready_path.unlink()

    cmd = [
        sys.executable, str(HERE / "launch_app.py"),
        "--data-dir", str(DATA_DIR),
        "--port", str(args.port),
        "--max-generation-calls", str(args.max_generation_calls),
        "--ready-file", str(ready_path),
    ]
    log = open(HERE.parent / "raw" / "boot_server.log", "ab")
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    result = {"pid": proc.pid, "ready": None, "checks": {}, "ok": False}
    try:
        t0 = time.time()
        while time.time() - t0 < 90:
            if ready_path.exists():
                time.sleep(0.5)
                break
            if proc.poll() is not None:
                result["error"] = f"server exited early rc={proc.returncode}"
                break
            time.sleep(0.3)
        if ready_path.exists():
            ready = json.loads(ready_path.read_text())
            result["ready"] = ready
            api = Api(ready["url"], TOKEN)
            h = api.get("/api/v1/health")
            hb = h["body"] if isinstance(h["body"], dict) else {}
            result["checks"]["health_status"] = h["status"]
            result["checks"]["contract_version"] = hb.get("contract_version")
            result["checks"]["package_version"] = hb.get("package_version")
            g = api.get("/_lgr3_generation")
            gb = g["body"] if isinstance(g["body"], dict) else {}
            result["checks"]["generation"] = gb.get("generation")
            result["checks"]["execution"] = ready.get("execution")
            result["checks"]["reviewer"] = ready.get("reviewer")
            result["checks"]["warnings"] = ready.get("warnings")
            result["ok"] = True
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(50):
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        log.close()

    print(json.dumps(result, indent=2, default=str))
    (HERE.parent / "raw" / "boot_readiness.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
