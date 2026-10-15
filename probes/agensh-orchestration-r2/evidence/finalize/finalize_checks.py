#!/usr/bin/env python3
"""Offline finalize checks (no model calls).

Rebuilds consistency evidence from runs/ for the round-2 report:
  - 18 runs, 9 per group, 3 per class
  - every run started from the frozen fixture initial hash
  - subtask lease authority matches events claim results, at most one writer/path/round
  - token sum from raw usage == budget state total_tokens
  - no auth/secret material in raw
Writes evidence/formal/consistency.json + a text summary.
"""
from __future__ import annotations

import glob
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
FIX = ROOT / "fixtures"
TASKS = ["t1_independent", "t2_interface", "t3_evolving"]
GROUPS = ["B", "C"]


def fixture_initial_hash(task: str) -> str:
    base = FIX / task / "initial"
    h = hashlib.sha256()
    for p in sorted(base.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(base).as_posix().encode()); h.update(b"\0")
            h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()


def parse_fm(path: Path) -> dict:
    fm = {}
    if not path.exists():
        return fm
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return fm
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def main() -> int:
    summary = json.loads((RUNS / "summary.json").read_text(encoding="utf-8"))
    state = summary["state"]
    issues: list[str] = []
    per_run = []

    init_hashes = {t: fixture_initial_hash(t) for t in TASKS}
    counts = {"group": {g: 0 for g in GROUPS}, "class_group": {}}
    raw_token_sum = 0
    raw_count = 0
    auth_hits: list[str] = []

    for rf in sorted(glob.glob(str(RUNS / "*" / "results.json"))):
        r = json.loads(Path(rf).read_text(encoding="utf-8"))
        rid, task, group = r["run_id"], r["task"], r["group"]
        counts["group"][group] = counts["group"].get(group, 0) + 1
        key = f"{task}__{group}"
        counts["class_group"][key] = counts["class_group"].get(key, 0) + 1

        if r.get("fixture_initial_hash") != init_hashes[task]:
            issues.append(f"{rid}: initial hash mismatch")
        if r.get("sot_issues"):
            issues.append(f"{rid}: sot_issues {r['sot_issues']}")

        # subtask lease authority vs events
        run_dir = RUNS / rid
        events = []
        if (run_dir / "events.jsonl").exists():
            for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        for rnd in (1, 2):
            leases: dict[str, str] = {}
            for sp in sorted((run_dir / "subtasks").glob(f"r{rnd}-*.md")):
                fm = parse_fm(sp)
                if fm.get("lease_state") == "granted" and fm.get("lease_path") not in (None, "-"):
                    if fm["lease_path"] in leases:
                        issues.append(f"{rid} r{rnd}: duplicate lease {fm['lease_path']}")
                    leases[fm["lease_path"]] = fm.get("worker")
            grants = {e.get("granted_path"): e.get("worker") for e in events
                      if e.get("type") == "claim_result" and e.get("round") == rnd
                      and e.get("state") == "granted"}
            if leases != grants:
                issues.append(f"{rid} r{rnd}: subtask leases {leases} != events {grants}")

        # raw token + auth scan
        for f in glob.glob(str(run_dir / "raw" / "*.json")):
            txt = Path(f).read_text(encoding="utf-8")
            if "Bearer " in txt or "Authorization" in txt:
                auth_hits.append(f)
            d = json.loads(txt)
            raw_count += 1
            u = d.get("usage") or {}
            raw_token_sum += int(u.get("total_tokens") or 0)

        per_run.append({
            "run_id": rid, "task": task, "group": group, "repeat": r.get("repeat"),
            "first_worker": r.get("first_worker"),
            "round1": f"{r.get('round1_passed')}/{r.get('round1_total')}",
            "final": f"{r.get('final_passed')}/{r.get('final_total')}",
            "all_passed": bool(r.get("all_passed")),
            "tokens": sum(int((json.loads(Path(f).read_text(encoding="utf-8")).get("usage") or {})
                              .get("total_tokens") or 0)
                          for f in glob.glob(str(run_dir / "raw" / "*.json"))),
            "elapsed": r.get("total_elapsed"),
        })

    if counts["group"] != {"B": 9, "C": 9}:
        issues.append(f"group counts != 9/9: {counts['group']}")
    for key, n in counts["class_group"].items():
        if n != 3:
            issues.append(f"cell {key} has {n} runs (expected 3)")
    if raw_token_sum != state.get("total_tokens"):
        issues.append(f"raw token sum {raw_token_sum} != state {state.get('total_tokens')}")
    if auth_hits:
        issues.append(f"auth material in raw: {auth_hits}")
    if raw_count != state.get("http_requests"):
        issues.append(f"raw attempts {raw_count} != state http_requests {state['http_requests']}")

    out = {
        "counts": counts, "raw_token_sum": raw_token_sum, "raw_attempts": raw_count,
        "budget_state": {k: state.get(k) for k in ("http_requests", "normal_calls", "retry_calls",
                                                   "total_tokens", "usage_unknown_calls",
                                                   "reserved_tokens", "fatal_protocol", "abort_reason")},
        "init_hashes": init_hashes, "auth_hits": auth_hits, "per_run": per_run,
        "issues": issues, "consistent": not issues,
    }
    (ROOT / "evidence" / "formal" / "consistency.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"consistent={not issues}", f"group_counts={counts['group']}",
             f"raw_attempts={raw_count}", f"raw_token_sum={raw_token_sum}",
             f"state_total_tokens={state.get('total_tokens')}", f"issues={issues}"]
    (ROOT / "evidence" / "formal" / "consistency.txt").write_text("\n".join(lines) + "\n",
                                                                  encoding="utf-8")
    print("\n".join(lines))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
