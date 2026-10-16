#!/usr/bin/env python3
"""LG-049 R3 — real product launcher (DIRECT app, real lifespan).

Boots the **actual product app** (`lightgravity.api.app.create_app` via
`build_runtime`) with:

* the **real product lifespan** (served directly by uvicorn, NOT mounted under a
  wrapper — this is the R1 harness defect fixed);
* the **real SDK executor** (`wire_real_executor=True`, real `LocalOpenAIAgentConfig`
  + loopback auth proxy) and the **real ModelDialogue + real ModelReviewer**;
* three real DeepSeek `openai-compat` connections (coordinator/worker/reviewer)
  whose credential comes ONLY from the process env `DEEPSEEK_API_KEY`
  (`credential_ref`); no secret is written to disk or printed;
* the product's **persistent generation ledger** rooted under the R2 campaign
  `data_dir`, capped at **16** before any forward, never reset across restarts.

Evidence-only loopback routes are added **directly onto the product app** (the
SPA catch-all is shadowed correctly by inserting before it):

* `GET /_lgr3_fixture/<name>` — serves the frozen human-written English
  fixture bytes (hash header) so a real browser can build a real `File` for the
  real upload path; no product source is modified.
* `GET /_lgr3_generation` — read-only snapshot of the product's own persistent
  generation ledger (count/limit/remaining/persistent/corrupt).

Run:
    /home/yhvh/code/lightgravity-bot/.venv/bin/python launch_app.py \
        --data-dir <campaign>/product-data --port <p> --max-generation-calls 16 \
        --ready-file <json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]  # .../N-R3-LIFECYCLE/scripts/launch_app.py -> repo root
sys.path.insert(0, str(REPO / "backend"))

FIXTURE_DIR = (REPO / "examples/selected-material-prototype/fixtures").resolve()


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _seed_connections(settings, credential_ref: str, model: str, base_url: str) -> None:
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    svc = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))
    for conn_id, title in (
        ("conn-coordinator", "N-R3 coordinator (DeepSeek)"),
        ("conn-worker", "N-R3 worker (DeepSeek)"),
        ("conn-reviewer", "N-R3 reviewer (DeepSeek)"),
    ):
        try:
            svc.create_connection(
                conn_id,
                title=title,
                backend="openai-compat",
                model=model,
                base_url=base_url,
                credential_ref=credential_ref,
                enabled=True,
                actor="qa-r3",
                request_id=f"qa-r3-{conn_id}",
            )
        except Exception as exc:  # idempotent across restarts (never reset data)
            if "already exists" not in str(exc):
                raise
    current = svc.get_settings()
    svc.update_settings(
        expected_revision=current.get("revision", 0),
        actor="qa-r3",
        default_coordinator_connection_ref="conn-coordinator",
        default_worker_connection_ref="conn-worker",
        default_reviewer_connection_ref="conn-reviewer",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--max-generation-calls", type=int, default=16)
    ap.add_argument("--credential-ref", default="DEEPSEEK_API_KEY")
    ap.add_argument("--model", default=os.environ.get("LG_QA_MODEL", "deepseek-v4-flash"))
    ap.add_argument("--base-url", default="https://api.deepseek.com/v1")
    ap.add_argument("--frontend-dist", default=str(REPO / "frontend" / "dist"))
    ap.add_argument("--ready-file", required=True)
    args = ap.parse_args()

    port = args.port or _free_port()
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Hard cap read by the product before each forward.
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(args.max_generation_calls)

    from lightgravity.config import Settings

    settings = Settings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=data_dir / "secrets",
        host="127.0.0.1",
        port=port,
    )

    _seed_connections(settings, args.credential_ref, args.model, args.base_url)

    from lightgravity.api.bootstrap import StartupOptions, build_runtime

    options = StartupOptions(
        settings=settings,
        serve_frontend=True,
        frontend_dist=Path(args.frontend_dist),
        wire_real_executor=True,   # REAL SDK worker + real reviewer
        seed_minimal_agent=True,
        allowed_hosts=("127.0.0.1", "localhost"),
        max_proxy_calls=args.max_generation_calls,
    )
    runtime = build_runtime(options)
    app = runtime.app

    from fastapi import HTTPException, Request
    from starlette.responses import Response
    from starlette.routing import Route

    def _fixture(request: Request):
        client = request.client
        if client and client.host not in ("127.0.0.1", "::1"):
            raise HTTPException(403, "loopback only")
        name = Path(request.path_params["name"]).name
        path = (FIXTURE_DIR / name).resolve()
        if FIXTURE_DIR not in path.parents or not path.is_file():
            raise HTTPException(404, "unknown fixture")
        data = path.read_bytes()
        return Response(
            data,
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-store",
                "X-LGR3-Fixture-Sha256": hashlib.sha256(data).hexdigest(),
            },
        )

    def _generation(request: Request):
        from lightgravity.adapter.proxy import global_generation_counter

        return Response(
            json.dumps({"generation": global_generation_counter().snapshot()}),
            media_type="application/json",
        )

    app.router.routes.insert(0, Route("/_lgr3_generation", _generation))
    app.router.routes.insert(0, Route("/_lgr3_fixture/{name}", _fixture))

    import uvicorn

    ready = Path(args.ready_file)
    ready.write_text(
        json.dumps(
            {
                "url": f"http://127.0.0.1:{port}/",
                "port": port,
                "data_dir": str(data_dir),
                "execution": runtime.execution_report(),
                "reviewer": runtime.reviewer,
                "warnings": runtime.warnings,
            },
            default=str,
        ),
        "utf-8",
    )

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _health_wait() -> None:
        for _ in range(200):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/v1/health", timeout=1
                ):
                    return
            except Exception:
                time.sleep(0.1)

    threading.Thread(target=_health_wait, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
