#!/usr/bin/env python3
"""Finalizer offline recheck (NO network, NO model calls).

Added by the integration/finalization step, separate from the original experiment
driver. It re-derives the pilot metrics from raw usage, checks the 9 samples'
SoT consistency and links, scans the real artifacts for sensitive material, and
statically compares the protocol's acceptance-item counts with ``acceptance.py``.

Run from the probe root:
    python3 evidence/finalize/offline_recheck.py
"""
from __future__ import annotations

import ast
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
DOCS = ["REPORT.md", "README.md", "PROTOCOL.md"]

fails: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" :: {detail}" if detail else ""))
    if not cond:
        fails.append(label)


# --------------------------------------------------------------------------
# 1. Recompute metrics from raw usage
# --------------------------------------------------------------------------
raw_files = sorted(RUNS.glob("*__*/raw/*.json"))
check(len(raw_files) == 45, "raw call files == 45", str(len(raw_files)))

tot = {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0,
       "reasoning_tokens": 0, "cache_hit_tokens": 0}
retries = 0
usage_unknown = 0
truncated = 0
groups: dict[str, dict] = {g: {"samples": set(), "tokens": 0, "all_passed": 0,
                               "final_passed": 0, "final_total": 0,
                               "truncated": 0, "reasoning": 0,
                               "worker_calls": 0, "orchestration_calls": 0}
                           for g in "ABC"}
