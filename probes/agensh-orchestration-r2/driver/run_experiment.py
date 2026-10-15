#!/usr/bin/env python3
"""Round-2 orchestration comparison driver (controlled editing collaboration).

Groups (single variable = independent orchestration model):
  B = one initial planner call + program-mediated claim/peer negotiation
  C = no orchestration model + identical program-mediated claim/peer negotiation

Both groups share: model/params, tool+file permission model, scheduling,
acceptance, rounds, worker templates, context retrieval/integration rules.
The only difference is the single B planner call whose text is shown to workers.

Per round: sequential claim/message phase (first worker's claim result and
message are visible to the second worker), then a parallel edit/review phase
against one frozen base. The program (never the model) grants leases, checks
base hashes, rejects overreach, integrates and runs acceptance.

This is a *bounded structured file-edit* protocol, NOT a real SDK tool loop.
Only the standard library is used.

Usage:
    DEEPSEEK_API_KEY=... python3 driver/run_experiment.py
Offline: python3 driver/run_experiment.py --mock --runs-dir runs_mock
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_client import (  # noqa: E402
    DEFAULT_HOST,
    DEFAULT_PATH,
    ModelResult,
    chat_completion,
    estimate_tokens,
)

# ---------------------------------------------------------------------------
# Frozen configuration (PROTOCOL.md §3, §6)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"

MODEL = "deepseek-v4-flash"
MAX_TOKENS = 8192
TEMPERATURE = 0.0
FIRST_EVENT_TIMEOUT = 30.0
TOTAL_TIMEOUT = 90.0
ORDER_SEED = 20261015
REPEATS = 3

MAX_NORMAL_CALLS = 153          # 144 worker + 9 planner
MAX_RETRIES = 9                 # infra retries only, cumulative
MAX_HTTP = 162
MAX_TOTAL_TOKENS = 600000
WALL_SECONDS = 1500             # hard wall clock from first formal request
ACCEPT_TIMEOUT = 30
MAX_EDIT_BYTES = 20000
MESSAGE_MAX_CHARS = 240
FINDINGS_MAX_ITEMS = 3
FINDING_MAX_CHARS = 160

ALL_TASKS = ["t1_independent", "t2_interface", "t3_evolving"]
ALL_GROUPS = ["B", "C"]
# First claimer per repeat: alternate w1/w2; both groups in a repeat share it.
FIRST_WORKER_BY_REPEAT = {0: "w1", 1: "w2", 2: "w1"}

T1_GOAL = """实现 src/slugs.py 和 src/ranges.py 中的函数（不要修改其他文件）：
- slugify(title): 把 title 转小写；把每一段连续的非字母数字字符（a-z、0-9 之外）替换成单个 "-"；去掉结果首尾的 "-"。
- clamp(value, lo, hi): value < lo 时返回 lo；value > hi 时返回 hi；否则返回 value。
- in_range(value, lo, hi): 当 lo <= value <= hi 时返回 True，否则返回 False。"""

T2_GOAL = """实现 src/geometry.py 和 src/report.py，二者必须遵守同一个 shape 接口（不要修改其他文件）：
- shape 是 dict：kind 为 "rect" 时含 width、height；kind 为 "circle" 时含 radius。
- geometry.area(shape): rect 返回 width*height；circle 返回 math.pi*radius**2；未知 kind 抛 ValueError。
- geometry.perimeter(shape): rect 返回 2*(width+height)；circle 返回 2*math.pi*radius；未知 kind 抛 ValueError。
- report.describe(shape): 使用 geometry 的 area/perimeter，返回 f"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"。"""

T3_GOAL1 = """实现 src/stats.py（不要修改其他文件）：
- mean(nums): 空列表抛 ValueError，否则返回算术平均。
- median(nums): 空列表抛 ValueError；奇数长度返回排序后的中间值；偶数长度返回中间两个数的平均。"""

T3_GOAL2_ADD = """用户在本轮开始前新增的明确要求（所有组同样适用）：
- 新增 mode(nums): 返回出现次数最多的值；若平局返回最小的那个值；空列表抛 ValueError。
- 新增 stdev(nums): 返回总体标准差（即 sqrt(方差)，方差按除以 n 计算）；空列表抛 ValueError。
- 必须保持 mean/median 对空列表抛 ValueError 的既有行为。"""

TASKS: dict[str, dict[str, Any]] = {
    "t1_independent": {"goal1": T1_GOAL, "goal2": T1_GOAL, "stage1": None, "stage2": None},
    "t2_interface": {"goal1": T2_GOAL, "goal2": T2_GOAL, "stage1": None, "stage2": None},
    "t3_evolving": {"goal1": T3_GOAL1, "goal2": T3_GOAL1 + "\n\n" + T3_GOAL2_ADD,
                    "stage1": 1, "stage2": 2},
}

PROGRAM_RULES = """程序规则（两组完全相同，由 driver 强制执行，模型只能提议）：
- 你只能通过返回 JSON 提议，不能直接写文件、不能修改 TASK/RUN/SUBTASK/events/测试/验收。
- 每轮每名 worker 最多持有 1 个可写文件的租约（程序原子检查/授予，先到先得）。
- 已被他人认领的文件不能再认领；拿不到租约时你可以复核并在 message/findings 留言。
- 编辑只能针对你本轮持有租约的文件，并携带该文件当前 sha256（base_sha256）。越权/base 不符/语法错误会被程序拒绝。
- 本轮编辑都基于同一个冻结 base，提交后由程序整合并运行验收。
"""

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_snapshot(ws: Path) -> dict[str, str]:
    snap: dict[str, str] = {}
    for path in sorted(ws.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        snap[path.relative_to(ws).as_posix()] = path.read_text(encoding="utf-8")
    return snap


def fixture_hash(ws: Path) -> str:
    snap = read_snapshot(ws)
    h = hashlib.sha256()
    for rel in sorted(snap):
        h.update(rel.encode("utf-8")); h.update(b"\0")
        h.update(snap[rel].encode("utf-8")); h.update(b"\0")
    return h.hexdigest()


def extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None


def parse_frontmatter(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def clean_env() -> dict[str, str]:
    """No credentials, no inherited provider vars: only what tests need."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def write_files(base: dict[str, str], out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for rel, content in base.items():
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def copy_initial(task: str, ws: Path) -> None:
    initial = FIXTURES / task / "initial"
    write_files({p.relative_to(initial).as_posix(): p.read_text(encoding="utf-8")
                 for p in initial.rglob("*") if p.is_file()}, ws)


# Generic writable-file rule (same for both groups, not task-semantic): package
# __init__ stubs are read-only; every other file in the workspace is claimable.
WRITABLE_EXCLUDE_BASENAMES = {"__init__.py"}


def writable_paths(snapshot: dict[str, str]) -> list[str]:
    return [rel for rel in sorted(snapshot)
            if Path(rel).name not in WRITABLE_EXCLUDE_BASENAMES]


def clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…[clipped]"


def format_feedback(acc: dict[str, Any]) -> str:
    checks = acc.get("checks", [])
    lines = [f"程序检查结果：{acc.get('passed', 0)}/{acc.get('total', 0)} 项通过。"]
    failed = [c for c in checks if not c.get("passed")]
    for c in failed:
        lines.append(f"- 未通过 {c['name']}: {clip(str(c.get('detail', '')), 200)}")
    if not failed:
        lines.append("- 全部检查通过。")
    return "\n".join(lines)


