#!/usr/bin/env python3
"""LG-047 E-QA — Flow A at the real HTTP/API seam (one real DeepSeek answer).

Steps (each recorded to evidence JSON):
  A1 upload alpha-brief.txt (real intake)          -> 0 product calls
  A2 poll receipt to terminal
  A3 send a Task message with selected_sources=[alpha] -> 1 product call
  A4 capture reply data: resolved_source_bindings / provided_context_note
  A5 read the real source content (kind=auto) and compare to the selected body
  A6 re-read history (task messages) and confirm the persisted binding

Also uploads gamma-decoy.txt **unselected** so a decoy leak can be checked.

Usage:
    python flow_a_api.py --base http://127.0.0.1:PORT --out evidence/flow_a.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import Api  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
FIX = REPO / "examples/selected-material-prototype/fixtures"


def load_facts():
    return json.loads((REPO / "examples/selected-material-prototype/expected-facts.json").read_text())


def rec(out: dict, key: str, value) -> None:
    out[key] = value
    print(f"[{key}] {json.dumps(value)[:400]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="alpha")
    ap.add_argument("--prep-only", action="store_true",
                    help="stop before the model call (0 product calls)")
    args = ap.parse_args()

    facts = load_facts()
    api = Api(args.base)
    out: dict = {"base": args.base, "started": time.time()}

    st, health = api.health()
    rec(out, "health", {"status": st, "body": health})

    # A1 — upload primary (alpha) inside a Task scope, plus unselected decoy.
    task = api.create_task(
        request_id="qa-flowA-task-1",
        title="ORION-71 selected-material QA (Flow A)",
        objective="Answer fact questions using the selected brief only.",
    )
    rec(out, "create_task", task)
    tid = task["body"]["task_id"] if isinstance(task["body"], dict) else None
    assert tid, "task creation failed"

    alpha_text = (FIX / "alpha-brief.txt").read_text()
    gamma_text = (FIX / "gamma-decoy.txt").read_text()

    up_a = api.upload_inline(request_id="qa-flowA-alpha", filename="alpha-brief.txt",
                             text=alpha_text, task_ref=tid, title="ORION-71 brief (sample)")
    rec(out, "upload_alpha", {"status": up_a["status"], "body": up_a["body"]})
    sid_a = up_a["body"]["source"]["id"]
    ver_a = up_a["body"]["source"]["source_version"]
    hash_a = up_a["body"]["source"]["content_hash"]

    up_g = api.upload_inline(request_id="qa-flowA-gamma", filename="gamma-decoy.txt",
                             text=gamma_text, task_ref=tid, title="ORION-99 decoy (sample)")
    rec(out, "upload_gamma_decoy", {"status": up_g["status"], "body": up_g["body"]})
    sid_g = up_g["body"]["source"]

    # Plain-text intake yields no derivative (LG-035 extraction not implemented);
    # the product-supported way to give the source a readable body is the human
    # formal edit. Record the observation, then materialize the formal layer.
    st_probe, cbody = api.source_content(sid_a, "auto")
    rec(out, "plain_text_body_probe", {"status": st_probe, "body": cbody})
    st_f, fbody = api.post(
        f"/api/v1/sources/{sid_a}/formal",
        {"content": alpha_text, "edited_by": "qa-human", "expected_revision": 0},
    )
    rec(out, "formal_edit_alpha", {"status": st_f, "body": fbody})["id"]

    # A2 — poll receipt to terminal.
    receipt = None
    for _ in range(60):
        st, receipt = api.receipt(sid_a)
        status = receipt.get("receipt", {}).get("status") if isinstance(receipt, dict) else None
        if status in ("succeeded", "failed", "rejected"):
            break
        time.sleep(1)
    rec(out, "receipt_alpha", {"status": st, "body": receipt})
    rec(out, "selected_ref", {"source_id": sid_a, "source_version": ver_a, "content_hash": hash_a})

    if args.prep_only:
        st, content = api.source_content(sid_a, "auto")
        rec(out, "source_content", {"status": st, "body": content})
        st, msgs = api.task_messages(tid)
        rec(out, "history_pre", {"status": st, "body": msgs})
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=2, default=str))
        print(f"prep-only done, wrote {args.out}")
        return

    # A3 — the ONE real product call: ask with the selected alpha source.
    q = ("Using only the selected brief, report: project code name, programme owner, "
         "primary launch date, total approved budget EUR, project id and change ticket.")
    msg = api.task_message(
        tid, message_id="qa-flowA-q1", content=q,
        selected_sources=[{"source_id": sid_a, "source_version": ver_a, "content_hash": hash_a}],
    )
    rec(out, "answer", {"status": msg["status"], "body": msg["body"]})

    body = msg["body"] if isinstance(msg["body"], dict) else {}
    reply = body.get("reply") or body.get("content")
    data = body.get("data") or {}
    rec(out, "reply_text", reply)
    rec(out, "reply_data", data)

    # A4 — answer judgement vs fixture truth (no decoy).
    truth = facts["fixtures"]["alpha-brief.txt"]
    decoy = facts["fixtures"]["gamma-decoy.txt"]
    required = [truth["project_code_name"], truth["programme_owner"],
                truth["primary_launch_date"], "418,250", truth["project_id"],
                truth["change_board_ticket"]]
    forbidden = [decoy["decoy_project_code_name"], decoy["decoy_programme_owner"],
                 decoy["decoy_primary_launch_date"], "999,999", decoy["decoy_project_id"],
                 decoy["decoy_change_board_ticket"]]
    reply_text = reply or ""
    rec(out, "fact_check", {
        "required_present": {k: (k in reply_text) for k in required},
        "forbidden_absent": {k: (k not in reply_text) for k in forbidden},
        "budget_form_alt": ("418250" in reply_text),
    })

    # A5 — open the real source content.
    st, content = api.source_content(sid_a, "auto")
    ctext = content.get("text") if isinstance(content, dict) else content
    rec(out, "source_content", {
        "status": st,
        "kind": content.get("kind") if isinstance(content, dict) else None,
        "chars": len(ctext or ""),
        "mentions_orion": "ORION-71" in (ctext or ""),
    })

    # A6 — history persist: re-read task messages from the SoT.
    st, msgs = api.task_messages(tid)
    items = msgs.get("items") if isinstance(msgs, dict) else msgs
    rec(out, "history", {"status": st, "count": len(items or []),
                         "sample": (items or [])[-1:]})

    out["finished"] = time.time()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
