"""LG-031 PROOF2-CLOSE — negative controls for the close harness (0 model).

These deterministic checks prove the close harness's adapters are **strict** and
not constant-True stand-ins.  They use no model and no real network:

  N1  ``RecordedStopFactReader`` refuses a run it has no recorded facts for.
  N2  ``RecordedStopFactReader`` refuses when a session id is unknown.
  N3  ``RecordedStopFactReader`` refuses when the originating process is
      reported still-alive.
  N4  ``RecordedRealReview`` refuses (-> ``unavailable``) when the candidate's
      plan_hash/requirements/reviewed-evidence binding differs.

Run:  <venv>/python .../harness/negative_controls.py --snapshot <dir> --out <json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))

import lightgravity.coordinator  # noqa: E402,F401  (break import cycle)

import close_proof2 as cp  # noqa: E402  (sibling module)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    snapshot = Path(args.snapshot).resolve()
    raw = json.loads(Path(args.raw).read_text())
    events = raw["events"]
    sdk_save_dir = snapshot / "workspaces" / ".lg-sdk-sessions"
    refs = cp.EXPECTED_SESSIONS

    results: dict[str, Any] = {}

    # N1: unknown run -> refused.
    reader = cp.RecordedStopFactReader(
        events, sdk_save_dir=sdk_save_dir, run_session_refs=refs,
        origin_pid=1, reviewer_turn_completed=True,
    )
    r1 = reader.confirm_stopped("run_does_not_exist", refs)
    results["N1_unknown_run_refused"] = {"confirmed": r1.confirmed, "problems": list(r1.problems)}

    # N2: an unknown session id in the set -> refused.
    reader2 = cp.RecordedStopFactReader(
        events, sdk_save_dir=sdk_save_dir, run_session_refs=refs,
        origin_pid=1, reviewer_turn_completed=True,
    )
    r2 = reader2.confirm_stopped(cp.RUN_ID, (*refs[:-1], "sess_unknown_xxxxxxxx"))
    results["N2_unknown_session_refused"] = {"confirmed": r2.confirmed, "unknown": list(r2.unknown_sessions)}

    # N3: origin process reported alive -> reviewer stop unconfirmed -> refused.
    reader3 = cp.RecordedStopFactReader(
        events, sdk_save_dir=sdk_save_dir, run_session_refs=refs,
        origin_pid=1, reviewer_turn_completed=True,
    )
    reader3._process_exited = lambda: False  # type: ignore[method-assign]
    r3 = reader3.confirm_stopped(cp.RUN_ID, refs)
    results["N3_alive_origin_refused"] = {"confirmed": r3.confirmed, "problems": list(r3.problems)}

    # N4: recorded-review binding mismatch -> unavailable.
    review = raw["review"]
    adapter = cp.RecordedRealReview(review, {"resolved_evidence": review.get("resolved_evidence", [])})
    fake_candidate = SimpleNamespace(
        run_id="run_wrong", plan_hash="deadbeef", requirements_revision=999,
        candidate_ref="run_wrong",
    )
    ctx = SimpleNamespace(candidate=fake_candidate, resolved_evidence={})
    rep = adapter.review(ctx)  # type: ignore[arg-type]
    results["N4_binding_mismatch_unavailable"] = {
        "outcome": rep.outcome, "refusal": adapter.refusal_reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(results, indent=2, sort_keys=True))

    ok = (
        results["N1_unknown_run_refused"]["confirmed"] is False
        and results["N2_unknown_session_refused"]["confirmed"] is False
        and results["N3_alive_origin_refused"]["confirmed"] is False
        and results["N4_binding_mismatch_unavailable"]["outcome"] == "unavailable"
    )
    print("ALL_NEGATIVE_CONTROLS_REFUSED:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
