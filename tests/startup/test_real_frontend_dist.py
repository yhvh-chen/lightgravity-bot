"""Startup/handshake against the *real* built frontend dist (LG-020 gap).

The original LG-020 report used a synthetic dist; this test mounts the actual
``npm run build`` output (gitignored) when it exists, so the handshake is proven
against the real bundle.  It skips cleanly when ``frontend/dist`` has not been
built (that is a build-environment gap, not a silent pass).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from lightgravity.api.bootstrap import (
    RuntimeState,
    StartupOptions,
    build_runtime,
    default_frontend_dist,
)
from lightgravity.runtime.pidfile import read_record
from lightgravity.runtime.token import RuntimeToken

from conftest import make_settings

TOKEN = "real-dist-token-lg020"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
async def real_dist_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    dist = default_frontend_dist()
    if not (dist / "index.html").is_file():
        pytest.skip(f"real frontend dist not built at {dist}; run `npm ci && npm run build`")
    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=make_settings(tmp_path),
            token=RuntimeToken(TOKEN, "generated"),
            frontend_dist=dist,
            serve_frontend=True,
        )
    )
    assert state.frontend_served is True
    async with state.app.router.lifespan_context(state.app):
        transport = httpx.ASGITransport(app=state.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_real_index_injects_token_and_serves_bundle(
    real_dist_client: httpx.AsyncClient,
) -> None:
    index = await real_dist_client.get("/")
    assert index.status_code == 200
    assert "__LG_RUNTIME_TOKEN__" in index.text
    assert TOKEN in index.text
    assert "no-store" in index.headers["cache-control"]

    # The real Vite bundle references a hashed asset; follow it once.
    dist = default_frontend_dist()
    assets = sorted((dist / "assets").glob("*.js"))
    assert assets, "the built dist should contain at least one JS bundle"
    asset = await real_dist_client.get(f"/assets/{assets[0].name}")
    assert asset.status_code == 200
    assert "javascript" in asset.headers["content-type"]


async def test_real_spa_deep_link_falls_back(real_dist_client: httpx.AsyncClient) -> None:
    response = await real_dist_client.get("/board/task_real")
    assert response.status_code == 200
    assert "__LG_RUNTIME_TOKEN__" in response.text


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base_url: str, *, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/v1/health", timeout=2.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ValueError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.1)
    raise AssertionError(f"service did not become healthy: {last_error}")


def test_real_dist_subprocess_start_handshake_and_stop(tmp_path: Path) -> None:
    dist = default_frontend_dist()
    if not (dist / "index.html").is_file():
        pytest.skip(f"real frontend dist not built at {dist}; run `npm ci && npm run build`")
    port = _free_port()
    data_dir = tmp_path / "data"
    secret_store = tmp_path / "secrets"
    workspace_root = tmp_path / "workspaces"
    base_url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "LIGHTGRAVITY_RUNTIME_TOKEN": TOKEN}

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "lightgravity",
            "start",
            "--data-dir",
            str(data_dir),
            "--workspace-root",
            str(workspace_root),
            "--secret-store",
            str(secret_store),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        health = _wait_health(base_url, timeout=40)
        assert health["status"] == "ok"

        with urllib.request.urlopen(base_url + "/", timeout=5.0) as response:
            html = response.read().decode("utf-8")
            assert "no-store" in response.headers.get("Cache-Control", "")
        assert "__LG_RUNTIME_TOKEN__" in html
        assert TOKEN in html  # real bundle + in-memory handshake

        request = urllib.request.Request(
            base_url + "/api/v1/settings",
            data=b"{}",
            method="PATCH",
            headers={"X-LG-Token": TOKEN, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5.0) as response:
            assert response.status == 200

        record = read_record(data_dir)
        assert record is not None and record.pid == process.pid
    finally:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "lightgravity",
                "stop",
                "--data-dir",
                str(data_dir),
                "--secret-store",
                str(secret_store),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if process.poll() is None:
            process.kill()
        process.wait(timeout=20)
        assert read_record(data_dir) is None
