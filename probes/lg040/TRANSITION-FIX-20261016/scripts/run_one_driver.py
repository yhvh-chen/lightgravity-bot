#!/usr/bin/env python3
"""LG-040 SETTLED-QA-20261016 — own single-driver runner (whole-file copy of the
prior FINAL-QA own run_one_driver.py, with own path constants and binding capture).

Boots the deny proxy + the real app on THIS probe's snapshot copy and runs ONE
named driver against it, then stops every process it started. Records the
candidate commit, served bundle hashes and snapshot tree hash into the run dir
so the browser evidence is bound to a specific source/bundle SHA.

Read-only w.r.t. product source; the deny proxy guarantees zero inference
attempts reach any upstream.
"""

from __future__ import annotations

import hashlib
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


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tree_hash(d: Path) -> tuple[int, str]:
    files = sorted(p for p in d.rglob("*") if p.is_file())
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(d).as_posix().encode())
        h.update(sha256(p).encode())
    return len(files), h.hexdigest()


def wait_file(p: Path, n: int = 300) -> None:
    for _ in range(n):
        if p.exists():
            return
        time.sleep(0.2)
    raise SystemExit(f"timeout waiting for {p}")


def write_bindings(run: Path, snap: Path) -> None:
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    branch = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    assets = {}
    for p in sorted((DIST / "assets").glob("*")):
        assets[p.name] = sha256(p)
    index_html = DIST / "index.html"
    nfiles, thash = tree_hash(snap)
    payload = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "worktree": str(ROOT),
        "branch": branch,
        "commit": commit,
        "venv_link": os.readlink(VENV.parent) if VENV.parent.is_symlink() else str(VENV.parent),
        "frontend_dist_index_sha256": sha256(index_html) if index_html.exists() else None,
        "frontend_dist_assets": assets,
        "snapshot_dir": str(snap),
        "snapshot_files": nfiles,
        "snapshot_tree_sha256": thash,
    }
    (run / "bindings.json").write_text(json.dumps(payload, indent=2), "utf-8")
    print("BINDINGS:", json.dumps({"commit": commit, "branch": branch,
                                   "css_sha256": assets.get("index-DIrliPjY.css"),
                                   "snapshot_tree_sha256": thash}), flush=True)


def main() -> int:
    driver = sys.argv[1]
    run = Path(os.environ.get("RUN_DIR", f"/tmp/lg040-settled-{driver}"))
    snap = Path(os.environ["LG040_SNAP"]) if os.environ.get("LG040_SNAP") else (PROBE / "evidence" / "snapshot" / "data")
    run.mkdir(parents=True, exist_ok=True)
    for p in (run / "proxy_ready.json", run / "app_ready.json", run / "ledger.json"):
        p.unlink(missing_ok=True)
    write_bindings(run, snap)
    print(f"ROOT={ROOT}\nVENV={VENV}\nDIST={DIST}\nSNAP={snap}\nRUN={run}", flush=True)

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
        profile = Path.home() / "snap" / "firefox" / "current" / f"lg040set-{os.getpid()}"
        profile.mkdir(parents=True, exist_ok=True)
        cmd = ["node", str(SCRIPTS / driver), "--url", aurl,
               "--out", str(PROBE / "evidence" / "run"),
               "--firefox", "/snap/bin/firefox", "--deadline-ms", "90000",
               "--profile-dir", str(profile)]
        # forward an optional bounded-readiness window for the settled driver
        if os.environ.get("LG040_BOUND_MS"):
            cmd += ["--bound-ms", os.environ["LG040_BOUND_MS"]]
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
