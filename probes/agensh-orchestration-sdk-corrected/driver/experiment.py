#!/usr/bin/env python3
"""SDK-round orchestration comparison driver (B vs C) — experiment host.

Groups (single variable = independent orchestration model):
  B = one initial planner SDK turn (structured output) + program claim/peer
  C = no orchestration model + identical program claim/peer

Both groups share: real SDK agent loop via the product AntigravityExecutor,
model/params (unified in the relay), tool permissions, program-mediated claims,
same-round peer messages, per-worker isolated staging, program-only integration,
acceptance, rounds and worker prompts.

Each logical turn is a real ``AntigravityExecutor.execute`` call (except in
``--mock``), so the SDK decides how many upstream HTTP requests a turn needs;
that expansion is metered by the relay and is part of the measured cost.

Usage:
    python3 driver/experiment.py --mode formal    [--runs-dir ...] [--resume]
    python3 driver/experiment.py --mode calibrate
    python3 driver/experiment.py --mode mock      [--runs-dir ...]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
PROBE_ROOT = _HERE.parents[1]
FIXTURES = PROBE_ROOT / "fixtures"
sys.path.insert(0, str(_HERE.parent))

import host as host_mod  # noqa: E402
from host import (  # noqa: E402
    ClaimSchema,
    EditSchema,
    PlanItem,
    PlanSchema,
    SdkHost,
    read_and_purge_secret,
)
from relay import MeteringRelay  # noqa: E402
from sotyaml import dump_frontmatter, is_legal_lease, try_parse_frontmatter_file  # noqa: E402

# ---------------------------------------------------------------------------
# Frozen configuration (see PROTOCOL.md)
# ---------------------------------------------------------------------------
MODEL = "deepseek-v4-flash"
RELAY_UPSTREAM = "https://api.deepseek.com/v1/chat/completions"
MAX_MODEL_CALLS_PER_TURN = 6
MAX_TOOL_CALLS_PER_TURN = 8
TURN_TIMEOUT = 90.0
MAX_EDIT_BYTES = 20000
MESSAGE_MAX_CHARS = 240
FINDINGS_MAX_ITEMS = 3
FINDING_MAX_CHARS = 160
ACCEPT_TIMEOUT = 30
# Corrected hard bounds (formal).  Calibration uses its own bounded driver.
FORMAL_HTTP_CAP = 220
FORMAL_TOKEN_CAP = 1_300_000
FORMAL_WALL_SECONDS = 900
ORDER_SEED = 20261015
INFRA_RETRY_MAX = 6
MAX_CONSECUTIVE_INFRA = 3
FIRST_WORKER_BY_REPEAT = {0: "w1", 1: "w2"}
ALL_TASKS = ["t1_independent", "t2_interface", "t3_evolving"]
ALL_GROUPS = ["B", "C"]

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
- 每轮每名 worker 最多持有 1 个可写文件的租约（程序原子检查/授予，先到先得）。
- 已被他人认领的文件不能再认领；拿不到租约时只能复核并留言。
- 只有持有租约的文件才能被修改；修改其他文件属于越权，程序拒绝整合。
- 每轮每文件只允许一名 writer；本轮编辑都基于同一个冻结 base，由程序整合并验收。
- 不得修改或建议修改 TASK/RUN/subtask/events/测试/验收。
"""

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
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            snap[path.relative_to(ws).as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
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
    base = {p.relative_to(initial).as_posix(): p.read_text(encoding="utf-8")
            for p in initial.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    write_files(base, ws)


WRITABLE_EXCLUDE_BASENAMES = {"__init__.py"}


def writable_paths(snapshot: dict[str, str]) -> list[str]:
    return [rel for rel in sorted(snapshot) if Path(rel).name not in WRITABLE_EXCLUDE_BASENAMES]


def clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…[clipped]"


def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


# ---------------------------------------------------------------------------
# mock host (offline protocol test only; never used for real evidence)
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


class MockHost:
    """Scripted offline model.  Writes files directly to staging (mock only)."""

    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = artifact_dir
        self.calls = 0

    def plan(self, task: str) -> dict[str, Any]:
        files = {
            "t1_independent": {"w1": ["src/slugs.py"], "w2": ["src/ranges.py"]},
            "t2_interface": {"w1": ["src/geometry.py"], "w2": ["src/report.py"]},
            "t3_evolving": {"w1": ["src/stats.py"], "w2": []},
        }[task]
        return {"plan": [
            {"worker": "w1", "objective": "implement assigned module", "files": files["w1"]},
            {"worker": "w2", "objective": "implement/verify assigned module", "files": files["w2"]},
        ], "interface_notes": "keep interfaces stable", "findings": ["plan created"]}

    def claim(self, task: str, worker: str, granted: dict[str, str]) -> dict[str, Any]:
        desired = {
            "t1_independent": {"w1": "src/slugs.py", "w2": "src/ranges.py"},
            "t2_interface": {"w1": "src/geometry.py", "w2": "src/report.py"},
            "t3_evolving": {"w1": "src/stats.py", "w2": None},
        }[task][worker]
        claim = desired if (desired and desired not in granted) else None
        return {"claim": claim, "message": f"{worker} proposes {claim or 'review only'}",
                "findings": [f"{worker} claim {claim or 'none'}"]}

    def edit(self, task: str, rnd: int, worker: str, lease: str | None,
             staging: Path, snapshot: dict[str, str], base_snapshot: dict[str, str]) -> dict[str, Any]:
        if lease is None:
            return {"summary": "review only", "findings": [f"{worker} reviewed"]}
        if task == "t1_independent":
            content = MOCK_SLUGS if lease.endswith("slugs.py") else MOCK_RANGES
        elif task == "t2_interface":
            content = MOCK_GEOMETRY if lease.endswith("geometry.py") else MOCK_REPORT
        else:
            content = MOCK_STATS_R1 if rnd == 1 else MOCK_STATS_FINAL_STDEV
        target = staging / lease
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"summary": f"implemented {lease}", "findings": [f"{worker} touched {lease}"]}


# ---------------------------------------------------------------------------
# experiment
# ---------------------------------------------------------------------------
class Budget:
    def __init__(self, *, http_cap: int, token_cap: int, wall_seconds: float) -> None:
        self.http_cap = http_cap
        self.token_cap = token_cap
        self.wall_seconds = wall_seconds
        self.http_used = 0
        self.tokens_used = 0
        self.tokens_unknown = 0
        self.wall_start: float | None = None
        self.lock = asyncio.Lock()

    def start_wall(self) -> None:
        if self.wall_start is None:
            self.wall_start = time.monotonic()

    def wall_used(self) -> float:
        return 0.0 if self.wall_start is None else time.monotonic() - self.wall_start

    def check(self) -> str | None:
        if self.http_used >= self.http_cap:
            return f"HTTP cap reached ({self.http_cap})"
        if self.tokens_used >= self.token_cap:
            return f"token cap reached ({self.token_cap})"
        if self.wall_start is not None and self.wall_used() > self.wall_seconds:
            return f"wall-clock cap reached ({self.wall_seconds}s)"
        return None

    def charge(self, *, http: int, usage: dict[str, Any] | None, est_tokens: int) -> None:
        self.http_used += http
        total = None
        if isinstance(usage, dict):
            try:
                total = int(usage.get("total_tokens") or 0)
            except (TypeError, ValueError):
                total = None
            if not total:
                total = None
        if total is None:
            self.tokens_unknown += 1
            self.tokens_used += est_tokens  # conservative reserve
        else:
            self.tokens_used += total


class Experiment:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.mock = args.mode == "mock"
        self.mode = args.mode
        self.runs_dir = Path(args.runs_dir).resolve() if args.runs_dir else (
            PROBE_ROOT / "runs" / ({"mock": "mock", "calibrate": "calibration"}.get(args.mode, "formal"))
        )
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.resume = bool(args.resume)
        self.abort_reason: str | None = None
        self.consecutive_infra = 0
        self.infra_retries = 0
        self.credential = ""
        if not self.mock:
            self.credential = read_and_purge_secret()
            if not self.credential:
                raise SystemExit("DEEPSEEK_API_KEY not present in the process environment")
        self.relay: MeteringRelay | None = None
        self.relay_start_log: list[dict[str, Any]] = []
        self.order_plan: dict[str, Any] | None = None

    # ------------------------------------------------------------- budget cfg
    def _budget(self) -> Budget:
        return Budget(http_cap=FORMAL_HTTP_CAP, token_cap=FORMAL_TOKEN_CAP,
                      wall_seconds=FORMAL_WALL_SECONDS)

    # ---------------------------------------------------------------- specs
    def _specs(self) -> list[dict[str, Any]]:
        reps = 1 if self.args.single else (2 if self.args.repeats is None else self.args.repeats)
        specs = [{"task": t, "group": g, "repeat": r}
                 for t in ALL_TASKS for g in ALL_GROUPS for r in range(reps)]
        return specs

    def _order(self, specs: list[dict[str, Any]]) -> list[int]:
        """Fixed-pair randomised order: random task-class order, random B/C order
        per class, recorded seed.  Workers are kept in the same order within a pair."""

        rng = random.Random(ORDER_SEED)
        by_task: dict[str, list[int]] = {}
        for idx, spec in enumerate(specs):
            by_task.setdefault(spec["task"], []).append(idx)
        task_order = list(by_task.keys())
        rng.shuffle(task_order)
        self.order_plan = {"seed": ORDER_SEED, "task_order": task_order, "group_order": {}}
        ordered: list[int] = []
        for task in task_order:
            idxs = by_task[task]
            groups = sorted({specs[i]["group"] for i in idxs})
            rng.shuffle(groups)
            self.order_plan["group_order"][task] = groups
            for group in groups:
                ordered.extend(i for i in idxs if specs[i]["group"] == group)
        return ordered

    # ------------------------------------------------------------ prompts
    def _files_block(self, snapshot: dict[str, str]) -> str:
        blocks = []
        for rel in sorted(snapshot):
            blocks.append(f"### {rel}\nsha256: {sha256_text(snapshot[rel])}\n```python\n{snapshot[rel]}\n```")
        return "\n\n".join(blocks)

    def _plan_block(self, group: str, plan: dict[str, Any] | None, worker: str) -> str:
        if group == "B" and plan is not None:
            parts = []
            for item in plan.get("plan") or []:
                if isinstance(item, dict) and item.get("worker") == worker:
                    parts.append(f"- objective: {item.get('objective', '')}\n  files: {item.get('files', [])}")
            notes = plan.get("interface_notes")
            if notes:
                parts.append(f"- interface_notes: {notes}")
            text = "\n".join(parts) if parts else "（计划中没有为该 worker 指定条目，请自行按目标选择工作）"
            pid = plan.get("plan_id", "")
            return f"## 本轮分工（编排角色给出，仅供参考）\nplan_id: {pid}\n{text}\n"
        return "## 本轮分工\n本轮没有提供任何计划或任务分解。你自行决定本轮做什么工作，并把决定与理由写进 findings。\n"

    def _claim_objective(self, task, group, rnd, worker, goal, snapshot, findings, feedback,
                         plan, granted, messages) -> str:
        granted_text = "\n".join(f"- {p} 已被 {w} 认领" for p, w in sorted(granted.items())) or "（本轮暂无可写文件被认领）"
        msg_text = "\n".join(f"- {m['worker']}: {m['text']}" for m in messages) or "（本轮暂无同伴消息）"
        writable_text = ", ".join(writable_paths(snapshot)) or "（无）"
        return (
            f"## 用户目标\n{goal}\n\n"
            f"## 当前文件（本轮冻结 base）\n{self._files_block(snapshot)}\n\n"
            f"## 共享发现（来自更早轮次）\n{self._shared_block(findings)}\n\n"
            f"## 上一轮程序检查反馈\n{feedback or '（暂无）'}\n\n"
            f"{self._plan_block(group, plan, worker)}\n"
            f"## 程序允许认领/编辑的文件\n{writable_text}\n\n"
            f"## 本轮已认领\n{granted_text}\n\n"
            f"## 本轮同伴已发出的消息\n{msg_text}\n\n"
            "## 你的第一阶段输出\n请先 view_file 查看需要的文件，然后用 finish 返回 JSON："
            '{"claim": <一个相对路径或 null>, "message": <不超过240字符>, "findings": [<短句>]}。'
        )

    def _edit_objective(self, task, group, rnd, worker, goal, snapshot, findings, feedback,
                        plan, lease, granted, messages) -> str:
        granted_text = "\n".join(f"- {p} -> {w}" for p, w in sorted(granted.items())) or "（本轮没有可写文件被认领）"
        msg_text = "\n".join(f"- {m['worker']}: {m['text']}" for m in messages) or "（本轮暂无同伴消息）"
        writable_text = ", ".join(writable_paths(snapshot)) or "（无）"
        if lease:
            lease_text = (f"你持有文件租约：{lease}\n请用文件工具实际写入/修改该文件（不要只返回文本），"
                          "完成后用 finish 返回 JSON。")
        else:
            lease_text = ("你没有持有任何文件租约；本轮只能 view_file 复核，"
                          "不得写入任何文件，用 finish 返回 JSON。")
        return (
            f"## 用户目标\n{goal}\n\n"
            f"## 当前文件（本轮冻结 base）\n{self._files_block(snapshot)}\n\n"
            f"## 共享发现（来自更早轮次）\n{self._shared_block(findings)}\n\n"
            f"## 上一轮程序检查反馈\n{feedback or '（暂无）'}\n\n"
            f"{self._plan_block(group, plan, worker)}\n"
            f"## 程序允许认领/编辑的文件\n{writable_text}\n\n"
            f"## 本轮认领结果\n{granted_text}\n\n"
            f"## 本轮同伴消息\n{msg_text}\n\n"
            f"## 你的租约\n{lease_text}\n\n"
            '## 你的第二阶段输出\n完成后用 finish 返回 JSON：{"summary": <短句>, "findings": [<短句>]}。'
        )

    def _planner_objective(self, task, goal, snapshot) -> str:
        writable = ", ".join(writable_paths(snapshot)) or "（无）"
        return (
            f"## 用户目标\n{goal}\n\n## 当前文件\n{self._files_block(snapshot)}\n\n"
            f"## 当前可写文件（必须逐一分配，每项最多 1 个）\n{writable}\n\n"
            "## 任务\n为两名 worker（w1、w2）各给一个条目；每个可写文件恰好分给一个 worker；"
            "没有分到文件的 worker 是评审者，files 必须为 []。只返回结构化结果，不要写实现代码。"
            "严格使用键 worker/objective/files；禁止额外键；objective 为简短非空文本。"
        )

    def _shared_block(self, findings: list[str]) -> str:
        return "\n".join(f"- {f}" for f in findings) if findings else "（暂无）"

    # ------------------------------------------------------------- persistence
    def _write_json(self, path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _append_event(self, run_dir: Path, event: dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("ts", now_utc())
        event.setdefault("run", run_dir.name)
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _write_task(self, run_dir: Path, task, group, init_hash, goal) -> None:
        (run_dir / "TASK.md").write_text(dump_frontmatter(
            {
                "run_id": run_dir.name, "task": task, "group": group,
                "fixture_initial_hash": init_hash,
                "experiment_schema": "agensh-orchestration-sdk/v1 (experiment-only)",
                "control_writer": "driver",
            },
            f"# TASK\n\n## 用户目标（本轮）\n{goal}\n"), encoding="utf-8")

    def _write_run(self, run_dir: Path, group, repeat, round_no, status, base_revision, first_worker) -> None:
        (run_dir / "RUN.md").write_text(dump_frontmatter(
            {
                "run_id": run_dir.name, "group": group, "repeat": repeat,
                "first_worker": first_worker, "current_round": round_no,
                "base_revision": base_revision, "status": status,
                "orchestration_scope": "initial_plan_only" if group == "B" else "none",
                "control_writer": "driver",
            },
            f"# RUN\n\ngroup={group}; first_worker={first_worker}; rounds=2; workers=2\n"), encoding="utf-8")

    def _write_subtask(self, run_dir: Path, round_no, worker, base_revision, grant, status, note="") -> None:
        sub_dir = run_dir / "subtasks"
        sub_dir.mkdir(parents=True, exist_ok=True)
        lease_path = grant.get("path")  # None -> legal YAML null
        (sub_dir / f"r{round_no}-{worker}.md").write_text(dump_frontmatter(
            {
                "subtask": f"{run_dir.name}::r{round_no}::{worker}",
                "worker": worker, "round": round_no, "base_revision": base_revision,
                "lease_path": lease_path, "lease_state": grant.get("state"),
                "claim_reason": grant.get("reason"), "status": status,
                "worker_writes_control_state": False,
            },
            f"# SUBTASK r{round_no} {worker}\n\nlease={lease_path}; base_revision={base_revision}; {note}\n",
        ), encoding="utf-8")

    # ------------------------------------------------------------- grant/validate
    def grant_claim(self, claim: Any, worker: str, granted: dict[str, str], snapshot: dict[str, str]) -> dict[str, Any]:
        if claim is None:
            return {"path": None, "state": "none", "reason": "no_claim"}
        if not isinstance(claim, str) or claim not in writable_paths(snapshot):
            return {"path": None, "state": "rejected", "reason": "invalid_or_unwritable_path"}
        if claim in granted:
            return {"path": None, "state": "rejected", "reason": f"already_claimed_by_{granted[claim]}"}
        granted[claim] = worker
        return {"path": claim, "state": "granted", "reason": "granted"}

    def validate_plan(self, plan: Any, snapshot: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
        """Strict program validation of a planner plan.

        Uses the restricted pydantic ``PlanSchema`` (extra keys forbidden,
        ``worker`` literal, ->1 file per assignment) *and* program checks:
        exactly w1+w2, every writable file assigned exactly once, no shared
        writer.  Any issue makes the plan invalid (``None``).
        """

        if not isinstance(plan, dict):
            return None, ["plan_not_a_dict"]
        try:
            model = PlanSchema.model_validate(plan)
        except Exception as exc:  # noqa: BLE001 - report and reject
            detail = []
            errors = getattr(exc, "errors", None)
            if callable(errors):
                try:
                    detail = [str(e.get("msg", e)) for e in errors()][:4]
                except Exception:  # noqa: BLE001
                    detail = [str(exc)]
            return None, [f"plan_schema_invalid:{type(exc).__name__}", *detail]

        issues: list[str] = []
        writable = set(writable_paths(snapshot))
        workers = [item.worker for item in model.plan]
        if sorted(workers) != ["w1", "w2"]:
            issues.append(f"plan_workers_not_exactly_w1_w2:{workers}")
        seen: dict[str, str] = {}
        assigned: list[str] = []
        for item in model.plan:
            if len(item.files) > 1:
                issues.append(f"plan_multiple_files:{item.worker}")
            for path in item.files:
                if path not in writable:
                    issues.append(f"plan_unwritable_file:{path}")
                    continue
                if path in seen:
                    issues.append(f"plan_shared_writer:{path}")
                    continue
                seen[path] = item.worker
                assigned.append(path)
        if set(assigned) != writable:
            issues.append(f"plan_files_not_covered:{sorted(writable - set(assigned))}")
        if issues:
            return None, issues

        cleaned_items = [
            {"worker": item.worker, "objective": item.objective, "files": list(item.files)}
            for item in model.plan
        ]
        canonical = json.dumps(
            {"plan": cleaned_items, "interface_notes": model.interface_notes},
            ensure_ascii=False, sort_keys=True,
        )
        plan_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return {
            "plan": cleaned_items,
            "interface_notes": model.interface_notes,
            "findings": [str(x) for x in model.findings][:FINDINGS_MAX_ITEMS],
            "plan_id": plan_id,
            "plan_canonical": canonical,
        }, []

    def _validate_edits(self, base: dict[str, str], lease: str | None, staging: dict[str, str]) -> dict[str, Any]:
        produced = [p for p in staging if p not in base]
        modified = [p for p in staging if p in base and staging[p] != base[p]]
        removed = [p for p in base if p not in staging]
        changed = sorted(set(produced) | set(modified))
        accepted: dict[str, str] = {}
        overreach: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        for path in changed:
            if lease is None or path != lease:
                overreach.append({"path": path, "reason": "no_lease_for_path", "lease": lease})
                continue
            content = staging[path]
            if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
                invalid.append({"path": path, "reason": "content_too_large"})
                continue
            if path.endswith(".py"):
                try:
                    compile(content, path, "exec")
                except SyntaxError as exc:
                    invalid.append({"path": path, "reason": f"syntax_error: {exc}"})
                    continue
            accepted[path] = content
        for path in removed:
            invalid.append({"path": path, "reason": "deletion_not_allowed"})
        return {"produced": produced, "modified": modified, "removed": removed,
                "accepted": accepted, "overreach": overreach, "invalid": invalid}

    # ------------------------------------------------------------- acceptance
    def run_acceptance(self, task: str, ws: Path, stage) -> dict[str, Any]:
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
        except (json.JSONDecodeError, IndexError):
            return {"checks": [], "passed": 0, "total": 0, "error": "acceptance unparseable"}

    def format_feedback(self, acc: dict[str, Any]) -> str:
        checks = acc.get("checks", [])
        lines = [f"程序检查结果：{acc.get('passed', 0)}/{acc.get('total', 0)} 项通过。"]
        failed = [c for c in checks if not c.get("passed")]
        for c in failed:
            lines.append(f"- 未通过 {c['name']}: {clip(str(c.get('detail', '')), 200)}")
        if not failed:
            lines.append("- 全部检查通过。")
        return "\n".join(lines)

    # ------------------------------------------------------------- turn runner
    async def _run_real_turn(self, host: SdkHost, *, agent_ref, workspace, objective,
                             schema, allowed_tools, logical, run_dir, save_dir,
                             write_lease=None, plan_id=None) -> dict[str, Any]:
        before = host_relay_count(self.relay)
        self._append_event(run_dir, {"type": "turn_start", "logical": logical,
                                     "agent_ref": agent_ref, "workspace": str(workspace),
                                     "write_lease": write_lease})
        turn = await host.run_turn(
            credential=self.credential, agent_ref=agent_ref, workspace=workspace,
            objective=objective, response_schema=schema, allowed_tools=allowed_tools,
            timeout_seconds=TURN_TIMEOUT, save_dir=save_dir,
            max_model_calls=MAX_MODEL_CALLS_PER_TURN, max_tool_calls=MAX_TOOL_CALLS_PER_TURN,
            write_lease=write_lease,
        )
        turn["plan_id"] = plan_id
        turn["plan_injected"] = (f"plan_id: {plan_id}" in objective) if plan_id else None
        turn["stop_positive"] = bool((turn.get("stop_evidence") or {}).get("positive"))
        if not turn["stop_positive"] and not self.mock:
            self.abort_reason = self.abort_reason or f"stop unconfirmed at {logical}"
        turn["logical"] = logical
        turn["relay_calls"] = self.relay.call_records()[before:] if self.relay else []
        turn["relay_http"] = len(turn["relay_calls"])
        turn["reported_tokens"] = sum(int((c.get("usage") or {}).get("total_tokens") or 0)
                                      for c in turn["relay_calls"])
        self._write_json(run_dir / "turns" / f"{logical}.json", turn)
        self._append_event(run_dir, {"type": "turn_end", "logical": logical, "state": turn["state"],
                                     "http": turn["relay_http"], "tokens": turn["reported_tokens"],
                                     "tool_calls": turn["tool_call_names"]})
        return turn

    # ------------------------------------------------------------- phases
    async def _claim_phase(self, *, task, group, repeat, rnd, run_dir, host, ws, goal,
                           shared_findings, prev_feedback, plan, first_worker, budget,
                           round_result) -> tuple[dict[str, str], dict[str, str | None], list[dict[str, str]]]:
        base_snapshot = read_snapshot(ws)
        base_revision = fixture_hash(ws)
        order = [first_worker, "w2" if first_worker == "w1" else "w1"]
        granted: dict[str, str] = {}
        leases: dict[str, str | None] = {}
        messages: list[dict[str, str]] = []
        for wid in order:
            logical = f"r{rnd}-claim-{wid}"
            err = budget.check()
            if err:
                self.abort_reason = self.abort_reason or f"budget: {err}"
                break
            objective = self._claim_objective(task, group, rnd, wid, goal, base_snapshot,
                                              shared_findings, prev_feedback, plan, granted, messages)
            budget.start_wall()
            if self.mock:
                turn = self._mock_turn("claim", task=task, rnd=rnd, worker=wid, run_dir=run_dir,
                                       logical=logical, lease=None, granted=granted,
                                       snapshot=base_snapshot, base_snapshot=base_snapshot)
            else:
                turn = await self._run_real_turn(host, agent_ref="claim-worker", workspace=ws,
                                                 objective=objective, schema=ClaimSchema,
                                                 allowed_tools=("view-file",), logical=logical,
                                                 run_dir=run_dir, save_dir=run_dir / "sessions" / logical,
                                                 plan_id=(plan or {}).get("plan_id") if isinstance(plan, dict) else None)
            budget.charge(http=turn.get("relay_http", 0), usage=self._turn_usage(turn),
                          est_tokens=self._estimate_turn_tokens(objective))
            round_result["turns"].append(self._turn_summary(turn))
            parsed = turn.get("finish_payload") or {}
            claim = parsed.get("claim") if isinstance(parsed, dict) else None
            if not isinstance(claim, str):
                claim = None
            grant = self.grant_claim(claim, wid, granted, base_snapshot)
            leases[wid] = grant["path"]
            self._write_subtask(run_dir, rnd, wid, base_revision, grant,
                                "claimed" if grant["path"] else "reviewing")
            self._append_event(run_dir, {"type": "claim_result", "round": rnd, "worker": wid,
                                         "proposed": claim, "granted_path": grant["path"],
                                         "state": grant["state"], "reason": grant["reason"]})
            if grant["state"] == "rejected":
                round_result["conflicts"].append({"round": rnd, "worker": wid, "path": claim,
                                                  "reason": grant["reason"]})
            msg = parsed.get("message") if isinstance(parsed, dict) else ""
            msg = clip(str(msg or ""), MESSAGE_MAX_CHARS)
            if msg:
                messages.append({"worker": wid, "text": msg})
                self._append_event(run_dir, {"type": "message", "round": rnd, "worker": wid, "text": msg})
            findings = parsed.get("findings") if isinstance(parsed, dict) else []
            for f in (findings or [])[:FINDINGS_MAX_ITEMS]:
                self._append_event(run_dir, {"type": "finding", "round": rnd, "worker": wid,
                                             "text": clip(str(f), FINDING_MAX_CHARS), "phase": "claim"})
            round_result["claims"].append({"worker": wid, "proposed": claim, "state": grant["state"],
                                           "granted_path": grant["path"], "reason": grant["reason"],
                                           "message": msg, "turn_state": turn.get("state")})
            round_result["messages"].append({"worker": wid, "text": msg})
        round_result["base_revision"] = base_revision
        return granted, leases, messages

    async def _edit_phase(self, *, task, group, repeat, rnd, run_dir, host, ws, goal,
                          shared_findings, prev_feedback, plan, granted, leases, messages,
                          budget, round_result) -> dict[str, str]:
        base_snapshot = read_snapshot(ws)
        base_revision = fixture_hash(ws)
        accepted: dict[str, str] = {}
        writer_reports: list[dict[str, Any]] = []
        for wid in ("w1", "w2"):
            err = budget.check()
            if err:
                self.abort_reason = self.abort_reason or f"budget: {err}"
                break
            logical = f"r{rnd}-edit-{wid}"
            staging = run_dir / "staging" / f"r{rnd}" / wid
            write_files(base_snapshot, staging)
            lease = leases.get(wid)
            objective = self._edit_objective(task, group, rnd, wid, goal, base_snapshot,
                                             shared_findings, prev_feedback, plan, lease, granted, messages)
            budget.start_wall()
            if self.mock:
                turn = self._mock_turn("edit", task=task, rnd=rnd, worker=wid, run_dir=run_dir,
                                       logical=logical, lease=lease, granted=granted,
                                       snapshot=base_snapshot, base_snapshot=base_snapshot,
                                       staging=staging)
            else:
                turn = await self._run_real_turn(host, agent_ref="edit-worker", workspace=staging,
                                                 objective=objective, schema=EditSchema,
                                                 allowed_tools=("view-file", "create-file", "edit-file"),
                                                 logical=logical, run_dir=run_dir,
                                                 save_dir=run_dir / "sessions" / logical,
                                                 write_lease=lease,
                                                 plan_id=(plan or {}).get("plan_id") if isinstance(plan, dict) else None)
            budget.charge(http=turn.get("relay_http", 0), usage=self._turn_usage(turn),
                          est_tokens=self._estimate_turn_tokens(objective))
            round_result["turns"].append(self._turn_summary(turn))
            staging_snapshot = read_snapshot(staging)
            validation = self._validate_edits(base_snapshot, lease, staging_snapshot)
            report = {"worker": wid, "lease": lease, "turn_state": turn.get("state"),
                      "finish_payload": turn.get("finish_payload"),
                      "tool_call_names": turn.get("tool_call_names"),
                      "covered_tool_calls": turn.get("tool_calls"),
                      "hook_decisions": turn.get("hook_decisions"),
                      "produced": validation["produced"], "modified": validation["modified"],
                      "removed": validation["removed"], "accepted": sorted(validation["accepted"].keys()),
                      "overreach": validation["overreach"], "invalid": validation["invalid"],
                      "http": turn.get("relay_http"), "tokens": turn.get("reported_tokens")}
            writer_reports.append(report)
            for o in validation["overreach"]:
                round_result["overreach"].append({"worker": wid, **o})
                self._append_event(run_dir, {"type": "overreach", "round": rnd, "worker": wid,
                                             "path": o.get("path"), "reason": o.get("reason")})
            for i in validation["invalid"]:
                round_result["invalid_edits"].append({"worker": wid, **i})
                self._append_event(run_dir, {"type": "invalid_edit", "round": rnd, "worker": wid,
                                             "path": i.get("path"), "reason": i.get("reason")})
            for path, content in validation["accepted"].items():
                if path in accepted and accepted[path] != content:
                    round_result["conflicts"].append({"path": path, "workers": [wid], "round": rnd})
                    continue
                accepted[path] = content
            for f in (turn.get("finish_payload") or {}).get("findings", [])[:FINDINGS_MAX_ITEMS] if isinstance(turn.get("finish_payload"), dict) else []:
                self._append_event(run_dir, {"type": "finding", "round": rnd, "worker": wid,
                                             "text": clip(str(f), FINDING_MAX_CHARS), "phase": "edit"})
            summary = (turn.get("finish_payload") or {}).get("summary") if isinstance(turn.get("finish_payload"), dict) else None
            if summary:
                shared_findings.append(f"{wid}: {clip(str(summary), 160)}")
            # persist staging for evidence
            self._write_json(run_dir / "turns" / f"{logical}.validate.json", validation)
        round_result["writer_reports"] = writer_reports
        return accepted

    def _mock_turn(self, kind, *, task, rnd, worker, run_dir, logical, lease, granted,
                   snapshot, base_snapshot, staging=None) -> dict[str, Any]:
        mock = self._mock
        if kind == "claim":
            payload = mock.claim(task, worker, granted)
        elif kind == "planner":
            payload = mock.plan(task)
        else:
            payload = mock.edit(task, rnd, worker, lease, staging, snapshot, base_snapshot)
            # simulate a tool call + finish
        return {
            "state": "succeeded", "summary": "mock", "stop_reason": "STOP_REASON_FINISH",
            "stop_confirmed": None, "failure": None,
            "usage": {"prompt_tokens": 100, "candidates_tokens": 50, "total_tokens": 150,
                      "unknown": []},
            "model": MODEL, "upstream_model": MODEL, "elapsed_seconds": 0.01,
            "tool_calls": ([{"name": "finish", "args": {"output_string": json.dumps(payload)}}]
                           if kind != "edit" else
                           [{"name": "edit_file", "args": {"file_path": str(staging / lease) if lease else ""}},
                            {"name": "finish", "args": {"output_string": json.dumps(payload)}}]),
            "tool_call_names": ["finish"] if kind != "edit" else ["edit_file", "finish"],
            "finish_payload": payload, "finish_parse_error": None,
            "structured_repr": repr(payload), "text": "", "hook_decisions": [],
            "tool_observations": [], "session_ref": {"session_id": "mock", "conversation_id": "mock",
                                                      "state": "created", "save_dir": None},
            "model_sent": MODEL, "logical": logical, "relay_calls": [], "relay_http": 1,
            "reported_tokens": 150,
        }

    # ------------------------------------------------------------- sample
    async def run_sample(self, spec: dict[str, Any]) -> dict[str, Any]:
        task, group, repeat = spec["task"], spec["group"], spec["repeat"]
        run_id = f"{task}__{group}__r{repeat}"
        run_dir = self.runs_dir / run_id
        if self.resume and (run_dir / "results.json").exists():
            existing = read_json(run_dir / "results.json", {})
            if existing.get("completed") or existing.get("status") == "aborted":
                return existing
        if run_dir.exists() and not self.resume:
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        ws = run_dir / "workspace"
        copy_initial(task, ws)
        init_hash = fixture_hash(ws)
        goal1 = TASKS[task]["goal1"]
        goal2 = TASKS[task]["goal2"]
        first_worker = FIRST_WORKER_BY_REPEAT[repeat]
        self._write_task(run_dir, task, group, init_hash, goal1)
        self._write_run(run_dir, group, repeat, 1, "running", init_hash, first_worker)
        self._append_event(run_dir, {"type": "start", "task": task, "group": group,
                                     "repeat": repeat, "fixture_initial_hash": init_hash,
                                     "first_worker": first_worker})

        budget = self._budget()
        if self.mock:
            host = None
            self._mock = MockHost(run_dir / "artifacts")
        else:
            host = SdkHost(run_dir / "sdkdata", self.relay.base_url, workspace_root=run_dir)
            self._mock = None

        shared_findings: list[str] = []
        prev_feedback = ""
        plan: dict[str, Any] | None = None
        sample_start = time.monotonic()

        # B: exactly one planner SDK turn
        if group == "B":
            logical = "planner"
            base_snapshot = read_snapshot(ws)
            objective = self._planner_objective(task, goal1, base_snapshot)
            budget.start_wall()
            if self.mock:
                turn = self._mock_turn("planner", task=task, rnd=0, worker=None, run_dir=run_dir,
                                       logical=logical, lease=None, granted={},
                                       snapshot=base_snapshot, base_snapshot=base_snapshot)
            else:
                turn = await self._run_real_turn(host, agent_ref="planner", workspace=ws,
                                                 objective=objective, schema=PlanSchema,
                                                 allowed_tools=("view-file",), logical=logical,
                                                 run_dir=run_dir, save_dir=run_dir / "sessions" / logical)
                budget.charge(http=turn.get("relay_http", 0), usage=self._turn_usage(turn),
                              est_tokens=self._estimate_turn_tokens(objective))
            self._write_json(run_dir / "turns" / "planner.summary.json", self._turn_summary(turn))
            raw_plan = turn.get("finish_payload")
            valid_plan, issues = self.validate_plan(raw_plan, base_snapshot)
            plan = valid_plan
            self._append_event(run_dir, {"type": "planner_plan" if plan else "planner_invalid",
                                         "plan": plan, "issues": issues,
                                         "plan_id": (plan or {}).get("plan_id"),
                                         "turn_state": turn.get("state"),
                                         "finish_source": turn.get("finish_source"),
                                         "finish_chars": turn.get("finish_payload_chars")})
            if plan:
                for f in (plan.get("findings") or [])[:FINDINGS_MAX_ITEMS]:
                    shared_findings.append(f"planner: {clip(str(f), FINDING_MAX_CHARS)}")
            else:
                # Corrected validity precondition: an invalid B plan invalidates
                # the baseline.  Never silently continue C with plan=None.
                self.abort_reason = self.abort_reason or "baseline_invalid: B planner plan invalid"
            if self.abort_reason:
                return self._finish_aborted(run_dir, task, group, repeat, init_hash,
                                            first_worker, sample_start, plan, None, budget)

        round_results = []
        for rnd, goal in ((1, goal1), (2, goal2)):
            round_result: dict[str, Any] = {
                "round": rnd, "turns": [], "claims": [], "messages": [],
                "overreach": [], "invalid_edits": [], "conflicts": [], "writer_reports": [],
            }
            granted, leases, messages = await self._claim_phase(
                task=task, group=group, repeat=repeat, rnd=rnd, run_dir=run_dir, host=host, ws=ws,
                goal=goal, shared_findings=shared_findings, prev_feedback=prev_feedback,
                plan=plan, first_worker=first_worker, budget=budget, round_result=round_result)
            if self.abort_reason:
                round_results.append(round_result)
                return self._finish_aborted(run_dir, task, group, repeat, init_hash,
                                            first_worker, sample_start, plan, round_results, budget)
            accepted = await self._edit_phase(
                task=task, group=group, repeat=repeat, rnd=rnd, run_dir=run_dir, host=host, ws=ws,
                goal=goal, shared_findings=shared_findings, prev_feedback=prev_feedback,
                plan=plan, granted=granted, leases=leases, messages=messages,
                budget=budget, round_result=round_result)
            if self.abort_reason:
                round_results.append(round_result)
                return self._finish_aborted(run_dir, task, group, repeat, init_hash,
                                            first_worker, sample_start, plan, round_results, budget)
            integrated = dict(read_snapshot(ws))
            integrated.update(accepted)
            write_files(integrated, ws)
            self._append_event(run_dir, {"type": "apply", "round": rnd, "applied": sorted(accepted)})
            stage = TASKS[task][f"stage{rnd}"]
            acc = self.run_acceptance(task, ws, stage)
            round_result["acceptance"] = acc
            round_result["feedback"] = self.format_feedback(acc)
            round_result["elapsed"] = round(time.monotonic() - sample_start, 3)
            self._append_event(run_dir, {"type": "acceptance", "round": rnd, "stage": stage,
                                         "passed": acc["passed"], "total": acc["total"],
                                         "failed": [c["name"] for c in acc["checks"] if not c["passed"]]})
            prev_feedback = round_result["feedback"]
            round_results.append(round_result)

        final_acc = self.run_acceptance(task, ws, TASKS[task]["stage2"])
        self._write_run(run_dir, group, repeat, 2, "completed", fixture_hash(ws), first_worker)
        all_turns = [t for rr in round_results for t in rr.get("turns", [])]
        injection_checks = [t.get("plan_injected") for t in all_turns if t.get("plan_injected") is not None]
        result = {
            "run_id": run_id, "task": task, "group": group, "repeat": repeat,
            "first_worker": first_worker, "fixture_initial_hash": init_hash,
            "mode": self.mode, "completed": True, "status": "completed",
            "plan_valid": plan is not None if group == "B" else None,
            "plan_id": (plan or {}).get("plan_id") if group == "B" and plan else None,
            "plan_injection": {
                "checked": len(injection_checks),
                "all_true": bool(injection_checks) and all(injection_checks),
            } if group == "B" else None,
            "stop_all_positive": all(t.get("stop_positive") for t in all_turns) if all_turns else False,
            "finish_lossless": all(
                (t.get("finish_parse_error") is None and not t.get("emitted_truncated"))
                for t in all_turns
            ) if all_turns else False,
            "rounds": round_results,
            "round1_passed": round_results[0]["acceptance"].get("passed"),
            "round1_total": round_results[0]["acceptance"].get("total"),
            "final_passed": final_acc.get("passed"), "final_total": final_acc.get("total"),
            "final_acceptance": final_acc,
            "all_passed": final_acc.get("passed") == final_acc.get("total") and final_acc.get("total", 0) > 0,
            "total_elapsed": round(time.monotonic() - sample_start, 3),
            "budget": {"http_used": budget.http_used, "tokens_used": budget.tokens_used,
                       "tokens_unknown_calls": budget.tokens_unknown,
                       "wall_used": round(budget.wall_used(), 3)},
        }
        self._append_event(run_dir, {"type": "complete", "final_passed": final_acc.get("passed"),
                                     "final_total": final_acc.get("total")})
        result["sot_issues"] = self.check_sot(run_dir, result)
        self._write_json(run_dir / "results.json", result)
        return result

    async def run_sample_guard(self, spec: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.run_sample(spec)
        except Exception as exc:  # noqa: BLE001
            self.abort_reason = self.abort_reason or f"driver exception: {exc}"
            rid = f"{spec['task']}__{spec['group']}__r{spec['repeat']}"
            run_dir = self.runs_dir / rid
            run_dir.mkdir(parents=True, exist_ok=True)
            self._append_event(run_dir, {"type": "driver_exception", "error": str(exc)})
            return {"run_id": rid, "completed": False, "status": "error", "error": str(exc),
                    "all_passed": False}

    # ------------------------------------------------------------- turn utils
    @staticmethod
    def _turn_usage(turn: dict[str, Any]) -> dict[str, Any] | None:
        return turn.get("usage")

    @staticmethod
    def _estimate_turn_tokens(objective: str) -> int:
        # Conservative reserve when usage is missing (prompt chars/4 + full output).
        return int(len(objective) / 4) + 8192

    @staticmethod
    def _turn_summary(turn: dict[str, Any]) -> dict[str, Any]:
        return {
            "logical": turn.get("logical"), "state": turn.get("state"),
            "stop_reason": turn.get("stop_reason"), "http": turn.get("relay_http"),
            "tokens": turn.get("reported_tokens"), "usage": turn.get("usage"),
            "tool_call_names": turn.get("tool_call_names"),
            "captured_call_names": turn.get("captured_call_names"),
            "finish_parse_error": turn.get("finish_parse_error"),
            "finish_source": turn.get("finish_source"),
            "finish_payload_chars": turn.get("finish_payload_chars"),
            "emitted_finish_chars": turn.get("emitted_finish_chars"),
            "emitted_truncated": turn.get("emitted_truncated"),
            "session_db_matches_hook": turn.get("session_db_matches_hook"),
            "plan_id": turn.get("plan_id"), "plan_injected": turn.get("plan_injected"),
            "stop_positive": turn.get("stop_positive"),
            "stop_evidence": turn.get("stop_evidence"),
            "hook_decisions": turn.get("hook_decisions"),
            "model_sent": turn.get("model_sent"), "upstream_model": turn.get("upstream_model"),
            "elapsed_seconds": turn.get("elapsed_seconds"),
        }

    # ------------------------------------------------------------- aborted
    def _finish_aborted(self, run_dir, task, group, repeat, init_hash, first_worker,
                        sample_start, plan, round_results, budget) -> dict[str, Any]:
        self._write_run(run_dir, group, repeat, len(round_results or []) or 1, "aborted",
                        fixture_hash(run_dir / "workspace"), first_worker)
        self._append_event(run_dir, {"type": "abort", "reason": self.abort_reason})
        all_turns = [t for rr in (round_results or []) for t in rr.get("turns", [])]
        injection_checks = [t.get("plan_injected") for t in all_turns if t.get("plan_injected") is not None]
        result = {
            "run_id": run_dir.name, "task": task, "group": group, "repeat": repeat,
            "first_worker": first_worker, "fixture_initial_hash": init_hash,
            "mode": self.mode, "completed": False, "status": "aborted",
            "abort_reason": self.abort_reason,
            "plan_valid": plan is not None if group == "B" else None,
            "plan_id": (plan or {}).get("plan_id") if group == "B" and plan else None,
            "plan_injection": {
                "checked": len(injection_checks),
                "all_true": bool(injection_checks) and all(injection_checks),
            } if group == "B" else None,
            "stop_all_positive": all(t.get("stop_positive") for t in all_turns) if all_turns else None,
            "finish_lossless": all(
                (t.get("finish_parse_error") is None and not t.get("emitted_truncated"))
                for t in all_turns
            ) if all_turns else None,
            "rounds": round_results or [], "all_passed": False,
            "final_passed": None, "final_total": None,
            "total_elapsed": round(time.monotonic() - sample_start, 3),
            "budget": {"http_used": budget.http_used, "tokens_used": budget.tokens_used,
                       "tokens_unknown_calls": budget.tokens_unknown,
                       "wall_used": round(budget.wall_used(), 3)},
        }
        self._write_json(run_dir / "results.json", result)
        return result

    # ------------------------------------------------------------- SoT check
    def check_sot(self, run_dir: Path, result: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        task_fm, err = try_parse_frontmatter_file(run_dir / "TASK.md")
        if err:
            issues.append(f"TASK.md YAML: {err}")
        run_fm, err = try_parse_frontmatter_file(run_dir / "RUN.md")
        if err:
            issues.append(f"RUN.md YAML: {err}")
        if run_fm.get("status") != result.get("status"):
            issues.append(f"RUN.md status {run_fm.get('status')} != result {result.get('status')}")
        if task_fm.get("fixture_initial_hash") != result.get("fixture_initial_hash"):
            issues.append("TASK.md fixture hash mismatch")
        parsed_leases: dict[int, dict[str, str]] = {1: {}, 2: {}}
        for p in sorted((run_dir / "subtasks").glob("*.md")):
            fm, err = try_parse_frontmatter_file(p)
            if err:
                issues.append(f"{p.name} YAML: {err}")
                continue
            if not is_legal_lease(fm.get("lease_path")):
                issues.append(f"{p.name}: illegal lease_path {fm.get('lease_path')!r}")
            rnd = fm.get("round")
            if fm.get("lease_state") == "granted":
                if not isinstance(fm.get("lease_path"), str):
                    issues.append(f"{p.name}: granted without string lease_path")
                elif rnd in parsed_leases:
                    parsed_leases[rnd][fm["lease_path"]] = str(fm.get("worker"))
            if fm.get("worker") not in ("w1", "w2"):
                issues.append(f"{p.name}: bad worker {fm.get('worker')!r}")
        # events
        event_leases: dict[int, dict[str, str]] = {1: {}, 2: {}}
        events = []
        ev_path = run_dir / "events.jsonl"
        if ev_path.exists():
            for line in ev_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    issues.append("events.jsonl: invalid JSON line")
                    continue
                events.append(ev)
                if ev.get("run") != run_dir.name:
                    issues.append("event run id mismatch")
                if ev.get("type") == "claim_result" and ev.get("state") == "granted":
                    rnd = ev.get("round")
                    if rnd in event_leases and isinstance(ev.get("granted_path"), str):
                        event_leases[rnd][ev["granted_path"]] = str(ev.get("worker"))
                if ev.get("type") == "finding" and ev.get("worker") not in ("w1", "w2", None):
                    issues.append("finding with unknown worker")
        for rnd in (1, 2):
            if parsed_leases[rnd] != event_leases[rnd]:
                issues.append(f"round {rnd}: parsed lease authority != event claims "
                              f"({parsed_leases[rnd]} vs {event_leases[rnd]})")
        applied = {p for ev in events if ev.get("type") == "apply" for p in ev.get("applied", [])}
        for rel in applied:
            if not (run_dir / "workspace" / rel).exists():
                issues.append(f"applied file missing: {rel}")
        return issues

    # ------------------------------------------------------------- run all
    async def run(self) -> dict[str, Any]:
        specs = self._specs()
        order = self._order(specs)
        results: list[dict[str, Any]] = []
        if self.mock:
            self.relay = None
        else:
            self.relay = MeteringRelay(upstream_url=RELAY_UPSTREAM)
            self.relay.start()
        try:
            for idx in order:
                spec = specs[idx]
                run_id = f"{spec['task']}__{spec['group']}__r{spec['repeat']}"
                if self.resume and (self.runs_dir / run_id / "results.json").exists():
                    prev = read_json(self.runs_dir / run_id / "results.json", {})
                    if prev.get("completed") or prev.get("status") == "aborted":
                        print(f"[exp] skip completed {run_id}", flush=True)
                        results.append(prev)
                        continue
                print(f"[exp] running {run_id} ...", flush=True)
                res = await self.run_sample_guard(spec)
                results.append(res)
                print(f"[exp]   final {res.get('final_passed')}/{res.get('final_total')} "
                      f"all_passed={res.get('all_passed')} elapsed={res.get('total_elapsed')}s "
                      f"http={res.get('budget', {}).get('http_used')} "
                      f"tokens={res.get('budget', {}).get('tokens_used')}", flush=True)
                if self.abort_reason:
                    print(f"[exp] ABORT: {self.abort_reason}", flush=True)
                    break
        finally:
            if self.relay is not None:
                self.relay.stop()
        summary = self.build_summary(results)
        self._write_json(self.runs_dir / "summary.json", summary)
        return summary

    def build_summary(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        by_group: dict[str, Any] = {}
        for g in ALL_GROUPS:
            rows = [r for r in results if r.get("group") == g]
            by_group[g] = {
                "samples": len(rows),
                "completed": sum(1 for r in rows if r.get("completed")),
                "all_passed_samples": sum(1 for r in rows if r.get("all_passed")),
                "valid_plans": sum(1 for r in rows if r.get("plan_valid") is True),
                "plan_injection_all_true": sum(
                    1 for r in rows if (r.get("plan_injection") or {}).get("all_true")),
                "stop_all_positive": sum(1 for r in rows if r.get("stop_all_positive")),
                "finish_lossless": sum(1 for r in rows if r.get("finish_lossless")),
                "sum_final_passed": sum((r.get("final_passed") or 0) for r in rows),
                "sum_final_total": sum((r.get("final_total") or 0) for r in rows),
                "sum_http": sum((r.get("budget") or {}).get("http_used", 0) for r in rows),
                "sum_tokens": sum((r.get("budget") or {}).get("tokens_used", 0) for r in rows),
                "sum_elapsed": round(sum(r.get("total_elapsed", 0) or 0 for r in rows), 3),
                "sot_issue_runs": sum(1 for r in rows if r.get("sot_issues")),
            }
        return {
            "mode": self.mode, "model": MODEL, "relay_upstream": RELAY_UPSTREAM,
            "prereg": {
                "http_cap": FORMAL_HTTP_CAP, "token_cap": FORMAL_TOKEN_CAP,
                "wall_seconds": FORMAL_WALL_SECONDS,
            },
            "order_plan": self.order_plan,
            "by_group": by_group, "samples": results,
            "abort_reason": self.abort_reason,
            "relay_total_calls": self.relay.call_count if self.relay else 0,
            "relay_total_tokens": self.relay.total_reported_tokens() if self.relay else 0,
        }


def host_relay_count(relay: MeteringRelay | None) -> int:
    return relay.call_count if relay else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mock", "formal"], default="formal")
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--repeats", type=int, default=None)
    ap.add_argument("--single", action="store_true", help="one repeat per class/group (6 runs)")
    args = ap.parse_args()
    exp = Experiment(args)
    summary = asyncio.run(exp.run())
    print(json.dumps({"mode": summary["mode"], "by_group": summary["by_group"],
                      "abort_reason": summary["abort_reason"],
                      "relay_total_calls": summary["relay_total_calls"],
                      "relay_total_tokens": summary["relay_total_tokens"]},
                     ensure_ascii=False, indent=2))
    return 0 if not summary["abort_reason"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