def plan_for_worker(plan: dict[str, Any] | None, worker: str) -> str:
    if not plan:
        return "（编排未提供有效计划）"
    parts = []
    for item in plan.get("plan") or []:
        if isinstance(item, dict) and item.get("worker") == worker:
            parts.append(f"- objective: {item.get('objective', '')}\n  files: {item.get('files', [])}")
    notes = plan.get("interface_notes")
    if notes:
        parts.append(f"- interface_notes: {notes}")
    return "\n".join(parts) if parts else "（计划中没有为该 worker 指定条目，请自行按目标选择工作）"


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------
class Budget:
    def __init__(self, state: dict[str, Any], state_path: Path, lock: threading.Lock):
        self.state = state
        self.state_path = state_path
        self.lock = lock

    def reserve(self, retry: bool, est_input: int) -> str | None:
        with self.lock:
            now = time.time()
            if self.state.get("formal_start_epoch") is None:
                self.state["formal_start_epoch"] = now
            if now - self.state["formal_start_epoch"] > WALL_SECONDS:
                return "wall-clock limit reached (1500s)"
            if self.state["http_requests"] >= MAX_HTTP:
                return f"http request cap reached ({MAX_HTTP})"
            if retry:
                if self.state["retry_calls"] >= MAX_RETRIES:
                    return f"retry cap reached ({MAX_RETRIES})"
                self.state["retry_calls"] += 1
            else:
                if self.state["normal_calls"] >= MAX_NORMAL_CALLS:
                    return f"normal call cap reached ({MAX_NORMAL_CALLS})"
                self.state["normal_calls"] += 1
            reserve = est_input + MAX_TOKENS
            if self.state["total_tokens"] + self.state["reserved_tokens"] + reserve > MAX_TOTAL_TOKENS:
                return "token budget would be exceeded (600000)"
            self.state["reserved_tokens"] += reserve
            self.state["http_requests"] += 1
            self._save()
            return None

    def release(self, res: ModelResult, est_input: int) -> None:
        with self.lock:
            self.state["reserved_tokens"] = max(0, self.state["reserved_tokens"] - (est_input + MAX_TOKENS))
            if res.usage:
                try:
                    self.state["total_tokens"] += int(res.usage.get("total_tokens") or 0)
                except (TypeError, ValueError):
                    self.state["total_tokens"] += res.estimated_tokens
                    self.state["usage_unknown_calls"] += 1
            else:
                self.state["total_tokens"] += res.estimated_tokens
                self.state["usage_unknown_calls"] += 1
            self._save()

    def release_without_call(self, est_input: int) -> None:
        with self.lock:
            self.state["reserved_tokens"] = max(0, self.state["reserved_tokens"] - (est_input + MAX_TOKENS))
            self._save()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# mock model (offline only)
# ---------------------------------------------------------------------------
MOCK_SLUGS = 'import re\n\n\ndef slugify(title: str) -> str:\n    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")\n'
MOCK_RANGES = ('def clamp(value, lo, hi):\n'
               '    if value < lo:\n        return lo\n    if value > hi:\n        return hi\n    return value\n\n\n'
               'def in_range(value, lo, hi) -> bool:\n    return lo <= value <= hi\n')
MOCK_GEOMETRY = ('import math\n\n\ndef area(shape):\n'
                 '    if shape["kind"] == "rect":\n        return shape["width"] * shape["height"]\n'
                 '    if shape["kind"] == "circle":\n        return math.pi * shape["radius"] ** 2\n'
                 '    raise ValueError(shape["kind"])\n\n\n'
                 'def perimeter(shape):\n'
                 '    if shape["kind"] == "rect":\n        return 2 * (shape["width"] + shape["height"])\n'
                 '    if shape["kind"] == "circle":\n        return 2 * math.pi * shape["radius"]\n'
                 '    raise ValueError(shape["kind"])\n')
MOCK_REPORT = ('from .geometry import area, perimeter\n\n\n'
               'def describe(shape):\n'
               '    return f"{shape[\'kind\']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"\n')
MOCK_STATS_R1 = ('def mean(nums):\n    if not nums:\n        raise ValueError("empty")\n    return sum(nums) / len(nums)\n\n\n'
                 'def median(nums):\n    if not nums:\n        raise ValueError("empty")\n'
                 '    ordered = sorted(nums)\n    n = len(ordered)\n    if n % 2:\n        return ordered[n // 2]\n'
                 '    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2\n')
MOCK_STATS_FINAL = MOCK_STATS_R1 + ('\n\ndef mode(nums):\n    if not nums:\n        raise ValueError("empty")\n'
                                    '    counts = {}\n    for x in nums:\n        counts[x] = counts.get(x, 0) + 1\n'
                                    '    best = max(counts.values())\n'
                                    '    return min(k for k, v in counts.items() if v == best)\n')
MOCK_STATS_FINAL_STDEV = MOCK_STATS_FINAL + ('\n\nimport math\n\n\ndef stdev(nums):\n'
                                             '    if not nums:\n        raise ValueError("empty")\n'
                                             '    mu = mean(nums)\n'
                                             '    return math.sqrt(sum((x - mu) ** 2 for x in nums) / len(nums))\n')


class FakeLLM:
    """Scripted offline model: exercises retry, overreach, claim conflict, review."""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()
        self.fired_infra = False

    def chat(self, messages, *, kind: str, run_ctx: dict[str, Any]) -> ModelResult:
        with self._lock:
            self.calls += 1
        task = run_ctx["task"]
        group = run_ctx["group"]
        rnd = run_ctx["round"]
        worker = run_ctx.get("worker")
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                 "completion_tokens_details": {"reasoning_tokens": 0}}
        # one transient infra failure + retry for the very first logical call
        if (kind == "claim" and task == "t1_independent" and group == "B" and rnd == 1
                and worker == "w1" and not self.fired_infra):
            self.fired_infra = True
            return ModelResult(ok=False, error="mock transient 503", infra_failure=True,
                               http_status=503, estimated_tokens=10, usage_unknown=True,
                               raw_request={"mock": True}, elapsed=0.01)
        if kind == "planner":
            content = json.dumps(self._plan(task))
        elif kind == "claim":
            content = self._claim(task, worker, run_ctx)
        else:
            content = self._edit(task, rnd, worker, run_ctx)
        return ModelResult(ok=True, content=content, usage=usage, http_status=200, elapsed=0.01,
                           raw_request={"mock": True, "kind": kind}, raw_response_text=content,
                           estimated_tokens=150, finish_reason="stop", response_model=MODEL,
                           reasoning_tokens=0)

    def _plan(self, task: str) -> dict[str, Any]:
        files = {
            "t1_independent": {"w1": ["src/slugs.py"], "w2": ["src/ranges.py"]},
            "t2_interface": {"w1": ["src/geometry.py"], "w2": ["src/report.py"]},
            "t3_evolving": {"w1": ["src/stats.py"], "w2": []},
        }[task]
        return {"plan": [
            {"worker": "w1", "objective": "implement assigned module", "files": files["w1"]},
            {"worker": "w2", "objective": "implement/verify assigned module", "files": files["w2"]},
        ], "interface_notes": "keep module interfaces stable", "findings": ["plan created"]}

    def _claim(self, task: str, worker: str, run_ctx: dict[str, Any]) -> str:
        leased = set(run_ctx.get("granted", {}))
        desired = {
            "t1_independent": {"w1": "src/slugs.py", "w2": "src/ranges.py"},
            "t2_interface": {"w1": "src/geometry.py", "w2": "src/report.py"},
            "t3_evolving": {"w1": "src/stats.py", "w2": None},
        }[task][worker]
        claim = desired if (desired and desired not in leased) else None
        return json.dumps({"claim": claim, "message": f"{worker} proposes {claim or 'review only'}",
                           "findings": [f"{worker} claim {claim or 'none'}"]})

    def _edit(self, task: str, rnd: int, worker: str, run_ctx: dict[str, Any]) -> str:
        lease = run_ctx.get("lease")
        snapshot: dict[str, str] = run_ctx["snapshot"]

        def out(path: str, content: str) -> str:
            return json.dumps({"summary": f"implemented {path}", "findings": [f"{worker} touched {path}"],
                               "edits": [{"path": path, "base_sha256": sha256_text(snapshot[path]),
                                          "content": content}]})

        if lease is None:
            # reviewers may not write; mock also proposes one overreach once to exercise rejection
            if worker == "w2" and task != "t3_evolving" and rnd == 2:
                return json.dumps({"summary": "review", "findings": ["review only"],
                                   "edits": [{"path": "src/__init__.py",
                                              "base_sha256": sha256_text(snapshot.get("src/__init__.py", "")),
                                              "content": "# overreach\n"}]})
            return json.dumps({"summary": "review", "findings": ["nothing to write"], "edits": []})
        if task == "t1_independent":
            return out(lease, MOCK_SLUGS if lease.endswith("slugs.py") else MOCK_RANGES)
        if task == "t2_interface":
            return out(lease, MOCK_GEOMETRY if lease.endswith("geometry.py") else MOCK_REPORT)
        if rnd == 1:
            return out(lease, MOCK_STATS_R1)
        return out(lease, MOCK_STATS_FINAL_STDEV)


