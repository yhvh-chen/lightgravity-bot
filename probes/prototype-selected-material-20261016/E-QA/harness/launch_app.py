#!/usr/bin/env python3
"""LG-047 E-QA — isolated real-product launcher (adapted from the LG-040
WHOLE real-app launcher, `probes/lg040/TRANSITION-QA-20261016/scripts/launch_app.py`).

Differences from the LG-040 launcher (only what LG-047 needs):

* boots the **real SDK executor** (``wire_real_executor=True``), not
  ``--no-executor`` — this is the real DeepSeek worker/reviewer path;
* the real executor is the *configured bootstrap* runtime; no
  ``UnavailableExecutor`` fallback and no FakeExecutor;
* wired through the product's real persistent generation ledger, capped at the
  LG-047 campaign budget (``LIGHTGRAVITY_MAX_GENERATION_CALLS``, default 12);
* seeds **three** real connections (coordinator / worker / reviewer), all the
  DeepSeek OpenAI-compat backend with ``credential_ref`` resolving from the
  process environment (``DEEPSEEK_API_KEY``); no secret is written to disk,
  no secret is printed;
* an evidence-only loopback fixture route ``/_lg047_fixture/<name>`` serves the
  frozen human-written English fixture bytes so a real browser can build a real
  ``File`` for the real upload path (byte-identical). It is a wrapper app around
  the product app and does not modify product source.

It also exposes an evidence-only read-only route ``/_lg047_generation`` that
returns the product's own persistent generation-ledger snapshot, so the QA
harness can record the real pre-forward counter without trusting only its own
guard.

Run:
    uv run --no-sync python launch_app.py --data-dir <tmp> --port <p> \
        --max-generation-calls 12 --ready-file <json>
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

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))

FIXTURE_DIR = (REPO / "examples/selected-material-prototype/fixtures").resolve()


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _seed_connections(settings: "Settings", credential_ref: str) -> dict:
    """Create coordinator/worker/reviewer connections and set them as defaults.

    Runs BEFORE ``build_runtime`` so the reviewer/dialogue wiring sees the
    defaults and produces a real ``reviewer: model`` status. All three use the
    real DeepSeek OpenAI-compat backend. The credential lives only in the
    environment (``credential_ref`` maps to ``DEEPSEEK_API_KEY``); it is never
    written to the data dir.
    """

    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    svc = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))
    model = os.environ.get("LG_QA_MODEL", "deepseek-v4-flash")
    base_url = "https://api.deepseek.com/v1"
    created = {}
    for conn_id, role_title in (
        ("conn-coordinator", "QA coordinator (DeepSeek)"),
        ("conn-worker", "QA worker (DeepSeek)"),
        ("conn-reviewer", "QA reviewer (DeepSeek)"),
    ):
        svc.create_connection(
            conn_id,
            title=role_title,
            backend="openai-compat",
            model=model,
            base_url=base_url,
            credential_ref=credential_ref,
            enabled=True,
            actor="qa",
            request_id=f"qa-{conn_id}",
        )
        created[conn_id] = True
    current = svc.get_settings()
    rev = current.get("revision", 0)
    svc.update_settings(
        expected_revision=rev,
        actor="qa",
        default_coordinator_connection_ref="conn-coordinator",
        default_worker_connection_ref="conn-worker",
        default_reviewer_connection_ref="conn-reviewer",
    )
    return created


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--max-generation-calls", type=int, default=12)
    ap.add_argument("--credential-ref", default="DEEPSEEK_API_KEY")
    ap.add_argument("--frontend-dist", default=str(REPO / "frontend" / "dist"))
    ap.add_argument("--ready-file", required=True)
    args = ap.parse_args()

    port = args.port or _free_port()
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    # The product reads the hard cap from this env var before each forward.
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(args.max_generation_calls)

    from lightgravity.config import Settings

    settings = Settings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=data_dir / "secrets",
        host="127.0.0.1",
        port=port,
    )

    # Seed the three real connections/settings BEFORE runtime assembly so the
    # built runtime wires the real reviewer+coordinator (not "unavailable").
    _seed_connections(settings, args.credential_ref)

    from lightgravity.api.bootstrap import StartupOptions, build_runtime

    options = StartupOptions(
        settings=settings,
        serve_frontend=True,
        frontend_dist=Path(args.frontend_dist),
        wire_real_executor=True,  # REAL SDK worker + reviewer path
        seed_minimal_agent=True,
        allowed_hosts=("127.0.0.1", "localhost"),
        max_proxy_calls=args.max_generation_calls,
    )
    runtime = build_runtime(options)

    app = runtime.app

    # Evidence-only routes are added DIRECTLY onto the product app (not a
    # wrapper mount) so the product app's own lifespan — which starts the
    # coordinator background queue worker — actually runs.
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
                "X-LG047-Fixture-Sha256": hashlib.sha256(data).hexdigest(),
            },
        )

    def _generation(request: Request):
        from lightgravity.adapter.proxy import global_generation_counter

        return Response(
            json.dumps({"generation": global_generation_counter().snapshot()}),
            media_type="application/json",
        )

    # Insert BEFORE the SPA catch-all (``/{path:path}``) so these are matched
    # first; a plain append would be shadowed by the frontend route.
    app.router.routes.insert(0, Route("/_lg047_generation", _generation))
    app.router.routes.insert(0, Route("/_lg047_fixture/{name}", _fixture))

    import uvicorn

    ready = Path(args.ready_file)
    ready.write_text(
        json.dumps(
            {
                "url": f"http://127.0.0.1:{port}/",
                "port": port,
                "data_dir": str(data_dir),
                "execution": runtime.execution_report(),
            }
        ),
        "utf-8",
    )

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _health_wait() -> None:
        for _ in range(100):
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
