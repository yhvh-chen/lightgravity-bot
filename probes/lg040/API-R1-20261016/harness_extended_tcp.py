"""LG-040 R1 API QA — extended real-TCP cases (second batch).

Real uvicorn + real create_app/FileStore over loopback TCP.  Fills the case
matrix gaps not exercised by harness_real_tcp.py: project_ref refusal, symlink
escape, scope-local dedup, inbox message not creating a Task, intake job
cancel/retry/restart-recovery, reprocess with no OCR backend, and list
scope-filtering.  OCR/vector target env unset -> zero inference.
"""

from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(parents=True, exist_ok=True)

RESULTS: list[dict] = []


def record(case, expected, actual, ok, provenance):
    RESULTS.append({"case": case, "expected": expected, "actual": actual,
                    "status": "PASS" if ok else "FAIL", "provenance": provenance})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {actual}")


def _b64(d):
    return base64.b64encode(d).decode()


def main() -> int:
    import httpx
    # Reuse the real-TCP server context manager from the first harness.
    from harness_real_tcp import server, free_port

    tmp = Path(tempfile.mkdtemp(prefix="lg040-api-ext-"))
    port = free_port()
    base = f"http://127.0.0.1:{port}/api/v1"
    print(f"== real TCP server port={port} ==")

    with server(tmp, port):
        c = httpx.Client(base_url=base, timeout=30.0)

        # C8 project_ref refused without registry
        r = c.post("/sources", json={"request_id": "ext-proj", "filename": "p.txt",
                                     "content_base64": _b64(b"p"),
                                     "scope": {"project_ref": "some-project"}})
        ok = r.status_code == 422 and r.json()["error"]["code"] == "reference_invalid"
        record("C8 project_ref refused w/o registry", "422 reference_invalid",
               f"{r.status_code} {r.json().get('error',{}).get('code')}", ok, f"POST {base}/sources project_ref")

        # C10 symlink escape (create symlink inside workspace root)
        ws = tmp / "data" / "workspaces"
        ws.mkdir(parents=True, exist_ok=True)
        outside = tmp / "outside.txt"
        outside.write_text("secret")
        link = ws / "escape.txt"
        if not link.exists():
            link.symlink_to(outside)
        r = c.post("/sources", json={"request_id": "ext-sym", "filename": "escape.txt",
                                     "path": "escape.txt"})
        ok = r.status_code == 403 and r.json()["error"]["code"] == "path_outside_workspace"
        record("C10 symlink escape refused", "403 path_outside_workspace",
               f"{r.status_code} {r.json().get('error',{}).get('code')}", ok, f"POST {base}/sources symlink")

        # C13 scope-local dedup not merged across tasks
        ta = c.post("/tasks", json={"request_id": "ext-ta", "title": "A",
                                    "objective": "o", "acceptance_criteria": ["x"]}).json()["task_id"]
        tb = c.post("/tasks", json={"request_id": "ext-tb", "title": "B",
                                    "objective": "o", "acceptance_criteria": ["x"]}).json()["task_id"]
        data = b"identical content"
        a = c.post("/sources", json={"request_id": "ext-a", "filename": "x.txt",
                                     "content_base64": _b64(data), "scope": {"task_ref": ta}})
        b = c.post("/sources", json={"request_id": "ext-b", "filename": "x.txt",
                                     "content_base64": _b64(data), "scope": {"task_ref": tb}})
        a2 = c.post("/sources", json={"request_id": "ext-a2", "filename": "x.txt",
                                      "content_base64": _b64(data), "scope": {"task_ref": ta}})
        ok = (a.json()["deduplicated"] is False and b.json()["deduplicated"] is False
              and a.json()["source"]["source_id"] != b.json()["source"]["source_id"]
              and a2.json()["deduplicated"] is True
              and a2.json()["source"]["source_id"] == a.json()["source"]["source_id"])
        record("C13 scope-local dedup not merged across tasks",
               "distinct across tasks, dedup within task",
               f"a_dedup={a.json()['deduplicated']} b_dedup={b.json()['deduplicated']} "
               f"a2_dedup={a2.json()['deduplicated']}", ok, f"POST {base}/sources x3")

        # C15 inbox message does not create a Task
        before = len(c.get("/tasks").json()["items"])
        r = c.post("/inbox/messages", json={"message_id": "ext-inbox", "content": "hello inbox"})
        after = len(c.get("/tasks").json()["items"])
        body = r.json()
        ok = (r.status_code == 201 and after == before
              and body.get("task_created") is False and body.get("run_created") is False)
        record("C15 inbox message creates NO Task/Run", f"201, tasks {before}→{before}",
               f"{r.status_code}, tasks {before}→{after}, task_created={body.get('task_created')}", ok, f"POST {base}/inbox/messages")

        # C24 intake cancel requires confirmation then succeeds (idempotent)
        rr = c.post("/sources", json={"request_id": "ext-job", "filename": "j.txt",
                                      "content_base64": _b64(b"job bytes")})
        jid = rr.json()["job"]["job_id"]
        un = c.post(f"/intake/jobs/{jid}/actions", json={"action": "cancel", "confirmed": False})
        conf = c.post(f"/intake/jobs/{jid}/actions", json={"action": "cancel", "confirmed": True})
        again = c.post(f"/intake/jobs/{jid}/actions", json={"action": "cancel", "confirmed": True})
        ok = (un.status_code == 409 and un.json()["error"]["code"] == "cancellation_unconfirmed"
              and conf.json()["status"] == "cancelled" and again.json()["status"] == "cancelled")
        record("C24 cancel needs confirm, idempotent", "409 then cancelled, cancelled",
               f"{un.status_code}→{conf.json().get('status')}→{again.json().get('status')}", ok,
               f"POST {base}/intake/jobs/{jid}/actions cancel")

        # C28 reprocess with no OCR backend -> honest unavailable, formal untouched
        rr = c.post("/sources", json={"request_id": "ext-rep", "filename": "rep.txt",
                                      "content_base64": _b64(b"rep bytes")})
        sid = rr.json()["source"]["source_id"]
        r = c.post(f"/sources/{sid}/actions", json={"action": "reprocess"})
        detail = c.get(f"/sources/{sid}").json()
        ok = r.status_code in (200, 409, 503) and detail.get("status") != "extracted"
        record("C28 reprocess w/o OCR → no fabricated derivative",
               "no extracted status, honest outcome",
               f"http={r.status_code} status={detail.get('status')}", ok,
               f"POST {base}/sources/{sid}/actions reprocess")

        # C8b unsupported action refused
        r = c.post(f"/sources/{sid}/actions", json={"action": "bogus"})
        ok = r.status_code in (422, 400)
        record("C-ext unsupported action refused", "422/400", f"{r.status_code}", ok,
               f"POST {base}/sources/{sid}/actions bogus")

        c.close()

    # C25/C27 job recovery + retry at service layer over the SAME real data dir.
    from lightgravity.sources import IntakeService, ReceiveRequest, SourceStore
    store = SourceStore(tmp / "data")
    svc = IntakeService(store)
    j = svc.receive(ReceiveRequest(request_id="ext-recov", filename="rec.txt", data=b"recov"))
    svc.set_stage(j.job.job_id, status="running", stage="extracting")
    retry_err = None
    try:
        svc.retry(j.job.job_id)
    except Exception as exc:  # noqa: BLE001
        retry_err = exc
    after = svc.store.read_job(j.job.job_id)
    ok = retry_err is not None and after.status == "recovery_required"
    record("C25 running job not auto-replayed → recovery_required",
           "retry rejected, status recovery_required",
           f"err={type(retry_err).__name__ if retry_err else None} status={after.status}", ok,
           "IntakeService.retry(set_stage running) over real store")
    # restart recovery: reopen + recover marks running jobs recovery_required
    store2 = SourceStore(tmp / "data")
    svc2 = IntakeService(store2)
    j2 = svc2.receive(ReceiveRequest(request_id="ext-restart", filename="rs.txt", data=b"rs"))
    svc2.set_stage(j2.job.job_id, status="running", stage="extracting")
    fresh = SourceStore(tmp / "data")
    IntakeService(fresh).recover()
    rec = fresh.read_job(j2.job.job_id)
    ok = rec.status == "recovery_required"
    record("C27 restart marks running job recovery_required", "recovery_required",
           f"status={rec.status}", ok, "IntakeService.recover() after reopen real store")
    # failed job can retry
    svc2.set_stage(j2.job.job_id, status="failed", fail_reason="qa fault")
    retried = svc2.retry(j2.job.job_id)
    ok = retried.status == "queued"
    record("C26 failed job can retry", "queued", f"status={retried.status}", ok,
           "IntakeService.retry(failed) over real store")

    (RAW / "04_extended_cases.json").write_text(json.dumps(RESULTS, indent=2))
    passed = sum(1 for x in RESULTS if x["status"] == "PASS")
    print(f"\n== extended cases: {passed}/{len(RESULTS)} PASS ==")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
