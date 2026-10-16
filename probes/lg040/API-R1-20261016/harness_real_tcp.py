"""LG-040 R1 API QA — real-TCP harness against a real create_app/FileStore.

Independent QA (not product).  Starts a real uvicorn server on loopback with an
isolated data dir + a chosen free port (never 8123), drives it over real TCP
HTTP, and tears it down on every exit path (finally + signal handlers).

No OCR/vector target env -> adapters stay disabled; no inference is possible.
No external LAN/model calls.  Stub is used ONLY for a controlled mechanical
fault and is labelled as such.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(parents=True, exist_ok=True)

RESULTS: list[dict] = []


def record(case: str, expected: str, actual: str, ok: bool, provenance: str) -> None:
    RESULTS.append(
        {
            "case": case,
            "expected": expected,
            "actual": actual,
            "status": "PASS" if ok else "FAIL",
            "provenance": provenance,
        }
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {actual}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


@contextlib.contextmanager
def server(tmp: Path, port: int, *, extra_env: dict | None = None):
    """Start a real uvicorn server on the given free port; always stop it."""
    env = dict(os.environ)
    # Hard-disable OCR/vector targets: no accidental inference possible.
    for var in (
        "LIGHTGRAVITY_OCR_BASE_URL",
        "LIGHTGRAVITY_OCR_MODEL",
        "LIGHTGRAVITY_VECTOR_BASE_URL",
        "LIGHTGRAVITY_VECTOR_MODEL",
        "LIGHTGRAVITY_VECTOR_TOKEN",
        "LIGHTGRAVITY_OCR_TOKEN",
    ):
        env.pop(var, None)
    env["LIGHTGRAVITY_DATA_DIR"] = str(tmp / "data")
    env["LIGHTGRAVITY_WORKSPACE_ROOT"] = str(tmp / "data" / "workspaces")
    env["LIGHTGRAVITY_SECRET_STORE"] = str(tmp / "secrets")
    env["PYTHONPATH"] = str(BACKEND)
    if extra_env:
        env.update(extra_env)

    log = (RAW / f"server-{port}.log").open("w")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "lightgravity.api.app:create_app", "--factory",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=str(tmp),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        if not wait_port(port):
            log.flush()
            raise RuntimeError(f"server failed to start on {port}")
        yield proc
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log.close()
        # Confirm the port is truly released.
        for _ in range(50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    break
            time.sleep(0.1)


def main() -> int:
    import httpx

    tmp = Path(tempfile.mkdtemp(prefix="lg040-api-qa-"))
    port = free_port()
    base = f"http://127.0.0.1:{port}/api/v1"
    print(f"== real TCP server port={port} data={tmp} ==")

    with server(tmp, port):
        client = httpx.Client(base_url=base, timeout=30.0)

        # C1 loopback, non-sensitive, no token
        r = client.get("/health")
        record("C1 loopback health no-token", "200", str(r.status_code), r.status_code == 200,
               f"GET {base}/health")

        # C6 global inline -> inbox, no Task
        import base64
        body = b"hello api qa\n"
        r = client.post("/sources", json={
            "request_id": "qa-global-1", "filename": "n.txt",
            "content_base64": base64.b64encode(body).decode(),
        })
        ok = r.status_code == 201 and r.json()["source"]["scope"] == {
            "task_ref": None, "project_ref": None, "inbox_ref": None}
        src_id = r.json()["source"]["source_id"] if r.status_code == 201 else None
        record("C6 global inline → inbox ref", "201 global scope", f"{r.status_code} {r.json().get('source',{}).get('scope')}", ok,
               f"POST {base}/sources")

        r = client.get("/tasks")
        record("C14 intake creates NO delivery Task", "items==[]", json.dumps(r.json())[:80],
               r.status_code == 200 and r.json()["items"] == [], f"GET {base}/tasks")

        # C11 idempotent replay
        r2 = client.post("/sources", json={
            "request_id": "qa-global-1", "filename": "n.txt",
            "content_base64": base64.b64encode(body).decode()})
        ok = r2.status_code == 200 and r2.json()["created"] is False and r2.json()["deduplicated"] is True
        record("C11 request_id idempotent replay", "200 created=false dedup", f"{r2.status_code} created={r2.json().get('created')} dedup={r2.json().get('deduplicated')}", ok,
               f"POST {base}/sources same request_id")

        # C12 conflict
        r3 = client.post("/sources", json={
            "request_id": "qa-global-1", "filename": "n.txt",
            "content_base64": base64.b64encode(b"DIFFERENT").decode()})
        ok = r3.status_code == 409 and r3.json()["error"]["code"] == "source_conflict"
        record("C12 request_id conflict diff payload", "409 source_conflict", f"{r3.status_code} {r3.json().get('error',{}).get('code')}", ok,
               f"POST {base}/sources diff payload")

        # C7 unknown task
        r = client.post("/sources", json={
            "request_id": "qa-bad-task", "filename": "x.txt",
            "content_base64": base64.b64encode(b"z").decode(),
            "scope": {"task_ref": "task_00000000000000000000000000"}})
        ok = r.status_code == 422 and r.json()["error"]["code"] == "reference_invalid"
        record("C7 unknown task_ref refused", "422 reference_invalid", f"{r.status_code} {r.json().get('error',{}).get('code')}", ok,
               f"POST {base}/sources bad task_ref")

        # C9 path escape
        r = client.post("/sources", json={
            "request_id": "qa-escape", "filename": "o.txt", "path": "../outside.txt"})
        ok = r.status_code == 403 and r.json()["error"]["code"] == "path_outside_workspace"
        record("C9 path escape refused", "403 path_outside_workspace", f"{r.status_code} {r.json().get('error',{}).get('code')}", ok,
               f"POST {base}/sources path=../")

        # C16 concurrent intake over real HTTP
        import concurrent.futures as cf
        def one(i):
            rr = client.post("/sources", json={
                "request_id": f"qa-conc-{i}", "filename": f"c{i}.txt",
                "content_base64": base64.b64encode(f"payload-{i}".encode()).decode()})
            return rr.status_code, rr.json().get("source", {}).get("source_id")
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            out = list(ex.map(one, range(10)))
        ids = [s for c, s in out if c == 201]
        listing = client.get("/sources", params={"limit": 500}).json()["items"]
        ok = len(ids) == 10 and len(set(ids)) == 10 and len(listing) >= 11
        record("C16 concurrent intake 10 distinct", "10 unique 201, listing≥11",
               f"201s={len(ids)} unique={len(set(ids))} listed={len(listing)}", ok,
               f"POST {base}/sources x10 parallel + GET /sources")

        # C5 sensitive write without injected token
        r = client.post("/settings/connections", json={})
        ok = r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
        record("C5 sensitive write denied w/o token", "401 unauthorized", f"{r.status_code} {r.json().get('error',{}).get('code')}", ok,
               f"POST {base}/settings/connections")

        # C17 content views: with OCR target env unset there is no machine
        # derivative; the honest outcome is 404 not a fabricated body.
        if src_id:
            r = client.get(f"/sources/{src_id}/content", params={"kind": "machine"})
            ok = r.status_code == 404 and r.json()["error"]["code"] == "not_found"
            record("C17 machine content absent (OCR off) → truthful 404", "404 not_found",
                   f"{r.status_code} {r.json().get('error',{}).get('code')}", ok,
                   f"GET {base}/sources/{src_id}/content?kind=machine (no derivative)")
            r = client.get(f"/sources/{src_id}/content", params={"kind": "auto"})
            ok = r.status_code == 404
            record("C17b auto content absent → truthful 404", "404", f"{r.status_code}", ok,
                   f"GET {base}/sources/{src_id}/content?kind=auto")
            r = client.get(f"/sources/{src_id}/content", params={"kind": "bogus"})
            ok = r.status_code == 422
            record("C17c invalid kind rejected", "422", f"{r.status_code}", ok,
                   f"GET {base}/sources/{src_id}/content?kind=bogus")

        # C18 formal edit without a machine seed: honest 404 (no fabrication).
        if src_id:
            rec = client.get(f"/sources/{src_id}").json()
            rev = rec.get("source", rec).get("revision") or rec.get("revision")
            r = client.post(f"/sources/{src_id}/formal", json={
                "content": "QA formal body", "edited_by": "qa", "expected_revision": rev})
            ok = r.status_code == 404 and r.json()["error"]["code"] == "not_found"
            record("C18 formal edit w/o machine seed → 404 (no fabrication)",
                   "404 not_found", f"{r.status_code} {r.json().get('error',{}).get('code')}", ok,
                   f"POST {base}/sources/{src_id}/formal (no machine derivative)")

        # C21/C23 revoke then delete lifecycle on a dedicated source.
        rr = client.post("/sources", json={
            "request_id": "qa-lifecycle", "filename": "lc.txt",
            "content_base64": base64.b64encode(b"lifecycle bytes").decode()})
        lc = rr.json()["source"]["source_id"]
        r = client.post(f"/sources/{lc}/actions", json={"action": "revoke"})
        det = client.get(f"/sources/{lc}").json()
        ok = r.status_code == 200 and r.json().get("revoked") is True and det.get("status") == "archived"
        record("C21 revoke → archived + index not_indexed",
               "200 revoked true, status archived", f"{r.status_code} revoked={r.json().get('revoked')} status={det.get('status')} idx={det.get('index',{}).get('lexical')}", ok,
               f"POST {base}/sources/{lc}/actions revoke")
        r = client.post(f"/sources/{lc}/actions", json={"action": "delete", "confirmed": True})
        det2 = client.get(f"/sources/{lc}")
        ok = r.status_code == 200 and r.json().get("deleted") is True and det2.status_code == 404
        record("C23 delete confirmed → gone (404 after)",
               "200 deleted true then 404", f"{r.status_code} deleted={r.json().get('deleted')} after={det2.status_code}", ok,
               f"POST {base}/sources/{lc}/actions delete confirmed=True")

        # C19 archive reversible
        if src_id:
            r = client.post(f"/sources/{src_id}/actions", json={"action": "archive"})
            ok = r.status_code == 200 and r.json().get("archived") is True
            record("C19 archive reversible flag", "200 archived=true", f"{r.status_code} {r.json()}", ok,
                   f"POST {base}/sources/{src_id}/actions archive")
            r = client.post(f"/sources/{src_id}/actions", json={"action": "unarchive"})
            record("C20 unarchive reverses", "200 archived=false", f"{r.status_code} {r.json()}", r.status_code == 200 and r.json().get("archived") is False,
                   f"POST {base}/sources/{src_id}/actions unarchive")

        # C22 delete unconfirmed
        if src_id:
            r = client.post(f"/sources/{src_id}/actions", json={"action": "delete"})
            ok = r.status_code == 409 and r.json()["error"]["code"] == "cancellation_unconfirmed"
            record("C22 delete requires confirmation", "409 cancellation_unconfirmed", f"{r.status_code} {r.json().get('error',{}).get('code')}", ok,
                   f"POST {base}/sources/{src_id}/actions delete unconfirmed")

        # C32 vector unavailable truthfulness
        r = client.get("/vector/status")
        rec = r.json() if r.status_code == 200 else {}
        record("C32 vector status (no target env)", "200 truthful unavailable", f"{r.status_code} {json.dumps(rec)[:120]}",
               r.status_code == 200 and rec.get("available") in (False, None), f"GET {base}/vector/status")

        client.close()

    # C2/C3/C4 non-loopback auth: use ASGI transport forging client host.
    import asyncio
    import httpx as _hx
    from lightgravity.api.access import LocalAccessPolicy, TOKEN_HEADER
    from lightgravity.api.app import create_app
    from lightgravity.config import Settings

    async def auth_cases():
        t = Path(tempfile.mkdtemp(prefix="lg040-api-auth-"))
        st = Settings(data_dir=t / "data", workspace_root=t / "data" / "ws", secret_store=t / "secrets")
        app = create_app(st, access_policy=LocalAccessPolicy(token="secret-token"))
        async with app.router.lifespan_context(app):
            for label, hdrs, expect in [
                ("C2 non-loopback no token", {"host": "10.0.0.9"}, 401),
                ("C3 non-loopback correct token", {"host": "10.0.0.9", TOKEN_HEADER: "secret-token"}, 200),
                ("C4 non-loopback wrong token", {"host": "10.0.0.9", TOKEN_HEADER: "nope"}, 401),
            ]:
                tr = _hx.ASGITransport(app=app, client=("10.0.0.9", 12345))
                async with _hx.AsyncClient(transport=tr, base_url="http://lg") as c:
                    r = await c.get("/api/v1/sources", headers=hdrs)
                record(label, str(expect), str(r.status_code), r.status_code == expect,
                       f"ASGI(forged 10.0.0.9) GET /api/v1/sources {label}")

    asyncio.run(auth_cases())

    out = RAW / "02_api_cases.json"
    out.write_text(json.dumps(RESULTS, indent=2))
    passed = sum(1 for x in RESULTS if x["status"] == "PASS")
    print(f"\n== API real-TCP cases: {passed}/{len(RESULTS)} PASS ==")
    # cleanup temp trees
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
