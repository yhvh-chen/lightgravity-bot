"""LG-040 R1-20261016 — API QA ACL addendum harness (independent reproduction).

Scope: closes original-REPORT §6 gap "cross-Task permission ... beyond the
task_ref reference checks" with a real ``FileStore`` + real ``create_app`` +
**real uvicorn TCP** on a free loopback port (never 8123).

Key contract facts established by reading the narrow docs/08 §6.6 source/
search/vector sections and the actual runtime source authorizer
(``backend/lightgravity/sources/service.py`` ``authorize_scope``,
``sources/lexical/query.py`` ``ScopeFilter``/``authorize_and_verify``,
``sources/lexical/service.py``, ``sources/service.py::list_sources``,
``api/search.py``, ``api/vector.py``):

* The source / search / vector HTTP surface has **no worker/member principal**.
  ``ApiContext.worker_identity`` / ``ApiContext.worker_grant`` are referenced
  **only** by ``api/collaboration.py`` (discovery/claim/lease/renew/release),
  never by ``api/search.py`` / ``api/vector.py`` / ``api/sources.py``
  (verified by ``grep -c`` == 0).  Therefore a "worker/member grant source API"
  case is **not applicable** to this context; see the REPORT addendum for the
  contract evidence.  What *does* exist is a **Task-attribution filter**
  (``ScopeFilter.allows``) that only narrows result scope — it is not an
  identity authorization.
* Every candidate hit is re-read from ``SOURCE.md`` (file SoT) and re-verified
  for existence / status / version / trusted-body before returning; a forged or
  stale cache row can never be returned as authority.

All cases are in-process deterministic logic with ZERO live inference.  OCR/
vector target env vars are unset.  No product writes.
"""

from __future__ import annotations

import base64
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

# ---- hard isolation: unset every inference target -------------------------
for _name in (
    "LIGHTGRAVITY_OCR_BASE_URL",
    "LIGHTGRAVITY_OCR_MODEL",
    "LIGHTGRAVITY_VECTOR_BASE_URL",
    "LIGHTGRAVITY_VECTOR_MODEL",
    "LIGHTGRAVITY_VECTOR_TOKEN",
):
    os.environ.pop(_name, None)

