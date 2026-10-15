#!/usr/bin/env python3
"""Corrected bounded real-SDK calibration (does not compare B/C scores).

Hard bounds (frozen): **<= 2 logical SDK turns, <= 12 real upstream HTTP,
<= 60,000 reported tokens, <= 180 s** from the first request.  All attempts are
counted; there is no separate re-validation budget.

Exactly two logical turns against a dedicated two-file fixture that is *not* any
formal class:

1. **planner** — must emit a full, strict, valid two-file plan (lossless
   payload, program-validated);
2. **edit** — must ``view_file`` and actually write its leased file with a real
   file tool, with (a) a non-empty real path in the hook decision, (b) the
   planner plan hash injected into its prompt, and (c) positive stop evidence.

If the plan is invalid, the payload is missing/truncated, the write did not land,
a path decision is empty, or a stop is unconfirmed, the calibration **fails and
stops**; it never falls back to a looser path.

Usage:
    python3 driver/calibrate.py [--runs-dir ...]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_PROBE_ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

from host import EditSchema, PlanSchema, SdkHost, read_and_purge_secret  # noqa: E402
from experiment import Experiment, read_snapshot, writable_paths  # noqa: E402
from relay import MeteringRelay  # noqa: E402

MODEL = "deepseek-v4-flash"
RELAY_UPSTREAM = "https://api.deepseek.com/v1/chat/completions"

CAL_MAX_TURNS = 2
CAL_MAX_HTTP = 12
CAL_MAX_TOKENS = 60_000
CAL_WALL_SECONDS = 180.0
PER_TURN_MODEL_CALLS = 6
PER_TURN_TOOL_CALLS = 8
TURN_TIMEOUT = 90.0

_CAL_FILES = {
    "src/__init__.py": "",
    "src/alpha.py": 'def add(a, b):\n    return None\n',
    "src/beta.py": "def multiply(a, b):\n    return None\n",
}
_CAL_GOAL = (
    "实现校准工作区中的两个文件（不要动其他文件）：\n"
    "- src/alpha.py 的 add(a, b) 返回 a + b。\n"
    "- src/beta.py 的 multiply(a, b) 返回 a * b。"
)


def _write_files(base: dict[str, str], out: Path) -> None:
    import shutil
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for rel, content in base.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _accept(ws: Path, lease: str | None) -> dict:
    """Check the *leased* file only (a single edit turn writes one file)."""

    import subprocess
    if not lease:
        return {"passed": False, "error": "no lease"}
    base = Path(lease).name
    if base == "alpha.py":
        code = ("import sys; sys.path.insert(0, '.');"
                "from src.alpha import add;"
                "assert add(2,3) == 5, add(2,3);"
                "print('CAL_OK')")
    elif base == "beta.py":
        code = ("import sys; sys.path.insert(0, '.');"
                "from src.beta import multiply;"
                "assert multiply(2,3) == 6, multiply(2,3);"
                "print('CAL_OK')")
    else:
        return {"passed": False, "error": f"unknown lease {lease!r}"}
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ws),
            timeout=20, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp",
                             "PYTHONDONTWRITEBYTECODE": "1"})
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "error": str(exc)}
    return {"passed": proc.returncode == 0 and "CAL_OK" in proc.stdout,
            "lease": lease,
            "stdout": proc.stdout[-200:], "stderr": proc.stderr[-300:]}


class Calibration:
    def __init__(self, runs_dir: Path, credential: str) -> None:
        self.runs_dir = runs_dir
        self.credential = credential
        self.relay = MeteringRelay(upstream_url=RELAY_UPSTREAM)
        self.turns: list[dict] = []
        self.http_used = 0
        self.tokens_used = 0
        self.tokens_unknown = 0
        self.wall_start: float | None = None
        self.abort: str | None = None
        self.gaps: list[str] = []

    def wall_used(self) -> float:
        return 0.0 if self.wall_start is None else time.monotonic() - self.wall_start

    def _precheck(self) -> str | None:
        if len(self.turns) >= CAL_MAX_TURNS:
            return "turn cap"
        if self.http_used + PER_TURN_MODEL_CALLS > CAL_MAX_HTTP:
            return "http cap headroom"
        if self.tokens_used >= CAL_MAX_TOKENS:
            return "token cap"
        if self.wall_start is not None and self.wall_used() > CAL_WALL_SECONDS:
            return "wall cap"
        return None

    async def _do(self, host: SdkHost, *, logical: str, agent_ref: str, ws: Path,
                  objective: str, schema, tools: tuple[str, ...],
                  write_lease: str | None, plan_id: str | None) -> dict:
        err = self._precheck()
        if err:
            self.abort = err
            return {"logical": logical, "skipped": err}
        before = self.relay.call_count
        if self.wall_start is None:
            self.wall_start = time.monotonic()
        turn = await host.run_turn(
            credential=self.credential, agent_ref=agent_ref, workspace=ws,
            objective=objective, response_schema=schema, allowed_tools=tools,
            timeout_seconds=TURN_TIMEOUT, max_model_calls=PER_TURN_MODEL_CALLS,
            max_tool_calls=PER_TURN_TOOL_CALLS,
            save_dir=self.runs_dir / "sessions" / logical, write_lease=write_lease,
        )
        calls = self.relay.call_records()[before:]
        turn["relay_calls"] = calls
        turn["relay_http"] = len(calls)
        turn["reported_tokens"] = sum(int((c.get("usage") or {}).get("total_tokens") or 0)
                                      for c in calls)
        turn["logical"] = logical
        turn["plan_id"] = plan_id
        turn["plan_injected"] = (f"plan_id: {plan_id}" in objective) if plan_id else None
        turn["stop_positive"] = bool((turn.get("stop_evidence") or {}).get("positive"))
        self.http_used += turn["relay_http"]
        usage = turn.get("usage") or {}
        total = usage.get("total_tokens")
        if isinstance(total, int) and total > 0:
            self.tokens_used += total
        else:
            self.tokens_unknown += 1
            self.tokens_used += int(len(objective) / 4) + 8192
        self.turns.append(turn)
        print(f"[cal] {logical}: state={turn['state']} http={turn['relay_http']} "
              f"tokens={turn['reported_tokens']} finish_chars={turn.get('finish_payload_chars')} "
              f"stop={turn.get('stop_evidence', {}).get('status')}", flush=True)
        return turn

    async def run(self) -> dict:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        workspace = self.runs_dir / "workspace"
        _write_files(_CAL_FILES, workspace)
        self.relay.start()
        try:
            host = SdkHost(self.runs_dir / "sdkdata", self.relay.base_url,
                           workspace_root=self.runs_dir)
            base = read_snapshot(workspace)
            exp = Experiment(SimpleNamespace(mode="mock", runs_dir=str(self.runs_dir / "mock"),
                                             resume=False, single=True, repeats=None))

            # --- turn 1: planner -------------------------------------------------
            planner_obj = (
                f"## 用户目标\n{_CAL_GOAL}\n\n"
                f"## 当前可写文件\n{', '.join(writable_paths(base))}\n\n"
                "## 任务\n为 w1、w2 各给一个条目；每个可写文件恰好分给一个 worker；"
                "严格使用键 worker/objective/files，禁止额外键，每项最多 1 个文件。"
            )
            turn1 = await self._do(host, logical="planner", agent_ref="planner",
                                   ws=workspace, objective=planner_obj, schema=PlanSchema,
                                   tools=("view-file",), write_lease=None, plan_id=None)
            plan, issues = (None, ["not_run"]) if turn1.get("skipped") else \
                exp.validate_plan(turn1.get("finish_payload"), base)
            if plan is None:
                self.gaps.append(f"planner_plan_invalid: {issues}")
            if turn1.get("finish_payload_chars") in (None, 0):
                self.gaps.append("planner_payload_missing")
            if turn1.get("finish_parse_error") is not None:
                self.gaps.append(f"planner_finish_error: {turn1.get('finish_parse_error')}")
            if not turn1.get("stop_positive"):
                self.gaps.append("planner_stop_unconfirmed")

            # --- turn 2: edit (holds w1's file lease) ----------------------------
            lease = None
            w1_objective = ""
            if plan:
                for item in plan["plan"]:
                    if item["worker"] == "w1":
                        w1_objective = item["objective"]
                        if item["files"]:
                            lease = item["files"][0]
            staging = self.runs_dir / "staging" / "r1-w1"
            _write_files(base, staging)
            plan_id = plan.get("plan_id") if plan else None
            plan_block = "（无有效计划）"
            if plan:
                plan_block = f"plan_id: {plan_id}\n- objective: {w1_objective}"
            edit_obj = (
                f"## 用户目标\n{_CAL_GOAL}\n\n"
                f"## 本轮分工（编排角色给出）\n{plan_block}\n\n"
                f"## 你的租约\n你持有 {lease} 的租约。先用 view_file 查看该文件，"
                "再用文件工具实际写入实现，最后 finish 返回 summary/findings。"
            )
            turn2 = await self._do(host, logical="edit-w1", agent_ref="edit-worker",
                                   ws=staging, objective=edit_obj, schema=EditSchema,
                                   tools=("view-file", "create-file", "edit-file"),
                                   write_lease=lease, plan_id=plan_id)
            snap = read_snapshot(staging)
            if lease is None:
                self.gaps.append("no_lease_for_edit")
            else:
                written = lease in snap and snap[lease] != base.get(lease)
                if not written:
                    self.gaps.append(f"edit_did_not_write_lease:{lease}")
            decisions = turn2.get("hook_decisions") or []
            read_ok = any(d.get("tool") in ("view_file",) and d.get("paths")
                          and d.get("allow") for d in decisions)
            write_ok = any(d.get("tool") in ("create_file", "edit_file", "write_to_file")
                           and d.get("paths") and d.get("allow") for d in decisions)
            if not read_ok:
                self.gaps.append("no_nonempty_read_path_decision")
            if not write_ok:
                self.gaps.append("no_nonempty_write_path_decision")
            if turn2.get("finish_payload") is None:
                self.gaps.append("edit_payload_missing")
            if not turn2.get("plan_injected"):
                self.gaps.append("plan_not_injected")
            if not turn2.get("stop_positive"):
                self.gaps.append("edit_stop_unconfirmed")

            acc = _accept(staging, lease) if lease else {"passed": False, "error": "no lease"}
            summary = {
                "mode": "calibration-corrected",
                "goal": "strict valid plan + one real leased write, within 2 turns",
                "bounds": {"max_turns": CAL_MAX_TURNS, "max_http": CAL_MAX_HTTP,
                           "max_tokens": CAL_MAX_TOKENS, "wall_seconds": CAL_WALL_SECONDS},
                "turns_run": len(self.turns),
                "http_used": self.http_used,
                "tokens_used": self.tokens_used,
                "tokens_unknown_calls": self.tokens_unknown,
                "wall_used": round(self.wall_used(), 3),
                "abort": self.abort,
                "gaps": self.gaps,
                "passed": (not self.abort) and (not self.gaps) and acc.get("passed") is True,
                "plan": plan,
                "plan_id": plan_id,
                "acceptance": acc,
                "turns": [{
                    "logical": t.get("logical"), "state": t.get("state"),
                    "http": t.get("relay_http"), "tokens": t.get("reported_tokens"),
                    "finish_payload_chars": t.get("finish_payload_chars"),
                    "finish_source": t.get("finish_source"),
                    "finish_parse_error": t.get("finish_parse_error"),
                    "emitted_truncated": t.get("emitted_truncated"),
                    "session_db_matches_hook": t.get("session_db_matches_hook"),
                    "tool_call_names": t.get("tool_call_names"),
                    "hook_decisions": t.get("hook_decisions"),
                    "plan_injected": t.get("plan_injected"),
                    "stop_evidence": t.get("stop_evidence"),
                    "relay_request_after": [(c.get("request_after") or {}) for c in (t.get("relay_calls") or [])],
                    "relay_rewrites": [c.get("rewrites") for c in (t.get("relay_calls") or [])],
                    "finish_reasons": [c.get("finish_reasons") for c in (t.get("relay_calls") or [])],
                } for t in self.turns],
            }
            return summary
        finally:
            self.relay.stop()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=str(_PROBE_ROOT / "runs" / "calibration"))
    args = ap.parse_args()
    credential = read_and_purge_secret()
    if not credential:
        print("DEEPSEEK_API_KEY not present", file=sys.stderr)
        return 2
    cal = Calibration(Path(args.runs_dir), credential)
    summary = asyncio.run(cal.run())
    out = Path(args.runs_dir) / "CALIBRATION_RAW.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("turns_run", "http_used", "tokens_used", "wall_used",
                       "abort", "gaps", "passed", "plan_id", "acceptance")},
                     ensure_ascii=False, indent=2))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
