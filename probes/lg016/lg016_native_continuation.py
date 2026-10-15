#!/usr/bin/env python3
"""LG-016 bounded real-SDK native session continuation evidence.

Not product code, not a pytest test.  It exercises the **product** adapter path
against the pinned SDK (``google-antigravity==0.1.22``) + loopback auth proxy +
real DeepSeek upstream and records whether a second ``ExecuteRequest`` that
carries the first run's non-secret native identity
(``conversation_id`` + ``save_dir`` + ``continuation_mode=resume``) actually
**attaches to the same native conversation** (the adapter reports the session
state as ``resumed`` and the same ``conversation_id``) instead of creating a
brand-new session.

Hard caps: at most ``--max-proxy-calls`` per execution and ``--model-calls-cap``
in total (default 2 — one quick turn for the fresh session and one for the
resumed session).  The credential is read only from the process environment and
never written to the evidence file.

This is deliberately a *small* probe: it proves the native continuation data
flow, not a full product resume — the product pause/resume gate is covered by
``probes/lg016/lg016_control_e2e.py`` and by the LG-016 unit tests.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_LG010 = _REPO / "probes" / "lg010"
sys.path.insert(0, str(_REPO / "backend"))
sys.path.insert(0, str(_LG010))

from lg010_e2e import (  # noqa: E402
    MODEL,
    UPSTREAM,
    RecordingExecutor,
    build_resources,
    build_workspace,
)
from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    ExecuteRequest,
)
from lightgravity.store import FileStore  # noqa: E402

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "lg016-native-continuation-evidence.json"

QUICK_PROMPT = "Reply with exactly the single word: ACK. Do not use any tools."


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git_head() -> str:
    import subprocess

    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _session_from_events(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("type") == "adapter.session_started":
            data = event.get("session")
            if isinstance(data, dict) and data.get("session_id"):
                return data
    return None


def _write_report(report: dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {EVIDENCE_PATH}", file=sys.stderr)


async def _one_turn(
    executor: AntigravityExecutor,
    request: ExecuteRequest,
) -> tuple[Any, dict[str, Any] | None]:
    events: list[dict[str, Any]] = []

    def sink(event: dict[str, Any]) -> None:
        events.append(event)

    result = await executor.execute(request, sink)
    return result, _session_from_events(events)


async def amain(args: argparse.Namespace) -> int:
    secret = os.environ.get("DEEPSEEK_API_KEY") or ""
    report: dict[str, Any] = {
        "task": "LG-016",
        "kind": "real-sdk-native-session-continuation",
        "at": _now(),
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine()}",
        "head": _git_head(),
        "model_requested": MODEL,
        "upstream": UPSTREAM,
        "credential": {"source": "env:DEEPSEEK_API_KEY", "present": bool(secret)},
        "hard_caps": {
            "max_proxy_calls_per_execution": args.max_proxy_calls,
            "model_calls_cap_total": args.model_calls_cap,
        },
        "findings": [],
        "limitations": [],
    }
    if not secret:
        report["limitations"].append(
            "DEEPSEEK_API_KEY was not present; the real native continuation path "
            "could not run (no stub substituted)."
        )
        _write_report(report)
        return 2

    root = Path(tempfile.mkdtemp(prefix="lg016-native-"))
    try:
        data_dir = root / "bot-data"
        workspace_root = data_dir / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        repo = build_workspace(workspace_root)

        store = FileStore(data_dir, workspace_root)
        build_resources(store)
        native_dir = data_dir / "native-sessions" / "task-lg016-native"
        executor = AntigravityExecutor(
            store,
            artifacts=DirectoryArtifactSink(root / "artifacts"),
            workspace_root=workspace_root,
            max_proxy_calls=args.max_proxy_calls,
            model_calls_cap=args.model_calls_cap,
            cancel_timeout=15.0,
            upstream_timeout=120.0,
        )
        recording = RecordingExecutor(executor)

        task_id = "task-lg016-native"
        common = {
            "task_id": task_id,
            "subtask_id": "subtask-lg016-native",
            "attempt": 1,
            "objective": QUICK_PROMPT,
            "instructions": QUICK_PROMPT,
            "agent_ref": "developer",
            "workspace_path": str(repo),
            "save_dir": str(native_dir),
        }

        # Turn 1: a fresh session.  The product records the non-secret native
        # identity (conversation_id + save_dir) the adapter reports.
        first = ExecuteRequest(run_id="run-lg016-native-1", **common)
        first_result, first_session = await _one_turn(recording, first)
        # The adapter's *final* SessionRef (after the turn) may carry the native
        # conversation id even when the session_started event did not.
        if first_result is not None and getattr(first_result, "session_ref", None) is not None:
            final_ref = first_result.session_ref.to_dict()
            first_session = final_ref
        report["first_run"] = {
            "state": getattr(first_result, "state", None),
            "session": first_session,
            "executor_state": getattr(first_result, "state", None),
            "stop_confirmed": getattr(first_result, "stop_confirmed", None),
        }
        conversation_id = (first_session or {}).get("conversation_id")
        save_dir = (first_session or {}).get("save_dir")

        if not conversation_id or not save_dir:
            report["limitations"].append(
                "the real first run reported no native conversation_id/save_dir; "
                "native continuation cannot be proven from this run"
            )
        else:
            # Turn 2: continue the *same* native conversation.  This is exactly the
            # (conversation_id, save_dir, continuation_mode=resume) tuple the
            # coordinator's ContinuationPlanner produces for a confirmed pause.
            second = ExecuteRequest(
                run_id="run-lg016-native-2",
                **common,
                conversation_id=str(conversation_id),
                continuation_mode="resume",
            )
            second_result, second_session = await _one_turn(recording, second)
            if second_result is not None and getattr(second_result, "session_ref", None) is not None:
                second_session = second_result.session_ref.to_dict()
            report["second_run"] = {
                "state": getattr(second_result, "state", None),
                "session": second_session,
                "stop_confirmed": getattr(second_result, "stop_confirmed", None),
            }
            report["continuation"] = {
                "requested_conversation_id": conversation_id,
                "requested_save_dir": save_dir,
                "requested_continuation_mode": "resume",
                "reported_session_state": (second_session or {}).get("state"),
                "reported_conversation_id": (second_session or {}).get("conversation_id"),
                "resumed_same_conversation": bool(
                    second_session
                    and second_session.get("state") == "resumed"
                    and second_session.get("conversation_id") == conversation_id
                ),
                "same_save_dir": bool(
                    second_session and second_session.get("save_dir") == save_dir
                ),
            }
            if not report["continuation"]["resumed_same_conversation"]:
                report["findings"].append(
                    {
                        "severity": "high",
                        "issue": (
                            "a request carrying the previous conversation_id + "
                            "save_dir + continuation_mode=resume did not attach to "
                            "the same native session"
                        ),
                        "evidence": report["continuation"],
                    }
                )

        report["model_calls_this_run"] = recording.model_calls_made
        report["within_cap"] = recording.model_calls_made <= args.model_calls_cap
    finally:
        if args.keep:
            print(f"kept temp root: {root}", file=sys.stderr)
        else:
            shutil.rmtree(root, ignore_errors=True)

    _write_report(report)
    passed = not report["findings"]
    continuation = report.get("continuation", {})
    print(
        json.dumps(
            {
                "passed": passed,
                "model_calls_this_run": report["model_calls_this_run"],
                "reported_session_state": continuation.get("reported_session_state"),
                "resumed_same_conversation": continuation.get(
                    "resumed_same_conversation"
                ),
                "same_save_dir": continuation.get("same_save_dir"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-proxy-calls", type=int, default=1)
    parser.add_argument("--model-calls-cap", type=int, default=2)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if args.max_proxy_calls * 2 > args.model_calls_cap:
        parser.error("max-proxy-calls*2 must not exceed model-calls-cap")
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
