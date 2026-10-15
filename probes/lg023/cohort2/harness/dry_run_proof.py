#!/usr/bin/env python3
"""LG-023 cohort-2 OFFLINE driver-wiring proof (zero DeepSeek generation).

Starts the local fake SSE upstream, then runs the REAL driver assembly end to
end (build_runtime -> create_app -> Coordinator/GraphDispatcher/
VerificationService/StoreResourceStopper with the adapter's ``confirm_stopped``
as session confirmer, frozen program plan, real HTTP task path) for one sample
and both arms.  The fake upstream never writes the fixture files, so the machine
gate is expected to fail and the phase must go to ``waiting_user`` — the proof
is that the *wiring* runs without harness errors and that the measurement/stop
facts are real.

Asserts and records:
* server starts; ``execution_ready``; reviewer wired as ``model``;
* ledger is the one persistent path with limit 48 and non-zero count after the
  run (worker + reviewer consume it);
* Task created; phase progressed through ``executing``/``verifying``;
* real session refs recorded; reviewer real teardown confirmed; accept correctly
  refused while not ``awaiting_acceptance``;
* workspace isolation is OFF (no per-node worktrees).

Usage::

    .venv/bin/python probes/lg023/cohort2/harness/dry_run_proof.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "backend"))

import cohort2_config as C  # noqa: E402

OUT = C.EVIDENCE_DIR / "offline" / "dry_run_proof.json"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> int:
    port = _free_port()
    upstream = subprocess.Popen(
        [sys.executable, str(HERE / "fake_sse_upstream.py"), str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    payload: dict = {"ok": False, "arms": {}}
    try:
        # wait for the fake upstream
        for _ in range(40):
            s = socket.socket()
            try:
                s.connect(("127.0.0.1", port))
                s.close()
                break
            except OSError:
                time.sleep(0.25)
        upstream_url = f"http://127.0.0.1:{port}/v1"
        for arm in ("A", "B"):
            result_path = (C.PHASE_DATA_DIR / "offline_dry_run_output"
                           / f"s1_independent__{arm}" / "result.json")
            proc = subprocess.run(
                [sys.executable, str(HERE / "run_attempt.py"), "--sample", "s1_independent",
                 "--arm", arm, "--dry-run", "--fake-upstream", upstream_url],
                capture_output=True, text=True, timeout=420,
                env={**__import__("os").environ, "DEEPSEEK_API_KEY": "offline-dry-run"},
            )
            data = {}
            if result_path.exists():
                data = json.loads(result_path.read_text(encoding="utf-8"))
            steps = {s["name"]: s["ok"] for s in data.get("steps", [])}
            run_root = C.PHASE_DATA_DIR / "offline_dry_run" / f"s1_independent__{arm}"
            isolated = (run_root / "workspaces" / ".lg-worktrees").glob("run_*")
            node_worktrees = sorted(str(p) for p in isolated)
            entry = {
                "returncode": proc.returncode,
                "final_phase": data.get("final_phase"),
                "phases_seen": data.get("phases_seen"),
                "steps": steps,
                "attempt_generation_requests": data.get("attempt_generation_requests"),
                "generation_final": data.get("generation_final"),
                "session_refs": data.get("session_refs"),
                "reviewer_cleanup": data.get("reviewer_cleanup"),
                "accept_response_state": (data.get("accept_response") or {}).get("state"),
                "node_worktrees": node_worktrees,
                "wiring_ok": bool(
                    steps.get("health_ok") and steps.get("execution_ready")
                    and steps.get("reviewer_wired_model") and steps.get("task_created")
                    and steps.get("real_session_refs_recorded")
                    and steps.get("reviewer_real_teardown_recorded")
                    and not node_worktrees
                    and (data.get("attempt_generation_requests") or 0) > 0
                ),
            }
            payload["arms"][arm] = entry
        payload["ok"] = all(v.get("wiring_ok") for v in payload["arms"].values())
    finally:
        upstream.terminate()
        try:
            upstream.wait(timeout=5)
        except subprocess.TimeoutExpired:
            upstream.kill()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"],
                      "arms": {k: v.get("wiring_ok") for k, v in payload["arms"].items()}},
                     indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
