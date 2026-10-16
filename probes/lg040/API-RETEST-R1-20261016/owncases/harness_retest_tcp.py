"""LG-040 API-RETEST-R1-20261016 — independent real-TCP retest harness.

Independent QA (distinct from the revoke-fix implementer and the original API QA
owner).  Starts a real uvicorn app (real ``create_app`` + real ``FileStore``) in
a subprocess on a free loopback port (never 8123), drives it over **real TCP
HTTP**, and always stops the server in ``finally`` with a port-release assertion.

Verifies the integrated candidate (product tree ``77685f0c...`` == fix
``266945c``) for the repaired MAJOR:

  BEFORE revoke  -> all content/download kinds 200 and serve the marker bytes;
  revoke         -> 200 archived/revoked;
  AFTER revoke   -> all content/download kinds 404 not_found revoked=true and
                    **no marker byte served**;
  metadata       -> GET /sources/{id} still 200 status=archived (diagnosable);
  raw files      -> original/formal/machine preserved on disk (byte-for-byte);
  search         -> hits [] after revoke;
  idempotency    -> repeated revoke 200 unchanged;
  no resurrection-> reprocess / formal refused;
  reversible     -> archive -> preview/search/download 200; unarchive restores;
  scopes         -> global/task/normal-user listing + search preserved;
  fail-closed    -> forged/stale hit + cross-task query scope never leak.

Isolation: ``LIGHTGRAVITY_OCR_*`` / ``LIGHTGRAVITY_VECTOR_*`` unset; zero
external/LAN/model calls; zero retries.  Machine derivative is a mechanical
scripted seed (no model) and is not quality evidence.

Run:  PYTHONPATH=<worktree>/backend python harness_retest_tcp.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

for _name in (
    "LIGHTGRAVITY_OCR_BASE_URL",
    "LIGHTGRAVITY_OCR_MODEL",
    "LIGHTGRAVITY_OCR_TOKEN",
    "LIGHTGRAVITY_VECTOR_BASE_URL",
    "LIGHTGRAVITY_VECTOR_MODEL",
    "LIGHTGRAVITY_VECTOR_TOKEN",
):
    os.environ.pop(_name, None)

API = "/api/v1"
MARKER = "RETEST-MARKER-c4f19a"
RESULTS: list[dict] = []
SERVERS: list["Server"] = []


def record(case: str, expected, actual, ok: bool, notes: str = "") -> None:
    RESULTS.append(
        {
            "case": case,
            "expected": expected,
            "actual": actual,
            "result": "PASS" if ok else "FAIL",
            "notes": notes,
        }
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {actual}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def http(method: str, base: str, path: str, *, params=None, body=None):
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = {"Cache-Control": "no-store"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    def _parse(status: int, data: bytes):
        try:
            return status, json.loads(data.decode() or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, {"raw_bytes_sha256": sha(data), "raw_len": len(data)}

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _parse(resp.status, resp.read())
    except urllib.error.HTTPError as exc:
        return _parse(exc.code, exc.read())


def raw_get(base: str, path: str):
    req = urllib.request.Request(base + path, method="GET", headers={"Cache-Control": "no-store"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class Server:
    """Real uvicorn subprocess exposing a real app (real FileStore)."""

    def __init__(self, data_dir: Path, port: int):
        self.data_dir = data_dir
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.base = f"http://127.0.0.1:{port}"

    def start(self) -> None:
        launcher = self.data_dir / "_launch_retest.py"
        launcher.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(BACKEND)!r})\n"
            "import uvicorn\n"
            "from pathlib import Path\n"
            "from lightgravity.config import Settings\n"
            "from lightgravity.api.app import create_app\n"
            "from lightgravity.api.access import LocalAccessPolicy\n"
            "from lightgravity.contracts import API_PREFIX\n"
            "from lightgravity.api.sources import build_sources_router\n"
            "from lightgravity.api.search import build_search_router\n"
            "from lightgravity.api.vector import build_vector_router\n"
            f"s = Settings(data_dir=Path({str(self.data_dir / 'data')!r}), "
            f"workspace_root=Path({str(self.data_dir / 'data' / 'workspaces')!r}), "
            f"secret_store=Path({str(self.data_dir / 'secrets')!r}))\n"
            "app = create_app(s, access_policy=LocalAccessPolicy("
            "allow_sensitive_without_token=True))\n"
            "app.include_router(build_sources_router(), prefix=API_PREFIX)\n"
            "app.include_router(build_search_router(), prefix=API_PREFIX)\n"
            "app.include_router(build_vector_router(), prefix=API_PREFIX)\n"
            f"uvicorn.run(app, host='127.0.0.1', port={self.port}, log_level='warning')\n",
            encoding="utf-8",
        )
        self.proc = subprocess.Popen(
            [sys.executable, str(launcher)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                status, _ = http("GET", self.base, API + "/health")
                if status == 200:
                    return
            except Exception:
                time.sleep(0.25)
        raise RuntimeError("server did not become healthy")

    def stop(self) -> bool:
        if self.proc is None:
            return True
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
        self.proc = None
        released = False
        for _ in range(50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                if s.connect_ex(("127.0.0.1", self.port)) != 0:
                    released = True
                    break
            time.sleep(0.1)
        return released


def create_task(base: str, title: str) -> str:
    status, payload = http(
        "POST",
        base,
        API + "/tasks",
        body={
            "request_id": f"retest-{title}",
            "title": title,
            "objective": "hold sources",
            "acceptance_criteria": ["n/a"],
        },
    )
    assert status in (200, 201), payload
    return payload["task_id"]


def receive(base: str, request_id: str, body: bytes, task_ref: str | None = None) -> str:
    scope = {"task_ref": task_ref} if task_ref else {}
    status, payload = http(
        "POST",
        base,
        API + "/sources",
        body={
            "request_id": request_id,
            "filename": "doc.txt",
            "content_base64": b64(body),
            "scope": scope,
        },
    )
    assert status == 201, payload
    return payload["source"]["source_id"]


def seed_formal(base: str, data_dir: Path, source_id: str, content: str) -> None:
    from lightgravity.sources.content import ContentStore, MachineDraft, PageText
    from lightgravity.sources.store import SourceStore

    store = SourceStore(data_dir / "data")
    rec = store.read_source(source_id)
    cs = ContentStore(source_root=store.source_dir(source_id))
    cs.write_machine(
        MachineDraft(
            source_version=rec.source_version,
            filename="doc.txt",
            model="scripted",
            pages=[
                PageText(
                    page=1,
                    text="machine seed placeholder RETEST-MARKER-c4f19a",
                    input_sha256="0" * 64,
                    model="scripted",
                )
            ],
            extractor="scripted",
            status="succeeded",
        )
    )
    status, payload = http(
        "POST",
        base,
        API + f"/sources/{source_id}/formal",
        body={"content": content, "edited_by": "retester"},
    )
    assert status == 200, payload
    reindex(data_dir, source_id)


def reindex(data_dir: Path, source_id: str) -> None:
    from lightgravity.sources.lexical import LexicalSearchService
    from lightgravity.sources.store import SourceStore

    LexicalSearchService(SourceStore(data_dir / "data")).index_source(source_id)


def lexical_db(data_dir: Path) -> Path:
    return data_dir / "data" / "sources-index" / "lexical" / "lexical.sqlite3"


def forge_candidate(data_dir: Path, source_id: str, *, version: int, body: str) -> None:
    conn = sqlite3.connect(str(lexical_db(data_dir)))
    conn.execute(
        "INSERT INTO docs(source_id, source_version, content_hash, basis, title, body, "
        "tokens, locators, lexical_hash) VALUES (?,?,?,?,?,?,?,?,?)",
        (source_id, version, "forged", "formal", "forged", body, "forged", "[]", "forged"),
    )
    conn.commit()
    conn.close()


def _read_all_kinds(base: str, sid: str, raw: bool = False) -> dict:
    """Read all 6 preview/download kinds over real TCP.

    Uses raw bytes (``raw_get``) so a served body is byte-checked for the
    marker even on non-JSON content responses.  ``raw=True`` returns only
    status/serves_marker/sha; otherwise the error code/revoked fields are
    parsed from the JSON error envelope (or captured when the body is bytes).
    """
    out: dict = {}
    for kind in ("auto", "formal", "machine"):
        st, body = raw_get(base, API + f"/sources/{sid}/content?kind={kind}")
        entry = {"status": st, "serves_marker": MARKER.encode() in body, "sha256": sha(body)}
        if not raw:
            try:
                payload = json.loads(body.decode())
                err = payload.get("error", {})
                entry["code"] = err.get("code")
                entry["revoked"] = err.get("details", {}).get("revoked")
            except (UnicodeDecodeError, json.JSONDecodeError):
                entry["code"] = None
                entry["revoked"] = None
        out[f"content_{kind}"] = entry
    for kind in ("original", "formal", "machine"):
        st, body = raw_get(base, API + f"/sources/{sid}/download?kind={kind}")
        entry = {"status": st, "serves_marker": MARKER.encode() in body, "sha256": sha(body)}
        if not raw:
            try:
                payload = json.loads(body.decode())
                err = payload.get("error", {})
                entry["code"] = err.get("code")
                entry["revoked"] = err.get("details", {}).get("revoked")
            except (UnicodeDecodeError, json.JSONDecodeError):
                entry["code"] = None
                entry["revoked"] = None
        out[f"download_{kind}"] = entry
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lg040-api-retest-"))
    port = free_port()
    assert port != 8123, "must not use 8123"
    server = Server(tmp, port)
    SERVERS.append(server)
    server.start()
    base = server.base
    data_dir = tmp
    try:
        # ---------- fixture: task-scoped source + global + archive ----------
        task_a = create_task(base, "retest-a")
        task_b = create_task(base, "retest-b")
        src_b = receive(base, "retest-b-src", f"{MARKER} beta original".encode(), task_ref=task_b)
        src_a = receive(base, "retest-a-src", f"{MARKER} alpha original".encode(), task_ref=task_a)
        src_g = receive(base, "retest-g-src", f"{MARKER} global original".encode())
        seed_formal(base, data_dir, src_a, f"{MARKER} ALPHA FORMAL")
        seed_formal(base, data_dir, src_b, f"{MARKER} BETA FORMAL")
        seed_formal(base, data_dir, src_g, f"{MARKER} GLOBAL FORMAL")

        # ---------- BEFORE: all content/download kinds 200 + marker --------
        before = _read_all_kinds(base, src_b, raw=True)
        ok = all(v["status"] == 200 and v["serves_marker"] for v in before.values())
        record("R1 BEFORE revoke content/download all kinds 200 + marker",
               "all 200 and serve marker", before, ok)

        before_hashes = {k: v["sha256"] for k, v in before.items()}

        # ---------- revoke --------------------------------------------------
        st, revoke = http("POST", base, API + f"/sources/{src_b}/actions", body={"action": "revoke"})
        ok = st == 200 and revoke.get("status") == "archived" and revoke.get("revoked") is True
        record("R2 revoke 200 status=archived revoked=true",
               "200 archived revoked", {"status": st, "body": revoke}, ok)

        # ---------- metadata diagnosable -----------------------------------
        st, detail = http("GET", base, API + f"/sources/{src_b}")
        ok = st == 200 and detail.get("status") == "archived"
        record("R3 metadata remains diagnosable (status archived)",
               "200 status archived", {"status": st, "status_field": detail.get("status")}, ok)

        # ---------- search hits [] ------------------------------------------
        st, srch = http("GET", base, API + "/search", params={"q": MARKER, "task_ref": task_b})
        ok = st == 200 and srch.get("hits") == []
        record("R4 search hits [] after revoke",
               "200 hits==[]", {"status": st, "hits": srch.get("hits")}, ok)

        # ---------- AFTER: all kinds 404 not_found revoked, no bytes -------
        after = _read_all_kinds(base, src_b)
        ok = all(
            v["status"] == 404 and v["code"] == "not_found" and v["revoked"] is True and not v["serves_marker"]
            for v in after.values()
        )
        record("R5 AFTER revoke all content/download kinds 404 not_found revoked + no bytes",
               "all 404 not_found revoked=true, no marker", after, ok)

        # machine-gate: raw TCP bytes contain no marker
        after_raw = _read_all_kinds(base, src_b, raw=True)
        ok = all(v["status"] == 404 and not v["serves_marker"] for v in after_raw.values())
        record("R5b raw TCP body bytes: no marker served for any kind",
               "all 404 and no marker", after_raw, ok)

        # ---------- raw files preserved on disk ----------------------------
        from lightgravity.sources.store import SourceStore

        store = SourceStore(data_dir / "data")
        sdir = store.source_dir(src_b)
        disk = {}
        for rel in ("original", "derivative", "formal"):
            d = sdir / rel
            files = sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []
            disk[rel] = files

        def any_file_matches(d: Path, target_sha: str) -> bool:
            return d.is_dir() and any(p.is_file() and sha(p.read_bytes()) == target_sha for p in d.iterdir())

        orig_bytes_ok = any_file_matches(sdir / "original", before_hashes["download_original"])
        machine_bytes_ok = any_file_matches(sdir / "derivative", before_hashes["download_machine"])
        formal_bytes_ok = any_file_matches(sdir / "formal", before_hashes["download_formal"])
        ok = (
            orig_bytes_ok
            and machine_bytes_ok
            and formal_bytes_ok
            and all(len(v) > 0 for v in disk.values())
        )
        record("R6 raw original/formal/machine preserved on disk (bytes unchanged)",
               "original+derivative+formal files present and byte-identical to pre-revoke served bytes",
               {"disk": disk, "original_matches_pre": orig_bytes_ok,
                "machine_matches_pre": machine_bytes_ok, "formal_matches_pre": formal_bytes_ok}, ok)

        # ---------- repeated revoke idempotent -----------------------------
        st, again = http("POST", base, API + f"/sources/{src_b}/actions", body={"action": "revoke"})
        st2, detail2 = http("GET", base, API + f"/sources/{src_b}")
        ok = st == 200 and again.get("revoked") is True and detail2.get("status") == "archived"
        record("R7 repeated revoke idempotent",
               "200 revoked, status still archived", {"status": st, "body": again, "detail": detail2.get("status")}, ok)

        # ---------- no resurrection ----------------------------------------
        st_rep, rep = http("POST", base, API + f"/sources/{src_b}/actions", body={"action": "reprocess"})
        st_for, form = http("POST", base, API + f"/sources/{src_b}/formal", body={"content": f"{MARKER} hack", "edited_by": "x"})
        st_after, _ = http("GET", base, API + f"/sources/{src_b}")
        ck = _read_all_kinds(base, src_b)
        ok = (
            st_rep == 404
            and rep.get("error", {}).get("code") == "not_found"
            and st_for == 404
            and form.get("error", {}).get("code") == "not_found"
            and st_after == 200
            and all(v["status"] == 404 for v in ck.values())
        )
        record("R8 reprocess/formal cannot resurrect",
               "both 404 not_found, status unchanged, views still 404",
               {"reprocess": st_rep, "formal": st_for, "status": st_after, "views": {k: v["status"] for k, v in ck.items()}}, ok)

        # ---------- reversible archive/unarchive ---------------------------
        src_arc = receive(base, "retest-arc-src", f"{MARKER} arc original".encode())
        seed_formal(base, data_dir, src_arc, f"{MARKER} ARC FORMAL")
        arc = http("POST", base, API + f"/sources/{src_arc}/actions", body={"action": "archive"})
        arc_c = raw_get(base, API + f"/sources/{src_arc}/content")
        arc_d = raw_get(base, API + f"/sources/{src_arc}/download?kind=original")
        arc_s = http("GET", base, API + "/search", params={"q": MARKER, "include_global": "true"})
        arc_ids = {h["source_id"] for h in arc_s[1].get("hits", [])}
        ok = (
            arc[0] == 200
            and arc_c[0] == 200
            and arc_d[0] == 200
            and src_arc in arc_ids
        )
        record("R9 archive keeps preview/search/download 200",
               "archive 200; content/download 200; hit present",
               {"archive": arc[0], "content": arc_c[0], "download": arc_d[0], "hit": src_arc in arc_ids}, ok)

        unarc = http("POST", base, API + f"/sources/{src_arc}/actions", body={"action": "unarchive"})
        st_u, det_u = http("GET", base, API + f"/sources/{src_arc}")
        un_c = raw_get(base, API + f"/sources/{src_arc}/content")
        ok = unarc[0] == 200 and det_u.get("status") != "archived" and un_c[0] == 200
        record("R10 unarchive restores openable (<-> archive reversible)",
               "unarchive 200; status != archived; content 200",
               {"unarchive": unarc[0], "status": det_u.get("status"), "content": un_c[0]}, ok)

        # ---------- normal user / global / task scope preserved ------------
        # global listing includes all; task-filtered search only admits its task
        st_list, listing = http("GET", base, API + "/sources", params={"limit": 500})
        ids = {s["source_id"] for s in listing.get("items", [])}
        st_sa, sa = http("GET", base, API + "/search", params={"q": MARKER, "task_ref": task_a})
        sa_ids = {h["source_id"] for h in sa.get("hits", [])}
        st_sb, sb = http("GET", base, API + "/search", params={"q": MARKER, "task_ref": task_b})
        sb_ids = {h["source_id"] for h in sb.get("hits", [])}
        ok = (
            st_list == 200
            and {src_a, src_g, src_arc}.issubset(ids)
            and src_a in sa_ids
            and src_b not in sa_ids
            and src_g not in sa_ids
            and src_b not in sb_ids  # revoked
        )
        record("R11 global/task scopes preserved (task filter narrows, no cross-task leak)",
               "global listing has live sources; task_a sees a not b; task_b excludes revoked",
               {"task_a": sorted(sa_ids), "task_b": sorted(sb_ids), "listing_has_a_g_arc": {src_a, src_g, src_arc}.issubset(ids)}, ok)

        # ---------- forged/stale fail-closed -------------------------------
        forge_candidate(data_dir, src_a, version=999, body="FORGED-RETEST-LEAK")
        st_f, f = http("GET", base, API + "/search", params={"q": "FORGED-RETEST-LEAK", "task_ref": task_a})
        forged_ids = {h["source_id"] for h in f.get("hits", [])}
        stale = f.get("stale", [])
        ok = (
            st_f == 200
            and forged_ids == set()
            and any(s.get("source_id") == src_a and s.get("reason") == "source_stale" for s in stale)
        )
        record("R12 forged/stale hit fail-closed (never returned as authority)",
               "no forged hit; source_stale reported",
               {"status": st_f, "forged_hits": sorted(forged_ids), "stale": stale}, ok)
        reindex(data_dir, src_a)

        # ---------- query scope fail-closed (unknown task) -----------------
        st_u2, u2 = http("GET", base, API + "/search", params={"q": MARKER, "task_ref": "task_00000000000000000000000000"})
        ok = st_u2 == 200 and u2.get("hits") == []
        record("R13 unknown task_ref query yields no hits (scope narrows, no grant)",
               "200 hits==[]", {"status": st_u2, "hits": u2.get("hits")}, ok)

        # ---------- missing source still not_found -------------------------
        st_m, m = http("GET", base, API + "/sources/source_01MISSINGMISSINGMISSING/content")
        ok = st_m == 404 and m.get("error", {}).get("code") == "not_found"
        record("R14 missing source content 404 not_found",
               "404 not_found", {"status": st_m, "code": m.get("error", {}).get("code")}, ok)

    finally:
        released = server.stop()
        record("R15 cleanup: server stopped / port released", "port released", {"port": port, "released": released}, released)

    out = Path(__file__).resolve().parents[1] / "raw"
    out.mkdir(parents=True, exist_ok=True)
    failures = [r for r in RESULTS if r["result"] == "FAIL"]
    (out / "retest_tcp_cases.json").write_text(
        json.dumps({"candidate_tree": "77685f0c64ba0403f6ba93823e7162d37be8e7bd",
                    "results": RESULTS, "failures": len(failures)}, indent=2) + "\n"
    )
    print(f"\n== retest real-TCP: {len(RESULTS) - len(failures)}/{len(RESULTS)} PASS ==")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
