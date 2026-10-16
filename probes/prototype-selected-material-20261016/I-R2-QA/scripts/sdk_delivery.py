#!/usr/bin/env python3
"""LG-047 R2 — real SDK delivery through the ACTUAL product API.

Flow (all real product code, no mocks, no seeding):

1. Verify the existing fresh GLOBAL native-alpha source
   ``source_01M521GDB7S4XB86X3WKPD2B6W`` is readable, has the expected
   version/hash and the native body (no OCR / no seeding).
2. POST one global message with ``selected_sources=[alpha]`` and an explicit
   user goal that asks for a Markdown deliverable.  The deterministic
   classifier routes it as a delivery -> the program creates an authorized Task
   workspace (``tasks/<id>``) + a derived acceptance criterion (ordinary program
   rule plan, NOT a model planner) and queues a Run.
3. The real coordinator queue loop dispatches the Run to the REAL SDK worker
   (antigravity/openai-compat via loopback proxy) which uses a real file tool to
   write the deliverable into the Task workspace.
4. The real independent ModelReviewer (separate reviewer connection) reviews the
   candidate; the real stop/release gate confirms; the Task moves to
   ``awaiting_acceptance``.
5. QA reads the actual artifact bytes (from the Task artifacts API AND from the
   workspace on disk) and checks the fixture facts are present; then the QA user
   ACCEPTs via the real API.

Every real upstream forward consumes the shared product generation ledger; the
JSON result records before/after counts, model IDs, stop facts and the artifact
bytes.  The script itself never fabricates any product fact.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
from api import Api  # noqa: E402

TOKEN = "qa-r2-token-not-a-credential"
ALPHA_SID = "source_01M521GDB7S4XB86X3WKPD2B6W"
ALPHA_HASH = "d34f0ca58b8dbfbd4c9ac29be31aba7122500cb1a3317e3c19a6ed7b3d59af6f"
ALPHA_VERSION = 1

# NOTE (LG-047 R2 finding): the PM-suggested wording "...total approved
# budget..." is mis-classified by the deterministic classifier as DECISION
# because the substring "approve" (inside "approved") matches the control
# keyword, so it would NOT create a delivery Task.  This is reported as a
# root-important product finding.  The goal below keeps the exact same required
# deliverable content (all six facts) with a verb-first wording that classifies
# correctly as a delivery (\"create\").  Nothing else in the flow is weakened.
GOAL = (
    "Create the deliverable orion-summary.md (Markdown) using only the selected "
    "brief. It must contain the project name, programme owner, primary launch "
    "date, total budget, project ID, and change ticket. Return the file as the "
    "deliverable."
)

# Fixture facts the deliverable must carry (all 6 fields requested by the goal).
FACTS = {
    "project name / code": ["ORION-71"],
    "programme owner": ["Halden Reyes"],
    "primary launch date": ["2027-03-14"],
    "total approved budget": ["418,250"],
    "project ID": ["PRJ-ORION-71"],
    "change ticket": ["CB-8842"],
}


def gen(api: Api) -> dict:
    r = api.get("/_lg047r2_generation")
    body = r["body"] if isinstance(r["body"], dict) else {}
    return body.get("generation") or {}


def poll(fn, *, timeout: float, interval: float = 1.0):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = fn()
        if last is not None:
            return last
        time.sleep(interval)
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", default=str(HERE.parent / "evidence" / "sdk_delivery.json"))
    ap.add_argument("--poll-timeout", type=float, default=150.0)
    args = ap.parse_args()

    api = Api(args.base, TOKEN)
    out: dict = {"base": args.base, "steps": {}, "started": time.time()}
    steps = out["steps"]

    # ---------------------------------------------------------------- 1. source
    src = api.get(f"/api/v1/sources/{ALPHA_SID}")
    sb = src["body"] if isinstance(src["body"], dict) else {}
    content = api.get(f"/api/v1/sources/{ALPHA_SID}/content?kind=machine")
    cb = content["body"] if isinstance(content["body"], dict) else {}
    body_text = cb.get("content") or cb.get("body") or ""
    steps["source_check"] = {
        "status": src["status"],
        "status_field": sb.get("status"),
        "source_version": sb.get("source_version"),
        "content_hash": sb.get("content_hash"),
        "scope": sb.get("scope"),
        "version_ok": sb.get("source_version") == ALPHA_VERSION,
        "hash_ok": (sb.get("content_hash") or "").endswith(ALPHA_HASH[:12])
        or sb.get("content_hash") == ALPHA_HASH,
        "readable_chars": len(body_text),
        "has_orion": "ORION-71" in body_text,
    }
    if not body_text:
        steps["source_check"]["error"] = "source body unreadable"
        Path(args.out).write_text(json.dumps(out, indent=2), "utf-8")
        print(json.dumps(out, indent=2))
        return 2

    gen_before = gen(api)
    out["gen_before"] = gen_before

    # ------------------------------------------------- 2. global delivery message
    mid = f"msg_r2sdk_{int(time.time())}"
    resp = api.post(
        "/api/v1/conversations/global/messages",
        {
            "message_id": mid,
            "role": "user",
            "content": GOAL,
            "selected_sources": [
                {"source_id": ALPHA_SID, "source_version": ALPHA_VERSION,
                 "content_hash": ALPHA_HASH}
            ],
        },
    )
    rb = resp["body"] if isinstance(resp["body"], dict) else {}
    steps["global_message"] = {
        "status": resp["status"],
        "kind": rb.get("kind"),
        "task_id": rb.get("task_id"),
        "queue_state": rb.get("queue_state"),
        "data": rb.get("data"),
        "reply": rb.get("reply"),
    }
    task_id = rb.get("task_id")
    if resp["status"] != 200 or not task_id:
        Path(args.out).write_text(json.dumps(out, indent=2), "utf-8")
        print(json.dumps(out, indent=2))
        return 3

    # ------------------------------------------- 3. wait for awaiting_acceptance
    # BUGFIX (R2 harness): the phase is ALWAYS a non-empty string, so a poll
    # that returns the phase on the first call exits immediately (in
    # 'queued'/'executing') and tears the server down mid-turn, which SIGTERMs
    # the SDK harness (WS 1006).  Wait for a genuinely terminal phase.
    TERMINAL = {"awaiting_acceptance", "failed", "cancelled", "done", "completed"}

    def _phase() -> str | None:
        t = api.get(f"/api/v1/tasks/{task_id}")
        tb = t["body"] if isinstance(t["body"], dict) else {}
        ph = tb.get("phase")
        return ph if ph in TERMINAL else None

    final_phase = poll(_phase, timeout=args.poll_timeout)
    if final_phase is None:
        # bounded escape: read the last phase for an honest report
        t = api.get(f"/api/v1/tasks/{task_id}")
        tb = t["body"] if isinstance(t["body"], dict) else {}
        final_phase = tb.get("phase")
    # Capture the terminal task detail + run info.
    detail = api.get(f"/api/v1/tasks/{task_id}")
    db = detail["body"] if isinstance(detail["body"], dict) else {}
    db_run = db.get("run") if isinstance(db.get("run"), dict) else {}
    steps["task_final"] = {
        "phase": final_phase,
        "status": db.get("status"),
        "workspace_ref": db.get("workspace_ref"),
        "acceptance": db.get("acceptance"),
        "active_run": db.get("active_run"),
        "run_state": db_run.get("state"),
        "run_id": db_run.get("id") or db_run.get("run_id"),
        "run_stop": {
            k: db_run.get(k)
            for k in ("worker_cleanup", "reviewer_cleanup", "stop_confirmed")
            if k in db_run
        },
    }

    # events (bounded read)
    ev = api.get(f"/api/v1/tasks/{task_id}/events?limit=2000")
    evb = ev["body"] if isinstance(ev["body"], dict) else {}
    steps["events_tail"] = [
        {k: e.get(k) for k in ("type", "payload", "run_ref") if k in e}
        for e in (evb.get("items") or [])[-40:]
    ]

    # ------------------------------------------------------- 4. artifacts + bytes
    art = api.get(f"/api/v1/tasks/{task_id}/artifacts")
    ab = art["body"] if isinstance(art["body"], dict) else {}
    deliverable_text = None
    deliverable_ref = None
    # Prefer canonical evidence ref content, else workspace file read.
    for entry in (ab.get("evidence") or []):
        ref = entry.get("evidence_ref")
        if ref and "orion-summary" in json.dumps(entry):
            c = api.get(
                f"/api/v1/tasks/{task_id}/artifacts/content?evidence_ref={ref}"
            )
            cbb = c["body"] if isinstance(c["body"], dict) else {}
            deliverable_text = cbb.get("content")
            deliverable_ref = ref
            break

    # Also read directly from the authorized workspace on disk (product root).
    workspace_path = None
    if isinstance(db.get("workspace_ref"), str):
        from lightgravity.config import Settings  # type: ignore

        data_dir = Path(__file__).resolve().parents[1] / "campaign" / "product-data"
        ws_root = data_dir / "workspaces"
        candidate = ws_root / str(db["workspace_ref"])
        orion = None
        if candidate.is_dir():
            for p in candidate.rglob("*.md"):
                orion = p
                break
        if orion is not None:
            workspace_path = str(orion)
            if deliverable_text is None:
                deliverable_text = orion.read_text("utf-8", "replace")

    steps["artifacts"] = {
        "status": art["status"],
        "categories": {
            k: [e.get("name") or e.get("evidence_ref") or e for e in v]
            for k, v in (ab.get("categories") or {}).items()
        },
        "candidate_ref": ab.get("candidate_ref"),
        "deliverable_ref": deliverable_ref,
        "workspace_path": workspace_path,
        "deliverable_chars": len(deliverable_text or ""),
    }
    out["deliverable_text"] = deliverable_text
    facts_found = {
        label: (any(tok in (deliverable_text or "") for tok in toks))
        for label, toks in FACTS.items()
    }
    out["facts_found"] = facts_found
    out["facts_all_present"] = all(facts_found.values())

    # ------------------------------------------------------------ 5. accept (API)
    rd = api.get(f"/api/v1/tasks/{task_id}")
    rdb = rd["body"] if isinstance(rd["body"], dict) else {}
    revision = rdb.get("revision")
    rdb_run = rdb.get("run") if isinstance(rdb.get("run"), dict) else {}
    accept_body = {
        "action": "accept",
        "request_id": f"qa-r2-accept-{mid}",
        "expected_revision": revision,
        "expected_requirements_revision": rdb.get("requirements_revision"),
        "expected_deliverable_revision": rdb.get("deliverable_revision"),
        "target_run_id": rdb_run.get("id") or rdb.get("active_run"),
    }
    accepted = api.post(f"/api/v1/tasks/{task_id}/actions", accept_body)
    accb = accepted["body"] if isinstance(accepted["body"], dict) else {}
    steps["accept"] = {
        "request": accept_body,
        "status": accepted["status"],
        "result_status": accb.get("status"),
        "body": accb,
    }

    out["gen_after"] = gen(api)
    out["finished"] = time.time()
    out["summary"] = {
        "task_id": task_id,
        "final_phase": final_phase,
        "deliverable_chars": len(deliverable_text or ""),
        "facts_all_present": out["facts_all_present"],
        "accept_status": accepted["status"],
        "accept_result_status": accb.get("status") or accb.get("state"),
        "gen_before": gen_before.get("count"),
        "gen_after": (out["gen_after"] or {}).get("count"),
    }
    Path(args.out).write_text(json.dumps(out, indent=2), "utf-8")
    print(json.dumps(out["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
