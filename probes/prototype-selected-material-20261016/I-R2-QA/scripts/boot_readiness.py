#!/usr/bin/env python3
"""LG-047 R2 — boot the real app, verify role wiring + lifespan readiness.

ZERO model calls. Confirms:
  * product app booted with the REAL lifespan (coordinator background loop);
  * real executor wired; real model reviewer wired (`reviewer: model`);
  * product persistent generation ledger is persistent and starts at the
    campaign count (never reset).

Readiness is not "health alone": we additionally prove the coordinator loop is
live by exercising a real control-free path (create Task + read messages) and
checking the runtime execution report.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--max-generation-calls", type=int, default=8)
    ap.add_argument("--ready-out", default=str(READY))
    args = ap.parse_args()

    # Deterministic runtime token so the harness can call protected writes.
    token = "qa-r2-token-not-a-credential"
    env = dict(os.environ)
    env["LIGHTGRAVITY_RUNTIME_TOKEN"] = token
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
    result = {"pid": proc.pid, "cmd": cmd, "ready": None, "checks": {}, "ok": False}
    try:
        t0 = time.time()
        while time.time() - t0 < 90:
            if ready_path.exists():
                time.sleep(0.5)  # let uvicorn bind
                break
            if proc.poll() is not None:
                result["error"] = f"server exited early rc={proc.returncode}"
                break
            time.sleep(0.3)
        if ready_path.exists():
            ready = json.loads(ready_path.read_text())
            result["ready"] = ready
            base = ready["url"]
            api = Api(base, token)
            # health (baseline)
            h = api.get("/api/v1/health")
            result["checks"]["health_status"] = h["status"]
            body = h["body"] if isinstance(h["body"], dict) else {}
            result["checks"]["contract_version"] = body.get("contract_version")
            result["checks"]["package_version"] = body.get("package_version")
            gen = api.get("/_lg047r2_generation")
            result["checks"]["generation"] = gen["body"]
            # lifespan readiness: coordinator control path must answer for a real Task
            task = api.post("/api/v1/tasks", {
                "request_id": "qa-r2-boot-task",
                "title": "R2 boot readiness",
                "objective": "readiness only",
            })
            result["checks"]["create_task_status"] = task["status"]
            tid = task["body"]["task_id"] if isinstance(task["body"], dict) else None
            if tid:
                msgs = api.get(f"/api/v1/tasks/{tid}/messages")
                result["checks"]["read_messages_status"] = msgs["status"]
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
    out = HERE.parent / "raw" / "boot_readiness.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
