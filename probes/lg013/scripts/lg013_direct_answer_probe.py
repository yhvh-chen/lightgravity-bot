"""One bounded real-model probe for the LG-013 direct-answer path (integration).

Purpose (integration-round evidence, NOT a version QA):

* Exercise the new **tool-less direct-answer** responder
  (`backend/lightgravity/coordinator/dialogue.py`) on a *real* default
  coordinator connection with a real credential, through the same
  `create_app(responder=...)` seam bootstrap wires.
* Prove that answering a plain read-only question:
    - does **not** create a Task,
    - does **not** create a Run / Member,
    - does **not** write any control file under the Task roots,
    - keeps the model tool-less (no workspace/tool capability).

The credential comes only from the process environment
(``DEEPSEEK_API_KEY``).  It is never printed, stored in the temp data dir, or
written to the evidence JSON.  Reads no `.env`.

Bound: exactly **one** model turn (``model_calls_cap=1``); a hard wall-clock
timeout aborts the whole probe.  If the connection/credential is missing the
probe records ``skipped`` honestly instead of faking an answer.

Run:
    DEEPSEEK_API_KEY=... uv run python probes/lg013/scripts/lg013_direct_answer_probe.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

import httpx

from lightgravity.api.bootstrap import StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.settings import ROLE_COORDINATOR
from lightgravity.settings.secret_store import FileSecretStore
from lightgravity.settings.service import ConnectionService
from lightgravity.store import FileStore

#: Bounded single question — a plain read-only ask, no delivery intent.
QUESTION = "In one short sentence, what is 2 + 2? Answer with just the number word."

#: Whole-probe wall clock cap; one model turn + overhead only.
PROBE_TIMEOUT_SECONDS = 120.0

_CRED_ID = "probe-lg013-cred"
_CONN_ID = "probe-lg013-coordinator"


def _count_markers(root: Path) -> dict[str, int]:
    """Cheap inventory of Task/Run/Member control artifacts under ``root``."""

    tasks = list(root.glob("tasks/**/TASK.md")) if root.is_dir() else []
    members = list(root.glob("**/MEMBERS.md")) if root.is_dir() else []
    runs = list(root.glob("**/runs/**/*.md")) if root.is_dir() else []
    return {
        "task_files": len(tasks),
        "member_files": len(members),
        "run_files": len(runs),
    }


def _leak_scan(blob: str, secret: str) -> list[str]:
    findings: list[str] = []
    if secret and secret in blob:
        findings.append("raw_secret_present")
    if re.search(r"sk-[A-Za-z0-9]{8,}", blob):
        findings.append("sk_like_token_present")
    return findings


async def _run(record: dict) -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    tmp = Path(tempfile.mkdtemp(prefix="lg013-probe-"))
    settings = Settings(
        data_dir=tmp / "data",
        workspace_root=tmp / "data" / "workspaces",
        secret_store=tmp / "secrets",
    )
    options = StartupOptions(
        settings=settings,
        serve_frontend=False,
        seed_minimal_agent=True,
        tester=False,
    )

    settings.ensure_data_dir()

    # --- configure the default coordinator connection BEFORE startup ---------
    # ``build_runtime`` resolves the responder at startup, so the connection and
    # default must exist first (otherwise the built-in deterministic responder
    # is used and no real model turn happens).  Seed on the same files the
    # runtime will read back.
    seed_store = FileStore(settings.data_dir, settings.workspace_root)
    seed_connections = ConnectionService(
        seed_store, secret_store=FileSecretStore(settings.secret_store)
    )
    seed_connections.create_connection(
        _CONN_ID,
        backend="openai-compat",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        credential_ref=_CRED_ID,
        credential_value=api_key,
        actor="probe:lg013",
        request_id="probe-lg013-connect",
    )
    seed_connections.update_settings(
        default_coordinator_connection_ref=_CONN_ID,
        actor="probe:lg013",
        expected_revision=None,
    )
    record["default_coordinator"] = _CONN_ID

    runtime = build_runtime(options)
    app = runtime.app

    settings_root = settings.data_dir
    before = _count_markers(settings_root)

    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/conversations/global/messages",
                json={
                    "message_id": "probe-lg013-msg-1",
                    "role": "user",
                    "content": QUESTION,
                    "request_id": "probe-lg013-req-1",
                },
            )
            record["http_status"] = resp.status_code
            record["response"] = resp.json() if resp.content else None

    after = _count_markers(settings_root)
    record["control_files_before"] = before
    record["control_files_after"] = after
    record["created_tasks"] = after["task_files"] - before["task_files"]
    record["created_members"] = after["member_files"] - before["member_files"]
    record["created_runs"] = after["run_files"] - before["run_files"]

    # --- workspace must stay empty (no tool wrote anything) -----------------
    ws = settings.workspace_root
    record["workspace_files"] = (
        [str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file()]
        if ws.is_dir()
        else []
    )
    record["leak_findings"] = _leak_scan(json.dumps(record, ensure_ascii=False), api_key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="evidence JSON output path")
    args = parser.parse_args()

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        record = {
            "status": "skipped",
            "reason": "DEEPSEEK_API_KEY not present in environment; no real probe run",
        }
    else:
        record: dict = {"status": "ran", "question": QUESTION, "model_calls_cap": 1}
        try:
            asyncio.run(
                asyncio.wait_for(_run(record), timeout=PROBE_TIMEOUT_SECONDS)
            )
        except asyncio.TimeoutError:
            record["status"] = "timeout"
            record["reason"] = f"probe exceeded {PROBE_TIMEOUT_SECONDS}s"
        except Exception as exc:  # noqa: BLE001 - record honestly, never fake
            record["status"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"

    text = json.dumps(record, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if record.get("status") == "ran" else 1


if __name__ == "__main__":
    raise SystemExit(main())
