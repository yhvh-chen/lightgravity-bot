#!/usr/bin/env python3
"""LG-040 FILES-NARROW-FIX — python orchestrator.

Starts the loopback DENY proxy, the real app on the snapshot copy, and the
Firefox BiDi driver; streams the driver output; stops every process it started.
Copied in whole from the PROVEN BROWSER-RETEST-R1 orchestrator (exit143 wall
was post-commit; off-by-one root fixed there) with only OWN probe/driver paths
changed. Only the driver script name/paths below differ from the proven copy.
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
RUN = Path(os.environ.get("RUN_DIR", "/tmp/lg040-files-narrow-run"))
SNAP = PROBE / "evidence" / "snapshot" / "data"
DIST = ROOT / "frontend" / "dist"

def hb(msg: str) -> None:
    """Append a heartbeat line to RUN/heartbeat.log and stdout.

    Written immediately so a hard parent kill still leaves a persistent,
    timestamped trace of startup progress (the missing signal that made the
    prior failure look like an unexplained early kill).
    """
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} pid={os.getpid()} {msg}"
    print(line, flush=True)
    try:
        RUN.mkdir(parents=True, exist_ok=True)
        with open(RUN / "heartbeat.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def wait_file(p: Path, n: int = 200) -> None:
    for _ in range(n):
        if p.exists():
            return
        time.sleep(0.2)
    raise SystemExit(f"timeout waiting for {p}")


def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    hb(f"start root={ROOT} venv={VENV} venv_exists={VENV.exists()} run={RUN}")
    for p in (RUN / "proxy_ready.json", RUN / "app_ready.json", RUN / "ledger.json"):
        p.unlink(missing_ok=True)
    if not VENV.exists():
        hb(f"FATAL venv missing: {VENV}")
        raise SystemExit(f"venv python missing: {VENV}")

    hb("launch deny proxy")
    proxy = subprocess.Popen(
        [str(VENV), str(SCRIPTS / "deny_proxy.py"), "--port", "0",
         "--ledger", str(RUN / "ledger.json"), "--ready-file", str(RUN / "proxy_ready.json")],
        stdout=open(RUN / "deny-proxy.log", "w"), stderr=subprocess.STDOUT,
    )
    app = None
    try:
        wait_file(RUN / "proxy_ready.json")
        pport = json.loads((RUN / "proxy_ready.json").read_text())["port"]
        hb(f"deny proxy :{pport} pid={proxy.pid}")

        hb("launch app")
        app = subprocess.Popen(
            [str(VENV), str(SCRIPTS / "launch_app.py"),
             "--data-dir", str(SNAP), "--ocr-base-url", f"http://127.0.0.1:{pport}",
             "--ocr-model", "qwen3.8-27b", "--table-mode", "1",
             "--frontend-dist", str(DIST), "--ready-file", str(RUN / "app_ready.json")],
            stdout=open(RUN / "app.log", "w"), stderr=subprocess.STDOUT,
        )
        wait_file(RUN / "app_ready.json", 300)
        aurl = json.loads((RUN / "app_ready.json").read_text())["url"]
        hb(f"app {aurl} pid={app.pid}")
        for _ in range(60):
            try:
                urllib.request.urlopen(aurl.rstrip("/") + "/api/v1/health", timeout=2)
                break
            except Exception:
                time.sleep(0.25)

        profile = Path.home() / "snap" / "firefox" / "current" / f"lg040ret-{os.getpid()}"
        profile.mkdir(parents=True, exist_ok=True)
        cmd = ["node", str(SCRIPTS / "lg040-files-narrow-driver.mjs"),
               "--url", aurl, "--out", str(PROBE / "evidence" / "run"),
               "--firefox", "/snap/bin/firefox", "--deadline-ms", "90000",
               "--profile-dir", str(profile)]
        hb("RUN: " + " ".join(cmd))
        rc = subprocess.call(cmd, stdout=open(RUN / "driver.log", "w"), stderr=subprocess.STDOUT)
        hb(f"driver exit: {rc}")
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
        hb("stopped own children")


if __name__ == "__main__":
    sys.exit(main())
