#!/usr/bin/env python3
"""LG-050 QA browser harness server.

Serves the *candidate* built frontend (`frontend/dist`) together with the real
team-mode API on a throwaway loopback port and data root.  Used by
``qa_browser_e2e.mjs`` through ``run_browser_e2e.sh``.

No real model, no .env, no existing data root.
"""

from __future__ import annotations

import argparse
import socket
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402

from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.runtime.frontend import mount_frontend  # noqa: E402
from lightgravity.team import TeamAccounts  # noqa: E402

QA_PASSWORD = "qa-throwaway-pass-123!"  # QA fixture only


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--frontend-dist", default=None)
    parser.add_argument("--ttl", type=int, default=3600)
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else Path(tempfile.mkdtemp(prefix="lg050-browser-"))
    data_dir.mkdir(parents=True, exist_ok=True)
    accounts = TeamAccounts(data_dir / "team" / "accounts.json")
    if not accounts.exists():
        accounts.add("alice", QA_PASSWORD, "admin")
        accounts.add("bob", QA_PASSWORD, "member")

    settings = Settings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=data_dir.parent / (data_dir.name + "-secrets"),
        team_mode=True,
        team_session_ttl_seconds=args.ttl,
    )
    app = create_app(settings)
    dist = Path(args.frontend_dist).resolve() if args.frontend_dist else Path(__file__).resolve().parents[3] / "frontend" / "dist"
    mounted = mount_frontend(app, dist, "", log=lambda m: print(f"# {m}", file=sys.stderr))
    if not mounted:
        print(f"FATAL frontend build missing at {dist}", file=sys.stderr)
        return 2

    port = args.port
    if port == 0:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    print(f"READY http://127.0.0.1:{port} data={data_dir}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
