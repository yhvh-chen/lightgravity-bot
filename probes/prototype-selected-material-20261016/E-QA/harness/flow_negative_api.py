#!/usr/bin/env python3
"""LG-047 E-QA — negative / edge cases at the real HTTP seam (0 product calls).

Every case below must be rejected by the program **before** model dispatch, so
none of them consumes the campaign budget. The harness asserts the generation
ledger count is unchanged across the whole run.

Cases (docs/10 §5 / docs/11 §5):
  N1 over-limit (4 refs)          -> validation_failed 422 (max_selected_sources)
  N2 stale version/hash           -> source_stale 409
  N3 revoked source               -> not_found 404 (revoked:true)
  N4 cross-Task source            -> reference_invalid 422
  N5 missing / no readable body   -> not_found 404 or capability_unavailable 503

Legacy no-selection compatibility is covered by a response-shape assertion
elsewhere; it is NOT sent here because a real direct-answer message would spend
campaign budget (kept at 0 for this harness).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import Api  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
FIX = REPO / "examples/selected-material-prototype/fixtures"


def rec(out, key, value):
    out[key] = value
    print(f"[{key}] {json.dumps(value)[:500]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    api = Api(args.base)
    out: dict = {}
    _, g0 = api.generation()
    out["ledger_before"] = g0

    alpha = (FIX / "alpha-brief.txt").read_text()
    sentinel = (FIX / "cross-task-negative.txt").read_text()

    # Two Tasks: A owns cross-task source, B tries to select it.
    ta = api.create_task(request_id="qa-neg-ta", title="QA neg Task A", objective="A")["body"]["task_id"]
    tb = api.create_task(request_id="qa-neg-tb", title="QA neg Task B", objective="B")["body"]["task_id"]

    up = api.upload_inline(request_id="qa-neg-alpha", filename="alpha-brief.txt",
                           text=alpha, task_ref=ta, title="alpha")
    sid = up["body"]["source"]["id"]
    ver = up["body"]["source"]["source_version"]
    h = up["body"]["source"]["content_hash"]

    up_xt = api.upload_inline(request_id="qa-neg-xt", filename="cross-task-negative.txt",
                              text=sentinel, task_ref=ta, title="cross-task marker")
    sid_xt = up_xt["body"]["source"]["id"]

    # N1 over limit (4 refs -> validation_failed).
    refs4 = [{"source_id": sid} for _ in range(4)]
    r = api.task_message(ta, message_id="qa-neg-over", content="q", selected_sources=refs4)
    rec(out, "N1_over_limit", {"status": r["status"], "body": r["body"]})

    # N2 stale (wrong version/hash).
    r = api.task_message(ta, message_id="qa-neg-stale", content="q",
                         selected_sources=[{"source_id": sid, "source_version": 999,
                                            "content_hash": "sha256:deadbeef"}])
    rec(out, "N2_stale", {"status": r["status"], "body": r["body"]})

    # N3 revoked.
    rev = api.source_action(sid_xt, "revoke")
    rec(out, "revoke_action", {"status": rev[0], "body": rev[1]})
    r = api.task_message(ta, message_id="qa-neg-revoked", content="q",
                         selected_sources=[{"source_id": sid_xt}])
    rec(out, "N3_revoked", {"status": r["status"], "body": r["body"]})

    # N4 cross-Task: source belongs to Task A, select from Task B.
    up_xt2 = api.upload_inline(request_id="qa-neg-xt2", filename="cross-task-negative.txt",
                               text=sentinel, task_ref=ta, title="cross-task marker 2")
    sid_xt2 = up_xt2["body"]["source"]["id"]
    r = api.task_message(tb, message_id="qa-neg-xtask", content="q",
                         selected_sources=[{"source_id": sid_xt2}])
    rec(out, "N4_cross_task", {"status": r["status"], "body": r["body"]})

    # N5 missing body (plain text has no derivative) -> not_found / capability_unavailable.
    r = api.task_message(ta, message_id="qa-neg-nobody", content="q",
                         selected_sources=[{"source_id": sid}])
    rec(out, "N5_no_readable_body", {"status": r["status"], "body": r["body"]})

    _, g1 = api.generation()
    out["ledger_after"] = g1
    out["ledger_unchanged"] = (g0.get("count") == g1.get("count"))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {args.out}; ledger unchanged = {out['ledger_unchanged']}")


if __name__ == "__main__":
    main()
