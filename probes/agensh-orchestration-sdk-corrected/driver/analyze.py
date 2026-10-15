#!/usr/bin/env python3
"""Offline analysis of the frozen formal runs.

Recomputes all metrics from raw artifacts (`results.json`, per-turn JSON, relay
records embedded in turns, `events.jsonl`, frontmatter) — never from a cached
summary — and evaluates the pre-registered candidate gate.

Nothing here makes model calls.  It may be re-run after the run window; only
pure offline bugs may be fixed (analysis changes are recorded in REPORT.md).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
PROBE_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_HERE.parent))

from sotyaml import try_parse_frontmatter_file  # noqa: E402

FORMAL = PROBE_ROOT / "runs" / "formal"
PLANNER_RECOVERY = PROBE_ROOT / "evidence" / "planner_recovery.json"
WRITE_TOOL_ALIASES = {"edit_file", "edit-file", "write_to_file", "write-to-file",
                      "replace_file_content", "create_file", "create-file"}


def load_runs() -> list[dict]:
    runs = []
    for d in sorted(FORMAL.glob("*")):
        rp = d / "results.json"
        if rp.exists():
            runs.append(json.loads(rp.read_text(encoding="utf-8")))
    return runs


def yaml_audit(run_dir: Path) -> list[str]:
    issues: list[str] = []
    for name in ("TASK.md", "RUN.md"):
        fm, err = try_parse_frontmatter_file(run_dir / name)
        if err:
            issues.append(f"{name}: {err}")
    for p in sorted((run_dir / "subtasks").glob("*.md")):
        fm, err = try_parse_frontmatter_file(p)
        if err:
            issues.append(f"{p.name}: {err}")
        else:
            lp = fm.get("lease_path")
            if not (lp is None or (isinstance(lp, str) and lp.strip())):
                issues.append(f"{p.name}: illegal lease_path {lp!r}")
    return issues


def turn_evidence(run: dict) -> dict:
    read_tools: set[str] = set()
    write_tools: set[str] = set()
    finish_tools = 0
    relay_write_tools: set[str] = set()
    length_truncated = 0
    budget_exhausted = 0
    failed = 0
    states: list[str] = []
    tool_call_total = 0
    for rnd in run.get("rounds", []):
        for t in rnd.get("turns", []):
            states.append(t.get("state"))
            for name in (t.get("tool_call_names") or []):
                tool_call_total += 1
                if name == "view_file":
                    read_tools.add("view_file")
                if name in WRITE_TOOL_ALIASES:
                    write_tools.add(name)
                if name == "finish":
                    finish_tools += 1
            for call in (t.get("turns") or []):
                pass
            if t.get("state") == "budget_exhausted":
                budget_exhausted += 1
            if t.get("state") in ("failed", "blocked"):
                failed += 1
        for t in rnd.get("turns", []):
            for call in (t.get("relay_calls") or []):
                for name in (call.get("request_before") or {}).get("tool_names") or []:
                    if name in ("write_to_file", "replace_file_content", "edit_file"):
                        relay_write_tools.add(name)
                reasons = call.get("finish_reasons") or []
                if any(str(x) == "length" for x in reasons):
                    length_truncated += 1
    return {"read_tools": sorted(read_tools), "write_tools": sorted(write_tools),
            "relay_write_tools": sorted(relay_write_tools), "finish_calls": finish_tools,
            "tool_call_total": tool_call_total, "length_truncated": length_truncated,
            "budget_exhausted_turns": budget_exhausted, "failed_turns": failed,
            "states": states}


def per_run(run: dict) -> dict:
    run_dir = FORMAL / run["run_id"]
    rounds = run.get("rounds", [])
    overreach = sum(len(r.get("overreach", [])) for r in rounds)
    invalid = sum(len(r.get("invalid_edits", [])) for r in rounds)
    writer_total = 0
    writer_wrote = 0
    reviewer_total = 0
    for r in rounds:
        for wr in r.get("writer_reports", []):
            if wr.get("lease"):
                writer_total += 1
                if wr.get("accepted"):
                    writer_wrote += 1
            else:
                reviewer_total += 1
    ev = turn_evidence(run)
    return {
        "run_id": run["run_id"], "task": run["task"], "group": run["group"],
        "all_passed": run.get("all_passed"), "final": f"{run.get('final_passed')}/{run.get('final_total')}",
        "round1": f"{run.get('round1_passed')}/{run.get('round1_total')}",
        "tokens": (run.get("budget") or {}).get("tokens_used"),
        "http": (run.get("budget") or {}).get("http_used"),
        "elapsed": run.get("total_elapsed"),
        "plan_valid": run.get("plan_valid"),
        "overreach_events": overreach, "invalid_edits": invalid,
        "writer_utilization": f"{writer_wrote}/{writer_total}",
        "reviewer_turns": reviewer_total,
        "length_truncated": ev["length_truncated"],
        "budget_exhausted_turns": ev["budget_exhausted_turns"],
        "failed_turns": ev["failed_turns"],
        "read_tools": ev["read_tools"], "write_tools": ev["write_tools"],
        "relay_write_tools": ev["relay_write_tools"], "finish_calls": ev["finish_calls"],
        "yaml_issues": yaml_audit(run_dir),
        "sot_issues": run.get("sot_issues", []),
        "finish_parse_errors": finish_errors(run_dir),
    }


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def finish_errors(run_dir: Path) -> int:
    n = 0
    for p in sorted((run_dir / "turns").glob("*.json")):
        if p.name.endswith(".validate.json") or p.name.endswith(".summary.json"):
            continue
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if t.get("finish_parse_error"):
            n += 1
    return n


def _validity(rows: list[dict]) -> dict:
    recovery = {}
    if PLANNER_RECOVERY.exists():
        data = json.loads(PLANNER_RECOVERY.read_text(encoding="utf-8"))
        for r in data.get("runs", []):
            recovery[r["run_id"]] = {"recovered": r["recovered"],
                                     "program_valid": r["program_valid"],
                                     "program_issues": r["program_issues"]}
    b_runs = [r for r in rows if r["group"] == "B"]
    b_arm_valid = bool(b_runs) and all(recovery.get(r["run_id"], {}).get("program_valid")
                                       for r in b_runs)
    return {
        "b_planner_recovery": recovery,
        "b_arm_valid": b_arm_valid,
        "b_arm_note": ("all B planner outputs were program-invalid (wrong field names and/or "
                       "2000-char event truncation), so workers received no plan: B was "
                       "effectively C plus one discarded planner call"),
        "finish_parse_errors_total": sum(r["finish_parse_errors"] for r in rows),
    }


def main() -> int:
    runs = load_runs()
    rows = [per_run(r) for r in runs]
    groups = {}
    for g in ("B", "C"):
        gs = [r for r in rows if r["group"] == g]
        groups[g] = {
            "samples": len(gs),
            "all_passed": sum(1 for r in gs if r["all_passed"]),
            "tokens_sum": sum(r["tokens"] or 0 for r in gs),
            "tokens_median": median([r["tokens"] for r in gs if r["tokens"] is not None]),
            "http_sum": sum(r["http"] or 0 for r in gs),
            "elapsed_median": median([r["elapsed"] for r in gs if r["elapsed"] is not None]),
            "overreach_events": sum(r["overreach_events"] for r in gs),
            "invalid_edits": sum(r["invalid_edits"] for r in gs),
            "length_truncated": sum(r["length_truncated"] for r in gs),
            "budget_exhausted_turns": sum(r["budget_exhausted_turns"] for r in gs),
            "failed_turns": sum(r["failed_turns"] for r in gs),
            "yaml_issue_runs": sum(1 for r in gs if r["yaml_issues"]),
            "sot_issue_runs": sum(1 for r in gs if r["sot_issues"]),
        }
    # per-class paired
    classes = {}
    for task in sorted({r["task"] for r in rows}):
        cls = {}
        for g in ("B", "C"):
            gs = [r for r in rows if r["task"] == task and r["group"] == g]
            cls[g] = {"all_passed": sum(1 for r in gs if r["all_passed"]),
                      "tokens": [r["tokens"] for r in gs],
                      "elapsed": [r["elapsed"] for r in gs]}
        classes[task] = cls
    b_tok = groups["B"]["tokens_median"] or 0
    c_tok = groups["C"]["tokens_median"] or 0
    b_el = groups["B"]["elapsed_median"] or 0
    c_el = groups["C"]["elapsed_median"] or 0
    tok_improve = (b_tok - c_tok) / b_tok * 100 if b_tok else None
    el_improve = (b_el - c_el) / b_el * 100 if b_el else None
    # gate
    c_all = groups["C"]["all_passed"] == groups["C"]["samples"] and groups["C"]["samples"] > 0
    quality_ok = all(cls["C"]["all_passed"] >= cls["B"]["all_passed"] for cls in classes.values())
    zero_overreach = groups["B"]["overreach_events"] + groups["C"]["overreach_events"] == 0
    zero_yaml_sot = (groups["B"]["yaml_issue_runs"] + groups["C"]["yaml_issue_runs"] == 0
                     and groups["B"]["sot_issue_runs"] + groups["C"]["sot_issue_runs"] == 0)
    zero_length = groups["B"]["length_truncated"] + groups["C"]["length_truncated"] == 0
    improve_15 = ((tok_improve is not None and tok_improve >= 15)
                  or (el_improve is not None and el_improve >= 15))
    other_not_worse = ((tok_improve is None or tok_improve > -10)
                       and (el_improve is None or el_improve > -10))
    all_have_tools = all(r["write_tools"] or r["relay_write_tools"] for r in rows)
    gate = {
        "C_all_pass": c_all,
        "C_quality_ge_B": quality_ok,
        "zero_overreach": zero_overreach,
        "zero_yaml_sot": zero_yaml_sot,
        "zero_length_truncation": zero_length,
        "improve_ge_15pct": improve_15,
        "other_metric_not_worse_10pct": other_not_worse,
        "all_classes_real_tool_evidence": all_have_tools,
        "PASS": bool(c_all and quality_ok and zero_overreach and zero_yaml_sot
                     and zero_length and improve_15 and other_not_worse and all_have_tools),
    }
    report = {
        "formal_runs": len(rows),
        "groups": groups,
        "classes": classes,
        "improvement": {"tokens_pct": round(tok_improve, 2) if tok_improve is not None else None,
                        "elapsed_pct": round(el_improve, 2) if el_improve is not None else None},
        "gate": gate,
        "validity": _validity(rows),
        "runs": rows,
    }
    (FORMAL / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
