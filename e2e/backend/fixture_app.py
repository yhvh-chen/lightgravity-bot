#!/usr/bin/env python3
"""Isolated real backend + SPA fixture for the LG-055 Playwright harness.

This is **test setup**, not a product entry point.  It:

* builds the real FastAPI app with a fresh temp data/workspace/secret root;
* seeds fixed, fake team accounts (admin/alice/bob) with real password hashes;
* injects a deterministic direct-answer responder so no product model is ever
  called (the harness must run without credentials);
* mounts the real built frontend at the same origin so the browser hits one
  real HTTP server (real routes, real file/JSONL persistence — no mocked APIs
  and no static HTML shell);
* is killed and its temp root removed by the Node launcher on teardown.

Run manually::

    PYTHONPATH=backend python3 e2e/backend/fixture_app.py \
        --mode team --port 8791 --data-dir /tmp/lg-e2e --dist frontend/dist
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Fixed, non-secret test credentials (fake accounts created at fixture startup).
TEST_ACCOUNTS = {
    "admin": ("lg-admin-test-pw", "admin"),
    "alice": ("lg-alice-test-pw", "member"),
    "bob": ("lg-bob-test-pw", "member"),
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("team", "single", "stale"), default="team")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--dist", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    return parser.parse_args(argv)


def _mount_frontend(app: Any, dist: str) -> None:
    from lightgravity.runtime.frontend import mount_frontend

    resolved = Path(dist).resolve()
    if not mount_frontend(app, resolved, token=""):
        raise SystemExit(
            f"frontend build not found at {resolved}; run the frontend build first"
        )


def _build_stale_app(args: argparse.Namespace) -> Any:
    """A deliberately outdated backend (contract 1.0.0, no auth/capabilities).

    Exercises the frontend's explicit ``backend_incompatible`` failure state
    over real HTTP, never a mocked browser response.
    """

    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "package_version": "0.1.0",
            "contract_version": "1.0.0",
            "schema_version": "lightgravity.bot/v1",
            "capabilities": {},
        }

    @app.get("/api/v1/version")
    def version() -> dict[str, Any]:
        return {
            "contract_version": "1.0.0",
            "schema_version": "lightgravity.bot/v1",
            "package_version": "0.1.0",
            "python_version": "3.12.0",
            "platform": "test",
        }

    _mount_frontend(app, args.dist)
    return app


def _build_app(args: argparse.Namespace) -> Any:
    from lightgravity.api.app import create_app
    from lightgravity.config import Settings
    from lightgravity.team import TeamAccounts

    data_dir = Path(args.data_dir)
    settings = Settings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=data_dir / "secrets",
        team_mode=args.mode == "team",
    )
    if args.mode == "team":
        accounts = TeamAccounts(settings.team_accounts_path)
        for username, (password, role) in TEST_ACCOUNTS.items():
            if accounts.get(username) is None:
                accounts.add(username, password, role)

    def responder(content: str, _classification: Any) -> str:
        # Deterministic, model-free reply used only by the acceptance harness.
        return f"[deterministic-test-responder] {content}"

    app = create_app(settings, responder=responder)
    _mount_frontend(app, args.dist)
    return app


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.mode == "stale":
        app = _build_stale_app(args)
    else:
        app = _build_app(args)

    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
