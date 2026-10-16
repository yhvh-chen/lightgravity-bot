#!/usr/bin/env python3
"""LG-047 R2 — pre-forward negative/edge cases (0 additional model calls).

All cases must be refused **before** model dispatch. We verify the frozen error
codes and additionally confirm the product persistent generation ledger count is
**unchanged** before/after (proving no forward).

Cases:
  N1 over-limit (4 refs)            -> validation_failed 422 (+max_selected_sources)
  N2 stale version                  -> source_stale 409
  N3 stale content_hash             -> source_stale 409
  N4 revoked source                 -> not_found 404 (details.revoked)
  N5 cross-Task selection           -> reference_invalid 422
  N6 missing/nonexistent source ref -> reference_invalid 422
  N7 unreadable (bodyless) source   -> capability_unavailable 503 (or 404)
  N8 oversize (>12000 chars)        -> 200 explicit truncation metadata

No OCR, no seed, no manual derivative writes; only real UI-equivalent uploads
of human SAMPLE fixture bytes (native text, auto-extracted).

Run:
    python negatives.py --base http://127.0.0.1:PORT
"""

from __future__ import annotations

import argparse
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


def upload(api: Api, request_id: str, filename: str, text: str, *, task_ref=None,
           media_type="text/plain") -> dict:
    import base64

    body = {
        "request_id": request_id,
        "filename": filename,
        "content_base64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "media_type": media_type,
        "title": filename,
        "scope": {"task_ref": task_ref, "project_ref": None, "inbox_ref": None},
    }
    return api.post("/api/v1/sources", body)


