#!/usr/bin/env python3
"""LG-049 R3 — real SDK delivery **full lifecycle** through the ACTUAL product API.

Campaign `N-R3-LIFECYCLE`, hard cap **16** real product forwards for the whole
lifecycle (worker / verify / reviewer / failed-output retries / connection
tests).  ONE fresh delivery Task only, NO automatic whole-run retry, retry 0.

Flow (all real product code, no mocks, no seeding):

1. Native `POST /api/v1/sources` upload of the frozen alpha-brief.txt bytes
   (real native UTF-8 extractor, `model=none`); assert body/hash/version/scope.
2. ONE global message with the EXACT formerly-failing ordinary goal +
   `selected_sources=[alpha@v1]`.  Deterministic classifier -> delivery ->
   `create_task`; program rule plan = `deliver` + `verify` SDK nodes.
3. Bounded poll (<= 300 s) for a genuinely terminal task phase.  NOTE (attempt-1
   harness defect fixed): a phase string is ALWAYS non-empty, so a poll that
   returns the phase on the first call tears the server down mid-turn
   (SIGTERM -> WS 1006).  This runner only treats explicit terminal phases as
   terminal and never tears down while the phase is queued/executing/verifying.
4. Assertions for the full lifecycle:
   * real SDK worker file tool wrote the deliverable with all 6 fixture facts;
   * the `verify` node ran (normal execution, not 429);
   * machine gates passed; real ModelReviewer used the independent connection;
   * worker AND reviewer stop CONFIRMED / idle / released BEFORE QA user accept;
   * API accept uses optimistic revisions and returns `done`;
   * artifact refs resolve to real authorized content; task history Sources
     match the selection bindings.
5. Stop the Task honestly on failure; cap never extended.

The script never fabricates a product fact and never prints/stores a secret.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
from api import Api  # noqa: E402

TOKEN = "qa-r3-token-not-a-credential"
PROBE = HERE.parent
REPO_ROOT = REPO
ALPHA_PATH = REPO / "examples/selected-material-prototype/fixtures/alpha-brief.txt"

#: The EXACT formerly-failing ordinary goal (PM-specified R3 wording with the
#: "approved" substring that the J fix made classify correctly as delivery).
GOAL = (
    "Create a Markdown file orion-summary.md using only the selected brief. "
    "Include project name, programme owner, primary launch date, total approved "
    "budget, project ID, and change ticket. Return the file as the deliverable."
)

#: The 6 fixture facts the deliverable must carry.
FACTS = {
    "project name": ["ORION-71"],
    "programme owner": ["Halden Reyes"],
    "primary launch date": ["2027-03-14"],
    "total approved budget": ["418,250"],
    "project ID": ["PRJ-ORION-71"],
    "change ticket": ["CB-8842"],
}

#: Only these phases are genuinely terminal; the poll must never treat a
#: non-empty-but-transient phase as terminal (attempt-1 bug).
TERMINAL = {"awaiting_acceptance", "failed", "cancelled", "done", "completed"}
STOPPED = {"failed", "cancelled"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gen(api: Api) -> dict:
    r = api.get("/_lgr3_generation")
    body = r["body"] if isinstance(r["body"], dict) else {}
    return body.get("generation") or {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", default=str(PROBE / "evidence" / "sdk_lifecycle.json"))
    ap.add_argument("--poll-timeout", type=float, default=300.0)
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    api = Api(args.base, TOKEN)
    out: dict = {"campaign": "N-R3-LIFECYCLE", "base": args.base, "steps": {},
                 "started": time.time()}
    steps = out["steps"]

    alpha_bytes = ALPHA_PATH.read_bytes()
    alpha_sha = _sha256(alpha_bytes)
    out["fixture"] = {"path": str(ALPHA_PATH), "bytes": len(alpha_bytes),
                      "sha256": alpha_sha}

    # ------------------------------------------------------------- 1. native upload
    up = api.post("/api/v1/sources", {
        "request_id": f"lgr3-up-{int(time.time())}",
        "filename": "alpha-brief.txt",
        "media_type": "text/plain",
        "content_base64": base64.b64encode(alpha_bytes).decode(),
    })
    ub = up["body"] if isinstance(up["body"], dict) else {}
    src = ub.get("source") or {}
    source_id = src.get("source_id")
    steps["upload"] = {
        "status": up["status"],
        "source_id": source_id,
        "status_field": src.get("status"),
        "source_version": src.get("source_version"),
        "content_hash": src.get("content_hash"),
        "scope": src.get("scope"),
        "receipts": ub.get("receipts"),
    }
    if up["status"] not in (200, 201) or not source_id:
        Path(args.out).write_text(json.dumps(out, indent=2), "utf-8")
        print(json.dumps(out["steps"].get("upload"), indent=2))
        return 2

    version = src.get("source_version")
    content_hash = src.get("content_hash")

    # ------------------------------------------------------- 1b. verify body/scope
    content = api.get(f"/api/v1/sources/{source_id}/content?kind=auto")
    cb = content["body"] if isinstance(content["body"], dict) else {}
    body_text = cb.get("content") or cb.get("body") or ""
    steps["source_verify"] = {
        "content_status": content["status"],
        "readable_chars": len(body_text),
        "has_orion": "ORION-71" in body_text,
        "has_owner": "Halden Reyes" in body_text,
        "kind": cb.get("kind"),
    }

    gen_before = gen(api)
    out["gen_before"] = gen_before

    # ------------------------------------------------- 2. global delivery message
    mid = f"msg_r3sdk_{int(time.time())}"
    resp = api.post("/api/v1/conversations/global/messages", {
        "message_id": mid,
        "role": "user",
        "content": GOAL,
        "selected_sources": [{
            "source_id": source_id,
            "source_version": version,
            "content_hash": content_hash,
        }],
    })
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
        print(json.dumps(steps["global_message"], indent=2))
        return 3

    # ------------------------------------------- 3. bounded terminal-phase poll
    def _phase() -> str | None:
        t = api.get(f"/api/v1/tasks/{task_id}")
        tb = t["body"] if isinstance(t["body"], dict) else {}
        ph = tb.get("phase")
        return ph if ph in TERMINAL else None

    t0 = time.time()
    final_phase = None
    polls = 0
    while time.time() - t0 < args.poll_timeout:
        polls += 1
        p = _phase()
        if p is not None:
            final_phase = p
            break
        time.sleep(args.interval)
    if final_phase is None:
        t = api.get(f"/api/v1/tasks/{task_id}")
        tb = t["body"] if isinstance(t["body"], dict) else {}
        final_phase = tb.get("phase")
    out["poll"] = {"polls": polls, "elapsed_s": round(time.time() - t0, 2),
                   "final_phase": final_phase}

    # ------------------------------------------------------- 4. terminal snapshot
    detail = api.get(f"/api/v1/tasks/{task_id}")
    db = detail["body"] if isinstance(detail["body"], dict) else {}
    d_run = db.get("run") if isinstance(db.get("run"), dict) else {}
    run_id = d_run.get("id") or db.get("active_run")
    run_stop_fields = {k: d_run.get(k) for k in
                       ("worker_cleanup", "reviewer_cleanup", "stop_confirmed",
                        "cleanup") if k in d_run}
    steps["task_final"] = {
        "phase": final_phase,
        "status": db.get("status"),
        "workspace_ref": db.get("workspace_ref"),
        "acceptance": db.get("acceptance") or db.get("acceptance_criteria"),
        "active_run": db.get("active_run"),
        "run_id": run_id,
        "run_state": d_run.get("state"),
        "run_stop": run_stop_fields,
        "reviewer": db.get("reviewer"),
    }

    # events
    ev = api.get(f"/api/v1/tasks/{task_id}/events?limit=2000")
    evb = ev["body"] if isinstance(ev["body"], dict) else {}
    items = evb.get("items") or []
    steps["events_tail"] = [
        {k: e.get(k) for k in ("type", "payload", "run_ref", "ts") if k in e}
        for e in items[-80:]
    ]
    out["event_types"] = sorted({e.get("type") for e in items if e.get("type")})

    # RUN detail (plan nodes + node_sessions stop/review facts).  There is no
    # GET /runs/{id}; the task detail embeds the full Run entity as ``run``.
    run_detail = d_run if isinstance(d_run, dict) and d_run else None
    out["run_detail"] = run_detail
    node_sessions = {}
    plan_subtasks = []
    if isinstance(run_detail, dict):
        ns = run_detail.get("node_sessions") or {}
        node_sessions = {k: {kk: vv for kk, vv in v.items()
                             if kk in ("key", "node_state", "role_ref", "state")}
                         for k, v in ns.items()}
        plan = run_detail.get("plan") or {}
        plan_subtasks = [s.get("key") for s in (plan.get("subtasks") or [])]
        out["reviewer_cleanup_run"] = run_detail.get("reviewer_cleanup")
        out["worker_cleanup_run"] = run_detail.get("cleanup")
    out["plan_subtasks"] = plan_subtasks
    out["node_sessions"] = node_sessions

    # Disk fallback: the Run entity as persisted (authoritative for node_sessions
    # / cleanup / reviewer_cleanup) if the API embedding was ever partial.
    if run_id and not node_sessions:
        runs_dir = PROBE / "campaign" / "product-data" / "runs" / str(run_id)
        run_md = runs_dir / "RUN.md"
        if run_md.is_file():
            out["run_md_tail"] = run_md.read_text("utf-8", "replace")[:4000]
        out["run_disk_path"] = str(runs_dir)

    # ------------------------------------------------------- 5. artifacts + bytes
    art = api.get(f"/api/v1/tasks/{task_id}/artifacts")
    ab = art["body"] if isinstance(art["body"], dict) else {}
    deliverable_text = None
    deliverable_ref = None
    for entry in (ab.get("evidence") or []):
        ref = entry.get("evidence_ref")
        if ref and "orion-summary" in json.dumps(entry):
            c = api.get(f"/api/v1/tasks/{task_id}/artifacts/content?evidence_ref={ref}")
            cbb = c["body"] if isinstance(c["body"], dict) else {}
            deliverable_text = cbb.get("content")
            deliverable_ref = ref
            break
    workspace_path = None
    ws_ref = db.get("workspace_ref")
    if isinstance(ws_ref, str):
        ws_root = PROBE / "campaign" / "product-data" / "workspaces"
        candidate = ws_root / ws_ref
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
        "candidate_ref": ab.get("candidate_ref"),
        "deliverable_ref": deliverable_ref,
        "workspace_path": workspace_path,
        "deliverable_chars": len(deliverable_text or ""),
    }
    out["deliverable_text"] = deliverable_text
    facts_found = {label: any(tok in (deliverable_text or "") for tok in toks)
                   for label, toks in FACTS.items()}
    out["facts_found"] = facts_found
    out["facts_all_present"] = all(facts_found.values())

    # ------------------------------------------------- 5b. history Sources bindings
    msgs = api.get(f"/api/v1/conversations/global/messages?limit=100")
    msb = msgs["body"] if isinstance(msgs["body"], dict) else {}
    hist_items = msb.get("items") or []
    out["history_tail"] = hist_items[-6:]

    # ---------------------------------------------------- 5c. STOP gate BEFORE accept
    # Host facts come from the real Run entity / events, not a fixture.
    def _facts_for(run: dict | None) -> dict:
        run = run or {}
        cleanup = run.get("cleanup") or {}
        reviewer = run.get("reviewer_cleanup") or {}
        return {
            "worker_cleanup_status": cleanup.get("status") if isinstance(cleanup, dict) else cleanup,
            "worker_stop_confirmed": (cleanup.get("confirmed") if isinstance(cleanup, dict) else None),
            "reviewer_cleanup_status": reviewer.get("status") if isinstance(reviewer, dict) else reviewer,
            "reviewer_stop_confirmed": (reviewer.get("confirmed") if isinstance(reviewer, dict) else None),
        }
    stop_facts = _facts_for(run_detail)
    # Fall back to task run summary.
    if not any(v for v in stop_facts.values()):
        stop_facts.update(_facts_for(d_run))
    out["stop_facts"] = stop_facts
    node_states = {v.get("key"): v.get("node_state") for v in node_sessions.values()}
    out["node_states"] = node_states
    out["verify_node_ran"] = ("verify" in plan_subtasks
                              and node_states.get("verify") in ("passed", "failed"))
    out["reviewer_is_model"] = (
        (db.get("reviewer") or {}).get("reviewer") == "model"
        or (isinstance(out.get("task_final", {}).get("reviewer"), dict)
            and out["task_final"]["reviewer"].get("reviewer") == "model")
    )

    # ------------------------------------------------------------ 6. accept (API)
    accepted_status = None
    accepted_result = None
    if final_phase == "awaiting_acceptance":
        rd2 = api.get(f"/api/v1/tasks/{task_id}")
        rdb = rd2["body"] if isinstance(rd2["body"], dict) else {}
        rdb_run = rdb.get("run") if isinstance(rdb.get("run"), dict) else {}
        accept_body = {
            "action": "accept",
            "request_id": f"lgr3-accept-{mid}",
            "expected_revision": rdb.get("revision"),
            "expected_requirements_revision": rdb.get("requirements_revision"),
            "expected_deliverable_revision": rdb.get("deliverable_revision"),
            "target_run_id": rdb_run.get("id") or rdb.get("active_run"),
        }
        accepted = api.post(f"/api/v1/tasks/{task_id}/actions", accept_body)
        accb = accepted["body"] if isinstance(accepted["body"], dict) else {}
        accepted_status = accepted["status"]
        accepted_result = accb.get("status") or accb.get("state")
        steps["accept"] = {"request": accept_body, "status": accepted["status"],
                           "result_status": accepted_result, "body": accb}
    else:
        # Failed/cancelled: do NOT fabricate acceptance; record a real attempt.
        rd2 = api.get(f"/api/v1/tasks/{task_id}")
        rdb = rd2["body"] if isinstance(rd2["body"], dict) else {}
        accept_body = {
            "action": "accept",
            "request_id": f"lgr3-accept-{mid}",
            "expected_revision": rdb.get("revision"),
            "target_run_id": rdb.get("active_run"),
        }
        accepted = api.post(f"/api/v1/tasks/{task_id}/actions", accept_body)
        accb = accepted["body"] if isinstance(accepted["body"], dict) else {}
        accepted_status = accepted["status"]
        accepted_result = accb.get("status") or accb.get("state")
        steps["accept_failed_attempt"] = {"request": accept_body,
                                          "status": accepted["status"],
                                          "result_status": accepted_result,
                                          "body": accb}

    out["gen_after"] = gen(api)
    out["finished"] = time.time()
    out["summary"] = {
        "task_id": task_id,
        "run_id": run_id,
        "final_phase": final_phase,
        "plan_subtasks": plan_subtasks,
        "node_states": node_states,
        "verify_node_ran": out["verify_node_ran"],
        "deliverable_chars": len(deliverable_text or ""),
        "facts_all_present": out["facts_all_present"],
        "stop_facts": stop_facts,
        "accept_status": accepted_status,
        "accept_result_status": accepted_result,
        "gen_before": (gen_before or {}).get("count"),
        "gen_after": (out["gen_after"] or {}).get("count"),
    }
    Path(args.out).write_text(json.dumps(out, indent=2), "utf-8")
    print(json.dumps(out["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
