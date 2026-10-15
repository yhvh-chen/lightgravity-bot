"""Independent QA (lg031-close-audit) additional negative controls.

Uses the *actual* PROOF2-CLOSE harness module (no product change, no live model,
no network) and adds controls the original suite did not cover:

  X1  execution_finished with state != succeeded must NOT count as stopped
      (guards against "finished == teardown" over-claim).
  X2  a session present in events but with NO SQLite DB must NOT count as
      stopped (guards the DB-existence leg).
  X3  RecordedRealReview must refuse when requirements_revision differs but the
      rest matches (isolates the requirements binding).

Read-only over the private snapshot copy; writes only to the QA out path.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "probes" / "lg031" / "PROOF2-CLOSE" / "harness"))

import lightgravity.coordinator  # noqa: E402,F401
import close_proof2 as cp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    snapshot = Path(args.snapshot).resolve()
    raw = json.loads(Path(args.raw).read_text())
    events = raw["events"]
    save_dir = snapshot / "workspaces" / ".lg-sdk-sessions"
    refs = cp.EXPECTED_SESSIONS
    out: dict = {}

    # X1: flip one session's execution_finished state to "failed" -> must not pass.
    ev_bad = copy.deepcopy(events)
    flipped = False
    for e in ev_bad:
        if e.get("type") == "adapter.execution_finished" and not flipped:
            e["result"]["state"] = "failed"
            flipped = True
    r = cp.RecordedStopFactReader(ev_bad, sdk_save_dir=save_dir, run_session_refs=refs,
                                  origin_pid=1, reviewer_turn_completed=True)
    x1 = r.confirm_stopped(cp.RUN_ID, refs)
    out["X1_non_succeeded_finish_refused"] = {
        "confirmed": x1.confirmed, "sessions_stopped": x1.sessions_stopped,
        "unknown": list(x1.unknown_sessions),
    }

    # X2: point the reader at a save_dir with no DBs -> must not pass.
    empty = snapshot / "workspaces" / ".lg-sdk-sessions-EMPTY-FOR-TEST"
    empty.mkdir(exist_ok=True)
    r2 = cp.RecordedStopFactReader(events, sdk_save_dir=empty, run_session_refs=refs,
                                   origin_pid=1, reviewer_turn_completed=True)
    x2 = r2.confirm_stopped(cp.RUN_ID, refs)
    out["X2_missing_sqlite_refused"] = {
        "confirmed": x2.confirmed, "sessions_stopped": x2.sessions_stopped,
        "problems": list(x2.problems),
    }

    # X3: requirements_revision mismatch only -> unavailable.
    review = raw["review"]
    ad = cp.RecordedRealReview(review, {"resolved_evidence": review.get("resolved_evidence", [])})
    cand = SimpleNamespace(run_id=cp.RUN_ID, plan_hash=cp.PLAN_HASH,
                           requirements_revision=999, candidate_ref=cp.RUN_ID)
    ctx = SimpleNamespace(candidate=cand, resolved_evidence=set(review["resolved_evidence"]))
    rep = ad.review(ctx)  # type: ignore[arg-type]
    out["X3_requirements_mismatch_unavailable"] = {
        "outcome": rep.outcome, "refusal": ad.refusal_reason,
    }

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    ok = (
        out["X1_non_succeeded_finish_refused"]["confirmed"] is False
        and out["X2_missing_sqlite_refused"]["confirmed"] is False
        and out["X3_requirements_mismatch_unavailable"]["outcome"] == "unavailable"
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    print("INDEPENDENT_CONTROLS_ALL_REFUSED:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
