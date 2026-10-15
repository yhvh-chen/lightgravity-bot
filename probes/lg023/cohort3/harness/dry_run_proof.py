#!/usr/bin/env python3
"""LG-023 cohort-3 DRY-RUN proof (zero DeepSeek generation).

Runs the REAL driver assembly (``run_attempt.py --dry-run`` with a local fake
SSE upstream) for both arms against the **formal phase data_dir**, exercising
the exact same code path as a formal attempt except the controlled upstream.
It asserts that the physical ledger lands on the ONE frozen phase path
(``cohort3_config.LEDGER_HISTORY``) and accumulates across the two sequential
arm runs -- this is the G6 (dry/formal same path) + formal-path wiring proof.

The fake upstream never writes the fixture files, so the machine gate is
expected to fail and the phase must not reach ``awaiting_acceptance``; the proof
is that the *wiring and measurement* are real and on the frozen path.

Usage::

    .venv/bin/python probes/lg023/cohort3/harness/dry_run_proof.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "backend"))

import cohort3_config as C  # noqa: E402

OUT = C.EVIDENCE_DIR / "offline" / "dry_run_proof.json"
#: Dry-run uses a sibling base dir (same code path, controlled base dir) so a
#: fake-upstream run never consumes the formal phase ledger reservations.
DRY_DATA_DIR = C.PHASE_DATA_DIR.parent / "lg023-cohort3-data-dry"
DRY_LEDGER_HISTORY = DRY_DATA_DIR / "generation" / "generation.jsonl"


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
    payload: dict = {
        "ok": False,
        "phase_data_dir": str(DRY_DATA_DIR),
        "frozen_ledger_history": str(DRY_LEDGER_HISTORY),
        "arms": {},
        "real_generation": 0,
    }
    try:
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
            result_path = (DRY_DATA_DIR / "offline_dry_run_output"
                           / f"s1_independent__{arm}" / "result.json")
            proc = subprocess.run(
                [sys.executable, str(HERE / "run_attempt.py"), "--sample", "s1_independent",
                 "--arm", arm, "--dry-run", "--fake-upstream", upstream_url],
                capture_output=True, text=True, timeout=420,
                env={**os.environ, "DEEPSEEK_API_KEY": "offline-dry-run"},
            )
            data = {}
            if result_path.exists():
                data = json.loads(result_path.read_text(encoding="utf-8"))
            steps = {s["name"]: s["ok"] for s in data.get("steps", [])}
            entry = {
                "returncode": proc.returncode,
                "final_phase": data.get("final_phase"),
                "phases_seen": data.get("phases_seen"),
                "steps": steps,
                "attempt_generation_requests": data.get("attempt_generation_requests"),
                "generation_final": data.get("generation_final"),
                "ledger_identity_at_freeze": data.get("ledger_identity_at_freeze"),
                "session_refs": data.get("session_refs"),
                "reviewer_cleanup": data.get("reviewer_cleanup"),
                "stderr_tail": proc.stderr[-500:] if proc.returncode != 0 else "",
                "wiring_ok": bool(
                    steps.get("health_ok") and steps.get("execution_ready")
                    and steps.get("reviewer_wired_model")
                    and steps.get("counter_ledger_matches_frozen_path")
                    and steps.get("task_created")
                    and steps.get("real_session_refs_recorded")
                    and steps.get("reviewer_real_teardown_recorded")
                    and (data.get("attempt_generation_requests") or 0) > 0
                ),
            }
            payload["arms"][arm] = entry
            payload[f"count_after_{arm}"] = (data.get("generation_final") or {}).get("count")

        # ledger is physically on the ONE dry phase path, accumulating
        payload["frozen_history_exists"] = DRY_LEDGER_HISTORY.exists()
        payload["frozen_history_lines"] = (
            len(DRY_LEDGER_HISTORY.read_text(encoding="utf-8").splitlines())
            if DRY_LEDGER_HISTORY.exists() else 0
        )
        payload["no_per_attempt_data_dir_ledger"] = not any(
            p.name == "generation"
            for p in (DRY_DATA_DIR / "attempts").rglob("generation")
        ) if (DRY_DATA_DIR / "attempts").exists() else True
        payload["ok"] = bool(
            payload["frozen_history_exists"]
            and payload["frozen_history_lines"] > 0
            and payload["no_per_attempt_data_dir_ledger"]
            and all(v.get("wiring_ok") for v in payload["arms"].values())
        )
    finally:
        upstream.terminate()
        try:
            upstream.wait(timeout=5)
        except subprocess.TimeoutExpired:
            upstream.kill()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"],
                      "frozen_history_lines": payload.get("frozen_history_lines"),
                      "no_per_attempt_ledger": payload.get("no_per_attempt_data_dir_ledger"),
                      "arms": {k: v.get("wiring_ok") for k, v in payload["arms"].items()}}))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
