#!/usr/bin/env python3
"""LG-040 FINAL-QA owner — isolated real-app launcher for browser E2E (reused BROWSER-RETEST).

Boots the **real** product via ``python -m lightgravity start --no-executor``
with:

* an isolated data dir under ``--data-dir`` (never the long-lived 8123/bot-data);
* an isolated free loopback port (or ``--port``);
* ``LIGHTGRAVITY_OCR_BASE_URL`` pointed at the **loopback reservation proxy**
  (never the LAN endpoint directly);
* ``LIGHTGRAVITY_OCR_MODEL=qwen3.8-27b``, OCR read timeout 110 s, max tokens
  4096, table mode as requested (default: ON for the named table test);
* the real built ``frontend/dist`` served by the product itself.

Additionally exposes an **evidence-only** read-only route ``/_lg040_fixture/<name>``
for the exact frozen fixture bytes so a real browser can reconstruct a genuine
``File`` object for the real upload path (byte-identical, hash-verified). This
route is added by a wrapper ASGI app around the product app; it does **not**
modify product source and is only reachable on the isolated loopback port.

Writes ``--ready-file`` JSON with ``{"url", "port", "data_dir"}`` once healthy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))

FIXTURE_DIR = (REPO / "probes/lg040/FINAL-QA-20261016/fixtures").resolve()
FIXTURE_HASHES = {
    "clear_real.pdf": "89c6b42242d0aa16efdb7ff814604c4bfc5214e0bbdd040ead67dcf453d9ec0f",
    "honest_table_grid_scale4.png": "39138a971d605f65d10b5df3a13e35c7cec5d3710bc38d55e6eb656fc1219652",
}


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--ocr-base-url", required=True)
    ap.add_argument("--ocr-model", default="qwen3.8-27b")
    ap.add_argument("--table-mode", choices=["0", "1"], default="1")
    ap.add_argument("--frontend-dist", default=str(REPO / "frontend" / "dist"))
    ap.add_argument("--ready-file", required=True)
    ap.add_argument("--runtime-token", default=None)
    args = ap.parse_args()

    port = args.port or _free_port()
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update(
        {
            "LIGHTGRAVITY_OCR_BASE_URL": args.ocr_base_url,
            "LIGHTGRAVITY_OCR_MODEL": args.ocr_model,
            "LIGHTGRAVITY_OCR_TIMEOUT_SECONDS": "110",
            "LIGHTGRAVITY_OCR_COLD_TIMEOUT_SECONDS": "110",
            "LIGHTGRAVITY_OCR_MAX_TOKENS": "4096",
            "LIGHTGRAVITY_OCR_TABLE_MODE": args.table_mode,
        }
    )
    if args.runtime_token:
        env["LIGHTGRAVITY_RUNTIME_TOKEN"] = args.runtime_token

    # The product reads OCR config directly from os.environ (backend_from_env),
    # so apply it to the launcher process before the runtime is built.
    os.environ.update(env)

    from lightgravity.config import Settings

    settings = Settings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=data_dir / "secrets",
        host="127.0.0.1",
        port=port,
    )

    # --- product app, exactly as the CLI builds it ---
    from lightgravity.api.bootstrap import StartupOptions, build_runtime

    options = StartupOptions(
        settings=settings,
        serve_frontend=True,
        frontend_dist=Path(args.frontend_dist),
        wire_real_executor=False,  # --no-executor equivalent
        seed_minimal_agent=False,
        allowed_hosts=("127.0.0.1", "localhost"),
    )
    runtime = build_runtime(options)

    app = runtime.app

    # --- evidence-only fixture route (wrapper; does not touch product source) ---
    from fastapi import FastAPI, HTTPException
    from starlette.responses import Response
    from starlette.routing import Route

    def _fixture(request):
        client = request.client
        if client and client.host not in ("127.0.0.1", "::1"):
            raise HTTPException(403, "loopback only")
        name = request.path_params["name"]
        path = (FIXTURE_DIR / name).resolve()
        if FIXTURE_DIR not in path.parents or not path.is_file():
            raise HTTPException(404, "unknown fixture")
        data = path.read_bytes()
        expected = FIXTURE_HASHES.get(name)
        if expected and hashlib.sha256(data).hexdigest() != expected:
            raise HTTPException(500, "fixture hash mismatch")
        return Response(data, media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store"})

    wrapper = FastAPI(routes=[Route("/_lg040_fixture/{name}", _fixture)])
    wrapper.mount("/", app)

    import uvicorn

    ready = Path(args.ready_file)
    ready.write_text(json.dumps({"url": f"http://127.0.0.1:{port}/",
                                 "port": port, "data_dir": str(data_dir)}), "utf-8")

    config = uvicorn.Config(wrapper, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _health_wait() -> None:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1):
                    return
            except Exception:
                time.sleep(0.1)

    threading.Thread(target=_health_wait, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
