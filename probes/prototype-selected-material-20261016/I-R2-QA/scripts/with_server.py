#!/usr/bin/env python3
"""LG-047 R2 — run a harness script against a booted real product app.

Boots the app DIRECT (real lifespan) with the campaign data dir + persistent
ledger, waits for readiness (ready-file AND health), runs the given command with
`--base <url>`, then stops the server and confirms it is gone. The campaign
data dir / ledger is NEVER deleted.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CAMPAIGN = HERE.parent / "campaign"
DATA_DIR = CAMPAIGN / "product-data"
TOKEN = "qa-r2-token-not-a-credential"


def wait_health(port: int, timeout: float = 30.0) -> bool:
    """Poll the app health on a KNOWN real port with a small finite bound.

    FIX (R2 harness defect): never call this with port 0. Port 0 can never
    connect, so the loop would burn the entire timeout. The ready file carries
    the real port; resolve it first, then call wait_health(real_port).
    """
    if not port:
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="command after -- ; use {base} placeholder")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--max-generation-calls", type=int, default=8)
    ap.add_argument("--tag", default="run")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    # REMAINDER may contain a leading "--" separator; drop it.
    cmd = [c for c in args.cmd if c != "--"]
    ready = HERE.parent / "evidence" / f"ready_{args.tag}.json"
    ready.parent.mkdir(parents=True, exist_ok=True)
    if ready.exists():
        ready.unlink()

    env = dict(os.environ)
    env["LIGHTGRAVITY_RUNTIME_TOKEN"] = TOKEN
    env["PYTHONPATH"] = str(REPO / "backend")

    launch = [
        sys.executable, str(HERE / "launch_app.py"),
        "--data-dir", str(DATA_DIR),
        "--port", str(args.port),
        "--max-generation-calls", str(args.max_generation_calls),
        "--ready-file", str(ready),
    ]
    srv_log = open(HERE.parent / "raw" / f"server_{args.tag}.log", "ab")
    proc = subprocess.Popen(launch, env=env, stdout=srv_log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    rc = 999
    try:
        # FIX: never probe port 0. Wait (bounded) for the ready file, which
        # carries the REAL port the product app actually bound, then health-check
        # that real port with a small finite bound. This removes the ~90s dead
        # wait the old code self-inflicted via wait_health(0).
        port = args.port
        t0 = time.time()
        while time.time() - t0 < 30:
            if ready.exists():
                try:
                    port = json.loads(ready.read_text())["port"]
                except Exception:
                    port = args.port
                break
            if proc.poll() is not None:
                print(f"server exited early rc={proc.returncode}")
                return 2
            time.sleep(0.1)
        if not wait_health(port, timeout=15.0):
            print(f"health never came up on real port {port}")
            return 3
        base = f"http://127.0.0.1:{port}"
        resolved = [c.replace("{base}", base) for c in cmd]
        print(f"RUN: {' '.join(resolved)}  (server pid {proc.pid}, port {port})")
        rc = subprocess.call(resolved, env=env)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(60):
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        srv_log.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
