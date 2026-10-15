#!/usr/bin/env python3
"""Corrected-experiment analyzer: derive every reported metric from raw runs."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent
FORMAL = ROOT / "runs" / "formal"
OUT = ROOT / "evidence" / "phaseD" / "analysis.json"


def load_run(run_dir: Path) -> dict:
    res = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    turns = []
    for p in sorted((run_dir / "turns").glob("*.json")):
        if p.name.endswith(".validate.json") or p.name == "planner.summary.json":
            continue
        turns.append(json.loads(p.read_text(encoding="utf-8")))
    # full relay call records per run (from turn records; each has relay_calls)
    relay = []
    for t in turns:
        relay.extend(t.get("relay_calls") or [])
    return res, turns, relay


def phase_of(logical: str) -> str:
    if logical == "planner":
        return "planner"
    if "claim" in logical:
        return "claim"
    return "edit"


def main() -> int:
    runs = {}
    for run_dir in sorted(FORMAL.glob("*__r0")):
        res, turns, relay = load_run(run_dir)
        phases = {"planner": [], "claim": [], "edit": []}
        for t in turns:
            phases[phase_of(t.get("logical", ""))].append(t)
        all_decisions = [d for t in turns for d in (t.get("hook_decisions") or [])]
        denials = [d for d in all_decisions if d.get("allow") is False]
        finish_turns = [t for t in turns if t.get("finish_payload") is not None]
        finish_present_lossless = all(
            t.get("finish_source") == "hook" and not t.get("emitted_truncated")
            and t.get("finish_parse_error") is None for t in finish_turns)
        lengths = [r for r in relay for fr in (r.get("finish_reasons") or []) if fr == "length"]
        overreach = [o for rr in res.get("rounds", []) for o in rr.get("overreach", [])]
        invalid = [o for rr in res.get("rounds", []) for o in rr.get("invalid_edits", [])]
        wrote = [wr for rr in res.get("rounds", []) for wr in rr.get("writer_reports", [])
                 if wr.get("accepted")]
        relay_tokens = sum(int((r.get("usage") or {}).get("total_tokens") or 0) for r in relay)
        relay_cache = sum(int((r.get("usage") or {}).get("prompt_cache_hit_tokens", 0)
                              or (r.get("usage") or {}).get("cached_tokens", 0)) for r in relay)
        runs[run_dir.name] = {
            "task": res["task"], "group": res["group"], "status": res["status"],
            "plan_valid": res.get("plan_valid"),
            "plan_injection": res.get("plan_injection"),
            "round1": [res.get("round1_passed"), res.get("round1_total")],
            "final": [res.get("final_passed"), res.get("final_total")],
            "all_passed": res.get("all_passed"),
            "turns_total": len(turns),
            "turns_by_phase": {k: len(v) for k, v in phases.items()},
            "turn_states": {s: sum(1 for t in turns if t.get("state") == s)
                            for s in sorted({t.get("state") for t in turns})},
            "http": res.get("budget", {}).get("http_used"),
            "tokens": res.get("budget", {}).get("tokens_used"),
            "relay_tokens": relay_tokens,
            "relay_tokens_by_phase": {k: sum(int((c.get("usage") or {}).get("total_tokens") or 0)
                                             for t in v for c in (t.get("relay_calls") or []))
                                      for k, v in phases.items()},
            "relay_cache_tokens": relay_cache,
            "relay_calls": len(relay),
            "tokens_unknown_calls": res.get("budget", {}).get("tokens_unknown_calls"),
            "elapsed": res.get("total_elapsed"),
            "tokens_by_phase": {k: sum((t.get("reported_tokens") or 0) for t in v)
                                for k, v in phases.items()},
            "http_by_phase": {k: sum((t.get("relay_http") or 0) for t in v)
                              for k, v in phases.items()},
            "finish_turns": len(finish_turns),
            "finish_lossless_when_present": finish_present_lossless,
            "finish_no_call_turns": [t.get("logical") for t in turns
                                     if t.get("finish_parse_error") == "no_finish_call"],
            "length_truncations": len(lengths),
            "finish_reasons": sorted({fr for r in relay for fr in (r.get("finish_reasons") or [])}),
            "cache_tokens": sum((r.get("usage") or {}).get("prompt_cache_hit_tokens", 0)
                                or (r.get("usage") or {}).get("cached_tokens", 0) for r in relay),
            "reasoning_seen": sum(1 for r in relay if r.get("reasoning_content_seen")),
            "hook_decisions": len(all_decisions),
            "hook_denials": len(denials),
            "hook_denial_reasons": [d.get("reason") for d in denials],
            "actual_overreach": len(overreach),
            "overreach_detail": overreach,
            "invalid_edits": invalid,
            "accepted_writes": len(wrote),
            "stop_all_positive": res.get("stop_all_positive"),
            "sot_issues": res.get("sot_issues"),
            "first_worker": res.get("first_worker"),
            "plan_id": res.get("plan_id"),
        }

    def med(vals):
        vals = [v for v in vals if isinstance(v, (int, float))]
        return round(statistics.median(vals), 3) if vals else None

    by_group = {}
    for g in ("B", "C"):
        rows = [r for r in runs.values() if r["group"] == g]
        by_group[g] = {
            "n": len(rows),
            "all_passed": sum(1 for r in rows if r["all_passed"]),
            "sum_final_passed": sum(r["final"][0] or 0 for r in rows),
            "sum_final_total": sum(r["final"][1] or 0 for r in rows),
            "median_tokens": med([r["tokens"] for r in rows]),
            "median_relay_tokens": med([r["relay_tokens"] for r in rows]),
            "median_elapsed": med([r["elapsed"] for r in rows]),
            "sum_http": sum(r["http"] or 0 for r in rows),
            "sum_tokens": sum(r["tokens"] or 0 for r in rows),
            "sum_relay_tokens": sum(r["relay_tokens"] or 0 for r in rows),
            "sum_elapsed": round(sum(r["elapsed"] or 0 for r in rows), 3),
            "median_turn_states": {s: med([r["turn_states"].get(s, 0) for r in rows])
                                   for s in {s for r in rows for s in r["turn_states"]}},
        }
    b_tok, c_tok = by_group["B"]["median_relay_tokens"], by_group["C"]["median_relay_tokens"]
    b_btok, c_btok = by_group["B"]["median_tokens"], by_group["C"]["median_tokens"]
    b_time, c_time = by_group["B"]["median_elapsed"], by_group["C"]["median_elapsed"]
    metrics = {
        "tokens_improvement_pct": round((b_tok - c_tok) / b_tok * 100, 2) if b_tok else None,
        "budget_tokens_improvement_pct": round((b_btok - c_btok) / b_btok * 100, 2) if b_btok else None,
        "elapsed_improvement_pct": round((b_time - c_time) / b_time * 100, 2) if b_time else None,
    }
    validity = {
        "all_b_plans_valid": all(r["plan_valid"] for r in runs.values() if r["group"] == "B"),
        "all_b_plans_injected": all((r["plan_injection"] or {}).get("all_true")
                                    for r in runs.values() if r["group"] == "B"),
        "all_stops_positive": all(r["stop_all_positive"] for r in runs.values()),
        "all_finishes_lossless_when_present": all(r["finish_lossless_when_present"]
                                                  for r in runs.values()),
        "zero_length_truncations": all(r["length_truncations"] == 0 for r in runs.values()),
        "all_sot_clean": all(not r["sot_issues"] for r in runs.values()),
        "all_real_writes": all(r["accepted_writes"] >= 1 for r in runs.values()),
    }
    report = {
        "relay_total_http": sum(r["http"] or 0 for r in runs.values()),
        "relay_total_tokens": sum(r["relay_tokens"] or 0 for r in runs.values()),
        "driver_budget_total_tokens": sum(r["tokens"] or 0 for r in runs.values()),
        "runs": runs, "by_group": by_group, "metrics": metrics, "validity": validity,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"by_group": by_group, "metrics": metrics, "validity": validity},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