# ---------------------------------------------------------------------------
# experiment
# ---------------------------------------------------------------------------
class Experiment:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.mock = args.mock
        self.runs_dir = Path(args.runs_dir).resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.runs_dir / "state.json"
        self.lock = threading.Lock()
        self.abort_reason: str | None = None
        self.fatal_protocol: str | None = None
        self.consecutive_infra = 0
        self._seq = 0
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.fake = FakeLLM() if self.mock else None
        self.state = self._load_state()
        self.budget = Budget(self.state, self.state_path, self.lock)

    # -- state -------------------------------------------------------------
    def _specs(self) -> list[dict[str, Any]]:
        specs = [{"task": t, "group": g, "repeat": r}
                 for t in ALL_TASKS for g in ALL_GROUPS for r in range(REPEATS)]
        return specs

    def _load_state(self) -> dict[str, Any]:
        if self.args.resume and self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        specs = self._specs()
        order = list(range(len(specs)))
        random.Random(ORDER_SEED).shuffle(order)
        return {
            "formal_start_epoch": None,
            "specs": specs,
            "order": order,
            "completed": {},
            "http_requests": 0,
            "normal_calls": 0,
            "retry_calls": 0,
            "total_tokens": 0,
            "reserved_tokens": 0,
            "usage_unknown_calls": 0,
            "fatal_protocol": None,
            "abort_reason": None,
            "plan_freeze": None,
        }

    def _save_state(self) -> None:
        with self.lock:
            self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    # -- model calls -------------------------------------------------------
    def _next_seq(self) -> int:
        with self.lock:
            self._seq += 1
            return self._seq

    def _raw_call(self, messages, kind, run_ctx) -> ModelResult:
        if self.mock:
            return self.fake.chat(messages, kind=kind, run_ctx=run_ctx)
        return chat_completion(
            self.api_key, messages, model=MODEL, host=DEFAULT_HOST, path=DEFAULT_PATH,
            max_tokens=MAX_TOKENS, temperature=TEMPERATURE, json_mode=False,
            first_event_timeout=FIRST_EVENT_TIMEOUT, total_timeout=TOTAL_TIMEOUT,
            thinking_disabled=True)

    def _journal_path(self, run_dir: Path, logical: str) -> Path:
        return run_dir / "calls" / f"{logical}.json"

    def _journal_to_result(self, d: dict[str, Any]) -> ModelResult:
        return ModelResult(
            ok=d["ok"], content=d.get("content", ""), usage=d.get("usage"),
            http_status=d.get("http_status"), error=d.get("error"),
            infra_failure=d.get("infra_failure", False), fatal=d.get("fatal", False),
            elapsed=d.get("elapsed", 0.0), raw_request=d.get("request", {}),
            raw_response_text=d.get("content", ""), estimated_tokens=d.get("estimated_tokens", 0),
            usage_unknown=d.get("usage_unknown", False),
            first_event_seconds=d.get("first_event_seconds"), finish_reason=d.get("finish_reason"),
            response_model=d.get("response_model"), reasoning_content=d.get("reasoning_content", ""),
            reasoning_tokens=int(d.get("reasoning_tokens") or 0))

    def call_model(self, messages, kind, run_ctx, round_no) -> tuple[ModelResult, int]:
        if self.abort_reason:
            return ModelResult(ok=False, error=f"aborted: {self.abort_reason}",
                               infra_failure=True, raw_request={}, usage_unknown=True), 0
        run_dir: Path = run_ctx["run_dir"]
        logical: str = run_ctx["logical"]
        jpath = self._journal_path(run_dir, logical)
        if jpath.exists():
            d = json.loads(jpath.read_text(encoding="utf-8"))
            return self._journal_to_result(d), 0

        est_input = estimate_tokens("\n".join(m.get("content", "") for m in messages))
        attempts = 0
        last: ModelResult | None = None
        while True:
            retry = attempts > 0
            err = self.budget.reserve(retry, est_input)
            if err:
                self.budget.release_without_call(est_input)
                self.abort_reason = self.abort_reason or f"budget: {err}"
                return ModelResult(ok=False, error=f"budget: {err}", infra_failure=True,
                                   raw_request={}, usage_unknown=True), attempts
            res = self._raw_call(messages, kind, run_ctx)
            self.budget.release(res, est_input)
            attempts += 1
            self._write_raw(run_dir, kind, run_ctx, res, retry, round_no, attempts, est_input)
            if res.ok:
                self.consecutive_infra = 0
                if res.reasoning_tokens > 0 or res.reasoning_content:
                    self.fatal_protocol = ("model still produced reasoning tokens/content; "
                                           "thinking.type=disabled not honored")
                    self.abort_reason = self.abort_reason or self.fatal_protocol
                self._journal_result(run_dir, logical, res, attempts, est_input)
                return res, attempts
            if res.fatal:
                self.fatal_protocol = f"HTTP {res.http_status} (request/config rejected): {res.error}"
                self.abort_reason = self.abort_reason or self.fatal_protocol
                self._journal_result(run_dir, logical, res, attempts, est_input)
                return res, attempts
            if not res.infra_failure:
                self.consecutive_infra = 0
                self._journal_result(run_dir, logical, res, attempts, est_input)
                return res, attempts
            self.consecutive_infra += 1
            if self.consecutive_infra >= 3:
                self.abort_reason = self.abort_reason or "3 consecutive infrastructure failures"
                return res, attempts
            if self.state["retry_calls"] >= MAX_RETRIES:
                self.abort_reason = self.abort_reason or "retry cap reached"
                return res, attempts
            time.sleep(min(2.0 ** attempts, 8.0))
            last = res

    def _write_raw(self, run_dir: Path, kind: str, run_ctx: dict[str, Any], res: ModelResult,
                   retry: bool, round_no: int, attempt: int, est_input: int) -> None:
        seq = self._next_seq()
        wid = run_ctx.get("worker") or "planner"
        record = {
            "seq": seq, "run": run_ctx.get("run_id"), "kind": kind,
            "worker": run_ctx.get("worker"), "round": round_no,
            "group": run_ctx.get("group"), "task": run_ctx.get("task"),
            "model_requested": MODEL,
            "base_url": f"https://{DEFAULT_HOST}{DEFAULT_PATH}",
            "retry": retry, "attempt": attempt, "estimated_input_tokens": est_input,
            "request": res.raw_request, "http_status": res.http_status, "ok": res.ok,
            "infra_failure": res.infra_failure, "fatal": res.fatal, "error": res.error,
            "elapsed_seconds": round(res.elapsed, 3),
            "first_event_seconds": res.first_event_seconds,
            "usage": res.usage, "usage_unknown": res.usage_unknown,
            "estimated_tokens": res.estimated_tokens,
            "finish_reason": res.finish_reason,
            "response_model": res.response_model,
            "reasoning_tokens": res.reasoning_tokens,
            "reasoning_content": res.reasoning_content,
            "response_text": res.raw_response_text,
        }
        raw_dir = run_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"{seq:04d}_{kind}_{wid}_r{round_no}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _journal_result(self, run_dir: Path, logical: str, res: ModelResult, attempts: int,
                        est_input: int) -> None:
        jpath = self._journal_path(run_dir, logical)
        jpath.parent.mkdir(parents=True, exist_ok=True)
        d = {
            "ok": res.ok, "content": res.raw_response_text if res.ok else res.content,
            "usage": res.usage, "http_status": res.http_status, "error": res.error,
            "infra_failure": res.infra_failure, "fatal": res.fatal,
            "elapsed": round(res.elapsed, 3), "request": res.raw_request,
            "estimated_tokens": res.estimated_tokens, "usage_unknown": res.usage_unknown,
            "first_event_seconds": res.first_event_seconds, "finish_reason": res.finish_reason,
            "response_model": res.response_model, "reasoning_content": res.reasoning_content,
            "reasoning_tokens": res.reasoning_tokens, "attempts": attempts,
            "estimated_input_tokens": est_input,
        }
        jpath.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- prompts -----------------------------------------------------------
    def _files_block(self, snapshot: dict[str, str]) -> str:
        blocks = []
        for rel in sorted(snapshot):
            blocks.append(f"### {rel}\nsha256: {sha256_text(snapshot[rel])}\n```python\n{snapshot[rel]}\n```")
        return "\n\n".join(blocks)

    def _shared_block(self, findings: list[str]) -> str:
        return "\n".join(f"- {f}" for f in findings) if findings else "（暂无）"

    def _plan_block(self, group: str, plan: dict[str, Any] | None, worker: str) -> str:
        if group == "B" and plan is not None:
            return f"## 本轮分工（编排角色给出，仅供你参考）\n{plan_for_worker(plan, worker)}\n"
        return "## 本轮分工\n本轮没有提供任何计划或任务分解。你自行决定本轮做什么工作，并把决定与理由写进 findings。\n"

    def claim_messages(self, task, group, rnd, worker, goal, snapshot, findings, feedback, plan,
                       granted: dict[str, str], messages: list[dict[str, str]]) -> list[dict[str, str]]:
        granted_text = "\n".join(f"- {p} 已被 {w} 认领" for p, w in sorted(granted.items())) or "（本轮暂无可写文件被认领）"
        msg_text = "\n".join(f"- {m['worker']}: {m['text']}" for m in messages) or "（本轮暂无同伴消息）"
        writable_text = ", ".join(writable_paths(snapshot)) or "（无）"
        system = (
            f"你是受控编辑协作实验中的 worker 角色 {worker}，团队为 {worker} 与另一名 worker。"
            "你没有工具也没有会话记忆，只能返回一个 JSON 对象。\n" + PROGRAM_RULES +
            "\n第一阶段：认领与协商。你最多提议认领 1 个可写文件（用相对路径），也可以 claim=null 只复核。\n"
            "message 不超过 240 字符，findings 不超过 3 条、每条不超过 160 字符。\n"
            'JSON schema: {"claim": str|null, "message": str, "findings": [str]}\n'
            "只输出 JSON，不要 Markdown 代码围栏。"
        )
        user = (
            f"## 用户目标\n{goal}\n\n"
            f"## 当前文件（本轮冻结 base）\n{self._files_block(snapshot)}\n\n"
            f"## 共享发现（来自更早轮次）\n{self._shared_block(findings)}\n\n"
            f"## 上一轮程序检查反馈\n{feedback or '（暂无）'}\n\n"
            f"{self._plan_block(group, plan, worker)}\n"
            f"## 程序允许认领/编辑的文件\n{writable_text}\n\n"
            f"## 本轮已认领\n{granted_text}\n\n"
            f"## 本轮同伴已发出的消息\n{msg_text}\n\n"
            "## 你的第一阶段输出\n提议认领（最多 1 个文件）、一条短消息、简短 findings。只返回 JSON。"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def edit_messages(self, task, group, rnd, worker, goal, snapshot, findings, feedback, plan,
                      lease: str | None, granted: dict[str, str],
                      messages: list[dict[str, str]]) -> list[dict[str, str]]:
        granted_text = "\n".join(f"- {p} -> {w}" for p, w in sorted(granted.items())) or "（本轮没有可写文件被认领）"
        msg_text = "\n".join(f"- {m['worker']}: {m['text']}" for m in messages) or "（本轮暂无同伴消息）"
        writable_text = ", ".join(writable_paths(snapshot)) or "（无）"
        lease_text = lease if lease else "（你没有持有任何文件租约；本轮只能复核，edits 必须为 []）"
        system = (
            f"你是受控编辑协作实验中的 worker 角色 {worker}。你没有工具也没有会话记忆，只能返回 JSON。\n" + PROGRAM_RULES +
            "\n第二阶段：编辑或复核。你只能修改本轮由程序授予你的租约文件；返回完整新文件内容，"
            "并携带该文件当前 sha256（base_sha256）。\n"
            "summary 不超过 200 字符，findings 不超过 3 条、每条不超过 160 字符。\n"
            'JSON schema: {"summary": str, "findings": [str], '
            '"edits": [{"path": str, "base_sha256": str, "content": str}]}\n'
            "只输出 JSON，不要 Markdown 代码围栏。"
        )
        user = (
            f"## 用户目标\n{goal}\n\n"
            f"## 当前文件（本轮冻结 base；编辑必须基于此，不得写其他文件）\n{self._files_block(snapshot)}\n\n"
            f"## 共享发现（来自更早轮次）\n{self._shared_block(findings)}\n\n"
            f"## 上一轮程序检查反馈\n{feedback or '（暂无）'}\n\n"
            f"{self._plan_block(group, plan, worker)}\n"
            f"## 程序允许认领/编辑的文件\n{writable_text}\n\n"
            f"## 本轮认领结果\n{granted_text}\n\n"
            f"## 本轮同伴消息\n{msg_text}\n\n"
            f"## 你的租约\n{lease_text}\n\n"
            "## 你的第二阶段输出\n如果你持有租约，提交针对该文件的完整新内容；否则复核并说明发现，edits 必须为 []。只返回 JSON。"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def planner_messages(self, task, goal, snapshot) -> list[dict[str, str]]:
        system = (
            "你是编排角色（planner）。你不修改任何文件，只输出 JSON 计划供两名 worker（w1、w2）执行。\n"
            "不得修改或建议修改验收测试，不得直接给出整个文件实现充当 worker 产出。\n"
            "findings 不超过 3 条、每条不超过 160 字符。\n"
            'JSON schema: {"plan": [{"worker": "w1", "objective": str, "files": [str]}, '
            '{"worker": "w2", "objective": str, "files": [str]}], "interface_notes": str, "findings": [str]}\n'
            "只输出 JSON，不要 Markdown 代码围栏。"
        )
        user = (
            f"## 用户目标\n{goal}\n\n## 当前文件\n{self._files_block(snapshot)}\n\n"
            "## 任务\n为两名 worker 分配本轮工作，尽量给出不重叠的文件与清晰接口约定，"
            "使他们能完成用户目标。注意后续轮次会由程序化认领/同伴协商决定实际写文件的人。只返回 JSON。"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # -- parsing -----------------------------------------------------------
    def parse_claim(self, content: str, worker: str) -> dict[str, Any]:
        obj = extract_json_object(content)
        if obj is None:
            return {"worker": worker, "parse_error": "no_valid_json", "claim": None,
                    "message": "", "findings": []}
        claim = obj.get("claim")
        if claim is not None and not isinstance(claim, str):
            claim = None
        findings = [clip(str(f), FINDING_MAX_CHARS) for f in (obj.get("findings") or [])
                    if isinstance(f, (str, int, float))][:FINDINGS_MAX_ITEMS]
        return {"worker": worker, "parse_error": None, "claim": claim,
                "message": clip(str(obj.get("message") or ""), MESSAGE_MAX_CHARS),
                "findings": findings}

    def parse_edit(self, content: str, worker: str) -> dict[str, Any]:
        obj = extract_json_object(content)
        if obj is None:
            return {"worker": worker, "parse_error": "no_valid_json", "edits": [],
                    "findings": [], "summary": ""}
        edits = obj.get("edits") if isinstance(obj.get("edits"), list) else []
        findings = [clip(str(f), FINDING_MAX_CHARS) for f in (obj.get("findings") or [])
                    if isinstance(f, (str, int, float))][:FINDINGS_MAX_ITEMS]
        return {"worker": worker, "parse_error": None,
                "edits": [e for e in edits if isinstance(e, dict)],
                "findings": findings, "summary": clip(str(obj.get("summary") or ""), 200)}

    def grant_claim(self, claim: str | None, worker: str, granted: dict[str, str],
                    snapshot: dict[str, str]) -> dict[str, Any]:
        if claim is None:
            return {"path": None, "state": "none", "reason": "no_claim"}
        if claim not in writable_paths(snapshot):
            return {"path": None, "state": "rejected", "reason": "invalid_or_unwritable_path"}
        if claim in granted:
            return {"path": None, "state": "rejected", "reason": f"already_claimed_by_{granted[claim]}"}
        granted[claim] = worker
        return {"path": claim, "state": "granted", "reason": "granted"}

    def validate_edits(self, snapshot: dict[str, str], lease: str | None,
                       parsed: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, Any]],
                                                       list[dict[str, Any]]]:
        valid: list[dict[str, str]] = []
        overreach: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        for e in parsed.get("edits", []):
            path = e.get("path")
            if not isinstance(path, str) or path not in snapshot:
                invalid.append({"path": path, "reason": "unknown_or_bad_path"})
                continue
            if lease is None or path != lease:
                overreach.append({"path": path, "reason": "no_lease_for_path",
                                  "lease": lease})
                continue
            if e.get("base_sha256") != sha256_text(snapshot[path]):
                invalid.append({"path": path, "reason": "base_sha256_mismatch"})
                continue
            content = e.get("content")
            if not isinstance(content, str):
                invalid.append({"path": path, "reason": "content_not_string"})
                continue
            if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
                invalid.append({"path": path, "reason": "content_too_large"})
                continue
            if path.endswith(".py"):
                try:
                    compile(content, path, "exec")
                except SyntaxError as exc:
                    invalid.append({"path": path, "reason": f"syntax_error: {exc}"})
                    continue
            valid.append({"path": path, "content": content})
        return valid, overreach, invalid

    # -- SoT ---------------------------------------------------------------
    def append_event(self, run_dir: Path, event: dict[str, Any]) -> None:
        event = dict(event)
        event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        event["run"] = run_dir.name
        with self.lock:
            with (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def write_task(self, run_dir, task, group, init_hash, goal) -> None:
        (run_dir / "TASK.md").write_text(
            "---\n"
            f"run_id: {run_dir.name}\n"
            f"task: {task}\n"
            f"group: {group}\n"
            f"fixture_initial_hash: {init_hash}\n"
            "experiment_schema: agensh-orchestration-r2/v0 (experiment-only)\n"
            "control_writer: driver\n"
            "---\n\n"
            "# TASK\n\n## 用户目标（本轮）\n" + goal + "\n",
            encoding="utf-8")

    def write_run(self, run_dir, group, repeat, round_no, status, base_revision,
                  first_worker) -> None:
        (run_dir / "RUN.md").write_text(
            "---\n"
            f"run_id: {run_dir.name}\n"
            f"group: {group}\n"
            f"repeat: {repeat}\n"
            f"first_worker: {first_worker}\n"
            f"current_round: {round_no}\n"
            f"base_revision: {base_revision}\n"
            f"status: {status}\n"
            "orchestration_scope: " + ("initial_plan_only" if group == "B" else "none") + "\n"
            "control_writer: driver\n"
            "---\n\n"
            "# RUN\n\n"
            f"group={group}; first_worker={first_worker}; rounds=2; workers=2\n",
            encoding="utf-8")

    def write_subtask(self, run_dir, round_no, worker, base_revision, grant,
                      status, note="") -> None:
        sub_dir = run_dir / "subtasks"
        sub_dir.mkdir(parents=True, exist_ok=True)
        path = grant.get("path") or "-"
        (sub_dir / f"r{round_no}-{worker}.md").write_text(
            "---\n"
            f"subtask: {run_dir.name}::r{round_no}::{worker}\n"
            f"worker: {worker}\n"
            f"round: {round_no}\n"
            f"base_revision: {base_revision}\n"
            f"lease_path: {path}\n"
            f"lease_state: {grant.get('state')}\n"
            f"claim_reason: {grant.get('reason')}\n"
            f"status: {status}\n"
            "worker_writes_control_state: false\n"
            "---\n\n"
            f"# SUBTASK r{round_no} {worker}\n\n"
            f"lease={path}; base_revision={base_revision}; {note}\n",
            encoding="utf-8")

    def read_round_leases(self, run_dir: Path, round_no: int) -> dict[str, str]:
        leases: dict[str, str] = {}
        sub_dir = run_dir / "subtasks"
        if not sub_dir.exists():
            return leases
        for p in sorted(sub_dir.glob(f"r{round_no}-*.md")):
            fm = parse_frontmatter(p)
            if fm.get("lease_state") == "granted" and fm.get("lease_path") not in (None, "-"):
                leases[fm["lease_path"]] = fm.get("worker", "")
        return leases

    def check_sot(self, run_dir: Path, results: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        run_fm = parse_frontmatter(run_dir / "RUN.md")
        task_fm = parse_frontmatter(run_dir / "TASK.md")
        if run_fm.get("status") != results.get("status"):
            issues.append(f"RUN.md status {run_fm.get('status')} != results {results.get('status')}")
        if task_fm.get("fixture_initial_hash") != results.get("fixture_initial_hash"):
            issues.append("TASK.md initial hash mismatch")
        events = []
        ev_path = run_dir / "events.jsonl"
        if ev_path.exists():
            for line in ev_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        for ev in events:
            if ev.get("type") == "finding" and ev.get("worker") not in ("w1", "w2", None):
                issues.append(f"finding with unknown worker: {ev.get('worker')}")
            if ev.get("run") != run_dir.name:
                issues.append("event run id mismatch")
            if ev.get("type") == "message" and ev.get("worker") not in ("w1", "w2"):
                issues.append("message with unknown worker")
        # applied files exist
        applied = {p for ev in events if ev.get("type") == "apply" for p in ev.get("applied", [])}
        for rel in applied:
            if not (run_dir / "workspace" / rel).exists():
                issues.append(f"applied file missing: {rel}")
        # event claim grants agree with subtask authority
        for round_no in (1, 2):
            leases = self.read_round_leases(run_dir, round_no)
            if len(set(leases.keys())) != len(leases):
                issues.append(f"round {round_no}: duplicate granted lease paths")
            for _, w in leases.items():
                if w not in ("w1", "w2"):
                    issues.append(f"round {round_no}: lease granted to unknown worker {w}")
        # results proposals vs events claims
        return issues

    # -- round -------------------------------------------------------------
    def run_round(self, task, group, repeat, rnd, run_dir, ws, shared_findings, prev_feedback,
                  plan, goal, first_worker) -> dict[str, Any]:
        round_start = time.monotonic()
        base_snapshot = read_snapshot(ws)
        base_revision = fixture_hash(ws)
        round_result: dict[str, Any] = {
            "round": rnd, "base_revision": base_revision, "first_worker": first_worker,
            "worker_calls": 0, "overreach": [], "invalid_edits": [], "conflicts": [],
            "duplicate_edits": [], "retries": 0, "claims": [], "messages": [], "proposals": [],
            "truncated": [], "acceptance": {"passed": 0, "total": 0, "checks": [],
                                             "error": "not_run"}, "feedback": "",
        }
        order = [first_worker, "w2" if first_worker == "w1" else "w1"]
        self.write_run(run_dir, group, repeat, rnd, "running", base_revision, first_worker)

        # phase 1: sequential claim / message
        granted: dict[str, str] = {}
        messages: list[dict[str, str]] = []
        leases: dict[str, str | None] = {}
        for wid in order:
            logical = f"r{rnd}-claim-{wid}"
            ctx = {"run_id": run_dir.name, "task": task, "group": group, "round": rnd,
                   "worker": wid, "snapshot": base_snapshot, "granted": dict(granted),
                   "run_dir": run_dir, "logical": logical}
            res, attempts = self.call_model(
                self.claim_messages(task, group, rnd, wid, goal, base_snapshot, shared_findings,
                                    prev_feedback, plan, granted, messages),
                "claim", ctx, rnd)
            round_result["worker_calls"] += 1
            round_result["retries"] += max(0, attempts - 1)
            ctx["granted"] = dict(granted)
            parsed = self.parse_claim(res.content, wid) if res.ok else {
                "worker": wid, "parse_error": res.error or "call_failed", "claim": None,
                "message": "", "findings": []}
            grant = self.grant_claim(parsed.get("claim"), wid, granted, base_snapshot)
            leases[wid] = grant["path"]
            self.write_subtask(run_dir, rnd, wid, base_revision, grant,
                               "claimed" if grant["path"] else "reviewing")
            self.append_event(run_dir, {"type": "claim_proposal", "round": rnd, "worker": wid,
                                        "claim": parsed.get("claim")})
            self.append_event(run_dir, {"type": "claim_result", "round": rnd, "worker": wid,
                                        "granted_path": grant["path"], "state": grant["state"],
                                        "reason": grant["reason"]})
            if grant["state"] == "rejected":
                self.append_event(run_dir, {"type": "claim_conflict", "round": rnd, "worker": wid,
                                            "claim": parsed.get("claim"), "reason": grant["reason"]})
                round_result["conflicts"].append(
                    {"round": rnd, "worker": wid, "path": parsed.get("claim"), "reason": grant["reason"]})
            if parsed.get("message"):
                messages.append({"worker": wid, "text": parsed["message"]})
                self.append_event(run_dir, {"type": "message", "round": rnd, "worker": wid,
                                            "text": parsed["message"]})
            for f in parsed.get("findings", []):
                self.append_event(run_dir, {"type": "finding", "round": rnd, "worker": wid,
                                            "text": f, "phase": "claim"})
            round_result["claims"].append({
                "worker": wid, "proposed": parsed.get("claim"), "state": grant["state"],
                "granted_path": grant["path"], "reason": grant["reason"],
                "parse_error": parsed.get("parse_error"), "attempts": attempts,
                "message": parsed.get("message")})
            round_result["messages"].append({"worker": wid, "text": parsed.get("message", "")})
            if self.abort_reason:
                break

        # If the run aborted mid-claim, do not issue the edit phase or acceptance.
        if self.abort_reason:
            round_result["elapsed"] = round(time.monotonic() - round_start, 3)
            return round_result

        # phase 2: parallel edit / review against the frozen base
        proposals: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futs = {}
            for wid in ("w1", "w2"):
                ctx = {"run_id": run_dir.name, "task": task, "group": group, "round": rnd,
                       "worker": wid, "snapshot": base_snapshot, "lease": leases.get(wid),
                       "granted": dict(granted), "messages": list(messages),
                       "run_dir": run_dir, "logical": f"r{rnd}-edit-{wid}"}
                futs[wid] = ex.submit(self._edit_call, task, group, rnd, wid, goal, base_snapshot,
                                      list(shared_findings), prev_feedback, plan, leases.get(wid),
                                      dict(granted), list(messages), ctx)
            for wid in ("w1", "w2"):
                proposals.append(futs[wid].result())
        for p in proposals:
            round_result["worker_calls"] += 1
            round_result["retries"] += max(0, p["attempts"] - 1)

        # program integration (mutual exclusion means at most one writer per path)
        path_props: dict[str, list[dict[str, str]]] = {}
        applied: dict[str, str] = {}
        for p in proposals:
            for e in p["valid_edits"]:
                path_props.setdefault(e["path"], []).append({"worker": p["worker"], "content": e["content"]})
            round_result["overreach"].extend({"worker": p["worker"], **o} for o in p["overreach"])
            round_result["invalid_edits"].extend({"worker": p["worker"], **i} for i in p["invalid"])
            if p.get("parse_error"):
                round_result["invalid_edits"].append({"worker": p["worker"], "reason": p["parse_error"]})
        for path, props in path_props.items():
            if len(props) > 1:
                round_result["duplicate_edits"].append(
                    {"path": path, "workers": [x["worker"] for x in props]})
            contents = {x["content"] for x in props}
            if len(contents) == 1:
                applied[path] = props[0]["content"]
            else:
                round_result["conflicts"].append(
                    {"path": path, "workers": [x["worker"] for x in props], "round": rnd})

        for p in proposals:
            worker_base = dict(base_snapshot)
            for e in p["valid_edits"]:
                worker_base[e["path"]] = e["content"]
            write_files(worker_base, run_dir / "staging" / f"r{rnd}" / p["worker"])
            for o in p["overreach"]:
                self.append_event(run_dir, {"type": "overreach", "round": rnd, "worker": p["worker"],
                                            "path": o.get("path"), "reason": o.get("reason")})
            for i in p["invalid"]:
                self.append_event(run_dir, {"type": "invalid_edit", "round": rnd, "worker": p["worker"],
                                            "path": i.get("path"), "reason": i.get("reason")})
            for f in p["findings"]:
                self.append_event(run_dir, {"type": "finding", "round": rnd, "worker": p["worker"],
                                            "text": f, "phase": "edit"})
            if p["summary"]:
                shared_findings.append(f"{p['worker']}: {p['summary']}")
            # real writer utilisation: did the lease holder actually submit a valid edit?
            round_result["proposals"].append({
                "worker": p["worker"], "lease": leases.get(p["worker"]),
                "wrote": bool(p["valid_edits"]), "summary": p["summary"],
                "findings": p["findings"], "parse_error": p.get("parse_error"),
                "finish_reason": p.get("finish_reason"), "attempts": p["attempts"],
                "valid_edits": [e["path"] for e in p["valid_edits"]],
                "overreach": p["overreach"], "invalid": p["invalid"]})

        integrated = dict(base_snapshot)
        integrated.update(applied)
        write_files(integrated, ws)
        self.append_event(run_dir, {"type": "apply", "round": rnd, "applied": sorted(applied.keys()),
                                    "conflicts": round_result["conflicts"],
                                    "duplicate_edits": round_result["duplicate_edits"],
                                    "invalid": round_result["invalid_edits"]})

        stage = TASKS[task][f"stage{rnd}"]
        acc = self.run_acceptance(task, ws, stage)
        feedback = format_feedback(acc)
        round_result["acceptance"] = acc
        round_result["feedback"] = feedback
        self.append_event(run_dir, {"type": "acceptance", "round": rnd, "stage": stage,
                                    "passed": acc["passed"], "total": acc["total"],
                                    "failed": [c["name"] for c in acc["checks"] if not c["passed"]]})
        # truncation bookkeeping from journal/raw of this round
        round_result["truncated"] = self._round_truncations(run_dir, rnd)
        round_result["elapsed"] = round(time.monotonic() - round_start, 3)
        return round_result

    def _round_truncations(self, run_dir: Path, rnd: int) -> list[dict[str, Any]]:
        out = []
        raw = run_dir / "raw"
        if not raw.exists():
            return out
        for p in sorted(raw.glob(f"*_r{rnd}.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("finish_reason") == "length":
                out.append({"file": p.name, "kind": d.get("kind"), "worker": d.get("worker")})
        return out

    def _edit_call(self, task, group, rnd, wid, goal, base_snapshot, findings, prev_feedback,
                   plan, lease, granted, messages, ctx) -> dict[str, Any]:
        try:
            res, attempts = self.call_model(
                self.edit_messages(task, group, rnd, wid, goal, base_snapshot, findings,
                                   prev_feedback, plan, lease, granted, messages),
                "edit", ctx, rnd)
            parsed = self.parse_edit(res.content, wid) if res.ok else {
                "worker": wid, "parse_error": res.error or "call_failed", "edits": [],
                "findings": [], "summary": ""}
            finish_reason = res.finish_reason
        except Exception as exc:  # noqa: BLE001
            self.append_event(ctx["run_dir"], {"type": "driver_error", "round": rnd,
                                               "where": f"edit:{wid}", "error": str(exc)})
            attempts = 1
            finish_reason = None
            parsed = {"worker": wid, "parse_error": f"driver error: {exc}", "edits": [],
                      "findings": [], "summary": ""}
        valid, overreach, invalid = self.validate_edits(base_snapshot, lease, parsed)
        parsed["valid_edits"] = valid
        parsed["overreach"] = overreach
        parsed["invalid"] = invalid
        parsed["attempts"] = attempts
        parsed["finish_reason"] = finish_reason
        return parsed

    def run_acceptance(self, task, ws, stage) -> dict[str, Any]:
        cmd = [sys.executable, str(FIXTURES / task / "acceptance.py"), "--workspace", str(ws)]
        if stage is not None:
            cmd += ["--stage", str(stage)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=ACCEPT_TIMEOUT,
                                  cwd=str(ws), env=clean_env())
        except subprocess.TimeoutExpired:
            return {"checks": [], "passed": 0, "total": 0, "error": "acceptance timeout"}
        if proc.returncode != 0:
            return {"checks": [], "passed": 0, "total": 0,
                    "error": f"acceptance crash: {proc.stderr[-300:]}"}
        try:
            return json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            return {"checks": [], "passed": 0, "total": 0, "error": "acceptance unparseable"}

    # -- sample ------------------------------------------------------------
    def run_sample(self, spec: dict[str, Any]) -> dict[str, Any]:
        task, group, repeat = spec["task"], spec["group"], spec["repeat"]
        run_id = f"{task}__{group}__r{repeat}"
        run_dir = self.runs_dir / run_id
        if self.args.resume and (run_dir / "results.json").exists():
            existing = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
            if existing.get("completed") or existing.get("status") == "aborted":
                return existing
        if run_dir.exists() and not self.args.resume:
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "raw").mkdir(exist_ok=True)
        ws = run_dir / "workspace"
        # Always rebuild from the frozen fixture. Resume replays already-journaled
        # calls (no new HTTP) and only issues the missing ones, so the workspace
        # is reconstructed deterministically without duplicate requests.
        copy_initial(task, ws)
        init_hash = fixture_hash(ws)
        goal1 = TASKS[task]["goal1"]
        goal2 = TASKS[task]["goal2"]
        first_worker = FIRST_WORKER_BY_REPEAT[repeat]
        self.write_task(run_dir, task, group, init_hash, goal1)
        self.write_run(run_dir, group, repeat, 1, "running", init_hash, first_worker)
        self.append_event(run_dir, {"type": "start", "task": task, "group": group, "repeat": repeat,
                                    "fixture_initial_hash": init_hash, "goal": goal1,
                                    "first_worker": first_worker})

        sample_start = time.monotonic()
        findings: list[str] = []
        prev_feedback = ""
        plan: dict[str, Any] | None = None

        # B: exactly one planner call at the start of the run
        if group == "B":
            snap = read_snapshot(ws)
            ctx = {"run_id": run_id, "task": task, "group": group, "round": 0, "worker": None,
                   "snapshot": snap, "run_dir": run_dir, "logical": "planner"}
            try:
                res, attempts = self.call_model(self.planner_messages(task, goal1, snap),
                                                "planner", ctx, 0)
                parsed = (extract_json_object(res.content) if res.ok else None)
                if parsed and isinstance(parsed.get("plan"), list):
                    plan = parsed
                    self.append_event(run_dir, {"type": "planner_plan", "group": group, "plan": plan})
                    for f in (parsed.get("findings") or [])[:FINDINGS_MAX_ITEMS]:
                        shared_findings.append(f"planner: {clip(str(f), FINDING_MAX_CHARS)}")
                else:
                    self.append_event(run_dir, {"type": "planner_invalid",
                                                "error": res.error or "no_valid_plan"})
            except Exception as exc:  # noqa: BLE001
                self.append_event(run_dir, {"type": "driver_error", "where": "planner",
                                            "error": str(exc)})
            if self.abort_reason:
                return self._finish_aborted(run_dir, task, group, repeat, init_hash, first_worker,
                                            sample_start, None)

        r1 = self.run_round(task, group, repeat, 1, run_dir, ws, findings, prev_feedback, plan,
                            goal1, first_worker)
        if self.abort_reason:
            return self._finish_aborted(run_dir, task, group, repeat, init_hash, first_worker,
                                        sample_start, r1)

        prev_feedback = r1["feedback"]
        self.write_task(run_dir, task, group, init_hash, goal2)
        r2 = self.run_round(task, group, repeat, 2, run_dir, ws, findings, prev_feedback, plan,
                            goal2, first_worker)
        if self.abort_reason:
            return self._finish_aborted(run_dir, task, group, repeat, init_hash, first_worker,
                                        sample_start, r1, r2)

        final_stage = TASKS[task]["stage2"]
        final_acc = self.run_acceptance(task, ws, final_stage)
        total_elapsed = round(time.monotonic() - sample_start, 3)
        retries = r1.get("retries", 0) + r2.get("retries", 0)
        worker_calls = r1.get("worker_calls", 0) + r2.get("worker_calls", 0)
        planner_calls = self._count_raw(run_dir, kind="planner")
        claims = self._count_raw(run_dir, kind="claim")
        edits = self._count_raw(run_dir, kind="edit")
        truncated = r1.get("truncated", []) + r2.get("truncated", [])
        result = {
            "run_id": run_id, "task": task, "group": group, "repeat": repeat,
            "first_worker": first_worker,
            "fixture_initial_hash": init_hash,
            "goal_round1": goal1, "goal_round2": goal2,
            "completed": True, "status": "completed",
            "round1": self._round_summary(r1), "round2": self._round_summary(r2),
            "round1_passed": r1["acceptance"]["passed"], "round1_total": r1["acceptance"]["total"],
            "final_passed": final_acc["passed"], "final_total": final_acc["total"],
            "final_acceptance": final_acc,
            "all_passed": final_acc["passed"] == final_acc["total"] and final_acc["total"] > 0,
            "total_elapsed": total_elapsed,
            "orchestration_elapsed": 0.0,
            "worker_calls": worker_calls, "planner_calls": planner_calls,
            "claim_calls": claims, "edit_calls": edits,
            "retries": retries, "truncated_calls": truncated,
            "sot_issues": [],
        }
        self.write_run(run_dir, group, repeat, 2, "completed", fixture_hash(ws), first_worker)
        self.append_event(run_dir, {"type": "complete", "final_passed": final_acc["passed"],
                                    "final_total": final_acc["total"]})
        result["sot_issues"] = self.check_sot(run_dir, result)
        (run_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        with self.lock:
            self.state["completed"][run_id] = {
                "all_passed": result["all_passed"], "final_passed": result["final_passed"],
                "final_total": result["final_total"], "round1_passed": result["round1_passed"],
                "round1_total": result["round1_total"], "total_elapsed": total_elapsed}
        self._save_state()
        return result

    def _count_raw(self, run_dir: Path, kind: str) -> int:
        raw = run_dir / "raw"
        if not raw.exists():
            return 0
        n = 0
        for p in raw.glob(f"*_{kind}_*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("retry"):
                continue
            n += 1
        return n

    def _round_summary(self, r: dict[str, Any]) -> dict[str, Any]:
        return {
            "passed": r["acceptance"]["passed"], "total": r["acceptance"]["total"],
            "checks": r["acceptance"].get("checks", []),
            "base_revision": r.get("base_revision"), "first_worker": r.get("first_worker"),
            "worker_calls": r.get("worker_calls", 0),
            "conflicts": r.get("conflicts", []), "overreach": r.get("overreach", []),
            "invalid_edits": r.get("invalid_edits", []),
            "duplicate_edits": r.get("duplicate_edits", []),
            "retries": r.get("retries", 0), "proposals": r.get("proposals", []),
            "claims": r.get("claims", []), "messages": r.get("messages", []),
            "feedback": r.get("feedback", ""), "elapsed": r.get("elapsed", 0.0),
            "truncated": r.get("truncated", []),
        }

    def _finish_aborted(self, run_dir, task, group, repeat, init_hash, first_worker,
                        sample_start, r1, r2=None):
        acc1 = (r1 or {}).get("acceptance") or {}
        result = {
            "run_id": run_dir.name, "task": task, "group": group, "repeat": repeat,
            "first_worker": first_worker, "fixture_initial_hash": init_hash,
            "completed": False, "status": "aborted", "abort_reason": self.abort_reason,
            "fatal_protocol": self.fatal_protocol,
            "round1": self._round_summary(r1) if r1 else None,
            "round2": self._round_summary(r2) if r2 else None,
            "round1_passed": acc1.get("passed"), "round1_total": acc1.get("total"),
            "final_passed": None, "final_total": None, "all_passed": False,
            "total_elapsed": round(time.monotonic() - sample_start, 3),
            "orchestration_elapsed": 0.0,
            "worker_calls": (r1 or {}).get("worker_calls", 0),
            "planner_calls": self._count_raw(run_dir, kind="planner"),
            "claim_calls": self._count_raw(run_dir, kind="claim"),
            "edit_calls": self._count_raw(run_dir, kind="edit"),
            "retries": (r1 or {}).get("retries", 0),
            "truncated_calls": (r1 or {}).get("truncated", []),
            "sot_issues": [],
        }
        self.write_run(run_dir, group, repeat, 2 if r2 else 1, "aborted", init_hash, first_worker)
        (run_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        self.append_event(run_dir, {"type": "abort", "reason": self.abort_reason})
        with self.lock:
            self.state["completed"][run_dir.name] = {"all_passed": False, "aborted": True}
        self._save_state()
        return result

    # -- run ---------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        specs = self.state["specs"]
        results = []
        for idx in self.state["order"]:
            spec = specs[idx]
            run_id = f"{spec['task']}__{spec['group']}__r{spec['repeat']}"
            if self.args.resume and self.state["completed"].get(run_id) is not None:
                print(f"[exp] skip completed {run_id}", flush=True)
                continue
            print(f"[exp] running {run_id} ...", flush=True)
            try:
                res = self.run_sample(spec)
            except Exception as exc:  # noqa: BLE001
                self.abort_reason = self.abort_reason or f"driver exception: {exc}"
                self.append_event(self.runs_dir / run_id if (self.runs_dir / run_id).exists()
                                  else self.runs_dir, {"type": "driver_exception", "error": str(exc),
                                                       "trace": traceback.format_exc()[-1500:]})
                break
            results.append(res)
            print(f"[exp]   final {res.get('final_passed')}/{res.get('final_total')} "
                  f"all_passed={res.get('all_passed')} elapsed={res.get('total_elapsed')}s",
                  flush=True)
            if self.abort_reason:
                print(f"[exp] ABORT: {self.abort_reason}", flush=True)
                break
        summary = self.build_summary(self._load_all_results())
        (self.runs_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
        self.state["abort_reason"] = self.abort_reason
        self.state["fatal_protocol"] = self.fatal_protocol
        self._save_state()
        return summary

    def _load_all_results(self) -> list[dict[str, Any]]:
        """Recompute summary inputs from on-disk results (resume-safe)."""
        out: list[dict[str, Any]] = []
        for i in self.state["order"]:
            spec = self.state["specs"][i]
            rid = f"{spec['task']}__{spec['group']}__r{spec['repeat']}"
            p = self.runs_dir / rid / "results.json"
            if p.exists():
                out.append(json.loads(p.read_text(encoding="utf-8")))
        return out

    def build_summary(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        by_group: dict[str, Any] = {}
        for g in ALL_GROUPS:
            rows = [r for r in results if r.get("group") == g]
            by_group[g] = {
                "samples": len(rows),
                "all_passed_samples": sum(1 for r in rows if r.get("all_passed")),
                "sum_final_passed": sum((r.get("final_passed") or 0) for r in rows),
                "sum_final_total": sum((r.get("final_total") or 0) for r in rows),
                "sum_total_elapsed": round(sum(r.get("total_elapsed", 0) or 0 for r in rows), 3),
                "sum_worker_calls": sum(r.get("worker_calls", 0) or 0 for r in rows),
                "sum_planner_calls": sum(r.get("planner_calls", 0) or 0 for r in rows),
                "sum_retries": sum(r.get("retries", 0) or 0 for r in rows),
            }
        return {
            "state": {k: v for k, v in self.state.items() if k not in ("specs", "order")},
            "order": [self.state["specs"][i]["task"] + "__" + self.state["specs"][i]["group"]
                      + "__r" + str(self.state["specs"][i]["repeat"]) for i in self.state["order"]],
            "by_group": by_group, "samples": results, "abort_reason": self.abort_reason,
            "fatal_protocol": self.fatal_protocol,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="offline scripted model, no network")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--runs-dir", default=None)
    args = ap.parse_args()
    if args.runs_dir is None:
        args.runs_dir = str(ROOT / ("runs_mock" if args.mock else "runs"))
    if not args.mock and not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not set in the process environment", file=sys.stderr)
        return 2
    exp = Experiment(args)
    summary = exp.run()
    print(json.dumps({"by_group": summary["by_group"], "abort_reason": summary["abort_reason"],
                      "fatal_protocol": summary.get("fatal_protocol")}, ensure_ascii=False, indent=2))
    return 0 if not summary["abort_reason"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
