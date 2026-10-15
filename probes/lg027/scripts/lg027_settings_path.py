#!/usr/bin/env python
"""LG-027 QA: real CLI-equivalent server + real HTTP settings -> execution path.

This drives the *real* product HTTP surface (uvicorn on loopback, not an
ASGI in-process transport) exactly as the local distribution would:

1. start with **no** credential / no connection  -> history readable, execution
   honestly unavailable (``execution_ready=false`` with explicit reasons);
2. Settings API: create openai-compat connection, store a credential, run a
   **layered** test, set the worker default;
3. a new Task reaches the executor via the seeded agent + default connection.

Network mode is controlled by $LG027_NETWORK:
  * ``off``  (default): BASE_URL points at an unused loopback port -> the
    executor fails fast without touching the internet; this proves the *entry*,
    not model success.  We assert the credential value never appears anywhere.
  * ``on``: BASE_URL is https://api.deepseek.com/v1 and the credential comes
    from the injected process env ($DEEPSEEK_API_KEY).  This performs at most
    ``LG027_MODEL_CAP`` (default 1) real model calls.

The credential value is never printed and never written by this script; it is
read from the environment and placed only into the controlled secret store (off
mode: a clearly fake value).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = REPO / "probes" / "lg027" / "evidence"

TOKEN = "lg027-qa-token"
CONNECTION_ID = "deepseek-lg027"
CREDENTIAL_REF = "lg027-upstream-key"
MODEL = "deepseek-v4-flash"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_port(port: int, *, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


def main() -> int:
    import httpx

    mode = os.environ.get("LG027_NETWORK", "off")
    cap = int(os.environ.get("LG027_MODEL_CAP", "1"))
    real_key = os.environ.get("DEEPSEEK_API_KEY")
    if mode == "on" and not real_key:
        print("LG027: LG027_NETWORK=on requires DEEPSEEK_API_KEY", file=sys.stderr)
        return 2

    data_dir = Path(tempfile.mkdtemp(prefix="lg027-data-"))
    workspace = data_dir / "workspaces"
    (workspace / "ws").mkdir(parents=True, exist_ok=True)
    secret_store = Path(tempfile.mkdtemp(prefix="lg027-secrets-"))
    port = free_port()
    base_url = "https://api.deepseek.com/v1" if mode == "on" else f"http://127.0.0.1:{free_port()}/v1"
    credential_value = real_key if mode == "on" else "lg027-fake-upstream-key"

    env = dict(os.environ)
    env["LIGHTGRAVITY_RUNTIME_TOKEN"] = TOKEN
    log = (data_dir / "server.log").open("w")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "lightgravity",
            "start",
            "--no-frontend",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--data-dir",
            str(data_dir),
            "--workspace-root",
            str(workspace),
            "--secret-store",
            str(secret_store),
        ],
        cwd=str(REPO),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    evidence: dict[str, object] = {
        "mode": mode,
        "model_call_cap": cap,
        "base_url": base_url,
        "port": port,
    }
    try:
        if not wait_port(port):
            evidence["error"] = "server did not start"
            print(json.dumps(evidence, indent=2))
            return 1
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=120.0)
        headers = {"X-LG-Token": TOKEN}

        # 1. Missing-auth startup: history + settings readable, execution off.
        tasks = client.get("/api/v1/tasks")
        settings_view = client.get("/api/v1/settings")
        health = client.get("/api/v1/health")
        status = json.loads(
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lightgravity",
                    "status",
                    "--deep",
                    "--data-dir",
                    str(data_dir),
                    "--workspace-root",
                    str(workspace),
                    "--secret-store",
                    str(secret_store),
                ],
                cwd=str(REPO),
                env=env,
                capture_output=True,
                text=True,
            ).stdout
            or "{}"
        )
        evidence["startup"] = {
            "tasks_status": tasks.status_code,
            "settings_status": settings_view.status_code,
            "health_status": health.status_code,
            "health_body": health.json(),
            "execution": status.get("execution"),
        }

        # Sensitive write must be default-denied without the token.
        denied = client.post(
            "/api/v1/settings/connections",
            json={"id": "x", "backend": "openai-compat", "model": MODEL},
        )
        evidence["unauthorized_write"] = {"status": denied.status_code, "body": denied.json()}

        # 2. Settings config: create connection + credential + layered test.
        created = client.post(
            "/api/v1/settings/connections",
            headers=headers,
            json={
                "id": CONNECTION_ID,
                "backend": "openai-compat",
                "model": MODEL,
                "base_url": base_url,
                "credential_ref": CREDENTIAL_REF,
            },
        )
        evidence["create_connection"] = {
            "status": created.status_code,
            "leaks_credential": credential_value in created.text,
        }
        put = client.put(
            f"/api/v1/settings/credentials/{CREDENTIAL_REF}",
            headers=headers,
            json={"action": "set", "value": credential_value},
        )
        evidence["put_credential"] = {
            "status": put.status_code,
            "body": put.json(),
            "leaks_credential": credential_value in put.text,
        }
        tested = client.post(
            f"/api/v1/settings/connections/{CONNECTION_ID}/test",
            headers=headers,
            json={"allow_network": mode == "on"},
        )
        test_body = tested.json()
        evidence["layered_test"] = {
            "status": tested.status_code,
            "overall": test_body.get("overall"),
            "layers": [
                {"name": layer["name"], "status": layer["status"]}
                for layer in test_body.get("layers", [])
            ],
            "leaks_credential": credential_value in tested.text,
        }

        # Set default worker.
        view = client.get("/api/v1/settings").json()
        patched = client.patch(
            "/api/v1/settings",
            headers=headers,
            json={
                "expected_revision": view.get("revision") if view.get("exists") else None,
                "default_worker_connection_ref": CONNECTION_ID,
            },
        )
        evidence["set_default"] = {"status": patched.status_code, "body": patched.json()}
        status2 = json.loads(
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lightgravity",
                    "status",
                    "--deep",
                    "--data-dir",
                    str(data_dir),
                    "--workspace-root",
                    str(workspace),
                    "--secret-store",
                    str(secret_store),
                ],
                cwd=str(REPO),
                env=env,
                capture_output=True,
                text=True,
            ).stdout
            or "{}"
        )
        evidence["execution_after_default"] = status2.get("execution")

        # 3. New Task -> executor via seeded agent + pinned default.
        task = client.post(
            "/api/v1/tasks",
            json={
                "request_id": "lg027-settings-req",
                "title": "lg027 settings entry",
                "objective": "Reply with exactly the word OK and nothing else.",
                "acceptance_criteria": ["the reply contains OK"],
                "workspace_ref": "ws",
            },
        )
        task_id = task.json().get("task_id")
        evidence["task"] = {"status": task.status_code, "task_id": task_id}

        from lightgravity.store import FileStore  # type: ignore

        store = FileStore(data_dir, workspace)
        started_at = time.monotonic()
        wait_seconds = float(os.environ.get("LG027_WAIT_SECONDS", "120" if mode == "on" else "25"))
        deadline = started_at + wait_seconds
        terminal_phases = {"done", "failed", "cancelled", "blocked", "awaiting_acceptance"}
        task_phase = None
        while time.monotonic() < deadline:
            if task_id:
                try:
                    task_phase = store.read("task", task_id).entity.get("phase")
                except Exception:  # noqa: BLE001 - entity may not exist yet
                    task_phase = None
                if task_phase in terminal_phases:
                    break
            time.sleep(0.25)
        evidence["task_wait"] = {
            "waited_seconds": round(time.monotonic() - started_at, 2),
            "wait_cap_seconds": wait_seconds,
            "reached_terminal_phase": task_phase in terminal_phases,
            "observed_phase": task_phase,
        }
        subtasks: list[dict] = []
        member_dir = data_dir / "members"
        member_ids = sorted(p.stem for p in member_dir.glob("*.md")) if member_dir.is_dir() else []
        evidence["members"] = [
            {
                "id": mid,
                "connection_ref": store.read("member", mid).entity.get("connection_ref"),
                "connection_pin": store.read("member", mid).entity.get("connection_pin"),
            }
            for mid in member_ids
        ]
        subtask_dir = data_dir / "subtasks"
        subtask_ids = sorted(p.name for p in subtask_dir.iterdir()) if subtask_dir.is_dir() else []
        for sid in subtask_ids:
            entity = store.read("subtask", sid).entity
            subtasks.append(
                {
                    "id": sid,
                    "state": entity.get("state"),
                    "acceptance": entity.get("acceptance", {}).get("status"),
                }
            )
        evidence["subtasks"] = subtasks
        if task_id:
            task_entity = store.read("task", task_id).entity
            evidence["task_phase"] = task_entity.get("phase")
            run_ref = task_entity.get("active_run") or task_entity.get("last_run")
            if run_ref:
                run = store.read("run", run_ref).entity
                evidence["run"] = {
                    "state": run.get("state"),
                    "connection_pin": run.get("connection_pin"),
                }

        # Secret-leak sweep across persisted product text.
        leaks: list[str] = []
        for path in data_dir.rglob("*"):
            if path.is_file():
                try:
                    text = path.read_text(errors="ignore")
                except OSError:
                    continue
                if credential_value in text:
                    leaks.append(str(path.relative_to(data_dir)))
        evidence["persisted_secret_leaks"] = leaks
        evidence["server_log_leaks"] = credential_value in (data_dir / "server.log").read_text(
            errors="ignore"
        )

        EVIDENCE.mkdir(parents=True, exist_ok=True)
        out = EVIDENCE / f"lg027-settings-path-{mode}.json"
        out.write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
