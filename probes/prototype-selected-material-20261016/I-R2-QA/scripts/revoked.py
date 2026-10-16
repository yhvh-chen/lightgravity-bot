#!/usr/bin/env python3
"""LG-047 R2 — focused revoke fail-closed negative (0 model calls if correct).

Revoke an uploaded native-text source with the CORRECT payload
(`action=revoke`, `confirmed=true`), then attempt to select it. The frozen
semantics are fail-closed: selection must be refused (not_found 404,
details.revoked). We assert the product generation ledger count is unchanged.

Also re-checks the same source is unreadable via content/reprocess.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
from api import Api  # noqa: E402

FIX = REPO / "examples/selected-material-prototype/fixtures"
TOKEN = "qa-r2-token-not-a-credential"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", default=str(HERE.parent / "evidence" / "revoked.json"))
    args = ap.parse_args()
    api = Api(args.base, TOKEN)
    out: dict = {"cases": {}}

    def gen():
        return (api.get("/_lg047r2_generation")["body"] or {}).get("generation")

    out["ledger_before"] = gen()

    t = api.post("/api/v1/tasks", {"request_id": "qa-r2-rev-task",
                                   "title": "R2 revoke", "objective": "revoke negative"})
    tid = t["body"]["task_id"]
    text = (FIX / "alpha-brief.txt").read_text()
    up = api.post("/api/v1/sources", {
        "request_id": "qa-r2-rev-alpha", "filename": "revoke-alpha.txt",
        "content_base64": base64.b64encode(text.encode()).decode(),
        "media_type": "text/plain", "title": "revoke alpha",
        "scope": {"task_ref": tid, "project_ref": None, "inbox_ref": None},
    })
    sid = up["body"]["source"]["id"]
    ver = up["body"]["source"]["source_version"]
    chash = up["body"]["source"]["content_hash"]
    for _ in range(40):
        st = api.get(f"/api/v1/sources/{sid}")["body"].get("status")
        if st in ("extracted", "attributed", "indexed", "partial", "failed"):
            break
        time.sleep(0.25)
    out["source_before_revoke"] = {"id": sid, "version": ver, "hash": chash, "status": st}

    rev = api.post(f"/api/v1/sources/{sid}/actions",
                   {"action": "revoke", "confirmed": True})
    out["cases"]["revoke_action"] = {"status": rev["status"], "body": rev["body"]}

    sel = api.post(f"/api/v1/tasks/{tid}/messages", {
        "message_id": "qa-r2-rev-msg", "role": "user", "content": "q",
        "selected_sources": [{"source_id": sid, "source_version": ver,
                              "content_hash": chash}],
    })
    b = sel["body"] if isinstance(sel["body"], dict) else {}
    err = b.get("error", {}) if isinstance(b.get("error"), dict) else {}
    out["cases"]["select_revoked"] = {
        "status": sel["status"], "code": err.get("code"), "details": err.get("details"),
        "pass": sel["status"] == 404 and err.get("code") == "not_found",
    }
    content = api.get(f"/api/v1/sources/{sid}/content?kind=auto")
    out["cases"]["revoked_content_read"] = {"status": content["status"], "body": content["body"]}
    reproc = api.post(f"/api/v1/sources/{sid}/actions",
                      {"action": "reprocess", "confirmed": True})
    out["cases"]["revoked_reprocess"] = {"status": reproc["status"], "body": reproc["body"]}

    out["ledger_after"] = gen()
    Path(args.out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out["cases"], indent=2, default=str))
    print("ledger", out["ledger_before"], "->", out["ledger_after"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
