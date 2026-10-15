#!/usr/bin/env python3
"""agen/sh orchestration ablation driver.

Controlled editing-collaboration pilot. Groups:
  A = initial plan + post-round-1 replan (<=2 orchestration calls)
  B = initial plan only            (<=1 orchestration call)
  C = no orchestration

Only the orchestration variable changes. Deterministic scheduling, file SoT,
permissions, budget and acceptance are shared. See ../PROTOCOL.md.

The driver implements a *bounded structured file-edit* protocol (model returns
full file contents + brief findings; the program validates path / base hash /
size, merges, runs acceptance). It is NOT a real agent tool loop.

Usage (real pilot):
    DEEPSEEK_API_KEY=... python3 driver/run_pilot.py
Offline self-test (no network):
    python3 driver/run_pilot.py --mock --runs-dir runs_mock
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
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
MAX_TOKENS = 2048
TEMPERATURE = 0.0
FIRST_EVENT_TIMEOUT = 40.0
TOTAL_TIMEOUT = 100.0
ORDER_SEED = 20261015

MAX_NORMAL_CALLS = 45
MAX_RETRIES = 3
MAX_HTTP = 48
MAX_TOTAL_TOKENS = 200000
WALL_SECONDS = 900
ACCEPT_TIMEOUT = 30
MAX_EDIT_BYTES = 20000

ALL_TASKS = ["t1_independent", "t2_interface", "t3_evolving"]
ALL_GROUPS = ["A", "B", "C"]

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
    "t1_independent": {
        "goal1": T1_GOAL,
        "goal2": T1_GOAL,
        "stage1": None,
        "stage2": None,
    },
    "t2_interface": {
        "goal1": T2_GOAL,
        "goal2": T2_GOAL,
        "stage1": None,
        "stage2": None,
    },
    "t3_evolving": {
        "goal1": T3_GOAL1,
        "goal2": T3_GOAL1 + "\n\n" + T3_GOAL2_ADD,
        "stage1": 1,
        "stage2": 2,
    },
}


# ---------------------------------------------------------------------------
# small helpers
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
        rel = path.relative_to(ws).as_posix()
        snap[rel] = path.read_text(encoding="utf-8")
    return snap


def fixture_hash(ws: Path) -> str:
    snap = read_snapshot(ws)
    h = hashlib.sha256()
    for rel in sorted(snap):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(snap[rel].encode("utf-8"))
        h.update(b"\0")
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
                    obj = json.loads(text[start : i + 1])
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


def format_feedback(acc: dict[str, Any]) -> str:
    checks = acc.get("checks", [])
    passed = acc.get("passed", 0)
    total = acc.get("total", 0)
    lines = [f"程序检查结果：{passed}/{total} 项通过。"]
    failed = [c for c in checks if not c.get("passed")]
    for c in failed:
        lines.append(f"- 未通过 {c['name']}: {c.get('detail', '')}")
    if not failed:
        lines.append("- 全部检查通过。")
    return "\n".join(lines)


def plan_for_worker(plan: dict[str, Any] | None, worker: str) -> str:
    if not plan:
        return "（编排未提供有效计划）"
    parts = []
    for item in plan.get("plan") or []:
        if isinstance(item, dict) and item.get("worker") == worker:
            parts.append(
                f"- objective: {item.get('objective', '')}\n  files: {item.get('files', [])}"
            )
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

    def reserve(self, retry: bool) -> str | None:
        with self.lock:
            now = time.time()
            if self.state.get("pilot_start_epoch") is None:
                self.state["pilot_start_epoch"] = now
            if now - self.state["pilot_start_epoch"] > WALL_SECONDS:
                return "wall-clock limit reached"
            if self.state["http_requests"] >= MAX_HTTP:
                return "http request cap reached (48)"
            if self.state["total_tokens"] + MAX_TOKENS > MAX_TOTAL_TOKENS:
                return "token budget would be exceeded (200000)"
            if retry:
                if self.state["retry_calls"] >= MAX_RETRIES:
                    return "retry cap reached (3)"
                self.state["retry_calls"] += 1
            else:
                if self.state["normal_calls"] >= MAX_NORMAL_CALLS:
                    return "normal call cap reached (45)"
                self.state["normal_calls"] += 1
            self.state["http_requests"] += 1
            self._save()
            return None

    def record_usage(self, res: ModelResult) -> None:
        with self.lock:
            if res.usage:
                self.state["total_tokens"] += int(res.usage.get("total_tokens") or 0)
            else:
                self.state["total_tokens"] += res.estimated_tokens
                self.state["usage_unknown_calls"] += 1
            self._save()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# mock model (offline self-test only; never used in the real pilot)
# ---------------------------------------------------------------------------
MOCK_SLUGS = '''import re


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
'''
MOCK_RANGES = '''def clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi) -> bool:
    return lo <= value <= hi
'''
MOCK_GEOMETRY = '''import math


def area(shape):
    if shape["kind"] == "rect":
        return shape["width"] * shape["height"]
    if shape["kind"] == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError(shape["kind"])


def perimeter(shape):
    if shape["kind"] == "rect":
        return 2 * (shape["width"] + shape["height"])
    if shape["kind"] == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError(shape["kind"])
'''
MOCK_REPORT = '''from .geometry import area, perimeter


def describe(shape):
    return f"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"
'''
MOCK_STATS_R1 = '''def mean(nums):
    if not nums:
        raise ValueError("empty")
    return sum(nums) / len(nums)


def median(nums):
    if not nums:
        raise ValueError("empty")
    ordered = sorted(nums)
    n = len(ordered)
    if n % 2:
        return ordered[n // 2]
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2
'''
MOCK_STATS_FINAL = MOCK_STATS_R1 + '''

def mode(nums):
    if not nums:
        raise ValueError("empty")
    counts = {}
    for x in nums:
        counts[x] = counts.get(x, 0) + 1
    best = max(counts.values())
    return min(k for k, v in counts.items() if v == best)


def _stub_stdev(nums):
    return 0.0
'''
MOCK_STATS_WRONG = MOCK_STATS_R1 + '''

def mode(nums):
    return 0


def stdev(nums):
    return 0
'''


class FakeLLM:
    """Scripted model for offline plumbing validation. Exercises retry + conflict."""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def chat(self, messages: list[dict[str, str]], *, kind: str, run_ctx: dict[str, Any]) -> ModelResult:
        with self._lock:
            self.calls += 1
            call_no = self.calls
        task = run_ctx["task"]
        group = run_ctx["group"]
        rnd = run_ctx["round"]
        worker = run_ctx.get("worker")
        snapshot: dict[str, str] = run_ctx["snapshot"]

        # exercise exactly one infrastructure failure + retry (first worker call of t1 w1)
        if (task, group, rnd, kind, worker) == ("t1_independent", "A", 1, "worker", "w1") and call_no < 100:
            if not run_ctx.get("_retried"):
                return ModelResult(ok=False, error="mock transient 503", infra_failure=True,
                                   http_status=503, estimated_tokens=10, usage_unknown=True,
                                   raw_request={"mock": True}, elapsed=0.01)

        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        if kind == "orchestrator":
            plan = self._plan(task)
            content = json.dumps(plan)
        else:
            content = self._worker(task, group, rnd, worker, snapshot)
        return ModelResult(ok=True, content=content, usage=usage, http_status=200,
                           elapsed=0.01, raw_request={"mock": True, "kind": kind},
                           raw_response_text=content, estimated_tokens=150)

    def _plan(self, task: str) -> dict[str, Any]:
        files = {
            "t1_independent": {"w1": ["src/slugs.py"], "w2": ["src/ranges.py"]},
            "t2_interface": {"w1": ["src/geometry.py"], "w2": ["src/report.py"]},
            "t3_evolving": {"w1": ["src/stats.py"], "w2": []},
        }[task]
        return {
            "plan": [
                {"worker": "w1", "objective": "implement assigned module", "files": files["w1"]},
                {"worker": "w2", "objective": "implement assigned module", "files": files["w2"]},
            ],
            "interface_notes": "keep module interfaces stable",
            "findings": ["plan created"],
        }

    def _worker(self, task, group, rnd, worker, snapshot) -> str:
        def out(path: str, content: str) -> str:
            return json.dumps({
                "summary": f"implemented {path}",
                "findings": [f"{worker} touched {path}"],
                "edits": [{"path": path, "base_sha256": sha256_text(snapshot[path]), "content": content}],
            })

        if task == "t1_independent":
            return out("src/slugs.py", MOCK_SLUGS) if worker == "w1" else out("src/ranges.py", MOCK_RANGES)
        if task == "t2_interface":
            return out("src/geometry.py", MOCK_GEOMETRY) if worker == "w1" else out("src/report.py", MOCK_REPORT)
        # t3
        if rnd == 1:
            if worker == "w1":
                return out("src/stats.py", MOCK_STATS_R1)
            return json.dumps({"summary": "no work", "findings": ["nothing to do"], "edits": []})
        if worker == "w1":
            return out("src/stats.py", MOCK_STATS_FINAL)
        # exercise a genuine conflict: w2 proposes different content for the same file
        return out("src/stats.py", MOCK_STATS_WRONG)


# ---------------------------------------------------------------------------
# pilot
# ---------------------------------------------------------------------------
class Pilot:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.mock = args.mock
        self.runs_dir = Path(args.runs_dir).resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.runs_dir / "pilot_state.json"
        self.lock = threading.Lock()
        self.abort_reason: str | None = None
        self.consecutive_infra = 0
        self._seq = 0
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.fake = FakeLLM() if self.mock else None
        self.state = self._load_state()
        self.budget = Budget(self.state, self.state_path, self.lock)

    # -- state -------------------------------------------------------------
    def _load_state(self) -> dict[str, Any]:
        if self.args.resume and self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        order = [[t, g] for t in ALL_TASKS for g in ALL_GROUPS]
        random.Random(ORDER_SEED).shuffle(order)
        return {
            "pilot_start_epoch": None,
            "order": order,
            "completed": {},
            "http_requests": 0,
            "normal_calls": 0,
            "retry_calls": 0,
            "total_tokens": 0,
            "usage_unknown_calls": 0,
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
        )

    def call_model(self, messages, kind, run_ctx, run_dir, round_no) -> tuple[ModelResult, int, str | None]:
        attempts = 0
        while True:
            retry = attempts > 0
            if retry:
                run_ctx = dict(run_ctx)
                run_ctx["_retried"] = True
            err = self.budget.reserve(retry)
            if err:
                self.abort_reason = self.abort_reason or f"budget: {err}"
                return ModelResult(ok=False, error=f"budget: {err}", infra_failure=True,
                                   raw_request={}, usage_unknown=True), attempts, err
            res = self._raw_call(messages, kind, run_ctx)
            self.budget.record_usage(res)
            attempts += 1
            self._write_raw(run_dir, kind, run_ctx, res, retry, round_no)
            if res.ok:
                self.consecutive_infra = 0
                return res, attempts, None
            if not res.infra_failure:
                self.consecutive_infra = 0
                return res, attempts, res.error
            self.consecutive_infra += 1
            if self.consecutive_infra >= 3:
                self.abort_reason = "3 consecutive infrastructure failures"
                return res, attempts, self.abort_reason
            if self.state["retry_calls"] >= MAX_RETRIES:
                return res, attempts, "retry cap reached"

    def _write_raw(self, run_dir: Path, kind: str, run_ctx: dict[str, Any], res: ModelResult,
                   retry: bool, round_no: int) -> None:
        seq = self._next_seq()
        wid = run_ctx.get("worker") or "planner"
        record = {
            "seq": seq,
            "run": run_ctx.get("run_id"),
            "kind": kind,
            "worker": run_ctx.get("worker"),
            "round": round_no,
            "group": run_ctx.get("group"),
            "task": run_ctx.get("task"),
            "model": MODEL,
            "base_url": f"https://{DEFAULT_HOST}{DEFAULT_PATH}",
            "retry": retry,
            "request": res.raw_request,
            "http_status": res.http_status,
            "ok": res.ok,
            "infra_failure": res.infra_failure,
            "error": res.error,
            "elapsed_seconds": round(res.elapsed, 3),
            "first_event_seconds": res.first_event_seconds,
            "usage": res.usage,
            "usage_unknown": res.usage_unknown,
            "estimated_tokens": res.estimated_tokens,
            "response_text": res.raw_response_text,
        }
        raw_dir = run_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        name = f"{seq:03d}_{kind}_{wid}_r{round_no}.json"
        (raw_dir / name).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- prompts -----------------------------------------------------------
    def _files_block(self, snapshot: dict[str, str]) -> str:
        blocks = []
        for rel in sorted(snapshot):
            blocks.append(f"### {rel}\nsha256: {sha256_text(snapshot[rel])}\n```python\n{snapshot[rel]}\n```")
        return "\n\n".join(blocks)

    def worker_messages(self, task, group, rnd, worker, goal, snapshot, findings, feedback, plan):
        system = (
            f"你是受控编辑协作实验中的 worker 角色 {worker}。你没有工具，也没有会话记忆，只能返回一个 JSON 对象。\n"
            "规则：\n"
            "- 只允许修改下面列出的文件；返回“完整的新文件内容”，不是 diff。\n"
            "- 每个 edit 必须携带该文件当前的 sha256（base_sha256），且必须与列出值完全一致。\n"
            "- 不得修改任何控制文件（TASK.md/RUN.md/SUBTASK.md/events.jsonl/验收程序），也不得改计划外文件。\n"
            "- 只输出 JSON，不要 Markdown 代码围栏，不要额外解释。\n"
            'JSON schema: {"summary": str, "findings": [str], '
            '"edits": [{"path": str, "base_sha256": str, "content": str}]}\n'
            "即使本轮不需要改动，也要返回 edits: [] 并在 findings 说明。"
        )
        assignment = plan_for_worker(plan, worker) if plan is not None else None
        if group == "C":
            assignment_section = (
                "## 本轮分工\n本轮没有提供任何计划或任务分解。你自行决定本轮做什么工作，"
                "并把决定与理由写进 findings。\n"
            )
        else:
            assignment_section = f"## 本轮分工（编排角色给出）\n{assignment}\n"
        findings_text = "\n".join(f"- {f}" for f in findings) if findings else "（暂无）"
        feedback_text = feedback or "（暂无）"
        user = (
            f"## 用户目标\n{goal}\n\n"
            f"## 当前文件（本轮 base）\n{self._files_block(snapshot)}\n\n"
            f"## 共享发现（来自更早轮次）\n{findings_text}\n\n"
            f"## 上一轮程序检查反馈\n{feedback_text}\n\n"
            f"{assignment_section}\n"
            "## 输出\n只返回 JSON（schema 见系统提示）。"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def orchestrator_messages(self, task, goal, snapshot, previous) -> list[dict[str, str]]:
        system = (
            "你是编排角色（planner）。你不修改任何文件，只输出 JSON 计划供两名 worker（w1、w2）执行。\n"
            "不得修改或建议修改验收测试，不得直接给出整个文件实现充当 worker 产出。\n"
            'JSON schema: {"plan": [{"worker": "w1", "objective": str, "files": [str]}, '
            '{"worker": "w2", "objective": str, "files": [str]}], "interface_notes": str, "findings": [str]}\n'
            "只输出 JSON，不要 Markdown 代码围栏。"
        )
        user = f"## 用户目标\n{goal}\n\n## 当前文件\n{self._files_block(snapshot)}\n\n"
        if previous:
            user += (
                "## 第一轮执行结果\n"
                f"- w1 summary: {previous.get('w1_summary', '')}\n"
                f"- w1 findings: {previous.get('w1_findings', [])}\n"
                f"- w2 summary: {previous.get('w2_summary', '')}\n"
                f"- w2 findings: {previous.get('w2_findings', [])}\n"
                f"- 程序检查反馈: {previous.get('feedback', '')}\n\n"
            )
        user += (
            "## 任务\n为两名 worker 分配本轮工作，尽量给出不重叠的文件与清晰的接口约定，"
            "使他们能完成用户目标。只返回 JSON。"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # -- parsing -----------------------------------------------------------
    def parse_orchestrator(self, content: str) -> dict[str, Any] | None:
        obj = extract_json_object(content)
        if not obj or not isinstance(obj.get("plan"), list):
            return None
        return obj

    def parse_worker(self, content: str, worker: str) -> dict[str, Any]:
        obj = extract_json_object(content)
        if obj is None:
            return {"worker": worker, "parse_error": "no_valid_json", "edits": [], "findings": [], "summary": ""}
        edits = obj.get("edits")
        if not isinstance(edits, list):
            edits = []
        findings = [str(f) for f in (obj.get("findings") or []) if isinstance(f, (str, int, float))]
        return {
            "worker": worker,
            "parse_error": None,
            "edits": [e for e in edits if isinstance(e, dict)],
            "findings": findings,
            "summary": str(obj.get("summary") or ""),
        }

    # -- one round ---------------------------------------------------------
    def run_round(self, task, group, rnd, run_dir, ws, shared_findings, prev_feedback,
                  plan, previous_info, goal) -> dict[str, Any]:
        round_start = time.monotonic()
        orchestration_elapsed = 0.0
        round_result: dict[str, Any] = {
            "round": rnd, "orchestration_used": False, "orchestration_elapsed": 0.0,
            "worker_calls": 0, "conflicts": [], "duplicate_edits": [], "invalid": [],
            "retries": 0, "feedbacks": [],
        }

        # orchestration
        need_plan = (group == "A" and rnd in (1, 2)) or (group == "B" and rnd == 1)
        if need_plan:
            snap = read_snapshot(ws)
            ctx = {"run_id": run_dir.name, "task": task, "group": group, "round": rnd,
                   "snapshot": snap, "kind": "orchestrator"}
            t0 = time.monotonic()
            try:
                res, attempts, err = self.call_model(
                    self.orchestrator_messages(task, goal, snap, previous_info if rnd == 2 else None),
                    "orchestrator", ctx, run_dir, rnd)
                orchestration_elapsed = time.monotonic() - t0
                parsed = self.parse_orchestrator(res.content) if res.ok else None
            except Exception as exc:  # noqa: BLE001
                orchestration_elapsed = time.monotonic() - t0
                attempts, err, res, parsed = 1, f"driver error: {exc}", None, None
                self.append_event(run_dir, {"type": "driver_error", "round": rnd,
                                            "where": "orchestrator", "error": str(exc)})
            round_result["orchestration_used"] = True
            round_result["orchestration_elapsed"] = round(orchestration_elapsed, 3)
            round_result["retries"] += attempts - 1
            if parsed is None:
                self.append_event(run_dir, {"type": "orchestration_invalid", "round": rnd,
                                            "error": err or (res.error if res else "unknown"), "group": group})
            else:
                plan = parsed
                self.append_event(run_dir, {"type": "orchestration_plan", "round": rnd,
                                            "group": group, "plan": plan})
                for f in parsed.get("findings") or []:
                    shared_findings.append(f"planner: {f}")

        # worker calls (concurrent, collected in w1/w2 order)
        snapshot = read_snapshot(ws)
        proposals: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futs = {}
            for wid in ("w1", "w2"):
                futs[wid] = ex.submit(
                    self._worker_round, task, group, rnd, wid, goal, snapshot,
                    list(shared_findings), prev_feedback, plan, run_dir)
            for wid in ("w1", "w2"):
                proposals.append(futs[wid].result())

        for p in proposals:
            round_result["worker_calls"] += 1
            round_result["retries"] += p["attempts"] - 1

        applied, conflicts, invalid, duplicate, _path_props = self.merge_edits(snapshot, proposals)
        round_result["conflicts"] = conflicts
        round_result["invalid"] = invalid
        round_result["duplicate_edits"] = duplicate

        # staging per worker (isolated checkout)
        for p in proposals:
            worker_base = dict(snapshot)
            for e in p["valid_edits"]:
                worker_base[e["path"]] = e["content"]
            write_files(worker_base, run_dir / "staging" / f"r{rnd}" / p["worker"])

        # integrate
        integrated = dict(snapshot)
        integrated.update(applied)
        write_files(integrated, ws)
        self.append_event(run_dir, {
            "type": "apply", "round": rnd, "applied": sorted(applied.keys()),
            "conflicts": conflicts, "duplicate_edits": duplicate, "invalid": invalid,
        })
        for p in proposals:
            for f in p["findings"]:
                self.append_event(run_dir, {"type": "finding", "round": rnd, "worker": p["worker"],
                                            "text": f})
            if p["summary"]:
                shared_findings.append(f"{p['worker']}: {p['summary']}")

        # acceptance
        stage = TASKS[task][f"stage{rnd}"]
        acc = self.run_acceptance(task, ws, stage)
        feedback = format_feedback(acc)
        round_result["acceptance"] = acc
        round_result["feedback"] = feedback
        self.append_event(run_dir, {"type": "acceptance", "round": rnd, "stage": stage,
                                    "passed": acc["passed"], "total": acc["total"],
                                    "failed": [c["name"] for c in acc["checks"] if not c["passed"]]})
        round_result["previous_info"] = {
            "w1_summary": proposals[0]["summary"], "w1_findings": proposals[0]["findings"],
            "w2_summary": proposals[1]["summary"], "w2_findings": proposals[1]["findings"],
            "feedback": feedback,
        }
        round_result["proposals"] = [
            {"worker": p["worker"], "summary": p["summary"], "findings": p["findings"],
             "parse_error": p["parse_error"], "valid_edits": [e["path"] for e in p["valid_edits"]],
             "attempts": p["attempts"]}
            for p in proposals
        ]
        round_result["elapsed"] = round(time.monotonic() - round_start, 3)
        round_result["plan"] = plan
        return round_result

    def _worker_round(self, task, group, rnd, wid, goal, snapshot, findings, feedback, plan, run_dir):
        ctx = {"run_id": run_dir.name, "task": task, "group": group, "round": rnd,
               "worker": wid, "snapshot": snapshot}
        try:
            res, attempts, err = self.call_model(
                self.worker_messages(task, group, rnd, wid, goal, snapshot, findings, feedback, plan),
                "worker", ctx, run_dir, rnd)
            parsed = self.parse_worker(res.content, wid) if res.ok else {
                "worker": wid, "parse_error": err or res.error or "call_failed",
                "edits": [], "findings": [], "summary": ""}
        except Exception as exc:  # noqa: BLE001
            self.append_event(run_dir, {"type": "driver_error", "round": rnd,
                                        "where": f"worker:{wid}", "error": str(exc)})
            attempts = 1
            parsed = {"worker": wid, "parse_error": f"driver error: {exc}",
                      "edits": [], "findings": [], "summary": ""}
        parsed["attempts"] = attempts
        # validate edits against base hash / path / size
        valid = []
        for e in parsed["edits"]:
            path = e.get("path")
            if not isinstance(path, str) or path not in snapshot:
                parsed.setdefault("invalid", []).append({"path": path, "reason": "unknown_or_bad_path"})
                continue
            if e.get("base_sha256") != sha256_text(snapshot[path]):
                parsed.setdefault("invalid", []).append({"path": path, "reason": "base_sha256_mismatch"})
                continue
            content = e.get("content")
            if not isinstance(content, str):
                parsed.setdefault("invalid", []).append({"path": path, "reason": "content_not_string"})
                continue
            if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
                parsed.setdefault("invalid", []).append({"path": path, "reason": "content_too_large"})
                continue
            valid.append({"path": path, "content": content})
        parsed["valid_edits"] = valid
        return parsed

    def merge_edits(self, base, proposals):
        path_props: dict[str, list[dict[str, str]]] = {}
        invalid: list[dict[str, Any]] = []
        for p in proposals:
            if p.get("parse_error"):
                invalid.append({"worker": p["worker"], "reason": p["parse_error"]})
            for inv in p.get("invalid", []):
                invalid.append({"worker": p["worker"], **inv})
            for e in p.get("valid_edits", []):
                path_props.setdefault(e["path"], []).append({"worker": p["worker"], "content": e["content"]})
        applied: dict[str, str] = {}
        conflicts: list[dict[str, Any]] = []
        duplicate: list[dict[str, Any]] = []
        for path, props in path_props.items():
            if len(props) > 1:
                duplicate.append({"path": path, "workers": [x["worker"] for x in props]})
            contents = {x["content"] for x in props}
            if len(props) == 1 or len(contents) == 1:
                applied[path] = props[0]["content"]
            else:
                conflicts.append({"path": path, "workers": [x["worker"] for x in props]})
        return applied, conflicts, invalid, duplicate, path_props

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
            return {"checks": [], "passed": 0, "total": 0, "error": f"acceptance crash: {proc.stderr[-300:]}"}
        try:
            return json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            return {"checks": [], "passed": 0, "total": 0, "error": "acceptance unparseable"}

    # -- SoT ---------------------------------------------------------------
    def append_event(self, run_dir: Path, event: dict[str, Any]) -> None:
        event = dict(event)
        event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        event["run"] = run_dir.name
        with self.lock:
            with (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def write_sot(self, run_dir, task, group, init_hash, round_no, status, goal, extra=None):
        (run_dir / "TASK.md").write_text(
            "---\n"
            f"run_id: {run_dir.name}\n"
            f"task: {task}\n"
            f"group: {group}\n"
            f"fixture_initial_hash: {init_hash}\n"
            f"status: {status}\n"
            f"experiment_schema: agensh-ablation/v0 (experiment-only, not the product schema)\n"
            "---\n\n"
            "# TASK\n\n"
            "## 用户目标（本轮）\n"
            f"{goal}\n",
            encoding="utf-8")
        (run_dir / "RUN.md").write_text(
            "---\n"
            f"run_id: {run_dir.name}\n"
            f"group: {group}\n"
            f"current_round: {round_no}\n"
            f"status: {status}\n"
            "control_writer: driver\n"
            "---\n\n"
            "# RUN\n\n"
            f"group={group}; orchestration={'yes' if group in ('A', 'B') else 'no'}; rounds=2\n",
            encoding="utf-8")
        sub_lines = []
        for wid in ("w1", "w2"):
            sub_lines.append(
                "---\n"
                f"subtask: {run_dir.name}::{wid}\n"
                f"worker: {wid}\n"
                f"round: {round_no}\n"
                f"worker_writes_control_state: false\n"
                "---\n"
            )
        (run_dir / "SUBTASK.md").write_text("\n".join(sub_lines), encoding="utf-8")

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
            if ev.get("type") == "finding" and ev.get("worker") not in ("w1", "w2"):
                issues.append(f"finding with unknown worker: {ev.get('worker')}")
            if ev.get("run") != run_dir.name:
                issues.append("event run id mismatch")
        applied = {p for ev in events if ev.get("type") == "apply" for p in ev.get("applied", [])}
        for rel in applied:
            if not (run_dir / "workspace" / rel).exists():
                issues.append(f"applied file missing: {rel}")
        return issues

    # -- sample ------------------------------------------------------------
    def run_sample(self, task, group) -> dict[str, Any]:
        run_id = f"{task}__{group}"
        run_dir = self.runs_dir / run_id
        if self.args.resume and (run_dir / "results.json").exists():
            existing = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
            if existing.get("completed"):
                return existing
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        (run_dir / "raw").mkdir()
        ws = run_dir / "workspace"
        copy_initial(task, ws)
        init_hash = fixture_hash(ws)
        goal1 = TASKS[task]["goal1"]
        goal2 = TASKS[task]["goal2"]
        self.write_sot(run_dir, task, group, init_hash, 1, "running", goal1)
        self.append_event(run_dir, {"type": "start", "task": task, "group": group,
                                    "fixture_initial_hash": init_hash, "goal": goal1})

        sample_start = time.monotonic()
        findings: list[str] = []
        prev_feedback = ""
        plan: dict[str, Any] | None = None
        previous_info: dict[str, Any] | None = None
        rounds: dict[str, Any] = {}

        r1 = self.run_round(task, group, 1, run_dir, ws, findings, prev_feedback, plan,
                            previous_info, goal1)
        rounds["round1"] = r1
        if self.abort_reason:
            return self._finish_aborted(run_dir, task, group, init_hash, r1, sample_start)
        plan = r1.get("plan")

        prev_feedback = r1["feedback"]
        previous_info = r1["previous_info"]
        self.write_sot(run_dir, task, group, init_hash, 2, "running", goal2)

        r2 = self.run_round(task, group, 2, run_dir, ws, findings, prev_feedback, plan,
                            previous_info, goal2)
        rounds["round2"] = r2
        if self.abort_reason:
            return self._finish_aborted(run_dir, task, group, init_hash, r1, sample_start, r2)

        final_stage = TASKS[task]["stage2"]
        final_acc = self.run_acceptance(task, ws, final_stage)
        total_elapsed = round(time.monotonic() - sample_start, 3)
        orch_elapsed = round(r1.get("orchestration_elapsed", 0.0) + r2.get("orchestration_elapsed", 0.0), 3)
        retries = r1.get("retries", 0) + r2.get("retries", 0)
        worker_calls = r1.get("worker_calls", 0) + r2.get("worker_calls", 0)
        orch_calls = (1 if r1.get("orchestration_used") else 0) + (1 if r2.get("orchestration_used") else 0)

        result = {
            "run_id": run_id, "task": task, "group": group,
            "fixture_initial_hash": init_hash,
            "goal_round1": goal1, "goal_round2": goal2,
            "completed": True, "status": "completed",
            "round1": self._round_summary(r1),
            "round2": self._round_summary(r2),
            "round1_passed": r1["acceptance"]["passed"], "round1_total": r1["acceptance"]["total"],
            "final_passed": final_acc["passed"], "final_total": final_acc["total"],
            "final_acceptance": final_acc,
            "all_passed": final_acc["passed"] == final_acc["total"] and final_acc["total"] > 0,
            "total_elapsed": total_elapsed,
            "orchestration_elapsed": orch_elapsed,
            "worker_calls": worker_calls,
            "orchestration_calls": orch_calls,
            "retries": retries,
        }
        result["sot_issues"] = []
        self.write_sot(run_dir, task, group, init_hash, 2, "completed", goal2)
        self.append_event(run_dir, {"type": "complete", "final_passed": final_acc["passed"],
                                    "final_total": final_acc["total"]})
        result["sot_issues"] = self.check_sot(run_dir, result)
        (run_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.lock:
            self.state["completed"][run_id] = {
                "all_passed": result["all_passed"],
                "final_passed": result["final_passed"], "final_total": result["final_total"],
                "round1_passed": result["round1_passed"], "round1_total": result["round1_total"],
                "total_elapsed": total_elapsed, "orchestration_elapsed": orch_elapsed,
            }
        self._save_state()
        return result

    def _round_summary(self, r: dict[str, Any]) -> dict[str, Any]:
        return {
            "passed": r["acceptance"]["passed"], "total": r["acceptance"]["total"],
            "checks": r["acceptance"].get("checks", []),
            "orchestration_used": r.get("orchestration_used", False),
            "orchestration_elapsed": r.get("orchestration_elapsed", 0.0),
            "worker_calls": r.get("worker_calls", 0),
            "conflicts": r.get("conflicts", []),
            "duplicate_edits": r.get("duplicate_edits", []),
            "invalid": r.get("invalid", []),
            "retries": r.get("retries", 0),
            "proposals": r.get("proposals", []),
            "feedback": r.get("feedback", ""),
            "elapsed": r.get("elapsed", 0.0),
        }

    def _finish_aborted(self, run_dir, task, group, init_hash, r1, sample_start, r2=None):
        result = {
            "run_id": run_dir.name, "task": task, "group": group,
            "fixture_initial_hash": init_hash, "completed": False, "status": "aborted",
            "abort_reason": self.abort_reason,
            "round1": self._round_summary(r1),
            "round2": self._round_summary(r2) if r2 else None,
            "round1_passed": r1["acceptance"]["passed"], "round1_total": r1["acceptance"]["total"],
            "final_passed": None, "final_total": None, "all_passed": False,
            "total_elapsed": round(time.monotonic() - sample_start, 3),
            "orchestration_elapsed": r1.get("orchestration_elapsed", 0.0),
            "worker_calls": r1.get("worker_calls", 0), "orchestration_calls": 1 if r1.get("orchestration_used") else 0,
            "retries": r1.get("retries", 0), "sot_issues": [],
        }
        (run_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        self.write_sot(run_dir, task, group, init_hash, 1, "aborted", TASKS[task]["goal1"])
        with self.lock:
            self.state["completed"][run_dir.name] = {"all_passed": False, "aborted": True}
        self._save_state()
        return result

    # -- pilot -------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        order = self.state["order"]
        if self.args.tasks:
            order = [p for p in order if p[0] in self.args.tasks]
        if self.args.groups:
            order = [p for p in order if p[1] in self.args.groups]
        results = []
        for task, group in order:
            print(f"[pilot] running {task} / group {group} ...", flush=True)
            res = self.run_sample(task, group)
            results.append(res)
            print(f"[pilot]   final {res.get('final_passed')}/{res.get('final_total')} "
                  f"all_passed={res.get('all_passed')} elapsed={res.get('total_elapsed')}s "
                  f"orch={res.get('orchestration_elapsed')}s", flush=True)
            if self.abort_reason:
                print(f"[pilot] ABORT: {self.abort_reason}", flush=True)
                break
        summary = self.build_summary(results)
        (self.runs_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
        return summary

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
                "sum_orchestration_elapsed": round(sum(r.get("orchestration_elapsed", 0) or 0 for r in rows), 3),
                "sum_worker_calls": sum(r.get("worker_calls", 0) or 0 for r in rows),
                "sum_orchestration_calls": sum(r.get("orchestration_calls", 0) or 0 for r in rows),
                "sum_retries": sum(r.get("retries", 0) or 0 for r in rows),
                "conflicts": sum(len(r.get("round1", {}).get("conflicts", [])) +
                                 len(r.get("round2", {}).get("conflicts", [])) for r in rows),
            }
        return {
            "pilot_state": {k: v for k, v in self.state.items() if k != "order"},
            "order": self.state["order"],
            "by_group": by_group,
            "samples": results,
            "abort_reason": self.abort_reason,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="offline scripted model, no network")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--tasks", nargs="*", default=None)
    ap.add_argument("--groups", nargs="*", default=None)
    args = ap.parse_args()
    if args.runs_dir is None:
        args.runs_dir = str(ROOT / ("runs_mock" if args.mock else "runs"))
    if not args.mock and not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not set in the process environment", file=sys.stderr)
        return 2
    pilot = Pilot(args)
    summary = pilot.run()
    print(json.dumps({"by_group": summary["by_group"], "abort_reason": summary["abort_reason"]},
                     ensure_ascii=False, indent=2))
    return 0 if not summary["abort_reason"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