def wait_extracted(api: Api, sid: str, tries: int = 40) -> dict:
    last = None
    for _ in range(tries):
        last = api.get(f"/api/v1/sources/{sid}")
        b = last["body"] if isinstance(last["body"], dict) else {}
        if b.get("status") in ("extracted", "attributed", "indexed", "partial", "failed"):
            return last
        time.sleep(0.25)
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", default=str(HERE.parent / "evidence" / "negatives.json"))
    args = ap.parse_args()

    api = Api(args.base, TOKEN)
    out: dict = {"base": args.base, "cases": {}, "started": time.time()}

    def gen_count() -> dict:
        r = api.get("/_lg047r2_generation")
        return (r["body"] or {}).get("generation")

    out["ledger_before"] = gen_count()

    # --- Task scope + two real native-text uploads -------------------------
    t = api.post("/api/v1/tasks", {"request_id": "qa-r2-neg-task-A",
                                   "title": "R2 negatives A",
                                   "objective": "negative cases"})
    tid = t["body"]["task_id"]
    t2 = api.post("/api/v1/tasks", {"request_id": "qa-r2-neg-task-B",
                                    "title": "R2 negatives B",
                                    "objective": "negative cases"})
    tid_b = t2["body"]["task_id"]

    alpha = (FIX / "alpha-brief.txt").read_text()
    cross = (FIX / "cross-task-negative.txt").read_text()

    up = upload(api, "qa-r2-neg-alpha", "alpha-brief.txt", alpha, task_ref=tid)
    sid = up["body"]["source"]["id"]
    ver = up["body"]["source"]["source_version"]
    chash = up["body"]["source"]["content_hash"]
    recv = wait_extracted(api, sid)
    out["alpha_source"] = {"id": sid, "version": ver, "hash": chash,
                           "status": recv["body"].get("status") if isinstance(recv["body"], dict) else None}

    up_x = upload(api, "qa-r2-neg-cross", "cross-task-negative.txt", cross, task_ref=tid_b)
    sid_x = up_x["body"]["source"]["id"]
    wait_extracted(api, sid_x)

    def send(task, mid, content, refs):
        return api.post(f"/api/v1/tasks/{task}/messages",
                        {"message_id": mid, "role": "user", "content": content,
                         "selected_sources": refs})

    def case(name, resp, expect_status, expect_code):
        b = resp["body"] if isinstance(resp["body"], dict) else {}
        err = b.get("error", {}) if isinstance(b.get("error"), dict) else {}
        code = err.get("code") or b.get("code")
        entry = {"status": resp["status"], "code": code, "body": resp["body"]}
        entry["pass"] = (resp["status"] == expect_status and code == expect_code)
        out["cases"][name] = entry
        print(f"[{name}] status={resp['status']} code={code} pass={entry['pass']}")
        return entry

    # N1 over-limit (4 refs) ------------------------------------------------
    ref = {"source_id": sid, "source_version": ver, "content_hash": chash}
    case("N1_over_limit", send(tid, "qa-r2-n1", "q", [ref, ref, ref, ref]),
         422, "validation_failed")

    # N2 stale version ------------------------------------------------------
    case("N2_stale_version",
         send(tid, "qa-r2-n2", "q", [{"source_id": sid, "source_version": ver + 99,
                                       "content_hash": chash}]),
         409, "source_stale")

    # N3 stale content_hash -------------------------------------------------
    case("N3_stale_hash",
         send(tid, "qa-r2-n3", "q", [{"source_id": sid, "source_version": ver,
                                       "content_hash": "sha256:deadbeef"}]),
         409, "source_stale")

    # N4 revoked ------------------------------------------------------------
    rev = api.post(f"/api/v1/sources/{sid}/actions", {"action": "revoke", "confirmed": True})
    out["cases"]["N4_revoke_action"] = {"status": rev["status"], "body": rev["body"]}
    case("N4_revoked",
         send(tid, "qa-r2-n4", "q", [{"source_id": sid, "source_version": ver,
                                      "content_hash": chash}]),
         404, "not_found")

    # N5 cross-Task ---------------------------------------------------------
    case("N5_cross_task",
         send(tid, "qa-r2-n5", "q", [{"source_id": sid_x}]),
         422, "reference_invalid")

    # N6 missing/nonexistent ref -------------------------------------------
    case("N6_missing_ref",
         send(tid, "qa-r2-n6", "q", [{"source_id": "source_does_not_exist"}]),
         422, "reference_invalid")

    # N7 unreadable/bodyless: a source with a bodyless state. Upload opaque
    # binary with an unknown media type -> stays `received`, no body.
    import base64
    bin_up = api.post("/api/v1/sources", {
        "request_id": "qa-r2-neg-bin",
        "filename": "opaque.bin",
        "content_base64": base64.b64encode(b"\x00\x01\x02\x03opaque-binary").decode(),
        "media_type": "application/octet-stream",
        "title": "opaque",
        "scope": {"task_ref": tid, "project_ref": None, "inbox_ref": None},
    })
    sid_bin = bin_up["body"]["source"]["id"]
    out["cases"]["N7_bin_upload"] = {"status": bin_up["status"],
                                     "source_status": bin_up["body"]["source"].get("status")}
    r7 = send(tid, "qa-r2-n7", "q", [{"source_id": sid_bin}])
    b7 = r7["body"] if isinstance(r7["body"], dict) else {}
    e7 = b7.get("error", {}) if isinstance(b7.get("error"), dict) else {}
    c7 = e7.get("code") or b7.get("code")
    out["cases"]["N7_unreadable"] = {
        "status": r7["status"], "code": c7, "body": r7["body"],
        "pass": r7["status"] in (503, 404) and c7 in ("capability_unavailable", "not_found"),
    }
    print(f"[N7_unreadable] status={r7['status']} code={c7} pass={out['cases']['N7_unreadable']['pass']}")

    # N8 oversize (> 12000 chars) is intentionally NOT sent here: a successful
    # reply would consume one of the 8 model calls. It is exercised separately
    # (see oversize_truncation.py / a local unit) so the pre-forward negatives
    # below stay at 0 model calls.

    out["ledger_after"] = gen_count()
    out["ended"] = time.time()
    Path(args.out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("ledger_before", out["ledger_before"], "ledger_after", out["ledger_after"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
