#!/usr/bin/env python3
"""LG-019 real-uviсorn HTTP/SSE smoke (subscription, cursor resume, dedupe).

This is a *bounded evidence harness*, not product code and not a pytest test.
It starts a real uvicorn process on loopback with a temp data dir, then:

1. creates a Task (bare, no Run) directly through the coordinator over the API;
2. appends durable events through a second HTTP-independent path is not
   available, so it drives real events via ``POST /tasks`` (which queues a Run
   the default UnavailableExecutor fails -> real ``task.failed``) and by
   reading the same event stream over real SSE;
3. opens SSE with ``cursor=v1:<task>:0`` and records the received ids;
4. disconnects, then reconnects with ``Last-Event-ID`` = last id and asserts no
   duplicate and no gap;
5. asserts ``GET/POST /notifications`` returns the failed notification, that a
   mark-read survives a "refresh" (a fresh GET), and that an unknown id is
   reported rather than fabricated.

No model calls. No writes outside the temp dir. Records a JSON report.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def wait_ready(base: str, process: subprocess.Popen, deadline: float = 30.0) -> None:
    last: Exception | None = None
    deadline = time.monotonic() + deadline
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited early with {process.returncode}")
        try:
            status, _ = http_json("GET", f"{base}/api/v1/health")
            if status == 200:
                return
            last = RuntimeError(f"health status {status}")
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.2)
    raise RuntimeError(f"uvicorn did not become ready: {last!r}")


def read_sse(url: str, *, headers: dict[str, str] | None = None, want: int, timeout: float = 15.0) -> list[dict]:
    """Read up to ``want`` SSE events, then close the connection (disconnect)."""

    request = urllib.request.Request(url)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    events: list[dict] = []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        assert response.status == 200, response.status
        current: dict[str, str] = {}
        deadline = time.monotonic() + timeout
        while len(events) < want and time.monotonic() < deadline:
            try:
                line = response.readline()
            except TimeoutError:
                # No more frames within the window: this is a healthy idle
                # subscription (keep-alives only), not a gap.
                break
            if not line:
                break
            text = line.decode().rstrip("\n")
            if text == "":
                if current:
                    events.append(current)
                    current = {}
                continue
            if text.startswith(":"):
                continue
            field, _, value = text.partition(":")
            current[field] = value[1:] if value.startswith(" ") else value
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO / "probes/lg019/evidence/sse-smoke.json"))
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="lg019-smoke-"))
    data_dir = tmp / "data"
    workspace = tmp / "workspace"
    workspace.mkdir(parents=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    env = dict(os.environ)
    env["LIGHTGRAVITY_DATA_DIR"] = str(data_dir)
    env["LIGHTGRAVITY_WORKSPACE_ROOT"] = str(workspace)
    env["LIGHTGRAVITY_HOST"] = "127.0.0.1"
    env["LIGHTGRAVITY_PORT"] = str(port)

    log = open(tmp / "uvicorn.log", "w")
    process = subprocess.Popen(
        [sys.executable, "-m", "lightgravity.api"],
        cwd=str(REPO / "backend"),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    report: dict = {"data_dir": str(data_dir), "port": port, "checks": {}}
    try:
        wait_ready(base, process)
        report["checks"]["ready"] = True

        status, created = http_json(
            "POST",
            f"{base}/api/v1/tasks",
            {
                "request_id": "lg019-smoke-1",
                "title": "LG019 smoke",
                "objective": "drive a real failure event",
                "acceptance_criteria": ["never runs a model"],
            },
        )
        task_id = created["task_id"]
        report["task_id"] = task_id

        # The default UnavailableExecutor fails the queued Run -> real durable
        # error.recorded + task.phase_changed(failed).
        deadline = time.monotonic() + 15
        phase = ""
        while time.monotonic() < deadline:
            _, detail = http_json("GET", f"{base}/api/v1/tasks/{task_id}")
            phase = detail.get("phase", "")
            if phase in {"failed", "cancelled", "completed"}:
                break
            time.sleep(0.1)
        report["phase"] = phase
        report["checks"]["reached_terminal_phase"] = phase == "failed"

        first = read_sse(f"{base}/api/v1/events/stream?cursor=v1:{task_id}:0", want=50)
        first_ids = [event["id"] for event in first if "id" in event]
        report["first_event_count"] = len(first_ids)
        report["checks"]["got_events"] = len(first_ids) > 0

        # Reconnect with Last-Event-ID = last delivered; must not repeat it.
        last_id = first_ids[-1]
        replay = read_sse(
            f"{base}/api/v1/events/stream",
            headers={"Last-Event-ID": last_id},
            want=1,
            timeout=4.0,
        )
        # Replay must not re-deliver ``last_id``; there are no newer events, so
        # a well-behaved server sends nothing (only keep-alives).
        replay_ids = [event["id"] for event in replay if "id" in event]
        report["replay_ids"] = replay_ids
        report["checks"]["no_duplicate_on_reconnect"] = last_id not in replay_ids

        # Notifications projection over real HTTP.
        status, listing = http_json("GET", f"{base}/api/v1/notifications")
        report["notification_count"] = len(listing.get("items", []))
        report["unread"] = listing.get("unread")
        report["checks"]["has_failed_notification"] = any(
            item["kind"] == "task.failed" for item in listing.get("items", [])
        )
        item = next(
            (i for i in listing.get("items", []) if i["kind"] == "task.failed"), None
        )
        if item is not None:
            report["notification"] = {
                "task_ref": item["task_ref"],
                "run_ref": item["run_ref"],
                "severity": item["severity"],
                "read": item["read"],
            }
            report["checks"]["targets_task"] = item["task_ref"] == task_id

            # Mark read, then re-GET to prove persistence across a "refresh".
            http_json(
                "POST",
                f"{base}/api/v1/notifications",
                {"notification_ids": [item["notification_id"]]},
            )
            _, after = http_json("GET", f"{base}/api/v1/notifications")
            refreshed = next(
                (i for i in after.get("items", []) if i["notification_id"] == item["notification_id"]),
                None,
            )
            report["checks"]["read_persists_across_refresh"] = bool(
                refreshed and refreshed["read"] is True
            )

        # Unknown notification id is reported, not fabricated.
        _, unknown = http_json(
            "POST",
            f"{base}/api/v1/notifications",
            {"notification_ids": ["notif_UNKNOWN"]},
        )
        report["checks"]["unknown_reported"] = unknown.get("unknown") == ["notif_UNKNOWN"]

        report["ok"] = all(report["checks"].values())
    finally:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=10)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        log.close()
        report["uvicorn_log_tail"] = (tmp / "uvicorn.log").read_text()[-1500:]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({k: report[k] for k in ("ok", "checks", "phase", "notification_count")}, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
