#!/usr/bin/env python3
"""Recompute round-2 metrics and the pre-registered decision rules from raw usage.

Reads runs/summary.json + runs/*/raw/*.json + runs/*/results.json. Writes JSON.
Usage: python3 driver/analyze_results.py [--runs-dir runs] [--out evidence/formal/analysis.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

GROUPS = ["B", "C"]
TASKS = ["t1_independent", "t2_interface", "t3_evolving"]
REPEATS = [0, 1, 2]


def _median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def _improve(base: float, new: float) -> float:
    return (base - new) / base if base else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--out", default="evidence/formal/analysis.json")
    args = ap.parse_args()
    runs = Path(args.runs_dir)
    summary = json.loads((runs / "summary.json").read_text(encoding="utf-8"))
    state = summary.get("state", {})

    per_group: dict[str, dict] = {g: {
        "samples": 0, "all_passed": 0, "sum_final_passed": 0, "sum_final_total": 0,
        "sum_round1_passed": 0, "sum_round1_total": 0,
        "worker_calls": 0, "planner_calls": 0, "claim_calls": 0, "edit_calls": 0,
        "retries": 0, "truncated_calls": 0, "parse_failures": 0,
        "total_tokens": 0, "input_tokens": 0, "output_tokens": 0,
        "reasoning_tokens": 0, "cache_hit_tokens": 0,
        "worker_tokens": 0, "planner_tokens": 0, "claim_tokens": 0, "edit_tokens": 0,
        "total_elapsed": 0.0, "first_pass_elapsed": 0.0,
        "claim_conflicts": 0, "edit_conflicts": 0, "overreach": 0, "invalid_edits": 0,
        "unclaimed_writes": 0,
        "writer_rounds": 0, "writer_rounds_with_edit": 0, "reviewer_rounds": 0,
        "sot_issues": 0, "run_tokens": [], "run_elapsed": [],
    } for g in GROUPS}

    per_cell: dict[str, dict] = {}
    per_sample = []
    for r in summary["samples"]:
        g, task, rep = r["group"], r["task"], r["repeat"]
        cell = f"{task}__{g}"
        c = per_cell.setdefault(cell, {"task": task, "group": g, "samples": 0, "all_passed": 0,
                                       "final_passed": 0, "final_total": 0})
        c["samples"] += 1
        c["all_passed"] += 1 if r.get("all_passed") else 0
        c["final_passed"] += r.get("final_passed") or 0
        c["final_total"] += r.get("final_total") or 0

        agg = per_group[g]
        agg["samples"] += 1
        agg["all_passed"] += 1 if r.get("all_passed") else 0
        agg["sum_final_passed"] += r.get("final_passed") or 0
        agg["sum_final_total"] += r.get("final_total") or 0
        agg["sum_round1_passed"] += r.get("round1_passed") or 0
        agg["sum_round1_total"] += r.get("round1_total") or 0
        agg["worker_calls"] += r.get("worker_calls", 0)
        agg["planner_calls"] += r.get("planner_calls", 0)
        agg["claim_calls"] += r.get("claim_calls", 0)
        agg["edit_calls"] += r.get("edit_calls", 0)
        agg["retries"] += r.get("retries", 0)
        agg["total_elapsed"] += r.get("total_elapsed", 0) or 0
        agg["truncated_calls"] += len(r.get("truncated_calls", []) or [])
        agg["sot_issues"] += len(r.get("sot_issues", []) or [])
        for rn in ("round1", "round2"):
            rr = r.get(rn)
            if not rr:
                continue
            for cc in rr.get("conflicts", []):
                if cc.get("reason"):
                    agg["claim_conflicts"] += 1
                else:
                    agg["edit_conflicts"] += 1
            agg["overreach"] += len(rr.get("overreach", []))
            agg["invalid_edits"] += len(rr.get("invalid_edits", []))
            agg["unclaimed_writes"] += sum(1 for o in rr.get("overreach", [])
                                           if o.get("reason") == "no_lease_for_path")
            for p in rr.get("proposals", []):
                if p.get("parse_error"):
                    agg["parse_failures"] += 1
                if p.get("lease"):
                    agg["writer_rounds"] += 1
                    agg["writer_rounds_with_edit"] += 1 if p.get("wrote") else 0
                else:
                    agg["reviewer_rounds"] += 1
        run_tokens = 0
        rid = r["run_id"]
        for f in glob.glob(str(runs / rid / "raw" / "*.json")):
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            u = d.get("usage") or {}
            total = int(u.get("total_tokens") or 0)
            if not total and d.get("usage_unknown"):
                total = int(d.get("estimated_tokens") or 0)
            run_tokens += total
            agg["input_tokens"] += int(u.get("prompt_tokens") or 0)
            agg["output_tokens"] += int(u.get("completion_tokens") or 0)
            agg["reasoning_tokens"] += int((u.get("completion_tokens_details") or {})
                                           .get("reasoning_tokens") or 0)
            agg["cache_hit_tokens"] += int(u.get("prompt_cache_hit_tokens") or 0)
            kind = d.get("kind")
            if kind == "planner":
                agg["planner_tokens"] += total
            elif kind == "claim":
                agg["claim_tokens"] += total
            elif kind == "edit":
                agg["edit_tokens"] += total
            else:
                agg["worker_tokens"] += total
        agg["total_tokens"] += run_tokens
        agg["run_tokens"].append(run_tokens)
        agg["run_elapsed"].append(r.get("total_elapsed") or 0)
        # time to first observed all-pass checkpoint
        r1 = r.get("round1") or {}
        if r1.get("total") and r1.get("passed") == r1.get("total"):
            agg["first_pass_elapsed"] += r1.get("elapsed", 0)
        elif r.get("all_passed"):
            agg["first_pass_elapsed"] += r.get("total_elapsed", 0)
        per_sample.append({
            "run_id": rid, "task": task, "group": g, "repeat": rep,
            "first_worker": r.get("first_worker"),
            "round1": f"{r.get('round1_passed')}/{r.get('round1_total')}",
            "final": f"{r.get('final_passed')}/{r.get('final_total')}",
            "all_passed": bool(r.get("all_passed")),
            "run_tokens": run_tokens, "total_elapsed": r.get("total_elapsed"),
            "truncated": len(r.get("truncated_calls", []) or []),
            "sot_issues": r.get("sot_issues", []),
            "status": r.get("status"),
        })

    # per-cell pass requirement: every task class C >= B
    per_class = {}
    for task in TASKS:
        b = per_cell.get(f"{task}__B", {})
        c = per_cell.get(f"{task}__C", {})
        per_class[task] = {"B_all_passed": b.get("all_passed", 0), "B_samples": b.get("samples", 0),
                           "C_all_passed": c.get("all_passed", 0), "C_samples": c.get("samples", 0)}

    expected = len(TASKS) * len(REPEATS)
    for g in GROUPS:
        per_group[g]["worker_tokens"] = per_group[g]["claim_tokens"] + per_group[g]["edit_tokens"]

    b, c = per_group["B"], per_group["C"]
    b_tok_med, c_tok_med = _median(b["run_tokens"]), _median(c["run_tokens"])
    b_time_med, c_time_med = _median(b["run_elapsed"]), _median(c["run_elapsed"])
    tok_imp = _improve(b_tok_med, c_tok_med) if (b_tok_med and c_tok_med) else 0.0
    time_imp = _improve(b_time_med, c_time_med) if (b_time_med and c_time_med) else 0.0

    c_all_pass = c["samples"] == expected and c["all_passed"] == expected
    c_class_ge_b = all(per_class[t]["C_all_passed"] >= per_class[t]["B_all_passed"] for t in TASKS)
    c_clean = c["sot_issues"] == 0 and c["overreach"] == 0
    c_no_trunc = c["truncated_calls"] == 0
    # improvement rule: either token or time improves >=15% and the other does not worsen >10%
    token_or_time = (tok_imp >= 0.15 and time_imp >= -0.10) or (time_imp >= 0.15 and tok_imp >= -0.10)
    candidate_remove = bool(c_all_pass and c_class_ge_b and c_clean and c_no_trunc and token_or_time)
    retain_planning = bool(not c_all_pass)

    out = {
        "budget_state": state,
        "group_metrics": {k: {kk: vv for kk, vv in v.items() if kk not in ("run_tokens", "run_elapsed")}
                          for k, v in per_group.items()},
        "group_tokens": {g: {"run_tokens": per_group[g]["run_tokens"],
                             "run_elapsed": per_group[g]["run_elapsed"]} for g in GROUPS},
        "per_cell": per_cell, "per_class": per_class, "per_sample": per_sample,
        "medians": {"B_tokens": b_tok_med, "C_tokens": c_tok_med,
                    "B_elapsed": b_time_med, "C_elapsed": c_time_med,
                    "token_improve_C_vs_B": round(tok_imp, 4),
                    "time_improve_C_vs_B": round(time_imp, 4)},
        "decision_rules": {
            "C_all_9_pass": c_all_pass,
            "C_each_class_ge_B": c_class_ge_b,
            "C_zero_sot_or_overreach": c_clean,
            "C_zero_truncation": c_no_trunc,
            "improvement_rule_met": bool(token_or_time),
            "candidate_independent_orchestration_removable": candidate_remove,
            "candidate_retain_planning": retain_planning,
            "note": "candidate only for a next-round product SDK check; NOT an automatic removal",
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"group_metrics": out["group_metrics"], "medians": out["medians"],
                      "decision_rules": out["decision_rules"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
