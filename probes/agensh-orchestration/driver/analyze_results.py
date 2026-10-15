#!/usr/bin/env python3
"""Recompute per-group metrics and the pre-registered decision rules from runs/.

Reads runs/summary.json + runs/*/raw/*.json (raw usage). Writes analysis JSON.
Usage: python3 driver/analyze_results.py [--runs-dir runs] [--out evidence/pilot/analysis.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

GROUPS = ["A", "B", "C"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--out", default="evidence/pilot/analysis.json")
    args = ap.parse_args()
    runs = Path(args.runs_dir)
    summary = json.loads((runs / "summary.json").read_text(encoding="utf-8"))

    per_group: dict[str, dict] = {g: {
        "samples": 0, "all_passed": 0, "sum_final_passed": 0, "sum_final_total": 0,
        "sum_round1_passed": 0, "sum_round1_total": 0,
        "worker_calls": 0, "orchestration_calls": 0, "retries": 0,
        "total_tokens": 0, "input_tokens": 0, "output_tokens": 0,
        "reasoning_tokens": 0, "cache_hit_tokens": 0,
        "worker_tokens": 0, "orchestration_tokens": 0,
        "total_elapsed": 0.0, "orchestration_elapsed": 0.0,
        "conflicts": 0, "duplicate_edits": 0, "invalid_edits": 0,
        "parse_failures": 0, "truncated_calls": 0,
    } for g in GROUPS}

    per_sample = []
    for r in summary["samples"]:
        g = r["group"]
        agg = per_group[g]
        agg["samples"] += 1
        agg["all_passed"] += 1 if r.get("all_passed") else 0
        agg["sum_final_passed"] += r.get("final_passed") or 0
        agg["sum_final_total"] += r.get("final_total") or 0
        agg["sum_round1_passed"] += r.get("round1_passed") or 0
        agg["sum_round1_total"] += r.get("round1_total") or 0
        agg["worker_calls"] += r.get("worker_calls", 0)
        agg["orchestration_calls"] += r.get("orchestration_calls", 0)
        agg["retries"] += r.get("retries", 0)
        agg["total_elapsed"] += r.get("total_elapsed", 0)
        agg["orchestration_elapsed"] += r.get("orchestration_elapsed", 0)
        for rn in ("round1", "round2"):
            rr = r[rn]
            agg["conflicts"] += len(rr.get("conflicts", []))
            agg["duplicate_edits"] += len(rr.get("duplicate_edits", []))
            agg["invalid_edits"] += len(rr.get("invalid", []))
            for p in rr.get("proposals", []):
                if p.get("parse_error"):
                    agg["parse_failures"] += 1
        rid = r["run_id"]
        for f in glob.glob(str(runs / rid / "raw" / "*.json")):
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            u = d.get("usage") or {}
            total = int(u.get("total_tokens") or 0)
            agg["total_tokens"] += total
            agg["input_tokens"] += int(u.get("prompt_tokens") or 0)
            agg["output_tokens"] += int(u.get("completion_tokens") or 0)
            agg["reasoning_tokens"] += int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
            agg["cache_hit_tokens"] += int(u.get("prompt_cache_hit_tokens") or 0)
            if d.get("kind") == "orchestrator":
                agg["orchestration_tokens"] += total
            else:
                agg["worker_tokens"] += total
            if int(u.get("completion_tokens") or 0) >= 2048:
                agg["truncated_calls"] += 1
        per_sample.append({
            "run_id": rid, "task": r["task"], "group": g,
            "round1": f"{r.get('round1_passed')}/{r.get('round1_total')}",
            "final": f"{r.get('final_passed')}/{r.get('final_total')}",
            "all_passed": bool(r.get("all_passed")),
            "total_elapsed": r.get("total_elapsed"), "orchestration_elapsed": r.get("orchestration_elapsed"),
            "sot_issues": r.get("sot_issues", []),
        })

    # pre-registered rules
    a, b, c = per_group["A"], per_group["B"], per_group["C"]
    token_improve_c = (a["total_tokens"] - c["total_tokens"]) / a["total_tokens"]
    time_improve_c = (a["total_elapsed"] - c["total_elapsed"]) / a["total_elapsed"]
    token_improve_b = (a["total_tokens"] - b["total_tokens"]) / a["total_tokens"]
    time_improve_b = (a["total_elapsed"] - b["total_elapsed"]) / a["total_elapsed"]
    c_all = c["all_passed"] == c["samples"]
    c_sot_clean = all(not s["sot_issues"] for s in per_sample if s["group"] == "C")
    rules = {
        "candidate_de_orchestration": bool(c_all and c_sot_clean and max(token_improve_c, time_improve_c) >= 0.20),
        "candidate_on_demand_initial_planning": bool(
            b["sum_final_passed"] >= a["sum_final_passed"]
            and (b["total_tokens"] < a["total_tokens"] or b["total_elapsed"] < a["total_elapsed"])),
        "retain_planning_for_dependency_change": "T3 (change task): C all-fail while B full-pass -> retain",
        "token_improve_c_vs_a": round(token_improve_c, 4),
        "time_improve_c_vs_a": round(time_improve_c, 4),
        "token_improve_b_vs_a": round(token_improve_b, 4),
        "time_improve_b_vs_a": round(time_improve_b, 4),
    }
    out = {
        "budget": summary["pilot_state"],
        "group_metrics": per_group,
        "per_sample": per_sample,
        "decision_rules": rules,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"group_metrics": per_group, "decision_rules": rules}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
