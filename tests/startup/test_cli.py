"""Real start / status / stop of the local service as a subprocess (LG-020).

This is intentionally a real process test: it starts ``python -m lightgravity
start`` on an ephemeral loopback port with temporary data/workspace/secret dirs,
verifies the health endpoint, then stops it through the pid record and checks
the process is gone and the record removed.  No model call is made.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from lightgravity.runtime.pidfile import read_record

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lightgravity", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_start_status_stop_roundtrip(tmp_path: Path) -> None:
    port = _free_port()
    data_dir = tmp_path / "data"
    workspace_root = tmp_path / "workspaces"
    secret_store = tmp_path / "secrets"
    base_url = f"http://127.0.0.1:{port}"

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
            "--no-frontend",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        health = _wait_health(base_url, timeout=40)
        assert health["status"] == "ok"
        assert health["capabilities"]["sdk_adapter"] is True

        record = read_record(data_dir)
        assert record is not None
        assert record.pid == process.pid
        assert record.port == port

        status = _cli("status", "--data-dir", str(data_dir), "--secret-store", str(secret_store))
        assert status.returncode == 0, status.stderr
        payload = json.loads(status.stdout)
        assert payload["running"] is True
        assert payload["pid"] == process.pid
        assert payload["health"]["status"] == "ok"

        stop = _cli("stop", "--data-dir", str(data_dir), "--secret-store", str(secret_store))
        assert stop.returncode == 0, stop.stderr
        stopped = json.loads(stop.stdout)
        assert stopped["stopped"] is True

        process.wait(timeout=20)
        assert process.poll() is not None
        assert read_record(data_dir) is None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_status_without_running_instance(tmp_path: Path) -> None:
    result = _cli(
        "status",
        "--data-dir",
        str(tmp_path / "data"),
        "--secret-store",
        str(tmp_path / "secrets"),
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["running"] is False
    assert payload["pid"] is None