for f in raw_files:
    d = json.loads(f.read_text(encoding="utf-8"))
    g = d["group"]
    u = d.get("usage") or {}
    tt = int(u.get("total_tokens") or 0)
    reasoning = int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    comp = int(u.get("completion_tokens") or 0)
    tot["total_tokens"] += tt
    tot["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
    tot["completion_tokens"] += comp
    tot["reasoning_tokens"] += reasoning
    tot["cache_hit_tokens"] += int(u.get("prompt_cache_hit_tokens") or 0)
    if d.get("retry"):
        retries += 1
    if d.get("usage_unknown"):
        usage_unknown += 1
    if comp >= 2048:
        truncated += 1
        groups[g]["truncated"] += 1
    groups[g]["samples"].add(d["run"])
    groups[g]["tokens"] += tt
    groups[g]["reasoning"] += reasoning
    if d.get("kind") == "orchestrator":
        groups[g]["orchestration_calls"] += 1
    else:
        groups[g]["worker_calls"] += 1

check(tot["total_tokens"] == 106949, "recomputed total_tokens == 106949", str(tot["total_tokens"]))
check(retries == 0, "recomputed retry raw calls == 0", str(retries))
check(usage_unknown == 0, "recomputed usage_unknown calls == 0", str(usage_unknown))
check(truncated == 6, "recomputed truncated calls == 6", str(truncated))
check(tot["reasoning_tokens"] == 24966 and tot["completion_tokens"] == 55199,
      "reasoning 24966 / completion 55199",
      f'{tot["reasoning_tokens"]}/{tot["completion_tokens"]}')

summary = json.loads((RUNS / "summary.json").read_text(encoding="utf-8"))
ps = summary["pilot_state"]
check(ps["normal_calls"] == 45, "summary normal_calls == 45", str(ps["normal_calls"]))
check(ps["http_requests"] == 45, "summary http_requests == 45", str(ps["http_requests"]))
check(ps["total_tokens"] == 106949, "summary total_tokens == 106949", str(ps["total_tokens"]))
check(ps["retry_calls"] == 0, "summary retry_calls == 0", str(ps["retry_calls"]))
check(ps["usage_unknown_calls"] == 0, "summary usage_unknown_calls == 0", str(ps["usage_unknown_calls"]))
check(ps["total_tokens"] == tot["total_tokens"], "raw sum == summary total_tokens")

for r in summary["samples"]:
    g = r["group"]
    groups[g]["all_passed"] += 1 if r["all_passed"] else 0
    groups[g]["final_passed"] += r["final_passed"] or 0
    groups[g]["final_total"] += r["final_total"] or 0

expected = {"A": (2, 17, 21, 48907), "B": (3, 21, 21, 34589), "C": (1, 6, 21, 23453)}
for g in "ABC":
    ap, fp, ft, tok = expected[g]
    check(groups[g]["all_passed"] == ap and groups[g]["final_passed"] == fp
          and groups[g]["final_total"] == ft and groups[g]["tokens"] == tok,
          f"group {g}: all_passed={ap}/3, final={fp}/{ft}, tokens={tok}",
          f'all={groups[g]["all_passed"]}, final={groups[g]["final_passed"]}/{groups[g]["final_total"]}, '
          f'tokens={groups[g]["tokens"]}, worker_calls={groups[g]["worker_calls"]}, '
          f'orch_calls={groups[g]["orchestration_calls"]}, truncated={groups[g]["truncated"]}')

# --------------------------------------------------------------------------
# 2. SoT consistency + link integrity for the 9 samples
# --------------------------------------------------------------------------
def parse_frontmatter(p: Path) -> dict[str, str]:
    txt = p.read_text(encoding="utf-8")
    if not txt.startswith("---"):
        return {}
    fm: dict[str, str] = {}
    for line in txt.split("---", 2)[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


run_dirs = sorted(d for d in RUNS.iterdir() if d.is_dir() and "__" in d.name)
check(len(run_dirs) == 9, "9 run dirs", str(len(run_dirs)))
sot_bad = 0
for d in run_dirs:
    name = d.name
    issues: list[str] = []
    res = json.loads((d / "results.json").read_text(encoding="utf-8"))
    task_fm = parse_frontmatter(d / "TASK.md")
    run_fm = parse_frontmatter(d / "RUN.md")
    if task_fm.get("fixture_initial_hash") != res.get("fixture_initial_hash"):
        issues.append("TASK hash != results hash")
    if run_fm.get("status") != res.get("status"):
        issues.append("RUN status != results status")
    sub = (d / "SUBTASK.md").read_text(encoding="utf-8")
    if "worker_writes_control_state: false" not in sub:
        issues.append("worker control-state flag missing")
    for m in re.finditer(r"worker: (\S+)", sub):
        if m.group(1) not in ("w1", "w2"):
            issues.append(f"bad subtask worker {m.group(1)}")
    evs = [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for ev in evs:
        if ev.get("run") != name:
            issues.append("event run mismatch")
        if ev.get("type") == "finding" and ev.get("worker") not in ("w1", "w2"):
            issues.append("finding with bad worker")
        if ev.get("type") == "apply":
            for rel in ev.get("applied", []):
                if not (d / "workspace" / rel).exists():
                    issues.append(f"applied file missing {rel}")
    kinds = {e["type"] for e in evs}
    for need in ("start", "acceptance", "complete"):
        if need not in kinds:
            issues.append(f"missing event {need}")
    if res["group"] in ("A", "B") and "orchestration_plan" not in kinds:
        issues.append("missing orchestration_plan")
    # result numbers must agree with summary
    smp = next((s for s in summary["samples"] if s["run_id"] == name), None)
    if smp is None:
        issues.append("run not present in summary")
    else:
        for k in ("all_passed", "final_passed", "final_total", "fixture_initial_hash", "worker_calls", "orchestration_calls", "retries"):
            if smp.get(k) != res.get(k):
                issues.append(f"results/summary mismatch on {k}")
        if smp.get("sot_issues") not in ([], None):
            issues.append(f"recorded sot_issues: {smp.get('sot_issues')}")
    if issues:
        sot_bad += 1
        print(f"    {name}: {issues}")
check(sot_bad == 0, "SoT consistency/links 9/9 (no issues)", f"{9 - sot_bad}/9 clean")

missing_links: list[str] = []
for r in summary["samples"]:
    rd = RUNS / r["run_id"]
    for fn in ("results.json", "events.jsonl", "TASK.md", "RUN.md", "SUBTASK.md"):
        if not (rd / fn).exists():
            missing_links.append(f"{r['run_id']}/{fn}")
check(not missing_links, "summary -> per-run file links", "; ".join(missing_links) or "all present")

md_missing: list[str] = []
for doc in DOCS:
    text = (ROOT / doc).read_text(encoding="utf-8")
    for m in re.finditer(r"\]\(([^)]+)\)", text):
        tgt = m.group(1).split("#")[0].strip()
        if not tgt or tgt.startswith(("http://", "https://", "mailto:")):
            continue
        if not (ROOT / tgt).exists():
            md_missing.append(f"{doc} -> {tgt}")
check(not md_missing, "markdown local links resolve", "; ".join(md_missing) or "all resolve")

rsl = ROOT / "evidence/pilot/run_stdout.log"
check(rsl.exists() and rsl.stat().st_size > 0, "evidence/pilot/run_stdout.log present",
      f"{rsl.stat().st_size} bytes" if rsl.exists() else "MISSING")

# --------------------------------------------------------------------------
# 3. Sensitive-info scan (real artifacts) + raw request allowlist
# --------------------------------------------------------------------------
LEAK_PATTERNS = {
    "authorization-header": re.compile(r"Authorization\s*[:=]\s*\S+", re.I),
    "bearer-token": re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}"),
    "openai-key": re.compile(r"sk-[A-Za-z0-9]{10,}"),
    "api-key-assignment": re.compile(r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{8,}", re.I),
    "deepseek-key-assignment": re.compile(r"DEEPSEEK_API_KEY\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{8,}"),
}
hits: list[str] = []
scan_roots = [RUNS, ROOT / "evidence", ROOT / "fixtures"]
for base in scan_roots:
    for f in base.rglob("*"):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".pyc":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pat in LEAK_PATTERNS.items():
            if pat.search(text):
                hits.append(f"{f.relative_to(ROOT)}:{label}")
check(not hits, "sensitive-info scan of runs/ evidence/ fixtures/ (leak patterns)", "; ".join(hits) or "no leaks")

bad_req: list[str] = []
allowed_req = {"model", "messages", "max_tokens", "temperature", "stream", "stream_options"}
for f in raw_files:
    d = json.loads(f.read_text(encoding="utf-8"))
    req = d.get("request") or {}
    if set(req.keys()) != allowed_req:
        bad_req.append(f"{f.relative_to(ROOT)}:{sorted(req.keys())}")
check(not bad_req, "raw request fields allowlisted (no auth headers/keys)", "; ".join(bad_req) or "all clean")

# --------------------------------------------------------------------------
# 4. Protocol vs acceptance item counts (static, no execution)
# --------------------------------------------------------------------------
def static_check_names(task: str) -> set[str]:
    tree = ast.parse((ROOT / "fixtures" / task / "acceptance.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "check" \
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            names.add(node.args[0].value)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) is None:
            pass
    return names


for task, n in (("t1_independent", 6), ("t2_interface", 6)):
    names = static_check_names(task)
    check(len(names) == n, f"{task} acceptance items == {n}", f"{len(names)}: {sorted(names)}")

t3_tree = ast.parse((ROOT / "fixtures/t3_evolving/acceptance.py").read_text(encoding="utf-8"))


def list_len(var: str) -> int:
    for node in ast.walk(t3_tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == var for t in node.targets) \
                and isinstance(node.value, ast.List):
            return len(node.value.elts)
    return -1


s1 = list_len("stage1")
s2new = list_len("stage2_new")
check(s1 == 5, "t3 stage1 acceptance items == 5", str(s1))
check(s2new == 4 and s1 + s2new == 9, "t3 stage2 total == 9 (5 + 4 new)", f"{s1}+{s2new}")

print()
if fails:
    print(f"RECHECK RESULT: {len(fails)} FAIL(S): {fails}")
    sys.exit(1)
print("RECHECK RESULT: ALL CHECKS PASSED")
