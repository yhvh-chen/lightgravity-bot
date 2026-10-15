#!/usr/bin/env python3
"""Bounded real-SDK calibration (does not compare B/C scores).

Purpose: confirm the real SDK agent loop honors the experiment contract and
measure per-turn HTTP/token/time so the formal sample count (12 vs 6) can be
chosen *before* freezing PROTOCOL.md.  Hard bounds:

    <= 6 logical SDK turns, <= 24 real upstream HTTP, <= 100,000 reported
    tokens, <= 300 s wall clock (from the first request).

The calibration case is a small, dedicated two-file workspace that is **not**
any of the three formal fixture classes, so calibration cannot leak into the
formal comparison.

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

_HERE = Path(__file__).resolve()
PROBE_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_HERE.parent))

import host as host_mod  # noqa: E402
from host import ClaimSchema, EditSchema, PlanSchema, SdkHost, read_and_purge_secret  # noqa: E402
from relay import MeteringRelay  # noqa: E402

MODEL = "deepseek-v4-flash"
RELAY_UPSTREAM = "https://api.deepseek.com/v1/chat/completions"
CAL_MAX_TURNS = 6
CAL_MAX_HTTP = 24
CAL_MAX_TOKENS = 100_000
CAL_WALL_SECONDS = 300.0
PER_TURN_MODEL_CALLS = 4
PER_TURN_TOOL_CALLS = 8
TURN_TIMEOUT = 90.0

CAL_GOAL1 = (
    "实现校准工作区中的两个文件（不要动其他文件）：\n"
    "- src/hello.py 的 greet(name) 返回字符串 'hi ' + name。\n"
    "- src/mathx.py 的 double(x) 返回 x * 2。"
)
CAL_GOAL2 = (
    "用户新增要求：\n"
    "- src/hello.py 新增 shout(name) 返回 greet(name).upper()。\n"
    "- src/mathx.py 新增 triple(x) 返回 x * 3。"
)

_CAL_FILES = {
    "src/__init__.py": "",
    "src/hello.py": 'def greet(name):\n    return "TODO"\n',
    "src/mathx.py": "def double(x):\n    return 0\n",
}


def _write_files(base: dict[str, str], out: Path) -> None:
    if out.exists():
        import shutil
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for rel, content in base.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _snapshot(root: Path) -> dict[str, str]:
    snap = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            snap[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return snap


def _accept_calibration(ws: Path) -> dict:
    import subprocess
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from src.hello import greet;"
        "from src.mathx import double;"
        "assert greet('bob') == 'hi bob', greet('bob');"
        "assert double(3) == 6, double(3);"
        "print('CAL_OK')"
    )
    try:
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              cwd=str(ws), timeout=20,
                              env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"})
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "error": str(exc)}
    return {"passed": proc.returncode == 0 and "CAL_OK" in proc.stdout,
            "stdout": proc.stdout[-200:], "stderr": proc.stderr[-300:]}


def _accept_stage2(ws: Path) -> dict:
    import subprocess
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from src.hello import greet, shout;"
        "from src.mathx import double, triple;"
        "assert greet('bob') == 'hi bob'; assert shout('bob') == 'HI BOB';"
        "assert double(3) == 6; assert triple(3) == 9;"
        "print('CAL_OK')"
    )
    try:
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              cwd=str(ws), timeout=20,
                              env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"})
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "error": str(exc)}
    return {"passed": proc.returncode == 0 and "CAL_OK" in proc.stdout,
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

    async def run(self) -> dict:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        workspace = self.runs_dir / "workspace"
        _write_files(_CAL_FILES, workspace)
        self.relay.start()
        try:
            host = SdkHost(self.runs_dir / "sdkdata", self.relay.base_url,
                           workspace_root=self.runs_dir)
            base = _snapshot(workspace)

            async def do(logical: str, agent_ref: str, ws: Path, objective: str, schema,
                         tools: tuple[str, ...]) -> dict:
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
                    timeout_seconds=TURN_TIMEOUT,
                    max_model_calls=PER_TURN_MODEL_CALLS, max_tool_calls=PER_TURN_TOOL_CALLS,
                    save_dir=self.runs_dir / "sessions" / logical,
                )
                calls = self.relay.call_records()[before:]
                turn["relay_calls"] = calls
                turn["relay_http"] = len(calls)
                turn["reported_tokens"] = sum(int((c.get("usage") or {}).get("total_tokens") or 0)
                                              for c in calls)
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
                      f"tokens={turn['reported_tokens']} tools={turn.get('tool_call_names')} "
                      f"finish={str(turn.get('finish_payload'))[:120]}", flush=True)
                return turn

            # 1 planner (structured)
            await do("planner", "planner", workspace, self._planner_obj(base), PlanSchema, ("view-file",))
            # 2 claim w1
            c1 = await do("claim-w1", "claim-worker", workspace, self._claim_obj(CAL_GOAL1, base, {}, []),
                          ClaimSchema, ("view-file",))
            # 3 claim w2 (sees w1 message)
            msg = (c1.get("finish_payload") or {}).get("message") if isinstance(c1.get("finish_payload"), dict) else ""
            c2 = await do("claim-w2", "claim-worker", workspace,
                          self._claim_obj(CAL_GOAL1, base, {"src/hello.py": "w1"},
                                          [{"worker": "w1", "text": str(msg or "")}]),
                          ClaimSchema, ("view-file",))
            # 4 edit w1 (real file write into isolated staging)
            staging1 = self.runs_dir / "staging" / "r1-w1"
            _write_files(base, staging1)
            e1 = await do("edit-w1-r1", "edit-worker", staging1,
                          self._edit_obj(CAL_GOAL1, base, "src/hello.py", "w1", [], []),
                          EditSchema, ("view-file", "create-file", "edit-file"))
            snap1 = _snapshot(staging1)
            # integrate accepted lease change
            integrated = dict(base)
            if "src/hello.py" in snap1:
                integrated["src/hello.py"] = snap1["src/hello.py"]
            _write_files(integrated, workspace)
            acc1 = _accept_calibration(workspace)
            # 5 edit w2 (no lease, review only)
            staging2 = self.runs_dir / "staging" / "r1-w2"
            _write_files(integrated, staging2)
            await do("edit-w2-r1", "edit-worker", staging2,
                     self._edit_obj(CAL_GOAL1, integrated, None, "w2", [], []),
                     EditSchema, ("view-file", "create-file", "edit-file"))
            snap2 = _snapshot(staging2)
            overreach = [p for p in snap2 if p in integrated and snap2[p] != integrated[p]]
            # 6 second-round edit w1 with evolved goal
            staging3 = self.runs_dir / "staging" / "r2-w1"
            _write_files(integrated, staging3)
            e3 = await do("edit-w1-r2", "edit-worker", staging3,
                          self._edit_obj(CAL_GOAL2, integrated, "src/hello.py", "w1", [], []),
                          EditSchema, ("view-file", "create-file", "edit-file"))
            snap3 = _snapshot(staging3)
            if "src/hello.py" in snap3:
                integrated["src/hello.py"] = snap3["src/hello.py"]
            _write_files(integrated, workspace)
            acc2 = _accept_stage2(workspace)

            summary = {
                "mode": "calibration",
                "goal": "confirm real SDK tool loop + measure per-turn cost",
                "bounds": {"max_turns": CAL_MAX_TURNS, "max_http": CAL_MAX_HTTP,
                           "max_tokens": CAL_MAX_TOKENS, "wall_seconds": CAL_WALL_SECONDS},
                "turns_run": len(self.turns),
                "http_used": self.http_used,
                "tokens_used": self.tokens_used,
                "tokens_unknown_calls": self.tokens_unknown,
                "wall_used": round(self.wall_used(), 3),
                "abort": self.abort,
                "per_turn": [{
                    "logical": t.get("logical"), "state": t.get("state"),
                    "http": t.get("relay_http"), "tokens": t.get("reported_tokens"),
                    "tool_call_names": t.get("tool_call_names"),
                    "finish_payload": t.get("finish_payload"),
                    "usage": t.get("usage"), "stop_reason": t.get("stop_reason"),
                    "hook_decisions": t.get("hook_decisions"),
                    "relay_rewrites": [c.get("rewrites") for c in (t.get("relay_calls") or [])],
                    "relay_request_before": [(c.get("request_before") or {}) for c in (t.get("relay_calls") or [])],
                    "finish_reasons": [c.get("finish_reasons") for c in (t.get("relay_calls") or [])],
                    "reasoning_seen": [c.get("reasoning_content_seen") for c in (t.get("relay_calls") or [])],
                } for t in self.turns],
                "evidence": {
                    "hello_written_by_sdk": "src/hello.py" in snap1 and snap1["src/hello.py"] != _CAL_FILES["src/hello.py"],
                    "mathx_written_by_sdk": "src/mathx.py" in snap3 and snap3["src/mathx.py"] != _CAL_FILES["src/mathx.py"],
                    "reviewer_overreach": overreach,
                    "acceptance_stage1": acc1,
                    "acceptance_stage2": acc2,
                },
            }
            return summary
        finally:
            self.relay.stop()

    @staticmethod
    def _planner_obj(base: dict[str, str]) -> str:
        files = "\n".join(f"### {k}\n```python\n{v}\n```" for k, v in sorted(base.items()))
        return f"## 当前文件\n{files}\n\n为两名 worker 规划实现 greet 与 double，文件不重叠。"

    @staticmethod
    def _claim_obj(goal: str, base: dict[str, str], granted: dict[str, str],
                   messages: list[dict]) -> str:
        files = "\n".join(f"### {k}\n```python\n{v}\n```" for k, v in sorted(base.items()))
        g = "\n".join(f"- {k} 已被 {v} 认领" for k, v in granted.items()) or "（无）"
        m = "\n".join(f"- {x['worker']}: {x['text']}" for x in messages) or "（无）"
        return (f"## 用户目标\n{goal}\n\n## 当前文件\n{files}\n\n## 已认领\n{g}\n"
                f"## 同伴消息\n{m}\n\n用 finish 返回 claim/message/findings。")

    @staticmethod
    def _edit_obj(goal: str, base: dict[str, str], lease: str | None, worker: str,
                  findings: list[str], messages: list[dict]) -> str:
        files = "\n".join(f"### {k}\n```python\n{v}\n```" for k, v in sorted(base.items()))
        if lease:
            lease_text = (f"你持有 {lease} 的租约。请用文件工具实际写入该文件，然后 finish。")
        else:
            lease_text = "你没有租约，只能 view_file 复核，不得写任何文件，然后 finish。"
        return (f"## 用户目标\n{goal}\n\n## 当前文件\n{files}\n\n## 你的租约\n{lease_text}\n\n"
                "完成后 finish 返回 summary/findings。")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=str(PROBE_ROOT / "runs" / "calibration"))
    args = ap.parse_args()
    credential = read_and_purge_secret()
    if not credential:
        print("DEEPSEEK_API_KEY not present", file=sys.stderr)
        return 2
    cal = Calibration(Path(args.runs_dir), credential)
    summary = asyncio.run(cal.run())
    (Path(args.runs_dir) / "CALIBRATION_RAW.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("turns_run", "http_used", "tokens_used",
                                              "wall_used", "abort", "evidence")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
