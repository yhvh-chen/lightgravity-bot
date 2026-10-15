#!/usr/bin/env python3
"""LG-032 METHOD-FINAL 门D — independent B s1/s2 0-fake result audit.

Reads the two persisted B attempt outputs (produced once each by
``run_method_dry.py``) and the fake-upstream captures, and independently checks:

1. the attempt is complete and honest (reached bound acceptance, machine truth
   5/5 and 7/7, real session refs, real reviewer teardown, candidate diffs);
2. the **fake phase classification** corresponds to the product's real phase
   signals: a ``selection`` request carries the product-frozen ``PHASE 1``
   sentinel; a ``verify`` request exposes ``view_file`` and no write tool; an
   ``execution`` request exposes a write tool; the reviewer request exposes no
   tools.  A misclassification would show up as a phase whose observed signals
   contradict its label;
3. the acceptance binds the product's REAL machine truth (``check_records`` with
   ``evidence-present`` passed) and the per-node candidate diffs (not the
   colliding run-level path), with a real ``candidate_plan_hash``;
4. the stop gate passed WITHOUT a hand-written ``cleanup=done`` (the run reached
   acceptance with ``cleanup.status == 'pending'`` -> the real adapter stop
   confirmation is what authorised it);
5. the seed identity is the same actual commit SHA as the frozen pin.

Real provider generation = 0 (all evidence originates from loopback fake runs).
Read-only.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import method_config as MC  # noqa: E402

C = MC.install()

_WRITE_TOOLS = {"write_to_file", "replace_file_content", "create_file", "edit_file"}


def _find_results() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for sample in ("s1_units", "s2_pipeline"):
        pats = sorted(glob.glob(str(
            MC.PHASE_DATA_DIR.parent / f"{MC.PHASE_DATA_DIR.name}-method-{sample[0:2]}B-*"
            / "offline_dry_run_output" / f"{sample}__B" / "result.json"
        )))
        if pats:
            out[sample] = Path(pats[-1])
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_capture(cap_path: Path, sample: str) -> dict[str, Any]:
    cap = json.loads(cap_path.read_text(encoding="utf-8"))
    records = cap["records"]
    phases: dict[str, int] = {}
    misclassified: list[dict[str, Any]] = []
    for r in records:
        phase = r["phase"]
        phases[phase] = phases.get(phase, 0) + 1
        tools = set(r.get("tool_names") or [])
        joined = " ".join(r.get("full") or [])
        has_write = bool(tools & _WRITE_TOOLS)
        has_view = "view_file" in tools
        if phase == "review":
            ok = not tools
        elif phase == "selection":
            # product-frozen sentinel must be present in the selection prompt.
            ok = "PHASE 1" in joined and not has_write
        elif phase == "verify":
            ok = has_view and not has_write
        elif phase == "execution":
            ok = has_write
        else:
            ok = False
        if not ok:
            misclassified.append({"phase": phase, "tools": sorted(tools),
                                  "sentinel": "PHASE 1" in joined})
    # A real B run must have exercised the selection path at least once.
    return {
        "capture": str(cap_path),
        "records": len(records),
        "phase_counts": phases,
        "selection_present": phases.get("selection", 0) >= 1,
        "execution_present": phases.get("execution", 0) >= 1,
        "verify_present": phases.get("verify", 0) >= 1,
        "review_present": phases.get("review", 0) >= 1,
        "misclassified": misclassified,
        "ok": not misclassified and phases.get("selection", 0) >= 1,
    }


def audit_result(sample: str, result_path: Path, capture_path: Path) -> dict[str, Any]:
    d = json.loads(result_path.read_text(encoding="utf-8"))
    acc = (d.get("accept_response") or {}).get("acceptance") or {}
    review = d.get("review") or {}
    pins = (C.FIXTURES_DIR / sample / "seed.sha256").read_text(encoding="utf-8").strip()
    checks = {
        "ok_true": d.get("ok") is True,
        "no_failed_steps": all(s["ok"] for s in d.get("steps", [])),
        "reached_awaiting_acceptance": d.get("final_phase") == "awaiting_acceptance",
        "truths_before_accept": d.get("truths_before_accept") is True,
        "machine_gate_full": d.get("machine_pass") is True,
        "real_session_refs": len(d.get("session_refs") or []) >= 1,
        "reviewer_teardown_confirmed": bool(
            (d.get("reviewer_cleanup") or {}).get("confirmed") is True
        ),
        "review_validated_passed": str(review.get("validated_outcome", "")) == "passed",
        "candidate_diff_count_2": d.get("candidate_diff_count") == 2,
        "candidate_patch_applied": d.get("candidate_patch_applied") is True,
        "accept_bound_candidate_ref": bool(acc.get("candidate_ref")),
        "accept_binds_plan_hash": bool(acc.get("candidate_plan_hash")),
        "accept_binds_evidence_present_passed": bool(
            acc.get("check_records")
            and acc["check_records"][0].get("check_id") == "evidence-present"
            and acc["check_records"][0].get("status") == "passed"
        ),
        "stop_gate_passed_without_cleanup_done": (
            (d.get("cleanup") or {}).get("status") != "done"
            and d.get("final_phase") == "awaiting_acceptance"
        ),
        "seed_head_equals_pin": d.get("seed_head") == pins,
        "initial_head_equals_seed": d.get("initial_head") == d.get("seed_head"),
        "attempt_requests_within_cap": 0 < d.get("attempt_generation_requests", 0) <= C.ATTEMPT_GENERATION_LIMIT,
        "generation_final_persistent": bool(
            (d.get("generation_final") or {}).get("persistent") is True
            and (d.get("generation_final") or {}).get("count", 0) > 0
        ),
        "idempotent_accept_replay": (
            (d.get("accept_idempotent_response") or {}).get("state") == "confirmed"
        ),
        "wrong_target_rejected": bool(
            (d.get("accept_wrong_target_response") or {}).get("code", 0) >= 400
        ),
        "phase_machine_truth_not_empty": bool(
            (d.get("accept_response") or {}).get("acceptance", {}).get("check_records")
        ),
    }
    return {
        "sample": sample,
        "result_path": str(result_path),
        "capture_path": str(capture_path),
        "attempt_id": d.get("attempt_id"),
        "phases_seen": d.get("phases_seen"),
        "cleanup_status": (d.get("cleanup") or {}).get("status"),
        "machine_gate": f"{d.get('machine_gate', {}).get('passed')}/{d.get('machine_gate', {}).get('total')}",
        "requests": d.get("attempt_generation_requests"),
        "accept_evidence_refs": acc.get("evidence_refs"),
        "accept_check_records": acc.get("check_records"),
        "checks": checks,
        "ok": all(checks.values()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    nonce = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = _find_results()
    payload: dict[str, Any] = {
        "probe": "METHOD-FINAL/gateD-independent-B-audit",
        "utc": nonce,
        "real_provider_generation": 0,
        "results_found": sorted(results),
    }
    audits: dict[str, Any] = {}
    caps = {}
    for sample, rpath in results.items():
        cap_pat = sorted(glob.glob(str(
            MC.METHOD_DIR / "evidence" / "dry_captures" / f"*-{sample}-B.json"
        )))
        cap = Path(cap_pat[-1]) if cap_pat else None
        if cap is None:
            audits[sample] = {"ok": False, "error": "no capture"}
            continue
        audits[sample] = audit_result(sample, rpath, cap)
        caps[sample] = audit_capture(cap, sample)
    payload["result_audits"] = audits
    payload["phase_classification_audits"] = caps
    payload["ok"] = (
        len(audits) == 2
        and all(v.get("ok") for v in audits.values())
        and all(v.get("ok") for v in caps.values())
    )
    out = Path(args.out) if args.out else (MC.METHOD_DIR / "evidence" / f"gateD-{nonce}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v)
                      for k, v in payload.items()}, indent=2))
    for s, a in audits.items():
        bad = [k for k, v in a.get("checks", {}).items() if not v]
        print(f"  {s}: ok={a.get('ok')} failed={bad}")
    for s, a in caps.items():
        print(f"  {s} phases={a.get('phase_counts')} misclassified={a.get('misclassified')}")
    print(f"WROTE {out}")
    print(f"GATE-D {'PASS' if payload['ok'] else 'FAIL'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
