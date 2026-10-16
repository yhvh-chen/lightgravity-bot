#!/usr/bin/env python3
"""LG-049 R3 — post-accept read-only verification (ZERO model calls).

Re-reads the final Task/Run via the real API (no executor dispatch: the Task is
terminal), and resolves each acceptance evidence ref through the real artifacts
content/download endpoints to confirm they point at actual authorized content;
then re-reads the global message history to confirm the Sources bindings match
the selection snapshot.

This does not start any model turn; the Task/Run are already terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from api import Api  # noqa: E402

TOKEN = "qa-r3-token-not-a-credential"
PROBE = HERE.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--out", default=str(PROBE / "evidence" / "post_accept_verify.json"))
    args = ap.parse_args()

    api = Api(args.base, TOKEN)
    out: dict = {"task_id": args.task_id}

    detail = api.get(f"/api/v1/tasks/{args.task_id}")
    db = detail["body"] if isinstance(detail["body"], dict) else {}
    out["task_status"] = db.get("status")
    out["task_phase"] = db.get("phase")
    acc = db.get("acceptance") or {}
    out["acceptance_status"] = acc.get("status")
    out["evidence_refs"] = acc.get("evidence_refs")
    out["active_run"] = db.get("active_run")

    # Resolve each evidence ref through the real content endpoint.
    resolved = []
    for ref in (acc.get("evidence_refs") or []):
        c = api.get(f"/api/v1/tasks/{args.task_id}/artifacts/content?evidence_ref={ref}")
        cb = c["body"] if isinstance(c["body"], dict) else {}
        content = cb.get("content") or cb.get("body") or ""
        resolved.append({
            "ref": ref,
            "status": c["status"],
            "chars": len(content) if isinstance(content, str) else None,
            "sha256_header": cb.get("sha256") or cb.get("content_hash"),
            "preview": (content[:120] if isinstance(content, str) else None),
        })
    out["evidence_resolution"] = resolved

    # Download endpoint for the deliverable ref.
    dl = api.get(f"/api/v1/tasks/{args.task_id}/artifacts/download?evidence_ref=orion-summary.md")
    out["download_orion"] = {"status": dl["status"]}

    # History Sources match selection.
    msgs = api.get("/api/v1/conversations/global/messages?limit=50")
    msb = msgs["body"] if isinstance(msgs["body"], dict) else {}
    items = msb.get("items") or []
    out["history_len"] = len(items)
    # Find assistant rows carrying resolved_source_bindings.
    for it in items:
        m = it.get("message") if isinstance(it.get("message"), dict) else it
        if m.get("role") == "assistant":
            out["assistant_bindings"] = m.get("resolved_source_bindings")
            out["assistant_message_id"] = m.get("message_id")
    # Cross-check against the run selected_trigger snapshot.
    br = db.get("run") if isinstance(db.get("run"), dict) else {}
    trig = br.get("selected_trigger") or db.get("selected_trigger") or {}
    snap = (trig or {}).get("snapshot") or {}
    out["trigger_message_id"] = trig.get("message_id")
    out["trigger_refs"] = [r.get("source_id") for r in (snap.get("refs") or [])]

    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
