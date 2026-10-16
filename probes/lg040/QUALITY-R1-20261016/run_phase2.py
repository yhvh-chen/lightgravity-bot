#!/usr/bin/env python3
"""LG-040 QUALITY-R1 phase 2: image (PNG) + cache delete/rebuild reproduction.

Fills the gaps from phase 1 within the remaining frozen embedding quota:
* upload the English image again as a **PNG** (phase-1 TIFF embed failed with the
  service "Failed to load image or audio file"), so the real image-vector path runs;
* explicitly DELETE the vector cache, then rebuild from files (reproduction);
* re-run Q3 (image) and Q1 (reproducibility) over the rebuilt cache.

Uses the same real app + counting hard-cap proxy.  Honest: if the PNG also fails
to embed, that is reported as a real image-embedding limitation, not hidden.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = HERE / "evidence"
DATA = Path(os.environ.get("LG040Q_DATA", "/tmp/lg040-quality-r1-20261016/data"))
PROXY_PORT = 18140
APP_PORT = 18141
BASE = f"http://127.0.0.1:{PROXY_PORT}"
APP = f"http://127.0.0.1:{APP_PORT}"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_app(url: str, timeout: float = 30.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/v1/health", timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    import httpx

    png = HERE / "corpus/d3_phototest.png"
    env = dict(os.environ)
    env.update({
        "LIGHTGRAVITY_DATA_DIR": str(DATA),
        "LIGHTGRAVITY_WORKSPACE_ROOT": str(DATA / "workspaces"),
        "LIGHTGRAVITY_SECRET_STORE": str(DATA / "secrets"),
        "LIGHTGRAVITY_VECTOR_BASE_URL": BASE,
        "LIGHTGRAVITY_VECTOR_MODEL": "embeddinggemma-2-Q8_0",
        "LIGHTGRAVITY_VECTOR_TIMEOUT_SECONDS": "90",
        "LIGHTGRAVITY_VECTOR_COLD_TIMEOUT_SECONDS": "90",
        "LIGHTGRAVITY_OCR_BASE_URL": BASE,
        "LIGHTGRAVITY_OCR_MODEL": "qwen3.8-27b",
    })
    app_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "--factory", "lightgravity.api.app:create_app",
         "--host", "127.0.0.1", "--port", str(APP_PORT), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    proxy_proc = subprocess.Popen(
        [sys.executable, str(HERE / "counting_proxy.py"), str(PROXY_PORT)],
        cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    out: dict = {}
    try:
        if not wait_app(APP):
            log("app failed to start"); return 2
        client = httpx.Client(base_url=APP, timeout=180)

        # upsize the image source with a PNG original
        data = png.read_bytes()
        r = client.post("/api/v1/sources", json={
            "request_id": "lg040q-d3png",
            "filename": "d3_phototest.png",
            "content_base64": base64.b64encode(data).decode("ascii"),
            "title": "LG040Q D3 PNG",
            "media_type": "image/png",
            "scope": {}, "origin": {"kind": "upload"}, "payload_hash": None,
        })
        d3b = r.json()["source"]["source_id"]
        log(f"intake D3png -> {d3b} ({r.status_code})")
        out["d3b_source_id"] = d3b

        # remove the phase-1 TIFF source so the rebuild does not re-attempt an
        # unsupported media type and waste a POST (delete action makes it unavailable)
        d3_tif = "source_01M51N8WQWF748WMW0XPKSZXGS"
        rd = client.post(f"/api/v1/sources/{d3_tif}/actions", json={"action": "delete", "confirmed": True})
        out["d3_tif_delete"] = {"http": rd.status_code, "body": rd.json()}
        log(f"delete D3 tif -> {rd.status_code}")

        # DELETE cache then rebuild (reproduction)
        cache_file = DATA / "sources-index" / "vectors" / "vectors.jsonl"
        existed = cache_file.exists()
        if existed:
            cache_file.unlink()
        out["cache_deleted"] = existed
        log(f"cache deleted (existed={existed})")

        t0 = time.monotonic()
        r = client.post("/api/v1/vector/rebuild")
        rebuild = r.json()
        out["rebuild"] = rebuild
        out["rebuild_wall_s"] = round(time.monotonic() - t0, 3)
        log(f"rebuild -> {r.status_code} indexed={rebuild.get('indexed')} not={rebuild.get('not_indexed')} docs={rebuild.get('documents')}")

        # Q3 (image) and Q1 (reproducibility) over rebuilt cache
        r = client.get("/api/v1/vector/search", params={"q": "scanned page of twelve point text with the quick brown fox sentence", "limit": 10}).json()
        out["Q3_rebuilt"] = r
        log(f"Q3' -> {r.get('index_status')} hits={[(h.get('title')) for h in r.get('hits', [])]}")
        r = client.get("/api/v1/vector/search", params={"q": "SI base unit for electric current", "limit": 10}).json()
        out["Q1_rebuilt"] = r
        log(f"Q1'' -> {r.get('index_status')} hits={[(h.get('title')) for h in r.get('hits', [])]}")

        status = client.get("/api/v1/vector/status").json()
        out["status_after"] = status
        (EVIDENCE / "phase2.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0
    finally:
        for proc in (app_proc, proxy_proc):
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