API = "/api/v1"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def http(method: str, base: str, path: str, *, params=None, body=None):
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "{}"
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def raw_get(base: str, path: str):
    """Return (status, raw_body_bytes) — no JSON parsing, no HTTP cache."""
    req = urllib.request.Request(base + path, method="GET", headers={"Cache-Control": "no-store"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


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
        launcher = self.data_dir / "_launch.py"
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

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
        self.proc = None


# --------------------------------------------------------------------- helpers
def create_task(base: str, title: str) -> str:
    status, payload = http(
        "POST",
        base,
        API + "/tasks",
        body={
            "request_id": f"req-{title}",
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
    """Seed a trusted machine derivative, then a human formal edit via the API.

    This mirrors a successful extraction + human formal edit.  The machine
    derivative is written mechanically to the file SoT (no model call); the
    formal edit goes through the real endpoint.  No inference.
    """

    sys.path.insert(0, str(BACKEND))
    from lightgravity.sources.content import ContentStore, MachineDraft, PageText
    from lightgravity.sources.store import SourceStore

    store = SourceStore(data_dir / "data")
    record = store.read_source(source_id)
    content_store = ContentStore(source_root=store.source_dir(source_id))
    content_store.write_machine(
        MachineDraft(
            source_version=record.source_version,
            filename="doc.txt",
            model="scripted",
            pages=[PageText(page=1, text="machine placeholder", input_sha256="0" * 64, model="scripted")],
            extractor="scripted",
            status="succeeded",
        )
    )
    status, payload = http(
        "POST", base, API + f"/sources/{source_id}/formal",
        body={"content": content, "edited_by": "tester"},
    )
    assert status == 200, payload
    reindex(data_dir, source_id)


def reindex(data_dir: Path, source_id: str) -> None:
    sys.path.insert(0, str(BACKEND))
    from lightgravity.sources.lexical import LexicalSearchService
    from lightgravity.sources.store import SourceStore

    store = SourceStore(data_dir / "data")
    LexicalSearchService(store).index_source(source_id)


def lexical_db(data_dir: Path) -> Path:
    return data_dir / "data" / "sources-index" / "lexical" / "lexical.sqlite3"


def forge_candidate(data_dir: Path, source_id: str, *, version: int, body: str) -> None:
    """Insert a forged FTS row (wrong version) directly into the cache.

    Models a cache that disagrees with the file SoT; the query layer must
    re-read SOURCE.md and never return this as authority.
    """

    conn = sqlite3.connect(str(lexical_db(data_dir)))
    conn.execute(
        "INSERT INTO docs(source_id, source_version, content_hash, basis, title, body, "
        "tokens, locators, lexical_hash) VALUES (?,?,?,?,?,?,?,?,?)",
        (source_id, version, "forged", "formal", "forged", body, "forged", "[]", "forged"),
    )
    conn.commit()
    conn.close()


# ----------------------------------------------------------------- case runner
RESULTS: list[dict] = []


def record(case: str, expected, actual, ok: bool, notes: str = "") -> None:
    RESULTS.append(
        {"case": case, "expected": expected, "actual": actual, "result": "PASS" if ok else "FAIL", "notes": notes}
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="lg040-api-acl-"))
    port = free_port()
    assert port != 8123, "must not use 8123"
    server = Server(tmp, port)
    server.start()
    base = server.base
    data_dir = tmp
    try:
        # ---------------- fixture: 2 real Tasks + scoped sources -------------
        task_a = create_task(base, "task-a")
        task_b = create_task(base, "task-b")
        src_a = receive(base, "req-a", b"alpha secret marker A-77", task_ref=task_a)
        src_b = receive(base, "req-b", b"beta secret marker B-88", task_ref=task_b)
        src_g = receive(base, "req-g", b"global shared marker G-99")
        seed_formal(base, data_dir, src_a, "TASK A BODY marker A-77")
        seed_formal(base, data_dir, src_b, "TASK B BODY marker B-88")
        seed_formal(base, data_dir, src_g, "GLOBAL BODY marker G-99")

        # ---- ACL-1 queryTaskA must not include TaskB ------------------------
        status, payload = http("GET", base, API + "/search", params={"q": '"marker"', "task_ref": task_a})
        hits = payload.get("hits", [])
        ids = {h["source_id"] for h in hits}
        scopes = {h["scope"]["task_ref"] for h in hits}
        ok = status == 200 and src_a in ids and src_b not in ids and src_g not in ids and scopes == {task_a}
        record("ACL-1 query TaskA excludes TaskB", "only task_a source", {"status": status, "hits": sorted(ids), "scopes": sorted(scopes)}, ok)
        RESULTS[-1]["source_a"] = src_a
        RESULTS[-1]["source_b"] = src_b

        # ---- ACL-2 scoped query cannot expand to another Task --------------
        # include_global is a documented additional admission of *global*
        # material only; it must never admit the OTHER Task's material.  The
        # real requirement is that narrowing can't bypass the ACL to reach B.
        status, payload = http(
            "GET", base, API + "/search",
            params={"q": '"marker"', "task_ref": task_a, "include_global": "true"},
        )
        ids = {h["source_id"] for h in payload.get("hits", [])}
        ok = status == 200 and src_a in ids and src_b not in ids
        record(
            "ACL-2 scoped query never reaches TaskB",
            "task_a (+global admitted by include_global), never task_b",
            {"status": status, "hits": sorted(ids), "global_admitted": src_g in ids},
            ok,
            notes="include_global only admits unscoped/global material; it must not leak TaskB",
        )

        # ---- ACL-3 direct returned hit resolves source scope/version/hash/existence
        status, payload = http("GET", base, API + "/search", params={"q": '"A-77"', "task_ref": task_a})
        hit = (payload.get("hits") or [None])[0]
        detail_status, detail = http("GET", base, API + f"/sources/{src_a}")
        ok = (
            hit is not None
            and hit["source_id"] == src_a
            and hit["scope"]["task_ref"] == task_a
            and hit["source_version"] == detail.get("source_version")
            and hit["content_hash"] == detail.get("content_hash")
            and detail.get("status") not in ("archived", None)
        )
        record(
            "ACL-3 hit resolves scope/version/hash/existence",
            "hit matches file SoT",
            {"hit": hit, "detail_status": detail.get("status"), "detail_version": detail.get("source_version")},
            ok,
        )

        # ---- ACL-4 forged/stale candidate fail-closed ----------------------
        # Forge an EXTRA FTS row for src_b at a wrong version.  The forged body
        # must never be returned; the stale row must be reported, and the
        # legitimate current row (if matched) comes only from the real SoT.
        forge_candidate(data_dir, src_b, version=999, body="FORGED LEAK B-88 FORGEMARK")
        status, payload = http("GET", base, API + "/search", params={"q": '"FORGEMARK"', "task_ref": task_b})
        forged_ids = {h["source_id"] for h in payload.get("hits", [])}
        stale = payload.get("stale", [])
        ok = (
            status == 200
            and "FORGEMARK" not in json.dumps(payload.get("hits", []))
            and forged_ids == set()
            and any(s.get("source_id") == src_b and s.get("reason") == "source_stale" for s in stale)
        )
        record(
            "ACL-4 forged/stale candidate fail-closed",
            "forged body never returned; source_stale reported",
            {"status": status, "forged_hits": sorted(forged_ids), "stale": stale},
            ok,
        )
        # Restore the real cache row for the remaining cases.
        reindex(data_dir, src_b)

        # ---- ACL-5 revoke -> cached hit cannot leak ------------------------
        before_status, before = http("GET", base, API + "/search", params={"q": '"B-88"', "task_ref": task_b})
        before_ids = {h["source_id"] for h in before.get("hits", [])}

        def sha(b: bytes) -> str:
            import hashlib
            return hashlib.sha256(b).hexdigest()

        # BEFORE-revoke raw reads over real TCP (no HTTP cache): must be 200+body
        pre_c_status, pre_c = raw_get(base, API + f"/sources/{src_b}/content")
        pre_d_status, pre_d = raw_get(base, API + f"/sources/{src_b}/download")
        pre_c_served = b"B-88" in pre_c
        pre_d_served = b"B-88" in pre_d
        rev = http("POST", base, API + f"/sources/{src_b}/actions", body={"action": "revoke"})
        after_status, after = http("GET", base, API + "/search", params={"q": '"B-88"', "task_ref": task_b})
        after_ids = {h["source_id"] for h in after.get("hits", [])}
        ok = src_b in before_ids and rev[0] == 200 and src_b not in after_ids and after.get("hits") == []
        record(
            "ACL-5 revoked source: search hit cannot leak",
            "before hit, after empty",
            {"before": sorted(before_ids), "after": sorted(after_ids), "revoke": rev[0]},
            ok,
        )

        # ---- ACL-5a revoke -> content body / download must not remain served
        # docs/08 §6.6 (line 594): archive/unarchive 保留…检索与打开能力; only
        # revoke/delete 使命中失效、资料不可用.  §4.3 (line 233): revoke 使资料
        # 不可用并失效命中.  So after revoke BOTH GET content and GET download
        # must refuse the bytes.  Capture raw actual status + body sha256.
        post_c_status, post_c = raw_get(base, API + f"/sources/{src_b}/content")
        post_d_status, post_d = raw_get(base, API + f"/sources/{src_b}/download")
        content_served = b"B-88" in post_c
        download_served = b"B-88" in post_d
        refused = {404, 409, 410, 423}
        ok = (
            pre_c_status == 200
            and pre_d_status == 200
            and post_c_status in refused
            and post_d_status in refused
        )
        record(
            "ACL-5b revoke -> content/download refused (资料不可用)",
            "pre 200/200; post content+download refused (404/409/410/423)",
            {
                "before_content_status": pre_c_status,
                "before_download_status": pre_d_status,
                "before_content_serves_marker": pre_c_served,
                "before_download_serves_marker": pre_d_served,
                "after_content_status": post_c_status,
                "after_download_status": post_d_status,
                "content_body_sha256": sha(post_c),
                "download_body_sha256": sha(post_d),
                "content_serves_marker": content_served,
                "download_serves_marker": download_served,
            },
            ok,
            notes="docs/08 §6.6 L594 + §4.3 L233: revoke 使资料不可用; archive 才保留打开",
        )
        # Machine-gate assertion: an actual 200 serving revoked bytes is a
        # contract violation (this is the confirmed finding when it happens).
        record(
            "ACL-5b2 revoked bytes actually served over TCP",
            "must be false for content and download",
            {"content_served": content_served, "download_served": download_served},
            not (content_served or download_served),
            notes="expected-contract-refusal vs raw-actual-200 receipt",
        )

        # ---- ACL-5c archive retains open/search (intended, NOT a leak) -----
        src_arc = receive(base, "req-arc", b"archivable marker AR-33")
        seed_formal(base, data_dir, src_arc, "ARCHIVE BODY marker AR-33")
        arc = http("POST", base, API + f"/sources/{src_arc}/actions", body={"action": "archive"})
        arc_hits = http("GET", base, API + "/search", params={"q": '"AR-33"', "include_global": "true"})[1]
        arc_ids = {h["source_id"] for h in arc_hits.get("hits", [])}
        arc_content = http("GET", base, API + f"/sources/{src_arc}/content")[0]
        ok = arc[0] == 200 and src_arc in arc_ids and arc_content == 200
        record(
            "ACL-5c archive retains search/open (intended)",
            "archived source still searchable/openable",
            {"archive": arc[0], "search_hits": sorted(arc_ids), "content_status": arc_content},
            ok,
            notes="reversible archive must NOT behave like revoke (recorded intended)",
        )

        # ---- ACL-6 deleted source -> no cached snippet leak ----------------
        src_del = receive(base, "req-del", b"deletable marker D-11")
        seed_formal(base, data_dir, src_del, "DELETE BODY marker D-11")
        pre = http("GET", base, API + "/search", params={"q": '"D-11"', "include_global": "true"})[1]
        pre_ids = {h["source_id"] for h in pre.get("hits", [])}
        dele = http("POST", base, API + f"/sources/{src_del}/actions", body={"action": "delete", "confirmed": True})
        post = http("GET", base, API + "/search", params={"q": '"D-11"', "include_global": "true"})[1]
        post_ids = {h["source_id"] for h in post.get("hits", [])}
        ok = src_del in pre_ids and dele[0] == 200 and src_del not in post_ids and post.get("hits") == []
        record(
            "ACL-6 deleted source no cached snippet",
            "before hit, after empty",
            {"pre": sorted(pre_ids), "post": sorted(post_ids), "delete": dele[0]},
            ok,
        )

        # ---- ACL-7 global browsing = intended, never leaks *task-scoped* ----
        # Single-user browser owns all Tasks; unscoped browsing returns only
        # unscoped/global material.  Task-scoped sources (even ones this browser
        # owns) must NOT appear unscoped.  (Note: src_b was revoked above, so it
        # is absent for that reason too; assert on the still-active task sources.)
        status, payload = http("GET", base, API + "/search", params={"q": '"marker"'})
        ids = {h["source_id"] for h in payload.get("hits", [])}
        scopes = {h["scope"].get("task_ref") for h in payload.get("hits", [])}
        ok = (
            status == 200
            and src_g in ids
            and src_a not in ids
            and scopes <= {None}
        )
        record(
            "ACL-7 unscoped browsing = only global, never task-scoped",
            "global present; task_a excluded; all hits unscoped",
            {"status": status, "hits": sorted(ids), "task_scopes_present": sorted(s for s in scopes if s)},
            ok,
            notes="global owner unscoped access is intended; task-scoped must stay out",
        )
        RESULTS[-1]["source_g"] = src_g

        # ---- ACL-8 worker/member grant on source API: N/A by contract ------
        # Define applicability from the actual code/contract, not assumption.
        sys.path.insert(0, str(BACKEND))
        import inspect
        from lightgravity.api import search as search_mod, vector as vector_mod, sources as sources_mod

        srcs = search_mod.__file__ + vector_mod.__file__ + sources_mod.__file__
        has_worker = any(
            "worker_grant" in inspect.getsource(m) or "worker_identity" in inspect.getsource(m)
            for m in (search_mod, vector_mod, sources_mod)
        )
        record(
            "ACL-8 worker/member grant on source API",
            "not applicable (no worker principal on source/search/vector)",
            {"worker_principal_present": has_worker, "modules": [Path(p).name for p in (srcs,)]},
            not has_worker,
            notes="docs/08 §4.3/§6.6 defines no member grant for source/search/vector; "
            "worker_grant only wires api/collaboration.py",
        )

        # ---- ACL-9 Task-attribution ref check (narrowing vs true authz) ----
        status, payload = http("GET", base, API + "/search", params={"q": '"marker"', "task_ref": "task_does_not_exist"})
        ok = status == 200 and payload.get("hits") == []
        record(
            "ACL-9 unknown task_ref filter yields no hits",
            "empty (filter narrows, not grants)",
            {"status": status, "hits": payload.get("hits")},
            ok,
        )

        # ---- ACL-10 vector path shares same scope rules & no inference -----
        vstatus, vpayload = http("GET", base, API + "/vector/status")
        vsearch = http("GET", base, API + "/vector/search", params={"q": '"marker"', "task_ref": task_a})[1]
        ok = (
            vstatus == 200
            and vpayload.get("enabled") is False
            and vsearch.get("index_status") == "index_unavailable"
            and vsearch.get("hits") == []
        )
        record(
            "ACL-10 vector disabled -> honest, no leak, no inference",
            "enabled=false, index_unavailable, hits empty",
            {"status": vstatus, "enabled": vpayload.get("enabled"), "vsearch": vsearch.get("index_status")},
            ok,
        )

    finally:
        server.stop()
        # confirm port release
        time.sleep(0.5)
        released = True
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                released = s.connect_ex(("127.0.0.1", port)) != 0
        except OSError:
            released = True
        RESULTS.append({"case": "ACL-cleanup port released", "expected": True, "actual": released,
                        "result": "PASS" if released else "FAIL", "notes": f"port {port}"})

    out = {
        "harness": "lg040-api-r1 acl addendum",
        "port": port,
        "inference_calls": 0,
        "retries": 0,
        "cases": RESULTS,
        "summary": {
            "total": len(RESULTS),
            "pass": sum(1 for r in RESULTS if r["result"] == "PASS"),
            "fail": sum(1 for r in RESULTS if r["result"] == "FAIL"),
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["summary"]["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
