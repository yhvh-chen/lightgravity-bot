#!/usr/bin/env python3
"""LG-040 FINAL-QA — generic single-driver runner (own probe).

Boots the deny proxy + the real app on the snapshot copy and runs ONE named
driver against it, then stops every process it started. Same proven child-tree
ownership pattern as orchestrate.py. Read-only w.r.t. product source; the deny
proxy guarantees zero inference attempts reach any upstream.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parent
PROBE = SCRIPTS.parent
VENV = ROOT / ".venv" / "bin" / "python"
DIST = ROOT / "frontend" / "dist"


def wait_file(p: Path, n: int = 300) -> None:
    for _ in range(n):
        if p.exists():
            return
        time.sleep(0.2)
    raise SystemExit(f"timeout waiting for {p}")


def main() -> int:
    driver = sys.argv[1]
    run = Path(os.environ.get("RUN_DIR", f"/tmp/lg040-finalqa-{driver}"))
    snap = PROBE / "evidence" / "snapshot" / "data"
    run.mkdir(parents=True, exist_ok=True)
    for p in (run / "proxy_ready.json", run / "app_ready.json", run / "ledger.json"):
        p.unlink(missing_ok=True)

    proxy = subprocess.Popen(
        [str(VENV), str(SCRIPTS / "deny_proxy.py"), "--port", "0",
         "--ledger", str(run / "ledger.json"), "--ready-file", str(run / "proxy_ready.json")],
        stdout=open(run / "deny-proxy.log", "w"), stderr=subprocess.STDOUT,
    )
    app = None
    try:
        wait_file(run / "proxy_ready.json")
        pport = json.loads((run / "proxy_ready.json").read_text())["port"]
        app = subprocess.Popen(
            [str(VENV), str(SCRIPTS / "launch_app.py"),
             "--data-dir", str(snap), "--ocr-base-url", f"http://127.0.0.1:{pport}",
             "--ocr-model", "qwen3.8-27b", "--table-mode", "1",
             "--frontend-dist", str(DIST), "--ready-file", str(run / "app_ready.json")],
            stdout=open(run / "app.log", "w"), stderr=subprocess.STDOUT,
        )
        wait_file(run / "app_ready.json", 300)
        aurl = json.loads((run / "app_ready.json").read_text())["url"]
        for _ in range(60):
            try:
                urllib.request.urlopen(aurl.rstrip("/") + "/api/v1/health", timeout=2)
                break
            except Exception:
                time.sleep(0.25)
        profile = Path.home() / "snap" / "firefox" / "current" / f"lg040fq-{os.getpid()}"
        profile.mkdir(parents=True, exist_ok=True)
        cmd = ["node", str(SCRIPTS / driver), "--url", aurl,
               "--out", str(PROBE / "evidence" / "run"),
               "--firefox", "/snap/bin/firefox", "--deadline-ms", "90000",
               "--profile-dir", str(profile)]
        print("RUN:", " ".join(cmd), flush=True)
        rc = subprocess.call(cmd, stdout=open(run / "driver.log", "w"), stderr=subprocess.STDOUT)
        print("driver exit:", rc, flush=True)
        return rc
    finally:
        for p in (app, proxy):
            if p and p.poll() is None:
                try:
                    p.send_signal(signal.SIGTERM)
                except Exception:
                    pass
        time.sleep(1.0)
        for p in (app, proxy):
            if p and p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass
        print("stopped own children", flush=True)


if __name__ == "__main__":
    sys.exit(main())
